"""Phase 5: minimal local guard — kernel guarantee with the engine OFF (degraded mode).

These tests deliberately NEVER start the daemon and NEVER open the SQLite state, to
prove the guarantee holds with the engine dead/never-started: mutating primary ->
ask, worktree/lease -> allow, unsafe cleanup refused.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from engine import guard, lifecycle
from engine.tests.helpers import EngineTestCase, commit_all

_POLICY_YAML = """\
version: 1
governed_roots:
  - {root}
default: include
include:
  - '*'
exclude:
  - .
detectors:
  governed_markers:
    - _ops/POLICY.md
  foreign_hook_frameworks:
    - husky
"""


class TestMutatingClassifier(unittest.TestCase):
    def test_adversarial_bypasses(self):
        for cmd in ("git -C . commit -m x", "git -c user.name=x commit",
                    "sed -i s/a/b/ f", "echo pwned > f", "rm -rf x",
                    "npm install", "perl -i -pe s/a/b/ f"):
            self.assertTrue(guard.classify_mutating(cmd), cmd)

    def test_read_only_allowed(self):
        for cmd in ("git status", "git log --oneline", "ls -la", "cat f",
                    "echo hi > /dev/null", "grep x f"):
            self.assertFalse(guard.classify_mutating(cmd), cmd)


class TestDecideShellDegraded(EngineTestCase):
    def _policy_for(self, root: str) -> str:
        p = tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False)
        p.write(_POLICY_YAML.format(root=root))
        p.close()
        return p.name

    def test_primary_mutation_asks(self):
        repo = self.make_repo()
        pol = self._policy_for(self._tmp.name)
        d = guard.decide_shell(repo, "git commit -am x", pol)
        self.assertEqual(d.permission, "ask")

    def test_primary_readonly_allows(self):
        repo = self.make_repo()
        pol = self._policy_for(self._tmp.name)
        d = guard.decide_shell(repo, "git status", pol)
        self.assertEqual(d.permission, "allow")

    def test_worktree_allows_without_engine(self):
        repo = self.make_repo()
        wt = self.add_worktree(repo, "feat/x")
        pol = self._policy_for(self._tmp.name)
        # a linked worktree is a Safe Workspace even with NO lease + NO daemon
        d = guard.decide_shell(wt, "git commit -am x", pol)
        self.assertEqual(d.permission, "allow")

    def test_adopted_lease_allows(self):
        repo = self.make_repo()
        wt = self.add_worktree(repo, "feat/x")
        lifecycle.adopt(wt)  # writes .awa/lease.json
        pol = self._policy_for(self._tmp.name)
        d = guard.decide_shell(wt, "git commit -am x", pol)
        self.assertEqual(d.permission, "allow")

    def test_override_allows_primary(self):
        repo = self.make_repo()
        pol = self._policy_for(self._tmp.name)
        d = guard.decide_shell(repo, "git commit -am x", pol, allow_primary=True)
        self.assertEqual(d.permission, "allow")

    def test_self_governed_repo_allows(self):
        repo = self.make_repo()
        Path(repo, "_ops").mkdir()
        Path(repo, "_ops", "POLICY.md").write_text("policy")
        pol = self._policy_for(self._tmp.name)
        d = guard.decide_shell(repo, "git commit -am x", pol)
        self.assertEqual(d.permission, "allow")
        self.assertEqual(d.classification, "exclude")


class TestCanClean(EngineTestCase):
    def test_refuses_primary(self):
        repo = self.make_repo()
        ok, why = guard.can_clean(repo)
        self.assertFalse(ok)
        self.assertIn("primary", why)

    def test_refuses_dirty_worktree(self):
        repo = self.make_repo()
        wt = self.add_worktree(repo, "feat/x")
        Path(wt, "README.md").write_text("dirty\n", encoding="utf-8")
        ok, why = guard.can_clean(wt)
        self.assertFalse(ok)
        self.assertIn("dirty", why)

    def test_refuses_local_only_commits(self):
        repo = self.make_repo()
        wt = self.add_worktree(repo, "feat/x")
        Path(wt, "new.txt").write_text("x\n", encoding="utf-8")
        commit_all(wt, "local-only")
        ok, why = guard.can_clean(wt)
        self.assertFalse(ok)
        self.assertIn("local-only", why)

    def test_refuses_ignored_files(self):
        repo = self.make_repo()
        Path(repo, ".gitignore").write_text("*.env\n", encoding="utf-8")
        commit_all(repo, "gitignore")
        wt = self.add_worktree(repo, "feat/x")
        Path(wt, "x.env").write_text("A=1\n", encoding="utf-8")
        ok, why = guard.can_clean(wt)
        self.assertFalse(ok)
        self.assertIn("ignored", why)

    def test_allows_safe_merged_worktree(self):
        repo = self.make_repo()
        wt = self.add_worktree(repo, "feat/x")  # points at main, merged, clean
        ok, why = guard.can_clean(wt)
        self.assertTrue(ok, why)


if __name__ == "__main__":
    unittest.main()
