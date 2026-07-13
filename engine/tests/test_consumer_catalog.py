"""A0 deliverable 1: AWA's real intent-catalog/v1 is well-formed and jargon-free.

Router-INDEPENDENT self-check (runs in `make verify` with the router uninstalled): the catalog
declares the frozen required-key floor per verb, valid enum values, the original five outcomes plus
the additive root-bound finish outcome, and
ZERO Tier A/B/C banned terms across every PM-facing / proposal-bound string (scanned with AWA's own
egress-terms snapshot). The seam test additionally proves the ROUTER'S authoritative catalog-verify
accepts this same file (when the router is installed)."""

from __future__ import annotations

import unittest

from consumer import egress

from .consumer_test_support import load_catalog

_REQUIRED_VERB_KEYS = {"verb", "aliases", "examples", "param_schema", "preconditions",
                       "safety_class", "tool_path", "start_point_rules", "plain_label",
                       "consequence_copy"}
_REQUIRED_PARAM_KEYS = {"name", "type", "required"}
_SAFETY = {"read", "write", "destructive"}
_TOOL = {"cli", "mcp", "hook"}
_PTYPE = {"string", "int", "number", "bool", "enum", "path", "ref"}
_PSOURCE = {"literal", "regex", "enum", "repo-resolver", "llm"}


class TestConsumerCatalog(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog()
        self.verbs = self.catalog.get("verbs", [])

    def test_schema_and_shape(self):
        self.assertEqual(self.catalog.get("schema"), "intent-catalog/v1")
        self.assertEqual(self.catalog.get("consumer"), "awa")
        self.assertGreaterEqual(len(self.verbs), 5, "at least the five-outcome verb set")

    def test_original_five_plus_finish_outcome_present(self):
        outcomes = self.catalog.get("outcomes", [])
        self.assertEqual(len(outcomes), 6, "original five outcomes plus additive finish_current")
        verbs_named = {v for o in outcomes for v in o.get("verbs", [])}
        catalog_verbs = {v.get("verb") for v in self.verbs}
        self.assertTrue(verbs_named <= catalog_verbs,
                        f"outcomes reference unknown verbs: {verbs_named - catalog_verbs}")

    def test_every_verb_satisfies_frozen_floor(self):
        for i, v in enumerate(self.verbs):
            missing = _REQUIRED_VERB_KEYS - set(v)
            self.assertEqual(missing, set(), f"verb[{i}] {v.get('verb')!r} missing {missing}")
            self.assertIn(v["safety_class"], _SAFETY, f"verb[{i}] bad safety_class")
            self.assertIn(v["tool_path"], _TOOL, f"verb[{i}] bad tool_path")
            self.assertIsInstance(v["aliases"], list)
            self.assertIsInstance(v["examples"], list)
            self.assertIsInstance(v["start_point_rules"], dict)
            for p in v["param_schema"]:
                pmissing = _REQUIRED_PARAM_KEYS - set(p)
                self.assertEqual(pmissing, set(), f"{v['verb']} param missing {pmissing}")
                self.assertIn(p["type"], _PTYPE, f"{v['verb']} param bad type")
                self.assertIsInstance(p["required"], bool)
                if "source" in p:
                    self.assertIn(p["source"], _PSOURCE)

    def test_destructive_verb_carries_literal_confirm_slot(self):
        """Old-copy cleanup keeps CR9 bool confirmation. finish_current deliberately has no trusted
        boolean bypass; its later literal Close is kernel challenge-bound."""
        for v in self.verbs:
            if v["safety_class"] == "destructive":
                if v["verb"] == "finish_current":
                    self.assertFalse(
                        [p for p in v["param_schema"] if p.get("name") == "confirm"],
                        "finish_current must not accept the legacy trusted-bool confirm slot")
                    continue
                confirm = [p for p in v["param_schema"] if p.get("name") == "confirm"]
                self.assertTrue(confirm, f"destructive verb {v['verb']!r} lacks a confirm slot")
                self.assertEqual(confirm[0].get("type"), "bool")
                self.assertEqual(confirm[0].get("source"), "literal")
                self.assertIs(confirm[0].get("required"), True)

    def test_zero_banned_terms_across_pm_facing_strings(self):
        """The system-wide egress gate at catalog authorship time: zero Tier A/B/C banned terms in
        any PM-facing / proposal-bound string. Uses AWA's own snapshot -> router-independent."""
        offenders = egress.scan_catalog(self.catalog)
        self.assertEqual(offenders, [], "banned term(s) in AWA catalog PM-facing strings:\n"
                         + "\n".join(offenders))


if __name__ == "__main__":
    unittest.main()
