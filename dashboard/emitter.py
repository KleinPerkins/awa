#!/usr/bin/env python3
"""emitter.py — READ-ONLY status emitter for the AWA worktree dashboard (generic).

Emits a single ``awa-worktree/v1`` JSON document describing, for every governed repo
under the scanned root, its worktrees and each worktree's status **vs `main`**:
classification (include/exclude/advisory), primary-vs-linked, dirty state, ahead/behind
counts vs the repo's ``main`` base, and the last commit.

ZERO-LINK: this emitter carries NO org/host literals. The scanned root, include roots, and
classification all come from the machine-local policy (kernel/lib/awa_policy.py), resolved by
role via AWA_POLICY / AWA_GOVERNED_ROOT — never a hard-coded org path.

Contract:
  * READ-ONLY — only ever runs read-only ``git`` inspection; never writes/fetches/mutates.
  * BOUNDED — enumerates repos at shallow depth under the policy include roots plus the
    scanned root, and bounds every per-repo ``git`` probe with a timeout.
  * RESILIENT — a repo with no ``main`` base, detached HEAD, no origin, or a probe timeout
    degrades to a clearly-labelled row instead of failing the whole emit.

Usage:
  emitter.py [--root DIR] [--timeout SECONDS]

``--root`` defaults to the resolved governed root (AWA_GOVERNED_ROOT / first policy
governed root / cwd); tests point it at a throwaway tree.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# The generic kernel policy resolver is the single classifier — import it by role.
_AWA_HOME = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_AWA_HOME / "kernel" / "lib"))
import awa_policy  # noqa: E402

SCHEMA = "awa-worktree/v1"

# The engine launcher lives at <AWA_HOME>/bin/awa-engine.sh. The dashboard is render-only +
# agent-command refresh; this probe is READ-ONLY (it only reads the daemon pidfile) and additive
# (Phase-8: `environment.engine`), so the kernel contract + data-free seed stay byte-stable and
# the engine stays off the safety path.
ENGINE_LAUNCHER = _AWA_HOME / "bin" / "awa-engine.sh"


def _policy_path() -> str:
    env = os.environ.get("AWA_POLICY")
    if env:
        return env
    return str(_AWA_HOME / "kernel" / "policy" / "default-worktree-policy.yml")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def git(repo: str, *args: str, timeout: float) -> tuple[int, str]:
    """Run a read-only git command, bounded by `timeout`. Returns (rc, stdout).

    rc 124 signals a timeout; rc 127 an execution error. stderr is discarded.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", repo, *args],
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return 124, ""
    except OSError:
        return 127, ""
    return proc.returncode, proc.stdout


def is_git_repo(path: Path) -> bool:
    dot = path / ".git"
    return dot.is_dir() or dot.is_file()


def origin_owner_repo(repo: str, timeout: float) -> str:
    rc, out = git(repo, "config", "--get", "remote.origin.url", timeout=timeout)
    url = out.strip()
    if rc != 0 or not url or "github.com" not in url:
        return ""
    rest = url.split("github.com", 1)[1].lstrip(":/")
    if rest.endswith(".git"):
        rest = rest[:-4]
    parts = [p for p in rest.split("/") if p]
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    return ""


def classify_repo(repo: str, rel: str, cfg, timeout: float) -> tuple[str, str, str]:
    """Return (classification, reason, owner_repo) via the generic kernel policy resolver."""
    owner_repo = origin_owner_repo(repo, timeout)
    rc, out = git(repo, "config", "--get", "core.hooksPath", timeout=timeout)
    hooks_path = out.strip() if rc == 0 else ""
    rc, out = git(repo, "config", "--get", "remote.origin.url", timeout=timeout)
    has_origin = rc == 0 and bool(out.strip())
    cls, reason = awa_policy.classify(
        rel, repo, cfg, hooks_path=hooks_path, has_origin=has_origin, is_root=(rel == "."),
    )
    return cls, reason, owner_repo


def base_ref(repo: str, timeout: float) -> str | None:
    rc, _ = git(repo, "show-ref", "--verify", "--quiet", "refs/heads/main", timeout=timeout)
    if rc == 0:
        return "refs/heads/main"
    rc, _ = git(repo, "show-ref", "--verify", "--quiet", "refs/remotes/origin/main", timeout=timeout)
    if rc == 0:
        return "refs/remotes/origin/main"
    return None


def ab_status(ahead: int, behind: int) -> str:
    if ahead and behind:
        return "diverged"
    if ahead:
        return "ahead"
    if behind:
        return "behind"
    return "even"


def parse_worktrees(porcelain: str) -> list[dict]:
    blocks: list[dict] = []
    cur: dict = {}
    for line in porcelain.splitlines():
        if not line:
            if cur:
                blocks.append(cur)
                cur = {}
            continue
        if line.startswith("worktree "):
            if cur:
                blocks.append(cur)
            cur = {"path": line[len("worktree "):]}
        elif line.startswith("HEAD "):
            cur["head"] = line[len("HEAD "):]
        elif line.startswith("branch "):
            cur["branch_ref"] = line[len("branch "):]
        elif line == "detached":
            cur["detached"] = True
        elif line == "bare":
            cur["bare"] = True
        elif line == "locked" or line.startswith("locked "):
            cur["locked"] = True
        elif line == "prunable" or line.startswith("prunable "):
            cur["prunable"] = True
    if cur:
        blocks.append(cur)
    return blocks


def worktree_role(wt_path: str, timeout: float) -> tuple[bool, bool]:
    rc, git_dir = git(wt_path, "rev-parse", "--path-format=absolute", "--git-dir", timeout=timeout)
    if rc != 0:
        return False, False
    rc, common_dir = git(wt_path, "rev-parse", "--path-format=absolute", "--git-common-dir", timeout=timeout)
    if rc != 0:
        return False, False
    gd = git_dir.strip()
    cd = common_dir.strip()
    return gd == cd, bool(gd and cd and gd != cd)


def worktree_detail(wt_path: str, block: dict, base: str | None, timeout: float) -> dict:
    branch_ref = block.get("branch_ref", "")
    branch = branch_ref[len("refs/heads/"):] if branch_ref.startswith("refs/heads/") else ""
    detached = bool(block.get("detached")) or (not branch and not block.get("bare"))

    is_primary, is_linked = worktree_role(wt_path, timeout)

    head_short = ""
    rc, out = git(wt_path, "rev-parse", "--short", "HEAD", timeout=timeout)
    if rc == 0:
        head_short = out.strip()

    dirty_count = 0
    dirty = False
    rc, out = git(wt_path, "status", "--porcelain", timeout=timeout)
    status_timed_out = rc == 124
    if rc == 0:
        lines = [ln for ln in out.splitlines() if ln.strip()]
        dirty_count = len(lines)
        dirty = dirty_count > 0

    ahead = behind = 0
    if base is None:
        status = "no-base"
    elif status_timed_out:
        status = "unknown"
    else:
        rc, out = git(wt_path, "rev-list", "--left-right", "--count", f"{base}...HEAD", timeout=timeout)
        if rc == 0 and out.strip():
            parts = out.split()
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                behind, ahead = int(parts[0]), int(parts[1])
                status = ab_status(ahead, behind)
            else:
                status = "unknown"
        elif rc == 124:
            status = "unknown"
        else:
            status = "unknown"

    base_branch = base == "refs/heads/main" and branch == "main"

    last_commit_ts = None
    last_commit_subject = None
    rc, out = git(wt_path, "log", "-1", "--format=%cI%x00%s", timeout=timeout)
    if rc == 0 and out.strip():
        ts, _, subject = out.strip().partition("\x00")
        last_commit_ts = ts or None
        last_commit_subject = subject or None

    return {
        "path": wt_path,
        "branch": branch,
        "detached": detached,
        "is_primary": is_primary,
        "is_linked": is_linked,
        "locked": bool(block.get("locked")),
        "prunable": bool(block.get("prunable")),
        "head": head_short,
        "dirty": dirty,
        "dirty_count": dirty_count,
        "ahead": ahead,
        "behind": behind,
        "ab_status": status,
        "is_base_branch": base_branch,
        "last_commit_ts": last_commit_ts,
        "last_commit_subject": last_commit_subject,
    }


def branch_detail(repo: str, branch: str, base: str | None, timeout: float) -> dict:
    head_short = ""
    rc, out = git(repo, "rev-parse", "--short", f"refs/heads/{branch}", timeout=timeout)
    if rc == 0:
        head_short = out.strip()

    ahead = behind = 0
    if base is None:
        status = "no-base"
    else:
        rc, out = git(repo, "rev-list", "--left-right", "--count", f"{base}...refs/heads/{branch}", timeout=timeout)
        if rc == 0 and out.strip():
            parts = out.split()
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                behind, ahead = int(parts[0]), int(parts[1])
                status = ab_status(ahead, behind)
            else:
                status = "unknown"
        elif rc == 124:
            status = "unknown"
        else:
            status = "unknown"

    last_commit_ts = None
    last_commit_subject = None
    rc, out = git(repo, "log", "-1", "--format=%cI%x00%s", f"refs/heads/{branch}", timeout=timeout)
    if rc == 0 and out.strip():
        ts, _, subject = out.strip().partition("\x00")
        last_commit_ts = ts or None
        last_commit_subject = subject or None

    return {
        "branch": branch,
        "head": head_short,
        "ahead": ahead,
        "behind": behind,
        "ab_status": status,
        "last_commit_ts": last_commit_ts,
        "last_commit_subject": last_commit_subject,
    }


def engine_status(timeout: float) -> dict:
    """READ-ONLY probe of the AWA engine daemon (Phase-8 engine-backed dashboard).

    Any absence/failure/timeout degrades to the honest ``engine off — kernel guard active``
    state, because the kernel guarantee holds with the engine OFF (kernel-first).
    """
    # `reason` is the internal mechanism note; `plain` is the jargon-free line the operator reads.
    _PLAIN_OFF = "I step in the moment you try to change something. The always-watching-in-the-background part isn't switched on here."
    _PLAIN_ON = "I'm watching continuously in the background, on top of stepping in at each change."
    off = lambda reason: {"engine": {"running": False, "mode": "off", "reason": reason, "plain": _PLAIN_OFF}}
    if not ENGINE_LAUNCHER.exists():
        return off("engine launcher not present")
    try:
        proc = subprocess.run(
            [str(ENGINE_LAUNCHER), "daemon", "status"],
            text=True, capture_output=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return off("engine probe timed out")
    except OSError as exc:
        return off(f"engine probe error: {exc}")
    try:
        running = bool(json.loads(proc.stdout).get("daemon", {}).get("running"))
    except (ValueError, AttributeError):
        return off("engine probe returned unparseable status")
    if running:
        return {"engine": {"running": True, "mode": "running",
                           "reason": "AWA daemon holds the single-instance lock (observation + bookkeeping)",
                           "plain": _PLAIN_ON}}
    return off("engine off — kernel guard active")


# ---- PM-facing plain rendering (dashboard + status honest-confidence surface) ---------------
# These map the read-only mechanism facts above into jargon-free, HONEST operator language. No
# Tier A/B/C term ever appears in a `plain_*` value; the system-wide egress gate scans the REAL
# emitted plain values (built over a synthetic multi-repo tree) and bites on any regression.
# The mechanism fields (ab_status, dirty, detached, ...) stay as-is for the technical view.

def _plain_worktree(wt: dict) -> dict:
    """(plain_status, plain_next) for one working area, in plain operator language."""
    if wt.get("is_primary") and not wt.get("is_linked"):
        return {"plain_status": "Your original folder. I keep new work out of here until it is in a safe copy.",
                "plain_next": "Nothing to do — this is where finished work lands."}
    if wt.get("prunable"):
        return {"plain_status": "This safe copy is already gone from disk.",
                "plain_next": "Safe to tidy away from the list."}
    if wt.get("locked"):
        return {"plain_status": "This safe copy is marked in-use right now.",
                "plain_next": "Leave it until whoever is using it is finished."}

    st = wt.get("ab_status")
    unsaved = (f"{wt.get('dirty_count', 0)} unsaved change(s) waiting to be kept safe. "
               if wt.get("dirty") else "")

    if wt.get("detached"):
        return {"plain_status": unsaved + "This safe copy is not tied to a named piece of work yet.",
                "plain_next": "Give it a name before tidying up, so nothing is lost."}
    if st == "no-base":
        return {"plain_status": unsaved + "There is no shared version here to compare against yet.",
                "plain_next": "Set up the shared version so I can tell you where this stands."}
    if st == "even":
        return {"plain_status": unsaved + "Up to date with the shared version.",
                "plain_next": "Save your changes when ready." if wt.get("dirty") else "Nothing to do."}
    if st == "ahead":
        return {"plain_status": unsaved + f"Has {wt.get('ahead', 0)} saved step(s) not yet in the shared version.",
                "plain_next": "Ready to bring this work into the shared version."}
    if st == "behind":
        return {"plain_status": unsaved + f"The shared version has {wt.get('behind', 0)} newer step(s) this copy does not have yet.",
                "plain_next": "Refresh from the shared version before doing more here."}
    if st == "diverged":
        return {"plain_status": unsaved + "This copy and the shared version have moved apart.",
                "plain_next": "These need reconciling before this work can be brought in."}
    return {"plain_status": unsaved + "I could not finish checking this copy in time.",
            "plain_next": "Try refreshing; if it keeps happening, this copy needs a closer look."}


def _plain_repo(cls: str, has_base: bool) -> dict:
    """plain_next for a whole project, from its protection setting + shared-version presence."""
    if cls == "exclude":
        return {"plain_next": "I leave this project alone — it looks after itself."}
    if cls == "advisory":
        return {"plain_next": "I warn but do not stop changes here. Work in a safe copy to be sure."}
    if not has_base:
        return {"plain_next": "Set up a shared version here so I can compare your work against it."}
    return {"plain_next": "I set up a safe copy before any changes are made here."}


def _plain_orphan(br: dict) -> dict:
    """plain_status/plain_next for a left-over safe copy that is not open anywhere."""
    st = br.get("ab_status")
    if st == "ahead":
        return {"plain_status": f"A left-over safe copy with {br.get('ahead', 0)} saved step(s) not in the shared version.",
                "plain_next": "Make sure those saved steps are kept somewhere, then it is safe to tidy away."}
    if st == "even":
        return {"plain_status": "A left-over safe copy with nothing unique in it.",
                "plain_next": "Safe to tidy away."}
    if st == "behind":
        return {"plain_status": "A left-over safe copy that is older than the shared version.",
                "plain_next": "Usually safe to tidy away."}
    if st == "diverged":
        return {"plain_status": "A left-over safe copy that moved apart from the shared version.",
                "plain_next": "Check what is unique in it before tidying it away."}
    if st == "no-base":
        return {"plain_status": "A left-over safe copy with no shared version to compare to.",
                "plain_next": "Check what is in it before tidying it away."}
    return {"plain_status": "A left-over safe copy I could not fully check.",
            "plain_next": "Take a closer look before tidying it away."}


def _plain_summary(summary: dict, environment: dict) -> dict:
    """Top-level HONEST-CONFIDENCE block: what I checked, and what I explicitly can't promise."""
    included = summary.get("included", 0)
    excluded = summary.get("excluded", 0)
    dirty = summary.get("dirty", 0)
    orphans = summary.get("orphan_branches", 0)
    running = bool(environment.get("engine", {}).get("running"))

    headline = f"I am protecting {included} project(s) under this folder."
    if excluded:
        headline += f" {excluded} project(s) are set to be left alone."

    bits = []
    if dirty:
        bits.append(f"{dirty} safe copy(ies) have unsaved changes")
    if orphans:
        bits.append(f"{orphans} left-over safe copy(ies) to review")
    attention = ("Needs a look: " + "; ".join(bits) + ".") if bits else "Nothing needs your attention right now."

    return {
        "headline": headline,
        # Honest confidence — name exactly what this snapshot verified...
        "checked": ("What I checked: for every protected project I looked at each safe copy and "
                    "compared it to the shared version, and I counted anything left unsaved or left over."),
        # ...and what it did NOT / cannot verify.
        "not_checked": ("What I can't promise: this is a snapshot from just now, so it can't show "
                        "changes made since. I can only NOTICE a direct edit to your original files "
                        "after it happens — I can't stop that kind of edit in advance. And I don't "
                        "judge whether your work is correct, only where it lives."),
        "watching": (environment.get("engine", {}) or {}).get("plain",
                     "I step in the moment you try to change something."),
        "attention": attention,
    }


def mode_scan_bases(cfg) -> list[str]:
    """First non-wildcard path prefix of each explicit-mode key.

    Dashboard enumeration hint: a repo configured ONLY via a ``modes:`` entry (an explicit
    OFF/ON repo that sits outside the include globs) would otherwise never be
    discovered. e.g. modes {'projects/*': on, 'personal/legacy': off} -> ['projects',
    'personal/legacy']. A prefix may be a directory of repos (scan its children) or name a
    repo directly (the base itself is the repo).
    """
    bases: list[str] = []
    for key in cfg.modes:
        seg = str(key).split("*", 1)[0].rstrip("/")
        if seg and seg not in bases:
            bases.append(seg)
    return bases


def enumerate_repos(root: Path, cfg) -> list[Path]:
    """Scanned root + shallow git-repo children of the policy include roots + mode-only roots.

    Absent include-root hints (standalone default), also shallow-scan the direct children of
    the root so sibling repos under a governed root are still discovered.     Mode-configured
    roots (from ``modes:`` keys) are additionally enumerated so explicitly-set OFF/ON
    repos outside the include globs still surface — a scan base may be a directory of repos
    or (for an exact mode key) the repo itself.
    """
    repos: list[Path] = []
    seen: set[str] = set()

    def add(p: Path) -> None:
        if is_git_repo(p) and str(p) not in seen:
            repos.append(p)
            seen.add(str(p))

    add(root)
    inc_roots = awa_policy.include_roots(cfg)
    scan_bases = [root / r for r in inc_roots] if inc_roots else [root]
    for seg in mode_scan_bases(cfg):
        base = root / seg
        if base not in scan_bases:
            scan_bases.append(base)
    for base in scan_bases:
        if not base.is_dir():
            continue
        add(base)  # an exact mode key can name a repo directly
        for child in sorted(base.iterdir()):
            if child.is_dir():
                add(child)
    return repos


def build(root: Path, timeout: float) -> dict:
    root = root.resolve()
    cfg = awa_policy.PolicyConfig.load(_policy_path())
    default_base = "main"
    repos_out: list[dict] = []

    summary = {
        "repos": 0,
        "included": 0,
        "excluded": 0,
        "advisory": 0,
        "worktrees": 0,
        "linked": 0,
        "dirty": 0,
        "ahead_of_main": 0,
        "behind_main": 0,
        "diverged": 0,
        "no_base": 0,
        "orphan_branches": 0,
    }

    for repo in enumerate_repos(root, cfg):
        repo_str = str(repo)
        rel = awa_policy.rel_to_root(repo_str, str(root))
        cls, reason, owner_repo = classify_repo(repo_str, rel, cfg, timeout)

        # Resolved explicit mode (additive-within-v1): "" (no matching modes entry),
        # a valid value (on|off), or "invalid" when a matching entry carries an
        # unrecognized value (e.g. a removed legacy value). mode_error is populated only for
        # the invalid case; the repo still classifies protected/include via the fail-safe rule.
        raw_mode = awa_policy.mode_for(rel, cfg)
        if raw_mode == "":
            mode = ""
            mode_error = ""
        elif raw_mode in awa_policy.MODE_VALUES:
            mode = raw_mode
            mode_error = ""
        else:
            mode = "invalid"
            mode_error = f"invalid mode value {raw_mode!r} for '{rel}' (expected one of {', '.join(awa_policy.MODE_VALUES)})"

        base = base_ref(repo_str, timeout)

        rc, out = git(repo_str, "worktree", "list", "--porcelain", timeout=timeout)
        worktrees: list[dict] = []
        if rc == 0:
            for block in parse_worktrees(out):
                if block.get("bare"):
                    continue
                wt_path = block.get("path", "")
                if not wt_path:
                    continue
                wt = worktree_detail(wt_path, block, base, timeout)
                wt.update(_plain_worktree(wt))  # additive jargon-free PM fields
                worktrees.append(wt)

        branches: list[str] = []
        rc, out = git(repo_str, "for-each-ref", "--format=%(refname:short)", "refs/heads", timeout=timeout)
        if rc == 0:
            branches = [b for b in (ln.strip() for ln in out.splitlines()) if b]
        attached_branches = {wt["branch"] for wt in worktrees if wt.get("branch")}
        orphan_branches = []
        for b in branches:
            if b.startswith("cursor/worktree/") and b not in attached_branches:
                br = branch_detail(repo_str, b, base, timeout)
                br.update(_plain_orphan(br))  # additive jargon-free PM fields
                orphan_branches.append(br)

        repos_out.append({
            "path": repo_str,
            "rel": rel,
            "name": repo.name,
            "classification": cls,
            "reason": reason,
            "mode": mode,
            "mode_error": mode_error,
            "owner_repo": owner_repo,
            "has_base": base is not None,
            "base_ref": base or "",
            "default_base": default_base,
            "branches": branches,
            "orphan_branches": orphan_branches,
            "worktrees": worktrees,
            **_plain_repo(cls, base is not None),  # additive jargon-free PM field (plain_next)
        })

        summary["repos"] += 1
        # classify() emits only include|exclude|advisory (never a mode value); .get() keeps
        # this resilient to any future open-vocabulary classification value.
        skey = {"include": "included", "exclude": "excluded", "advisory": "advisory"}.get(cls)
        if skey:
            summary[skey] += 1
        for wt in worktrees:
            summary["worktrees"] += 1
            if wt["is_linked"]:
                summary["linked"] += 1
            if wt["dirty"]:
                summary["dirty"] += 1
            if wt["ahead"] > 0:
                summary["ahead_of_main"] += 1
            if wt["behind"] > 0:
                summary["behind_main"] += 1
            if wt["ahead"] > 0 and wt["behind"] > 0:
                summary["diverged"] += 1
            if wt["ab_status"] == "no-base":
                summary["no_base"] += 1
        summary["orphan_branches"] += len(orphan_branches)

    environment = engine_status(timeout)
    return {
        "schema": SCHEMA,
        "generated_at": now_iso(),
        "root": str(root),
        "default_base": default_base,
        "summary": summary,
        "plain": _plain_summary(summary, environment),  # PM-facing honest-confidence block
        "repos": repos_out,
        "environment": environment,
    }


def render_status_lines(doc: dict) -> list[str]:
    """Plain-language HONEST status report (surface: doctor/status), built ONLY from the jargon-free
    ``plain`` / ``plain_*`` fields this emitter already computes. It never authors a mechanism term
    of its own — every line traces to a scanned plain field — so the system-wide egress gate scans
    this exact render (over a synthetic tree) and bites on any regression. Project NAMES are operator
    data (echoed verbatim), not AWA copy; the gate scopes AWA's own jargon, not operator naming."""
    p = doc.get("plain", {}) or {}
    lines: list[str] = [p[k] for k in ("headline", "checked", "not_checked", "watching", "attention")
                        if p.get(k)]
    for repo in doc.get("repos", []) or []:
        name = repo.get("name", "this project")
        if repo.get("plain_next"):
            lines.append(f"{name}: {repo['plain_next']}")
        for wt in repo.get("worktrees", []) or []:
            if wt.get("plain_status"):
                lines.append(f"{name}: {wt['plain_status']}")
        for br in repo.get("orphan_branches", []) or []:
            if br.get("plain_status"):
                lines.append(f"{name}: {br['plain_status']}")
    return lines


def _default_root() -> Path:
    env_root = os.environ.get("AWA_GOVERNED_ROOT")
    if env_root:
        return Path(os.path.expanduser(env_root))
    cfg = awa_policy.PolicyConfig.load(_policy_path())
    if cfg.governed_roots:
        return Path(os.path.expanduser(cfg.governed_roots[0]))
    return Path.cwd()


def main(argv: list[str]) -> int:
    root = _default_root()
    timeout = float(os.environ.get("AWA_DASHBOARD_GIT_TIMEOUT", "4"))
    plain = False
    i = 1
    while i < len(argv):
        arg = argv[i]
        if arg == "--root":
            i += 1
            root = Path(argv[i])
        elif arg == "--timeout":
            i += 1
            timeout = float(argv[i])
        elif arg == "--plain":
            plain = True  # PM-facing jargon-free status text (surface: doctor/status)
        elif arg in ("-h", "--help"):
            print(__doc__)
            return 0
        else:
            print(f"emitter: unknown argument: {arg}", file=sys.stderr)
            return 2
        i += 1

    doc = build(root, timeout)
    if plain:
        for line in render_status_lines(doc):
            print(line)
        return 0
    json.dump(doc, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
