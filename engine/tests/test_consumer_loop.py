"""A0 deliverable 2: the thin operator loop — routing + the kernel-sourced confirmation gate.

Uses a FakeRouter so routing/gating logic is covered WITH THE ROUTER UNINSTALLED (kernel-first). A
separate section runs the REAL router when it is installed. Proves: the loop executes AWA's OWN verb
only after the gate passes; a destructive consequence always confirms; a benign strong verb never
nags; missing target -> ask; and the router is only ever asked to PROPOSE (never execute)."""

from __future__ import annotations

import json
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

    def test_confirmation_replay_is_bound_to_shown_verb_target_and_consequence(self):
        calls = []
        m = {"clean up": make_proposal(
            verb="cleanup", safety_class="destructive", verdict="strong",
            missing_params=["confirm", "which_work"], requires_confirmation=True)}
        loop = self._loop(m, executor=_record_executor(calls))
        shown = loop.handle("clean up", target="/tmp/x", facts=F_UNSHARED)
        fingerprint = shown["_internal"]["confirmation_fingerprint"]
        self.assertEqual(len(fingerprint), 64)
        drifted = loop.handle(
            "clean up",
            target="/tmp/y",
            facts={**F_UNSHARED, "target": "/tmp/y"},
            confirm=True,
            expected_confirmation_fingerprint=fingerprint,
        )
        self.assertEqual(drifted["decision"], L.AWAITING_CONFIRMATION)
        self.assertFalse(drifted["_internal"]["confirmation_replay_valid"])
        self.assertEqual(calls, [])
        accepted = loop.handle(
            "clean up",
            target="/tmp/x",
            facts=F_UNSHARED,
            confirm=True,
            expected_confirmation_fingerprint=fingerprint,
        )
        self.assertEqual(accepted["decision"], L.EXECUTE)
        self.assertTrue(accepted["_internal"]["confirmation_replay_valid"])
        self.assertEqual(calls, [("cleanup", "/tmp/x")])

    def test_benign_strong_write_does_not_nag(self):
        calls = []
        m = {"save my progress": make_proposal(verb="save", safety_class="write", verdict="strong",
                                               requires_confirmation=True)}
        r = self._loop(m, executor=_record_executor(calls)).handle(
            "save my progress", target="/tmp/x", facts=F_SAVED)
        self.assertEqual(r["decision"], L.EXECUTE, "a benign strong write must run without a nag")
        self.assertEqual(calls, [("save", "/tmp/x")])
        self.assertNotIn(
            "if you're happy",
            json.dumps(r["understanding"], ensure_ascii=False).lower(),
        )

    def test_cleanup_saved_elsewhere_still_confirms_via_cr9(self):
        """Even when the kernel says a removal is benign (work saved elsewhere), the destructive
        verb's CR9 literal-confirm slot forces an explicit confirmation — with honest copy."""
        m = {"clean up": make_proposal(verb="cleanup", safety_class="destructive", verdict="strong",
                                       missing_params=["confirm", "which_work"], requires_confirmation=True)}
        r = self._loop(m).handle("clean up", target="/tmp/x", facts=F_SAVED)
        self.assertEqual(r["decision"], L.AWAITING_CONFIRMATION)
        self.assertFalse(r["consequence"]["destroys_unshared_work"])
        self.assertIn("already saved", r["consequence"]["risk"])

    def test_lying_router_cannot_suppress_destructive_confirm_cr9(self):
        """MUST-FIX 1 — CR9 literal-confirm derives from the CATALOG, not the router. A maximally
        LYING router (missing_params=[], verdict=strong, safety_class mislabelled 'read',
        requires_confirmation=False) on a destructive-class verb whose kernel consequence is BENIGN
        (work saved elsewhere) must STILL await confirmation and must NOT execute. The only thing
        that can force the confirm here is the consumer catalog (cleanup.safety_class==destructive /
        its required literal `confirm` slot) — so the gate is fully router-independent. BITES pre-fix
        (old logic read `"confirm" in proposal.missing_params`, which the lie empties -> execute)."""
        calls = []
        m = {"clean up": make_proposal(verb="cleanup", safety_class="read", verdict="strong",
                                       missing_params=[], requires_confirmation=False)}
        r = self._loop(m, executor=_record_executor(calls)).handle(
            "clean up", target="/tmp/x", facts=F_SAVED)
        self.assertEqual(r["decision"], L.AWAITING_CONFIRMATION,
                         "a destructive-class verb must confirm even when the router lies (missing=[], strong)")
        self.assertEqual(calls, [], "must NOT execute a destructive verb without a confirmation")

    def test_affects_shared_ref_is_live_on_the_product_path(self):
        """SHOULD-FIX 4 — affects_shared_ref is reachable on the product path. A verb whose CATALOG
        entry declares `removes_shared_reference: true` makes the loop pass remove_saved_reference to
        the kernel, so the 'changes something other people rely on' confirmation reason surfaces.
        BITES pre-fix: the loop never passed remove_saved_reference, so the flag/reason were dead."""
        shared_verb = {
            "verb": "retire_shared", "aliases": ["retire the shared copy"],
            "examples": ["retire the shared copy"],
            "param_schema": [{"name": "confirm", "type": "bool", "required": True, "source": "literal"}],
            "preconditions": [], "safety_class": "destructive", "tool_path": "mcp",
            "start_point_rules": {"default": "named-target"},
            "plain_label": "Remove a copy other people also use",
            "consequence_copy": "Removes a copy that other people also use.",
            "removes_shared_reference": True,
        }
        cat = {**self.catalog, "verbs": list(self.catalog["verbs"]) + [shared_verb]}
        # A shared reference exists (branch_on_remote) but this copy's own work IS saved elsewhere,
        # so the ONLY reason to confirm-for-shared is the shared-ref removal -> isolates the fix.
        facts = {"target": "/tmp/x", "exists": True, "disposition": "stale",
                 "has_uncommitted_changes": False, "has_unshared_work": False, "branch_on_remote": True}
        m = {"retire the shared copy": make_proposal(
            verb="retire_shared", safety_class="destructive", verdict="strong",
            missing_params=[], requires_confirmation=True)}
        r = L.OperatorLoop(cat, router=FakeRouter(m)).handle(
            "retire the shared copy", target="/tmp/x", facts=facts)
        self.assertTrue(r["consequence"]["affects_shared_ref"],
                        "affects_shared_ref must be live on the product path (derived from the catalog)")
        self.assertEqual(r["decision"], L.AWAITING_CONFIRMATION)
        reasons = " ".join(r["confirmation"].get("why_it_matters", []))
        self.assertIn("other people rely on", reasons)

    def test_missing_target_asks_before_acting(self):
        m = {"go back": make_proposal(verb="resume", safety_class="write", verdict="strong",
                                      missing_params=["which_work"], requires_confirmation=True)}
        r = self._loop(m).handle("go back", target=None, facts=F_SAVED)
        self.assertEqual(r["decision"], L.NEED_MORE_INFO)

    def test_resolved_target_and_confirmation_slots_do_not_render_as_missing(self):
        m = {"clean up": make_proposal(
            verb="cleanup", safety_class="destructive", verdict="strong",
            missing_params=["confirm", "which_work"], requires_confirmation=True)}
        loop = self._loop(m)
        shown = loop.handle("clean up", target="/tmp/x", facts=F_UNSHARED)
        shown_text = json.dumps(shown["understanding"], ensure_ascii=False).lower()
        self.assertNotIn("which protected work", shown_text)
        replayed = loop.handle(
            "clean up",
            target="/tmp/x",
            facts=F_UNSHARED,
            confirm=True,
            expected_confirmation_fingerprint=shown["_internal"][
                "confirmation_fingerprint"
            ],
        )
        replayed_text = json.dumps(replayed["understanding"], ensure_ascii=False).lower()
        self.assertNotIn("say yes", replayed_text)
        self.assertNotIn("which protected work", replayed_text)
        self.assertNotIn("if you're happy", replayed_text)

    def test_none_verdict_offers_options_never_guesses(self):
        m = {"do the thing": make_proposal(verb="", verdict="none", safety_class="destructive",
                                           requires_confirmation=True)}
        r = self._loop(m).handle("do the thing", target="/tmp/x", facts=F_UNSHARED)
        self.assertEqual(r["decision"], L.NOT_UNDERSTOOD)
        self.assertIn("secondary_explicit_path", r)

    def test_raw_router_envelope_stays_out_of_pm_facing_output(self):
        """SHOULD-FIX 8 — the raw router envelope (tool_path/why[]/safety_class/start_point) is
        internal machinery and must not ride in the loop's PM-facing output. BITES pre-fix: the
        top-level result carried the raw proposal, so `tool_path='mcp'` leaked into anything that
        serialized the result."""
        m = {"save my progress": make_proposal(verb="save", safety_class="write", verdict="strong",
                                               tool_path="mcp", why=["safety_class:write"])}
        r = self._loop(m, executor=_record_executor([])).handle(
            "save my progress", target="/tmp/x", facts=F_SAVED)
        # the raw envelope is NOT a top-level (PM-facing) result field ...
        self.assertNotIn("proposal", r, "raw proposal must not be a top-level PM-facing result field")
        # ... and the sanctioned PM view carries zero internal routing metadata.
        pm = L.pm_view(r)
        blob = json.dumps(pm, ensure_ascii=False)
        for internal in ("tool_path", "mcp", "safety_class", "\"why\"", "start_point"):
            self.assertNotIn(internal, blob, f"PM view leaked internal field {internal!r}")
        # the PM view still carries the plain-language understanding the operator actually reads.
        self.assertIn("understanding", pm)
        self.assertEqual(pm["decision"], L.EXECUTE)

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
