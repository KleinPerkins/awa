from __future__ import annotations

import json
import re
import unittest

from engine import (
    registration_admission,
    registration_schema,
    registration_view,
)
from engine.tests.test_registration_admission_b import (
    E,
    H,
    M,
    _authority,
    _basis,
    _host,
    _payload,
    _receipt,
)


def _project(authority=None, host=None):
    return registration_view.project_status(
        authority or _authority(),
        host or _host(),
        event=registration_admission.parse_registration_event(_payload()),
        basis=_basis(),
        receipt=_receipt(),
        expected_candidate_digest="22" * 32,
        episode_id=H,
        discriminator="shell",
        inventory=registration_admission.ToolInventory(
            ordinary=frozenset({"shell"}),
            task_launch=frozenset({"Task"}),
        ),
    )


class RegistrationViewTest(unittest.TestCase):
    def test_all_twenty_six_runtime_reasons_render_deterministically(self) -> None:
        self.assertEqual(len(registration_admission.RUNTIME_REASONS), 26)
        sql = registration_schema.canonical_sql_text()
        match = re.search(
            r"(?<![A-Za-z0-9_])reason_code TEXT CHECK"
            r"\(reason_code IS NULL OR reason_code IN\(([^)]+)\)\)",
            sql,
        )
        self.assertIsNotNone(match)
        sql_reasons = {
            token.strip().strip("'")
            for token in match.group(1).split(",")
        }
        self.assertEqual(
            set(registration_admission.RUNTIME_REASONS), sql_reasons
        )
        for reason in registration_admission.RUNTIME_REASONS:
            with self.subTest(reason=reason):
                first = registration_admission.render_reason(reason)
                self.assertEqual(
                    first, registration_admission.render_reason(reason)
                )
                self.assertTrue(first)

    def test_ready_requires_complete_live_envelope(self) -> None:
        snapshot = _project()
        self.assertTrue(snapshot.ready)
        self.assertEqual(snapshot.reason, "READY")
        self.assertEqual(snapshot.member_id, M)

    def test_reason_priority_is_deterministic_and_bounded(self) -> None:
        authority = registration_admission.SelectedAuthorityView(
            **{
                **_authority().__dict__,
                "member_phase": "EFFECT_IN_FLIGHT",
                "effect_outcome": None,
            }
        )
        snapshot = _project(
            authority,
            registration_admission.HostEnvelope(
                **{**_host().__dict__, "host_tick_current": False}
            ),
        )
        self.assertFalse(snapshot.ready)
        self.assertEqual(snapshot.reason, "EFFECT_IN_FLIGHT")

    def test_rendering_is_stateless_byte_deterministic(self) -> None:
        snapshot = _project()
        first = registration_view.render_status(snapshot)
        second = registration_view.render_status(snapshot)
        self.assertEqual(first, second)
        self.assertNotIn("/fixture", first)
        encoded = registration_view.status_json(snapshot)
        self.assertEqual(encoded, registration_view.status_json(snapshot))
        self.assertEqual(json.loads(encoded)["reason"], "READY")

    def test_metrics_and_adr0020_component_are_redacted(self) -> None:
        snapshot = registration_view.RegistrationStatus(
            ready=False,
            reason="DIRTY_UNSUPPORTED",
            member_id=M,
            member_epoch=3,
            phase="REQUESTED",
            outcome=None,
            effect_id=E,
            status_version=4,
            protocol_generation=1,
            protocol_mode="WRITABLE",
        )
        metrics = registration_view.product_metrics(snapshot)
        component = registration_view.adr0020_component(snapshot)
        serialized = json.dumps(
            {"metrics": metrics, "component": component},
            sort_keys=True,
        )
        self.assertNotIn("/", serialized)
        self.assertNotIn("prompt", serialized)
        self.assertEqual(metrics["registration_ready"], 0)
        self.assertEqual(component["severity"], "degraded")
        self.assertEqual(component["reason_code"], "DIRTY_UNSUPPORTED")

    def test_unknown_internal_value_maps_store_unavailable(self) -> None:
        authority = registration_admission.SelectedAuthorityView(
            **{**_authority().__dict__, "member_phase": "UNKNOWN"}
        )
        snapshot = _project(authority)
        self.assertEqual(snapshot.reason, "STORE_UNAVAILABLE")
        self.assertFalse(snapshot.ready)

    def test_ready_requires_basis_episode_and_deployment_receipt(self) -> None:
        mismatched_basis = registration_admission.BasisSample(
            **{**_basis().__dict__, "current_basis_hash": "ff" * 32}
        )
        snapshot = registration_view.project_status(
            _authority(),
            _host(),
            event=registration_admission.parse_registration_event(_payload()),
            basis=mismatched_basis,
            receipt=_receipt(),
            expected_candidate_digest="22" * 32,
            episode_id=H,
            discriminator="shell",
            inventory=registration_admission.ToolInventory(
                ordinary=frozenset({"shell"}),
                task_launch=frozenset({"Task"}),
            ),
        )
        self.assertFalse(snapshot.ready)
        self.assertEqual(snapshot.reason, "REGISTRATION_REQUIRED")

        wrong_episode = registration_admission.SelectedAuthorityView(
            **{**_authority().__dict__, "episode_member_id": "ff" * 32}
        )
        snapshot = _project(wrong_episode)
        self.assertFalse(snapshot.ready)
        self.assertEqual(snapshot.reason, "REGISTRATION_REQUIRED")

        other_root_receipt = registration_admission.DeploymentReceipt(
            **{
                **_receipt("R1_CANARY").__dict__,
                "canonical_root_hash": "ff" * 32,
            }
        )
        snapshot = registration_view.project_status(
            _authority(),
            _host(),
            event=registration_admission.parse_registration_event(_payload()),
            basis=_basis(),
            receipt=other_root_receipt,
            expected_candidate_digest="22" * 32,
            episode_id=H,
            discriminator="shell",
            inventory=registration_admission.ToolInventory(
                ordinary=frozenset({"shell"}),
                task_launch=frozenset({"Task"}),
            ),
        )
        self.assertFalse(snapshot.ready)
        self.assertEqual(snapshot.reason, "ROOT_UNSUPPORTED")


if __name__ == "__main__":
    unittest.main()
