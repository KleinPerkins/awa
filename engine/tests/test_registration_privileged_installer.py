"""V7 privileged-request validation, renderers, and packet authority tests."""

from __future__ import annotations

import hashlib
import importlib.util
import base64
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engine import registration_privileged_installer as privileged


ROOT = Path(__file__).resolve().parents[2]
OWNER_SIGNERS_V1 = ROOT / "contracts/awa-registration-owner-signers.v1"
OWNER_SIGNERS_V2 = ROOT / "contracts/awa-registration-owner-signers.v2"
ADMIN = ROOT / "kernel/bin/awa-private-runtime-admin.py"
EXACT_HEAD = "03d0d3dd3e840925149d3ae1c5dd94e7791e8c3d"
SOURCE_LOCK_DIGEST = (
    "a8b1415067e7b33c18ccc3c1d42e19ae27a9ad5784a7f294fffc562083762d72"
)
V12_PRODUCT_AUTHORITY_ROLES = (
    "PRODUCT_CURRENT",
    "BUNDLE_MANIFEST",
    "BUNDLE_PROJECTION",
    "IMPORT_MANIFEST",
    "HOST_AUTHORITY",
    "DIRECT_RECEIPT",
    "OWNER_GATE",
    "WRITER_CAPABILITY",
)


def _load_admin():
    spec = importlib.util.spec_from_file_location(
        "awa_private_runtime_admin_test", ADMIN
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("admin module unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _request_mapping(operation: str = "QUALIFY") -> dict:
    return privileged.PrivilegedRequest.create(
        mode="QUALIFY",
        operation=operation,
        requested_uid="501",
        request_id="a" * 64,
        target_root="/Library/Application Support/"
        "AWA-qualification-" + "b" * 64,
        packet_root_digest="3" * 64,
        qualification_context_digest="4" * 64,
        qualification_allowed_signers_digest="5" * 64,
        pre_current_digest=None,
        target_release_envelope_digest=None,
        target_manifest_sha256=None,
        target_epoch=None,
        previous_manifest_sha256=None,
        current_manifest_sha256=None,
        new_manifest_sha256=None,
        q1_envelope_digest="6" * 64,
        q1_manifest_sha256="7" * 64,
        q2_envelope_digest="8" * 64,
        q2_manifest_sha256="9" * 64,
        created_wall_ns="1000",
        expires_wall_ns="901000",
    ).to_mapping()


def _final_packet_values() -> dict[str, object]:
    blob = {
        "path": "evidence/sha256/" + "1" * 64,
        "role": "AUTHORIZATION_RESULT",
        "domain": "synthetic/v1",
        "size": "1",
        "sha256": "1" * 64,
        "mode": "0444",
        "media_type": "application/octet-stream",
        "encoding": "BINARY",
        "packet_root_digest": "2" * 64,
    }
    test_record = {
        "command": ["synthetic"],
        "exit_code": "0",
        "passed": "1",
        "failed": "0",
        "skipped": "0",
        "stdout": dict(blob),
        "stderr": dict(blob),
        "started_wall_ns": "1",
        "completed_wall_ns": "2",
        "digest": "3" * 64,
    }
    build = lambda build_id: {
        "build_id": build_id,
        "clean_root_id": ("4" if build_id == "A" else "5") * 64,
        "toolchain": {
            "codesign_path": "/usr/bin/codesign",
            "codesign_project": "codesign",
            "codesign_sha256": "6" * 64,
            "clt_version": "1",
            "sdk_version": "1",
            "target_triple": "aarch64-apple-darwin",
        },
        "manifest": {
            "object": {
                "schema": "awa-private-runtime-manifest/v1",
                "source_lock_sha256": "1" * 64,
                "normalizer_source_sha256": "1" * 64,
                "signing_recipe_source_sha256": "1" * 64,
                "record_framing_digest": "1" * 64,
                "records": [
                    {
                        "path": "Python",
                        "mode": "0555",
                        "size": "1",
                        "sha256": "1" * 64,
                        "macho": True,
                    }
                ],
            },
            "digest": "7" * 64,
        },
        "signature_inventory": {
            "object": {
                "schema": "awa-private-runtime-signature-inventory/v1",
                "records": [
                    {
                        "path": "Python",
                        "identifier": "org.python",
                        "cdhash": "1" * 64,
                        "adhoc": True,
                        "strict_valid": True,
                    }
                ],
            },
            "digest": "8" * 64,
        },
        "transcript": dict(blob),
        "archive": dict(blob),
        "sbom": dict(blob),
        "license_inventory": dict(blob),
        "registration_tests": dict(test_record),
        "full_tests": dict(test_record),
    }
    fixture = lambda fixture_id: {
        "fixture_id": fixture_id,
        "epoch": "1" if fixture_id == "Q1" else "2",
        "marker_relative_path": "qualification/MARKER",
        "marker_bytes_base64": (
            "QVdBLVFVQUxJRklDQVRJT04tUTEK"
            if fixture_id == "Q1"
            else "QVdBLVFVQUxJRklDQVRJT04tUTIK"
        ),
        "marker_size": "21",
        "marker_sha256": (
            "c01efa502dabedbfe5d9d1a7cfff4f186e74d99ffa2e9f9c6c1a9fa8b529e541"
            if fixture_id == "Q1"
            else "6b80282df498fa05da5ff173e56e701c54cc093841041c10cc4a47e4fe657fc3"
        ),
        "build_a_manifest_sha256": "9" * 64,
        "build_b_manifest_sha256": "9" * 64,
        "manifest_sha256": "a" * 64,
        "release_envelope_digest": "b" * 64,
        "synthetic_signature_sha256": "c" * 64,
    }
    values: dict[str, object] = {
        "source_lock": {
            "object": {"schema": "awa-private-runtime-source-lock/v1"},
            "blob": dict(blob),
            "sha256": "d" * 64,
        },
        "github_attestation": {
            name: (
                True
                if name == "verified"
                else []
                if name in {"verification_command", "rejected_records"}
                else dict(blob)
                if name in {"bundle", "payload", "certificate"}
                else "1"
            )
            for name in (
                "repository", "artifact_name", "artifact_sha256", "release",
                "selection_rule", "matching_record_count", "predicate_type",
                "payload_type", "bundle_media_type", "oidc_issuer",
                "certificate_issuer", "subject_name", "subject_sha256",
                "subject_count", "build_type", "builder_id",
                "workflow_repository", "workflow_name", "workflow_path",
                "workflow_ref", "workflow_sha", "event_name",
                "run_invocation", "bundle", "payload", "certificate",
                "verification_command", "rejected_records", "verified",
                "digest",
            )
        },
        "normalizer_source": dict(blob),
        "signing_recipe_source": dict(blob),
        "capability": {
            "object": {
                "schema": "awa-registration-python-capability/v1",
                "platform": "darwin",
                "os_build": "synthetic",
                "python_implementation": "CPython",
                "python_version": "3.14.8",
                "required_python_apis": [
                    "fcntl.flock", "os.O_NOFOLLOW", "os.fstat",
                    "sqlite3.Connection.setconfig",
                    "sqlite3.SQLITE_DBCONFIG_DEFENSIVE",
                    "sqlite3.SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE",
                ],
                "sqlite_runtime_version": "3.53.1",
                "sqlite_source_id": "synthetic",
                "sqlite_compile_options_hash": "1" * 64,
                "sqlite_vfs_name": "unix",
                "journal_mode": "wal",
                "synchronous": "full",
                "fullfsync": True,
                "checkpoint_fullfsync": True,
                "foreign_keys": True,
                "connection_setconfig_available": True,
                "sqlite_dbconfig_defensive_available": True,
                "defensive": True,
                "trusted_schema": False,
                "locking_mode": "normal",
                "nofollow_available": True,
                "checkpoint_on_close": False,
                "probe_program_hash": "1" * 64,
            },
            "digest": "d" * 64,
        },
        "compile_options": {
            "object": {
                "schema": "awa-registration-sqlite-compile-options/v1",
                "options": ["ENABLE_FTS5", "THREADSAFE=1"],
            },
            "digest": "d" * 64,
        },
        "builds": [build("A"), build("B")],
        "byte_comparison": {
            "schema": "awa-private-runtime-byte-comparison/v1",
            "build_a_manifest_sha256": "1" * 64,
            "build_b_manifest_sha256": "1" * 64,
            "build_a_archive_sha256": "1" * 64,
            "build_b_archive_sha256": "1" * 64,
            "tree_comparison": dict(blob),
            "archive_comparison": dict(blob),
            "equal": True,
            "digest": "1" * 64,
        },
        "selected_build_id": "A",
        "final_archives": [dict(blob), dict(blob)],
        "sbom_license_inventory": {
            "schema": "awa-private-runtime-sbom-license-comparison/v1",
            "build_a_sbom_sha256": "1" * 64,
            "build_b_sbom_sha256": "1" * 64,
            "build_a_license_inventory_sha256": "1" * 64,
            "build_b_license_inventory_sha256": "1" * 64,
            "equal": True,
            "digest": "1" * 64,
        },
        "relocation_load_image_evidence": [
            {
                "relocation_id": relocation_id,
                "root_hash": "1" * 64,
                "command": ["synthetic"],
                "loaded_image_count": "0",
                "loaded_images": dict(blob),
                "dependency_escapes": dict(blob),
                "exit_code": "0",
                "digest": "1" * 64,
            }
            for relocation_id in ("A", "B")
        ],
        "registration_test_evidence": dict(test_record),
        "full_test_evidence": dict(test_record),
        "qualification_allowed_signers": {
            "object": {
                "schema": "awa-registration-qualification-allowed-signers/v1",
                "mode": "QUALIFY",
                "repository": "KleinPerkins/awa",
                "exact_head": EXACT_HEAD,
                "qualification_nonce": "1" * 64,
                "qualification_root": "/synthetic",
                "principal": "AWAQualification",
                "namespaces": [
                    "awa-private-runtime-qualification-release-v1"
                ],
                "key_algorithm": "ssh-ed25519",
                "public_key_openssh": "ssh-ed25519 synthetic",
                "public_key_wire_sha256": "1" * 64,
                "openssh_fingerprint": "SHA256:synthetic",
                "allowed_signers_line": "synthetic\n",
                "allowed_signers_sha256": "1" * 64,
                "contract_digest": "1" * 64,
            },
            "blob": dict(blob),
            "digest": "1" * 64,
        },
        "qualification_fixtures": {
            "schema": "awa-registration-qualification-fixtures/v1",
            "qualification_nonce": "1" * 64,
            "qualification_root": "/synthetic",
            "runtime_archive_sha256": "1" * 64,
            "q1": fixture("Q1"),
            "q2": fixture("Q2"),
            "digest": "1" * 64,
        },
        "privileged_qualification_context": {
            "object": {
                name: (
                    "awa-registration-privileged-qualification-context/v1"
                    if name == "schema"
                    else "KleinPerkins/awa"
                    if name == "repository"
                    else EXACT_HEAD
                    if name == "exact_head"
                    else "/synthetic"
                    if name == "qualification_root"
                    else "1" * 64
                )
                for name in (
                    "schema", "repository", "exact_head",
                    "source_lock_sha256", "c_runtime_scope_hash",
                    "packet_root_digest", "qualification_nonce",
                    "qualification_root",
                    "qualification_allowed_signers_digest",
                    "qualification_public_key_wire_sha256",
                    "qualification_public_key_fingerprint",
                    "q1_release_envelope_digest", "q1_manifest_sha256",
                    "q2_release_envelope_digest", "q2_manifest_sha256",
                    "build_a_manifest_sha256", "build_b_manifest_sha256",
                    "build_a_archive_sha256", "build_b_archive_sha256",
                    "byte_comparison_digest", "registration_test_digest",
                    "full_test_digest",
                )
            },
            "digest": "1" * 64,
        },
        "preprompt_rejection_evidence": {
            "schema": "awa-registration-preprompt-rejection-evidence/v1",
            "exact_head": EXACT_HEAD,
            "validator_source_sha256": "1" * 64,
            "cases": [],
            "syscall_denial_trace": dict(blob),
            "path_remapped_harness": dict(blob),
            "digest": "1" * 64,
        },
        "admin_qualification_evidence": {
            "schema": "awa-registration-privileged-qualification/v1",
            "exact_head": EXACT_HEAD,
            "packet_root_digest": "2" * 64,
            "qualification_context_digest": "1" * 64,
            "qualification_allowed_signers_digest": "1" * 64,
            "qualification_nonce": "1" * 64,
            "request_id": "1" * 64,
            "qualification_root": "/synthetic",
            "authorization_result": dict(blob),
            "operation_results": [],
            "audit_receipts": [],
            "cleanup_result": dict(blob),
            "no_residue": True,
            "digest": "1" * 64,
        },
        "parent_death_evidence": {
            "schema": "awa-registration-parent-death-evidence/v1",
            "exact_head": EXACT_HEAD,
            "platform_bootstrap_contract_sha256": "1" * 64,
            "cases": [],
            "syscall_trace": dict(blob),
            "operator_message_results": dict(blob),
            "digest": "1" * 64,
        },
        "executed_identities": [
            {
                "role": "SYNTHETIC",
                "path": "/synthetic",
                "dev": "1",
                "ino": "1",
                "pid": "1",
                "pidversion": "1" * 64,
                "mapped_vnode_dev": "1",
                "mapped_vnode_ino": "1",
                "cdhash": "1" * 64,
                "sha256": "1" * 64,
                "packet_root_digest": "2" * 64,
                "digest": "1" * 64,
            }
        ],
        "securityagent_result": {
            "schema": "awa-registration-securityagent-result/v1",
            "invocation_id": "1" * 64,
            "prompt_count": "1",
            "result": "ACCEPTED",
            "osascript_exit_code": "0",
            "error_number": "0",
            "stdout": dict(blob),
            "stderr": dict(blob),
            "started_wall_ns": "1",
            "completed_wall_ns": "2",
            "packet_root_digest": "2" * 64,
            "digest": "1" * 64,
        },
        "private_key_deletion": {
            "schema": "awa-registration-qualification-private-key-deletion/v1",
            "qualification_nonce": "1" * 64,
            "public_key_openssh": "ssh-ed25519 synthetic",
            "public_key_wire_sha256": "1" * 64,
            "deleted_wall_ns": "1",
            "private_material_absent": True,
            "open_fd_matches": "0",
            "packet_private_blob_matches": "0",
            "packet_root_digest": "2" * 64,
            "digest": "1" * 64,
        },
    }
    added_fields = {
        "product_authority_evidence": (
            "schema", "product_current", "bundle_manifest",
            "bundle_projection", "import_manifest", "host_authority",
            "direct_receipt", "owner_gate", "installed_layout",
            "retention_cases", "equality_results", "digest",
        ),
        "fd_topology_evidence": (
            "schema", "launch_context", "source_fd_map", "target_fd_map",
            "fault_cases", "ready_measurements", "go_measurements", "digest",
        ),
        "retained_import_evidence": (
            "schema", "manifest_digest", "first_import", "package_cases",
            "module_cases", "relative_import_cases", "resource_cases",
            "filesystem_open_trace", "bytecode_write_trace", "digest",
        ),
        "transaction_recovery_evidence": (
            "schema", "production_fixture", "qualification_fixture",
            "fault_cases", "recovery_cases", "immutable_phase_chains",
            "by_request_pointer_cases", "preprepared_null_transaction_cases",
            "asset_role_operation_cases", "nonce_mode_cases",
            "static_contract_set_cases", "asset_index_cases",
            "result_receipts", "head_current_receipt_equalities",
            "remove_evidence", "digest",
        ),
        "shell_startup_evidence": (
            "schema", "script_hashes", "sentinel_cases",
            "executed_startup_files", "inherited_environment",
            "product_prebootstrap_imports", "digest",
        ),
    }
    for field, fields in added_fields.items():
        values[field] = {
            name: (
                "awa-registration-" + field.replace("_", "-") + "/v1"
                if name == "schema"
                else "1" * 64
                if name == "digest"
                else []
            )
            for name in fields
        }
    for field in (
        "product_current", "bundle_manifest", "bundle_projection",
        "import_manifest", "host_authority", "direct_receipt", "owner_gate",
        "installed_layout",
    ):
        values["product_authority_evidence"][field] = dict(blob)
    values["retained_import_evidence"]["manifest_digest"] = "1" * 64
    values["retained_import_evidence"]["first_import"] = dict(blob)
    for field in ("filesystem_open_trace", "bytecode_write_trace"):
        values["retained_import_evidence"][field] = dict(blob)
    for field in ("launch_context", "source_fd_map", "target_fd_map"):
        values["fd_topology_evidence"][field] = dict(blob)
    for field in ("production_fixture", "qualification_fixture"):
        values["transaction_recovery_evidence"][field] = {"verified": True}
    values["transaction_recovery_evidence"]["remove_evidence"] = dict(blob)
    values["shell_startup_evidence"]["script_hashes"] = [
        {"path": "script", "sha256": "1" * 64}
    ]
    values["github_attestation"]["digest"] = "1" * 64
    return values


def _valid_readback(packet: dict) -> dict[str, object]:
    body: dict[str, object] = {
        "schema": privileged.QUALIFICATION_READBACK_SCHEMA,
        "repository": "KleinPerkins/awa",
        "exact_head": EXACT_HEAD,
        "packet_root_digest": packet["packet_root_digest"],
        "bound_input_index_digest": packet["bound_index_digest"],
        "evidence_root_digest": packet["evidence_index_digest"],
        "qualification_packet_digest": packet["qualification_packet_digest"],
        "packet_file_count": "4",
        "input_blob_count": "1",
        "evidence_blob_count": "1",
        "static_contract_set_equal": True,
        "verified": True,
    }
    return {
        **body,
        "verifier_digest": privileged.authority_digest(
            privileged.QUALIFICATION_READBACK_SCHEMA, body
        ),
    }


def _complete_packet_builder(
    extra_root_blobs: dict[str, bytes] | None = None,
    *,
    include_evidence: bool = True,
) -> privileged.QualificationPacketBuilder:
    builder = privileged.QualificationPacketBuilder(
        exact_head=EXACT_HEAD,
        accepted_digest="8" * 64,
        c_runtime_scope_hash="7" * 64,
    )
    for path, digest in privileged.V8_STATIC_CONTRACT_HASHES.items():
        content = (ROOT / path).read_bytes()
        if hashlib.sha256(content).hexdigest() != digest:
            raise AssertionError(f"static contract drift: {path}")
        try:
            privileged._parse_canonical_value(content)
        except (UnicodeError, ValueError, json.JSONDecodeError):
            encoding = "UTF8_LF"
        else:
            encoding = "JCS_LF"
        builder.add_packet_root_blob(
            role="STATIC_CONTRACT",
            domain=path,
            content=content,
            media_type=(
                "application/json"
                if path.endswith(".json")
                else "text/plain"
            ),
            encoding=encoding,
        )
    for role in (
        "QUALIFICATION_ALLOWED_SIGNERS",
        "Q1_MANIFEST",
        "Q1_ENVELOPE",
        "Q1_SIGNATURE",
        "Q2_MANIFEST",
        "Q2_ENVELOPE",
        "Q2_SIGNATURE",
    ):
        encoding = "BINARY" if role.endswith("SIGNATURE") else "JCS_LF"
        content = (
            f"synthetic-{role}\n".encode("ascii")
            if encoding == "BINARY"
            else privileged.canonical_lf_bytes(
                {"schema": f"synthetic-{role.lower()}/v1"}
            )
        )
        builder.add_packet_root_blob(
            role=role,
            domain=f"synthetic:{role}",
            content=content,
            media_type=(
                "application/octet-stream"
                if encoding == "BINARY"
                else "application/json"
            ),
            encoding=encoding,
        )
    if set(V12_PRODUCT_AUTHORITY_ROLES) <= privileged.PACKET_ROOT_ROLES:
        for role in V12_PRODUCT_AUTHORITY_ROLES:
            builder.add_packet_root_blob(
                role=role,
                domain=f"synthetic:{role}",
                content=privileged.canonical_lf_bytes(
                    {
                        "schema": (
                            f"synthetic-{role.lower().replace('_', '-')}/v1"
                        )
                    }
                ),
                media_type="application/json",
                encoding="JCS_LF",
            )
    for role, content in (extra_root_blobs or {}).items():
        builder.add_packet_root_blob(
            role=role,
            domain=f"synthetic:{role}",
            content=content,
        )
    builder.finalize_packet_root()
    builder.add_bound_blob(
        role="PRIVILEGED_REQUEST",
        domain="awa-registration-privileged-request/v1",
        content=privileged.canonical_lf_bytes(_request_mapping()),
        media_type="application/json",
        encoding="JCS_LF",
    )
    builder.add_bound_blob(
        role="PRIVILEGED_CONTEXT",
        domain="awa-registration-privileged-context/v1",
        content=privileged.canonical_lf_bytes(
            {"schema": "awa-registration-privileged-context/v1"}
        ),
        media_type="application/json",
        encoding="JCS_LF",
    )
    if include_evidence:
        builder.add_evidence_blob(
            role="AUTHORIZATION_RESULT",
            domain="synthetic-authorization-result/v1",
            content=privileged.canonical_lf_bytes(
                {"schema": "synthetic-authorization-result/v1"}
            ),
            media_type="application/json",
            encoding="JCS_LF",
        )
    return builder


class OwnerSignerContractTest(unittest.TestCase):
    def test_owner_v1_is_delivered_byte_identically(self) -> None:
        raw = OWNER_SIGNERS_V1.read_bytes()
        self.assertEqual(
            hashlib.sha256(raw).hexdigest(),
            "9155be780c73e65a549ae97326dc56c53045aeaddb697745a95ce191aa472b7e",
        )
        self.assertEqual(len(raw), 138)
        privileged.validate_owner_signers_v1(raw)

    def test_qualification_signer_v2_is_public_only_and_exactly_scoped(self) -> None:
        raw = OWNER_SIGNERS_V2.read_bytes()
        value = privileged.validate_owner_signers_v2(raw)
        self.assertEqual(value["principal"], "KleinPerkins")
        self.assertEqual(
            value["namespaces"],
            (
                "awa-private-runtime-release-envelope-v1",
                "awa-registration-owner-gate-v3",
            ),
        )
        self.assertEqual(value["algorithm"], "ssh-ed25519")
        self.assertEqual(
            value["public_key_sha256"],
            "ccc9283906c612aed388f23bf5ef26f16a0a780926a447dbe8c7e71a94b4df63",
        )
        self.assertNotIn(b"BEGIN OPENSSH PRIVATE KEY", raw)


class PureValidationTest(unittest.TestCase):
    def test_request_parser_requires_exact_fields_and_jcs_lf(self) -> None:
        mapping = _request_mapping()
        raw = privileged.canonical_lf_bytes(mapping)
        request = privileged.PrivilegedRequest.from_bytes(raw)
        self.assertEqual(request.operation, "QUALIFY")
        self.assertEqual(request.to_bytes(), raw)
        for key in tuple(mapping):
            with self.subTest(missing=key):
                broken = dict(mapping)
                del broken[key]
                with self.assertRaises(ValueError):
                    privileged.PrivilegedRequest.from_mapping(broken)
        with self.assertRaises(ValueError):
            privileged.PrivilegedRequest.from_bytes(raw[:-1] + b" \n")

    def test_pure_validator_performs_no_syscalls(self) -> None:
        request = privileged.PrivilegedRequest.from_mapping(_request_mapping())
        context = privileged.ValidationContext.synthetic(
            operation="QUALIFY",
            request_digest=request.digest,
            now_wall_ns="1001",
            signature_valid=True,
            path_metadata_valid=True,
            packet_root_digest="3" * 64,
            qualification_context_digest="4" * 64,
            qualification_allowed_signers_digest="5" * 64,
        )
        denied = AssertionError("validator made a syscall")
        with (
            mock.patch.object(os, "stat", side_effect=denied),
            mock.patch.object(os, "lstat", side_effect=denied),
            mock.patch.object(os, "open", side_effect=denied),
            mock.patch.object(os, "read", side_effect=denied),
            mock.patch.object(os, "readlink", side_effect=denied),
            mock.patch.object(os, "listdir", side_effect=denied),
        ):
            result = privileged.validate_privileged_request(request, context)
        self.assertTrue(result.allowed)
        self.assertEqual(result.reason_code, "VALIDATED")

    def test_expected_vs_observed_denials_are_disjoint(self) -> None:
        request = privileged.PrivilegedRequest.from_mapping(_request_mapping())
        expected = privileged.ValidationContext.synthetic(
            operation="QUALIFY",
            request_digest="f" * 64,
            now_wall_ns="1001",
            signature_valid=True,
            path_metadata_valid=True,
            packet_root_digest="3" * 64,
            qualification_context_digest="4" * 64,
            qualification_allowed_signers_digest="5" * 64,
        )
        observed = privileged.ValidationContext.synthetic(
            operation="QUALIFY",
            request_digest=request.digest,
            now_wall_ns="1001",
            signature_valid=True,
            path_metadata_valid=False,
            packet_root_digest="3" * 64,
            qualification_context_digest="4" * 64,
            qualification_allowed_signers_digest="5" * 64,
        )
        expected_result = privileged.validate_privileged_request(request, expected)
        observed_result = privileged.validate_privileged_request(request, observed)
        self.assertEqual(expected_result.denial_class, "EXPECTED_MISMATCH")
        self.assertEqual(expected_result.reason_code, "REQUEST_DIGEST_MISMATCH")
        self.assertEqual(observed_result.denial_class, "OBSERVED_DRIFT")
        self.assertEqual(observed_result.reason_code, "PATH_METADATA_DRIFT")


class PathlessRendererTest(unittest.TestCase):
    def test_initial_authorization_renderer_has_no_operator_supplied_path(self) -> None:
        source = privileged.render_initial_authorization_script()
        self.assertTrue(source.startswith("on run argv\n"))
        self.assertIn(
            'if (count of argv) is not 2 then error "AWA_ARGV_REFUSED"',
            source,
        )
        self.assertIn(
            "do shell script commandText with administrator privileges",
            source,
        )
        self.assertIn('error "AWA_AUTH_CANCELLED"', source)
        self.assertEqual(
            privileged.render_initial_osascript_argv("501", "a" * 64),
            (
                "/usr/bin/osascript",
                "-l",
                "AppleScript",
                "-e",
                source,
                "--",
                "501",
                "a" * 64,
            ),
        )
        self.assertNotIn(str(Path.home()), source)
        self.assertNotIn("/tmp/", source)
        self.assertNotIn("osascript", source)

    def test_admin_command_renderer_uses_only_fixed_root_paths(self) -> None:
        command = privileged.render_admin_command(
            operation="REPAIR",
            requested_uid="501",
            request_id="a" * 64,
        )
        self.assertEqual(command.decision, "REFUSE")
        command = privileged.render_admin_command(
            operation="UPDATE",
            requested_uid="501",
            request_id="a" * 64,
        )
        self.assertEqual(command.decision, "ALLOW")
        self.assertEqual(
            command.shell_argv,
            (
                "/usr/bin/env",
                "-i",
                "LANG=C",
                "LC_ALL=C",
                "/Library/Application Support/AWA/bin/"
                "awa-private-runtime-admin",
                "UPDATE",
                "501",
                "a" * 64,
            ),
        )


class QualificationFixtureTest(unittest.TestCase):
    def test_q1_q2_lifecycle_is_deterministic_and_contains_no_private_key(
        self,
    ) -> None:
        fixture_hashes = {}
        for fixture in ("Q1", "Q2"):
            first = privileged.build_synthetic_qualification_fixture(
                fixture=fixture,
                exact_head=EXACT_HEAD,
                qualification_nonce="a" * 64,
                qualification_root="/Library/Application Support/"
                "AWA-qualification-" + "a" * 64,
                runtime_digest="1" * 64,
                qualification_allowed_signers_digest="2" * 64,
                synthetic_signature=("signature-" + fixture).encode("ascii"),
            )
            second = privileged.build_synthetic_qualification_fixture(
                fixture=fixture,
                exact_head=EXACT_HEAD,
                qualification_nonce="a" * 64,
                qualification_root="/Library/Application Support/"
                "AWA-qualification-" + "a" * 64,
                runtime_digest="1" * 64,
                qualification_allowed_signers_digest="2" * 64,
                synthetic_signature=("signature-" + fixture).encode("ascii"),
            )
            self.assertEqual(first, second)
            self.assertEqual(first["fixture_id"], fixture)
            self.assertEqual(first["envelope"]["mode"], "QUALIFY")
            self.assertEqual(
                first["signature_namespace"],
                "awa-private-runtime-qualification-release-v1",
            )
            serialized = privileged.canonical_lf_bytes(first).upper()
            self.assertNotIn(b"BEGIN OPENSSH PRIVATE KEY", serialized)
            self.assertNotIn(b'"PRIVATE_KEY"', serialized)
            fixture_hashes[fixture] = privileged.qualification_fixture_digest(first)
        self.assertNotEqual(fixture_hashes["Q1"], fixture_hashes["Q2"])


class QualificationPacketTest(unittest.TestCase):
    def test_v12_packet_binds_every_exact_product_authority_asset(self) -> None:
        self.assertTrue(
            set(V12_PRODUCT_AUTHORITY_ROLES)
            <= privileged.PACKET_ROOT_ROLES,
            "packet root omits accepted product-authority roles",
        )
        self.assertEqual(
            privileged.PACKET_ROOT_ROLES,
            privileged._READER_ROOT_ROLES,
        )
        packet = _complete_packet_builder().finalize(_final_packet_values())
        by_role = {
            record["role"]: record
            for record in packet["packet_root_index"]["records"]
        }
        for role in V12_PRODUCT_AUTHORITY_ROLES:
            with self.subTest(role=role):
                self.assertIn(role, by_role)
                content = packet["blobs"][by_role[role]["sha256"]]
                self.assertEqual(
                    hashlib.sha256(content).hexdigest(),
                    by_role[role]["sha256"],
                )
        changed = dict(packet)
        changed["blobs"] = dict(packet["blobs"])
        target = by_role["IMPORT_MANIFEST"]["sha256"]
        changed["blobs"][target] = b'{"schema":"wrong/v1"}\n'
        with self.assertRaises(ValueError):
            privileged.validate_qualification_packet(changed)

    def test_packet_indices_bind_content_addressed_fixture_blobs(self) -> None:
        builder = _complete_packet_builder()
        packet_root = builder.finalize_packet_root()
        packet = builder.finalize(_final_packet_values())
        request_sha = packet["bound_index"]["records"][0]["sha256"]
        evidence_sha = packet["evidence_index"]["records"][0]["sha256"]
        self.assertEqual(
            hashlib.sha256(packet["blobs"][request_sha]).hexdigest(),
            request_sha,
        )
        self.assertEqual(
            hashlib.sha256(packet["blobs"][evidence_sha]).hexdigest(),
            evidence_sha,
        )
        self.assertIn(
            request_sha,
            {row["sha256"] for row in packet["bound_index"]["records"]},
        )
        self.assertIn(
            evidence_sha,
            {row["sha256"] for row in packet["evidence_index"]["records"]},
        )
        self.assertIn(
            privileged.V8_STATIC_CONTRACT_HASHES[
                "contracts/awa-contract.v2.json"
            ],
            {row["sha256"] for row in packet["packet_root_index"]["records"]},
        )
        self.assertEqual(
            packet["bound_index"]["packet_root_digest"],
            packet_root,
        )
        self.assertEqual(
            packet["bound_index_digest"],
            packet["bound_index"]["index_digest"],
        )
        self.assertEqual(
            packet["evidence_index_digest"],
            packet["evidence_index"]["index_digest"],
        )
        self.assertEqual(
            packet["packet_root_index"]["schema"],
            (
                "awa-registration-private-runtime-qualification-"
                "packet-root-index/v2"
            ),
        )
        self.assertEqual(
            packet["bound_index"]["schema"],
            (
                "awa-registration-private-runtime-qualification-"
                "bound-input-index/v2"
            ),
        )
        self.assertEqual(
            packet["evidence_index"]["schema"],
            (
                "awa-registration-private-runtime-qualification-"
                "evidence-index/v2"
            ),
        )
        final_packet = packet["packet"]
        self.assertEqual(
            final_packet["schema"],
            "awa-registration-private-runtime-qualification/v2",
        )
        self.assertEqual(
            packet["packet_bytes"],
            privileged.canonical_lf_bytes(final_packet),
        )
        body = dict(final_packet)
        claim = body.pop("packet_digest")
        self.assertEqual(
            claim,
            privileged.authority_digest(
                "awa-registration-private-runtime-qualification/v2",
                body,
            ),
        )

    def test_packet_builder_rejects_cycles_and_digest_aliasing(self) -> None:
        builder = privileged.QualificationPacketBuilder(
            exact_head=EXACT_HEAD,
            accepted_digest="8" * 64,
            c_runtime_scope_hash="7" * 64,
        )
        with self.assertRaises(ValueError):
            builder.add_packet_root_blob(
                role="PACKET_ROOT",
                domain="self",
                content=b"packet_root_digest",
            )
        digest = builder.add_packet_root_blob(
            role="STATIC_CONTRACT",
            domain="one",
            content=b"same",
        )
        with self.assertRaises(ValueError):
            builder.add_packet_root_blob(
                role="SOURCE_LOCK",
                domain="two",
                content=b"same",
            )
        self.assertEqual(digest, hashlib.sha256(b"same").hexdigest())

    def test_prepare_and_finalize_dependencies_are_ordered(self) -> None:
        incomplete = privileged.QualificationPacketBuilder(
            exact_head=EXACT_HEAD,
            accepted_digest="8" * 64,
            c_runtime_scope_hash="7" * 64,
        )
        with self.assertRaises(ValueError):
            incomplete.finalize_packet_root()
        builder = _complete_packet_builder(include_evidence=False)
        with self.assertRaises(ValueError):
            builder.finalize(_final_packet_values())
        builder.add_evidence_blob(
            role="AUTHORIZATION_RESULT",
            domain="synthetic-authorization-result/v1",
            content=privileged.canonical_lf_bytes(
                {
                    "schema": "synthetic-authorization-result/v1",
                    "replacement": True,
                }
            ),
            media_type="application/json",
            encoding="JCS_LF",
        )
        missing = _final_packet_values()
        missing.pop("private_key_deletion")
        with self.assertRaises(ValueError):
            builder.finalize(missing)

    def test_prepare_is_complete_before_privileged_evidence_exists(self) -> None:
        builder = _complete_packet_builder(include_evidence=False)
        prepared = builder.prepare()
        self.assertNotIn("evidence_index", prepared)
        self.assertNotIn("packet", prepared)
        with tempfile.TemporaryDirectory() as parent:
            output = Path(parent) / "packet"
            privileged.publish_qualification_packet_prepare(output, prepared)
            self.assertEqual(
                set(path.name for path in output.iterdir()),
                {
                    "packet-root-index.json",
                    "bound-input-index.json",
                    "inputs",
                    "evidence",
                },
            )
            builder.add_evidence_blob(
                role="AUTHORIZATION_RESULT",
                domain="synthetic-authorization-result/v1",
                content=privileged.canonical_lf_bytes(
                    {
                        "schema": "synthetic-authorization-result/v1",
                        "after_prompt": True,
                    }
                ),
                media_type="application/json",
                encoding="JCS_LF",
            )
            packet = builder.finalize(_final_packet_values())
            finalize_readback = (
                privileged.publish_qualification_packet_finalize(output, packet)
            )
            self.assertEqual(
                finalize_readback["qualification_packet_digest"],
                packet["qualification_packet_digest"],
            )

    def test_final_packet_fields_and_static_contract_set_are_exact(self) -> None:
        packet = _complete_packet_builder().finalize(_final_packet_values())
        missing = dict(packet)
        missing_final = dict(packet["packet"])
        missing_final.pop("product_authority_evidence")
        missing["packet"] = missing_final
        with self.assertRaises(ValueError):
            privileged.validate_qualification_packet(missing)
        extra = dict(packet)
        extra_final = {**packet["packet"], "unknown": True}
        extra["packet"] = extra_final
        with self.assertRaises(ValueError):
            privileged.validate_qualification_packet(extra)
        missing_static = dict(packet)
        root = dict(packet["packet_root_index"])
        root["records"] = [
            row
            for row in root["records"]
            if row["domain"] != "contracts/awa-contract.v1.json"
        ]
        root_body = dict(root)
        root_body.pop("index_digest")
        root["index_digest"] = privileged.authority_digest(
            privileged.PACKET_ROOT_DOMAIN, root_body
        )
        missing_static["packet_root_index"] = root
        missing_static["packet_root_index_bytes"] = (
            privileged.canonical_lf_bytes(root)
        )
        missing_static["packet_root_digest"] = root["index_digest"]
        with self.assertRaises(ValueError):
            privileged.validate_qualification_packet(missing_static)

    def test_final_packet_payload_types_and_closed_shapes_are_exact(self) -> None:
        values = _final_packet_values()
        privileged._validate_final_packet_payload_shapes(values)
        wrong_values = (
            ("selected_build_id", {"build_id": "A"}),
            ("builds", {"A": values["builds"][0]}),
            ("builds", [values["builds"][0]]),
            ("final_archives", values["final_archives"][0]),
            ("final_archives", [values["final_archives"][0]]),
            (
                "relocation_load_image_evidence",
                [values["relocation_load_image_evidence"][0]],
            ),
            ("executed_identities", values["executed_identities"][0]),
            ("source_lock", []),
            (
                "private_key_deletion",
                {
                    **values["private_key_deletion"],
                    "unexpected": True,
                },
            ),
            (
                "product_authority_evidence",
                {
                    key: value
                    for key, value in values[
                        "product_authority_evidence"
                    ].items()
                    if key != "digest"
                },
            ),
        )
        for field, replacement in wrong_values:
            with self.subTest(field=field, replacement_type=type(replacement)):
                changed = dict(values)
                changed[field] = replacement
                with self.assertRaises(ValueError):
                    privileged._validate_final_packet_payload_shapes(changed)
                with self.assertRaises(ValueError):
                    privileged._reader_validate_final_packet_payload_shapes(
                        changed
                    )

    def test_nested_packet_payload_values_refuse_wrong_types_recursively(
        self,
    ) -> None:
        values = _final_packet_values()
        mutations = []

        def mutate(field: str, path: tuple[str | int, ...], replacement: object):
            changed = json.loads(json.dumps(values))
            target = changed[field]
            for part in path[:-1]:
                target = target[part]
            target[path[-1]] = replacement
            mutations.append((field, path, changed))

        mutate("source_lock", ("sha256",), True)
        mutate("github_attestation", ("matching_record_count",), True)
        mutate("github_attestation", ("verified",), 1)
        mutate("github_attestation", ("verification_command",), [1])
        mutate("github_attestation", ("rejected_records",), ["bad"])
        mutate("github_attestation", ("bundle", "size"), True)
        mutate("capability", ("object",), [])
        mutate("compile_options", ("object",), {"schema": "wrong"})
        mutate("builds", (0, "toolchain", "codesign_sha256"), False)
        mutate("builds", (0, "manifest", "object"), [])
        mutate("builds", (0, "signature_inventory", "object"), [])
        mutate("builds", (0, "registration_tests", "passed"), True)
        mutate("byte_comparison", ("equal",), 1)
        mutate("relocation_load_image_evidence", (0, "command"), [1])
        mutate("qualification_allowed_signers", ("blob", "mode"), 444)
        mutate("qualification_fixtures", ("q1", "epoch"), True)
        mutate("privileged_qualification_context", ("object",), [])
        mutate("preprompt_rejection_evidence", ("cases",), ["bad"])
        mutate("admin_qualification_evidence", ("no_residue",), 1)
        mutate("parent_death_evidence", ("cases",), ["bad"])
        mutate("executed_identities", (0, "dev"), True)
        mutate("securityagent_result", ("prompt_count",), True)
        mutate("private_key_deletion", ("private_material_absent",), 1)
        mutate("product_authority_evidence", ("retention_cases",), ["bad"])
        mutate("fd_topology_evidence", ("fault_cases",), ["bad"])
        mutate("retained_import_evidence", ("manifest_digest",), [])
        mutate("transaction_recovery_evidence", ("fault_cases",), ["bad"])
        mutate("shell_startup_evidence", ("script_hashes",), ["bad"])
        for field, path, changed in mutations:
            with self.subTest(field=field, path=path):
                with self.assertRaises(ValueError):
                    privileged._validate_final_packet_payload_shapes(changed)

    def test_reader_writer_authority_manifests_remain_in_exact_parity(
        self,
    ) -> None:
        self.assertEqual(privileged.PACKET_ROOT_ROLES, privileged._READER_ROOT_ROLES)
        self.assertEqual(privileged.BOUND_ROLES, privileged._READER_BOUND_ROLES)
        self.assertEqual(privileged.EVIDENCE_ROLES, privileged._READER_EVIDENCE_ROLES)
        self.assertEqual(
            privileged.V8_STATIC_CONTRACT_HASHES,
            privileged._READER_STATIC_CONTRACT_HASHES,
        )
        self.assertIsNot(
            privileged.V8_STATIC_CONTRACT_HASHES,
            privileged._READER_STATIC_CONTRACT_HASHES,
        )

    def test_in_memory_and_reader_refuse_role_encoding_mismatch(self) -> None:
        packet = _complete_packet_builder().finalize(_final_packet_values())
        for key, replacement in (
            ("bound_index", "BINARY"),
            ("evidence_index", "UTF8"),
        ):
            with self.subTest(index=key):
                index = {
                    **packet[key],
                    "records": [
                        {
                            **packet[key]["records"][0],
                            "encoding": replacement,
                        },
                        *packet[key]["records"][1:],
                    ],
                }
                body = dict(index)
                body.pop("index_digest")
                domain = (
                    privileged.BOUND_INPUT_DOMAIN
                    if key == "bound_index"
                    else privileged.EVIDENCE_DOMAIN
                )
                index["index_digest"] = privileged.authority_digest(
                    domain, body
                )
                with self.assertRaises(ValueError):
                    privileged._validate_packet_index(
                        index,
                        schema=index["schema"],
                        domain=domain,
                        packet_root_digest=packet["packet_root_digest"],
                    )
                indexes = {
                    "root": packet["packet_root_index"],
                    "bound": packet["bound_index"],
                    "evidence": packet["evidence_index"],
                }
                indexes[
                    "bound" if key == "bound_index" else "evidence"
                ] = index
                with self.assertRaises(ValueError):
                    privileged._reader_validate_packet(
                        root_index=indexes["root"],
                        root_bytes=privileged.canonical_lf_bytes(indexes["root"]),
                        bound_index=indexes["bound"],
                        bound_bytes=privileged.canonical_lf_bytes(indexes["bound"]),
                        evidence_index=indexes["evidence"],
                        evidence_bytes=privileged.canonical_lf_bytes(
                            indexes["evidence"]
                        ),
                        final_packet=packet["packet"],
                        packet_bytes=packet["packet_bytes"],
                        blobs=packet["blobs"],
                    )

    def test_in_memory_packet_indexes_refuse_wrong_and_cross_index_roles(
        self,
    ) -> None:
        packet = _complete_packet_builder().finalize(_final_packet_values())
        cases = (
            (
                "packet_root_index",
                privileged.PACKET_ROOT_INDEX_SCHEMA,
                privileged.PACKET_ROOT_DOMAIN,
                None,
                "PRIVILEGED_REQUEST",
            ),
            (
                "bound_index",
                privileged.BOUND_INPUT_INDEX_SCHEMA,
                privileged.BOUND_INPUT_DOMAIN,
                packet["packet_root_digest"],
                "AUTHORIZATION_RESULT",
            ),
            (
                "evidence_index",
                privileged.EVIDENCE_INDEX_SCHEMA,
                privileged.EVIDENCE_DOMAIN,
                packet["packet_root_digest"],
                "ROOT_ADMIN",
            ),
        )
        for key, schema, domain, packet_root, role in cases:
            with self.subTest(index=key, role=role):
                index = {
                    **packet[key],
                    "records": [
                        {**packet[key]["records"][0], "role": role},
                        *packet[key]["records"][1:],
                    ],
                }
                body = dict(index)
                body.pop("index_digest")
                index["index_digest"] = privileged.authority_digest(
                    domain, body
                )
                with self.assertRaises(ValueError):
                    privileged._validate_packet_index(
                        index,
                        schema=schema,
                        domain=domain,
                        packet_root_digest=packet_root,
                    )
                changed_indexes = {
                    "packet_root_index": packet["packet_root_index"],
                    "bound_index": packet["bound_index"],
                    "evidence_index": packet["evidence_index"],
                }
                changed_indexes[key] = index
                with self.assertRaises(ValueError):
                    privileged._reader_validate_packet(
                        root_index=changed_indexes["packet_root_index"],
                        root_bytes=privileged.canonical_lf_bytes(
                            changed_indexes["packet_root_index"]
                        ),
                        bound_index=changed_indexes["bound_index"],
                        bound_bytes=privileged.canonical_lf_bytes(
                            changed_indexes["bound_index"]
                        ),
                        evidence_index=changed_indexes["evidence_index"],
                        evidence_bytes=privileged.canonical_lf_bytes(
                            changed_indexes["evidence_index"]
                        ),
                        final_packet=packet["packet"],
                        packet_bytes=packet["packet_bytes"],
                        blobs=packet["blobs"],
                    )

    def test_blob_encodings_have_distinct_exact_rules(self) -> None:
        positives = (
            (b"\xff\x00", "BINARY"),
            ("snowman \u2603".encode("utf-8"), "UTF8"),
            (b"line one\nline two\n", "UTF8_LF"),
            (b'{"schema":"example/v1"}\n', "JCS_LF"),
        )
        for content, encoding in positives:
            with self.subTest(positive=encoding):
                privileged._validate_blob_encoding(content, encoding)
        negatives = (
            (b"\xef\xbb\xbftext", "UTF8"),
            (b"nul\0", "UTF8"),
            (b"missing-lf", "UTF8_LF"),
            (b"double\n\n", "UTF8_LF"),
            (b'{"b":1, "a":2}\n', "JCS_LF"),
            (b'{"a":1,"a":2}\n', "JCS_LF"),
        )
        for content, encoding in negatives:
            with self.subTest(negative=(content, encoding)):
                with self.assertRaises((UnicodeError, ValueError)):
                    privileged._validate_blob_encoding(content, encoding)

    def test_packet_v1_mixed_and_unknown_authority_refuses(self) -> None:
        packet = _complete_packet_builder().finalize(_final_packet_values())
        for key, replacement in (
            (
                "packet_root_index",
                "awa-registration-private-runtime-qualification-"
                "packet-root-index/v1",
            ),
            (
                "bound_index",
                "awa-registration-private-runtime-qualification-"
                "bound-input-index/v1",
            ),
            (
                "evidence_index",
                "awa-registration-private-runtime-qualification-"
                "evidence-index/v1",
            ),
        ):
            with self.subTest(key=key):
                changed = dict(packet)
                changed[key] = {**packet[key], "schema": replacement}
                with self.assertRaises(ValueError):
                    privileged.validate_qualification_packet(changed)
        changed = dict(packet)
        changed["packet"] = {
            **packet["packet"],
            "schema": "awa-registration-private-runtime-qualification/v1",
        }
        with self.assertRaises(ValueError):
            privileged.validate_qualification_packet(changed)

    def test_typed_root_and_final_packet_digests_are_not_interchangeable(
        self,
    ) -> None:
        packet = _complete_packet_builder().finalize(_final_packet_values())
        readback = _valid_readback(packet)
        privileged.validate_qualification_packet_binding(
            packet_root_digest=packet["packet_root_digest"],
            qualification_packet_digest=packet[
                "qualification_packet_digest"
            ],
            readback=readback,
        )
        for root, final in (
            (
                packet["qualification_packet_digest"],
                packet["qualification_packet_digest"],
            ),
            (packet["packet_root_digest"], packet["packet_root_digest"]),
            (
                packet["qualification_packet_digest"],
                packet["packet_root_digest"],
            ),
        ):
            with self.subTest(root=root, final=final):
                with self.assertRaises(ValueError):
                    privileged.validate_qualification_packet_binding(
                        packet_root_digest=root,
                        qualification_packet_digest=final,
                        readback=readback,
                    )

    def test_packet_binding_requires_exact_authenticated_readback(self) -> None:
        packet = _complete_packet_builder().finalize(_final_packet_values())
        readback = _valid_readback(packet)
        privileged.validate_qualification_packet_binding(
            packet_root_digest=packet["packet_root_digest"],
            qualification_packet_digest=packet[
                "qualification_packet_digest"
            ],
            readback=readback,
        )
        variants = [
            {key: value for key, value in readback.items() if key != "schema"},
            {**readback, "unexpected": True},
            {**readback, "schema": "qualification-readback/v0"},
            {**readback, "verified": 1},
            {**readback, "static_contract_set_equal": 1},
            {**readback, "packet_file_count": True},
            {**readback, "verifier_digest": "0" * 64},
        ]
        for variant in variants:
            with self.subTest(fields=set(variant)):
                with self.assertRaises(ValueError):
                    privileged.validate_qualification_packet_binding(
                        packet_root_digest=packet["packet_root_digest"],
                        qualification_packet_digest=packet[
                            "qualification_packet_digest"
                        ],
                        readback=variant,
                    )

    def test_descriptor_safe_publish_and_three_fresh_readbacks(self) -> None:
        packet = _complete_packet_builder().finalize(_final_packet_values())
        with tempfile.TemporaryDirectory() as parent:
            output = Path(parent) / "packet"
            privileged.publish_qualification_packet_prepare(
                output, _complete_packet_builder().prepare()
            )
            self.assertFalse((output / "packet.json").exists())
            self.assertFalse((output / "evidence-index.json").exists())
            finalize = privileged.publish_qualification_packet_finalize(
                output, packet
            )
            expected = {
                "repository": "KleinPerkins/awa",
                "exact_head": EXACT_HEAD,
                "packet_root_digest": packet["packet_root_digest"],
                "bound_input_index_digest": packet["bound_index_digest"],
                "evidence_root_digest": packet["evidence_index_digest"],
                "qualification_packet_digest": packet[
                    "qualification_packet_digest"
                ],
            }
            accept = privileged.verify_qualification_packet_directory(
                output, **expected
            )
            ready = privileged.verify_qualification_packet_directory(
                output, **expected
            )
            self.assertEqual(finalize, accept)
            self.assertEqual(finalize, ready)
            self.assertTrue(finalize["verified"])
            self.assertTrue(finalize["static_contract_set_equal"])

    def test_readback_is_independent_of_writer_side_packet_validator(self) -> None:
        packet = _complete_packet_builder().finalize(_final_packet_values())
        expected = {
            "repository": "KleinPerkins/awa",
            "exact_head": EXACT_HEAD,
            "packet_root_digest": packet["packet_root_digest"],
            "bound_input_index_digest": packet["bound_index_digest"],
            "evidence_root_digest": packet["evidence_index_digest"],
            "qualification_packet_digest": packet[
                "qualification_packet_digest"
            ],
        }
        with tempfile.TemporaryDirectory() as parent:
            output = Path(parent) / "packet"
            privileged.publish_qualification_packet_prepare(
                output, _complete_packet_builder().prepare()
            )
            privileged.publish_qualification_packet_finalize(output, packet)
            with mock.patch.object(
                privileged,
                "validate_qualification_packet",
                side_effect=AssertionError("writer validator called by reader"),
            ), mock.patch.object(
                privileged,
                "_validate_final_packet_payload_shapes",
                side_effect=AssertionError("writer payload validator called by reader"),
            ):
                readback = privileged.verify_qualification_packet_directory(
                    output, **expected
                )
            self.assertTrue(readback["verified"])

    def test_descriptor_verifier_refuses_mutation_and_unexpected_names(
        self,
    ) -> None:
        packet = _complete_packet_builder().finalize(_final_packet_values())
        with tempfile.TemporaryDirectory() as parent:
            output = Path(parent) / "packet"
            privileged.publish_qualification_packet_prepare(
                output, _complete_packet_builder().prepare()
            )
            privileged.publish_qualification_packet_finalize(output, packet)
            (output / "unexpected").write_bytes(b"x")
            with self.assertRaises(ValueError):
                privileged.verify_qualification_packet_directory(
                    output,
                    repository="KleinPerkins/awa",
                    exact_head=EXACT_HEAD,
                    packet_root_digest=packet["packet_root_digest"],
                    bound_input_index_digest=packet["bound_index_digest"],
                    evidence_root_digest=packet["evidence_index_digest"],
                    qualification_packet_digest=packet[
                        "qualification_packet_digest"
                    ],
                )

    def test_readback_refuses_between_gate_content_and_metadata_drift(
        self,
    ) -> None:
        packet = _complete_packet_builder().finalize(_final_packet_values())
        expected = {
            "repository": "KleinPerkins/awa",
            "exact_head": EXACT_HEAD,
            "packet_root_digest": packet["packet_root_digest"],
            "bound_input_index_digest": packet["bound_index_digest"],
            "evidence_root_digest": packet["evidence_index_digest"],
            "qualification_packet_digest": packet[
                "qualification_packet_digest"
            ],
        }
        with tempfile.TemporaryDirectory() as parent:
            output = Path(parent) / "packet"
            privileged.publish_qualification_packet_prepare(
                output, _complete_packet_builder().prepare()
            )
            privileged.publish_qualification_packet_finalize(output, packet)
            privileged.verify_qualification_packet_directory(
                output, **expected
            )
            packet_path = output / "packet.json"
            packet_path.chmod(0o600)
            with self.assertRaises(ValueError):
                privileged.verify_qualification_packet_directory(
                    output, **expected
                )

    def test_writer_handles_short_write_and_eintr_and_refuses_fsync_failure(
        self,
    ) -> None:
        packet = _complete_packet_builder().finalize(_final_packet_values())
        real_write = os.write
        calls = 0

        def interrupted_short_write(fd: int, content: object) -> int:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise InterruptedError
            view = memoryview(content)
            return real_write(fd, view[: max(1, len(view) // 2)])

        with tempfile.TemporaryDirectory() as parent:
            output = Path(parent) / "packet"
            with mock.patch.object(
                os, "write", side_effect=interrupted_short_write
            ):
                privileged.publish_qualification_packet_prepare(
                    output, _complete_packet_builder().prepare()
                )
            self.assertGreater(calls, 2)
        with tempfile.TemporaryDirectory() as parent:
            output = Path(parent) / "packet"
            with mock.patch.object(os, "fsync", side_effect=OSError("fsync")):
                with self.assertRaises(OSError):
                    privileged.publish_qualification_packet_prepare(
                        output, _complete_packet_builder().prepare()
                    )

    def test_writer_verify_read_retries_eintr_and_refuses_identity_drift(
        self,
    ) -> None:
        real_read = os.read
        read_calls = 0

        def interrupted_read(fd: int, size: int) -> bytes:
            nonlocal read_calls
            read_calls += 1
            if read_calls == 1:
                raise InterruptedError
            return real_read(fd, size)

        with tempfile.TemporaryDirectory() as parent:
            output = Path(parent) / "packet"
            with mock.patch.object(os, "read", side_effect=interrupted_read):
                privileged.publish_qualification_packet_prepare(
                    output, _complete_packet_builder().prepare()
                )
            self.assertGreater(read_calls, 1)

        real_fstat = os.fstat
        verify_reads: dict[tuple[int, int], int] = {}

        def drifting_fstat(fd: int):
            current = real_fstat(fd)
            if (
                current.st_mode & 0o777 == 0o444
                and current.st_size == 1
            ):
                identity = (fd, current.st_ino)
                verify_reads[identity] = verify_reads.get(identity, 0) + 1
                if verify_reads[identity] == 2:
                    changed = mock.Mock(wraps=current)
                    changed.st_size = current.st_size + 1
                    return changed
            return current

        with tempfile.TemporaryDirectory() as parent:
            directory_fd = os.open(parent, privileged._directory_flags())
            try:
                with mock.patch.object(
                    os, "fstat", side_effect=drifting_fstat
                ):
                    with self.assertRaises(ValueError):
                        privileged._write_file_at(directory_fd, "drift", b"x")
            finally:
                os.close(directory_fd)

    def test_read_file_refuses_post_read_permission_and_link_drift(self) -> None:
        real_fstat = os.fstat
        for attribute, replacement in (("st_mode", 0o100600), ("st_nlink", 2)):
            with self.subTest(attribute=attribute):
                with tempfile.TemporaryDirectory() as parent:
                    directory_fd = os.open(
                        parent, privileged._directory_flags()
                    )
                    privileged._write_file_at(directory_fd, "value", b"x")
                    calls: dict[tuple[int, int], int] = {}

                    def drifting_fstat(fd: int):
                        current = real_fstat(fd)
                        identity = (fd, current.st_ino)
                        calls[identity] = calls.get(identity, 0) + 1
                        if (
                            current.st_size == 1
                            and calls[identity] == 2
                        ):
                            changed = mock.Mock(wraps=current)
                            setattr(changed, attribute, replacement)
                            return changed
                        return current

                    try:
                        with mock.patch.object(
                            os, "fstat", side_effect=drifting_fstat
                        ):
                            with self.assertRaises(ValueError):
                                privileged._read_file_at(
                                    directory_fd, "value", 1024
                                )
                    finally:
                        os.close(directory_fd)

    def test_safe_writer_refuses_preexisting_and_symlinked_roots(self) -> None:
        packet = _complete_packet_builder().finalize(_final_packet_values())
        with tempfile.TemporaryDirectory() as parent:
            output = Path(parent) / "packet"
            output.mkdir()
            with self.assertRaises(ValueError):
                privileged.publish_qualification_packet_prepare(
                    output, _complete_packet_builder().prepare()
                )
        with tempfile.TemporaryDirectory() as parent:
            target = Path(parent) / "target"
            target.mkdir()
            output = Path(parent) / "packet"
            output.symlink_to(target, target_is_directory=True)
            with self.assertRaises(ValueError):
                privileged.publish_qualification_packet_prepare(
                    output, _complete_packet_builder().prepare()
                )


class InstalledAdminContextTest(unittest.TestCase):
    def test_admin_context_binds_closure_to_owner_signed_packet_root(self) -> None:
        admin = _load_admin()
        closure_bytes = {
            role: f"{role}\n".encode("ascii")
            for role in admin.CLOSURE_ROLES
        }
        builder = _complete_packet_builder(closure_bytes)
        closure = []
        for role, (path, mode) in admin.CLOSURE_ROLES.items():
            content = closure_bytes[role]
            digest = hashlib.sha256(content).hexdigest()
            closure.append(
                {
                    "role": role,
                    "path": path,
                    "mode": mode,
                    "size": str(len(content)),
                    "sha256": digest,
                    "content_base64": base64.b64encode(content).decode("ascii"),
                }
            )
        packet = builder.finalize(_final_packet_values())
        manifest_digest = "2" * 64
        release_body = {
            "schema": "awa-private-runtime-release-envelope/v1",
            "repository": "KleinPerkins/awa",
            "exact_head": EXACT_HEAD,
            "source_lock_sha256": SOURCE_LOCK_DIGEST,
            "normalizer_source_sha256": "1" * 64,
            "signing_recipe_source_sha256": "3" * 64,
            "capability_digest": "4" * 64,
            "sqlite_compile_options_hash": "5" * 64,
            "runtime_manifest_sha256": manifest_digest,
            "signature_inventory_sha256": "6" * 64,
            "archive_sha256": "7" * 64,
            "archive_size": "1",
            "sbom_sha256": "9" * 64,
            "license_inventory_sha256": "a" * 64,
            "qualification_packet_digest": packet[
                "qualification_packet_digest"
            ],
            "minimum_epoch": "1",
        }
        release = dict(release_body)
        release["release_envelope_digest"] = privileged.authority_digest(
            release["schema"], release_body
        )
        request = privileged.PrivilegedRequest.create(
            mode="PRODUCTION",
            operation="INSTALL",
            requested_uid="501",
            request_id="b" * 64,
            target_root=privileged.PRODUCTION_ROOT,
            packet_root_digest=packet["packet_root_digest"],
            qualification_context_digest=None,
            qualification_allowed_signers_digest=None,
            pre_current_digest=None,
            target_release_envelope_digest=release[
                "release_envelope_digest"
            ],
            target_manifest_sha256=manifest_digest,
            target_epoch="1",
            previous_manifest_sha256=None,
            current_manifest_sha256=manifest_digest,
            new_manifest_sha256=manifest_digest,
            q1_envelope_digest=None,
            q1_manifest_sha256=None,
            q2_envelope_digest=None,
            q2_manifest_sha256=None,
            created_wall_ns="1",
            expires_wall_ns="900000000001",
        ).to_mapping()
        context_body = {
            "schema": "awa-registration-privileged-context/v1",
            "request": request,
            "release_envelope": release,
            "allowed_signers": None,
            "packet_root_index": packet["packet_root_index"],
            "installed_closure": closure,
        }
        context = dict(context_body)
        context["context_digest"] = admin._digest(
            context["schema"], context_body
        )
        parsed = admin.parse_privileged_context(
            admin._canonical(context) + b"\n"
        )
        self.assertEqual(parsed[0], request)
        self.assertEqual(set(parsed[4]), set(admin.CLOSURE_ROLES))
        v1 = json.loads(admin._canonical(context))
        v1["packet_root_index"]["schema"] = (
            "awa-registration-private-runtime-qualification-"
            "packet-root-index/v1"
        )
        v1_body = dict(v1)
        v1_body.pop("context_digest")
        v1["context_digest"] = admin._digest(v1["schema"], v1_body)
        with self.assertRaises(admin.AdminRefusal):
            admin.parse_privileged_context(admin._canonical(v1) + b"\n")

        substituted = json.loads(admin._canonical(context))
        substituted["release_envelope"]["qualification_packet_digest"] = (
            packet["packet_root_digest"]
        )
        release_body = dict(substituted["release_envelope"])
        release_body.pop("release_envelope_digest")
        substituted["release_envelope"]["release_envelope_digest"] = (
            admin._digest(
                substituted["release_envelope"]["schema"], release_body
            )
        )
        substituted_body = dict(substituted)
        substituted_body.pop("context_digest")
        substituted["context_digest"] = admin._digest(
            substituted["schema"], substituted_body
        )
        with self.assertRaises(admin.AdminRefusal):
            admin.parse_privileged_context(
                admin._canonical(substituted) + b"\n"
            )

        changed = json.loads(admin._canonical(context))
        changed["installed_closure"][0]["content_base64"] = base64.b64encode(
            b"tampered"
        ).decode("ascii")
        changed_body = dict(changed)
        changed_body.pop("context_digest")
        changed["context_digest"] = admin._digest(
            changed["schema"], changed_body
        )
        with self.assertRaises(admin.AdminRefusal):
            admin.parse_privileged_context(
                admin._canonical(changed) + b"\n"
            )


class V8TransactionalAdminAuthorityTest(unittest.TestCase):
    def _asset(
        self,
        role: str,
        logical_name: str,
        *,
        nonce: str | None = None,
        request_id: str = "a" * 64,
        context_digest: str = "b" * 64,
        digest: str | None = None,
    ) -> privileged.AdminAssetRecordV1:
        value = digest or hashlib.sha256(
            f"{role}:{logical_name}".encode("utf-8")
        ).hexdigest()
        return privileged.AdminAssetRecordV1(
            role=role,
            logical_name=logical_name,
            content_path=(
                "/Library/Application Support/AWA-admin/v2/staging/sha256/"
                f"{value[:2]}/{value}.blob"
            ),
            size="1",
            mode="0444",
            sha256=value,
            signature_digest=None,
            request_id=request_id,
            qualification_nonce=nonce,
            context_digest=context_digest,
        )

    def _remove_assets(
        self, *, nonce: str | None = None
    ) -> tuple[privileged.AdminAssetRecordV1, ...]:
        records = [
            self._asset(role, role, nonce=nonce)
            for role in (
                "REQUEST",
                "CONTEXT",
                "ADMIN_ENTRYPOINT",
                "REMOVE_INVENTORY",
                "RUNTIME_CURRENT_TARGET",
                "PRODUCT_CURRENT_TARGET",
            )
        ]
        records.extend(
            self._asset(
                "STATIC_CONTRACT_SET",
                path,
                nonce=nonce,
                digest=digest,
            )
            for path, digest in privileged.V8_STATIC_CONTRACT_HASHES.items()
        )
        return tuple(
            sorted(records, key=lambda item: (
                item.role.encode("utf-8"),
                item.logical_name.encode("utf-8"),
            ))
        )

    def test_asset_index_binds_exact_contract_set_and_mode_nonce(self) -> None:
        assets = self._remove_assets()
        index = privileged.AdminAssetIndexV1.create(
            mode="PRODUCTION",
            request_id="a" * 64,
            operation="REMOVE",
            qualification_nonce=None,
            records=assets,
        )
        self.assertEqual(index.record_count, str(len(assets)))
        self.assertEqual(
            privileged.AdminAssetIndexV1.from_bytes(index.to_bytes()),
            index,
        )
        with self.assertRaises(ValueError):
            privileged.AdminAssetIndexV1.create(
                mode="PRODUCTION",
                request_id="a" * 64,
                operation="REMOVE",
                qualification_nonce="c" * 64,
                records=assets,
            )
        with self.assertRaises(ValueError):
            privileged.AdminAssetIndexV1.create(
                mode="PRODUCTION",
                request_id="a" * 64,
                operation="REMOVE",
                qualification_nonce=None,
                records=assets[:-1],
            )
        qualify = tuple(
            privileged.AdminAssetRecordV1.from_mapping(
                {**record.to_mapping(), "qualification_nonce": "c" * 64}
            )
            for record in assets
        )
        with self.assertRaises(ValueError):
            privileged.AdminAssetIndexV1.create(
                mode="QUALIFY",
                request_id="a" * 64,
                operation="REMOVE",
                qualification_nonce="d" * 64,
                records=qualify,
            )

    def test_immutable_phase_chain_has_no_receipt_fixed_point(self) -> None:
        index = privileged.AdminAssetIndexV1.create(
            mode="PRODUCTION",
            request_id="a" * 64,
            operation="REMOVE",
            qualification_nonce=None,
            records=self._remove_assets(),
        )
        chain = privileged.synthetic_admin_success_chain_v2(
            mode="PRODUCTION",
            request_id="a" * 64,
            operation="REMOVE",
            qualification_nonce=None,
            request_digest="d" * 64,
            context_digest="b" * 64,
            asset_index=index,
            pre_head_digest="e" * 64,
            pre_runtime_current_digest="f" * 64,
            pre_product_current_digest="0" * 64,
        )
        privileged.verify_admin_success_chain_v2(
            chain.transactions,
            chain.receipt,
            chain.head,
        )
        self.assertEqual(
            tuple(item.phase for item in chain.transactions),
            (
                "PREPARED",
                "FILES_PUBLISHED",
                "CURRENT_PUBLISHED",
                "RECEIPT_PUBLISHED",
                "COMMITTED",
            ),
        )
        self.assertIsNone(chain.transactions[0].predecessor_transaction_digest)
        self.assertIsNone(chain.transactions[2].admin_receipt_digest)
        self.assertEqual(
            chain.receipt.transaction_digest,
            chain.transactions[2].transaction_digest,
        )
        self.assertEqual(
            chain.head.transaction_digest,
            chain.transactions[-1].transaction_digest,
        )
        changed = list(chain.transactions)
        changed[-1] = privileged.AdminTransactionV1.from_mapping(
            {
                **changed[-1].to_mapping(),
                "predecessor_transaction_digest": "1" * 64,
                "transaction_digest": "2" * 64,
            },
            verify_digest=False,
        )
        with self.assertRaises(ValueError):
            privileged.verify_admin_success_chain_v2(
                tuple(changed), chain.receipt, chain.head
            )

    def test_preprepared_receipt_has_null_transaction_and_asset_index(self) -> None:
        receipt = privileged.AdminAuditReceiptV2.synthetic_preprepared(
            mode="PRODUCTION",
            operation="INSTALL",
            reason_code="ARGUMENT_INVALID",
        )
        self.assertIsNone(receipt.transaction_digest)
        self.assertIsNone(receipt.asset_index_digest)
        self.assertIsNone(receipt.qualification_nonce)
        receipt.validate()


if __name__ == "__main__":
    unittest.main()
