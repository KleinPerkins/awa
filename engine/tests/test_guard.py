"""Phase 5: minimal local guard — kernel guarantee with the engine OFF (degraded mode).

These tests deliberately NEVER start the daemon and NEVER open the SQLite state, to
prove the guarantee holds with the engine dead/never-started: a mutating command on an
included primary -> DENY (Cursor enforces `deny`; it treats `ask` as non-blocking — L4),
a linked worktree/lease -> allow, a Cloud/background agent -> allow, unsafe cleanup refused.
"""

from __future__ import annotations

import os
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

# Same shape as _POLICY_YAML, with an injectable body ({body}) for per-repo mode /
# default_mode cases. `repo` is the rel of the default make_repo() under the governed root.
_POLICY_MODE_YAML = """\
version: 1
governed_roots:
  - {root}
default: include
include:
  - '*'
exclude:
  - .
{body}
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

    def test_chained_command_bypasses(self):
        """Regression: a mutating sub-command must not hide behind a read-only leader
        joined by a shell control operator (`;`, `&&`, `||`, `|`, subshell parens)."""
        for cmd in ("git status && git commit -am x", "ls; rm -rf x",
                    "true || rm -rf x", "cat foo | tee bar", "(rm -rf x)",
                    "echo hi && sed -i s/a/b/ f"):
            self.assertTrue(guard.classify_mutating(cmd), cmd)

    def test_control_operators_inside_quotes_not_split(self):
        """A literal `&&`/`;`/`|` inside a quoted argument is not a real control
        operator and must not trigger a false positive."""
        for cmd in ('echo "a && b"', 'git log --oneline -m "fix: a; b"', 'echo "a | b"'):
            self.assertFalse(guard.classify_mutating(cmd), cmd)

    # Wrapper forms that MUST classify mutating (regression matrix for the option-aware
    # wrapper-skip fix). Skipping only the wrapper NAME let all of these fast-path allow.
    WRAPPER_MUTATING = [
        "nice -n 10 git commit -m x",
        "env -C /r git commit",
        "env -i git commit",
        "env -u FOO git commit",
        "sudo -u root git commit",
        "sudo -g grp git commit",
        "xargs -I{} git commit",
        "xargs -I {} git commit",
        "xargs -n 1 git commit",
        "timeout 5 git commit",
        "timeout -s KILL 5 git commit",
        "timeout --signal=KILL 5 git commit",
        "ionice -c 3 git commit",
        "chrt -b 0 git commit",
        "stdbuf -oL git commit",
        "nice -n 10 rm -rf x",
        "sudo -u root npm install",
        "env -C /r sed -i s/a/b/ f",
        "timeout 5 nice -n 10 git commit",   # nested wrappers
        "{ git commit; }",                    # brace group (#7)
        "{ git status; git commit -am x; }",
        'bash -c "git commit -am x"',
        'sh -c "git commit"',
        "builtin git commit",
        "exec git commit",
        "doas git commit",
        "run0 git commit",
        "setsid git commit",
        'script -c "git commit" /dev/null',
    ]
    WRAPPER_READONLY = [
        "timeout 5 git status",
        "nice -n 10 ls -la",
        "env -C /r cat f",
        "sudo -u root git status",
        "{ git status; }",
        "ionice -c 3 git log",
        'bash -c "git status"',
        "python3 -c 'print(1)'",
    ]

    def test_wrapper_option_forms_are_mutating(self):
        for cmd in self.WRAPPER_MUTATING:
            self.assertTrue(guard.classify_mutating(cmd), cmd)

    def test_wrapper_readonly_forms_allowed(self):
        for cmd in self.WRAPPER_READONLY:
            self.assertFalse(guard.classify_mutating(cmd), cmd)


class TestDecideShellDegraded(EngineTestCase):
    def _policy_for(self, root: str) -> str:
        p = tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False)
        p.write(_POLICY_YAML.format(root=root))
        p.close()
        return p.name

    def _mode_policy_for(self, root: str, body: str) -> str:
        p = tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False)
        p.write(_POLICY_MODE_YAML.format(root=root, body=body))
        p.close()
        return p.name

    def test_primary_mutation_denies(self):
        repo = self.make_repo()
        pol = self._policy_for(self._tmp.name)
        d = guard.decide_shell(repo, "git commit -am x", pol)
        self.assertEqual(d.permission, "deny")
        self.assertEqual(d.classification, "include")

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

    def test_cloud_allows_primary_mutation(self):
        """A Cursor Cloud / background agent degrades to ALLOW *before* the deny branch (an
        isolated own-branch /workspace clone must never be hard-blocked)."""
        repo = self.make_repo()
        pol = self._policy_for(self._tmp.name)
        prev = os.environ.get("AWA_FORCE_CLOUD")
        os.environ["AWA_FORCE_CLOUD"] = "1"
        try:
            d = guard.decide_shell(repo, "git commit -am x", pol)
        finally:
            if prev is None:
                os.environ.pop("AWA_FORCE_CLOUD", None)
            else:
                os.environ["AWA_FORCE_CLOUD"] = prev
        self.assertEqual(d.permission, "allow")
        self.assertEqual(d.classification, "cloud")

    def test_false_broker_env_does_not_cloud_allow(self):
        """A false/0 broker env must not degrade to allow on Desktop."""
        repo = self.make_repo()
        pol = self._policy_for(self._tmp.name)
        saved = {k: os.environ.get(k) for k in (
            "cloud_agent_identity_broker", "CURSOR_AGENT_IDENTITY_BROKER")}
        try:
            for val in ("false", "0", ""):
                os.environ["cloud_agent_identity_broker"] = val
                d = guard.decide_shell(repo, "git commit -am x", pol)
                self.assertEqual(d.permission, "deny", val)
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_self_governed_repo_allows(self):
        repo = self.make_repo()
        Path(repo, "_ops").mkdir()
        Path(repo, "_ops", "POLICY.md").write_text("policy")
        pol = self._policy_for(self._tmp.name)
        d = guard.decide_shell(repo, "git commit -am x", pol)
        self.assertEqual(d.permission, "allow")
        self.assertEqual(d.classification, "exclude")

    def test_legacy_default_mode_denies(self):
        """A removed legacy default_mode (ask_on) is not `off`, so it fails safe to include/ON
        -> a mutating primary DENIES (no legacy-specific branch)."""
        repo = self.make_repo()
        pol = self._mode_policy_for(self._tmp.name, "default_mode: ask_on")
        d = guard.decide_shell(repo, "git commit -am x", pol)
        self.assertEqual(d.permission, "deny")
        self.assertEqual(d.classification, "include")

    def test_legacy_default_mode_readonly_allows(self):
        repo = self.make_repo()
        pol = self._mode_policy_for(self._tmp.name, "default_mode: ask_on")
        d = guard.decide_shell(repo, "git status", pol)
        self.assertEqual(d.permission, "allow")
        self.assertEqual(d.classification, "include")

    def test_off_primary_mutation_allows(self):
        repo = self.make_repo()
        pol = self._mode_policy_for(self._tmp.name, "default_mode: off")
        d = guard.decide_shell(repo, "git commit -am x", pol)
        self.assertEqual(d.permission, "allow")
        self.assertEqual(d.classification, "exclude")

    def test_invalid_explicit_mode_denies(self):
        """A per-repo legacy/unknown value is not `off`, so it fails safe to include -> deny."""
        repo = self.make_repo()
        pol = self._mode_policy_for(self._tmp.name, "modes:\n  repo: bogus")
        d = guard.decide_shell(repo, "git commit -am x", pol)
        self.assertEqual(d.permission, "deny")
        self.assertEqual(d.classification, "include")

    def test_wrapper_forms_deny_on_primary_include(self):
        """Each wrapper-obscured mutating form must DENY on an included primary checkout."""
        repo = self.make_repo()
        pol = self._policy_for(self._tmp.name)
        for cmd in ("nice -n 10 git commit -am x", "env -C /r git commit",
                    "sudo -u root git commit", "timeout 5 git commit",
                    "xargs -I{} git commit", "{ git commit; }",
                    'bash -c "git commit -am x"', "builtin git commit"):
            d = guard.decide_shell(repo, cmd, pol)
            self.assertEqual(d.permission, "deny", cmd)

    def test_wrapper_forms_deny_on_legacy_default_mode(self):
        """Same, on a legacy default_mode: ask_on (which fails safe to include)."""
        repo = self.make_repo()
        pol = self._mode_policy_for(self._tmp.name, "default_mode: ask_on")
        for cmd in ("nice -n 10 git commit -am x", "timeout 5 git commit"):
            d = guard.decide_shell(repo, cmd, pol)
            self.assertEqual(d.permission, "deny", cmd)

    def test_unreadable_modes_file_still_denies_on_primary(self):
        """FAIL-SAFE (#1): an existing-but-unreadable modes_file (a directory) must NOT let a
        mutating primary command through. It is treated as absent -> default include -> deny."""
        repo = self.make_repo()
        # Build a policy that points modes_file at a DIRECTORY (unreadable as a file). Use an
        # absolute path so it resolves regardless of where the temp policy file lives.
        modesdir = Path(self._tmp.name) / "modesdir"
        modesdir.mkdir()
        pol = tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False)
        pol.write(_POLICY_MODE_YAML.format(root=self._tmp.name,
                                           body=f"modes_file: {modesdir}"))
        pol.close()
        d = guard.decide_shell(repo, "git commit -am x", pol.name)
        self.assertEqual(d.permission, "deny")


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
