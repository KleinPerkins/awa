"""Body C stable routing through one exact immutable active bundle."""

from __future__ import annotations

import io
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from engine import registration_receiver
from engine.tests.test_registration_installer_c import _immutable_authority


class RegistrationReceiverRouterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(
            prefix="awa-registration-receiver."
        )
        self.root = Path(self.tmp.name).resolve()
        self.authority, self.receipt, _old = _immutable_authority(
            self.root
        )
        self.authority.install_candidate()
        self.authority.project_new_receiver()
        self.environment = {
            "AWA_REGISTRATION_ACTIVE_BUNDLE": str(
                self.authority.pointer_path
            ),
            "HOME": str(self.root),
            "PYTHONPATH": "/hostile/shadow",
            "PYTHONHOME": "/hostile/home",
            "PYTHONSTARTUP": "/hostile/startup.py",
            "PYTHONINSPECT": "1",
            "PATH": "/hostile/bin",
        }

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_exact_bundle_routes_only_validated_receiver(self) -> None:
        for route in ("admission", "startup", "tick"):
            with self.subTest(route=route), mock.patch.dict(
                os.environ, self.environment, clear=True
            ), mock.patch(
                "engine.registration_receiver._receiver_authority_state",
                return_value="CURRENT",
            ):
                executable, command, environment, deny_only = (
                    registration_receiver._bundle_launcher(route)
                )
                self.assertEqual(
                    executable,
                    self.authority.bundle_dir
                    / "bin/awa-registration-receiver",
                )
                self.assertEqual(command, (str(executable), route))
                self.assertFalse(deny_only)
                self.assertEqual(
                    environment["AWA_REGISTRATION_INTERPRETER"],
                    self.authority.launcher_config.interpreter_path,
                )
                for hostile in (
                    "PYTHONPATH",
                    "PYTHONHOME",
                    "PYTHONSTARTUP",
                    "PYTHONINSPECT",
                    "PATH",
                ):
                    self.assertNotIn(hostile, environment)

    def test_tampered_bundle_fails_before_exec(self) -> None:
        target = (
            self.authority.bundle_dir
            / "bin/awa-registration-receiver"
        )
        target.write_bytes(b"tampered")
        with mock.patch.dict(
            os.environ, self.environment, clear=True
        ), mock.patch(
            "engine.registration_receiver._receiver_authority_state",
            return_value="CURRENT",
        ), self.assertRaises(ValueError):
            registration_receiver._bundle_launcher("admission")

    def test_staged_and_r0_interfaces_are_deterministic_deny_only(
        self,
    ) -> None:
        for event, expected_keys in (
            (
                "preToolUse",
                {"permission", "user_message", "agent_message"},
            ),
            (
                "subagentStart",
                {"permission", "user_message"},
            ),
        ):
            stdin = SimpleNamespace(
                buffer=io.BytesIO(
                    (
                        '{"hook_event_name":"'
                        + event
                        + '"}'
                    ).encode()
                )
            )
            output = io.BytesIO()
            stdout = SimpleNamespace(buffer=output)
            with mock.patch.object(
                registration_receiver,
                "_bundle_launcher",
                return_value=(
                    Path("/not/exec"),
                    (),
                    {},
                    True,
                ),
            ), mock.patch.object(
                registration_receiver.sys, "stdin", stdin
            ), mock.patch.object(
                registration_receiver.sys, "stdout", stdout
            ):
                self.assertEqual(
                    registration_receiver.main(["admission"]), 2
                )
            value = __import__("json").loads(output.getvalue())
            self.assertEqual(set(value), expected_keys)
            self.assertEqual(value["permission"], "deny")
        for route in ("startup", "tick"):
            with mock.patch.object(
                registration_receiver,
                "_bundle_launcher",
                return_value=(
                    Path("/not/exec"),
                    (),
                    {},
                    True,
                ),
            ):
                self.assertEqual(registration_receiver.main([route]), 2)

    def test_current_receiver_execs_exact_closed_environment(self) -> None:
        executable = Path("/exact/receiver")
        environment = {"HOME": "/private", "XDG_STATE_HOME": "/state"}
        with mock.patch.object(
            registration_receiver,
            "_bundle_launcher",
            return_value=(
                executable,
                (str(executable), "tick"),
                environment,
                False,
            ),
        ), mock.patch.object(
            registration_receiver.os, "execve", side_effect=RuntimeError
        ) as execute:
            self.assertEqual(registration_receiver.main(["tick"]), 1)
        execute.assert_called_once_with(
            executable, [str(executable), "tick"], environment
        )

    def test_protocol_classifies_only_exact_current_or_staged(self) -> None:
        fields = registration_receiver._PROTOCOL_RECEIPT_FIELDS
        current = {
            "mode": "WRITABLE",
            "protocol_generation": int(self.receipt.protocol_generation),
            "schema_hash": self.receipt.schema_hash,
            **{
                field: registration_receiver._receipt_protocol_value(
                    self.receipt, field
                )
                for field in fields
            },
        }

        class Store:
            def __init__(self, protocol):
                self.protocol = protocol

            def current_protocol(self):
                return self.protocol

            def close(self):
                pass

        with mock.patch.object(
            registration_receiver.registration_store,
            "RegistrationStore",
            return_value=Store(current),
        ):
            self.assertEqual(
                registration_receiver._receiver_authority_state(
                    self.receipt
                ),
                "CURRENT",
            )
        staged = {
            "mode": "DRAINING",
            "protocol_generation": 1,
            "staged_generation": int(
                self.receipt.protocol_generation
            ),
            "staged_schema_hash": self.receipt.schema_hash,
            **{
                f"staged_{field}": (
                    registration_receiver._receipt_protocol_value(
                        self.receipt, field
                    )
                )
                for field in fields
            },
        }
        with mock.patch.object(
            registration_receiver.registration_store,
            "RegistrationStore",
            return_value=Store(staged),
        ):
            self.assertEqual(
                registration_receiver._receiver_authority_state(
                    self.receipt
                ),
                "DENY_ONLY",
            )
        staged["staged_hook_projection_hash"] = "f" * 64
        with mock.patch.object(
            registration_receiver.registration_store,
            "RegistrationStore",
            return_value=Store(staged),
        ), self.assertRaises(ValueError):
            registration_receiver._receiver_authority_state(
                self.receipt
            )

    def test_unknown_route_is_refused_without_exec(self) -> None:
        self.assertEqual(registration_receiver.main(["repair"]), 2)


if __name__ == "__main__":
    unittest.main()
