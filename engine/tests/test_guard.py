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
from engine.tests.git_guard_command_corpus import (
    GIT_MUTATING_FAMILY_COMMANDS,
    GIT_READONLY_FAMILY_COMMANDS,
)
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

# Same shape as _POLICY_YAML, but WITHOUT the catch-all `include: ['*']` glob. Needed for
# is_standalone regression coverage: _POLICY_YAML's include:['*'] matches ANY non-'.' rel,
# so classify()'s include-glob check (which the new is_standalone branch sits immediately
# after) would fire first and mask the standalone branch entirely. PolicyConfig.include
# defaults to [] when omitted, so _match_any never matches here.
_POLICY_YAML_NO_INCLUDE_GLOB = """\
version: 1
governed_roots:
  - {root}
default: include
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

    def test_git_readonly_forms_inside_mutating_families_allowed(self):
        for cmd in GIT_READONLY_FAMILY_COMMANDS:
            self.assertFalse(guard.classify_mutating(cmd), cmd)

    def test_git_mutating_forms_inside_mutating_families_still_mutating(self):
        for cmd in GIT_MUTATING_FAMILY_COMMANDS:
            self.assertTrue(guard.classify_mutating(cmd), cmd)

    def test_git_family_unknown_or_malformed_forms_fail_safe(self):
        for cmd in (
            "git -C",
            "git --unknown-global branch --show-current",
            "git branch --unknown",
            "git remote -- get-url origin",
            "git config --get",
            "git submodule -- status",
            "git sparse-checkout check-rules",
        ):
            self.assertTrue(guard.classify_mutating(cmd), cmd)

    def test_branch_copy_flag_is_not_global_chdir(self):
        self.assertTrue(guard.classify_mutating("git branch -C main copied"))

    def test_unmodeled_global_flag_preserves_unrelated_read_behavior(self):
        self.assertFalse(guard.classify_mutating("git --exec-path=/tmp status"))

    def test_branch_list_invalid_forms_never_crash_to_allow(self):
        for cmd in (
            "git branch --list --unknown",
            "git branch --list --unknown -- topic",
            "git branch --list --unknown ; rm -rf protected",
        ):
            self.assertTrue(guard.classify_mutating(cmd), cmd)


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

    def _policy_for_no_include_glob(self, root: str) -> str:
        p = tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False)
        p.write(_POLICY_YAML_NO_INCLUDE_GLOB.format(root=root))
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

    def test_primary_allows_readonly_git_family_forms(self):
        repo = self.make_repo()
        pol = self._policy_for(self._tmp.name)
        for cmd in GIT_READONLY_FAMILY_COMMANDS:
            d = guard.decide_shell(repo, cmd, pol)
            self.assertEqual(d.permission, "allow", cmd)
            self.assertEqual(d.classification, "include", cmd)

    def test_primary_still_denies_mutating_git_family_forms(self):
        repo = self.make_repo()
        pol = self._policy_for(self._tmp.name)
        for cmd in GIT_MUTATING_FAMILY_COMMANDS:
            d = guard.decide_shell(repo, cmd, pol)
            self.assertEqual(d.permission, "deny", cmd)
            self.assertEqual(d.classification, "include", cmd)

    def test_standalone_repo_with_origin_allows_not_denies(self):
        """Regression: a standalone clone (e.g. under /tmp) with an origin remote, OUTSIDE
        every governed root and matching no include-glob, must classify advisory -> allow,
        never include -> deny. Uses the dedicated no-include-glob policy (NOT the shared
        _policy_for fixture) because that fixture's include: ['*'] would match first and
        mask this exact code path -- see the swarm-review note above this test."""
        repo = self.make_standalone_repo()
        pol = self._policy_for_no_include_glob(self._tmp.name)
        d = guard.decide_shell(repo, "git commit -am x", pol)
        self.assertEqual(d.permission, "allow")
        self.assertEqual(d.classification, "advisory")

    def test_standalone_repo_without_origin_allows(self):
        """Control, not is_standalone coverage: a standalone repo with NO origin remote hits
        the pre-existing 'no origin remote' advisory branch (engine/policy.py:323-324), which
        fires before the include-glob check and before is_standalone regardless of which
        policy fixture is used. This proves that pre-existing behavior still holds for a
        standalone repo; the test above is the one that actually covers is_standalone."""
        repo = self.make_standalone_repo(origin=False)
        pol = self._policy_for(self._tmp.name)
        d = guard.decide_shell(repo, "git commit -am x", pol)
        self.assertEqual(d.permission, "allow")
        self.assertEqual(d.classification, "advisory")

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
        """An unreadable modes file overrides lower-priority inline OFF fail-closed."""
        repo = self.make_repo()
        # Both the inline default and exact entry are OFF. Because a referenced file could
        # contain protective overrides, its unreadability must force ON rather than trust them.
        modesdir = Path(self._tmp.name) / "modesdir"
        modesdir.mkdir()
        pol = tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False)
        pol.write(_POLICY_MODE_YAML.format(
            root=self._tmp.name,
            body=(
                "default_mode: off\n"
                "modes:\n"
                "  repo: off\n"
                f"modes_file: {modesdir}"
            ),
        ))
        pol.close()
        d = guard.decide_shell(repo, "git commit -am x", pol.name)
        self.assertEqual(d.permission, "deny")

    # ---- ADR 0001: target-path-aware mutation scope ----------------------------
    def test_precise_target_outside_any_repo_allows(self):
        repo = self.make_repo()
        pol = self._policy_for(self._tmp.name)
        outside = os.path.join(tempfile.gettempdir(), "awa-guard-precision-outside.txt")
        d = guard.decide_shell(repo, "rm -f %s" % outside, pol)
        self.assertEqual(d.permission, "allow")

    def test_precise_target_inside_same_primary_still_denies(self):
        repo = self.make_repo()
        pol = self._policy_for(self._tmp.name)
        d = guard.decide_shell(repo, "rm -f README.md", pol)
        self.assertEqual(d.permission, "deny")

    def test_precise_target_inside_another_protected_primary_denies(self):
        repo_a = self.make_repo("repo-a")
        repo_b = self.make_repo("repo-b")
        pol = self._policy_for(self._tmp.name)
        target = os.path.join(repo_b, "README.md")
        d = guard.decide_shell(repo_a, "rm -f %s" % target, pol)
        self.assertEqual(d.permission, "deny")

    def test_precise_target_inside_linked_worktree_allows(self):
        repo = self.make_repo()
        wt = self.add_worktree(repo, "feat/x")
        pol = self._policy_for(self._tmp.name)
        target = os.path.join(wt, "README.md")
        d = guard.decide_shell(repo, "rm -f %s" % target, pol)
        self.assertEqual(d.permission, "allow")

    def test_precise_target_inside_excluded_or_advisory_repo_allows(self):
        """Uses the dedicated no-include-glob policy fixture for the SAME reason as
        test_standalone_repo_with_origin_allows_not_denies above: the shared
        _policy_for fixture's include: ['*'] would match the standalone repo's own
        rel first and misclassify it INCLUDE, masking the is_standalone branch this
        test needs on the TARGET side (not the cwd side)."""
        repo = self.make_repo()
        pol = self._policy_for_no_include_glob(self._tmp.name)
        standalone = self.make_standalone_repo()
        target = os.path.join(standalone, "README.md")
        d = guard.decide_shell(repo, "rm -f %s" % target, pol)
        self.assertEqual(d.permission, "allow")

    def test_glob_target_falls_back_conservative_denies(self):
        repo = self.make_repo()
        pol = self._policy_for(self._tmp.name)
        d = guard.decide_shell(repo, "rm -rf *", pol)
        self.assertEqual(d.permission, "deny")

    def test_multiple_targets_any_protected_denies(self):
        repo = self.make_repo()
        pol = self._policy_for(self._tmp.name)
        outside = os.path.join(tempfile.gettempdir(), "awa-guard-precision-multi.txt")
        d = guard.decide_shell(repo, "rm -f %s README.md" % outside, pol)
        self.assertEqual(d.permission, "deny")

    def test_mv_cp_source_and_dest_both_checked(self):
        repo = self.make_repo()
        pol = self._policy_for(self._tmp.name)
        outside = os.path.join(tempfile.gettempdir(), "awa-guard-precision-mv.txt")
        # Destination outside, source inside the protected repo -- still deny (the
        # source is removed by mv too, not just written).
        d1 = guard.decide_shell(repo, "mv README.md %s" % outside, pol)
        self.assertEqual(d1.permission, "deny")
        # The reverse: source outside, destination inside the protected repo.
        d2 = guard.decide_shell(repo, "mv %s README2.md" % outside, pol)
        self.assertEqual(d2.permission, "deny")

    def test_git_dash_c_target_redirects_classification(self):
        repo_a = self.make_repo("repo-a")
        pol = self._policy_for(self._tmp.name)
        repo_b = self.make_repo("repo-b")
        d_deny = guard.decide_shell(repo_a, "git -C %s commit -am x" % repo_b, pol)
        self.assertEqual(d_deny.permission, "deny")
        wt = self.add_worktree(repo_a, "feat/x")
        d_allow = guard.decide_shell(repo_a, "git -C %s commit -am x" % wt, pol)
        self.assertEqual(d_allow.permission, "allow")

    def test_git_dir_flag_not_masked_by_trailing_safe_work_tree(self):
        """A trailing safe --work-tree must not launder an earlier --git-dir that still
        points at the protected primary: git honors -C / --git-dir / --work-tree
        SIMULTANEOUSLY, so a commit with an explicit --git-dir=<protected>/.git still
        writes its objects/refs into that protected primary even when --work-tree
        redirects the checked-out files elsewhere. The previous implementation kept
        only the LAST-seen flag as "the" target, so ordering --work-tree after
        --git-dir made the whole command look safe -- a guard bypass."""
        repo = self.make_repo()
        pol = self._policy_for(self._tmp.name)
        safe_wt = tempfile.mkdtemp()
        cmd = "git --git-dir=%s/.git --work-tree=%s commit -am x" % (repo, safe_wt)
        d = guard.decide_shell(repo, cmd, pol)
        self.assertEqual(d.permission, "deny")

    def test_too_many_targets_falls_back_conservative(self):
        repo = self.make_repo()
        pol = self._policy_for(self._tmp.name)
        many = " ".join("f%d.txt" % i for i in range(guard._MAX_PRECISE_TARGETS + 1))
        d = guard.decide_shell(repo, "rm -f %s" % many, pol)
        self.assertEqual(d.permission, "deny")

    def test_unresolvable_target_conservative_denies(self):
        """A target with no real filesystem/git anchor at all resolves outside any
        protected primary (allow); a not-yet-created nested path INSIDE the
        protected repo's own working tree cannot be probed via git at all (`git -C`
        requires the exact directory to already exist) -- this must still deny via
        the governed-roots fallback (_path_looks_governed), never silently allow
        just because the exact nested path does not exist yet."""
        repo = self.make_repo()
        pol = self._policy_for(self._tmp.name)
        nowhere = "/nonexistent-awa-guard-test-root-xyz/deeply/nested/file.txt"
        d_allow = guard.decide_shell(repo, "rm -f %s" % nowhere, pol)
        self.assertEqual(d_allow.permission, "allow")
        nested = os.path.join(repo, "a", "b", "c")
        d_deny = guard.decide_shell(repo, "mkdir -p %s" % nested, pol)
        self.assertEqual(d_deny.permission, "deny")

    # ---- ADR 0001 §2/§4: a .git-internal target IS inside the protected primary ----
    # git's own --is-inside-work-tree semantics EXCLUDE the .git directory, so a target
    # like `.git`, `.git/config`, `.git/objects`, `.git/hooks/<name>` resolves as
    # "not a work tree" and was (wrongly) treated as outside all protection -> the deny
    # was converted to allow. Destroying the object DB / refs / hooks is at least as
    # catastrophic as deleting tracked files (and, unlike a tracked-file delete,
    # irrecoverable), so AWA's protection boundary MUST include .git/.
    def test_dotgit_directory_target_on_primary_denies(self):
        repo = self.make_repo()
        pol = self._policy_for(self._tmp.name)
        for cmd in ("rm -rf .git", "rm -rf %s" % os.path.join(repo, ".git")):
            d = guard.decide_shell(repo, cmd, pol)
            self.assertEqual(d.permission, "deny", cmd)

    def test_dotgit_internal_targets_on_primary_deny(self):
        repo = self.make_repo()
        pol = self._policy_for(self._tmp.name)
        # config/HEAD are files; refs/objects/objects/pack are dirs; hooks/<name> is a
        # nested file -- cover both file and directory probes at several depths.
        for rel in (".git/config", ".git/HEAD", ".git/refs", ".git/objects",
                    ".git/objects/pack", ".git/hooks/pre-commit",
                    ".git/refs/heads/main"):
            d = guard.decide_shell(repo, "rm -rf %s" % rel, pol)
            self.assertEqual(d.permission, "deny", rel)

    def test_dotgit_internal_target_in_another_protected_primary_denies(self):
        """§2: the unit of protection is 'some protected primary', not the cwd's repo --
        a .git-internal target inside a DIFFERENT protected primary must still deny."""
        repo_a = self.make_repo("repo-a")
        repo_b = self.make_repo("repo-b")
        pol = self._policy_for(self._tmp.name)
        target = os.path.join(repo_b, ".git", "objects")
        d = guard.decide_shell(repo_a, "rm -rf %s" % target, pol)
        self.assertEqual(d.permission, "deny")

    def test_dotgit_internal_target_in_advisory_repo_allows(self):
        """No over-blocking (requirement 1): a .git-internal path inside a NON-included
        (standalone/advisory) repo must still ALLOW. The fix attributes the target to its
        ENCLOSING repo and classifies THAT repo normally -- it does not blanket-deny every
        .git-shaped path. Uses the no-include-glob fixture for the same reason as
        test_precise_target_inside_excluded_or_advisory_repo_allows above."""
        repo = self.make_repo()
        pol = self._policy_for_no_include_glob(self._tmp.name)
        standalone = self.make_standalone_repo()
        for rel in (".git", os.path.join(".git", "objects"), os.path.join(".git", "config")):
            target = os.path.join(standalone, rel)
            d = guard.decide_shell(repo, "rm -rf %s" % target, pol)
            self.assertEqual(d.permission, "allow", rel)

    def test_linked_worktree_dotgit_file_target_still_allows(self):
        """Requirement 3: a linked worktree's .git is a FILE (a `gitdir:` pointer), which
        _probe_dir redirects to the worktree root (a Safe Workspace) BEFORE the .git
        reattribution runs -- so it stays ALLOW, on a different code path, unaffected."""
        repo = self.make_repo()
        wt = self.add_worktree(repo, "feat/x")
        pol = self._policy_for(self._tmp.name)
        dotgit = os.path.join(wt, ".git")
        self.assertTrue(os.path.isfile(dotgit))  # sanity: worktree .git really is a file
        d = guard.decide_shell(repo, "rm -rf %s" % dotgit, pol)
        self.assertEqual(d.permission, "allow")

    def test_reattribute_dotgit_probe_helper(self):
        """Unit-level parity anchor for the reattribution walk-up (mirrored byte-for-byte
        in kernel/hooks/worktree-guard.sh). A .git component redirects to its parent; a
        `..` that escapes .git (a path OUTSIDE it) does NOT; no .git is unchanged."""
        self.assertEqual(guard._reattribute_dotgit_probe("/r/.git"), "/r")
        self.assertEqual(guard._reattribute_dotgit_probe("/r/.git/objects/pack"), "/r")
        self.assertEqual(guard._reattribute_dotgit_probe("/r/sub/.git"), "/r/sub")
        self.assertEqual(guard._reattribute_dotgit_probe("/r/work"), "/r/work")
        # `.git/..` normalizes to `/r` (a path OUTSIDE .git), so it is NOT treated as
        # .git-internal: the probe is returned UNCHANGED for the caller to resolve (git
        # itself collapses the `..`), never reattributed to /r's parent (`/`).
        self.assertEqual(guard._reattribute_dotgit_probe("/r/.git/.."), "/r/.git/..")

    def test_remote_dry_runs_allow_only_after_safe_workspace_classification(self):
        repo = self.make_repo()
        wt = self.add_worktree(repo, "feat/remote-proof")
        pol = self._policy_for(self._tmp.name)
        for cmd in ("git fetch --dry-run", "git push --dry-run"):
            self.assertEqual(guard.decide_shell(repo, cmd, pol).permission, "deny", cmd)
            self.assertEqual(guard.decide_shell(wt, cmd, pol).permission, "allow", cmd)

    def test_branch_local_copy_flag_cannot_launder_target_scope(self):
        repo = self.make_repo()
        outside = self.make_standalone_repo(origin=False)
        pol = self._policy_for(self._tmp.name)
        cmd = f"git branch -C {outside} copied"
        self.assertEqual(guard.decide_shell(repo, cmd, pol).permission, "deny")

    def test_unscoped_family_mutations_cannot_narrow_to_outside_target(self):
        repo = self.make_repo()
        outside = self.make_standalone_repo(origin=False)
        protected_config = Path(repo) / ".git" / "config"
        pol = self._policy_for(self._tmp.name)
        for cmd in (
            f"git -C {outside} config --file {protected_config} user.name changed",
            f"git -C {outside} submodule foreach true",
        ):
            self.assertEqual(guard.decide_shell(repo, cmd, pol).permission, "deny", cmd)


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
