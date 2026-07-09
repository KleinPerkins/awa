"""A0 deliverable 2: the thin operator loop — routing + the kernel-sourced confirmation gate.

Uses a FakeRouter so routing/gating logic is covered WITH THE ROUTER UNINSTALLED (kernel-first). A
separate section runs the REAL router when it is installed. Proves: the loop executes AWA's OWN verb
only after the gate passes; a destructive consequence always confirms; a benign strong verb never
nags; missing target -> ask; and the router is only ever asked to PROPOSE (never execute)."""

from __future__ import annotations

import unittest

from consumer import operator_loop as L

from .consumer_test_support import (FakeRouter, load_catalog, load_kernel_consequence,
                                    make_proposal, router_engine)

C = load_kernel_consequence()

F_UNSHARED = {"target": "/tmp/x", "exists": True, "disposition": "stale",
              "has_uncommitted_changes": True, "has_unshared_work": True, "branch_on_remote": False}
F_SAVED = {"target": "/tmp/x", "exists": True, "disposition": "stale",
           "has_uncommitted_changes": False, "has_unshared_work": False, "branch_on_remote": False}


def _record_executor(sink):
    def ex(verb, params, target):
        sink.append((verb, target))
        return {"ok": True, "verified": True, "detail": "done"}
    return ex


class TestOperatorLoop(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog()

    def _loop(self, mapping, executor=None):
        return L.OperatorLoop(self.catalog, router=FakeRouter(mapping), executor=executor)

    def test_destructive_unshared_awaits_confirmation(self):
        m = {"clean up": make_proposal(verb="cleanup", safety_class="destructive", verdict="strong",
                                       missing_params=["confirm", "which_work"], requires_confirmation=True)}
        r = self._loop(m).handle("clean up", target="/tmp/x", facts=F_UNSHARED)
        self.assertEqual(r["decision"], L.AWAITING_CONFIRMATION)
        self.assertTrue(r["confirmation"]["needs_confirmation"])
        self.assertTrue(r["consequence"]["destroys_unshared_work"])

    def test_confirmed_destructive_executes_awa_verb(self):
        calls = []
        m = {"clean up": make_proposal(verb="cleanup", safety_class="destructive", verdict="strong",
                                       missing_params=["confirm", "which_work"], requires_confirmation=True)}
        r = self._loop(m, executor=_record_executor(calls)).handle(
            "clean up", target="/tmp/x", facts=F_UNSHARED, confirm=True)
        self.assertEqual(r["decision"], L.EXECUTE)
        self.assertEqual(calls, [("cleanup", "/tmp/x")], "executes AWA's OWN verb, once, after confirm")
        self.assertTrue(r["narration"]["ok"])

    def test_benign_strong_write_does_not_nag(self):
        calls = []
        m = {"save my progress": make_proposal(verb="save", safety_class="write", verdict="strong",
                                               requires_confirmation=True)}
        r = self._loop(m, executor=_record_executor(calls)).handle(
            "save my progress", target="/tmp/x", facts=F_SAVED)
        self.assertEqual(r["decision"], L.EXECUTE, "a benign strong write must run without a nag")
        self.assertEqual(calls, [("save", "/tmp/x")])

    def test_cleanup_saved_elsewhere_still_confirms_via_cr9(self):
        """Even when the kernel says a removal is benign (work saved elsewhere), the destructive
        verb's CR9 literal-confirm slot forces an explicit confirmation — with honest copy."""
        m = {"clean up": make_proposal(verb="cleanup", safety_class="destructive", verdict="strong",
                                       missing_params=["confirm", "which_work"], requires_confirmation=True)}
        r = self._loop(m).handle("clean up", target="/tmp/x", facts=F_SAVED)
        self.assertEqual(r["decision"], L.AWAITING_CONFIRMATION)
        self.assertFalse(r["consequence"]["destroys_unshared_work"])
        self.assertIn("already saved", r["consequence"]["risk"])

    def test_missing_target_asks_before_acting(self):
        m = {"go back": make_proposal(verb="resume", safety_class="write", verdict="strong",
                                      missing_params=["which_work"], requires_confirmation=True)}
        r = self._loop(m).handle("go back", target=None, facts=F_SAVED)
        self.assertEqual(r["decision"], L.NEED_MORE_INFO)

    def test_none_verdict_offers_options_never_guesses(self):
        m = {"do the thing": make_proposal(verb="", verdict="none", safety_class="destructive",
                                           requires_confirmation=True)}
        r = self._loop(m).handle("do the thing", target="/tmp/x", facts=F_UNSHARED)
        self.assertEqual(r["decision"], L.NOT_UNDERSTOOD)
        self.assertIn("secondary_explicit_path", r)

    def test_feedback_record_is_feedback_v1_shaped(self):
        m = {"save my progress": make_proposal(verb="save", safety_class="write", verdict="strong")}
        r = self._loop(m, executor=_record_executor([])).handle(
            "save my progress", target="/tmp/x", facts=F_SAVED)
        fb = r["feedback"]
        for k in ("ts", "consumer", "catalog_version", "utterance", "proposal", "operator_choice",
                  "verdict", "confidence", "outcome", "session_id"):
            self.assertIn(k, fb)
        self.assertEqual(fb["consumer"], "awa")

    # ---- REAL router (skips when uninstalled) ----
    @unittest.skipIf(router_engine() is None, "router not installed (off-switch): real-router loop skipped")
    def test_real_router_destructive_utterance_confirms(self):
        loop = L.OperatorLoop(self.catalog)  # resolves the real router
        r = loop.handle("clean up my old safe copy", target="/tmp/x", facts=F_UNSHARED)
        self.assertTrue(r["router_available"])
        self.assertEqual(r["verb"], "cleanup")
        self.assertEqual(r["decision"], L.AWAITING_CONFIRMATION)
        self.assertTrue(r["consequence"]["destroys_unshared_work"])

    @unittest.skipIf(router_engine() is None, "router not installed (off-switch): real-router loop skipped")
    def test_real_router_benign_status_reads(self):
        loop = L.OperatorLoop(self.catalog)
        r = loop.handle("is everything okay", target="/tmp/x", facts=F_SAVED)
        self.assertTrue(r["router_available"])
        self.assertEqual(r["verb"], "status")
        self.assertFalse(r["consequence"]["requires_confirmation"], "a read is a benign kernel action")


if __name__ == "__main__":
    unittest.main()
