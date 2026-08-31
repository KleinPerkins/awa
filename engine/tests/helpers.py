"""helpers.py — scratch git repos + isolated XDG state for the engine tests.

SAFETY (fork-bomb + clobber avoidance, per the mandate): every scratch repo lives in
the SYSTEM temp dir (outside ~/dev), so a `git commit` there has NO governed hooks
installed and can never chain into verify-operating-model -> worktree-verify (the
historical fork-bomb). A re-entrancy guard is set for defense-in-depth. Each test
points XDG_STATE_HOME/XDG_DATA_HOME/XDG_CONFIG_HOME at its own tmp so no test touches
the operator's real state.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Optional, Set, Tuple

_IDENT = ("-c", "user.email=49759187+KleinPerkins@users.noreply.github.com",
          "-c", "user.name=KleinPerkins")
_ACTIVE_TEST_ROOTS: Set[Path] = set()
_PROCESS_REPO_SEED: Optional["RepoSeed"] = None
_PROCESS_REPO_SEED_LOCK = threading.Lock()


def git(cwd: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, check=check)


def commit_all(cwd: str, message: str) -> None:
    git(cwd, "add", "-A")
    subprocess.run(["git", "-C", cwd, *_IDENT, "commit", "-qm", message],
                   capture_output=True, text=True, check=True)


def _private_mode(metadata: os.stat_result) -> int:
    return 0o700 if stat.S_ISDIR(metadata.st_mode) or metadata.st_mode & 0o100 else 0o600


def _make_tree_private(root: Path) -> None:
    paths = [root, *sorted(root.rglob("*"))]
    for path in paths:
        metadata = path.lstat()
        if path.is_symlink():
            raise RuntimeError(f"seed tree contains a symlink: {path}")
        if not stat.S_ISDIR(metadata.st_mode) and not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError(f"seed tree contains a special file: {path}")
        path.chmod(_private_mode(metadata))


def _tree_audit(root: Path) -> Tuple[str, Set[Tuple[int, int]]]:
    if not root.is_dir() or root.is_symlink():
        raise RuntimeError("seed root must be a real directory")
    if (root / ".git" / "objects" / "info" / "alternates").exists():
        raise RuntimeError("seed tree must not use object alternates")
    if (root / ".git" / "commondir").exists():
        raise RuntimeError("seed tree must own its common Git directory")

    digest = hashlib.sha256()
    inodes = set()
    paths = [root, *sorted(root.rglob("*"))]
    for path in paths:
        metadata = path.lstat()
        relative = "." if path == root else path.relative_to(root).as_posix()
        if path.is_symlink():
            raise RuntimeError(f"seed tree contains a symlink: {relative}")
        if stat.S_ISDIR(metadata.st_mode):
            kind = b"directory"
        elif stat.S_ISREG(metadata.st_mode):
            kind = b"file"
            inode = (metadata.st_dev, metadata.st_ino)
            if metadata.st_nlink != 1 or inode in inodes:
                raise RuntimeError(f"seed tree contains a hard link: {relative}")
            inodes.add(inode)
        else:
            raise RuntimeError(f"seed tree contains a special file: {relative}")
        if metadata.st_mode & 0o077:
            raise RuntimeError(f"seed tree permissions are not private: {relative}")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(kind)
        digest.update(b"\0")
        digest.update(oct(metadata.st_mode & 0o777).encode("ascii"))
        digest.update(b"\0")
        if kind == b"file":
            digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest(), inodes


def _build_seed_from_scratch(root: Path) -> None:
    root.mkdir(mode=0o700)
    git(str(root), "init", "-q", ".")
    (root / "README.md").write_text("# uat\n", encoding="utf-8")
    git(str(root), "add", "-A")
    commit_env = os.environ.copy()
    commit_env.update({
        "GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z",
        "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z",
    })
    subprocess.run(
        ["git", "-C", str(root), *_IDENT, "commit", "-qm", "init"],
        capture_output=True,
        text=True,
        check=True,
        env=commit_env,
    )
    git(str(root), "branch", "-M", "main")
    git(
        str(root),
        "remote",
        "add",
        "origin",
        "git@github.com:KleinPerkins/awa-test.git",
    )
    _make_tree_private(root)


def _active_test_destination(destination: Path) -> Path:
    if destination.exists() or destination.is_symlink():
        raise ValueError("seed destination must not exist")
    try:
        parent = destination.parent.resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise ValueError("seed destination parent must exist") from exc
    target = parent / destination.name
    for root in tuple(_ACTIVE_TEST_ROOTS):
        if target != root and root in target.parents:
            return target
    raise ValueError("seed destination must be beneath an active engine test root")


class RepoSeed:
    """One process-local, audited repository copied into independent test roots."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="awa-git-seed.")
        temporary_root = Path(self._tmp.name)
        temporary_root.chmod(0o700)
        self.root = temporary_root / "repo"
        _build_seed_from_scratch(self.root)
        self._sha256, self._inodes = _tree_audit(self.root)

    @property
    def sha256(self) -> str:
        return self._sha256

    def audit(self) -> str:
        digest, inodes = _tree_audit(self.root)
        if digest != self._sha256 or inodes != self._inodes:
            raise RuntimeError("process Git seed changed after publication")
        return digest

    def materialize(self, destination: Path, origin: bool = True) -> str:
        if type(origin) is not bool:
            raise TypeError("origin must be a bool")
        self.audit()
        target = _active_test_destination(Path(destination))
        try:
            shutil.copytree(
                self.root,
                target,
                symlinks=False,
                copy_function=shutil.copy2,
            )
            _make_tree_private(target)
            copied_digest, copied_inodes = _tree_audit(target)
            if copied_digest != self._sha256:
                raise RuntimeError("materialized Git seed bytes differ")
            if copied_inodes & self._inodes:
                raise RuntimeError("materialized Git seed shares an inode")
            if not origin:
                git(str(target), "remote", "remove", "origin")
                _make_tree_private(target)
                _tree_audit(target)
            self.audit()
            return str(target)
        except BaseException:
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            raise


def _process_repo_seed() -> RepoSeed:
    global _PROCESS_REPO_SEED
    if _PROCESS_REPO_SEED is None:
        with _PROCESS_REPO_SEED_LOCK:
            if _PROCESS_REPO_SEED is None:
                _PROCESS_REPO_SEED = RepoSeed()
    return _PROCESS_REPO_SEED


class EngineTestCase(unittest.TestCase):
    """Base case: isolated XDG dirs + a fresh scratch git repo with a linked worktree."""

    def setUp(self) -> None:
        os.environ["AWA_ENGINE_TEST_ACTIVE"] = "1"  # re-entrancy guard (defense-in-depth)
        self._tmp = tempfile.TemporaryDirectory(prefix="awa-engine-test.")
        base = Path(self._tmp.name)
        base.chmod(0o700)
        _ACTIVE_TEST_ROOTS.add(base.resolve())
        self.state_home = base / "state"
        self.data_home = base / "data"
        self.config_home = base / "config"
        for d in (self.state_home, self.data_home, self.config_home):
            d.mkdir(mode=0o700, parents=True, exist_ok=True)
            d.chmod(0o700)
        self._saved_env = {}
        for k, v in (("XDG_STATE_HOME", self.state_home),
                     ("XDG_DATA_HOME", self.data_home),
                     ("XDG_CONFIG_HOME", self.config_home)):
            self._saved_env[k] = os.environ.get(k)
            os.environ[k] = str(v)

    def tearDown(self) -> None:
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        _ACTIVE_TEST_ROOTS.discard(Path(self._tmp.name).resolve())
        self._tmp.cleanup()

    # ---- scratch repo builders ----------------------------------------------
    def make_repo(self, name: str = "repo", *, origin: bool = True) -> str:
        repo = str(Path(self._tmp.name) / name)
        os.makedirs(repo, exist_ok=True)
        git(repo, "init", "-q", ".")
        Path(repo, "README.md").write_text("# uat\n", encoding="utf-8")
        commit_all(repo, "init")
        git(repo, "branch", "-M", "main")
        if origin:
            git(repo, "remote", "add", "origin", "git@github.com:KleinPerkins/awa-test.git")
        return repo

    def make_seeded_repo(
        self,
        name: str = "repo",
        *,
        origin: bool = True,
        fresh: bool = False,
    ) -> str:
        if type(fresh) is not bool:
            raise TypeError("fresh must be a bool")
        if fresh:
            return self.make_repo(name, origin=origin)
        destination = Path(self._tmp.name) / name
        return _process_repo_seed().materialize(destination, origin=origin)

    def make_standalone_repo(self, name: str = "standalone-repo", *, origin: bool = True) -> str:
        """A scratch repo OUTSIDE self._tmp.name — i.e. outside any governed root the tests'
        policy fixtures configure. Used for is_standalone regression coverage. Lives in its
        own tempdir (a sibling of self._tmp.name, never nested under it) so it is a genuine
        standalone repo from the classifier's point of view.
        """
        tmp = tempfile.TemporaryDirectory(prefix="awa-engine-test-standalone.")
        self.addCleanup(tmp.cleanup)
        repo = str(Path(tmp.name) / name)
        os.makedirs(repo, exist_ok=True)
        git(repo, "init", "-q", ".")
        Path(repo, "README.md").write_text("# uat\n", encoding="utf-8")
        commit_all(repo, "init")
        git(repo, "branch", "-M", "main")
        if origin:
            git(repo, "remote", "add", "origin", "git@github.com:KleinPerkins/awa-test.git")
        return repo

    def add_worktree(self, repo: str, branch: str, suffix: str = ".wt") -> str:
        wt = repo + suffix
        git(repo, "worktree", "add", "-q", "-b", branch, wt, "main")
        return wt

    def add_bare_remote(self, repo: str, name: str = "origin.git") -> str:
        """Create a LOCAL bare repo and point `repo`'s origin at it (a reachable remote
        for end-to-end publish/quarantine tests — still fully offline, no network)."""
        bare = str(Path(self._tmp.name) / name)
        git(str(Path(self._tmp.name)), "init", "-q", "--bare", bare)
        # origin already exists (fake url) from make_repo; repoint it at the bare path.
        r = subprocess.run(["git", "-C", repo, "remote", "set-url", "origin", bare],
                           capture_output=True, text=True)
        if r.returncode != 0:
            git(repo, "remote", "add", "origin", bare)
        return bare
