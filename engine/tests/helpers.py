"""helpers.py — scratch git repos + isolated XDG state for the engine tests.

SAFETY (fork-bomb + clobber avoidance, per the mandate): every scratch repo lives in
the SYSTEM temp dir (outside ~/dev), so a `git commit` there has NO governed hooks
installed and can never chain into verify-operating-model -> worktree-verify (the
historical fork-bomb). A re-entrancy guard is set for defense-in-depth. Each test
points XDG_STATE_HOME/XDG_DATA_HOME/XDG_CONFIG_HOME at its own tmp so no test touches
the operator's real state.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

_IDENT = ("-c", "user.email=49759187+KleinPerkins@users.noreply.github.com",
          "-c", "user.name=KleinPerkins")


def git(cwd: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, check=check)


def commit_all(cwd: str, message: str) -> None:
    git(cwd, "add", "-A")
    subprocess.run(["git", "-C", cwd, *_IDENT, "commit", "-qm", message],
                   capture_output=True, text=True, check=True)


class EngineTestCase(unittest.TestCase):
    """Base case: isolated XDG dirs + a fresh scratch git repo with a linked worktree."""

    def setUp(self) -> None:
        os.environ["AWA_ENGINE_TEST_ACTIVE"] = "1"  # re-entrancy guard (defense-in-depth)
        self._tmp = tempfile.TemporaryDirectory(prefix="awa-engine-test.")
        base = Path(self._tmp.name)
        self.state_home = base / "state"
        self.data_home = base / "data"
        self.config_home = base / "config"
        for d in (self.state_home, self.data_home, self.config_home):
            d.mkdir(parents=True, exist_ok=True)
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
