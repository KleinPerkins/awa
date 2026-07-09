"""A0 deliverable 3: plain-language translators — honest confidence, zero banned terms.

Router-INDEPENDENT. Proves every rendering (proposal / confirmation / block / outcome) carries an
HONEST-confidence structure (what was checked AND what was not — never a bare status) and zero Tier
A/B/C banned terms across all rendered strings (AWA snapshot)."""

from __future__ import annotations

import unittest

from consumer import egress, translators

from .consumer_test_support import load_catalog, make_proposal


class TestTranslators(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog()
        self.entry = {v["verb"]: v for v in self.catalog["verbs"]}

    def test_proposal_strong_has_honest_confidence(self):
        p = make_proposal(verb="protect", safety_class="write", verdict="strong",
                          requires_confirmation=True)
        r = translators.render_proposal(p, self.entry["protect"])
        self.assertTrue(r["understood"])
        conf = r["confidence"]
        self.assertIn("checked", conf)
        self.assertIn("not_checked", conf)
        self.assertTrue(conf["checked"] and conf["not_checked"], "must state both sides honestly")

    def test_proposal_weak_expresses_uncertainty(self):
        p = make_proposal(verb="status", safety_class="read", verdict="weak",
                          requires_confirmation=True)
        r = translators.render_proposal(p, self.entry["status"])
        self.assertIn("not", r["confidence"]["plain"].lower())  # "not fully sure"

    def test_proposal_none_offers_options_and_does_not_guess(self):
        p = make_proposal(verb="", verdict="none", safety_class="destructive",
                          requires_confirmation=True)
        r = translators.render_proposal(p, None)
        self.assertFalse(r["understood"])
        self.assertTrue(len(r["options"]) >= 5)
        self.assertIn("didn't", r["confidence"]["not_checked"].lower() + r["plain"].lower())

    def test_confirmation_destructive_spells_out_risk(self):
        cons = {
            "action_label": "Remove an old safe copy", "destroys_unshared_work": True,
            "irreversible": True, "affects_shared_ref": False, "requires_confirmation": True,
            "risk": "This safe copy still has work that is not saved anywhere else.",
            "undo": "The unsaved work cannot be brought back.",
            "irreversible_step": "Once removed, the unsaved work is gone.",
        }
        r = translators.render_confirmation(cons, self.entry["cleanup"])
        self.assertTrue(r["needs_confirmation"])
        self.assertTrue(r["ask"])
        self.assertTrue(r["undo"])
        self.assertTrue(r["point_of_no_return"])
        self.assertTrue(any("lost" in w for w in r["why_it_matters"]))

    def test_confirmation_benign_does_not_nag(self):
        cons = {
            "action_label": "Check whether your work is protected",
            "destroys_unshared_work": False, "irreversible": False, "affects_shared_ref": False,
            "requires_confirmation": False, "risk": "Nothing will be lost.", "undo": "", "irreversible_step": "",
        }
        r = translators.render_confirmation(cons)
        self.assertFalse(r["needs_confirmation"])
        self.assertIsNone(r["ask"])

    def test_block_is_reassuring_and_plain(self):
        r = translators.render_block({"reason": "there was work that wasn't saved yet",
                                      "next": "Save it first, then ask me again."})
        self.assertTrue(r["blocked"])
        self.assertIn("Nothing was changed", r["reassurance"])

    def test_outcome_is_honest_about_failure(self):
        ok = translators.render_outcome(True, did="save your progress", detail="I checked and it worked.")
        bad = translators.render_outcome(False, did="save your progress")
        self.assertTrue(ok["ok"])
        self.assertFalse(bad["ok"])
        self.assertIn("untouched", bad["plain"].lower())

    def test_zero_banned_terms_across_all_renderings(self):
        """Every rendered surface (proposal / confirmation / block / outcome) across every verb must
        carry zero Tier A/B/C banned terms."""
        rendered = []
        for verb, entry in self.entry.items():
            for verdict in ("strong", "weak", "none"):
                p = make_proposal(verb=verb if verdict != "none" else "",
                                  safety_class=entry["safety_class"], verdict=verdict,
                                  missing_params=[pp["name"] for pp in entry["param_schema"]
                                                  if pp.get("required")],
                                  requires_confirmation=True)
                rendered.append(translators.render_proposal(p, entry if verdict != "none" else None))
        # confirmations (destructive + benign)
        rendered.append(translators.render_confirmation({
            "action_label": "Remove an old safe copy", "destroys_unshared_work": True,
            "irreversible": True, "affects_shared_ref": True, "requires_confirmation": True,
            "risk": "Work that is not saved anywhere else would be lost for good.",
            "undo": "The unsaved work cannot be brought back.",
            "irreversible_step": "Once removed, the unsaved work is gone.",
        }, self.entry["cleanup"]))
        rendered.append(translators.render_block({"reason": "some work was not saved yet"}))
        rendered.append(translators.render_outcome(False, did="remove an old safe copy"))
        offenders = egress.scan_object(rendered)
        self.assertEqual(offenders, [], "banned term(s) in rendered PM-facing text:\n"
                         + "\n".join(offenders))


if __name__ == "__main__":
    unittest.main()
