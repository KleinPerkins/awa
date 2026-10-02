from __future__ import annotations

import os
import platform
import sqlite3
import tempfile
import unittest
import hashlib
from pathlib import Path

from engine import registration_profile, registration_store


H = "aa" * 32
ROLES = (
    "state_parent",
    "db",
    "wal",
    "shm",
    "proof_parent",
    "projection_parent",
    "legacy_parent",
    "root",
    "git_dir",
    "git_common",
)


def _descriptor_records() -> list[dict]:
    return [
        {
            "ordinal": str(ordinal),
            "role": role,
            "component_hash": H,
            "st_dev": "1",
            "st_ino": "1",
            "st_mode": "1",
            "st_uid": "1",
            "st_gid": "1",
            "st_nlink": "1",
            "fd_flags": "1",
            "nofollow": True,
            "fstype": "apfs",
            "fsid_0": "-1",
            "fsid_1": "1",
            "mount_flags": "1",
        }
        for ordinal, role in enumerate(ROLES)
    ]


def _profile(descriptor_hash: str) -> dict:
    return {
        "schema": "awa-registration-profile/v2",
        "measurement_order": list(registration_profile.MEASUREMENT_ORDER),
        "platform": "darwin",
        "os_build": "fixture",
        "apfs_fstype": "apfs",
        "apfs_fsid_0": "-1",
        "apfs_fsid_1": "1",
        "apfs_mount_flags": "1",
        "sqlite_runtime_version": "3.51.3",
        "sqlite_source_id": "fixture",
        "sqlite_compile_options_hash": H,
        "sqlite_vfs_name": "unix",
        "journal_mode": "wal",
        "synchronous": "full",
        "fullfsync": True,
        "checkpoint_fullfsync": True,
        "foreign_keys": True,
        "defensive": True,
        "trusted_schema": False,
        "locking_mode": "normal",
        "nofollow_available": True,
        "checkpoint_on_close": False,
        "state_parent_dev": "1",
        "db_dev": "1",
        "wal_dev": "1",
        "shm_dev": "1",
        "proof_parent_dev": "1",
        "projection_parent_dev": "1",
        "legacy_parent_dev": "1",
        "root_dev": "1",
        "git_dir_dev": "1",
        "git_common_dev": "1",
        "ancestry_hash": H,
        "descriptor_binding_hash": descriptor_hash,
    }


def _capability() -> dict:
    return {
        "schema": "awa-registration-python-capability/v1",
        "platform": "darwin",
        "os_build": "fixture",
        "python_implementation": "CPython",
        "python_version": "3.14.6",
        "required_python_apis": list(registration_profile.REQUIRED_PYTHON_APIS),
        "sqlite_runtime_version": "3.53.3",
        "sqlite_source_id": "fixture-source-id",
        "sqlite_compile_options_hash": (
            "b320250f51085d00daadd152978a2023a9bbd59d647976d91d3696372515f0dd"
        ),
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
        "probe_program_hash": "f" * 64,
    }


def _external_interpreter(capability_hash: str) -> dict:
    return {
        "schema": "awa-registration-external-interpreter/v1",
        "selection_hash": (
            "bb1b13000040b1cbbe3f2c8b047ecbf6d5866ac7de73fa53b12d75e68c9b3211"
        ),
        "path": "/fixture/python/bin/python3.14",
        "path_hash": (
            "a0caf9d8b6c5a2649358e0dc2d9ce4c9d75a3065496c6a50008bed580520ffdd"
        ),
        "ancestry_hash": (
            "975c44feaf12545fbd1f9c0a091e0701acc2f580ba02a31e31eb205dca53e825"
        ),
        "st_uid": "501",
        "st_gid": "20",
        "st_mode": "33261",
        "st_dev": "1",
        "st_ino": "2",
        "st_nlink": "1",
        "st_size": "3",
        "content_sha256": "b" * 64,
        "capability_probe_hash": capability_hash,
        "probe_program_hash": "f" * 64,
    }


class RegistrationProfileVectorTest(unittest.TestCase):
    def test_a03_published_vectors(self) -> None:
        records = _descriptor_records()
        descriptor_hash = registration_profile.descriptor_binding_hash(records)
        self.assertEqual(
            descriptor_hash,
            "300bd90ff7f86774d939835c8d410f0b25e817c47881391fae95327610241e71",
        )
        self.assertEqual(
            registration_profile.profile_hash(_profile(descriptor_hash)),
            "3d6c52ff2aaa14f64a2793586c2703c7c6edcfc25033a448503e5d3ea8e539a7",
        )
        records[1]["st_ino"] = "2"
        self.assertEqual(
            registration_profile.descriptor_binding_hash(records),
            "bb26b2b3a2f69b3f826410f910c1b0920302abdd1d85962739c372fd433db3bf",
        )

    def test_vector_rejects_unknown_field_order_and_encoding(self) -> None:
        records = _descriptor_records()
        mutations = [
            [*reversed(records)],
            [{**records[0], "unknown": "1"}, *records[1:]],
            [{**records[0], "ordinal": 0}, *records[1:]],
            [{**records[0], "st_dev": "+1"}, *records[1:]],
            [{**records[0], "nofollow": "true"}, *records[1:]],
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation[0]):
                with self.assertRaises(registration_profile.ProfileError):
                    registration_profile.descriptor_binding_hash(mutation)

    def test_interpreter_capability_supported_and_rejected_vectors(self) -> None:
        capability = _capability()
        self.assertEqual(
            registration_profile.python_capability_hash(capability),
            "ca675a27a71e6ff366a59c943ab17e47d02e8f560cd3c2cc00f213424747c9f6",
        )
        validated = registration_profile.validate_python_capability(capability)
        external = _external_interpreter(validated.digest)
        self.assertEqual(
            registration_profile.external_interpreter_hash(
                external, capability=validated
            ),
            "7b7032befe3cb79573811d97763cb8dddec67f0147a98fb99c9f912b2a3154b2",
        )
        rejected = {
            **capability,
            "python_version": "3.9.6",
            "sqlite_runtime_version": "3.51.0",
            "connection_setconfig_available": False,
            "sqlite_dbconfig_defensive_available": False,
            "defensive": False,
        }
        self.assertEqual(
            registration_profile.python_capability_hash(rejected),
            "825d7068ff8d6c2f5a73052054de1cf58f5e49cff809b609223aae80d7ec25f3",
        )
        with self.assertRaises(registration_profile.ProfileError):
            registration_profile.validate_python_capability(rejected)
        for field in (
            "connection_setconfig_available",
            "sqlite_dbconfig_defensive_available",
            "defensive",
        ):
            mutated = {**capability, field: 1}
            with self.subTest(field=field), self.assertRaises(
                registration_profile.ProfileError
            ):
                registration_profile.python_capability_hash(mutated)

    def test_typed_current_staged_and_r0_bindings_reject_role_input_swaps(self) -> None:
        descriptor_hash = registration_profile.descriptor_binding_hash(
            _descriptor_records()
        )
        profile_object = _profile(descriptor_hash)
        targets = tuple(
            (
                role,
                Path(f"/fixture/{role}"),
                (
                    "directory"
                    if role.endswith("parent")
                    or role in {"root", "git_dir", "git_common"}
                    else "file"
                ),
                (
                    0o700
                    if role.endswith("parent")
                    or role in {"root", "git_dir", "git_common"}
                    else 0o600
                ),
            )
            for role in ROLES
        )
        with self.assertRaises(registration_profile.ProfileError):
            registration_profile.ProfileBinding(
                targets=targets,
                descriptor_digest=descriptor_hash,
                profile_object=profile_object,
                digest=registration_profile.profile_hash(profile_object),
                storage_dev=1,
                _seal=object(),
            )
        with self.assertRaises(registration_profile.ProfileError):
            registration_profile.ProfileBinding(
                targets=targets,
                descriptor_digest=descriptor_hash,
                profile_object=profile_object,
                digest=registration_profile.profile_hash(profile_object),
                storage_dev=True,
                _seal=registration_profile._PROFILE_BINDING_SEAL,
            )
        profile = registration_profile.ProfileBinding(
            targets=targets,
            descriptor_digest=descriptor_hash,
            profile_object=profile_object,
            digest=registration_profile.profile_hash(profile_object),
            storage_dev=1,
            _seal=registration_profile._PROFILE_BINDING_SEAL,
        )
        capability = _capability()
        capability_hash = registration_profile.python_capability_hash(capability)
        external = _external_interpreter(capability_hash)
        bindings = (
            registration_profile.CurrentProfileBinding.bind(
                profile, capability, external
            ),
            registration_profile.StagedProfileBinding.bind(
                profile, capability, external
            ),
            registration_profile.R0ProfileBinding.bind(
                profile, capability, external
            ),
        )
        self.assertEqual(
            tuple(binding.role for binding in bindings),
            ("CURRENT", "STAGED", "R0"),
        )
        self.assertEqual(len({type(binding) for binding in bindings}), 3)
        promoted = registration_profile.CurrentProfileBinding.promote(
            bindings[1]
        )
        self.assertIs(type(promoted), registration_profile.CurrentProfileBinding)
        self.assertIs(promoted.profile, bindings[1].profile)
        self.assertEqual(
            promoted.capability_bytes, bindings[1].capability_bytes
        )
        self.assertEqual(
            promoted.external_interpreter_bytes,
            bindings[1].external_interpreter_bytes,
        )
        with self.assertRaises(registration_profile.ProfileError):
            registration_profile.CurrentProfileBinding.promote(bindings[0])
        connection = sqlite3.connect(":memory:")
        self.addCleanup(connection.close)
        with self.assertRaises(registration_profile.ProfileError):
            bindings[0].recheck(
                connection,
                {**capability, "os_build": "swapped"},
                external,
            )
        with self.assertRaises(registration_profile.ProfileError):
            bindings[1].recheck(
                connection,
                capability,
                {**external, "st_ino": "3"},
            )
        with self.assertRaises(registration_profile.ProfileError):
            registration_profile.R0ProfileBinding.bind(
                profile,
                capability,
                {**external, "capability_probe_hash": "0" * 64},
            )


@unittest.skipUnless(platform.system() == "Darwin", "M1 supports macOS/APFS only")
class RegistrationSecureDescriptorTest(unittest.TestCase):
    def test_secure_walk_rejects_links_modes_and_object_swap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            good = base / "private"
            good.mkdir(mode=0o700)
            target = good / "target"
            target.write_bytes(b"x")
            target.chmod(0o600)

            with registration_profile.bind_secure_path(
                target, kind="file", required_mode=0o600
            ) as bound:
                registration_profile.recheck_bound_path(bound)
                replacement = good / "replacement"
                replacement.write_bytes(b"y")
                replacement.chmod(0o600)
                os.replace(replacement, target)
                with self.assertRaises(registration_profile.ProfileError):
                    registration_profile.recheck_bound_path(bound)

            link = good / "link"
            link.symlink_to(target)
            with self.assertRaises(registration_profile.ProfileError):
                with registration_profile.bind_secure_path(
                    link, kind="file", required_mode=0o600
                ):
                    pass

            target.chmod(0o660)
            with self.assertRaises(registration_profile.ProfileError):
                with registration_profile.bind_secure_path(
                    target, kind="file", required_mode=0o600
                ):
                    pass

            target.chmod(0o600)
            alias = good / "alias"
            os.link(target, alias)
            with self.assertRaises(registration_profile.ProfileError):
                with registration_profile.bind_secure_path(
                    target, kind="file", required_mode=0o600
                ):
                    pass

    def test_descriptor_measurement_is_apfs_and_same_device(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            paths = []
            for name in ROLES:
                path = root / name
                if name.endswith("parent") or name in {"root", "git_dir", "git_common"}:
                    path.mkdir(mode=0o700)
                    kind = "directory"
                    mode = 0o700
                else:
                    path.write_bytes(b"")
                    path.chmod(0o600)
                    kind = "file"
                    mode = 0o600
                paths.append((name, path, kind, mode))
            measurement = registration_profile.measure_bound_targets(paths)
            self.assertEqual(measurement.fstype, "apfs")
            self.assertEqual(len({record["st_dev"] for record in measurement.records}), 1)
            self.assertEqual(
                len({(record["fsid_0"], record["fsid_1"]) for record in measurement.records}),
                1,
            )

    def test_supported_store_rechecks_complete_profile_before_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            state = root / "registration-v1"
            state.mkdir(mode=0o700)
            dirs = {}
            for role in (
                "proof_parent",
                "projection_parent",
                "legacy_parent",
                "root",
                "git_dir",
                "git_common",
            ):
                path = root / role
                path.mkdir(mode=0o700)
                dirs[role] = path
            db = state / "registration.db"
            targets = [
                ("state_parent", state, "directory", 0o700),
                ("db", db, "file", 0o600),
                ("wal", Path(f"{db}-wal"), "file", 0o600),
                ("shm", Path(f"{db}-shm"), "file", 0o600),
                ("proof_parent", dirs["proof_parent"], "directory", 0o700),
                (
                    "projection_parent",
                    dirs["projection_parent"],
                    "directory",
                    0o700,
                ),
                ("legacy_parent", dirs["legacy_parent"], "directory", 0o700),
                ("root", dirs["root"], "directory", 0o700),
                ("git_dir", dirs["git_dir"], "directory", 0o700),
                ("git_common", dirs["git_common"], "directory", 0o700),
            ]
            with self.assertRaises(registration_store.AuthorizationError):
                registration_store.RegistrationStore(
                    db, profile_targets=targets
                )
            self.assertFalse(db.exists())
            digest = lambda value: hashlib.sha256(value.encode()).hexdigest()
            identity = b"installer-id"
            capability = b"installer-cap"
            identity_hash = hashlib.sha256(
                b"awa-registration-installer-identity/v1\0" + identity
            ).hexdigest()
            capability_hash = hashlib.sha256(
                b"awa-registration-installer-capability/v1\0" + capability
            ).hexdigest()
            control = registration_store.authenticate_control(
                installer_identity=identity,
                installer_capability=capability,
                protocol_lock_receipt=b"lock",
                control_binding=b"binding",
                expected_identity_hash=identity_hash,
                expected_capability_hash=capability_hash,
            )
            with registration_store.RegistrationStore.create_supported(
                db, profile_targets=targets, control=control
            ) as store:
                self.assertIsNotNone(store.measured_profile_hash)
                self.assertIsNotNone(store.measured_storage_dev)
                candidate = registration_store.ProtocolCandidate(
                    profile_hash=str(store.measured_profile_hash),
                    runtime_capability_hash=digest("runtime"),
                    writer_binary_hash=digest("writer"),
                    writer_capability_hash=digest("writer-cap"),
                    tool_inventory_hash=digest("tools"),
                    hook_projection_hash=digest("projection"),
                    hook_matcher_mode="ENUMERATED",
                    hook_matcher_hash=digest("matcher"),
                    projection_receipt_hash=digest("receipt"),
                    projection_file_generation=1,
                    installer_identity_hash=identity_hash,
                    installer_capability_hash=capability_hash,
                    storage_dev=int(store.measured_storage_dev),
                )
                result = store.bootstrap(control, candidate)
                self.assertEqual(result.disposition, "COMMITTED")
                before = store.table_count("registration_operation_audit")
                capability_object = _capability()
                external_interpreter = _external_interpreter(
                    registration_profile.python_capability_hash(
                        capability_object
                    )
                )
                typed_bindings = (
                    registration_profile.CurrentProfileBinding.bind(
                        store._profile_binding,
                        capability_object,
                        external_interpreter,
                    ),
                    registration_profile.StagedProfileBinding.bind(
                        store._profile_binding,
                        capability_object,
                        external_interpreter,
                    ),
                    registration_profile.R0ProfileBinding.bind(
                        store._profile_binding,
                        capability_object,
                        external_interpreter,
                    ),
                )
                dirs["proof_parent"].rename(root / "old-proof-parent")
                dirs["proof_parent"].mkdir(mode=0o700)
                for binding in typed_bindings:
                    with self.subTest(role=binding.role), self.assertRaises(
                        registration_profile.ProfileError
                    ):
                        binding.recheck(
                            store._connection,
                            capability_object,
                            external_interpreter,
                        )
                with self.assertRaises(registration_profile.ProfileError):
                    store.activate(control, candidate)
                self.assertEqual(
                    store.table_count("registration_operation_audit"), before
                )
            with self.assertRaises(registration_profile.ProfileError):
                registration_store.RegistrationStore(
                    db, profile_targets=targets
                )


if __name__ == "__main__":
    unittest.main()
