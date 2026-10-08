"""Body C startup/tick host packaging over Body B's scheduler."""

from __future__ import annotations

import inspect
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from engine import (
    registration_admission,
    registration_host,
    registration_projection,
    registration_runtime,
)


def _receipt(*, suspended: bool = False) -> registration_runtime.TickReceipt:
    return registration_runtime.TickReceipt(
        snapshot_token="aa" * 32,
        selected_member_ids=("bb" * 32,),
        selected_status_hashes=(("bb" * 32, "cc" * 32),),
        missed_member_ids=(),
        member_reasons=(),
        recovery_member_ids=(),
        fairness_suspended=suspended,
    )


def _cursor(boot_id: str = "boot-a") -> registration_runtime.SameBootCursor:
    return registration_runtime.SameBootCursor(
        boot_id=boot_id,
        protocol_seq=1,
        protocol_hash="11" * 32,
        selection_snapshot_hash="22" * 32,
        last_member_id=None,
        last_pre_status_hash=None,
        last_post_status_hash=None,
        outcome=None,
        batch_count=0,
        wrapped=False,
    )


class RegistrationHostTickTest(unittest.TestCase):
    def test_v12_host_has_no_environment_selected_authority(self) -> None:
        source = inspect.getsource(registration_host.open_service)
        for forbidden in (
            "AWA_REGISTRATION_RUNTIME_CONFIG",
            "AWA_REGISTRATION_BUNDLE_ROOT",
            "_config_path",
            "_load_config",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(
                    forbidden,
                    source,
                    "host still reopens config/product path authority",
                )
        parameters = inspect.signature(
            registration_host.HostService.__init__
        ).parameters
        for required in (
            "host_authority",
            "direct_receipt",
            "owner_gate",
            "product_current",
            "bundle_projection",
            "import_manifest",
            "writer_capability",
            "resource_provider",
        ):
            with self.subTest(required=required):
                self.assertIn(required, parameters)

    def test_startup_json_rejects_duplicate_keys(self) -> None:
        with self.assertRaises(ValueError):
            registration_host._strict_json(
                b'{"hook_event_name":"sessionStart",'
                b'"hook_event_name":"preToolUse"}'
            )

    def test_retained_admission_uses_public_invocation_parser(self) -> None:
        payload = {
            "hook_event_name": "beforeMCPExecution",
            "workspace_roots": ["/fixture/root"],
            "conversation_id": "conversation-1",
            "generation_id": "generation-1",
            "mcp_server_name": "server-a",
            "tool_name": "lookup",
        }
        invocation = registration_host.registration_hook_runtime.ObservableInvocation(
            "beforeMCPExecution",
            "server-a",
            "MCP:lookup",
            "cursor-permission/v1",
        )

        class ControlledService:
            def __init__(self) -> None:
                self.calls = []

            def handle(self, observed_payload, observed_invocation):
                self.calls.append((observed_payload, observed_invocation))
                return registration_admission.AdmissionDecision(
                    True,
                    "READY",
                    registration_admission.render_reason("READY"),
                    1,
                )

        service = ControlledService()
        retained = {
            "host_authority": object(),
            "direct_receipt": object(),
            "owner_gate": object(),
            "product_current": object(),
            "bundle_projection": object(),
            "import_manifest": object(),
            "writer_capability": b"writer",
            "resource_provider": {},
        }
        sealed_authority = SimpleNamespace(**retained)
        manager = mock.MagicMock()
        manager.__enter__.return_value = service
        manager.__exit__.return_value = False
        output = io.BytesIO()
        with mock.patch.object(
            registration_host,
            "_read_stdin",
            return_value=json.dumps(payload, separators=(",", ":")).encode(),
        ), mock.patch.object(
            registration_host,
            "open_service",
            return_value=manager,
        ) as open_service, mock.patch.object(
            registration_host.sys,
            "stdout",
            SimpleNamespace(buffer=output),
        ):
            result = registration_host.retained_main(
                route="admission",
                authority=sealed_authority,
            )
        self.assertEqual(result, 0)
        self.assertEqual(service.calls, [(payload, invocation)])
        open_service.assert_called_once_with(**retained)
        self.assertEqual(json.loads(output.getvalue())["permission"], "allow")

        service.calls.clear()
        output = io.BytesIO()
        with mock.patch.object(
            registration_host,
            "_read_stdin",
            return_value=b"[]",
        ), mock.patch.object(
            registration_host,
            "open_service",
            return_value=manager,
        ), mock.patch.object(
            registration_host.sys,
            "stdout",
            SimpleNamespace(buffer=output),
        ):
            malformed = registration_host.retained_main(
                route="admission",
                authority=sealed_authority,
            )
        self.assertEqual(malformed, 1)
        self.assertEqual(service.calls, [])
        self.assertEqual(output.getvalue(), b"")

    def test_host_rejects_each_observable_field_mismatch(self) -> None:
        expected = registration_projection.InventoryEntry(
            "beforeMCPExecution",
            "server-a",
            "MCP:lookup",
            "ordinary",
            "cursor-permission/v1",
        )

        class RefusingCollector:
            def collect_observation(self, _event):
                raise AssertionError("mismatched invocation reached basis")

        service = object.__new__(registration_host.HostService)
        service.inventory_entries = (expected,)
        service.inventory_tokens = {
            (
                expected.event,
                expected.server_or_empty,
                expected.discriminator,
                expected.serializer_schema,
            ): "inventory-token"
        }
        service.admission = registration_admission.AdmissionController
        service.collector = RefusingCollector()
        payload = {
            "hook_event_name": "beforeMCPExecution",
            "workspace_roots": ["/fixture/root"],
            "conversation_id": "conversation-1",
            "generation_id": "generation-1",
        }
        mismatches = {
            "event": (
                "beforeMCP",
                "server-a",
                "MCP:lookup",
                "cursor-permission/v1",
            ),
            "server": (
                "beforeMCPExecution",
                "server-b",
                "MCP:lookup",
                "cursor-permission/v1",
            ),
            "discriminator": (
                "beforeMCPExecution",
                "server-a",
                "MCP:other",
                "cursor-permission/v1",
            ),
            "serializer": (
                "beforeMCPExecution",
                "server-a",
                "MCP:lookup",
                "cursor-subagent/v1",
            ),
        }
        for field, values in mismatches.items():
            with self.subTest(field=field):
                decision = service.handle(
                    payload,
                    registration_host.registration_hook_runtime.ObservableInvocation(
                        *values
                    ),
                )
                self.assertFalse(decision.allowed)
                self.assertEqual(decision.reason, "UNKNOWN_DISCRIMINATOR")

    def test_runtime_byte_binding_rejects_installed_or_wrapper_drift(
        self,
    ) -> None:
        self.assertTrue(
            hasattr(registration_host, "_verify_retained_runtime_bytes"),
            "host lacks retained-resource runtime verification",
        )
        host = b"VALUE = 1\n"
        wrapper = b"#!/bin/sh\nexit 2\n"
        sealed = SimpleNamespace(
            installed_file_hash=hashlib.sha256(
                b"awa-registration-installed-file/v1\0" + host
            ).hexdigest(),
            wrapper_runtime_hash=hashlib.sha256(
                b"awa-registration-wrapper-runtime/v2\0" + wrapper
            ).hexdigest(),
        )
        retained = {
            "engine/registration_host.py": host,
            "bin/awa-registration-entrypoint": wrapper,
        }
        registration_host._verify_retained_runtime_bytes(
            host_authority=sealed,
            retained_resources=retained,
        )
        for path in retained:
            with self.subTest(path=path):
                changed = dict(retained)
                changed[path] = b"drift"
                with self.assertRaises(
                    registration_host.registration_hook_runtime.HookUnavailable
                ):
                    registration_host._verify_retained_runtime_bytes(
                        host_authority=sealed,
                        retained_resources=changed,
                    )

    def test_host_envelope_uses_fresh_storage_and_serializer_checks(
        self,
    ) -> None:
        class Store:
            measured_profile_hash = "aa" * 32

            @staticmethod
            def current_protocol():
                return {"mode": "WRITABLE"}

            @staticmethod
            def storage_ready():
                return False

        service = object.__new__(registration_host.HostService)
        service.store = Store()
        service.receipt = registration_projection.DirectReceipt.vector_r1()
        service.host_tick_path = Path("/not/read")
        with mock.patch(
            "engine.registration_host._host_tick_current",
            return_value=True,
        ):
            envelope = service._host_envelope()
        self.assertFalse(envelope.storage_ready)
        self.assertTrue(envelope.parser_ready)
        self.assertTrue(envelope.serializer_ready)
        self.assertTrue(registration_host._serializer_ready())

    def test_startup_checks_deployment_scope_before_ensure(self) -> None:
        class Collector:
            def collect_observation(self, _event):
                return SimpleNamespace(basis_sample=object())

        class Admission:
            def preflight(self, _event, _discriminator, _basis):
                return "ROOT_UNSUPPORTED"

        class Coordinator:
            def ensure(self, *_args):
                raise AssertionError("startup persisted before scope gate")

        service = object.__new__(registration_host.HostService)
        service.collector = Collector()
        service.admission = Admission()
        service.coordinator = Coordinator()
        service.inventory = registration_admission.ToolInventory(
            ordinary=frozenset({"Shell"}),
            task_launch=frozenset({"Task"}),
        )
        reason = service.startup(
            {
                "hook_event_name": "sessionStart",
                "workspace_roots": ["/fixture/root"],
                "conversation_id": "conversation-1",
                "generation_id": "generation-1",
                "session_id": "conversation-1",
            }
        )
        self.assertEqual(reason, "ROOT_UNSUPPORTED")

    def test_r0_scope_never_runs_startup_or_tick_runtime(self) -> None:
        r0, _gate = registration_projection.fixed_authority_vector(
            "R0_THROWAWAY"
        )
        service = object.__new__(registration_host.HostService)
        service.receipt = r0
        with self.assertRaises(registration_host.registration_hook_runtime.HookUnavailable):
            registration_host._require_runtime_receipt(r0)
        with self.assertRaises(registration_host.registration_hook_runtime.HookUnavailable):
            service.tick()

    def test_tick_receipt_is_private_exact_and_fresh_only_when_healthy(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "state" / "host-tick.json"
            registration_host.write_host_tick_receipt(
                path,
                _receipt(),
                boot_id="boot-a",
                written_mono_ns=100,
                same_boot_cursor=_cursor(),
            )
            value = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                set(value),
                {
                    "schema",
                    "boot_id",
                    "written_mono_ns",
                    "interval_ns",
                    "protocol_seq",
                    "protocol_hash",
                    "same_boot_cursor",
                    "same_boot_cursor_hash",
                    "due_snapshot_hash",
                    "fairness_suspended",
                },
            )
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
            with mock.patch(
                "engine.registration_host.registration_clock.mach_continuous_time_ns",
                return_value=101,
            ), mock.patch(
                "engine.registration_host.identity.boot_id",
                return_value="boot-a",
            ):
                self.assertTrue(
                    registration_host._host_tick_current(path)
                )
            registration_host.write_host_tick_receipt(
                path,
                _receipt(suspended=True),
                boot_id="boot-a",
                written_mono_ns=100,
                same_boot_cursor=_cursor(),
            )
            with mock.patch(
                "engine.registration_host.registration_clock.mach_continuous_time_ns",
                return_value=101,
            ), mock.patch(
                "engine.registration_host.identity.boot_id",
                return_value="boot-a",
            ):
                self.assertFalse(
                    registration_host._host_tick_current(path)
                )

    def test_old_boot_and_stale_tick_receipts_are_not_current(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "state" / "host-tick.json"
            registration_host.write_host_tick_receipt(
                path,
                _receipt(),
                boot_id="boot-a",
                written_mono_ns=100,
                same_boot_cursor=_cursor(),
            )
            for boot, now in (
                ("boot-b", 101),
                ("boot-a", 99),
                (
                    "boot-a",
                    100 + 2 * registration_runtime.TICK_INTERVAL_NS + 1,
                ),
            ):
                with self.subTest(boot=boot, now=now), mock.patch(
                    "engine.registration_host.registration_clock.mach_continuous_time_ns",
                    return_value=now,
                ), mock.patch(
                    "engine.registration_host.identity.boot_id",
                    return_value=boot,
                ):
                    self.assertFalse(
                        registration_host._host_tick_current(path)
                    )

    def test_tick_uses_body_b_scheduler_and_process_attempt_callback(
        self,
    ) -> None:
        source = inspect.getsource(registration_host.HostService.tick)
        self.assertIn("registration_runtime.FairnessScheduler", source)
        self.assertIn("_tick_attempt", source)
        self.assertNotIn("sleep(", source)


if __name__ == "__main__":
    unittest.main()
