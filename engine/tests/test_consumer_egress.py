"""A0: the system-wide egress gate across the consumer's A0 PM-facing surfaces — ZERO banned terms.

This is the router-INDEPENDENT, behavioral egress proof (runs inside AWA's `make verify` with the
router uninstalled). It scans the ACTUAL chat surface a PM sees: the catalog copy, the loop's static
secondary-path text, and the LIVE loop renderings (understanding + confirmation + narration +
degrade) produced for all 30 golden utterances (via a FakeRouter built from the pinned golden
expectations, so the surface matches what the real router would drive). Any Tier A/B/C leak fails."""

from __future__ import annotations

import unittest

from consumer import egress, operator_loop as L, translators

from .consumer_test_support import FakeRouter, load_catalog, load_golden, make_proposal

# Kernel target facts that maximize rendered confirmation copy (unshared work -> spells out risk).
F_UNSHARED = {"target": "/tmp/x", "exists": True, "disposition": "stale",
              "has_uncommitted_changes": True, "has_unshared_work": True, "branch_on_remote": False}


def _proposal_from_golden(expect: dict) -> dict:
    verdict = expect.get("verdict", "none")
    conf = {"strong": 1.0, "weak": 0.5}.get(verdict, 0.0)
    return make_proposal(
        verb=expect.get("verb", ""), safety_class=expect.get("safety_class", "read"),
        verdict=verdict, confidence=conf, missing_params=list(expect.get("missing_params", [])),
        requires_confirmation=expect.get("requires_confirmation", True))


class TestConsumerEgress(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog()
        self.golden = load_golden()

    def test_catalog_is_jargon_free(self):
        self.assertEqual(egress.scan_catalog(self.catalog), [],
                         "AWA catalog leaks banned term(s) on a PM-facing/proposal-bound field")

    def test_secondary_explicit_path_is_jargon_free(self):
        self.assertEqual(egress.scan_object(L._SECONDARY_EXPLICIT_PATH), [])

    def test_live_loop_surface_over_golden_set_is_jargon_free(self):
        """Drive the loop over every golden utterance and scan the full PM-facing rendering. This is
        the closest thing to the real chat transcript: understanding, kernel confirmation, narration,
        and any secondary path — all rendered, all scanned."""
        mapping = {c["utterance"]: _proposal_from_golden(c["expect"]) for c in self.golden["cases"]}
        offenders: list[str] = []
        for case in self.golden["cases"]:
            utt = case["utterance"]
            loop = L.OperatorLoop(self.catalog, router=FakeRouter(mapping),
                                  executor=lambda v, p, t: {"ok": True, "verified": True,
                                                            "detail": "I checked afterwards and it worked."})
            # Two renderings per utterance: the pre-confirm turn, and (for confirmables) the confirmed turn.
            for confirm in (None, True):
                r = loop.handle(utt, target="/tmp/x", facts=F_UNSHARED, confirm=confirm)
                surface = {k: r.get(k) for k in ("understanding", "confirmation", "narration",
                                                 "secondary_explicit_path")}
                hits = egress.scan_object(surface)
                if hits:
                    offenders.append(f"utterance={utt!r} confirm={confirm}: {hits}")
        self.assertEqual(offenders, [], "live loop surface leaked banned term(s)")

    def test_degrade_to_ask_surface_is_jargon_free(self):
        loop = L.OperatorLoop(self.catalog)
        loop._router, loop._router_resolved = None, True
        r = loop.handle("clean up my old copy", target="/tmp/x", facts=F_UNSHARED)
        self.assertEqual(egress.scan_object({k: r.get(k) for k in
                         ("understanding", "secondary_explicit_path")}), [])

    def test_block_rendering_is_jargon_free(self):
        # A kernel block should never leak the mechanism to the PM.
        block = translators.render_block({"reason": "there is unsaved work here", "next": "Tell me what to do."})
        self.assertEqual(egress.scan_object(block), [])


if __name__ == "__main__":
    unittest.main()
