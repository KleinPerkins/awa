"""Body C startup/tick host packaging over Body B's scheduler."""

from __future__ import annotations

import inspect
import hashlib
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
