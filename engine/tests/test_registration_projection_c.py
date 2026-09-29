"""Body C A22 inventory, projection, and DIRECT-receipt evidence."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from engine import registration_projection


H_A = "aa" * 32
H_B = "bb" * 32
H_C = "cc" * 32
H_D = "dd" * 32
H_E = "ee" * 32


def _candidate_fields() -> dict[str, str]:
    return {
        "schema_hash": H_A,
        "profile_hash": H_A,
        "runtime_capability_hash": H_A,
        "writer_binary_hash": H_A,
        "writer_capability_hash": H_A,
        "tool_inventory_hash": H_A,
        "hook_projection_hash": H_A,
        "hook_matcher_mode": "ENUMERATED",
        "hook_matcher_hash": H_A,
        "projection_file_generation": "1",
        "protocol_generation": "1",
    }


def _receipt(scope: str = "R1_CANARY", *, root: str | None = H_D):
    member = H_E if scope == "R1_CANARY" else None
    return registration_projection.DirectReceipt(
        schema="awa-registration-direct-receipt/v2",
        owner_mode="DIRECT",
        deployment_scope=scope,
        candidate_digest=registration_projection.candidate_digest(
            _candidate_fields()
        ),
        schema_hash=H_A,
        profile_hash=H_A,
        runtime_capability_hash=H_A,
        writer_binary_hash=H_A,
        writer_capability_hash=H_A,
        tool_inventory_hash=H_A,
        hook_projection_hash=H_A,
        hook_matcher_mode="ENUMERATED",
        hook_matcher_hash=H_A,
        installed_file_hash=H_B,
        projection_file_generation="1",
        protocol_generation="1",
        wrapper_runtime_hash=H_B,
        installer_identity_hash=H_A,
        installer_capability_hash=H_A,
        owner_gate_digest=H_C,
        canonical_root_hash=root,
        member_id=member,
    )


class DirectReceiptVectorTest(unittest.TestCase):
    def test_accepted_a22_candidate_and_receipt_vectors(self) -> None:
        self.assertEqual(
            registration_projection.candidate_digest(_candidate_fields()),
            "a1c2c85d94124228ee839295c92b27efd1811c583e9e2e0f2b7ff06c7791e9ae",
        )
        self.assertEqual(
            _receipt().digest,
            "4bc1ec7a34c527402da5ea85a55e868a5409bc1cb4a7634c6032f6ed65793d75",
        )
        self.assertEqual(
            _receipt(root="ff" * 32).digest,
            "abc336e3e104857960bda2540744b81ba1a343bf900cd4b27c1ddb0c42d7d6fb",
        )
        self.assertEqual(
            _receipt("R2_DIRECT", root=None).digest,
            "b6f93242d5f21629898d41aa101639753b26cc133be4d8932d48e3cc5a4e7431",
        )

    def test_receipt_schema_is_exact_and_round_trips_canonical_bytes(self) -> None:
        receipt = _receipt()
        raw = receipt.to_bytes()
        self.assertEqual(
            set(json.loads(raw)),
            set(registration_projection.DIRECT_RECEIPT_FIELDS),
        )
        self.assertEqual(
            registration_projection.DirectReceipt.from_bytes(raw),
            receipt,
        )
        contaminated = json.loads(raw)
        contaminated["opaque"] = "forbidden"
        with self.assertRaises(ValueError):
            registration_projection.DirectReceipt.from_mapping(contaminated)

    def test_scope_nullability_and_external_owner_reject(self) -> None:
        with self.assertRaises(ValueError):
            _receipt("R1_CANARY", root=None)
        with self.assertRaises(ValueError):
            registration_projection.DirectReceipt.from_mapping(
                {**_receipt().to_mapping(), "owner_mode": "EXTERNAL"}
            )
        with self.assertRaises(ValueError):
            registration_projection.DirectReceipt.from_mapping(
                {
                    **_receipt("R2_DIRECT", root=None).to_mapping(),
                    "member_id": H_E,
                }
            )

    def test_r0_converts_to_evidence_but_not_runtime_authority(self) -> None:
        receipt = _receipt("R0_THROWAWAY", root=None)
        deployment = receipt.deployment_receipt()
        self.assertEqual(deployment.deployment_scope, "R0_THROWAWAY")
        self.assertEqual(deployment.candidate_digest, receipt.candidate_digest)

    def test_owner_gate_requires_detached_signature_verification(self) -> None:
        gate = registration_projection.OwnerGate(
            schema="awa-registration-owner-gate/v1",
            repository="KleinPerkins/awa",
            authorized_by="KleinPerkins",
            deployment_scope="R1_CANARY",
            candidate_digest=_receipt().candidate_digest,
            canonical_root_hash=H_D,
            member_id=H_E,
            authorized=True,
        )
        raw = gate.to_bytes()
        calls = []

        def valid(payload: bytes, signature: bytes) -> bool:
            calls.append((payload, signature))
            return signature in {b"sig-a", b"sig-b"}

        first = registration_projection.verified_owner_gate_digest(
            raw, b"sig-a", verifier=valid
        )
        second = registration_projection.verified_owner_gate_digest(
            raw, b"sig-b", verifier=valid
        )
        self.assertEqual(first, second)
        self.assertEqual(calls[0][0], raw)
        bound = registration_projection.DirectReceipt.from_mapping(
            {**_receipt().to_mapping(), "owner_gate_digest": first}
        )
        registration_projection.verify_receipt_owner_gate(
            bound, raw, b"sig-a", verifier=valid
        )
        with self.assertRaises(ValueError):
            registration_projection.verify_receipt_owner_gate(
                _receipt(), raw, b"sig-a", verifier=valid
            )
        with self.assertRaises(ValueError):
            registration_projection.verified_owner_gate_digest(
                raw, b"invalid", verifier=valid
            )


class InventoryProjectionTest(unittest.TestCase):
    def _inventory(self):
        return (
            registration_projection.InventoryEntry(
                "preToolUse", "", "Delete", "ordinary", "cursor-permission/v1"
            ),
            registration_projection.InventoryEntry(
                "preToolUse", "", "MCP:awa_status", "ordinary", "cursor-permission/v1"
            ),
            registration_projection.InventoryEntry(
                "preToolUse", "", "Read", "ordinary", "cursor-permission/v1"
            ),
            registration_projection.InventoryEntry(
                "preToolUse", "", "Shell", "ordinary", "cursor-permission/v1"
            ),
            registration_projection.InventoryEntry(
                "preToolUse", "", "Task", "task_launch", "cursor-permission/v1"
            ),
            registration_projection.InventoryEntry(
                "subagentStart", "", "Task", "task_launch", "cursor-subagent/v1"
            ),
        )

    def test_inventory_hash_is_bytewise_order_independent(self) -> None:
        entries = self._inventory()
        self.assertEqual(
            registration_projection.tool_inventory_hash(entries),
            registration_projection.tool_inventory_hash(tuple(reversed(entries))),
        )
        with self.assertRaises(ValueError):
            registration_projection.tool_inventory_hash(entries + entries[:1])
        with self.assertRaises(ValueError):
            registration_projection.InventoryEntry(
                "preToolUse", "", "Read*", "ordinary", "cursor-permission/v1"
            )

    def test_projection_hash_binds_every_normalized_component(self) -> None:
        inventory_hash = registration_projection.tool_inventory_hash(
            self._inventory()
        )
        rows = (
            registration_projection.HookRow(
                "preToolUse",
                "*",
                ("/runtime/kernel/hooks/awa-registration-admission.sh",),
                20_000,
                False,
            ),
            registration_projection.HookRow(
                "subagentStart",
                "*",
                ("/runtime/kernel/hooks/awa-registration-admission.sh",),
                20_000,
                False,
            ),
        )
        first = registration_projection.hook_projection_hash(
            rows,
            matcher_mode="CATCH_ALL",
            matcher_hash=H_A,
            inventory_hash=inventory_hash,
            file_generation="1",
            protocol_generation="1",
            wrapper_runtime_hash=H_B,
        )
        second = registration_projection.hook_projection_hash(
            tuple(reversed(rows)),
            matcher_mode="CATCH_ALL",
            matcher_hash=H_A,
            inventory_hash=inventory_hash,
            file_generation="1",
            protocol_generation="1",
            wrapper_runtime_hash=H_B,
        )
        self.assertEqual(first, second)
        self.assertNotEqual(
            first,
            registration_projection.hook_projection_hash(
                rows,
                matcher_mode="CATCH_ALL",
                matcher_hash=H_A,
                inventory_hash=inventory_hash,
                file_generation="2",
                protocol_generation="1",
                wrapper_runtime_hash=H_B,
            ),
        )

    def test_catch_all_requires_contract_and_live_discriminator_receipts(self) -> None:
        proof = registration_projection.MatcherProof(
            mode="CATCH_ALL",
            official_contract_hash=H_A,
            observed_discriminators=frozenset(
                {"Shell", "Read", "Write", "Grep", "Delete", "MCP:awa_status", "Task"}
            ),
            task_launch_receivable=True,
        )
        inventory = self._inventory()
        registration_projection.validate_matcher_proof(proof, inventory)
        for mutation in (
            registration_projection.MatcherProof(
                "CATCH_ALL", None, proof.observed_discriminators, True
            ),
            registration_projection.MatcherProof(
                "CATCH_ALL", H_A, proof.observed_discriminators - {"Task"}, True
            ),
            registration_projection.MatcherProof(
                "CATCH_ALL", H_A, proof.observed_discriminators, False
            ),
        ):
            with self.subTest(mutation=mutation):
                with self.assertRaises(
                    registration_projection.HookUnsupported
                ):
                    registration_projection.validate_matcher_proof(
                        mutation, inventory
                    )

    def test_enumerated_mode_requires_exact_inventory(self) -> None:
        expected = frozenset(entry.discriminator for entry in self._inventory())
        proof = registration_projection.MatcherProof(
            "ENUMERATED", None, expected, True
        )
        registration_projection.validate_matcher_proof(proof, self._inventory())
        for observed in (expected - {"Task"}, expected | {"RenamedTool"}):
            with self.assertRaises(registration_projection.HookUnsupported):
                registration_projection.validate_matcher_proof(
                    registration_projection.MatcherProof(
                        "ENUMERATED", None, observed, True
                    ),
                    self._inventory(),
                )

    def test_candidate_evidence_binds_inventory_matcher_and_projection(
        self,
    ) -> None:
        inventory = self._inventory()
        proof = registration_projection.MatcherProof(
            "CATCH_ALL",
            H_A,
            frozenset(
                {
                    "Shell",
                    "Read",
                    "Write",
                    "Grep",
                    "Delete",
                    "MCP:awa_status",
                    "Task",
                    "RenamedTool",
                    "UnknownTool",
                }
            ),
            True,
        )
        inventory_hash = registration_projection.tool_inventory_hash(
            inventory
        )
        matcher_hash = registration_projection.matcher_proof_hash(proof)
        rows = (
            registration_projection.HookRow(
                "preToolUse",
                "*",
                ("/runtime/awa-registration-admission.sh",),
                20_000,
                False,
            ),
            registration_projection.HookRow(
                "subagentStart",
                "*",
                ("/runtime/awa-registration-admission.sh",),
                20_000,
                False,
            ),
            registration_projection.HookRow(
                "sessionStart",
                "",
                ("/runtime/awa-registration-startup.sh",),
                5_000,
                False,
            ),
        )
        projection_hash = (
            registration_projection.hook_projection_hash(
                rows,
                matcher_mode="CATCH_ALL",
                matcher_hash=matcher_hash,
                inventory_hash=inventory_hash,
                file_generation="1",
                protocol_generation="1",
                wrapper_runtime_hash=H_B,
            )
        )
        candidate = {
            **_candidate_fields(),
            "tool_inventory_hash": inventory_hash,
            "hook_projection_hash": projection_hash,
            "hook_matcher_mode": "CATCH_ALL",
            "hook_matcher_hash": matcher_hash,
        }
        receipt = registration_projection.DirectReceipt.from_mapping(
            {
                **_receipt().to_mapping(),
                **candidate,
                "candidate_digest": (
                    registration_projection.candidate_digest(candidate)
                ),
                "wrapper_runtime_hash": H_B,
            }
        )
        registration_projection.validate_candidate_evidence(
            receipt,
            inventory=inventory,
            matcher_proof=proof,
            rows=rows,
        )
        with self.assertRaises(registration_projection.HookUnsupported):
            registration_projection.validate_candidate_evidence(
                receipt,
                inventory=inventory,
                matcher_proof=registration_projection.MatcherProof(
                    "CATCH_ALL",
                    H_A,
                    proof.observed_discriminators - {"Task"},
                    False,
                ),
                rows=rows,
            )

    def test_installed_and_wrapper_runtime_hashes_bind_exact_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            wrapper = root / "wrapper.sh"
            runtime = root / "runtime.py"
            wrapper.write_bytes(b"#!/bin/sh\nexit 0\n")
            runtime.write_bytes(b"VALUE = 1\n")
            first_file = registration_projection.installed_file_hash(wrapper)
            first_runtime = registration_projection.wrapper_runtime_hash(
                wrapper, (runtime,)
            )
            runtime.write_bytes(b"VALUE = 2\n")
            self.assertEqual(
                registration_projection.installed_file_hash(wrapper),
                first_file,
            )
            self.assertNotEqual(
                registration_projection.wrapper_runtime_hash(
                    wrapper, (runtime,)
                ),
                first_runtime,
            )


if __name__ == "__main__":
    unittest.main()
