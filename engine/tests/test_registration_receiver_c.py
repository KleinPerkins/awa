"""Body C stable routing through one exact immutable active bundle."""

from __future__ import annotations

import io
import inspect
import unittest
from types import SimpleNamespace
from unittest import mock

from engine import registration_projection, registration_receiver


class RegistrationReceiverRouterTest(unittest.TestCase):
    def test_v12_private_entry_accepts_only_retained_authority_bytes(self) -> None:
        parameters = inspect.signature(registration_receiver.private_runtime_main).parameters
        self.assertIn("retained_authority", parameters)
        source = inspect.getsource(registration_receiver.private_runtime_main)
        for forbidden in (
            "AWA_REGISTRATION_ACTIVE_BUNDLE",
            "AWA_REGISTRATION_PROJECTION",
            "XDG_DATA_HOME",
            "_active_pointer_path",
            "_projection_path",
            "_bundle_launcher",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(
                    forbidden,
                    source,
                    "receiver still reopens path/config authority",
                )

    def test_exact_bundle_routes_only_validated_receiver(self) -> None:
        self.assertTrue(hasattr(registration_receiver, "RetainedReceiverAuthority"))
        self.assertTrue(hasattr(registration_receiver, "retained_host_main"))
        authority = registration_receiver.RetainedReceiverAuthority.synthetic()
        for route in ("admission", "startup", "tick"):
            with self.subTest(route=route), mock.patch.object(
                registration_receiver,
                "retained_host_main",
                return_value=0,
            ) as retained:
                self.assertEqual(
                    registration_receiver.private_runtime_main(
                        [route], retained_authority=authority
                    ),
                    0,
                )
                retained.assert_called_once_with(
                    route=route,
                    authority=authority,
                )

    def test_tampered_bundle_fails_before_exec(self) -> None:
        self.assertTrue(hasattr(registration_receiver, "RetainedReceiverAuthority"))
        authority = registration_receiver.RetainedReceiverAuthority.synthetic()
        tampered = authority.replace(
            import_manifest_hash="f" * 64,
            validated=False,
        )
        with mock.patch.object(
            registration_receiver,
            "retained_host_main",
            side_effect=AssertionError("tampered authority reached host"),
            create=True,
        ):
            self.assertEqual(
                registration_receiver.private_runtime_main(
                    ["admission"], retained_authority=tampered
                ),
                1,
            )

    def test_staged_and_r0_interfaces_are_deterministic_deny_only(
        self,
    ) -> None:
        self.assertTrue(hasattr(registration_receiver, "RetainedReceiverAuthority"))
        authority = registration_receiver.RetainedReceiverAuthority.synthetic(
            deny_only=True
        )
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
                "retained_host_main",
                return_value=registration_receiver._deny_only("admission"),
                create=True,
            ), mock.patch.object(
                registration_receiver.sys, "stdin", stdin
            ), mock.patch.object(
                registration_receiver.sys, "stdout", stdout
            ):
                self.assertEqual(
                    registration_receiver.private_runtime_main(
                        ["admission"], retained_authority=authority
                    ),
                    2,
                )
            value = __import__("json").loads(output.getvalue())
            self.assertEqual(set(value), expected_keys)
            self.assertEqual(value["permission"], "deny")
        for route in ("startup", "tick"):
            with mock.patch.object(
                registration_receiver,
                "retained_host_main",
                return_value=2,
                create=True,
            ):
                self.assertEqual(
                    registration_receiver.private_runtime_main(
                        [route], retained_authority=authority
                    ),
                    2,
                )

    def test_current_receiver_execs_exact_closed_environment(self) -> None:
        self.assertTrue(hasattr(registration_receiver, "RetainedReceiverAuthority"))
        authority = registration_receiver.RetainedReceiverAuthority.synthetic()
        with mock.patch.object(
            registration_receiver,
            "retained_host_main",
            return_value=0,
            create=True,
        ) as retained:
            self.assertEqual(
                registration_receiver.private_runtime_main(
                    ["tick"], retained_authority=authority
                ),
                0,
            )
        retained.assert_called_once_with(route="tick", authority=authority)

    def test_protocol_classifies_only_exact_current_or_staged(self) -> None:
        receipt, _gate = registration_projection.fixed_authority_vector(
            "R1_CANARY"
        )
        fields = registration_receiver._PROTOCOL_RECEIPT_FIELDS
        current = {
            "mode": "WRITABLE",
            "protocol_generation": int(receipt.protocol_generation),
            "schema_hash": receipt.schema_hash,
            **{
                field: registration_receiver._receipt_protocol_value(
                    receipt, field
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
                    receipt
                ),
                "CURRENT",
            )
        staged = {
            "mode": "DRAINING",
            "protocol_generation": 1,
            "staged_generation": int(
                receipt.protocol_generation
            ),
            "staged_schema_hash": receipt.schema_hash,
            **{
                f"staged_{field}": (
                    registration_receiver._receipt_protocol_value(
                        receipt, field
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
                    receipt
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
                receipt
            )

    def test_unknown_route_is_refused_without_exec(self) -> None:
        parameters = inspect.signature(
            registration_receiver.private_runtime_main
        ).parameters
        authority = (
            {"retained_authority": object()}
            if "retained_authority" in parameters
            else {"authority_bytes": ()}
        )
        self.assertEqual(
            registration_receiver.private_runtime_main(
                ["repair"], **authority
            ),
            2,
        )


if __name__ == "__main__":
    unittest.main()
