"""Phase 9 / S3: apply-back remote adapter — token split, SHA-binding, preview→confirm
gating, recovery-before-mutation ordering. The network is fully mocked (injected
callables); nothing here touches a real remote.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from engine import gitutil, lifecycle, remote, state as state_mod
from engine.tests.helpers import EngineTestCase, commit_all


class TestTokenSplit(unittest.TestCase):
    def test_read_op_uses_read_token(self):
        self.assertEqual(remote.select_token("status", read_token="R", write_token="W"), "R")
        self.assertEqual(remote.select_token("poll", read_token="R", write_token=None), "R")

    def test_read_op_unauthenticated_allowed(self):
        self.assertEqual(remote.select_token("status", read_token=None, write_token=None), "")

    def test_write_op_uses_write_token(self):
        self.assertEqual(remote.select_token("push", read_token="R", write_token="W"), "W")
        self.assertEqual(remote.select_token("pr", read_token="R", write_token="W"), "W")

    def test_write_op_refuses_without_write_token(self):
        # S3: a write op must NEVER fall back to a read-scoped token.
        with self.assertRaises(remote.RemoteError):
            remote.select_token("push", read_token="R", write_token=None)
        with self.assertRaises(remote.RemoteError):
            remote.select_token("pr", read_token="R", write_token="")

    def test_unknown_op_refused(self):
        with self.assertRaises(remote.RemoteError):
            remote.select_token("delete", read_token="R", write_token="W")


class TestApplyBackExecute(EngineTestCase):
    def _repo_with_commit(self):
        repo = self.make_repo()
        wt = self.add_worktree(repo, "feat/x")
        Path(wt, "new.txt").write_text("work\n", encoding="utf-8")
        commit_all(wt, "feature commit")
        return repo, wt

    def test_confirm_false_previews_and_never_mutates(self):
        repo, wt = self._repo_with_commit()
        calls = []
        res = remote.apply_back_execute(
            wt, confirm=False, read_token="R", write_token="W",
            pusher=lambda ctx: calls.append("push") or "ref",
        )
        self.assertTrue(res.ok)
        self.assertFalse(res.mutated)
        self.assertFalse(res.pushed)
        self.assertEqual(calls, [])  # pusher NEVER invoked in preview
        self.assertIsNotNone(res.base_sha)

    def test_recovery_before_mutation_then_push(self):
        repo, wt = self._repo_with_commit()
        # an uncommitted edit so the recovery patch is non-trivial
        Path(wt, "new.txt").write_text("work\nmore\n", encoding="utf-8")
        order = []

        def pusher(ctx: remote.PushContext) -> str:
            # recovery patch MUST already exist on disk before any push happens.
            self.assertTrue(ctx.recovery_patch and os.path.exists(ctx.recovery_patch))
            self.assertEqual(ctx.token, "WTOKEN")   # write-scoped token reached the pusher
            order.append("push")
            return f"refs/heads/{ctx.branch}"

        def pr_opener(ctx: remote.PushContext):
            self.assertEqual(ctx.token, "WTOKEN")
            order.append("pr")
            return "https://example/pr/1"

        def poller(pr_url, token):
            self.assertEqual(token, "RTOKEN")       # read-scoped token for status/poll
            order.append("poll")

        with state_mod.State() as st:
            res = remote.apply_back_execute(
                wt, confirm=True, read_token="RTOKEN", write_token="WTOKEN",
                pusher=pusher, pr_opener=pr_opener, poller=poller, state=st,
            )
        self.assertTrue(res.mutated and res.pushed)
        self.assertEqual(res.pr_url, "https://example/pr/1")
        self.assertEqual(order, ["push", "pr", "poll"])  # write ops before the read poll

    def test_confirmed_execute_without_write_token_refuses(self):
        repo, wt = self._repo_with_commit()
        calls = []
        with self.assertRaises(remote.RemoteError):
            remote.apply_back_execute(
                wt, confirm=True, read_token="R", write_token=None,
                pusher=lambda ctx: calls.append("push") or "ref",
            )
        self.assertEqual(calls, [])  # refused BEFORE any push

    def test_confirmed_execute_without_pusher_is_honest_operator_step(self):
        repo, wt = self._repo_with_commit()
        with self.assertRaises(remote.RemoteError) as cm:
            remote.apply_back_execute(wt, confirm=True, read_token="R", write_token="W")
        self.assertIn("operator", str(cm.exception).lower())

    def test_sha_drift_refuses_and_does_not_push(self):
        repo, wt = self._repo_with_commit()
        # take a preview, THEN advance HEAD so the reviewed sha is stale.
        plan = lifecycle.apply_back_preview(wt)
        Path(wt, "drift.txt").write_text("drift\n", encoding="utf-8")
        commit_all(wt, "post-preview commit (drift)")
        self.assertNotEqual(gitutil.head_sha(wt), plan.head)
        calls = []
        with self.assertRaises(remote.RemoteError) as cm:
            remote.apply_back_execute(
                wt, confirm=True, read_token="R", write_token="W", plan=plan,
                pusher=lambda ctx: calls.append("push") or "ref",
            )
        self.assertIn("drift", str(cm.exception).lower())
        self.assertEqual(calls, [])  # never pushed on drift

    def test_no_base_is_honest_noop(self):
        repo = self.make_repo(origin=False)
        gitutil.git(repo, "branch", "-m", "trunk")
        wt = repo + ".wt"
        gitutil.git(repo, "worktree", "add", "-q", "-b", "feat/x", wt, "trunk")
        res = remote.apply_back_execute(wt, confirm=True, read_token="R", write_token="W")
        self.assertTrue(res.ok)
        self.assertFalse(res.mutated)
        self.assertIn("no base", res.reason)


if __name__ == "__main__":
    unittest.main()
