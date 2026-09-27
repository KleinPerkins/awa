"""gitutil.py — thin, read-mostly git adapter (zero-link, stdlib only).

Every git invocation is bounded by a timeout so a wedged repo cannot hang the
engine. The ignored-file scan is cache-free (untrackedCache + fsmonitor OFF) so a
just-written file is never missed (a known race that would silently defeat the
no-lost-work guarantee).
"""

from __future__ import annotations

import concurrent.futures
import subprocess
from dataclasses import dataclass
from typing import Mapping


class GitError(RuntimeError):
    pass


def git(
    cwd: str,
    *args: str,
    timeout: float = 15.0,
    check: bool = False,
    env: Mapping[str, str] | None = None,
) -> tuple[int, str, str]:
    """Run `git -C cwd <args>`. Returns (rc, stdout, stderr). rc 124 = timeout."""
    try:
        proc = subprocess.run(
            ["git", "-C", cwd, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
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


def resolve(
    cwd: str,
    timeout: float = 15.0,
    *,
    env: Mapping[str, str] | None = None,
) -> RepoContext:
    def identity_probe() -> tuple[int, str, str]:
        return git(
            cwd,
            "rev-parse",
            "--show-toplevel",
            "--path-format=absolute",
            "--git-dir",
            "--git-common-dir",
            timeout=timeout,
            env=env,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        identity_future = executor.submit(identity_probe)
        branch_future = executor.submit(
            git,
            cwd,
            "rev-parse",
            "--abbrev-ref",
            "HEAD",
            timeout=timeout,
            env=env,
        )
        head_future = executor.submit(
            git,
            cwd,
            "rev-parse",
            "HEAD",
            timeout=timeout,
            env=env,
        )
        identity_rc, identity_out, _ = identity_future.result()
        branch_rc, branch_out, _ = branch_future.result()
        head_rc, head_out, _ = head_future.result()
    identity_lines = identity_out.splitlines() if identity_rc == 0 else []
    complete = len(identity_lines) == 3
    branch = branch_out.strip() if branch_rc == 0 else None
    head = head_out.strip() if head_rc == 0 else None
    return RepoContext(
        cwd=cwd,
        toplevel=identity_lines[0] if complete else None,
        git_dir=identity_lines[1] if complete else None,
        common_dir=identity_lines[2] if complete else None,
        branch=(
            branch
            if branch and branch not in {"HEAD", "(detached)"}
            else None
        ),
        head=(
            head
            if head and head not in {"(initial)", "(unknown)"}
            else None
        ),
    )
