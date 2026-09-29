"""Body C startup/tick host packaging over Body B's scheduler."""

from __future__ import annotations

import inspect
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


class RegistrationHostTickTest(unittest.TestCase):
    def test_startup_json_rejects_duplicate_keys(self) -> None:
        with self.assertRaises(ValueError):
            registration_host._strict_json(
                b'{"hook_event_name":"sessionStart",'
                b'"hook_event_name":"preToolUse"}'
            )

    def test_runtime_byte_binding_rejects_installed_or_wrapper_drift(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            installed = root / "receiver"
            wrapper = root / "wrapper"
            runtime = root / "runtime.py"
            installed.write_bytes(b"receiver-v1")
            wrapper.write_bytes(b"wrapper-v1")
            runtime.write_bytes(b"runtime-v1")
            for path in (installed, wrapper, runtime):
                path.chmod(0o700)
            base = registration_projection.DirectReceipt.vector_r1()
            receipt = registration_projection.DirectReceipt.from_mapping(
                {
                    **base.to_mapping(),
                    "installed_file_hash": (
                        registration_projection.installed_file_hash(
                            installed
                        )
                    ),
                    "wrapper_runtime_hash": (
                        registration_projection.wrapper_runtime_hash(
                            wrapper, (runtime,)
                        )
                    ),
                }
            )
            config = {
                "installed_file_path": str(installed),
                "wrapper_path": str(wrapper),
                "runtime_files": [str(runtime)],
            }
            registration_host._verify_runtime_bytes(config, receipt)
            runtime.write_bytes(b"runtime-v2")
            with self.assertRaises(
                registration_host.registration_hook_runtime.HookUnavailable
            ):
                registration_host._verify_runtime_bytes(config, receipt)

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
        r1 = registration_projection.DirectReceipt.vector_r1()
        r0 = registration_projection.DirectReceipt.from_mapping(
            {
                **r1.to_mapping(),
                "deployment_scope": "R0_THROWAWAY",
                "canonical_root_hash": None,
                "member_id": None,
            }
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
            )
            value = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                set(value),
                {
                    "schema",
                    "boot_id",
                    "written_mono_ns",
                    "interval_ns",
                    "snapshot_token",
                    "selected_member_ids",
                    "selected_status_hashes",
                    "missed_member_ids",
                    "member_reasons",
                    "recovery_member_ids",
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
