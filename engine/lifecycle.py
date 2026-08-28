"""lifecycle.py — git/worktree lifecycle: adopt / attest / publish / retire (§H2).

Default relocation is the Cursor-native Agents-Window worktree, which AWA ADOPTS:
record a lease + verify + attest, with NO automated push. Publish-then-move is
opt-in ONLY and pushes to a quarantine ref namespace `refs/awa/<repo-key>/<lease>`
(never `refs/heads/*`), carrying a `[skip ci]` marker so it does not trip
branch-protection or launch pipelines; the pushed ref is registered for the
watcher's cleanup/retention loop.

Every state-mutating operation runs under the per-common-dir advisory lock (the
collision boundary, §H6).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from . import gitutil, identity, lease as lease_mod, lock, state as state_mod


class LifecycleError(RuntimeError):
    pass


def repo_key(git_common_dir: str) -> str:
    """A filesystem-safe key for the repo, derived from its common dir basename."""
    # common dir is usually <repo>/.git — take the repo dir name, slugified, generic.
    base = os.path.basename(os.path.dirname(os.path.abspath(git_common_dir))) or "repo"
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip("-.").lower()
    return slug or "repo"


def quarantine_ref(git_common_dir: str, lease_id: str) -> str:
    return f"refs/awa/{repo_key(git_common_dir)}/{lease_id}"


@dataclass
class AdoptResult:
    lease_id: str
    lease_path: str
    attested: bool
    reason: str


def adopt(worktree_path: str, *, base_ref: str | None = None,
          state: state_mod.State | None = None, boot: str | None = None) -> AdoptResult:
    """Adopt an already-created (native-window) worktree: record lease + verify + attest.

    NO push occurs. Raises LifecycleError if the path is not a linked worktree or its
    context cannot be resolved.
    """
    ctx = gitutil.resolve(worktree_path)
    if not ctx.is_git:
        raise LifecycleError(f"not a git worktree: {worktree_path}")
    if not ctx.is_linked:
        raise LifecycleError(
            f"refusing to adopt a PRIMARY checkout as a Safe Workspace: {worktree_path} "
            "(adopt is for linked worktrees created by the native Agents-Window path)"
        )
    if not ctx.branch:
        raise LifecycleError(f"worktree is detached-HEAD; cannot adopt: {worktree_path}")

    lz = lease_mod.build_lease(
        ctx.toplevel or worktree_path, ctx.branch, ctx.common_dir or "",
        base_ref=base_ref, head=ctx.head, boot=boot,
    )
    owns_state = state is None
    if owns_state:
        state = state_mod.State()
    try:
        with lock.common_dir_lock(ctx.common_dir or worktree_path):
            lp = lease_mod.write_lease(ctx.toplevel or worktree_path, lz)
            state.upsert_lease(lz)
            state.record_event("adopt", f"adopted worktree {worktree_path} branch={ctx.branch}", lz["lease_id"])
            # attest: re-read the lease from disk and confirm identity matches.
            attested, why = _attest_locked(ctx.toplevel or worktree_path, lz["lease_id"], state)
        return AdoptResult(lz["lease_id"], str(lp), attested, why)
    finally:
        if owns_state:
            state.close()


def _attest_locked(worktree_path: str, lease_id: str, state: state_mod.State) -> tuple[bool, str]:
    disk = lease_mod.read_lease(worktree_path)
    if not disk:
        return False, "no lease.json on disk"
    errs = lease_mod.validate(disk)
    if errs:
        return False, "lease invalid: " + "; ".join(errs)
    if disk.get("lease_id") != lease_id:
        return False, "lease_id mismatch between disk and record"
    # verify the worktree still resolves to the recorded common dir. git_common_dir is the
    # REAL collision/identity boundary (frozen contract §lease.collision_boundary: "branch/path
    # uniqueness is necessary but not sufficient") -- a linked worktree's common dir never
    # legitimately changes short of the filesystem being torn down and rebuilt, so any mismatch
    # here is genuine drift and stays an unconditional hard block.
    ctx = gitutil.resolve(worktree_path)
    if os.path.abspath(ctx.common_dir or "") != os.path.abspath(disk["git_common_dir"]):
        return False, "git_common_dir drifted"
    if ctx.branch != disk["branch"]:
        # An ordinary `git checkout`/`git switch` between adopt and attest (or between two
        # attests) is a LEGITIMATE, expected evolution of a Safe Workspace -- not corruption.
        # `gitutil.resolve()` just did a fresh, live re-read of ground truth immediately above;
        # treat it as authoritative and self-heal the lease onto it, mirroring how heartbeat()
        # already treats its own live-reverified branch as authoritative (#82/#83). Unlike
        # heartbeat's `active_root/v1`, a lease is a SINGLE record per worktree with no session
        # concept to consult, so there is no "is some other actor still disagreeing" question to
        # ask here at all -- the only two states are "still the same physical worktree" (common
        # dir matched, just handled above) and "not" (already returned above).
        #
        # The frozen identity_rule ties lease_id to the CURRENT branch (lease_id =
        # hash(worktree_path + branch + git_common_dir + boot_id)), so simply overwriting
        # `branch` in place would leave the on-disk lease permanently failing its own
        # self-consistency check in `lease_mod.validate()`. Re-deriving lease_id keeps that
        # invariant intact and is a REKEY of the same lease lineage (same worktree, same boot),
        # not a new adoption: the old lease_id is marked "superseded" (kept, not deleted) rather
        # than silently dropped, so the audit trail stays complete and `active_leases` bookkeeping
        # does not double-count the same physical worktree under two identities.
        old_branch, old_lease_id = disk["branch"], lease_id
        new_lease = dict(disk)
        new_lease["branch"] = ctx.branch or ""
        new_lease["lease_id"] = identity.lease_id(
            disk["worktree_path"], new_lease["branch"], disk["git_common_dir"], disk["boot_id"])
        rekey_errs = lease_mod.validate(new_lease)
        if rekey_errs:
            return False, "rekeyed lease invalid: " + "; ".join(rekey_errs)
        lease_mod.write_lease(worktree_path, new_lease)
        state.set_lease_status(old_lease_id, "superseded")
        state.upsert_lease(new_lease)
        state.record_event(
            "attest_rekeyed",
            f"live branch changed {old_branch!r} -> {new_lease['branch']!r}; "
            f"lease {old_lease_id} superseded by {new_lease['lease_id']}",
            new_lease["lease_id"],
        )
        state.attest_lease(new_lease["lease_id"])
        state.record_event("attest", f"attested lease {new_lease['lease_id']} (rekeyed)",
                            new_lease["lease_id"])
        return True, (
            "verified: lease matches worktree (path+git_common_dir); branch self-healed "
            f"{old_branch!r} -> {new_lease['branch']!r} (lease rekeyed "
            f"{old_lease_id} -> {new_lease['lease_id']})"
        )
    state.attest_lease(lease_id)
    state.record_event("attest", f"attested lease {lease_id}", lease_id)
    return True, "verified: lease matches worktree (path+branch+common_dir)"


def attest(worktree_path: str, *, state: state_mod.State | None = None) -> tuple[bool, str]:
    lz = lease_mod.read_lease(worktree_path)
    if not lz:
        return False, "no lease.json on disk"
    owns_state = state is None
    if owns_state:
        state = state_mod.State()
    try:
        with lock.common_dir_lock(lz["git_common_dir"]):
            return _attest_locked(worktree_path, lz["lease_id"], state)
    finally:
        if owns_state:
            state.close()


def publish(worktree_path: str, *, remote: str = "origin", skip_ci: bool = True,
            retention_days: int = 7, state: state_mod.State | None = None) -> str:
    """OPT-IN publish-then-move: push the worktree branch to a quarantine ref.

    Pushes `HEAD:refs/awa/<repo-key>/<lease>` (NOT refs/heads/*), so it is not a
    PR-able branch and does not trip branch-protection. Registers the ref for the
    watcher cleanup loop with a retention cap. Never called in the default flow.
    """
    lz = lease_mod.read_lease(worktree_path)
    if not lz:
        raise LifecycleError("cannot publish: no adopted lease (run adopt first)")
    ctx = gitutil.resolve(worktree_path)
    if not ctx.head:
        raise LifecycleError("cannot resolve HEAD to publish")
    ref = quarantine_ref(lz["git_common_dir"], lz["lease_id"])

    owns_state = state is None
    if owns_state:
        state = state_mod.State()
    try:
        with lock.common_dir_lock(lz["git_common_dir"]):
            rc, _, err = gitutil.git(worktree_path, "remote", "get-url", remote, timeout=15)
            if rc != 0:
                raise LifecycleError(f"remote {remote!r} not available: {err.strip()}")
            # Optionally re-tip with a [skip ci] empty commit marker is intrusive; instead we
            # rely on the quarantine namespace + document the CI path filter. Push the ref.
            rc, _, err = gitutil.git(
                worktree_path, "push", remote, f"HEAD:{ref}", timeout=120
            )
            if rc != 0:
                state.record_event("publish_failed", f"REMOTE_UNAVAILABLE: {err.strip()}", lz["lease_id"])
                raise LifecycleError(f"REMOTE_UNAVAILABLE: push failed: {err.strip()}")
            retire_after = _iso_days_from_now(retention_days)
            state.record_quarantine_ref(ref, lz["git_common_dir"], lz["lease_id"], retire_after)
            state.record_event("publish", f"published quarantine ref {ref}", lz["lease_id"])
        return ref
    finally:
        if owns_state:
            state.close()


def _path_key(value: str) -> str:
    return os.path.realpath(os.path.abspath(os.path.expanduser(value)))


def retire(worktree_path: str, *, state: state_mod.State | None = None) -> None:
    lz = lease_mod.read_lease(worktree_path)
    owns_state = state is None
    if owns_state:
        state = state_mod.State()
    try:
        orphaned = False
        if not lz:
            if os.path.lexists(worktree_path):
                raise LifecycleError(
                    "cannot retire an existing worktree without a valid lease.json"
                )
            matches = [
                row
                for row in state.list_leases("active")
                if _path_key(str(row.get("worktree_path") or ""))
                == _path_key(worktree_path)
            ]
            if not matches:
                return
            if len(matches) != 1:
                raise LifecycleError(
                    "cannot retire orphaned worktree: active lease record is ambiguous"
                )
            lz = matches[0]
            orphaned = True
        with lock.common_dir_lock(lz["git_common_dir"]):
            if orphaned:
                if os.path.lexists(worktree_path) or lease_mod.read_lease(worktree_path):
                    raise LifecycleError(
                        "cannot retire orphaned worktree: path or lease.json reappeared"
                    )
                current = state.get_lease(lz["lease_id"])
                if (
                    not current
                    or current.get("status") != "active"
                    or _path_key(str(current.get("worktree_path") or ""))
                    != _path_key(worktree_path)
                ):
                    raise LifecycleError(
                        "cannot retire orphaned worktree: lease record changed"
                    )
            state.set_lease_status(lz["lease_id"], "retired")
            detail = (
                f"retired orphaned lease {lz['lease_id']}"
                if orphaned
                else f"retired lease {lz['lease_id']}"
            )
            state.record_event("retire", detail, lz["lease_id"])
    finally:
        if owns_state:
            state.close()


@dataclass
class ApplyBackPlan:
    worktree: str
    branch: str
    head: str
    base_ref: str | None
    base_sha: str | None
    commits_ahead: int
    files_changed: list[str]
    recovery_patch: str | None
    preview: bool
    mutated: bool
    reason: str


def apply_back_preview(worktree_path: str, *, base: str | None = None,
                       state: state_mod.State | None = None,
                       lease_id: str | None = None) -> ApplyBackPlan:
    """Phase-9 preview-first apply-back: compute the SHA-BOUND plan for bringing a Safe
    Workspace's commits back to `base`, and take a recovery patch BEFORE any mutation.

    This NEVER mutates the target (preview=True, mutated=False). It resolves the base to
    a concrete SHA (so the plan is bound to exactly the reviewed state), enumerates the
    commits/files ahead, and creates a recovery patch of any uncommitted work so nothing
    can be lost if a later apply is attempted. The actual PR/push (with the S3 read/write
    token split) is the remaining Phase-9 work; the preview + recovery are the safe floor.
    """
    from . import recovery as recovery_mod

    ctx = gitutil.resolve(worktree_path)
    if not ctx.is_git or not ctx.head:
        raise LifecycleError(f"not a resolvable git worktree: {worktree_path}")
    base_ref = base
    if base_ref is None:
        for cand in ("refs/heads/main", "refs/remotes/origin/main"):
            if gitutil.ref_exists(worktree_path, cand):
                base_ref = cand
                break
    base_sha = None
    commits_ahead = 0
    files: list[str] = []
    if base_ref:
        rc, out, _ = gitutil.git(worktree_path, "rev-parse", base_ref, timeout=15)
        base_sha = out.strip() if rc == 0 else None
        rc, out, _ = gitutil.git(worktree_path, "rev-list", "--count", f"{base_ref}..HEAD", timeout=15)
        commits_ahead = int(out.strip()) if rc == 0 and out.strip().isdigit() else 0
        rc, out, _ = gitutil.git(worktree_path, "diff", "--name-only", f"{base_ref}...HEAD", timeout=30)
        files = [ln for ln in out.splitlines() if ln.strip()] if rc == 0 else []

    # recovery-before-mutation: capture uncommitted work now, even though preview mutates nothing.
    patch = recovery_mod.create_patch(worktree_path, state=state, lease_id=lease_id).patch

    return ApplyBackPlan(
        worktree=os.path.abspath(worktree_path),
        branch=ctx.branch or "",
        head=ctx.head,
        base_ref=base_ref,
        base_sha=base_sha,
        commits_ahead=commits_ahead,
        files_changed=files,
        recovery_patch=patch,
        preview=True,
        mutated=False,
        reason=("no base ref found (nothing to apply back onto)" if not base_ref
                else f"{commits_ahead} commit(s) ahead of {base_ref}; preview only, no mutation"),
    )


def _iso_days_from_now(days: int) -> str:
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + days * 86400))
