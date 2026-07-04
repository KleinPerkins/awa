"""gitutil.py — thin, read-mostly git adapter (zero-link, stdlib only).

Every git invocation is bounded by a timeout so a wedged repo cannot hang the
engine. The ignored-file scan is cache-free (untrackedCache + fsmonitor OFF) so a
just-written file is never missed (a known race that would silently defeat the
no-lost-work guarantee).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass


class GitError(RuntimeError):
    pass


def git(cwd: str, *args: str, timeout: float = 15.0, check: bool = False) -> tuple[int, str, str]:
    """Run `git -C cwd <args>`. Returns (rc, stdout, stderr). rc 124 = timeout."""
    try:
        proc = subprocess.run(
            ["git", "-C", cwd, *args],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        if check:
            raise GitError(f"git timed out: {' '.join(args)}")
        return 124, "", "timeout"
    except OSError as exc:
        if check:
            raise GitError(f"git not executable: {exc}")
        return 127, "", str(exc)
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed ({proc.returncode}): {proc.stderr.strip()}")
    return proc.returncode, proc.stdout, proc.stderr


def toplevel(cwd: str, timeout: float = 15.0) -> str | None:
    rc, out, _ = git(cwd, "rev-parse", "--show-toplevel", timeout=timeout)
    return out.strip() or None if rc == 0 else None


def git_dir(cwd: str, timeout: float = 15.0) -> str | None:
    rc, out, _ = git(cwd, "rev-parse", "--path-format=absolute", "--git-dir", timeout=timeout)
    return out.strip() or None if rc == 0 else None


def common_dir(cwd: str, timeout: float = 15.0) -> str | None:
    rc, out, _ = git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir", timeout=timeout)
    return out.strip() or None if rc == 0 else None


def is_linked_worktree(cwd: str, timeout: float = 15.0) -> bool:
    gd, cd = git_dir(cwd, timeout), common_dir(cwd, timeout)
    return bool(gd and cd and gd != cd)


def current_branch(cwd: str, timeout: float = 15.0) -> str | None:
    rc, out, _ = git(cwd, "rev-parse", "--abbrev-ref", "HEAD", timeout=timeout)
    branch = out.strip()
    return branch if rc == 0 and branch and branch != "HEAD" else None


def head_sha(cwd: str, timeout: float = 15.0) -> str | None:
    rc, out, _ = git(cwd, "rev-parse", "HEAD", timeout=timeout)
    return out.strip() or None if rc == 0 else None


def is_dirty(cwd: str, timeout: float = 15.0) -> bool:
    rc, out, _ = git(cwd, "status", "--porcelain", timeout=timeout)
    return bool(out.strip()) if rc == 0 else True  # unknown -> treat as dirty (safe)


def ignored_files(cwd: str, timeout: float = 30.0) -> list[str]:
    """Cache-free list of git-ignored files (paths relative to `cwd`).

    Forces untrackedCache + fsmonitor OFF and a full untracked scan so a file
    written microseconds earlier is never missed (racy-index defeat of no-lost-work).
    """
    rc, out, _ = git(
        cwd,
        "-c", "core.untrackedCache=false",
        "-c", "core.fsmonitor=false",
        "status", "--porcelain", "--ignored=matching", "--untracked-files=all",
        timeout=timeout,
    )
    if rc != 0:
        return []
    return [ln[3:] for ln in out.splitlines() if ln.startswith("!! ")]


def merge_base_is_ancestor(cwd: str, sha: str, ref: str, timeout: float = 15.0) -> bool:
    rc, _, _ = git(cwd, "merge-base", "--is-ancestor", sha, ref, timeout=timeout)
    return rc == 0


def ref_exists(cwd: str, ref: str, timeout: float = 15.0) -> bool:
    rc, _, _ = git(cwd, "show-ref", "--verify", "--quiet", ref, timeout=timeout)
    return rc == 0


@dataclass
class RepoContext:
    """Resolved git context for a working directory."""
    cwd: str
    toplevel: str | None
    git_dir: str | None
    common_dir: str | None
    branch: str | None
    head: str | None

    @property
    def is_linked(self) -> bool:
        return bool(self.git_dir and self.common_dir and self.git_dir != self.common_dir)

    @property
    def is_git(self) -> bool:
        return self.toplevel is not None


def resolve(cwd: str, timeout: float = 15.0) -> RepoContext:
    return RepoContext(
        cwd=cwd,
        toplevel=toplevel(cwd, timeout),
        git_dir=git_dir(cwd, timeout),
        common_dir=common_dir(cwd, timeout),
        branch=current_branch(cwd, timeout),
        head=head_sha(cwd, timeout),
    )
