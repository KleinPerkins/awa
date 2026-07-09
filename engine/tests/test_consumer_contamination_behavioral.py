"""A0 deliverable 7b (KI3): BEHAVIORAL non-contamination — the router can NEVER buy an execute.

A confidence-1.0 proposal that LIES ("this is a safe read, no confirmation needed") over a
destructive verb on unshared work must yield the IDENTICAL kernel decision as the hand-typed
equivalent (router absent). The kernel consequence gate dominates: the loop still awaits
confirmation; the router never turns a kernel confirm/refuse into an allow."""

from __future__ import annotations

import unittest

from consumer import operator_loop as L

from .consumer_test_support import FakeRouter, load_catalog, load_kernel_consequence, make_proposal

C = load_kernel_consequence()

F_UNSHARED = {"target": "/tmp/x", "exists": True, "disposition": "stale",
              "has_uncommitted_changes": True, "has_unshared_work": True, "branch_on_remote": False}


class TestBehavioralContamination(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog()

    def test_confident_lying_proposal_yields_identical_kernel_decision(self):
        # Hand-typed baseline: kernel consequence for cleanup on unshared work, NO router involved.
        baseline = C.consequence_for_verb("cleanup", "/tmp/x", facts=F_UNSHARED)

        # A maximally-confident LIE from the router: safety_class=read, strong, no missing, no confirm.
        liar = FakeRouter({"clean up": make_proposal(
            verb="cleanup", safety_class="read", verdict="strong", confidence=1.0,
            missing_params=[], requires_confirmation=False)})
        calls = []
        loop = L.OperatorLoop(self.catalog, router=liar,
                              executor=lambda v, p, t: calls.append((v, t)) or {"ok": True, "verified": True})
        r = loop.handle("clean up", target="/tmp/x", facts=F_UNSHARED)

        # IDENTICAL kernel decision, regardless of the router's confident lie.
        self.assertEqual(r["consequence"], baseline)
        self.assertTrue(r["consequence"]["destroys_unshared_work"])
        self.assertTrue(r["consequence"]["requires_confirmation"])

        # The router could NOT buy an execute: the loop still awaits confirmation and ran no verb.
        self.assertEqual(r["decision"], L.AWAITING_CONFIRMATION)
        self.assertEqual(calls, [], "router confidence=1.0 must NEVER execute a destructive verb")

    def test_confidence_does_not_move_the_kernel_gate(self):
        """The kernel consequence is a pure function of (verb, target, facts). Two proposals that
        differ ONLY in router confidence/verdict/safety_class produce the SAME kernel decision."""
        results = []
        for conf, verdict, sclass, conf_flag in [
            (1.0, "strong", "read", False),   # confident lie
            (0.05, "weak", "destructive", True),  # timid truth
        ]:
            fr = FakeRouter({"clean up": make_proposal(
                verb="cleanup", safety_class=sclass, verdict=verdict, confidence=conf,
                missing_params=(["confirm", "which_work"] if conf_flag else []),
                requires_confirmation=conf_flag)})
            r = L.OperatorLoop(self.catalog, router=fr).handle("clean up", target="/tmp/x", facts=F_UNSHARED)
            results.append(r["consequence"])
            self.assertEqual(r["decision"], L.AWAITING_CONFIRMATION)  # both must confirm
        self.assertEqual(results[0], results[1], "router confidence must not move the kernel gate")

    def test_kernel_refuse_cannot_be_flipped_to_allow(self):
        """A confident read-labeled proposal for a destructive verb can never downgrade the kernel's
        'destroys unshared work' into a no-confirm allow — this is the defense for the router's
        structural destructive->read limit."""
        fr = FakeRouter({"delete it": make_proposal(
            verb="cleanup", safety_class="read", verdict="strong", confidence=1.0,
            missing_params=[], requires_confirmation=False)})
        r = L.OperatorLoop(self.catalog, router=fr).handle("delete it", target="/tmp/x", facts=F_UNSHARED)
        self.assertNotEqual(r["decision"], L.EXECUTE)
        self.assertTrue(r["consequence"]["destroys_unshared_work"])


if __name__ == "__main__":
    unittest.main()
