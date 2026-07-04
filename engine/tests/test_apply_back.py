"""Phase 9: SHA-bound apply-back preview (preview-first, recovery-before-mutation)."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from engine import gitutil, lifecycle, state as state_mod
from engine.tests.helpers import EngineTestCase, commit_all


class TestApplyBackPreview(EngineTestCase):
    def test_preview_is_sha_bound_and_never_mutates(self):
        repo = self.make_repo()
        wt = self.add_worktree(repo, "feat/x")
        Path(wt, "new.txt").write_text("work\n", encoding="utf-8")
        commit_all(wt, "feature commit")
        head_before = gitutil.head_sha(wt)
        main_before = gitutil.head_sha(repo)

        with state_mod.State() as st:
            plan = lifecycle.apply_back_preview(wt, state=st)

        self.assertTrue(plan.preview)
        self.assertFalse(plan.mutated)
        self.assertEqual(plan.commits_ahead, 1)
        self.assertIn("new.txt", plan.files_changed)
        self.assertIsNotNone(plan.base_sha)   # bound to a concrete base SHA
        self.assertEqual(plan.head, head_before)
        # NOTHING mutated: worktree HEAD + primary main unchanged
        self.assertEqual(gitutil.head_sha(wt), head_before)
        self.assertEqual(gitutil.head_sha(repo), main_before)

    def test_recovery_before_mutation_captures_uncommitted(self):
        repo = self.make_repo()
        wt = self.add_worktree(repo, "feat/x")
        Path(wt, "README.md").write_text("uncommitted-edit\n", encoding="utf-8")
        plan = lifecycle.apply_back_preview(wt)
        self.assertIsNotNone(plan.recovery_patch)
        self.assertTrue(os.path.exists(plan.recovery_patch))
        # the recovery patch actually round-trips the uncommitted edit
        from engine import recovery
        gitutil.git(wt, "checkout", "--", "README.md")
        recovery.restore_patch(plan.recovery_patch, wt)
        self.assertEqual(Path(wt, "README.md").read_text(), "uncommitted-edit\n")

    def test_no_base_ref_is_honest(self):
        repo = self.make_repo(origin=False)
        # rename main away so there is no main/origin/main base
        gitutil.git(repo, "branch", "-m", "trunk")
        wt = repo + ".wt"
        gitutil.git(repo, "worktree", "add", "-q", "-b", "feat/x", wt, "trunk")
        plan = lifecycle.apply_back_preview(wt)
        self.assertIsNone(plan.base_ref)
        self.assertIn("no base", plan.reason)


if __name__ == "__main__":
    unittest.main()
