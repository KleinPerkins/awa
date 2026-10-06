"""Accepted-v5 Body C deployment-authority and continuity vectors."""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import tempfile
import unittest
from pathlib import Path

from engine import registration_installer, registration_projection


class DeploymentAuthorityVectorTest(unittest.TestCase):
    def test_interpreter_selection_path_and_ancestry_vectors(self) -> None:
        h = lambda value: value * 64
        selection = registration_projection.InterpreterSelection(
            schema="awa-registration-interpreter-selection/v1",
            scope="R0",
            repository="KleinPerkins/awa",
            authorized_by="KleinPerkins",
            source_revision="b" * 40,
            candidate_digest=(
                "44eaaa6cd88e4aee5c2e69890bad2e2db925cfae40fa2a79abdec8d29d282cfc"
            ),
            harness_root_hash=h("7"),
            installation_root_hash=None,
            interpreter_path="/fixture/python/bin/python3.14",
            authorization_nonce=h("6"),
            authorized=True,
        )
        self.assertEqual(
            selection.digest,
            "bb1b13000040b1cbbe3f2c8b047ecbf6d5866ac7de73fa53b12d75e68c9b3211",
        )
        self.assertEqual(
            registration_projection.interpreter_path_hash(
                selection.interpreter_path
            ),
            "a0caf9d8b6c5a2649358e0dc2d9ce4c9d75a3065496c6a50008bed580520ffdd",
        )
        components = ("/", "fixture", "python", "bin")
        records = []
        for ordinal, component in enumerate(components):
            records.append(
                {
                    "ordinal": str(ordinal),
                    "component_hash": __import__("hashlib").sha256(
                        b"awa-registration-path-component/v1\0"
                        + component.encode()
                    ).hexdigest(),
                    "st_dev": "1",
                    "st_ino": str(10 + ordinal),
                    "st_mode": "16877" if ordinal == 0 else "16832",
                    "st_uid": "0" if ordinal == 0 else "501",
                    "st_gid": "0" if ordinal == 0 else "20",
                    "st_nlink": "1",
                    "object_type": "DIRECTORY",
                }
            )
        self.assertEqual(
            registration_projection.interpreter_ancestry_hash(records),
            "975c44feaf12545fbd1f9c0a091e0701acc2f580ba02a31e31eb205dca53e825",
        )
        for field in selection.FIELDS:
            mutated = selection.to_mapping()
            mutated[field] = (
                registration_projection.mutated_authority_value(
                    field, mutated[field]
                )
            )
            with self.subTest(field=field):
                try:
                    changed = (
                        registration_projection.InterpreterSelection.from_mapping(
                            mutated
                        )
                    )
                except ValueError:
                    continue
                self.assertNotEqual(changed.digest, selection.digest)

    def test_receipt_v3_and_owner_gate_v2_fixed_vectors(self) -> None:
        expected = {
            "R0_THROWAWAY": (
                "eacdbd28b08d7f7674059fff7e8c29f491b76dbb42c43748758ae111e0fbef48",
                "d0a07bd84458a9fb9cbe200b7f17e882f1ffd670df83bfcc011dce8eede20277",
                "2534fc8d372ceda50cee15761898eebda847c152d8df8ba530cb9871ff906cd5",
            ),
            "R1_CANARY": (
                "dd0ef515d7fa7cc98cc241f2922e363460373d3799d9b938fd7887a55e021881",
                "f0b6cf0c2f79e224a629d0a8dc9aa3c41f6a282bc84750fbf35a4b9827c001f1",
                "19382cb1c7eba25aaabe4cfc75b55b10c4d0d87b6b17c65924fe21cc9845d518",
            ),
            "R2_DIRECT": (
                "500f13a4de86ef501f5e0e3e2efd7d62c19346b5e0d8435f6056649e7d36cea0",
                "1c86fc68c0eb6794f8e5671b7f448436ec886f1d63f329b94d9f5c28c921cc3d",
                "24f5363f6efdd6dc2620b4f3219b6db4f7a525b62c3ca1d404e6f663251fb8fa",
            ),
        }
        for scope, hashes in expected.items():
            with self.subTest(scope=scope):
                receipt, gate = registration_projection.fixed_authority_vector(
                    scope
                )
                self.assertEqual(receipt.schema, "awa-registration-direct-receipt/v3")
                self.assertEqual(gate.schema, "awa-registration-owner-gate/v2")
                self.assertEqual(receipt.direct_receipt_body_hash, hashes[0])
                self.assertEqual(gate.digest, hashes[1])
                self.assertEqual(receipt.owner_gate_digest, gate.digest)
                self.assertEqual(receipt.digest, hashes[2])
                self.assertEqual(
                    registration_projection.DirectReceipt.from_bytes(
                        receipt.to_bytes()
                    ),
                    receipt,
                )
                self.assertEqual(
                    registration_projection.OwnerGate.from_bytes(gate.to_bytes()),
                    gate,
                )

    def test_every_receipt_and_gate_field_is_authority(self) -> None:
        receipt, gate = registration_projection.fixed_authority_vector(
            "R1_CANARY"
        )
        receipt_mapping = receipt.to_mapping()
        gate_mapping = gate.to_mapping()
        for field in receipt_mapping:
            with self.subTest(receipt_field=field):
                mutated = dict(receipt_mapping)
                mutated[field] = registration_projection.mutated_authority_value(
                    field, mutated[field]
                )
                with self.assertRaises(ValueError):
                    registration_projection.validate_receipt_against_gate(
                        registration_projection.DirectReceipt.from_mapping(mutated),
                        gate,
                    )
        for field in gate_mapping:
            with self.subTest(gate_field=field):
                mutated = dict(gate_mapping)
                mutated[field] = registration_projection.mutated_authority_value(
                    field, mutated[field]
                )
                with self.assertRaises(ValueError):
                    registration_projection.validate_receipt_against_gate(
                        receipt,
                        registration_projection.OwnerGate.from_mapping(mutated),
                    )

    def test_observable_inventory_key_is_unique_before_role_policy(self) -> None:
        first = registration_projection.InventoryEntry(
            "preToolUse",
            "server-a",
            "MCP:tool",
            "ordinary",
            "cursor-permission/v1",
        )
        conflicting = registration_projection.InventoryEntry(
            "preToolUse",
            "server-a",
            "MCP:tool",
            "task_launch",
            "cursor-permission/v1",
        )
        with self.assertRaises(ValueError):
            registration_projection.tool_inventory_hash((first, conflicting))
        self.assertEqual(
            registration_projection.lookup_inventory_entry(
                (first,),
                event="preToolUse",
                server_or_empty="server-a",
                discriminator="MCP:tool",
                serializer_schema="cursor-permission/v1",
            ),
            first,
        )

    def test_current_enrollment_and_stock_openssh_negatives(self) -> None:
        contract = (
            Path(__file__).parents[2]
            / "contracts/awa-registration-owner-signers.v1"
        ).read_bytes()
        public_hash, fingerprint, contract_hash = (
            registration_projection._parse_allowed_signers(contract)
        )
        path_hash = __import__("hashlib").sha256(
            b"awa-registration-owner-signers-path/v1\0"
            b"contracts/awa-registration-owner-signers.v1"
        ).hexdigest()
        enrollment = {
            "schema": "awa-registration-owner-key-enrollment/v1",
            "principal": "KleinPerkins",
            "namespace": "awa-registration-owner-gate-v2",
            "key_algorithm": "ssh-ed25519",
            "public_key_sha256": public_hash,
            "openssh_fingerprint": fingerprint,
            "allowed_signers_relative_path": (
                "contracts/awa-registration-owner-signers.v1"
            ),
            "allowed_signers_path_hash": path_hash,
            "allowed_signers_contract_hash": contract_hash,
            "authorized": True,
        }
        enrollment_digest = registration_projection._domain_hash(
            "awa-registration-owner-key-enrollment/v1", enrollment
        )
        current_body = {
            "schema": "awa-registration-owner-key-current/v1",
            "sequence": "1",
            "status": "ACTIVE",
            "principal": "KleinPerkins",
            "namespace": "awa-registration-owner-gate-v2",
            "key_algorithm": "ssh-ed25519",
            "public_key_sha256": public_hash,
            "openssh_fingerprint": fingerprint,
            "allowed_signers_relative_path": (
                "contracts/awa-registration-owner-signers.v1"
            ),
            "allowed_signers_path_hash": path_hash,
            "allowed_signers_contract_hash": contract_hash,
            "key_enrollment_digest": enrollment_digest,
            "owner_authorization_digest": "a" * 64,
            "previous_enrollment_hash": None,
            "created_wall_ns": "100",
        }
        current = registration_projection.CurrentOwnerKey.from_mapping(
            {
                **current_body,
                "enrollment_hash": registration_projection._domain_hash(
                    "awa-registration-owner-key-current/v1",
                    current_body,
                ),
            }
        )
        receipt, _ = registration_projection.fixed_authority_vector(
            "R1_CANARY"
        )
        receipt = registration_projection.DirectReceipt.from_mapping(
            {
                **receipt.to_mapping(),
                "allowed_signers_contract_path_hash": path_hash,
                "allowed_signers_contract_hash": contract_hash,
                "signer_public_key_sha256": public_hash,
                "signer_fingerprint": fingerprint,
                "key_enrollment_digest": enrollment_digest,
            }
        )
        _receipt, gate = registration_projection.bind_owner_gate(receipt)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            bundle = root / "bundle"
            (bundle / "contracts").mkdir(parents=True, mode=0o700)
            os.chmod(bundle, 0o700)
            contract_path = (
                bundle
                / "contracts/awa-registration-owner-signers.v1"
            )
            contract_path.write_bytes(contract)
            os.chmod(contract_path, 0o644)
            current_path = root / "current.json"
            current_path.write_bytes(
                registration_projection.registration_jcs.canonical_bytes(
                    {
                        field: getattr(current, field)
                        for field in current.FIELDS
                    }
                )
                + b"\n"
            )
            os.chmod(current_path, 0o600)
            signature = root / "gate.sig"
            signature.write_bytes(b"not-an-openssh-signature\n")
            os.chmod(signature, 0o600)
            with self.assertRaisesRegex(
                ValueError, "detached owner signature"
            ):
                registration_projection.verify_owner_gate_signature(
                    gate.to_bytes(),
                    signature_path=signature,
                    bundle_root=bundle,
                    current_receipt_path=current_path,
                    expected_enrollment_hash=current.enrollment_hash,
                )
            with self.assertRaisesRegex(
                ValueError, "delivery authority"
            ):
                registration_projection.verify_owner_gate_signature(
                    gate.to_bytes(),
                    signature_path=signature,
                    bundle_root=bundle,
                    current_receipt_path=current_path,
                    expected_enrollment_hash="f" * 64,
                )
            revoked = registration_projection.CurrentOwnerKey.from_mapping(
                {
                    **{
                        field: getattr(current, field)
                        for field in current.FIELDS
                    },
                    "status": "REVOKED",
                    "enrollment_hash": registration_projection._domain_hash(
                        "awa-registration-owner-key-current/v1",
                        {**current_body, "status": "REVOKED"},
                    ),
                }
            )
            current_path.write_bytes(
                registration_projection.registration_jcs.canonical_bytes(
                    {
                        field: getattr(revoked, field)
                        for field in revoked.FIELDS
                    }
                )
                + b"\n"
            )
            with self.assertRaisesRegex(ValueError, "not ACTIVE"):
                registration_projection.verify_owner_gate_signature(
                    gate.to_bytes(),
                    signature_path=signature,
                    bundle_root=bundle,
                    current_receipt_path=current_path,
                    expected_enrollment_hash=revoked.enrollment_hash,
                )


class BundleAndImportAuthorityTest(unittest.TestCase):
    def test_closed_bundle_wrapper_proof_and_readiness_vectors(self) -> None:
        h = lambda value: value * 64
        manifest = registration_projection.ImportManifest(
            "awa-registration-import-manifest/v1",
            ("engine.registration_host",),
            (
                registration_projection.ImportRecord(
                    "engine/__init__.py",
                    "PACKAGE_INITIALIZER",
                    "420",
                    "1",
                    h("a"),
                ),
                registration_projection.ImportRecord(
                    "engine/registration_host.py",
                    "MODULE",
                    "420",
                    "2",
                    h("b"),
                ),
            ),
        )
        self.assertEqual(
            manifest.digest,
            "dddb3b7741e48de647da4d6950364e7330a56bb94617097a79b2b7207676e170",
        )
        self.assertEqual(
            __import__("hashlib").sha256(manifest.to_bytes()).hexdigest(),
            "671ff69bc00de5472889da47199821ae141e92bd37e7637ff616259cb4f3fa2c",
        )
        config = registration_projection.LauncherConfig(
            "awa-registration-launcher-config/v1",
            "2",
            "/fixture/python/bin/python3.14",
            "7b7032befe3cb79573811d97763cb8dddec67f0147a98fb99c9f912b2a3154b2",
            "ca675a27a71e6ff366a59c943ab17e47d02e8f560cd3c2cc00f213424747c9f6",
            manifest.digest,
            "engine.registration_host",
            ("-I", "-S", "-B"),
        )
        self.assertEqual(
            config.file_hash,
            "75b27f23c46c9ef25aea30667e32bc8daab02a046ea4a24846e8cfa651cd0e63",
        )
        records = (
            registration_projection.BundleEntry(
                "engine/__init__.py",
                "PACKAGE_INITIALIZER",
                "420",
                "1",
                h("a"),
            ),
            registration_projection.BundleEntry(
                "engine/registration_host.py",
                "RUNTIME",
                "420",
                "2",
                h("b"),
            ),
        )
        self.assertEqual(
            registration_projection.wrapper_runtime_v2_hash(
                bundle_digest="2ceab2235e3c1c107c26fcdaa213cf191450b395e51d8e1d08f34e52e0b9ca3d",
                launcher_hash=h("c"),
                import_manifest_hash=manifest.digest,
                external_interpreter_hash=(
                    "7b7032befe3cb79573811d97763cb8dddec67f0147a98fb99c9f912b2a3154b2"
                ),
                interpreter_capability_hash=(
                    "ca675a27a71e6ff366a59c943ab17e47d02e8f560cd3c2cc00f213424747c9f6"
                ),
                launcher_config_hash=config.file_hash,
                runtime_records=records,
            ),
            "9b2d07ca937ea451028f5b0d5a755383320f5b0f3c8224eea3c090a9fdad28e0",
        )
        proof_records = tuple(
            sorted(
                (
                    registration_projection.DenialProofRecord(
                        "preToolUse",
                        "",
                        "Shell",
                        "cursor-permission/v1",
                        "ordinary",
                        seam,
                        "2ceab2235e3c1c107c26fcdaa213cf191450b395e51d8e1d08f34e52e0b9ca3d",
                        h("7"),
                        h("8"),
                        "2",
                    )
                    for seam in (
                        "DIRECT_RECEIVER",
                        "SHADOW_INSTALLED",
                    )
                ),
                key=lambda record: registration_projection.registration_jcs.canonical_bytes(
                    record.to_mapping()
                ),
            )
        )
        proof = registration_projection.StagedDenialProof(
            "awa-registration-staged-denial-proof/v2",
            proof_records,
        )
        self.assertEqual(
            proof.digest,
            "c72a4fc31d3037732bf55305511f58dbf0b7f5f58377e98bd80a61461d53b4cd",
        )
        readiness = registration_projection.StagedReadiness(
            "awa-registration-staged-readiness/v2",
            "DENY_ONLY",
            h("1"),
            h("2"),
            "2ceab2235e3c1c107c26fcdaa213cf191450b395e51d8e1d08f34e52e0b9ca3d",
            h("3"),
            manifest.digest,
            "7b7032befe3cb79573811d97763cb8dddec67f0147a98fb99c9f912b2a3154b2",
            "ca675a27a71e6ff366a59c943ab17e47d02e8f560cd3c2cc00f213424747c9f6",
            h("a"),
            "1",
            proof.digest,
        )
        self.assertEqual(
            readiness.digest,
            "77db8c1f786d2f10bd21574f2d56b8b867c90ec6898eea7d2f6032b0b48ecd77",
        )

    def test_generated_manifest_includes_initializers_and_rejects_dynamic_import(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "engine").mkdir()
            (root / "engine/__init__.py").write_text("", encoding="utf-8")
            (root / "engine/registration_receiver.py").write_text(
                "from . import registration_host\n", encoding="utf-8"
            )
            (root / "engine/registration_host.py").write_text(
                "from . import registration_hook_runtime\n"
                "from . import registration_schema\n",
                encoding="utf-8",
            )
            (root / "engine/registration_hook_runtime.py").write_bytes(b"")
            (root / "engine/registration_schema.py").write_bytes(b"")
            (root / "engine/registration_schema.sql").write_bytes(
                b"SELECT 1;\n"
            )
            manifest = registration_installer.generate_import_manifest(root)
            logical_names = [
                record.logical_name for record in manifest.records
            ]
            self.assertIn("engine", logical_names)
            self.assertIn("engine.registration_receiver", logical_names)
            self.assertIn("engine.registration_host", logical_names)
            self.assertIn("engine.registration_hook_runtime", logical_names)
            self.assertIn(
                "engine.registration_schema:registration_schema.sql",
                logical_names,
            )
            payload = manifest.to_bytes()
            self.assertEqual(
                registration_projection.ImportManifestV2.from_bytes(payload),
                manifest,
            )
            (root / "engine/registration_receiver.py").write_text(
                "__import__('engine.registration_host')\n",
                encoding="utf-8",
            )
            with self.assertRaises(registration_installer.CutoverRefused):
                registration_installer.generate_import_manifest(root)

    def test_active_pointer_binds_immutable_generation_bundle(self) -> None:
        receipt, _gate = registration_projection.fixed_authority_vector(
            "R1_CANARY"
        )
        pointer = registration_projection.ActiveBundlePointer(
            schema="awa-registration-active-bundle/v1",
            generation=receipt.bundle_generation,
            bundle_relative_dir=(
                f"bundles/{receipt.bundle_generation}-{receipt.bundle_digest}"
            ),
            bundle_digest=receipt.bundle_digest,
            bundle_projection_hash=receipt.bundle_projection_hash,
            direct_receipt_hash=receipt.digest,
            external_interpreter_hash=receipt.external_interpreter_hash,
            interpreter_capability_hash=receipt.interpreter_capability_hash,
        )
        self.assertEqual(
            pointer.digest,
            "a7a5af2456ae4f0e4db786965ab54720174cd02da5e9176822899dc11aa336de",
        )
        self.assertEqual(
            json.loads(pointer.to_bytes()),
            pointer.to_mapping(),
        )


class TruthfulR0AuthorityVectorTest(unittest.TestCase):
    def test_r0_manifest_kill_observation_and_cut_vectors(self) -> None:
        h = lambda value: value * 64
        oid = lambda value: value * 40
        records = tuple(
            sorted(
                (
                    registration_projection.R0ManifestRecord(
                        h("1"),
                        "HOOKS",
                        "ABSENT",
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                    ),
                    registration_projection.R0ManifestRecord(
                        h("2"),
                        "RUNTIME",
                        "PRESENT",
                        "REGULAR",
                        "1",
                        "2",
                        "384",
                        "501",
                        "20",
                        "1",
                        "3",
                        h("a"),
                        None,
                    ),
                    registration_projection.R0ManifestRecord(
                        "d1ef657ecdb8c9aec6fdc404740b5c6e433c65e47a253582c44b1e624abab147",
                        "EXTERNAL_INTERPRETER",
                        "PRESENT",
                        "REGULAR",
                        "1",
                        "2",
                        "33261",
                        "501",
                        "20",
                        "1",
                        "3",
                        h("b"),
                        "7b7032befe3cb79573811d97763cb8dddec67f0147a98fb99c9f912b2a3154b2",
                    ),
                ),
                key=lambda record: record.path_hash,
            )
        )
        before = registration_projection.R0GovernedManifest(
            "awa-registration-r0-governed-manifest/v1",
            "BEFORE",
            "C2",
            "C2.STAGE_COMMITTED",
            oid("b"),
            records,
        )
        after = registration_projection.R0GovernedManifest(
            "awa-registration-r0-governed-manifest/v1",
            "AFTER",
            "C2",
            "C2.STAGE_COMMITTED",
            oid("b"),
            records,
        )
        self.assertEqual(
            before.digest,
            "22c58a83f0093c2a6108dc09d501f6c8a070cc12d2f48cd2b721d3eff360c1d3",
        )
        self.assertEqual(
            after.digest,
            "0b5f0d8a1928944332bc034c774f996521e39327db91fc3e7a4fae6949606028",
        )
        process = registration_projection.R0ProcessIdentity(
            "awa-registration-process-identity/v1",
            "123",
            h("1"),
            h("2"),
            h("3"),
            h("4"),
            h("5"),
        )
        killed = registration_projection.R0ProcessKill(
            "awa-registration-r0-process-kill/v1",
            "C2",
            "C2.STAGE_COMMITTED",
            "123",
            "SIGKILL",
            "-9",
            "10",
            "20",
            "30",
            process.digest,
        )
        self.assertEqual(
            killed.digest,
            "92df917c462ad025895acfb8f394ab35dc82068b2e617837b0b4ca23e67c6d7d",
        )


class V8ProductClosureAuthorityTest(unittest.TestCase):
    def _import_manifest(
        self,
    ) -> registration_projection.ImportManifestV2:
        payloads = {
            "engine/__init__.py": b"",
            "engine/registration_receiver.py": b"VALUE = 1\n",
            "engine/registration_host.py": b"VALUE = 2\n",
            "engine/registration_hook_runtime.py": b"VALUE = 3\n",
            "engine/registration_schema.py": b"VALUE = 2\n",
            "engine/registration_schema.sql": b"SELECT 1;\n",
        }
        records = (
            registration_projection.ImportRecordV2(
                "PACKAGE_INITIALIZER",
                "engine",
                "engine/__init__.py",
                None,
                "16",
                "444",
                str(len(payloads["engine/__init__.py"])),
                hashlib.sha256(payloads["engine/__init__.py"]).hexdigest(),
            ),
            registration_projection.ImportRecordV2(
                "MODULE",
                "engine.registration_hook_runtime",
                "engine/registration_hook_runtime.py",
                None,
                "17",
                "444",
                str(len(payloads["engine/registration_hook_runtime.py"])),
                hashlib.sha256(
                    payloads["engine/registration_hook_runtime.py"]
                ).hexdigest(),
            ),
            registration_projection.ImportRecordV2(
                "MODULE",
                "engine.registration_host",
                "engine/registration_host.py",
                None,
                "18",
                "444",
                str(len(payloads["engine/registration_host.py"])),
                hashlib.sha256(
                    payloads["engine/registration_host.py"]
                ).hexdigest(),
            ),
            registration_projection.ImportRecordV2(
                "MODULE",
                "engine.registration_receiver",
                "engine/registration_receiver.py",
                None,
                "19",
                "444",
                str(len(payloads["engine/registration_receiver.py"])),
                hashlib.sha256(
                    payloads["engine/registration_receiver.py"]
                ).hexdigest(),
            ),
            registration_projection.ImportRecordV2(
                "MODULE",
                "engine.registration_schema",
                "engine/registration_schema.py",
                None,
                "20",
                "444",
                str(len(payloads["engine/registration_schema.py"])),
                hashlib.sha256(
                    payloads["engine/registration_schema.py"]
                ).hexdigest(),
            ),
            registration_projection.ImportRecordV2(
                "RESOURCE",
                "engine.registration_schema:registration_schema.sql",
                "engine/registration_schema.sql",
                "engine.registration_schema",
                "21",
                "444",
                str(len(payloads["engine/registration_schema.sql"])),
                hashlib.sha256(
                    payloads["engine/registration_schema.sql"]
                ).hexdigest(),
            ),
        )
        return registration_projection.ImportManifestV2.create(records)

    def test_v12_receiver_rooted_generator_owns_complete_recursive_closure(
        self,
    ) -> None:
        self.assertEqual(
            tuple(inspect.signature(
                registration_installer.generate_import_manifest
            ).parameters),
            ("bundle_root",),
            "caller-selected entry modules remain production authority",
        )
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "engine").mkdir()
            (root / "engine/__init__.py").write_bytes(b"")
            (root / "engine/registration_receiver.py").write_text(
                "from . import registration_host\n",
                encoding="utf-8",
            )
            (root / "engine/registration_host.py").write_text(
                "from . import registration_hook_runtime\n"
                "from . import registration_schema\n",
                encoding="utf-8",
            )
            (root / "engine/registration_hook_runtime.py").write_bytes(b"")
            (root / "engine/registration_schema.py").write_bytes(b"")
            (root / "engine/registration_schema.sql").write_bytes(b"SELECT 1;\n")
            manifest = registration_installer.generate_import_manifest(root)
        self.assertIsInstance(
            manifest, registration_projection.ImportManifestV2
        )
        names = [record.logical_name for record in manifest.records]
        self.assertEqual(len(names), len(set(names)))
        for required in (
            "engine",
            "engine.registration_receiver",
            "engine.registration_host",
            "engine.registration_hook_runtime",
            "engine.registration_schema",
            "engine.registration_schema:registration_schema.sql",
        ):
            self.assertEqual(names.count(required), 1)

    def test_v12_import_v2_parser_refuses_omission_and_wrong_identity(
        self,
    ) -> None:
        manifest = self._import_manifest()
        self.assertTrue(
            hasattr(registration_projection.ImportManifestV2, "from_bytes"),
            "import-v2 has no canonical production parser",
        )
        self.assertEqual(
            registration_projection.ImportManifestV2.from_bytes(
                manifest.to_bytes()
            ),
            manifest,
        )
        for omitted in (
            "engine.registration_host",
            "engine.registration_hook_runtime",
        ):
            with self.subTest(omitted=omitted), self.assertRaises(ValueError):
                registration_projection.ImportManifestV2.create(
                    tuple(
                        record
                        for record in manifest.records
                        if record.logical_name != omitted
                    )
                )
        value = manifest.to_mapping()
        value["schema"] = "awa-registration-import-manifest/v1"
        with self.assertRaises(ValueError):
            registration_projection.ImportManifestV2.from_mapping(value)

    def test_v12_bundle_v3_is_canonical_and_rejects_wrong_version(self) -> None:
        imports = self._import_manifest()
        host = self._host()
        payloads = {
            record.relative_path: (
                b""
                if record.kind == "PACKAGE_INITIALIZER"
                else b"SELECT 1;\n"
                if record.kind == "RESOURCE"
                else (
                    b"VALUE = 1\n"
                    if record.logical_name == "engine.registration_receiver"
                    else b"VALUE = 2\n"
                    if record.logical_name in {
                        "engine.registration_host",
                        "engine.registration_schema",
                    }
                    else b"VALUE = 3\n"
                )
            )
            for record in imports.records
        }
        bundle = registration_projection.BundleManifestV3.create(
            generation="1",
            import_manifest=imports,
            host_authority=host,
            writer_capability_hash="9" * 64,
            installed_file_hash="a" * 64,
            payload_bytes=payloads,
        )
        try:
            parsed = registration_projection.BundleManifestV3.from_bytes(
                bundle.to_bytes()
            )
        except Exception as exc:
            self.fail(
                "bundle-v3 canonical production parser refused its own bytes: "
                f"{type(exc).__name__}: {exc}"
            )
        self.assertEqual(parsed, bundle)
        changed = bundle.to_mapping()
        changed["schema"] = "awa-registration-bundle-manifest/v2"
        with self.assertRaises(ValueError):
            registration_projection.BundleManifestV3.from_mapping(changed)

    def _host(self) -> registration_projection.HostAuthorityV2:
        targets = tuple(
            registration_projection.ProfileTargetV2(
                role,
                f"/fixture/{role}",
                kind,
                mode,
            )
            for role, kind, mode in (
                ("state_parent", "directory", "0700"),
                ("db", "file", "0600"),
                ("wal", "file", "0600"),
                ("shm", "file", "0600"),
                ("proof_parent", "directory", "0700"),
                ("projection_parent", "directory", "0700"),
                ("legacy_parent", "directory", "0700"),
                ("root", "directory", "0700"),
                ("git_dir", "directory", "0700"),
                ("git_common", "directory", "0700"),
            )
        )
        targets = (
            targets[0],
            registration_projection.ProfileTargetV2(
                "db", "/fixture/state_parent/registration.db", "file", "0600"
            ),
            registration_projection.ProfileTargetV2(
                "wal",
                "/fixture/state_parent/registration.db-wal",
                "file",
                "0600",
            ),
            registration_projection.ProfileTargetV2(
                "shm",
                "/fixture/state_parent/registration.db-shm",
                "file",
                "0600",
            ),
            *targets[4:],
        )
        inventory = (
            registration_projection.InventoryEntry(
                "preToolUse", "", "Shell", "ordinary", "cursor-permission/v1"
            ),
            registration_projection.InventoryEntry(
                "preToolUse",
                "",
                "Task",
                "task_launch",
                "cursor-permission/v1",
            ),
        )
        h = lambda value: value * 64
        return registration_projection.HostAuthorityV2.create(
            registration_db_path="/fixture/state_parent/registration.db",
            writer_capability_path="authority/writer-capability.json",
            profile_targets=targets,
            inventory=inventory,
            proof_parent="/fixture/proof_parent",
            projection_parent="/fixture/projection_parent",
            legacy_parent="/fixture/legacy_parent",
            host_tick_receipt_path="/fixture/tick-receipt",
            profile_hash=h("1"),
            runtime_capability_hash=h("2"),
            writer_binary_hash=h("3"),
            writer_capability_hash=h("4"),
            hook_projection_hash=h("5"),
            hook_matcher_hash=h("6"),
            projection_file_generation="1",
            protocol_generation="1",
            installer_identity_hash=h("7"),
            installer_capability_hash=h("8"),
            storage_dev="9",
        )

    def test_v8_import_bundle_host_and_product_pointer_are_acyclic(self) -> None:
        h = lambda value: value * 64
        imports = self._import_manifest()
        host = self._host()
        bundle = registration_projection.BundleManifestV2.create(
            generation="1",
            import_manifest=imports,
            host_authority=host,
            writer_capability_hash=h("9"),
            installed_file_hash=h("a"),
            payload_bytes={
                record.relative_path: (
                    b""
                    if record.logical_name == "engine"
                    else (
                        b"SELECT 1;\n"
                        if record.kind == "RESOURCE"
                        else (
                            b"VALUE = 1\n"
                            if record.logical_name
                            == "engine.registration_receiver"
                            else b"VALUE = 2\n"
                        )
                    )
                )
                for record in imports.records
            },
        )
        projection = registration_projection.BundleProjectionV2.create(
            generation="1",
            bundle_digest=bundle.bundle_digest,
            import_manifest_hash=imports.import_manifest_hash,
            host_authority_digest=host.host_authority_digest,
            candidate_digest=h("b"),
            installed_file_hash=bundle.installed_file_hash,
            wrapper_runtime_hash=h("c"),
            projection_file_generation="1",
            protocol_generation="1",
        )
        runtime = registration_projection.RuntimeCurrentV2.create(
            runtime_epoch="1",
            active_manifest_sha256=h("d"),
            previous_manifest_sha256=None,
            active_release_envelope_digest=h("e"),
            installed_at_wall_ns="1",
            capability_digest=h("f"),
            qualification_packet_digest=h("0"),
            predecessor_runtime_current_digest=None,
        )
        q1 = registration_projection.ProductCurrentV1.create(
            selection_epoch="1",
            bundle_generation="1",
            bundle_digest=bundle.bundle_digest,
            bundle_projection_hash=projection.bundle_projection_hash,
            direct_receipt_digest=h("1"),
            owner_gate_digest=h("2"),
            import_manifest_hash=imports.import_manifest_hash,
            host_authority_digest=host.host_authority_digest,
            runtime_current_digest=runtime.runtime_current_digest,
            predecessor_product_current_digest=None,
        )
        q2 = registration_projection.ProductCurrentV1.create(
            selection_epoch="2",
            bundle_generation="2",
            bundle_digest=h("3"),
            bundle_projection_hash=h("4"),
            direct_receipt_digest=h("5"),
            owner_gate_digest=h("6"),
            import_manifest_hash=h("7"),
            host_authority_digest=h("8"),
            runtime_current_digest=runtime.runtime_current_digest,
            predecessor_product_current_digest=q1.product_current_digest,
        )
        rollback = registration_projection.ProductCurrentV1.create(
            selection_epoch="3",
            bundle_generation=q1.bundle_generation,
            bundle_digest=q1.bundle_digest,
            bundle_projection_hash=q1.bundle_projection_hash,
            direct_receipt_digest=q1.direct_receipt_digest,
            owner_gate_digest=q1.owner_gate_digest,
            import_manifest_hash=q1.import_manifest_hash,
            host_authority_digest=q1.host_authority_digest,
            runtime_current_digest=q1.runtime_current_digest,
            predecessor_product_current_digest=q2.product_current_digest,
        )
        self.assertEqual(
            registration_projection.retained_product_versions(
                (q1, q2, rollback)
            ),
            frozenset(
                {
                    q1.bundle_relative_dir,
                    q2.bundle_relative_dir,
                }
            ),
        )
        self.assertEqual(rollback.bundle_generation, "1")
        self.assertNotIn(
            "direct_receipt_digest", bundle.to_mapping()
        )
        self.assertNotIn(
            "product_current_digest", runtime.to_mapping()
        )

    def test_v8_resource_profile_and_inventory_mutations_refuse(self) -> None:
        imports = self._import_manifest()
        bad = list(imports.records)
        bad[-1] = registration_projection.ImportRecordV2(
            "RESOURCE",
            "engine.registration_schema:../registration_schema.sql",
            "engine/registration_schema.sql",
            "engine.registration_schema",
            "19",
            "444",
            "10",
            "a" * 64,
        )
        with self.assertRaises(ValueError):
            registration_projection.ImportManifestV2.create(tuple(bad))
        host = self._host()
        with self.assertRaises(ValueError):
            registration_projection.HostAuthorityV2.from_mapping(
                {
                    **host.to_mapping(),
                    "profile_targets": list(reversed(
                        host.to_mapping()["profile_targets"]
                    )),
                }
            )


if __name__ == "__main__":
    unittest.main()
