"""Body C authenticated cutover orchestration and C0-C7 restart matrix."""

from __future__ import annotations

import hashlib
import inspect
import json
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from engine import (
    registration_installer,
    registration_jcs,
    registration_lock,
    registration_projection,
    registration_profile,
    registration_schema,
    registration_store,
)
from engine.tests.registration_harness import RegistrationHarness
from engine.tests.test_registration_profile import (
    ROLES,
    _capability,
    _external_interpreter,
)


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _candidate() -> registration_store.ProtocolCandidate:
    identity = b"installer"
    capability = b"capability"
    return registration_store.ProtocolCandidate(
        profile_hash=_digest("profile"),
        runtime_capability_hash=_digest("runtime"),
        writer_binary_hash=_digest("writer"),
        writer_capability_hash=_digest("writer-capability"),
        tool_inventory_hash=_digest("inventory"),
        hook_projection_hash=_digest("projection"),
        hook_matcher_mode="CATCH_ALL",
        hook_matcher_hash=_digest("matcher"),
        projection_receipt_hash=_digest("receipt"),
        projection_file_generation=2,
        installer_identity_hash=registration_store._domain_hash(
            "awa-registration-installer-identity/v1", identity
        ),
        installer_capability_hash=registration_store._domain_hash(
            "awa-registration-installer-capability/v1", capability
        ),
        storage_dev=1,
    )


def _immutable_authority(
    root: Path,
) -> tuple[
    registration_installer.ImmutableBundleAuthority,
    registration_projection.DirectReceipt,
    Path,
]:
    runtime = root / "runtime"
    interpreter = root / "python-fixture"
    interpreter.write_bytes(b"fixture interpreter\n")
    interpreter.chmod(0o700)
    receiver = b"#!/bin/bash\nexit 2\n"
    launcher = b"#!/usr/bin/env python3\nraise SystemExit(2)\n"
    package = b""
    host = b"VALUE = 1\n"
    import_manifest = registration_projection.ImportManifest(
        schema="awa-registration-import-manifest/v1",
        entry_modules=("engine.registration_host",),
        records=(
            registration_projection.ImportRecord(
                "engine/__init__.py",
                "PACKAGE_INITIALIZER",
                str(0o644),
                str(len(package)),
                hashlib.sha256(package).hexdigest(),
            ),
            registration_projection.ImportRecord(
                "engine/registration_host.py",
                "MODULE",
                str(0o644),
                str(len(host)),
                hashlib.sha256(host).hexdigest(),
            ),
        ),
    )
    external_hash = _digest("external-interpreter")
    capability_hash = _digest("interpreter-capability")
    config = registration_projection.LauncherConfig(
        schema="awa-registration-launcher-config/v1",
        bundle_generation="2",
        interpreter_path=str(interpreter.resolve()),
        external_interpreter_hash=external_hash,
        interpreter_capability_hash=capability_hash,
        import_manifest_hash=import_manifest.digest,
        entry_module="engine.registration_host",
        isolated_flags=("-I", "-S", "-B"),
    )
    contract = (
        b'KleinPerkins namespaces="awa-registration-owner-gate-v2" '
        b"ssh-ed25519 "
        b"AAAAC3NzaC1lZDI1NTE5AAAAIE+scgn2qp86lkQWcVDpJ+SXT/"
        b"pVF0DntlxGVnmnFyEp\n"
    )
    public_hash, fingerprint, contract_hash = (
        registration_projection._parse_allowed_signers(contract)
    )
    key_enrollment = registration_projection._domain_hash(
        "awa-registration-owner-key-enrollment/v1",
        {
            "schema": "awa-registration-owner-key-enrollment/v1",
            "principal": "KleinPerkins",
            "namespace": "awa-registration-owner-gate-v2",
            "key_algorithm": "ssh-ed25519",
            "public_key_sha256": public_hash,
            "openssh_fingerprint": fingerprint,
            "allowed_signers_relative_path": (
                "contracts/awa-registration-owner-signers.v1"
            ),
            "allowed_signers_path_hash": hashlib.sha256(
                b"awa-registration-owner-signers-path/v1\0"
                b"contracts/awa-registration-owner-signers.v1"
            ).hexdigest(),
            "allowed_signers_contract_hash": contract_hash,
            "authorized": True,
        },
    )
    payloads = {
        "bin/awa-registration-launcher": launcher,
        "bin/awa-registration-receiver": receiver,
        "contracts/awa-registration-owner-signers.v1": contract,
        "engine/__init__.py": package,
        "engine/registration_host.py": host,
        "import-manifest.json": import_manifest.to_bytes(),
        "runtime-config.json": config.to_bytes(),
    }
    roles = {
        "bin/awa-registration-launcher": ("LAUNCHER", 0o755),
        "bin/awa-registration-receiver": ("RECEIVER", 0o755),
        "contracts/awa-registration-owner-signers.v1": (
            "SIGNER_CONTRACT",
            0o644,
        ),
        "engine/__init__.py": ("PACKAGE_INITIALIZER", 0o644),
        "engine/registration_host.py": ("RUNTIME", 0o644),
        "import-manifest.json": ("IMPORT_MANIFEST", 0o644),
        "runtime-config.json": ("CONFIG", 0o600),
    }
    entries = tuple(
        registration_projection.BundleEntry(
            path,
            roles[path][0],
            str(roles[path][1]),
            str(len(payloads[path])),
            hashlib.sha256(payloads[path]).hexdigest(),
        )
        for path in sorted(payloads, key=lambda item: item.encode())
    )
    manifest = registration_projection.BundleManifest(
        schema="awa-registration-bundle-manifest/v1",
        generation="2",
        entries=entries,
        import_manifest_hash=import_manifest.digest,
        external_interpreter_hash=external_hash,
        interpreter_capability_hash=capability_hash,
        allowed_signers_contract_hash=contract_hash,
    )
    projection = registration_projection.BundleProjection(
        schema="awa-registration-bundle-projection/v1",
        generation="2",
        bundle_digest=manifest.digest,
        receiver_relative_path="bin/awa-registration-receiver",
        launcher_relative_path="bin/awa-registration-launcher",
        import_manifest_hash=import_manifest.digest,
        external_interpreter_hash=external_hash,
        interpreter_capability_hash=capability_hash,
        runtime_config_hash=config.file_hash,
        allowed_signers_contract_hash=contract_hash,
    )
    inventory = (
        registration_projection.InventoryEntry(
            "preToolUse",
            "",
            "Shell",
            "ordinary",
            "cursor-permission/v1",
        ),
    )
    key = ("preToolUse", "", "Shell", "cursor-permission/v1")
    request = b'{"hook_event_name":"preToolUse","tool_name":"Shell"}'
    output = b'{"permission":"deny"}\n'
    proof_records = tuple(
        sorted(
            (
                registration_projection.DenialProofRecord(
                    event=key[0],
                    server_or_empty=key[1],
                    discriminator=key[2],
                    serializer_schema=key[3],
                    role="ordinary",
                    seam=seam,
                    bundle_digest=manifest.digest,
                    request_hash=hashlib.sha256(request).hexdigest(),
                    output_hash=hashlib.sha256(output).hexdigest(),
                    exit_code="2",
                )
                for seam in (
                    "DIRECT_RECEIVER",
                    "SHADOW_INSTALLED",
                )
            ),
            key=lambda record: registration_jcs.canonical_bytes(
                record.to_mapping()
            ),
        )
    )
    proof = registration_projection.StagedDenialProof(
        "awa-registration-staged-denial-proof/v2",
        proof_records,
    )
    fixed, _ = registration_projection.fixed_authority_vector(
        "R1_CANARY"
    )
    receiver_hash = hashlib.sha256(
        b"awa-registration-installed-file/v1\0" + receiver
    ).hexdigest()
    runtime_entries = tuple(
        entry
        for entry in entries
        if entry.role in {"PACKAGE_INITIALIZER", "RUNTIME"}
    )
    wrapper_hash = registration_projection.wrapper_runtime_v2_hash(
        bundle_digest=manifest.digest,
        launcher_hash=next(
            entry.sha256
            for entry in entries
            if entry.role == "LAUNCHER"
        ),
        import_manifest_hash=import_manifest.digest,
        external_interpreter_hash=external_hash,
        interpreter_capability_hash=capability_hash,
        launcher_config_hash=config.file_hash,
        runtime_records=runtime_entries,
    )
    receipt = registration_projection.DirectReceipt.from_mapping(
        {
            **fixed.to_mapping(),
            "installed_file_hash": receiver_hash,
            "wrapper_runtime_hash": wrapper_hash,
            "bundle_digest": manifest.digest,
            "bundle_projection_hash": projection.digest,
            "import_manifest_hash": import_manifest.digest,
            "external_interpreter_hash": external_hash,
            "interpreter_capability_hash": capability_hash,
            "denial_proof_vector_hash": proof.digest,
            "allowed_signers_contract_hash": contract_hash,
            "signer_public_key_sha256": public_hash,
            "signer_fingerprint": fingerprint,
            "key_enrollment_digest": key_enrollment,
            "owner_gate_digest": "0" * 64,
        }
    )
    receipt, gate = registration_projection.bind_owner_gate(receipt)
    authorization = registration_installer.AuthorizedCandidate(
        receipt,
        owner_gate=gate,
        enrollment_hash="a" * 64,
        _seal=registration_installer._CANDIDATE_SEAL,
    )
    old_hash = _digest("old-bundle")
    old_pointer = registration_projection.ActiveBundlePointer(
        schema="awa-registration-active-bundle/v1",
        generation="1",
        bundle_relative_dir=f"bundles/1-{old_hash}",
        bundle_digest=old_hash,
        bundle_projection_hash=_digest("old-projection"),
        direct_receipt_hash=_digest("old-receipt"),
        external_interpreter_hash=_digest("old-interpreter"),
        interpreter_capability_hash=_digest("old-capability"),
    )
    old_dir = runtime / old_pointer.bundle_relative_dir
    old_dir.mkdir(parents=True, mode=0o700)
    (old_dir / "old").write_bytes(b"old")
    (old_dir / "old").chmod(0o600)
    runtime.chmod(0o700)
    pointer_path = runtime / "active-bundle.json"
    pointer_path.write_bytes(old_pointer.to_bytes())
    pointer_path.chmod(0o600)
    authority = registration_installer.ImmutableBundleAuthority(
        root=runtime,
        authorization=authorization,
        manifest=manifest,
        projection=projection,
        launcher_config=config,
        payloads=payloads,
        expected_denial_proof=proof,
        inventory=inventory,
        denial_requests={key: request},
        denial_runner=lambda _phase, _seam, _entry, _request: (
            output,
            2,
        ),
        old_pointer=old_pointer,
    )
    return authority, receipt, old_dir


class FakeFiles:
    def __init__(self) -> None:
        self.installed = False
        self.projected = False
        self.disabled = False
        self.old_present = True
        self.current_verified = True
        self.calls: list[str] = []
        self.proof_phases: list[str] = []

    def preflight(self) -> None:
        self.calls.append("preflight")

    def candidate_installed(self) -> bool:
        return self.installed

    def install_candidate(self) -> None:
        self.calls.append("install_candidate")
        self.installed = True

    def new_projection_active(self) -> bool:
        return self.projected

    def project_new_receiver(self) -> None:
        self.calls.append("project_new_receiver")
        if not self.installed:
            raise AssertionError("projection before candidate")
        self.projected = True

    def prove_staged(self, phase: str) -> None:
        self.calls.append(f"prove_staged:{phase}")
        self.proof_phases.append(phase)
        if phase == "PRE_SWITCH" and self.projected:
            raise AssertionError("pre-switch proof after pointer")
        if phase == "POST_SWITCH" and not self.projected:
            raise AssertionError("post-switch proof before pointer")

    def restore_old_projection(self) -> None:
        self.calls.append("restore_old_projection")
        self.projected = False
        self.disabled = False

    def old_entrypoints_disabled(self) -> bool:
        return self.disabled

    def disable_old_entrypoints(self) -> None:
        self.calls.append("disable_old_entrypoints")
        if not self.projected or not self.current_verified:
            raise AssertionError("last receiver would be disabled")
        self.prove_staged("POST_SWITCH")
        self.disabled = True

    def old_bytes_present(self) -> bool:
        return self.old_present

    def clean_old_bytes(self) -> None:
        self.calls.append("clean_old_bytes")
        if not self.current_verified:
            raise AssertionError("unverified new receiver")
        self.old_present = False

    def verify_current(self) -> None:
        self.calls.append("verify_current")
        if not self.current_verified:
            raise registration_installer.CutoverRefused(
                "new receiver is not exact"
            )


class FakeControl:
    def __init__(self) -> None:
        self.mode = "WRITABLE"
        self.staged = False
        self.new_current = False
        self.adoption_complete = False
        self.custody_empty = False
        self.calls: list[str] = []

    def protocol_state(self):
        return registration_installer.ProtocolState(
            mode=self.mode,
            staged=self.staged,
            current_is_candidate=self.new_current,
            adoption_pass_complete=self.adoption_complete,
            custody_empty=self.custody_empty,
        )

    def begin_drain(self) -> None:
        self.calls.append("begin_drain")
        self.mode = "DRAINING"

    def activate_current(self) -> None:
        self.calls.append("activate_current")
        self.mode = "WRITABLE"

    def stage_and_adopt(self) -> None:
        self.stage_candidate()
        self.reconcile_adoption()

    def stage_candidate(self) -> None:
        self.calls.append("stage_candidate")
        self.staged = True

    def reconcile_adoption(self) -> None:
        self.calls.append("reconcile_adoption")
        self.adoption_complete = True
        self.custody_empty = True

    def advance_generation(self) -> None:
        self.calls.append("advance_generation")
        self.mode = "WRITABLE"
        self.staged = False
        self.new_current = True

    def cancel_drain(self) -> None:
        self.calls.append("cancel_drain")
        self.mode = "DORMANT"
        self.staged = False
        self.adoption_complete = False
        self.custody_empty = False

    def enter_containment(self, reason: str) -> None:
        self.calls.append(f"enter_containment:{reason}")
        self.mode = "CONTAINMENT"

    def begin_repair(self) -> None:
        self.calls.append("begin_repair")
        self.mode = "DRAINING"


class CutoverMatrixTest(unittest.TestCase):
    def test_exact_c0_to_c7_order_and_idempotent_restart(self) -> None:
        files = FakeFiles()
        control = FakeControl()
        observed = []
        for expected in registration_installer.Cut:
            driver = registration_installer.CutoverDriver(files, control)
            self.assertEqual(driver.current_cut(), expected)
            observed.append(expected.value)
            if expected is not registration_installer.Cut.C7:
                driver.step()
        self.assertEqual(
            observed,
            ["C0", "C1", "C2", "C3", "C4", "C5", "C6", "C7"],
        )
        self.assertEqual(
            files.calls,
            [
                "preflight",
                "install_candidate",
                "preflight",
                "prove_staged:PRE_SWITCH",
                "preflight",
                "verify_current",
                "project_new_receiver",
                "preflight",
                "verify_current",
                "disable_old_entrypoints",
                "prove_staged:POST_SWITCH",
                "preflight",
                "preflight",
                "preflight",
                "verify_current",
                "clean_old_bytes",
            ],
        )
        self.assertEqual(
            control.calls,
            [
                "begin_drain",
                "stage_candidate",
                "reconcile_adoption",
                "advance_generation",
            ],
        )
        self.assertEqual(
            registration_installer.CutoverDriver(
                files, control
            ).step(),
            registration_installer.Cut.C7,
        )
        self.assertEqual(files.calls[-2:], ["preflight", "verify_current"])

    def test_kill_after_each_cut_resumes_from_file_and_protocol_authority(
        self,
    ) -> None:
        for crash_cut in registration_installer.Cut:
            with self.subTest(crash_cut=crash_cut):
                files = FakeFiles()
                control = FakeControl()
                while True:
                    driver = registration_installer.CutoverDriver(
                        files, control
                    )
                    current = driver.current_cut()
                    if current is crash_cut:
                        break
                    driver.step()
                # Simulate process death: retain only file and protocol
                # authorities, then construct a new driver with no journal.
                replacement = registration_installer.CutoverDriver(
                    files, control
                )
                self.assertEqual(replacement.current_cut(), crash_cut)
                self.assertFalse(hasattr(replacement, "journal"))
                self.assertEqual(
                    replacement.run_to_completion(),
                    registration_installer.Cut.C7,
                )

    def test_no_cut_disables_last_verified_receiver(self) -> None:
        files = FakeFiles()
        control = FakeControl()
        driver = registration_installer.CutoverDriver(files, control)
        driver.step()  # C0 -> C1
        driver.step()  # C1 -> C2
        files.current_verified = False
        with self.assertRaises(registration_installer.CutoverRefused):
            driver.step()
        self.assertFalse(files.disabled)
        self.assertTrue(files.old_present)

    def test_post_adoption_failure_contains_and_pre_adoption_can_cancel(
        self,
    ) -> None:
        class Recovering(FakeControl):
            def cancel_drain(self) -> None:
                self.calls.append("cancel_drain")
                self.mode = "DORMANT"
                self.staged = False

            def enter_containment(
                self, reason: str = "ADOPTION_FAILED"
            ) -> None:
                self.calls.append(f"enter_containment:{reason}")
                self.mode = "CONTAINMENT"

        files = FakeFiles()
        control = Recovering()
        driver = registration_installer.CutoverDriver(files, control)
        for _ in range(4):
            driver.step()
        self.assertEqual(driver.current_cut(), registration_installer.Cut.C4)
        driver.recover_failure(adoption_started=False)
        self.assertIn("cancel_drain", control.calls)
        self.assertEqual(
            driver.current_cut(), registration_installer.Cut.C1
        )
        self.assertEqual(
            driver.run_to_completion(), registration_installer.Cut.C7
        )
        self.assertIn("activate_current", control.calls)

        files = FakeFiles()
        files.installed = True
        files.projected = True
        files.disabled = True
        control = Recovering()
        control.mode = "DRAINING"
        control.staged = True
        driver = registration_installer.CutoverDriver(files, control)
        driver.recover_failure(adoption_started=True)
        self.assertIn("enter_containment:ADOPTION_FAILED", control.calls)
        self.assertEqual(
            driver.current_cut(), registration_installer.Cut.C4
        )
        self.assertEqual(
            driver.run_to_completion(), registration_installer.Cut.C7
        )
        self.assertIn("begin_repair", control.calls)

        files = FakeFiles()
        files.installed = True
        files.projected = True
        files.disabled = True
        control = Recovering()
        control.mode = "DRAINING"
        control.staged = True
        driver = registration_installer.CutoverDriver(files, control)
        driver.recover_failure(
            adoption_started=False,
            containment_reason="DRAIN_BOOT_CHANGED",
        )
        self.assertEqual(
            driver.current_cut(), registration_installer.Cut.C4
        )
        self.assertEqual(
            driver.run_to_completion(), registration_installer.Cut.C7
        )
        self.assertIn(
            "enter_containment:DRAIN_BOOT_CHANGED", control.calls
        )

    @unittest.skipIf(
        sqlite3.sqlite_version_info < registration_store.MIN_SQLITE_VERSION,
        "ADR 0025 requires stock SQLite >=3.51.3",
    )
    def test_real_body_a_control_adapter_owns_every_protocol_transition(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw:
            db = Path(raw) / "state/registration-v1/registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                current = harness.candidate()
                profile_root = (Path(raw).resolve() / "profile")
                profile_root.mkdir(mode=0o700)
                targets = []
                for role in ROLES:
                    path = profile_root / role
                    is_directory = (
                        role.endswith("parent")
                        or role in {"root", "git_dir", "git_common"}
                    )
                    if is_directory:
                        path.mkdir(mode=0o700)
                    else:
                        path.write_bytes(b"")
                        path.chmod(0o600)
                    targets.append(
                        (
                            role,
                            path,
                            "directory" if is_directory else "file",
                            0o700 if is_directory else 0o600,
                        )
                    )
                measured = registration_profile.ProfileBinding.measure(
                    harness.connection, targets
                )
                capability = _capability()
                external = _external_interpreter(
                    registration_profile.python_capability_hash(
                        capability
                    )
                )
                current_binding = (
                    registration_profile.CurrentProfileBinding.bind(
                        measured, capability, external
                    )
                )
                staged_binding = (
                    registration_profile.StagedProfileBinding.bind(
                        measured, capability, external
                    )
                )
                current = replace(
                    current,
                    profile_hash=current_binding.digest,
                    storage_dev=current_binding.storage_dev,
                )
                staged = replace(
                    current,
                    profile_hash=staged_binding.digest,
                    runtime_capability_hash=_digest("staged-runtime"),
                    writer_binary_hash=_digest("staged-writer"),
                    tool_inventory_hash=_digest("staged-inventory"),
                    hook_projection_hash=_digest("staged-projection"),
                    projection_receipt_hash=_digest("staged-receipt"),
                    projection_file_generation=2,
                )
                candidate_fields = {
                    "schema_hash": registration_schema.SCHEMA_SHA256,
                    "profile_hash": staged.profile_hash,
                    "runtime_capability_hash": (
                        staged.runtime_capability_hash
                    ),
                    "writer_binary_hash": staged.writer_binary_hash,
                    "writer_capability_hash": (
                        staged.writer_capability_hash
                    ),
                    "tool_inventory_hash": staged.tool_inventory_hash,
                    "hook_projection_hash": staged.hook_projection_hash,
                    "hook_matcher_mode": staged.hook_matcher_mode,
                    "hook_matcher_hash": staged.hook_matcher_hash,
                    "projection_file_generation": str(
                        staged.projection_file_generation
                    ),
                    "protocol_generation": "2",
                }
                fixed, _gate = (
                    registration_projection.fixed_authority_vector(
                        "R1_CANARY"
                    )
                )
                receipt = registration_projection.DirectReceipt.from_mapping(
                    {
                        **fixed.to_mapping(),
                        **candidate_fields,
                        "candidate_digest": (
                            registration_projection.candidate_digest(
                                candidate_fields
                            )
                        ),
                        "installer_identity_hash": (
                            staged.installer_identity_hash
                        ),
                        "installer_capability_hash": (
                            staged.installer_capability_hash
                        ),
                        "owner_gate_digest": "0" * 64,
                    }
                )
                receipt, gate = registration_projection.bind_owner_gate(
                    receipt
                )
                staged = replace(
                    staged, projection_receipt_hash=receipt.digest
                )
                authorization = registration_installer.AuthorizedCandidate(
                    receipt,
                    owner_gate=gate,
                    enrollment_hash="a" * 64,
                    _seal=registration_installer._CANDIDATE_SEAL,
                )
                control = harness.control()
                harness.store.bootstrap(control, current)
                harness.store.activate(
                    control,
                    current,
                    profile_binding=current_binding,
                )
                adapter = registration_installer.StoreControlAdapter(
                    store=harness.store,
                    control=control,
                    current=current,
                    staged=staged,
                    authorization=authorization,
                    quiescence_proof_hash="ab" * 32,
                    adopter=lambda: None,
                    current_profile_binding=current_binding,
                    staged_profile_binding=staged_binding,
                )
                files = FakeFiles()
                files.installed = True
                driver = registration_installer.CutoverDriver(
                    files, adapter
                )
                self.assertEqual(
                    driver.current_cut(), registration_installer.Cut.C1
                )
                self.assertEqual(
                    driver.run_to_completion(),
                    registration_installer.Cut.C7,
                )
                protocol = harness.store.current_protocol()
                self.assertEqual(protocol["mode"], "WRITABLE")
                self.assertEqual(protocol["protocol_generation"], 2)
                self.assertEqual(
                    protocol["runtime_capability_hash"],
                    staged.runtime_capability_hash,
                )
                self.assertEqual(
                    protocol["transition_kind"], "ADVANCE_GENERATION"
                )
                with self.assertRaises(
                    registration_installer.CutoverRefused
                ):
                    registration_installer.StoreControlAdapter(
                        store=harness.store,
                        control=control,
                        current=staged,
                        staged=replace(
                            staged,
                            hook_projection_hash="ff" * 32,
                        ),
                        authorization=authorization,
                        quiescence_proof_hash="ab" * 32,
                        adopter=lambda: None,
                        current_profile_binding=current_binding,
                        staged_profile_binding=staged_binding,
                    )


class InstallerAuthenticationTest(unittest.TestCase):
    @unittest.skipIf(
        sqlite3.sqlite_version_info < registration_store.MIN_SQLITE_VERSION,
        "ADR 0025 requires stock SQLite >=3.51.3",
    )
    def test_typed_storage_readiness_remeasures_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            db = Path(raw) / "state/registration-v1/registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                before = harness.store.table_count(
                    "registration_operation_audit"
                )
                self.assertTrue(harness.store.storage_ready())
                harness.measured_free_bytes = (
                    registration_store.FILESYSTEM_SAFETY_FLOOR - 1
                )
                self.assertFalse(harness.store.storage_ready())
                self.assertEqual(
                    harness.store.table_count(
                        "registration_operation_audit"
                    ),
                    before,
                )

    def test_external_owner_rejects_before_any_persistence_callback(self) -> None:
        calls: list[str] = []
        with self.assertRaises(registration_installer.ExternalOwnership):
            registration_installer.authenticate_installer(
                owner_mode="external",
                candidate=_candidate(),
                installer_identity=b"installer",
                installer_capability=b"capability",
                protocol_lock_receipt=b"lock",
                control_binding=b"binding",
                before_persist=lambda: calls.append("persist"),
            )
        self.assertEqual(calls, [])
        verifier_calls = []
        with self.assertRaises(registration_installer.ExternalOwnership):
            registration_installer.authorize_candidate(
                owner_mode="external",
                receipt=registration_projection.DirectReceipt.vector_r1(),
                owner_gate_bytes=b"not-read",
                owner_gate_signature_path=Path("/not/read/signature"),
                bundle_root=Path("/not/read/bundle"),
                current_enrollment_path=Path("/not/read/current"),
                expected_enrollment_hash="a" * 64,
                inventory=(),
                matcher_proof=registration_projection.MatcherProof(
                    "CATCH_ALL", None, frozenset(), False
                ),
                hook_rows=(),
            )
        self.assertEqual(verifier_calls, [])

    def test_identity_capability_and_protocol_lock_are_all_bound(self) -> None:
        candidate = _candidate()
        calls: list[str] = []
        control = registration_installer.authenticate_installer(
            owner_mode="direct",
            candidate=candidate,
            installer_identity=b"installer",
            installer_capability=b"capability",
            protocol_lock_receipt=b"lock",
            control_binding=b"binding",
            before_persist=lambda: calls.append("persist"),
        )
        self.assertEqual(calls, ["persist"])
        self.assertEqual(
            control.installer_identity_hash,
            candidate.installer_identity_hash,
        )
        self.assertEqual(
            control.installer_capability_hash,
            candidate.installer_capability_hash,
        )
        self.assertEqual(len(control.protocol_lock_receipt_hash), 64)
        for field, replacement in (
            ("installer_identity", b"wrong"),
            ("installer_capability", b"wrong"),
            ("protocol_lock_receipt", b""),
        ):
            values = {
                "installer_identity": b"installer",
                "installer_capability": b"capability",
                "protocol_lock_receipt": b"lock",
            }
            values[field] = replacement
            with self.subTest(field=field):
                with self.assertRaises(
                    (registration_store.AuthorizationError, ValueError)
                ):
                    registration_installer.authenticate_installer(
                        owner_mode="direct",
                        candidate=candidate,
                        control_binding=b"binding",
                        **values,
                    )

    def test_protocol_lock_receipt_comes_from_verified_lock_object(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            manager = registration_lock.LockManager(
                Path(raw) / "locks"
            )
            control = registration_installer.authenticate_with_protocol_lock(
                owner_mode="direct",
                candidate=_candidate(),
                installer_identity=b"installer",
                installer_capability=b"capability",
                control_binding=b"binding",
                locks=manager,
            )
            self.assertEqual(len(control.protocol_lock_receipt_hash), 64)
            self.assertTrue((Path(raw) / "locks/protocol.lock").is_file())

    def test_body_c_contains_no_sql_or_direct_relation_mutator(self) -> None:
        source = inspect.getsource(registration_installer)
        self.assertNotIn("sqlite3", source)
        self.assertNotIn("registration_protocol_epoch", source)
        self.assertNotIn("registration_member", source)
        self.assertNotIn("INSERT ", source)
        self.assertNotIn("UPDATE ", source)
        self.assertNotIn("DELETE ", source)


class AtomicReceiptTest(unittest.TestCase):
    def test_private_atomic_receipt_round_trip_and_corruption_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "registration" / "direct-receipt.json"
            store = registration_installer.DirectReceiptStore(path)
            receipt = registration_projection.DirectReceipt(
                **{
                    **registration_projection.DirectReceipt.vector_r1()
                    .to_mapping(),
                    "canonical_root_hash": "dd" * 32,
                    "member_id": "ee" * 32,
                }
            )
            store.write(receipt)
            self.assertEqual(store.read(), receipt)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
            path.write_bytes(b'{"schema":')
            with self.assertRaises(registration_installer.ReceiptUnavailable):
                store.read()

    def test_real_file_authority_is_atomic_restartable_and_disables_old(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw:
            authority, receipt, old_dir = _immutable_authority(Path(raw))
            # A known partial generation is resumable, while its exact bytes
            # remain immutable.
            authority.bundle_dir.mkdir(parents=True, mode=0o700)
            first = authority.manifest.entries[0]
            registration_installer._write_immutable_file(
                authority.bundle_dir / first.path,
                authority.payloads[first.path],
                int(first.mode),
            )
            self.assertFalse(authority.candidate_installed())
            driver = registration_installer.CutoverDriver(
                authority, FakeControl()
            )
            self.assertEqual(driver.step(), registration_installer.Cut.C1)
            self.assertTrue(authority.candidate_installed())
            self.assertTrue(old_dir.exists())
            restarted = registration_installer.CutoverDriver(
                authority, driver.control
            )
            for expected in (
                registration_installer.Cut.C1,
                registration_installer.Cut.C2,
                registration_installer.Cut.C3,
                registration_installer.Cut.C4,
                registration_installer.Cut.C5,
                registration_installer.Cut.C6,
            ):
                self.assertEqual(restarted.current_cut(), expected)
                restarted.step()
                if expected is not registration_installer.Cut.C6:
                    self.assertTrue(old_dir.exists())
            self.assertEqual(
                restarted.current_cut(), registration_installer.Cut.C7
            )
            self.assertFalse(old_dir.exists())
            self.assertEqual(
                authority._read_pointer(), authority.candidate_pointer
            )
            installed = registration_projection.DirectReceipt.from_bytes(
                (
                    authority.bundle_dir / "direct-receipt.json"
                ).read_bytes()
            )
            self.assertEqual(installed, receipt)
        return
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "candidate-source"
            candidate_bytes = b"#!/bin/sh\nexit 0\n"
            source.write_bytes(candidate_bytes)
            source.chmod(0o700)
            inventory = (
                registration_projection.InventoryEntry(
                    "preToolUse", "", "Delete", "ordinary",
                    "cursor-permission/v1"
                ),
                registration_projection.InventoryEntry(
                    "preToolUse", "", "Grep", "ordinary",
                    "cursor-permission/v1"
                ),
                registration_projection.InventoryEntry(
                    "preToolUse", "", "MCP:awa_status", "ordinary",
                    "cursor-permission/v1"
                ),
                registration_projection.InventoryEntry(
                    "preToolUse", "", "Read", "ordinary",
                    "cursor-permission/v1"
                ),
                registration_projection.InventoryEntry(
                    "preToolUse", "", "Shell", "ordinary",
                    "cursor-permission/v1"
                ),
                registration_projection.InventoryEntry(
                    "preToolUse", "", "Task", "task_launch",
                    "cursor-permission/v1"
                ),
                registration_projection.InventoryEntry(
                    "preToolUse", "", "Write", "ordinary",
                    "cursor-permission/v1"
                ),
                registration_projection.InventoryEntry(
                    "subagentStart", "", "Task", "task_launch",
                    "cursor-subagent/v1"
                ),
            )
            proof = registration_projection.MatcherProof(
                "CATCH_ALL",
                "fa" * 32,
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
            matcher_hash = registration_projection.matcher_proof_hash(
                proof
            )
            inventory_hash = (
                registration_projection.tool_inventory_hash(inventory)
            )
            hook_rows = (
                registration_projection.HookRow(
                    "preToolUse",
                    "*",
                    (str(root / "stable-admission"),),
                    20_000,
                    False,
                ),
                registration_projection.HookRow(
                    "subagentStart",
                    "*",
                    (str(root / "stable-admission"),),
                    20_000,
                    False,
                ),
                registration_projection.HookRow(
                    "sessionStart",
                    "",
                    (str(root / "stable-startup"),),
                    5_000,
                    False,
                ),
            )
            projection_hash = (
                registration_projection.hook_projection_hash(
                    hook_rows,
                    matcher_mode="CATCH_ALL",
                    matcher_hash=matcher_hash,
                    inventory_hash=inventory_hash,
                    file_generation="1",
                    protocol_generation="1",
                    wrapper_runtime_hash="bb" * 32,
                )
            )
            candidate_fields = {
                field: (
                    registration_projection.DirectReceipt.vector_r1()
                    .to_mapping()[field]
                )
                for field in registration_projection.CANDIDATE_FIELDS
            }
            candidate_fields.update(
                {
                    "tool_inventory_hash": inventory_hash,
                    "hook_projection_hash": projection_hash,
                    "hook_matcher_mode": "CATCH_ALL",
                    "hook_matcher_hash": matcher_hash,
                }
            )
            candidate_digest = (
                registration_projection.candidate_digest(candidate_fields)
            )
            gate = registration_projection.OwnerGate(
                schema="awa-registration-owner-gate/v1",
                repository="KleinPerkins/awa",
                authorized_by="KleinPerkins",
                deployment_scope="R1_CANARY",
                candidate_digest=candidate_digest,
                canonical_root_hash="dd" * 32,
                member_id="ee" * 32,
                authorized=True,
            )
            gate_bytes = gate.to_bytes()
            signature = b"fixture-owner-signature"
            gate_digest = (
                registration_projection.verified_owner_gate_digest(
                    gate_bytes,
                    signature,
                    verifier=lambda payload, signed: (
                        payload == gate_bytes and signed == signature
                    ),
                )
            )
            receipt = registration_projection.DirectReceipt.from_mapping(
                {
                    **registration_projection.DirectReceipt.vector_r1()
                    .to_mapping(),
                    **candidate_fields,
                    "candidate_digest": candidate_digest,
                    "installed_file_hash": (
                        registration_projection.installed_file_hash(source)
                    ),
                    "owner_gate_digest": gate_digest,
                }
            )
            authorization = registration_installer.authorize_candidate(
                owner_mode="direct",
                receipt=receipt,
                owner_gate_bytes=gate_bytes,
                owner_gate_signature=signature,
                owner_gate_verifier=lambda payload, signed: (
                    payload == gate_bytes and signed == signature
                ),
                inventory=inventory,
                matcher_proof=proof,
                hook_rows=hook_rows,
            )
            files = registration_installer.RuntimeFileAuthority(
                root=root / "install",
                authorization=authorization,
                candidate_bytes=candidate_bytes,
            )
            files.seed_old_receiver(b"#!/bin/sh\nexit 1\n")
            control = FakeControl()
            driver = registration_installer.CutoverDriver(files, control)
            self.assertEqual(driver.step(), registration_installer.Cut.C1)
            self.assertEqual(driver.step(), registration_installer.Cut.C2)
            restarted = registration_installer.RuntimeFileAuthority(
                root=root / "install",
                authorization=authorization,
                candidate_bytes=candidate_bytes,
            )
            self.assertEqual(
                registration_installer.CutoverDriver(
                    restarted, control
                ).current_cut(),
                registration_installer.Cut.C2,
            )
            self.assertEqual(
                registration_installer.CutoverDriver(
                    restarted, control
                ).run_to_completion(),
                registration_installer.Cut.C7,
            )
            self.assertTrue(restarted.candidate_path.is_file())
            self.assertFalse(restarted.old_receiver_path.exists())
            self.assertFalse(restarted.disabled_old_path.exists())
            projection = json.loads(
                restarted.projection_path.read_text(encoding="utf-8")
            )
            self.assertEqual(
                projection["candidate_digest"], receipt.candidate_digest
            )


if __name__ == "__main__":
    unittest.main()
