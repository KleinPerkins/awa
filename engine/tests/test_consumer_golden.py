"""A0 deliverable 5: the 25-30 utterance golden set is well-formed, safety-invariant, and (when the
router is installed) reproduced EXACTLY by the router's deterministic floor over AWA's REAL catalog.

Two layers:
  * ALWAYS (router-independent): the pinned data is shape-valid, covers every required category, and
    every case satisfies the safety invariants declared in the file (destructive/injection/negative/
    all). This is a property of the PIN itself, so it holds with the router uninstalled.
  * WHEN INSTALLED: the router's L0-L2+L5 floor (no LLM) reproduces each pinned proposal over the
    real catalog. This is the regression + safety pin against the actual router; it SKIPS when the
    router is uninstalled (kernel-first)."""

from __future__ import annotations

import unittest

from .consumer_test_support import CATALOG_PATH, load_catalog, load_golden, router_engine

_VERDICTS = {"strong", "weak", "none"}
_SAFETY = {"read", "write", "destructive"}
_REQUIRED_CATEGORIES = {"destructive", "injection", "negative", "reentry", "okay-check",
                        "calibration-review", "ambiguous"}


class TestGoldenSetShape(unittest.TestCase):
    def setUp(self):
        self.golden = load_golden()
        self.cases = self.golden["cases"]

    def test_count_is_25_to_30(self):
        self.assertGreaterEqual(len(self.cases), 25)
        self.assertLessEqual(len(self.cases), 30)

    def test_every_case_is_well_formed(self):
        for c in self.cases:
            self.assertIn("utterance", c)
            self.assertIn("category", c)
            e = c["expect"]
            self.assertIn(e["verdict"], _VERDICTS, c["utterance"])
            self.assertIn(e["safety_class"], _SAFETY, c["utterance"])
            self.assertIsInstance(e["requires_confirmation"], bool, c["utterance"])
            self.assertIsInstance(e["missing_params"], list, c["utterance"])

    def test_required_categories_present(self):
        cats = {c["category"] for c in self.cases}
        missing = _REQUIRED_CATEGORIES - {x.split("-")[0] if x != "ambiguous-destructive" else "ambiguous"
                                          for x in cats} - cats
        # accept either exact category or its prefix family
        present_families = set()
        for c in cats:
            present_families.add(c)
            present_families.add(c.split("-")[0])
        self.assertEqual(_REQUIRED_CATEGORIES - present_families, set(),
                         f"golden set missing required categories: {_REQUIRED_CATEGORIES - present_families}")

    # ---- safety invariants (properties of the PIN; hold router-uninstalled) ----
    def test_invariant_all_cases_require_confirmation(self):
        for c in self.cases:
            self.assertTrue(c["expect"]["requires_confirmation"],
                            f"every golden case must require confirmation (no strong no-missing read): {c['utterance']!r}")

    def test_invariant_destructive_cases(self):
        for c in self.cases:
            if c["category"] in ("destructive", "ambiguous-destructive"):
                e = c["expect"]
                self.assertEqual(e["verb"], "cleanup", c["utterance"])
                self.assertEqual(e["safety_class"], "destructive", c["utterance"])
                self.assertTrue(e["requires_confirmation"], c["utterance"])

    def test_invariant_injection_never_buys_a_no_confirm_read(self):
        for c in self.cases:
            if c["category"] == "injection":
                e = c["expect"]
                self.assertNotEqual(e["safety_class"], "read",
                                    f"injection content must never yield a read: {c['utterance']!r}")
                self.assertTrue(e["requires_confirmation"], c["utterance"])

    def test_invariant_negative_yields_none(self):
        for c in self.cases:
            if c["category"] == "negative":
                self.assertEqual(c["expect"]["verdict"], "none",
                                 f"a negative/off-domain utterance must not match a verb: {c['utterance']!r}")


@unittest.skipIf(router_engine() is None,
                 "router not installed (off-switch): golden propose skipped — AWA verify passes router-uninstalled")
class TestGoldenAgainstRealRouter(unittest.TestCase):
    def setUp(self):
        self.golden = load_golden()
        self.catalog = load_catalog()

    def test_router_reproduces_every_pinned_proposal(self):
        engine = router_engine()
        failures = []
        for c in self.golden["cases"]:
            p = engine.propose("awa", c["utterance"], self.catalog)
            e = c["expect"]
            got = {"verdict": p["verdict"], "verb": p["verb"], "safety_class": p["safety_class"],
                   "requires_confirmation": p["requires_confirmation"],
                   "missing_params": sorted(p["missing_params"])}
            want = {"verdict": e["verdict"], "verb": e["verb"], "safety_class": e["safety_class"],
                    "requires_confirmation": e["requires_confirmation"],
                    "missing_params": sorted(e["missing_params"])}
            if got != want:
                failures.append(f"{c['utterance']!r}: got {got} != pinned {want}")
        self.assertEqual(failures, [], "golden drift vs the real router:\n" + "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
