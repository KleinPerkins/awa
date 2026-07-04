"""Phase 2: git/worktree lifecycle — adopt/attest (no push in default), publish, retire."""

from __future__ import annotations

import unittest

from engine import gitutil, lease as lease_mod, lifecycle, state as state_mod
from engine.tests.helpers import EngineTestCase


class TestLifecycle(EngineTestCase):
    def test_adopt_records_lease_and_attests_no_push(self):
        repo = self.make_repo()
        wt = self.add_worktree(repo, "feat/x")
        res = lifecycle.adopt(wt)
        self.assertTrue(res.attested, res.reason)
        # a lease.json exists + validates
        lz = lease_mod.read_lease(wt)
        self.assertIsNotNone(lz)
        self.assertEqual(lease_mod.validate(lz), [])
        # NO quarantine ref was pushed in the default adopt path
        with state_mod.State() as st:
            self.assertEqual(st.quarantine_refs(), [])
            self.assertEqual(len(st.list_leases("active")), 1)
            kinds = {e["kind"] for e in st.events()}
            self.assertIn("adopt", kinds)
            self.assertIn("attest", kinds)

    def test_adopt_refuses_primary_checkout(self):
        repo = self.make_repo()
        with self.assertRaises(lifecycle.LifecycleError):
            lifecycle.adopt(repo)

    def test_attest_detects_branch_drift(self):
        repo = self.make_repo()
        wt = self.add_worktree(repo, "feat/x")
        lifecycle.adopt(wt)
        # switch the worktree to a different branch -> attest must fail
        gitutil.git(wt, "checkout", "-q", "-b", "feat/y")
        ok, why = lifecycle.attest(wt)
        self.assertFalse(ok)
        self.assertIn("drift", why)

    def test_publish_without_remote_surfaces_remote_unavailable(self):
        repo = self.make_repo(origin=False)
        wt = self.add_worktree(repo, "feat/x")
        lifecycle.adopt(wt)
        with self.assertRaises(lifecycle.LifecycleError) as ctx:
            lifecycle.publish(wt)
        self.assertIn("not available", str(ctx.exception).lower() + str(ctx.exception))

    def test_quarantine_ref_namespace(self):
        ref = lifecycle.quarantine_ref("/some/repo/.git", "awa1-deadbeef")
        self.assertTrue(ref.startswith("refs/awa/"))
        self.assertNotIn("refs/heads/", ref)
        self.assertIn("awa1-deadbeef", ref)

    def test_retire_marks_lease(self):
        repo = self.make_repo()
        wt = self.add_worktree(repo, "feat/x")
        lifecycle.adopt(wt)
        lifecycle.retire(wt)
        with state_mod.State() as st:
            self.assertEqual(len(st.list_leases("retired")), 1)


if __name__ == "__main__":
    unittest.main()
