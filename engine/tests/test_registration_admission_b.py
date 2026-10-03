from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engine import registration_admission, registration_hashes


M = "bb" * 32
E = "cc" * 32
ROOT_HASH = "aa" * 32
WORKSPACE_HASH = "dd" * 32
H = registration_hashes.deterministic_id(
    "awa-reg-episode-v1",
    "conversation-1",
    "generation-1",
    "cursor-hook/v1",
    "beforeShellExecution",
    "1",
    M,
    WORKSPACE_HASH,
    "13" * 32,
    "14" * 32,
)


def _payload(root: str = "/fixture/root") -> dict:
    return {
        "hook_event_name": "beforeShellExecution",
        "workspace_roots": [root],
        "conversation_id": "conversation-1",
        "generation_id": "generation-1",
    }


def _basis(root: str = "/fixture/root") -> registration_admission.BasisSample:
    return registration_admission.BasisSample(
        canonical_root=root,
        canonical_root_hash=ROOT_HASH,
        member_id=M,
        current_basis_hash=E,
        physical_basis_hash="01" * 32,
        git_basis_hash="02" * 32,
        policy_basis_hash="03" * 32,
        operation_basis_hash="04" * 32,
        lifecycle_basis_hash="05" * 32,
        workspace_roots_hash=WORKSPACE_HASH,
    )


def _authority() -> registration_admission.SelectedAuthorityView:
    return registration_admission.SelectedAuthorityView(
        protocol_seq=2,
        protocol_hash="10" * 32,
        protocol_generation=1,
        protocol_mode="WRITABLE",
        protocol_schema_hash=registration_admission.SCHEMA_SHA256,
        profile_hash="11" * 32,
        runtime_capability_hash="12" * 32,
        tool_inventory_hash="13" * 32,
        hook_projection_hash="14" * 32,
        episode_id=H,
        episode_envelope_hash="15" * 32,
        episode_member_id=M,
        member_id=M,
        member_epoch=1,
        member_phase="RESOLVED",
        member_tuple_hash="16" * 32,
        member_write_sequence=7,
        member_basis_hash=E,
        pending_effect_id=None,
        status_version=4,
        status_hash="17" * 32,
        status_reason=None,
        status_executor_hash=None,
        status_help_due=0,
        effect_id="18" * 32,
        effect_outcome="SUCCESS",
        effect_outcome_sequence=6,
        effect_tuple_hash="19" * 32,
        ledger_head_hash="20" * 32,
        certificate_hash="21" * 32,
        action_count=4,
        revision_token=("token", 1),
    )


def _host() -> registration_admission.HostEnvelope:
    return registration_admission.HostEnvelope(
        host_tick_current=True,
        profile_hash="11" * 32,
        projection_hash="14" * 32,
        inventory_hash="13" * 32,
        storage_ready=True,
        parser_ready=True,
        serializer_ready=True,
    )


def _receipt(
    scope: str = "R2_DIRECT",
) -> registration_admission.DeploymentReceipt:
    return registration_admission.DeploymentReceipt(
        owner_mode="DIRECT",
        deployment_scope=scope,
        candidate_digest="22" * 32,
        canonical_root_hash=(
            ROOT_HASH if scope == "R1_CANARY" else None
        ),
        member_id=(M if scope == "R1_CANARY" else None),
        owner_gate_digest="23" * 32,
    )


class FakeCollector:
    def __init__(self, samples: list[object]) -> None:
        self.samples = list(samples)
        self.calls = 0

    def collect(self, _event: registration_admission.RegistrationEvent):
        self.calls += 1
        value = self.samples.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class FakeStore:
    def __init__(
        self,
        authorities: list[registration_admission.SelectedAuthorityView],
        revisions: list[tuple],
    ) -> None:
        self.authorities = list(authorities)
        self.revisions = list(revisions)
        self.reads = 0

    def read_view(self, _member_id: str, _episode_id: str):
        self.reads += 1
        return self.authorities.pop(0)

    def read_revision(self, _member_id: str, _episode_id: str):
        return self.revisions.pop(0)


class RegistrationEventParserTest(unittest.TestCase):
    def test_exact_one_root_and_payload_identity(self) -> None:
        event = registration_admission.parse_registration_event(_payload())
        self.assertEqual(event.workspace_roots, ("/fixture/root",))
        self.assertEqual(event.conversation_id, "conversation-1")
        self.assertEqual(event.generation_id, "generation-1")
        self.assertEqual(event.source_event, "beforeShellExecution")

    def test_missing_empty_multi_root_alias_and_bad_identity_refuse(self) -> None:
        cases = [
            {},
            {**_payload(), "workspace_roots": []},
            {**_payload(), "workspace_roots": ["/a", "/b"]},
            {**_payload(), "workspace_roots": ["/a"], "cwd": "/b"},
            {**_payload(), "conversation_id": "bad value"},
            {**_payload(), "generation_id": ""},
            {**_payload(), "unknown_envelope_key": "x"},
            {**_payload(), "session_id": "other-conversation"},
            {
                **_payload(),
                "tool_input": {"conversation_id": "other-conversation"},
            },
        ]
        for case in cases:
            with self.subTest(case=case):
                with self.assertRaises(registration_admission.EventRefused):
                    registration_admission.parse_registration_event(case)

    def test_byte_parser_rejects_duplicate_oversize_and_invalid_utf8(self) -> None:
        valid = json.dumps(_payload(), separators=(",", ":")).encode()
        self.assertEqual(
            registration_admission.parse_registration_event_bytes(valid).root,
            "/fixture/root",
        )
        duplicate = (
            b'{"hook_event_name":"beforeShellExecution",'
            b'"hook_event_name":"beforeReadFile",'
            b'"workspace_roots":["/fixture/root"],'
            b'"conversation_id":"conversation-1",'
            b'"generation_id":"generation-1"}'
        )
        for raw in (duplicate, b"\xff", b"x" * 65_537):
            with self.subTest(raw=raw[:30]):
                with self.assertRaises(registration_admission.EventRefused):
                    registration_admission.parse_registration_event_bytes(raw)

    def test_byte_parser_bounds_depth_and_nodes_before_json_decode(self) -> None:
        depth_16 = b"[" * 16 + b"null" + b"]" * 16
        with mock.patch.object(
            registration_admission.json,
            "loads",
            wraps=json.loads,
        ) as loads:
            with self.assertRaises(registration_admission.EventRefused):
                registration_admission.parse_registration_event_bytes(depth_16)
            self.assertEqual(loads.call_count, 1)

        for raw in (
            b"[" * 17 + b"null" + b"]" * 17,
            b"[" * 1_000 + b"null" + b"]" * 1_000,
            b"[" + b",".join([b"null"] * 513) + b"]",
        ):
            with self.subTest(length=len(raw)), mock.patch.object(
                registration_admission.json,
                "loads",
                wraps=json.loads,
            ) as loads:
                with self.assertRaises(registration_admission.EventRefused):
                    registration_admission.parse_registration_event_bytes(raw)
                self.assertEqual(loads.call_count, 0)

    def test_byte_parser_bounds_recursion_memory_and_truncation(self) -> None:
        valid = json.dumps(_payload(), separators=(",", ":")).encode()
        for failure in (RecursionError("deep"), MemoryError("wide")):
            with self.subTest(failure=type(failure).__name__), mock.patch.object(
                registration_admission.json,
                "loads",
                side_effect=failure,
            ):
                with self.assertRaises(
                    registration_admission.EventRefused
                ) as captured:
                    registration_admission.parse_registration_event_bytes(
                        valid
                    )
                self.assertEqual(captured.exception.reason, "PARSER_REJECT")
        with self.assertRaises(registration_admission.EventRefused):
            registration_admission.parse_registration_event_bytes(valid[:-1])

    def test_object_parser_bounds_predecoded_depth_and_nodes(self) -> None:
        deep = _payload()
        deep["tool_input"] = {}
        current = deep["tool_input"]
        for _ in range(registration_admission.MAX_EVENT_JSON_DEPTH):
            current["command"] = {}
            current = current["command"]
        wide = _payload()
        wide["tool_input"] = {
            "command": [None] * registration_admission.MAX_EVENT_JSON_NODES
        }
        for payload in (deep, wide):
            with self.subTest(kind=("deep" if payload is deep else "wide")):
                with self.assertRaises(
                    registration_admission.EventRefused
                ) as captured:
                    registration_admission.parse_registration_event(payload)
                self.assertEqual(captured.exception.reason, "PARSER_REJECT")

    def test_existing_symlink_alias_rejects_during_parse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "root"
            root.mkdir()
            alias = Path(tmp).resolve() / "alias"
            alias.symlink_to(root, target_is_directory=True)
            with self.assertRaises(registration_admission.EventRefused):
                registration_admission.parse_registration_event(
                    _payload(str(alias))
                )


class RegistrationAdmissionTest(unittest.TestCase):
    def test_deployment_receipt_scope_is_closed(self) -> None:
        with self.assertRaises(ValueError):
            registration_admission.DeploymentReceipt(
                "DIRECT",
                "R1_CANARY",
                "22" * 32,
                None,
                M,
                "23" * 32,
            )
        with self.assertRaises(ValueError):
            registration_admission.DeploymentReceipt(
                "EXTERNAL",
                "R2_DIRECT",
                "22" * 32,
                None,
                None,
                "23" * 32,
            )

    def _controller(
        self,
        collector: FakeCollector,
        store: FakeStore | None = None,
        receipt: registration_admission.DeploymentReceipt | None = None,
    ) -> registration_admission.AdmissionController:
        authority = _authority()
        store = store or FakeStore(
            [authority], [authority.revision_token]
        )
        return registration_admission.AdmissionController(
            inventory=registration_admission.ToolInventory(
                ordinary=frozenset({"shell", "read", "mcp"}),
                task_launch=frozenset({"Task", "subagent", "agent_launch"}),
            ),
            collector=collector,
            store=store,
            host_provider=_host,
            receipt_provider=lambda: receipt or _receipt(),
            expected_candidate_digest="22" * 32,
        )

    def test_task_launch_denies_before_basis_or_authority(self) -> None:
        collector = FakeCollector([_basis()])
        store = FakeStore([], [])
        decision = self._controller(collector, store).admit(
            _payload(), "Task", member_id=M, episode_id=H
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "TASK_SUBAGENT_DENIED")
        self.assertEqual(collector.calls, 0)
        self.assertEqual(store.reads, 0)

    def test_unknown_denies_only_after_valid_identity(self) -> None:
        collector = FakeCollector([_basis()])
        decision = self._controller(collector).admit(
            _payload(), "renamed-unknown", member_id=M, episode_id=H
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "UNKNOWN_DISCRIMINATOR")
        self.assertEqual(collector.calls, 0)

    def test_b1_r1_b2_r2_allows_exact_ready_member(self) -> None:
        collector = FakeCollector([_basis(), _basis()])
        decision = self._controller(collector).admit(
            _payload(), "shell", member_id=M, episode_id=H
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "READY")
        self.assertEqual(collector.calls, 2)

    def test_one_mismatch_retry_then_deny(self) -> None:
        changed = registration_admission.BasisSample(
            **{**_basis().__dict__, "current_basis_hash": "ff" * 32}
        )
        authority = _authority()
        collector = FakeCollector(
            [_basis(), changed, _basis(), changed]
        )
        store = FakeStore(
            [authority, authority],
            [authority.revision_token, authority.revision_token],
        )
        decision = self._controller(collector, store).admit(
            _payload(), "shell", member_id=M, episode_id=H
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "BASIS_UNSTABLE")
        self.assertEqual(collector.calls, 4)

    def test_selected_revision_change_retries_without_global_revision(self) -> None:
        authority = _authority()
        changed = (*authority.revision_token, "changed")
        collector = FakeCollector([_basis(), _basis(), _basis(), _basis()])
        store = FakeStore(
            [authority, authority],
            [changed, authority.revision_token],
        )
        decision = self._controller(collector, store).admit(
            _payload(), "shell", member_id=M, episode_id=H
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(collector.calls, 4)

    def test_r1_scope_denies_other_root_and_r2_broadens(self) -> None:
        other = registration_admission.DeploymentReceipt(
            **{**_receipt("R1_CANARY").__dict__, "canonical_root_hash": "ff" * 32}
        )
        denied = self._controller(
            FakeCollector([_basis(), _basis()]), receipt=other
        ).admit(_payload(), "shell", member_id=M, episode_id=H)
        self.assertFalse(denied.allowed)
        self.assertEqual(denied.reason, "ROOT_UNSUPPORTED")
        allowed = self._controller(
            FakeCollector([_basis(), _basis()]), receipt=_receipt("R2_DIRECT")
        ).admit(_payload(), "shell", member_id=M, episode_id=H)
        self.assertTrue(allowed.allowed)
        r0 = self._controller(
            FakeCollector([_basis(), _basis()]),
            receipt=_receipt("R0_THROWAWAY"),
        ).admit(_payload(), "shell", member_id=M, episode_id=H)
        self.assertFalse(r0.allowed)
        self.assertEqual(r0.reason, "PROTOCOL_INCOMPATIBLE")

    def test_full_envelope_component_failures_are_bounded_reasons(self) -> None:
        for field, reason in (
            ("host_tick_current", "HOST_STARVED"),
            ("storage_ready", "STORAGE_RED"),
            ("parser_ready", "PARSER_REJECT"),
            ("serializer_ready", "SERIALIZER_INVALID"),
        ):
            host = registration_admission.HostEnvelope(
                **{**_host().__dict__, field: False}
            )
            authority = _authority()
            controller = registration_admission.AdmissionController(
                inventory=registration_admission.ToolInventory(
                    ordinary=frozenset({"shell"}),
                    task_launch=frozenset({"Task"}),
                ),
                collector=FakeCollector([_basis(), _basis()]),
                store=FakeStore([authority], [authority.revision_token]),
                host_provider=lambda host=host: host,
                receipt_provider=_receipt,
                expected_candidate_digest="22" * 32,
            )
            with self.subTest(field=field):
                decision = controller.admit(
                    _payload(), "shell", member_id=M, episode_id=H
                )
                self.assertFalse(decision.allowed)
                self.assertEqual(decision.reason, reason)

    def test_member_status_reason_preserves_specific_operator_remediation(self) -> None:
        for phase, status_reason in (
            ("REQUESTED", "DIRTY_UNSUPPORTED"),
            ("REQUESTED", "GIT_OPERATION_UNSUPPORTED"),
            ("EFFECT_IN_FLIGHT", "RESOLVER_UNAVAILABLE"),
        ):
            authority = registration_admission.SelectedAuthorityView(
                **{
                    **_authority().__dict__,
                    "member_phase": phase,
                    "effect_outcome": None,
                    "status_reason": status_reason,
                }
            )
            controller = self._controller(
                FakeCollector([_basis(), _basis()]),
                FakeStore([authority], [authority.revision_token]),
            )
            with self.subTest(phase=phase, reason=status_reason):
                decision = controller.admit(
                    _payload(), "shell", member_id=M, episode_id=H
                )
                self.assertFalse(decision.allowed)
                self.assertEqual(decision.reason, status_reason)


if __name__ == "__main__":
    unittest.main()
