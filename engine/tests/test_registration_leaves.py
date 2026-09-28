from __future__ import annotations

import unittest
import sqlite3

from engine import registration_schema, registration_store
from engine.tests.registration_leaf_scenarios import run_scenario


SCENARIOS = {
    "trg_protocol_epoch_insert": {
        "bootstrap": "bootstrap",
        "activate": "activate",
        "first_effect": "open",
        "begin_drain": "begin_drain",
        "stage_next": "stage_next",
        "cancel_drain": "cancel_drain",
        "advance_generation": "advance_generation",
        "pre_effect_dormant": "pre_effect_dormant",
        "contain_boot": "contain_boot",
        "contain_timeout": "contain_timeout",
        "contain_adoption": "contain_adoption",
        "contain_store": "contain_store",
        "begin_repair": "begin_repair",
    },
    "trg_operation_audit_insert": {
        "bootstrap": "bootstrap",
        "install_member": "install_clean",
        "bind_episode": "bind",
        "reacquire": "reacquire_native",
        "open": "open",
        "append": "append_observed",
        "close_success": "close_success_idle",
        "close_conflict": "close_conflict_idle",
        "invalidate": "invalidate_clean",
        "set_pending": "set_pending",
        "replace_pending": "replace_pending",
        "handoff": "handoff_basis_clean",
        "mark_unavailable": "mark_unavailable",
        "reboot": "reboot_requested_clean",
        "schedule": "schedule",
        "activate": "activate",
        "begin_drain": "begin_drain",
        "stage_next": "stage_next",
        "cancel_drain": "cancel_drain",
        "adopt": "adopt_preserve",
        "advance": "advance_generation",
        "pre_effect_dormant": "pre_effect_dormant",
        "contain": "contain_store",
        "begin_repair": "begin_repair",
    },
    "trg_member_update_state_machine": {
        "invalidate": "invalidate_clean",
        "open": "open",
        "set_pending": "set_pending",
        "replace_pending": "replace_pending",
        "adopt_preserve": "adopt_preserve",
        "adopt_replace": "adopt_replace",
        "close_success": "close_success_idle",
        "close_conflict": "close_conflict_idle",
        "handoff_pending": "handoff_pending",
        "handoff_basis": "handoff_basis_clean",
        "handoff_closure": "handoff_closure_clean",
        "handoff_conflict_retry": "handoff_conflict_retry",
    },
    "trg_episode_insert": {"bind": "bind"},
    "trg_effect_insert": {
        "install": "install_clean",
        "invalidate": "invalidate_clean",
        "set_pending": "set_pending",
        "replace_pending": "replace_pending",
        "handoff_basis": "handoff_basis_clean",
        "handoff_closure": "handoff_closure_clean",
        "handoff_conflict_retry": "handoff_conflict_retry",
        "adopt_replace": "adopt_replace",
    },
    "trg_effect_close": {
        "success": "close_success_idle",
        "conflict": "close_conflict_idle",
        "supersede_requested": "invalidate_clean",
        "supersede_pending": "replace_pending",
        "supersede_adopted": "adopt_replace",
    },
    "trg_effect_action_append": {
        "observed_exact": "append_observed",
        "applied_verified": "append_applied",
        "logical_conflict": "append_conflict",
    },
    "trg_runtime_status_insert": {
        "clean": "install_clean",
        "dirty": "install_dirty",
        "operation_blocked": "install_operation",
    },
    "trg_runtime_status_update": {
        "reacquire_native": "reacquire_native",
        "reacquire_adopted": "reacquire_adopted",
        "open": "open",
        "close_success_idle": "close_success_idle",
        "close_success_pending": "close_success_pending",
        "close_conflict_idle": "close_conflict_idle",
        "close_conflict_pending": "close_conflict_pending",
        "invalidate_clean": "invalidate_clean",
        "invalidate_dirty": "invalidate_dirty",
        "invalidate_operation": "invalidate_operation",
        "handoff_basis_clean": "handoff_basis_clean",
        "handoff_basis_dirty": "handoff_basis_dirty",
        "handoff_basis_operation": "handoff_basis_operation",
        "handoff_closure_clean": "handoff_closure_clean",
        "handoff_closure_dirty": "handoff_closure_dirty",
        "handoff_closure_operation": "handoff_closure_operation",
        "handoff_conflict_retry": "handoff_conflict_retry",
        "adopt_preserve": "adopt_preserve",
        "adopt_install": "adopt_install",
        "mark_unavailable": "mark_unavailable",
        "reboot_requested_clean": "reboot_requested_clean",
        "reboot_requested_dirty": "reboot_requested_dirty",
        "reboot_requested_operation": "reboot_requested_operation",
        "reboot_in_flight": "reboot_in_flight",
        "reboot_resolved_success": "reboot_resolved_success",
        "reboot_resolved_conflict": "reboot_resolved_conflict",
        "reboot_resolved_pending": "reboot_resolved_pending",
        "schedule": "schedule",
    },
}


@unittest.skipUnless(
    sqlite3.sqlite_version_info >= registration_store.MIN_SQLITE_VERSION,
    "ADR 0025 requires stock SQLite >=3.51.3",
)
class RegistrationLeafCoverageTest(unittest.TestCase):
    def test_every_generated_leaf_has_independent_valid_transaction(self) -> None:
        catalog = {
            f"{trigger}|{leaf.replace('@', '|')}": SCENARIOS[trigger][
                leaf.split("@", 1)[0]
            ]
            for trigger, leaves in registration_schema.LEAF_GROUPS.items()
            for leaf in leaves
        }
        self.assertEqual(frozenset(catalog), registration_schema.LEAF_IDS)
        self.assertEqual(len(catalog), 97)
        for leaf_id, scenario in catalog.items():
            with self.subTest(leaf_id=leaf_id, scenario=scenario):
                observed = run_scenario(scenario)
                self.assertIn(leaf_id, observed)


if __name__ == "__main__":
    unittest.main()
