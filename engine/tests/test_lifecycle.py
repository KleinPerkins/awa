"""Phase 2: git/worktree lifecycle — adopt/attest (no push in default), publish, retire."""

from __future__ import annotations

import json
import unittest

from engine import gitutil, identity, lease as lease_mod, lifecycle, state as state_mod
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

    # ---- branch self-heal (fix: attest no longer vetoes an ordinary checkout) ----------
    def test_attest_self_heals_live_reverified_branch_change(self):
        """BITING: before the fix, an ordinary `git checkout -b` between adopt and attest --
        gitutil.resolve() inside _attest_locked() had JUST, freshly, independently re-read the
        new branch as live ground truth -- was reported as "branch drifted" and failed attest
        forever, exactly the same defect class as #82/#83 in a structurally different subsystem.
        A legitimate branch change must now self-heal: attest succeeds, the on-disk lease.json is
        updated to the new branch, and it stays internally self-consistent (re-validates clean)."""
        repo = self.make_repo()
        wt = self.add_worktree(repo, "feat/x")
        adopt_res = lifecycle.adopt(wt)
        old_lease_id = adopt_res.lease_id

        gitutil.git(wt, "checkout", "-q", "-b", "feat/y")
        ok, why = lifecycle.attest(wt)
        self.assertTrue(ok, why)
        self.assertNotIn("drift", why)

        lz = lease_mod.read_lease(wt)
        self.assertEqual(lz["branch"], "feat/y")
        self.assertEqual(lease_mod.validate(lz), [], "self-healed lease must stay self-consistent")
        # lease_id is a function of branch (frozen identity_rule) -- it MUST be re-derived, not
        # left stale, or `validate()` would report this perfectly healthy lease as corrupt.
        self.assertNotEqual(lz["lease_id"], old_lease_id)
        self.assertEqual(
            lz["lease_id"],
            identity.lease_id(lz["worktree_path"], "feat/y", lz["git_common_dir"], lz["boot_id"]),
        )

        with state_mod.State() as st:
            old = st.get_lease(old_lease_id)
            self.assertIsNotNone(old)
            self.assertEqual(old["status"], "superseded",
                             "old identity must be kept (audit trail), not silently dropped")
            new = st.get_lease(lz["lease_id"])
            self.assertIsNotNone(new)
            self.assertEqual(new["status"], "active")
            self.assertIsNotNone(new["attested_at"])
            # bookkeeping must not double-count the SAME physical worktree under two identities.
            self.assertEqual(len(st.list_leases("active")), 1)
            self.assertIn("attest_rekeyed", {e["kind"] for e in st.events()})

    def test_attest_self_heal_is_idempotent_across_repeated_calls(self):
        """A second attest call with no further branch change must succeed via the ordinary
        (non-rekeying) path and must NOT churn the lease_id again."""
        repo = self.make_repo()
        wt = self.add_worktree(repo, "feat/x")
        lifecycle.adopt(wt)
        gitutil.git(wt, "checkout", "-q", "-b", "feat/y")
        ok1, _ = lifecycle.attest(wt)
        self.assertTrue(ok1)
        rekeyed_id = lease_mod.read_lease(wt)["lease_id"]

        ok2, why2 = lifecycle.attest(wt)
        self.assertTrue(ok2, why2)
        self.assertEqual(lease_mod.read_lease(wt)["lease_id"], rekeyed_id)
        with state_mod.State() as st:
            self.assertEqual(len(st.list_leases("active")), 1)

    def test_attest_detects_git_common_dir_drift_unconditionally(self):
        """BITING: git_common_dir is the REAL collision/identity boundary (frozen contract) and
        must remain an unconditional hard block -- never self-healed like branch. A hand-edited
        lease claiming a different common dir than the worktree actually resolves to today must
        still fail attest."""
        repo = self.make_repo()
        wt = self.add_worktree(repo, "feat/x")
        lifecycle.adopt(wt)
        lz = lease_mod.read_lease(wt)
        # Tamper common_dir AND re-derive lease_id so the record stays internally
        # self-consistent (validate() clean) -- isolating the live git_common_dir comparison as
        # the ONLY thing that can catch this, exactly like a lease.json copied/pointed at the
        # wrong physical worktree.
        lz["git_common_dir"] = "/tmp/awa-some-other-repo/.git"
        lz["lease_id"] = identity.lease_id(
            lz["worktree_path"], lz["branch"], lz["git_common_dir"], lz["boot_id"])
        lease_path = lease_mod.lease_path(wt)
        lease_path.write_text(json.dumps(lz), encoding="utf-8")

        ok, why = lifecycle.attest(wt)
        self.assertFalse(ok)
        self.assertIn("git_common_dir drifted", why)
        # unhealed: no rekey/self-heal event fired for a structural-identity mismatch.
        with state_mod.State() as st:
            self.assertNotIn("attest_rekeyed", {e["kind"] for e in st.events()})

    def test_attest_detects_genuinely_corrupt_lease_id(self):
        """A tampered/mismatched lease_id (independent of any branch change) must still fail
        attest -- this is the "actually something is wrong" case the branch self-heal must not
        weaken."""
        repo = self.make_repo()
        wt = self.add_worktree(repo, "feat/x")
        lifecycle.adopt(wt)
        lz = lease_mod.read_lease(wt)
        lz["lease_id"] = "awa1-" + ("0" * 64)  # well-formed shape, wrong hash
        lease_path = lease_mod.lease_path(wt)
        lease_path.write_text(json.dumps(lz), encoding="utf-8")

        ok, why = lifecycle.attest(wt)
        self.assertFalse(ok)
        self.assertIn("lease_id does not match hash", why)

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
