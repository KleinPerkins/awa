"""A0 deliverable 4 (KI4): consequence confirmations are KERNEL-sourced and airtight.

Router-INDEPENDENT (kernel only). Proves the three kernel flags {destroys_unshared_work,
irreversible, affects_shared_ref} are COMPUTED FROM LIVE TARGET FACTS (never a per-verb constant),
that a safe-looking action with a destructive consequence MUST confirm, that a benign action never
nags, and — structurally — that the descriptor API has NO router/proposal input, so a router
artifact cannot source a confirmation (KI4 hygiene)."""

from __future__ import annotations

import inspect
import subprocess
import tempfile
import unittest
from pathlib import Path

from .consumer_test_support import load_kernel_consequence

C = load_kernel_consequence()


def _facts(**kw):
    base = {"target": "/tmp/x", "exists": True, "disposition": "stale",
            "has_uncommitted_changes": False, "has_unshared_work": False, "branch_on_remote": False}
    base.update(kw)
    return base


class TestKernelConsequence(unittest.TestCase):
    # ---- flags are computed from LIVE FACTS, per target ----
    def test_remove_with_unshared_work_destroys_and_confirms(self):
        d = C.describe_consequence(C.ACTION_REMOVE, "/tmp/x",
                                   facts=_facts(has_unshared_work=True))
        self.assertTrue(d["destroys_unshared_work"])
        self.assertTrue(d["irreversible"])
        self.assertTrue(d["requires_confirmation"])
        self.assertTrue(d["risk"] and d["irreversible_step"], "must spell out the risk + point of no return")

    def test_remove_with_uncommitted_changes_destroys(self):
        d = C.describe_consequence(C.ACTION_REMOVE, "/tmp/x",
                                   facts=_facts(has_uncommitted_changes=True))
        self.assertTrue(d["destroys_unshared_work"])
        self.assertTrue(d["requires_confirmation"])

    def test_remove_when_work_saved_elsewhere_is_benign(self):
        """Same verb, DIFFERENT target facts -> benign. Proves the flag is per-target, not a
        per-verb constant. A benign removal must NOT nag."""
        d = C.describe_consequence(C.ACTION_REMOVE, "/tmp/x", facts=_facts())
        self.assertFalse(d["destroys_unshared_work"])
        self.assertFalse(d["irreversible"])
        self.assertFalse(d["requires_confirmation"])
        self.assertIn("already saved", d["risk"])

    def test_benign_actions_never_confirm(self):
        for action in (C.ACTION_INSPECT, C.ACTION_CREATE, C.ACTION_OPEN, C.ACTION_RECORD):
            d = C.describe_consequence(action, "/tmp/x",
                                       facts=_facts(has_uncommitted_changes=True,
                                                    has_unshared_work=True, branch_on_remote=True))
            self.assertFalse(d["requires_confirmation"],
                             f"{action} must never nag, even on a dirty target")
            self.assertFalse(d["destroys_unshared_work"])

    def test_affects_shared_ref_only_when_removing_a_shared_reference(self):
        d = C.describe_consequence(C.ACTION_REMOVE, "/tmp/x",
                                   facts=_facts(branch_on_remote=True), remove_saved_reference=True)
        self.assertTrue(d["affects_shared_ref"])
        self.assertTrue(d["requires_confirmation"])
        d2 = C.describe_consequence(C.ACTION_REMOVE, "/tmp/x",
                                    facts=_facts(branch_on_remote=True), remove_saved_reference=False)
        self.assertFalse(d2["affects_shared_ref"])

    # ---- verb -> effect mapping (kernel-owned; unknown = most cautious) ----
    def test_action_for_verb_mapping(self):
        self.assertEqual(C.action_for_verb("cleanup"), C.ACTION_REMOVE)
        self.assertEqual(C.action_for_verb("status"), C.ACTION_INSPECT)
        self.assertEqual(C.action_for_verb("list_protected"), C.ACTION_INSPECT)
        self.assertEqual(C.action_for_verb("protect"), C.ACTION_CREATE)
        self.assertEqual(C.action_for_verb("resume"), C.ACTION_OPEN)
        self.assertEqual(C.action_for_verb("save"), C.ACTION_RECORD)

    def test_unknown_verb_is_treated_as_most_cautious(self):
        """A spoofed/novel verb must resolve to the most cautious effect (remove) so it is confirmed
        against live facts, never waved through."""
        self.assertEqual(C.action_for_verb("definitely_not_a_verb"), C.ACTION_REMOVE)
        d = C.consequence_for_verb("definitely_not_a_verb", "/tmp/x",
                                   facts=_facts(has_unshared_work=True))
        self.assertTrue(d["requires_confirmation"])

    def test_safe_looking_verb_with_destructive_consequence_confirms(self):
        """THE airtight case: the router might mislabel/downgrade a destructive verb to look safe.
        The kernel confirmation is computed from the ACTUAL verb's effect + live facts, so a cleanup
        on a target holding unshared work ALWAYS confirms — no router label can suppress it."""
        d = C.consequence_for_verb("cleanup", "/tmp/x", facts=_facts(has_unshared_work=True))
        self.assertTrue(d["requires_confirmation"])
        self.assertTrue(d["destroys_unshared_work"])

    # ---- KI4 hygiene: the descriptor cannot be sourced from the router ----
    def test_descriptor_api_has_no_router_or_proposal_input(self):
        """Structural: describe_consequence's inputs are (action, target, facts, remove_saved_
        reference) only — there is no `proposal`/`router`/`confidence` parameter, so a router
        artifact structurally cannot influence the confirmation (KI4)."""
        params = set(inspect.signature(C.describe_consequence).parameters)
        self.assertEqual(params, {"action", "target_path", "facts", "remove_saved_reference"})
        for banned in ("proposal", "router", "confidence", "verdict", "safety_class"):
            self.assertNotIn(banned, params)

    # ---- fail-safe: unknown/unprobeable target leans toward destroy on a REMOVE ----
    def test_probe_fail_safe_on_non_git_dir(self):
        """A REMOVE on an existing directory that is NOT a resolvable checkout cannot PROVE its work
        is saved elsewhere -> has_unshared_work True -> confirm (fail-safe)."""
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "loose.txt").write_text("unsaved\n", encoding="utf-8")
            facts = C.probe_target(d)
            self.assertTrue(facts["exists"])
            self.assertTrue(facts["has_unshared_work"], "non-checkout dir cannot be proven shared")
            cons = C.describe_consequence(C.ACTION_REMOVE, d, facts=facts)
            self.assertTrue(cons["requires_confirmation"])

    def test_describe_is_deterministic(self):
        f = _facts(has_unshared_work=True)
        a = C.describe_consequence(C.ACTION_REMOVE, "/tmp/x", facts=f)
        b = C.describe_consequence(C.ACTION_REMOVE, "/tmp/x", facts=f)
        self.assertEqual(a, b)

    # ---- the module runs engine-off / router-off as a subprocess CLI ----
    def test_cli_describe_runs_standalone(self):
        lib = Path(C.__file__)
        r = subprocess.run(["python3", str(lib), "describe", "--verb", "status", "--target", "/tmp/x"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("consequence_descriptor/v1", r.stdout)


if __name__ == "__main__":
    unittest.main()
