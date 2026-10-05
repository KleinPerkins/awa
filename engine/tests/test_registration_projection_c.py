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
    receipt, _gate = registration_projection.fixed_authority_vector(
        "R1_CANARY"
    )
    return {
        field: receipt.to_mapping()[field]
        for field in registration_projection.CANDIDATE_FIELDS
    }


def _receipt(scope: str = "R1_CANARY", *, root: str | None = H_D):
    receipt, _gate = registration_projection.fixed_authority_vector(scope)
    if scope == "R1_CANARY":
        return registration_projection.DirectReceipt.from_mapping(
            {**receipt.to_mapping(), "canonical_root_hash": root}
        )
    return receipt


class DirectReceiptVectorTest(unittest.TestCase):
    def test_accepted_a22_candidate_and_receipt_vectors(self) -> None:
        self.assertEqual(
            registration_projection.candidate_digest(_candidate_fields()),
            "44eaaa6cd88e4aee5c2e69890bad2e2db925cfae40fa2a79abdec8d29d282cfc",
        )
        self.assertEqual(
            registration_projection.fixed_authority_vector(
                "R1_CANARY"
            )[0].digest,
            "19382cb1c7eba25aaabe4cfc75b55b10c4d0d87b6b17c65924fe21cc9845d518",
        )
        self.assertEqual(
            _receipt("R2_DIRECT", root=None).digest,
            "24f5363f6efdd6dc2620b4f3219b6db4f7a525b62c3ca1d404e6f663251fb8fa",
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
        receipt, gate = registration_projection.fixed_authority_vector(
            "R1_CANARY"
        )
        registration_projection.validate_receipt_against_gate(
            receipt, gate
        )
        with self.assertRaises(ValueError):
            registration_projection.validate_receipt_against_gate(
                registration_projection.DirectReceipt.from_mapping(
                    {
                        **receipt.to_mapping(),
                        "owner_gate_digest": H_A,
                    }
                ),
                gate,
            )
        with self.assertRaises(ValueError):
            registration_projection.verified_owner_gate_digest(
                gate.to_bytes(),
                b"historical-callback-signature",
                verifier=lambda *_: True,
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
                file_generation=_candidate_fields()[
                    "projection_file_generation"
                ],
                protocol_generation=_candidate_fields()[
                    "protocol_generation"
                ],
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


class ProtectedRuntimeSuccessorTest(unittest.TestCase):
    def _receipt_values(self) -> dict:
        values = {
            field: H_A
            for field in registration_projection.DIRECT_RECEIPT_V4_FIELDS
        }
        values.update(
            {
                "schema": "awa-registration-direct-receipt/v4",
                "owner_mode": "DIRECT",
                "deployment_scope": "R2_DIRECT",
                "hook_matcher_mode": "ENUMERATED",
                "projection_file_generation": "2",
                "protocol_generation": "3",
                "bundle_generation": "4",
                "canonical_root_hash": None,
                "member_id": None,
                "harness_root_hash": None,
                "source_lock_sha256":
                    registration_projection.V7_SOURCE_LOCK_SHA256,
                "bootstrap_contract_hash":
                    "4d9e89a327c4b50e287e5a61e96522a50d4f00346c3dbfa616c401c89fa79f0c",
                "private_runtime_contract_hash":
                    "f313e4d04f15fa5bcf7147b870a240402393d9a74cb16c23d5bdfd0b547a3321",
                "privileged_envelope_contract_hash":
                    "7fc2cdf48e041b501eb7230dd1e0ec9548540fba17f129dbe86a7ad07a117034",
                "admin_audit_contract_hash":
                    "a5718883a1b49c2030bdbe32eb88482f684cae635173449000be13c935345e8a",
                "allowed_signers_contract_path_hash":
                    registration_projection.V7_SIGNER_PATH_HASH,
                "allowed_signers_contract_hash":
                    registration_projection.V7_SIGNER_CONTRACT_HASH,
                "signer_public_key_sha256":
                    registration_projection.V7_SIGNER_PUBLIC_KEY_SHA256,
                "signer_fingerprint":
                    registration_projection.V7_SIGNER_FINGERPRINT,
            }
        )
        return values

    def test_v4_receipt_body_gate_and_final_digest_are_branched(self) -> None:
        preliminary = registration_projection.DirectReceiptV4(
            **self._receipt_values()
        )
        gate_values = {
            field: getattr(preliminary, field)
            for field in registration_projection.OWNER_GATE_V3_FIELDS
            if field in registration_projection.DIRECT_RECEIPT_V4_FIELDS
        }
        gate_values.update(
            {
                "schema": "awa-registration-owner-gate/v3",
                "repository": "KleinPerkins/awa",
                "authorized_by": "KleinPerkins",
                "direct_receipt_body_hash": preliminary.body_hash,
                "accepted_v6_normalized_digest":
                    registration_projection.V7_ACCEPTED_V6_DIGEST,
                "implementation_exact_head":
                    "03d0d3dd3e840925149d3ae1c5dd94e7791e8c3d",
                "authorized": True,
            }
        )
        gate = registration_projection.OwnerGateV3(**gate_values)
        final_values = self._receipt_values()
        final_values["owner_gate_digest"] = gate.digest
        receipt = registration_projection.DirectReceiptV4(**final_values)
        registration_projection.verify_direct_receipt_owner_gate_v3(
            receipt, gate
        )
        self.assertEqual(receipt.body_hash, preliminary.body_hash)
        self.assertNotEqual(receipt.digest, preliminary.digest)
        self.assertIn(gate.digest.encode(), receipt.to_bytes())

    def test_v2_signer_enrollment_chain_is_public_only(self) -> None:
        enrollment = registration_projection.OwnerKeyEnrollmentV2(
            schema="awa-registration-owner-key-enrollment/v2",
            principal="KleinPerkins",
            namespaces=list(registration_projection.V7_NAMESPACES),
            key_algorithm="ssh-ed25519",
            public_key_sha256=
                registration_projection.V7_SIGNER_PUBLIC_KEY_SHA256,
            openssh_fingerprint=
                registration_projection.V7_SIGNER_FINGERPRINT,
            allowed_signers_relative_path=
                "contracts/awa-registration-owner-signers.v2",
            allowed_signers_path_hash=
                registration_projection.V7_SIGNER_PATH_HASH,
            allowed_signers_contract_hash=
                registration_projection.V7_SIGNER_CONTRACT_HASH,
            authorized=True,
        )
        authorization = registration_projection.OwnerKeyAuthorizationV2(
            schema="awa-registration-owner-key-authorization/v2",
            repository="KleinPerkins/awa",
            authorized_by="KleinPerkins",
            action="ENROLL",
            principal="KleinPerkins",
            namespaces=list(registration_projection.V7_NAMESPACES),
            key_algorithm="ssh-ed25519",
            public_key_sha256=
                registration_projection.V7_SIGNER_PUBLIC_KEY_SHA256,
            openssh_fingerprint=
                registration_projection.V7_SIGNER_FINGERPRINT,
            allowed_signers_relative_path=
                "contracts/awa-registration-owner-signers.v2",
            allowed_signers_path_hash=
                registration_projection.V7_SIGNER_PATH_HASH,
            allowed_signers_contract_hash=
                registration_projection.V7_SIGNER_CONTRACT_HASH,
            key_enrollment_digest=enrollment.digest,
            acceptance_normalized_digest=H_B,
            authorization_nonce=H_C,
            authorized=True,
        )
        current_body = {
            "schema": "awa-registration-owner-key-current/v2",
            "sequence": "2",
            "status": "ACTIVE",
            "principal": "KleinPerkins",
            "namespaces": list(registration_projection.V7_NAMESPACES),
            "key_algorithm": "ssh-ed25519",
            "public_key_sha256":
                registration_projection.V7_SIGNER_PUBLIC_KEY_SHA256,
            "openssh_fingerprint":
                registration_projection.V7_SIGNER_FINGERPRINT,
            "allowed_signers_relative_path":
                "contracts/awa-registration-owner-signers.v2",
            "allowed_signers_path_hash":
                registration_projection.V7_SIGNER_PATH_HASH,
            "allowed_signers_contract_hash":
                registration_projection.V7_SIGNER_CONTRACT_HASH,
            "key_enrollment_digest": enrollment.digest,
            "owner_authorization_digest": authorization.digest,
            "previous_enrollment_hash":
                registration_projection.V7_PREVIOUS_ENROLLMENT_HASH,
            "created_wall_ns": "1",
        }
        enrollment_hash = registration_projection._domain_hash_lf(
            "awa-registration-owner-key-current/v2", current_body
        )
        current = registration_projection.OwnerKeyCurrentV2(
            **current_body,
            enrollment_hash=enrollment_hash,
        )
        self.assertEqual(current.digest, enrollment_hash)
        self.assertNotIn(b"PRIVATE KEY", current.to_bytes().upper())

    def test_observed_vector_cannot_feed_signed_expected_dag(self) -> None:
        dag = registration_projection.V7AuthorityDAG(
            bundle_entry_plain_hash=H_A,
            import_manifest_hash=H_B,
            installed_file_hash=H_C,
            bundle_digest=H_D,
            bootstrap_authority_hash="e" * 64,
            runtime_release_envelope_digest="f" * 64,
            expected_denial_vector_hash="1" * 64,
        )
        signed = dag.signed_expected_authority_hash
        self.assertFalse(dag.compare_observed("2" * 64))
        self.assertEqual(dag.signed_expected_authority_hash, signed)
        self.assertTrue(dag.compare_observed("1" * 64))


if __name__ == "__main__":
    unittest.main()
