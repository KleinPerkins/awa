"""A0 deliverable 6: the router<->AWA SEAM test — pins the router's contract-version strings.

Neither repo's own CI tests the seam; THIS is that test. It runs only when the router is INSTALLED
(importable) — when it is not, it SKIPS (that is the kernel-first / off-switch property: AWA's
`make verify` passes with the router uninstalled). AWA obtains the router pre-release by putting a
clone checked out at the pinned ref (consumer/router-pin.json) on PYTHONPATH so `import intent_router`
resolves.

A router contract-version bump (v1 -> v2), a rename, or unfreezing the proposal MUST break this test."""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from consumer import egress

from .consumer_test_support import CATALOG_PATH, load_router_pin, router_engine


class TestSeamRouterPresence(unittest.TestCase):
    """Always-present guard (NOT skipped). The dedicated CI seam job co-installs the pinned router
    and sets AWA_SEAM_REQUIRE_ROUTER=1; in that mode a NON-importable router is a HARD FAILURE — never
    a silent skip — so a broken co-install (or a router that drifted so far it won't import) turns
    AWA CI red. In normal `make verify` (router uninstalled, env unset) this passes while the
    router-dependent seam class below skips, preserving the kernel-first / off-switch property
    (SHOULD-FIX 5)."""

    def test_router_present_when_required(self):
        if os.environ.get("AWA_SEAM_REQUIRE_ROUTER") == "1":
            self.assertIsNotNone(
                router_engine(),
                "AWA_SEAM_REQUIRE_ROUTER=1 but the router is not importable — the CI seam co-install "
                "failed or the pinned router drifted. The seam must run NON-skipped in that job.")


def _router_repo_root():
    """The router repo root, derived from the installed package (intent_router/ -> repo root)."""
    import intent_router  # type: ignore
    return Path(intent_router.__file__).resolve().parent.parent


@unittest.skipIf(router_engine() is None,
                 "router not installed (off-switch): seam test skipped — AWA verify passes router-uninstalled")
class TestRouterSeam(unittest.TestCase):
    def setUp(self):
        self.pin = load_router_pin()
        self.root = _router_repo_root()
        self.contracts = self.root / "contracts"

    def test_catalog_schema_string_matches_pin(self):
        import intent_router.catalog as catalog  # type: ignore
        self.assertEqual(catalog.SCHEMA, self.pin["expected_contract_versions"]["intent-catalog"])

    def test_proposal_contract_is_frozen_at_pinned_version(self):
        c = json.loads((self.contracts / "intent-proposal.v1.json").read_text(encoding="utf-8"))
        self.assertEqual(c["schema"], self.pin["expected_contract_versions"]["intent-proposal"])
        self.assertEqual(c["status"], self.pin["expected_proposal_status"],
                         "the seam pins intent-proposal/v1 as FROZEN; unfreezing must break the seam")
        self.assertTrue(c.get("frozen"), "a frozen proposal must record a frozen date")

    def test_catalog_contract_schema_string_matches_pin(self):
        c = json.loads((self.contracts / "intent-catalog.v1.json").read_text(encoding="utf-8"))
        self.assertEqual(c["schema"], self.pin["expected_contract_versions"]["intent-catalog"])

    def test_constitution_schema_string_matches_pin(self):
        c = json.loads((self.contracts / "intent-constitution.v1.json").read_text(encoding="utf-8"))
        self.assertEqual(c["schema"], self.pin["expected_contract_versions"]["intent-constitution"])

    def test_router_authoritative_catalog_verify_accepts_awa_catalog(self):
        """The router's OWN catalog-verify (the authoritative egress + shape gate) passes AWA's REAL
        catalog with zero Tier A/B/C banned terms. This is the cross-repo proof of deliverable 1."""
        import intent_router.catalog as catalog  # type: ignore
        ok, errors = catalog.verify_catalog_file(CATALOG_PATH)
        self.assertTrue(ok, "router catalog-verify rejected AWA's catalog:\n" + "\n".join(errors))

    def test_constitution_egress_check_active_if_declared(self):
        """Cross-repo flip enforcement: once the system-wide operator egress gate is active (AWA side
        declared in consumer/egress-gate.v1.json), the router constitution's `egress` machine-check
        must read `active`, not `spec`. Defensive: if the router constitution does not (yet) carry a
        machine_checks map, this is a no-op — so it never fails for an unrelated shape, but it turns
        the co-installed seam job RED if the router still declares egress as `spec`."""
        c = json.loads((self.contracts / "intent-constitution.v1.json").read_text(encoding="utf-8"))
        checks = c.get("machine_checks") or c.get("checks") or {}
        if isinstance(checks, dict) and "egress" in checks:
            want = self.pin.get("expected_constitution_checks", {}).get("egress", "active")
            self.assertEqual(str(checks["egress"]).lower(), want,
                             "router constitution `egress` machine-check must be flipped spec->active "
                             "(consumer/egress-gate.v1.json + router-pin.json expect 'active')")

    def test_awa_egress_snapshot_is_superset_of_router_tiers(self):
        """Drift guard: AWA's local egress snapshot must contain every shared Tier A + Tier B term the
        router constitution declares. If the router ADDS a shared banned term, AWA's snapshot must be
        updated or this fails."""
        c = json.loads((self.contracts / "intent-constitution.v1.json").read_text(encoding="utf-8"))
        router_shared = set(c["banned_terms"]["tier_a_generic_mechanism"]) | \
            set(c["banned_terms"]["tier_b_git_workflow"])
        awa_terms = set(egress.load_terms())
        missing = router_shared - awa_terms
        self.assertEqual(missing, set(),
                         f"AWA egress snapshot is missing shared router tiers: {sorted(missing)}")

    def test_matcher_logic_agrees_with_router(self):
        """AWA's router-independent matcher must MIRROR the router's authoritative matcher exactly.
        Run both over a battery with the SAME term set to isolate matcher logic (bounded, case rules).
        """
        import intent_router.catalog as catalog  # type: ignore
        terms = egress.load_terms()
        battery = [
            "Start protecting this work", "go back to earlier work", "nothing changed here",
            "WORKTREE and Merge and KERNEL", "the head of the queue", "print the result",
            "your branch is ahead", "this is a safe copy", "remove an old copy", "--bundle now",
            "primary checkout", "HEAD detached at origin/main", "just proceed please",
        ]
        for s in battery:
            self.assertEqual(egress.find_banned_terms(s, terms),
                             catalog.find_banned_terms(s, terms),
                             f"matcher divergence on {s!r}")


if __name__ == "__main__":
    unittest.main()
