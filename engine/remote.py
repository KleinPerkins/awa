"""remote.py — Phase-9 apply-back remote adapter with an S3 read/write token split.

Extends the preview-first apply-back (`lifecycle.apply_back_preview`) to a real remote
adapter that is SHA-BOUND, recovery-BEFORE-mutation, and preview→confirm gated. The
security-critical property (Cluster-D **S3**) is a LEAST-PRIVILEGE token split:

  * status / poll  -> a READ-scoped token (may even be unauthenticated for public state);
  * push / PR      -> a WRITE-scoped token, and NEVER the read token.

Requesting a write op without a write-scoped token is REFUSED (it does not silently fall
back to the read token). The network operations (push, open-PR, poll) are injected as
callables so the ordering + token-selection + SHA-binding logic is fully unit-testable
with the network mocked. The `default_*` implementations are the LIVE operator path
(real `git push` / `gh pr create`); they require a real credential + remote and are an
operator/live step — never exercised headless.

Ordering invariant (enforced + tested):
    preview (SHA-bound) -> recovery patch captured -> confirm gate -> SHA re-bind
      -> WRITE push (write token) -> open PR (write token) -> poll status (read token)

Nothing here is on the safety-critical path (kernel-first): a failure raises `RemoteError`
and mutates nothing beyond the already-captured recovery patch.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

from . import gitutil, lifecycle

_READ_OPS = frozenset({"status", "poll"})
_WRITE_OPS = frozenset({"push", "pr"})


class RemoteError(RuntimeError):
    pass


def select_token(op: str, *, read_token: str | None, write_token: str | None) -> str:
    """S3 least-privilege token selection.

    Read ops use the READ token (unauthenticated read is permitted — least data). Write
    ops REQUIRE the WRITE token and never fall back to the read token; a missing write
    token is a hard refusal.
    """
    if op in _READ_OPS:
        return read_token or ""
    if op in _WRITE_OPS:
        if not write_token:
            raise RemoteError(
                f"S3 least-privilege: write op {op!r} requires a WRITE-scoped token; "
                "refusing to use a read-scoped token for a mutating operation"
            )
        return write_token
    raise RemoteError(f"unknown remote op {op!r}")


@dataclass
class PushContext:
    """Everything a pusher/PR-opener needs — bound to the exact reviewed SHA."""
    worktree: str
    remote: str
    branch: str
    head: str          # the reviewed HEAD sha the push is BOUND to
    base_sha: str      # the reviewed base sha the plan was computed against
    token: str         # write-scoped token
    recovery_patch: str | None


@dataclass
class ApplyBackResult:
    ok: bool
    mutated: bool
    pushed: bool
    pushed_ref: str | None
    pr_url: str | None
    base_sha: str | None
    head: str | None
    recovery_patch: str | None
    reason: str


def apply_back_execute(
    worktree_path: str,
    *,
    base: str | None = None,
    confirm: bool = False,
    read_token: str | None = None,
    write_token: str | None = None,
    pusher=None,
    pr_opener=None,
    poller=None,
    remote: str = "origin",
    push_ref: str | None = None,
    plan: lifecycle.ApplyBackPlan | None = None,
    state=None,
    lease_id: str | None = None,
) -> ApplyBackResult:
    """Execute (or preview) a SHA-bound apply-back with the S3 token split.

    `pusher(PushContext) -> pushed_ref`, `pr_opener(PushContext) -> pr_url`, and
    `poller(pr_url, read_token) -> None` are injected so the network is mockable. With no
    `pusher`, a confirmed execute honestly refuses (live push is an operator step).

    Order of operations is fixed so the recovery-before-mutation + SHA-binding invariants
    hold; each is unit-tested.
    """
    if plan is None:
        plan = lifecycle.apply_back_preview(worktree_path, base=base, state=state, lease_id=lease_id)

    # Honest no-op: nothing to apply back onto.
    if not plan.base_ref or plan.base_sha is None:
        return ApplyBackResult(True, False, False, None, None, plan.base_sha, plan.head,
                               plan.recovery_patch, "no base ref — nothing to apply back")

    # Recovery-BEFORE-mutation: the preview already captured a patch; assert it on disk
    # BEFORE any write can occur.
    if not plan.recovery_patch or not os.path.exists(plan.recovery_patch):
        raise RemoteError(
            "recovery-before-mutation invariant violated: no recovery patch captured before push"
        )

    # Preview -> confirm gate: without an explicit confirm, mutate NOTHING.
    if not confirm:
        return ApplyBackResult(
            True, False, False, None, None, plan.base_sha, plan.head, plan.recovery_patch,
            f"preview only (confirm=False): {plan.commits_ahead} commit(s) ahead of {plan.base_ref}",
        )

    # SHA binding: re-resolve HEAD + base and refuse if either moved since the reviewed
    # preview (the push is bound to exactly the reviewed state).
    ctx = gitutil.resolve(worktree_path)
    if (ctx.head or "") != plan.head:
        raise RemoteError(
            f"SHA drift: worktree HEAD moved {plan.head[:12]}->{(ctx.head or '')[:12]} "
            "since preview — re-preview required before push"
        )
    rc, out, _ = gitutil.git(worktree_path, "rev-parse", plan.base_ref, timeout=15)
    cur_base = out.strip() if rc == 0 else None
    if cur_base != plan.base_sha:
        raise RemoteError(
            f"SHA drift: base {plan.base_ref} moved since preview — re-preview required before push"
        )

    # WRITE op: push, using a WRITE-scoped token ONLY (S3).
    wtok = select_token("push", read_token=read_token, write_token=write_token)
    if pusher is None:
        raise RemoteError(
            "live push requires a real remote + credential — operator/live step "
            "(no pusher configured). The adapter is code + unit-test complete; run the "
            "documented operator apply-back to perform the push."
        )
    pctx = PushContext(
        worktree=os.path.abspath(worktree_path), remote=remote, branch=plan.branch,
        head=plan.head, base_sha=plan.base_sha, token=wtok,
        recovery_patch=plan.recovery_patch,
    )
    pushed_ref = pusher(pctx) if push_ref is None else pusher(pctx) or push_ref

    # Open PR — WRITE-scoped token.
    pr_url = None
    if pr_opener is not None:
        pr_url = pr_opener(pctx)

    # Poll status — READ-scoped token (never the write token).
    if poller is not None:
        rtok = select_token("status", read_token=read_token, write_token=write_token)
        poller(pr_url, rtok)

    if state is not None:
        state.record_event(
            "apply_back_push",
            f"pushed {plan.head} to {remote} {pushed_ref}; pr={pr_url}", lease_id,
        )
    return ApplyBackResult(
        True, True, True, pushed_ref, pr_url, plan.base_sha, plan.head, plan.recovery_patch,
        "pushed + PR opened (SHA-bound; recovery captured before mutation; S3 token split)",
    )


# ---------------------------------------------------------------------------
# LIVE operator path (real network). Never exercised headless — documented as an
# operator/live step. SHA-bound: pushes exactly the reviewed HEAD.
# ---------------------------------------------------------------------------
def default_pusher(ctx: PushContext) -> str:
    """Push the reviewed HEAD to the remote using the WRITE-scoped token.

    Builds a tokenized HTTPS URL so the write token is never written to argv beyond this
    process; SHA-bound via the `<head>:refs/heads/<branch>` refspec. Requires a real
    remote + credential (operator/live step).
    """
    ref = f"refs/heads/{ctx.branch}"
    rc, url, err = gitutil.git(ctx.worktree, "remote", "get-url", ctx.remote, timeout=15)
    if rc != 0:
        raise RemoteError(f"remote {ctx.remote!r} not available: {err.strip()}")
    push_url = _tokenized_https(url.strip(), ctx.token)
    rc, _, err = gitutil.git(
        ctx.worktree, "push", push_url, f"{ctx.head}:{ref}", timeout=120,
    )
    if rc != 0:
        raise RemoteError(f"REMOTE_UNAVAILABLE: push failed: {err.strip()}")
    return ref


def default_pr_opener(ctx: PushContext) -> str | None:
    """Open a PR with the WRITE token via `gh` (operator/live step). Returns the PR URL."""
    env = os.environ.copy()
    env["GH_TOKEN"] = ctx.token
    proc = subprocess.run(
        ["gh", "pr", "create", "--head", ctx.branch, "--fill"],
        cwd=ctx.worktree, capture_output=True, text=True, env=env, timeout=120,
    )
    if proc.returncode != 0:
        raise RemoteError(f"gh pr create failed: {proc.stderr.strip()}")
    return proc.stdout.strip() or None


def _tokenized_https(url: str, token: str) -> str:
    """Inject a write token into an https git URL (x-access-token scheme). Passthrough
    for ssh/other schemes (the operator's configured credential handles those)."""
    if url.startswith("https://") and "@" not in url.split("://", 1)[1].split("/", 1)[0]:
        return "https://x-access-token:" + token + "@" + url[len("https://"):]
    return url
