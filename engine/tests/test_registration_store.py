from __future__ import annotations

import multiprocessing
import os
import pickle
import sqlite3
import tempfile
import threading
import unittest
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from unittest import mock

from engine import (
    registration_executor,
    registration_hashes,
    registration_lock,
    registration_profile,
    registration_store,
)
from engine.tests.registration_harness import RegistrationHarness


def _member_id(identity: registration_store.MemberIdentity) -> str:
    return registration_hashes.deterministic_id(
        "awa-reg-member-v1",
        identity.canonical_root,
        str(identity.root_dev),
        str(identity.root_ino),
        identity.git_dir,
        str(identity.git_dir_dev),
        str(identity.git_dir_ino),
        identity.git_common_dir,
        str(identity.git_common_dev),
        str(identity.git_common_ino),
    )


def _fresh_basis(
    harness: RegistrationHarness, ordinal: int
) -> registration_store.FreshMemberBasis:
    base = harness.identity(ordinal=1)
    observed = harness.identity(ordinal=ordinal)
    identity = replace(
        base,
        physical_basis_hash=observed.physical_basis_hash,
        git_basis_hash=observed.git_basis_hash,
        policy_basis_hash=observed.policy_basis_hash,
        operation_basis_hash=observed.operation_basis_hash,
        lifecycle_basis_hash=observed.lifecycle_basis_hash,
        current_basis_hash=observed.current_basis_hash,
    )
    return registration_store.FreshMemberBasis(
        identity=identity,
        intent=harness.clean_intent(ordinal=ordinal),
        workspace_roots_hash="ab" * 32,
    )


def _install_member(
    harness: RegistrationHarness,
    ordinal: int,
    *,
    sample_boot_id: str,
) -> tuple[
    registration_store.MemberIdentity,
    registration_store.EffectIntent,
    registration_store.OperationResult,
]:
    identity = harness.identity(ordinal=ordinal)
    intent = harness.clean_intent(ordinal=ordinal)
    previous_boot = harness.sample_boot_id
    harness.sample_boot_id = sample_boot_id
    try:
        result = harness.store.install_member(
            harness.data(),
            harness.candidate(),
            identity,
            intent,
            operation_id=f"{(1 << 255) + ordinal:064x}",
        )
    finally:
        harness.sample_boot_id = previous_boot
    return identity, intent, result


def _scope_install_process(
    db_path: str,
    shared_ordinal,
    attempting,
    provider_entered,
    release_provider,
    initial_ordinal: int,
    operation_id: str,
    results,
) -> None:
    try:
        with RegistrationHarness.open(
            Path(db_path), measured_free_bytes=2 * 1024**3
        ) as harness:
            member_id = _member_id(harness.identity())
            attempting.set()
            with harness.store.member_mutation_scope(member_id) as scope:

                def provider() -> registration_store.FreshMemberBasis:
                    provider_entered.set()
                    if release_provider is not None and not release_provider.wait(5):
                        raise RuntimeError("provider release timed out")
                    return _fresh_basis(harness, int(shared_ordinal.value))

                basis = scope.collect_fresh_basis(provider)
                result = scope.install_member(
                    harness.data(),
                    harness.candidate(),
                    basis,
                    operation_id=operation_id,
                )
                results.put(
                    (
                        "ok",
                        result.disposition,
                        result.operation_id,
                        result.target_hash,
                        initial_ordinal,
                        basis.identity.current_basis_hash,
                    )
                )
    except BaseException as error:
        results.put(("error", type(error).__name__, str(error)))


def _typed_profile_pair() -> tuple[
    registration_profile.CurrentProfileBinding,
    registration_profile.StagedProfileBinding,
]:
    from engine.tests.test_registration_profile import (
        ROLES,
        _capability,
        _descriptor_records,
        _external_interpreter,
        _profile,
    )

    descriptor_hash = registration_profile.descriptor_binding_hash(
        _descriptor_records()
    )
    profile_object = _profile(descriptor_hash)
    measured = registration_profile.ProfileBinding(
        targets=tuple(
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
        ),
        descriptor_digest=descriptor_hash,
        profile_object=profile_object,
        digest=registration_profile.profile_hash(profile_object),
        storage_dev=1,
        _seal=registration_profile._PROFILE_BINDING_SEAL,
    )
    capability = _capability()
    external = _external_interpreter(
        registration_profile.python_capability_hash(capability)
    )
    return (
        registration_profile.CurrentProfileBinding.bind(
            measured, capability, external
        ),
        registration_profile.StagedProfileBinding.bind(
            measured, capability, external
        ),
    )


@unittest.skipUnless(
    sqlite3.sqlite_version_info >= registration_store.MIN_SQLITE_VERSION,
    "ADR 0025 requires stock SQLite >=3.51.3",
)
class RegistrationStoreBootstrapTest(unittest.TestCase):
    @staticmethod
    def _drop_all_registration_triggers(
        connection: sqlite3.Connection,
    ) -> None:
        for (trigger,) in connection.execute(
            "SELECT name FROM sqlite_schema WHERE type='trigger'"
        ).fetchall():
            connection.execute(
                'DROP TRIGGER "' + trigger.replace('"', '""') + '"'
            )

    @staticmethod
    def _rewrite_operation_and_backlinks(
        connection: sqlite3.Connection,
        operation_id: str,
        **changes: object,
    ) -> str:
        connection.row_factory = sqlite3.Row
        operation = dict(
            connection.execute(
                "SELECT * FROM registration_operation_audit "
                "WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
        )
        operation.update(changes)
        operation_hash = registration_hashes.derive(
            "operation_envelope_hash", operation
        )
        assignments = [f"{column}=?" for column in changes]
        assignments.append("operation_envelope_hash=?")
        connection.execute(
            "UPDATE registration_operation_audit SET "
            + ",".join(assignments)
            + " WHERE operation_id=?",
            (*changes.values(), operation_hash, operation_id),
        )
        for table, operation_column, hash_column in (
            (
                "registration_member",
                "write_operation_id",
                "write_operation_hash",
            ),
            (
                "registration_runtime_status",
                "write_operation_id",
                "write_operation_hash",
            ),
            (
                "registration_episode",
                "write_operation_id",
                "write_operation_hash",
            ),
            (
                "registration_effect_action",
                "write_operation_id",
                "write_operation_hash",
            ),
            (
                "registration_effect",
                "created_operation_id",
                "created_operation_hash",
            ),
            (
                "registration_effect",
                "outcome_operation_id",
                "outcome_operation_hash",
            ),
        ):
            connection.execute(
                f"UPDATE {table} SET {hash_column}=? "
                f"WHERE {operation_column}=?",
                (operation_hash, operation_id),
            )
        return operation_hash

    @classmethod
    def _rewrite_latest_protocol(
        cls,
        connection: sqlite3.Connection,
        **changes: object,
    ) -> str:
        connection.row_factory = sqlite3.Row
        protocol = dict(
            connection.execute(
                "SELECT * FROM registration_protocol_epoch "
                "ORDER BY protocol_seq DESC LIMIT 1"
            ).fetchone()
        )
        protocol.update(changes)
        protocol_hash = registration_hashes.derive(
            "protocol_hash", protocol
        )
        assignments = [f"{column}=?" for column in changes]
        assignments.append("protocol_hash=?")
        connection.execute(
            "UPDATE registration_protocol_epoch SET "
            + ",".join(assignments)
            + " WHERE protocol_seq=?",
            (
                *changes.values(),
                protocol_hash,
                protocol["protocol_seq"],
            ),
        )
        cls._rewrite_operation_and_backlinks(
            connection,
            protocol["operation_id"],
            target_protocol_hash=protocol_hash,
        )
        return protocol_hash

    def test_every_operation_has_nonzero_bounded_projection(self) -> None:
        self.assertEqual(
            registration_store.PROJECTED_DB_BYTES,
            {
                "BOOTSTRAP": 1_048_576,
                "INSTALL_MEMBER": 32_768,
                "BIND_EPISODE": 8_192,
                "REACQUIRE_EFFECT": 8_192,
                "OPEN_EFFECT": 16_384,
                "APPEND_ACTION": 8_192,
                "CLOSE_SUCCESS": 16_384,
                "CLOSE_CONFLICT": 16_384,
                "INVALIDATE_REQUESTED": 32_768,
                "SET_PENDING": 24_576,
                "REPLACE_PENDING": 32_768,
                "HANDOFF_RESOLVED": 32_768,
                "MARK_UNAVAILABLE": 8_192,
                "REBOOT_STATUS": 8_192,
                "SCHEDULE_STATUS": 8_192,
                "ACTIVATE": 16_384,
                "BEGIN_DRAIN": 16_384,
                "STAGE_NEXT": 16_384,
                "CANCEL_DRAIN": 16_384,
                "ADOPT_EFFECT": 65_536,
                "ADVANCE_GENERATION": 16_384,
                "PRE_EFFECT_DORMANT": 16_384,
                "ENTER_CONTAINMENT": 16_384,
                "BEGIN_REPAIR": 16_384,
            },
        )

    def test_reservation_floors_and_boolean_integer_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            harness = RegistrationHarness.open(
                Path(tmp) / "state" / "registration-v1" / "registration.db",
                measured_free_bytes=2 * 1024**3,
            )
            self.addCleanup(harness.close)
            intent = harness.clean_intent()
            self.assertEqual(intent.outcome_reservation_bytes, 98_304)
            self.assertEqual(intent.successor_reservation_bytes, 32_768)
            for mutation in (
                {"outcome_reservation_bytes": 98_303},
                {"successor_reservation_bytes": 32_767},
                {"external_growth_reservation_bytes": True},
                {"outcome_reservation_bytes": True},
                {"successor_reservation_bytes": False},
            ):
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    replace(intent, **mutation)
            candidate = harness.candidate()
            for mutation in (
                {"projection_file_generation": True},
                {"storage_dev": False},
            ):
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    replace(candidate, **mutation)
            identity = harness.identity()
            for field in (
                "root_dev",
                "root_ino",
                "git_dir_dev",
                "git_dir_ino",
                "git_common_dev",
                "git_common_ino",
                "proof_dev",
                "projection_dev",
                "legacy_state_dev",
            ):
                with self.subTest(field=field), self.assertRaises(ValueError):
                    replace(identity, **{field: True})

    def test_boolean_operation_integers_reject_before_durable_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                control = harness.control()
                data = harness.data()
                candidate = harness.candidate()

                def rejects_without_write(call: Callable[[], object]) -> None:
                    before = store.table_count(
                        "registration_operation_audit"
                    )
                    with self.assertRaises(ValueError):
                        call()
                    self.assertEqual(
                        store.table_count("registration_operation_audit"),
                        before,
                    )

                rejects_without_write(
                    lambda: store.bootstrap(
                        control,
                        candidate,
                        projected_db_growth_bytes=False,
                    )
                )
                store.bootstrap(control, candidate)
                rejects_without_write(
                    lambda: store.activate(
                        control,
                        candidate,
                        projected_db_growth_bytes=True,
                    )
                )
                store.activate(control, candidate)
                rejects_without_write(
                    lambda: store.install_member(
                        data,
                        candidate,
                        harness.identity(),
                        harness.clean_intent(),
                        sample_boot_id="boot-a",
                        sample_mono_ns=True,
                    )
                )
                rejects_without_write(
                    lambda: store.install_member(
                        data,
                        candidate,
                        harness.identity(),
                        harness.clean_intent(),
                        sample_boot_id="boot-a",
                        sample_mono_ns=1,
                        projected_db_growth_bytes=False,
                    )
                )
                store.install_member(
                    data,
                    candidate,
                    harness.identity(),
                    harness.clean_intent(),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )

                member_id = harness.connection.execute(
                    "SELECT member_id FROM registration_member"
                ).fetchone()[0]
                authority = store.read_selected_authority(member_id)
                source = registration_store.EpisodeSource(
                    conversation_id="conversation-1",
                    generation_id="generation-1",
                    source_contract="cursor-hook/v1",
                    source_event="beforeSubmitPrompt",
                    workspace_roots_hash="a" * 64,
                )
                rejects_without_write(
                    lambda: store.bind_episode(
                        data,
                        candidate,
                        member_id=member_id,
                        source=source,
                        projected_db_growth_bytes=True,
                    )
                )
                changed = harness.identity(ordinal=2)
                rejects_without_write(
                    lambda: store.invalidate_requested(
                        data,
                        candidate,
                        member_id=member_id,
                        expected_member_hash=authority.member[
                            "member_tuple_hash"
                        ],
                        expected_effect_hash=authority.effect[
                            "request_tuple_hash"
                        ],
                        expected_status_hash=authority.status["status_hash"],
                        basis=registration_store.BasisUpdate(
                            policy_basis_hash=changed.policy_basis_hash,
                            operation_basis_hash=(
                                changed.operation_basis_hash
                            ),
                            lifecycle_basis_hash=(
                                changed.lifecycle_basis_hash
                            ),
                            current_basis_hash=changed.current_basis_hash,
                        ),
                        intent=harness.clean_intent(ordinal=2),
                        projected_db_growth_bytes=False,
                    )
                )
                rejects_without_write(
                    lambda: store.open_effect(
                        data,
                        candidate,
                        member_id=member_id,
                        expected_member_hash=authority.member[
                            "member_tuple_hash"
                        ],
                        expected_effect_hash=authority.effect[
                            "request_tuple_hash"
                        ],
                        expected_status_hash=authority.status["status_hash"],
                        projected_db_growth_bytes=True,
                    )
                )
                opened = store.open_effect(
                    data,
                    candidate,
                    member_id=member_id,
                    expected_member_hash=authority.member[
                        "member_tuple_hash"
                    ],
                    expected_effect_hash=authority.effect[
                        "request_tuple_hash"
                    ],
                    expected_status_hash=authority.status["status_hash"],
                )
                rejects_without_write(
                    lambda: store.append_action(
                        data,
                        candidate,
                        opened.execution,
                        observation_kind="OBSERVED_EXACT",
                        measured_postcondition_hash=(
                            harness.next_postcondition(member_id)
                        ),
                        external_growth_bytes=True,
                    )
                )
                rejects_without_write(
                    lambda: store.append_action(
                        data,
                        candidate,
                        opened.execution,
                        observation_kind="OBSERVED_EXACT",
                        measured_postcondition_hash=(
                            harness.next_postcondition(member_id)
                        ),
                        projected_db_growth_bytes=False,
                    )
                )
                rejects_without_write(
                    lambda: store.close_success(
                        data,
                        candidate,
                        opened.execution,
                        final_basis_hash=(
                            harness.identity().current_basis_hash
                        ),
                        projected_db_growth_bytes=True,
                    )
                )
                rejects_without_write(
                    lambda: store.close_conflict(
                        data,
                        candidate,
                        opened.execution,
                        conflict_code="ACTION_POSTCONDITION_DIVERGENT",
                        expected_hash="a" * 64,
                        observed_hash="b" * 64,
                        projected_db_growth_bytes=False,
                    )
                )
                rejects_without_write(
                    lambda: store.mark_unavailable(
                        data,
                        candidate,
                        opened.execution,
                        projected_db_growth_bytes=True,
                    )
                )
                rejects_without_write(
                    lambda: store.schedule_status(
                        data,
                        candidate,
                        member_id=member_id,
                        expected_status_hash=authority.status["status_hash"],
                        attempt_count=True,
                        backoff_ns=0,
                    )
                )
                rejects_without_write(
                    lambda: store.schedule_status(
                        data,
                        candidate,
                        member_id=member_id,
                        expected_status_hash=authority.status["status_hash"],
                        attempt_count=0,
                        backoff_ns=False,
                    )
                )
                with self.assertRaises(ValueError):
                    store.list_due_candidates(
                        boot_id="boot-a", now_mono_ns=True
                    )
                with self.assertRaises(ValueError):
                    store.list_due_candidates(
                        boot_id="boot-a", now_mono_ns=1, limit=False
                    )
                with self.assertRaises(ValueError):
                    store.resolve_operation(
                        "f" * 64, expected_revision=True
                    )
                opened.execution.close()

    def test_corrupt_low_reservation_cannot_reduce_global_space_charge(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                store.install_member(
                    harness.data(),
                    candidate,
                    harness.identity(),
                    harness.clean_intent(),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                member_id = harness.connection.execute(
                    "SELECT member_id FROM registration_member"
                ).fetchone()[0]
                external = sqlite3.connect(str(db))
                try:
                    self._drop_all_registration_triggers(external)
                    external.execute(
                        "PRAGMA ignore_check_constraints=ON"
                    )
                    external.execute(
                        "UPDATE registration_effect "
                        "SET external_growth_reservation_bytes=0,"
                        "outcome_kind='SUCCESS' "
                        "WHERE member_id=?",
                        (member_id,),
                    )
                    external.commit()
                finally:
                    external.close()
                before = store.table_count("registration_operation_audit")
                harness.measured_free_bytes = (
                    registration_store.FILESYSTEM_SAFETY_FLOOR
                    + registration_store.MAX_CONTROL_RESERVE
                    + registration_store.UNVALIDATED_EFFECT_CHARGE
                    + registration_store.PROJECTED_DB_BYTES["BIND_EPISODE"]
                    - 1
                )
                with self.assertRaises(registration_store.InsufficientSpace):
                    store.bind_episode(
                        harness.data(),
                        candidate,
                        member_id=member_id,
                        source=registration_store.EpisodeSource(
                            conversation_id="conversation-corrupt",
                            generation_id="generation-corrupt",
                            source_contract="cursor-hook/v1",
                            source_event="beforeSubmitPrompt",
                            workspace_roots_hash="a" * 64,
                        ),
                    )
                harness.measured_free_bytes += 1
                with self.assertRaises(
                    registration_store.SemanticClosureError
                ):
                    store.bind_episode(
                        harness.data(),
                        candidate,
                        member_id=member_id,
                        source=registration_store.EpisodeSource(
                            conversation_id="conversation-corrupt",
                            generation_id="generation-corrupt",
                            source_contract="cursor-hook/v1",
                            source_event="beforeSubmitPrompt",
                            workspace_roots_hash="a" * 64,
                        ),
                    )
                self.assertEqual(
                    store.table_count("registration_operation_audit"), before
                )

    def test_resolved_current_charges_only_successor_reservation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                store.install_member(
                    harness.data(),
                    candidate,
                    harness.identity(),
                    harness.clean_intent(),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                member_id = harness.connection.execute(
                    "SELECT member_id FROM registration_member"
                ).fetchone()[0]
                authority = store.read_selected_authority(member_id)
                execution = store.open_effect(
                    harness.data(),
                    candidate,
                    member_id=member_id,
                    expected_member_hash=authority.member[
                        "member_tuple_hash"
                    ],
                    expected_effect_hash=authority.effect[
                        "request_tuple_hash"
                    ],
                    expected_status_hash=authority.status["status_hash"],
                    executor_secret=b"a" * 32,
                ).execution
                for _ in range(4):
                    store.append_action(
                        harness.data(),
                        candidate,
                        execution,
                        observation_kind="OBSERVED_EXACT",
                        measured_postcondition_hash=(
                            harness.next_postcondition()
                        ),
                    )
                store.close_success(
                    harness.data(),
                    candidate,
                    execution,
                    final_basis_hash=harness.identity().current_basis_hash,
                )
                self.assertEqual(
                    store._outstanding_reservations(),
                    registration_store.UNVALIDATED_SUCCESSOR_CHARGE,
                )
                threshold = (
                    registration_store.FILESYSTEM_SAFETY_FLOOR
                    + registration_store.MAX_CONTROL_RESERVE
                    + registration_store.UNVALIDATED_SUCCESSOR_CHARGE
                    + registration_store.PROJECTED_DB_BYTES["BIND_EPISODE"]
                )
                source = registration_store.EpisodeSource(
                    conversation_id="resolved-threshold",
                    generation_id="resolved-threshold",
                    source_contract="cursor-hook/v1",
                    source_event="beforeSubmitPrompt",
                    workspace_roots_hash="a" * 64,
                )
                before = store.table_count("registration_operation_audit")
                harness.measured_free_bytes = threshold - 1
                with self.assertRaises(
                    registration_store.InsufficientSpace
                ):
                    store.bind_episode(
                        harness.data(),
                        candidate,
                        member_id=member_id,
                        source=source,
                    )
                self.assertEqual(
                    store.table_count("registration_operation_audit"), before
                )
                harness.measured_free_bytes = threshold
                self.assertEqual(
                    store.bind_episode(
                        harness.data(),
                        candidate,
                        member_id=member_id,
                        source=source,
                    ).disposition,
                    "COMMITTED",
                )

    def test_unrelated_corruption_is_charged_without_blocking_healthy_member(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                member_ids: list[str] = []
                for ordinal in (1, 2):
                    store.install_member(
                        harness.data(),
                        candidate,
                        harness.identity(ordinal=ordinal),
                        harness.clean_intent(ordinal=ordinal),
                        sample_boot_id="boot-a",
                        sample_mono_ns=ordinal,
                    )
                    member_ids.append(
                        harness.connection.execute(
                            "SELECT member_id FROM registration_member "
                            "WHERE canonical_root=?",
                            (f"/fixture/root-{ordinal}",),
                        ).fetchone()[0]
                    )
                external = sqlite3.connect(str(db))
                try:
                    self._drop_all_registration_triggers(external)
                    external.execute(
                        "PRAGMA ignore_check_constraints=ON"
                    )
                    external.execute(
                        "UPDATE registration_effect "
                        "SET external_growth_reservation_bytes=0,"
                        "outcome_kind='SUCCESS' "
                        "WHERE member_id=?",
                        (member_ids[0],),
                    )
                    external.commit()
                finally:
                    external.close()
                harness.measured_free_bytes = (
                    registration_store.FILESYSTEM_SAFETY_FLOOR
                    + registration_store.MAX_CONTROL_RESERVE
                    + 2 * registration_store.UNVALIDATED_EFFECT_CHARGE
                    + registration_store.PROJECTED_DB_BYTES["BIND_EPISODE"]
                    - 1
                )
                source = registration_store.EpisodeSource(
                    conversation_id="conversation-healthy",
                    generation_id="generation-healthy",
                    source_contract="cursor-hook/v1",
                    source_event="beforeSubmitPrompt",
                    workspace_roots_hash="a" * 64,
                )
                before = store.table_count("registration_operation_audit")
                with self.assertRaises(registration_store.InsufficientSpace):
                    store.bind_episode(
                        harness.data(),
                        candidate,
                        member_id=member_ids[1],
                        source=source,
                    )
                self.assertEqual(
                    store.table_count("registration_operation_audit"), before
                )
                harness.measured_free_bytes += 1
                committed = store.bind_episode(
                    harness.data(),
                    candidate,
                    member_id=member_ids[1],
                    source=source,
                )
                self.assertEqual(committed.disposition, "COMMITTED")

    def test_corrupt_detached_outcome_cannot_reduce_global_space_charge(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                store.install_member(
                    harness.data(),
                    candidate,
                    harness.identity(ordinal=1),
                    harness.clean_intent(ordinal=1),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                member_id = harness.connection.execute(
                    "SELECT member_id FROM registration_member"
                ).fetchone()[0]
                authority = store.read_selected_authority(member_id)
                opened = store.open_effect(
                    harness.data(),
                    candidate,
                    member_id=member_id,
                    expected_member_hash=authority.member[
                        "member_tuple_hash"
                    ],
                    expected_effect_hash=authority.effect[
                        "request_tuple_hash"
                    ],
                    expected_status_hash=authority.status["status_hash"],
                    executor_secret=b"a" * 32,
                )
                for _index in range(4):
                    store.append_action(
                        harness.data(),
                        candidate,
                        opened.execution,
                        observation_kind="OBSERVED_EXACT",
                        measured_postcondition_hash=(
                            harness.next_postcondition(member_id)
                        ),
                    )
                store.close_success(
                    harness.data(),
                    candidate,
                    opened.execution,
                    final_basis_hash=(
                        harness.identity(ordinal=1).current_basis_hash
                    ),
                )
                predecessor_id = authority.effect["effect_id"]
                resolved = store.read_selected_authority(member_id)
                changed = harness.identity(ordinal=2)
                store.handoff_resolved(
                    harness.data(),
                    candidate,
                    member_id=member_id,
                    expected_member_hash=resolved.member[
                        "member_tuple_hash"
                    ],
                    expected_effect_hash=resolved.effect[
                        "outcome_tuple_hash"
                    ],
                    expected_status_hash=resolved.status["status_hash"],
                    cause="BASIS_CHANGED",
                    basis=registration_store.BasisUpdate(
                        policy_basis_hash=changed.policy_basis_hash,
                        operation_basis_hash=changed.operation_basis_hash,
                        lifecycle_basis_hash=changed.lifecycle_basis_hash,
                        current_basis_hash=changed.current_basis_hash,
                    ),
                    intent=harness.clean_intent(ordinal=2),
                )
                external = sqlite3.connect(str(db))
                try:
                    self._drop_all_registration_triggers(external)
                    external.execute("PRAGMA ignore_check_constraints=ON")
                    completion = external.execute(
                        "SELECT completion_blob FROM registration_effect "
                        "WHERE effect_id=?",
                        (predecessor_id,),
                    ).fetchone()[0]
                    external.execute(
                        "UPDATE registration_effect "
                        "SET completion_blob=? WHERE effect_id=?",
                        (
                            sqlite3.Binary(bytes(completion) + b" "),
                            predecessor_id,
                        ),
                    )
                    external.commit()
                finally:
                    external.close()
                source = registration_store.EpisodeSource(
                    conversation_id="conversation-detached-corrupt",
                    generation_id="generation-detached-corrupt",
                    source_contract="cursor-hook/v1",
                    source_event="beforeSubmitPrompt",
                    workspace_roots_hash="a" * 64,
                )
                before = store.table_count("registration_operation_audit")
                harness.measured_free_bytes = (
                    registration_store.FILESYSTEM_SAFETY_FLOOR
                    + registration_store.MAX_CONTROL_RESERVE
                    + 2 * registration_store.UNVALIDATED_EFFECT_CHARGE
                    + registration_store.PROJECTED_DB_BYTES["BIND_EPISODE"]
                    - 1
                )
                with self.assertRaises(registration_store.InsufficientSpace):
                    store.bind_episode(
                        harness.data(),
                        candidate,
                        member_id=member_id,
                        source=source,
                    )
                self.assertEqual(
                    store.table_count("registration_operation_audit"), before
                )
                harness.measured_free_bytes += 1
                with self.assertRaises(
                    registration_store.SemanticClosureError
                ):
                    store.bind_episode(
                        harness.data(),
                        candidate,
                        member_id=member_id,
                        source=source,
                    )
                self.assertEqual(
                    store.table_count("registration_operation_audit"), before
                )

    def test_typed_profiles_are_required_and_advance_installs_staged(self) -> None:
        current_binding, staged_binding = _typed_profile_pair()
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness, mock.patch.object(
                registration_profile.ProfileBinding,
                "recheck",
                return_value=2 * 1024**3,
            ):
                store = harness.store
                current = replace(
                    harness.candidate(),
                    profile_hash=current_binding.digest,
                )
                staged = replace(
                    harness.staged_candidate(),
                    profile_hash=staged_binding.digest,
                )
                store.bootstrap(harness.control(), current)
                store._allow_test_profile = False
                before = store.table_count("registration_operation_audit")
                with self.assertRaises(registration_profile.ProfileError):
                    store.activate(harness.control(), current)
                self.assertEqual(
                    store.table_count("registration_operation_audit"), before
                )
                store.activate(
                    harness.control(),
                    current,
                    profile_binding=current_binding,
                )
                store.begin_drain(
                    harness.control(),
                    current,
                    profile_binding=current_binding,
                )
                before = store.table_count("registration_operation_audit")
                with self.assertRaises(registration_profile.ProfileError):
                    store.stage_next(
                        harness.control(),
                        current,
                        staged,
                        quiescence_proof_hash="1" * 64,
                        current_profile_binding=current_binding,
                        staged_profile_binding=current_binding,
                    )
                self.assertEqual(
                    store.table_count("registration_operation_audit"), before
                )
                store.stage_next(
                    harness.control(),
                    current,
                    staged,
                    quiescence_proof_hash="1" * 64,
                    current_profile_binding=current_binding,
                    staged_profile_binding=staged_binding,
                )
                self.assertIs(
                    store._staged_typed_profile_binding, staged_binding
                )
                store.cancel_drain(
                    harness.control(),
                    current,
                    quiescence_proof_hash="2" * 64,
                    profile_binding=current_binding,
                )
                self.assertIsNone(store._staged_typed_profile_binding)
                store.activate(
                    harness.control(),
                    current,
                    profile_binding=current_binding,
                )
                store.begin_drain(
                    harness.control(),
                    current,
                    profile_binding=current_binding,
                )
                store.stage_next(
                    harness.control(),
                    current,
                    staged,
                    quiescence_proof_hash="3" * 64,
                    current_profile_binding=current_binding,
                    staged_profile_binding=staged_binding,
                )
                before = store.table_count("registration_operation_audit")
                with self.assertRaises(registration_profile.ProfileError):
                    store.advance_generation(
                        harness.control(),
                        current,
                        quiescence_proof_hash="4" * 64,
                        staged_candidate=staged,
                        current_profile_binding=current_binding,
                        staged_profile_binding=current_binding,
                    )
                self.assertEqual(
                    store.table_count("registration_operation_audit"), before
                )
                store.advance_generation(
                    harness.control(),
                    current,
                    quiescence_proof_hash="4" * 64,
                    staged_candidate=staged,
                    current_profile_binding=current_binding,
                    staged_profile_binding=staged_binding,
                )
                self.assertIsInstance(
                    store._current_typed_profile_binding,
                    registration_profile.CurrentProfileBinding,
                )
                self.assertIs(
                    store._current_typed_profile_binding.profile,
                    staged_binding.profile,
                )
                self.assertIs(store._profile_binding, staged_binding.profile)
                self.assertIsNone(store._staged_typed_profile_binding)

    def test_typed_profiles_fence_adopt_and_staged_reacquire(self) -> None:
        current_binding, staged_binding = _typed_profile_pair()
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness, mock.patch.object(
                registration_profile.ProfileBinding,
                "recheck",
                return_value=2 * 1024**3,
            ):
                store = harness.store
                current = replace(
                    harness.candidate(),
                    profile_hash=current_binding.digest,
                )
                staged = replace(
                    harness.staged_candidate(),
                    profile_hash=staged_binding.digest,
                )
                store.bootstrap(harness.control(), current)
                store._allow_test_profile = False
                store.activate(
                    harness.control(),
                    current,
                    profile_binding=current_binding,
                )
                store.install_member(
                    harness.data(),
                    current,
                    harness.identity(),
                    harness.clean_intent(),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                member_id = harness.connection.execute(
                    "SELECT member_id FROM registration_member"
                ).fetchone()[0]
                authority = store.read_selected_authority(member_id)
                secret = b"a" * 32
                opened = store.open_effect(
                    harness.data(),
                    current,
                    member_id=member_id,
                    expected_member_hash=authority.member[
                        "member_tuple_hash"
                    ],
                    expected_effect_hash=authority.effect[
                        "request_tuple_hash"
                    ],
                    expected_status_hash=authority.status["status_hash"],
                    executor_secret=secret,
                )
                opened.execution.close()
                store.begin_drain(
                    harness.control(),
                    current,
                    profile_binding=current_binding,
                )
                store.stage_next(
                    harness.control(),
                    current,
                    staged,
                    quiescence_proof_hash="5" * 64,
                    current_profile_binding=current_binding,
                    staged_profile_binding=staged_binding,
                )
                refused_transfer = (
                    registration_executor.StagedSecretTransfer.precreate(
                        clock_ns=harness._next_mono
                    )
                )
                refused_deadline = refused_transfer.deadline_after(1)
                try:
                    with self.assertRaises(
                        registration_profile.ProfileError
                    ):
                        store.receive_staged_execution(
                            refused_transfer,
                            expected_frame_digest="a" * 64,
                            deadline_ns=refused_deadline,
                        )
                    with self.assertRaises(
                        registration_profile.ProfileError
                    ):
                        store.receive_staged_execution(
                            refused_transfer,
                            expected_frame_digest="a" * 64,
                            deadline_ns=refused_deadline,
                            staged_candidate=staged,
                            staged_profile_binding=current_binding,
                        )
                finally:
                    refused_transfer.close()
                authority = store.read_selected_authority(member_id)
                before = store.table_count("registration_operation_audit")
                with self.assertRaises(registration_profile.ProfileError):
                    store.adopt_effect(
                        harness.control(),
                        current,
                        member_id=member_id,
                        expected_member_hash=authority.member[
                            "member_tuple_hash"
                        ],
                        expected_status_hash=authority.status["status_hash"],
                        executor_secret=secret,
                    )
                self.assertEqual(
                    store.table_count("registration_operation_audit"), before
                )
                adopted = store.adopt_effect(
                    harness.control(),
                    current,
                    member_id=member_id,
                    expected_member_hash=authority.member[
                        "member_tuple_hash"
                    ],
                    expected_status_hash=authority.status["status_hash"],
                    current_profile_binding=current_binding,
                    staged_candidate=staged,
                    staged_profile_binding=staged_binding,
                    executor_secret=secret,
                )
                adopted.execution.close()
                authority = store.read_selected_authority(member_id)
                before = store.table_count("registration_operation_audit")
                with self.assertRaises(registration_profile.ProfileError):
                    store.mark_dead_executor_unavailable(
                        harness.staged_data(),
                        staged,
                        member_id=member_id,
                        expected_status_hash=authority.status["status_hash"],
                    )
                self.assertEqual(
                    store.table_count("registration_operation_audit"), before
                )
                store.mark_dead_executor_unavailable(
                    harness.staged_data(),
                    staged,
                    member_id=member_id,
                    expected_status_hash=authority.status["status_hash"],
                    profile_binding=staged_binding,
                )
                authority = store.read_selected_authority(member_id)
                before = store.table_count("registration_operation_audit")
                with self.assertRaises(registration_profile.ProfileError):
                    store.reacquire_effect(
                        harness.staged_data(),
                        staged,
                        member_id=member_id,
                        expected_member_hash=authority.member[
                            "member_tuple_hash"
                        ],
                        expected_effect_hash=authority.effect[
                            "request_tuple_hash"
                        ],
                        expected_status_hash=authority.status["status_hash"],
                    )
                self.assertEqual(
                    store.table_count("registration_operation_audit"), before
                )
                reacquired = store.reacquire_effect(
                    harness.staged_data(),
                    staged,
                    member_id=member_id,
                    expected_member_hash=authority.member[
                        "member_tuple_hash"
                    ],
                    expected_effect_hash=authority.effect[
                        "request_tuple_hash"
                    ],
                    expected_status_hash=authority.status["status_hash"],
                    profile_binding=staged_binding,
                    executor_secret=b"b" * 32,
                )
                store.mark_unavailable(
                    harness.staged_data(),
                    staged,
                    reacquired.execution,
                    profile_binding=staged_binding,
                )

    def test_bootstrap_is_authenticated_exact_and_append_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                control = harness.control()
                candidate = harness.candidate()
                result = store.bootstrap(control, candidate)
                self.assertEqual(result.disposition, "COMMITTED")
                snapshot = store.current_protocol()
                self.assertEqual(snapshot["protocol_seq"], 1)
                self.assertEqual(snapshot["protocol_generation"], 1)
                self.assertEqual(snapshot["mode"], "DORMANT")
                self.assertEqual(snapshot["schema_hash"], registration_store.SCHEMA_SHA256)
                self.assertEqual(store.table_count("registration_operation_audit"), 1)

                with self.assertRaises(registration_store.AuthorizationError):
                    store.bootstrap("installer", candidate)  # type: ignore[arg-type]
                with self.assertRaises(registration_store.AuthorizationError):
                    control.installer_identity_hash = "00" * 32
                data = harness.data()
                with self.assertRaises(registration_store.AuthorizationError):
                    data.writer_capability_hash = "00" * 32
                with self.assertRaises(registration_store.AuthorizationError):
                    registration_store.MemberExecution(
                        store_identity=id(store),
                        member_lock=None,  # type: ignore[arg-type]
                        secret=b"x" * 32,
                        member_id="00" * 32,
                        effect_id="00" * 32,
                        executor_token_hash="00" * 32,
                        operation_id="00" * 32,
                        target_member_hash="00" * 32,
                        target_effect_hash="00" * 32,
                        target_status_hash="00" * 32,
                        target_protocol_hash="00" * 32,
                        _seal=object(),
                    )
                with self.assertRaises(sqlite3.DatabaseError):
                    harness.connection.execute(
                        "DELETE FROM registration_protocol_epoch"
                    )
                with self.assertRaises(sqlite3.DatabaseError):
                    harness.connection.execute(
                        "UPDATE registration_operation_audit "
                        "SET operation_kind='ACTIVATE'"
                    )
                denied = (
                    "INSERT INTO registration_operation_audit"
                    "(operation_seq,operation_id,operation_class,operation_kind,"
                    "expected_revision,protocol_seq,expected_mode,"
                    "expected_generation,runtime_capability_hash,"
                    "writer_binary_hash,profile_hash,operation_envelope_hash,"
                    "measured_free_bytes,projected_db_growth_bytes,"
                    "external_growth_bytes,new_external_reservation_bytes,"
                    "new_outcome_reservation_bytes,new_successor_reservation_bytes,"
                    "control_reserve_bytes,created_wall_ns)"
                    " VALUES(2,?,'DATA','BIND_EPISODE',1,1,'DORMANT',1,"
                    "?,?,?,?,0,0,0,0,0,0,14680064,0)",
                    "DROP TABLE registration_member",
                    "ATTACH DATABASE ':memory:' AS other",
                    "VACUUM",
                    "PRAGMA writable_schema=ON",
                )
                for statement in denied:
                    with self.subTest(statement=statement):
                        with self.assertRaises(sqlite3.DatabaseError):
                            if "?" in statement:
                                harness.connection.execute(
                                    statement,
                                    (
                                        "aa" * 32,
                                        "bb" * 32,
                                        "cc" * 32,
                                        "dd" * 32,
                                        "ee" * 32,
                                    ),
                                )
                            else:
                                harness.connection.execute(statement)

    def test_existing_v1_schema_refuses_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            db.parent.mkdir(parents=True, mode=0o700)
            connection = sqlite3.connect(str(db))
            try:
                connection.executescript(
                    Path(registration_store.__file__)
                    .with_name("registration_schema.sql")
                    .read_text(encoding="utf-8")
                )
            finally:
                connection.close()
            db.chmod(0o600)
            before = db.read_bytes()
            with self.assertRaises(registration_store.StoreUnavailable):
                RegistrationHarness.open(
                    db, measured_free_bytes=2 * 1024**3
                )
            self.assertEqual(db.read_bytes(), before)
            for suffix in ("-journal", "-wal", "-shm"):
                self.assertFalse(Path(f"{db}{suffix}").exists())

    def test_existing_empty_database_refuses_before_wal_configuration(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            db.parent.mkdir(parents=True, mode=0o700)
            db.touch(mode=0o600)
            before = db.read_bytes()
            with self.assertRaises(registration_store.StoreUnavailable):
                RegistrationHarness.open(
                    db, measured_free_bytes=2 * 1024**3
                )
            self.assertEqual(db.read_bytes(), before)
            for suffix in ("-journal", "-wal", "-shm"):
                self.assertFalse(Path(f"{db}{suffix}").exists())

    def test_existing_canonical_database_refuses_unknown_schema_residue(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            harness = RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            )
            harness.store.bootstrap(
                harness.control(), harness.candidate()
            )
            harness.close()
            residue = db.with_name(
                f".{db.name}.awa-schema-{'ab' * 32}.tmp"
            )
            residue.write_bytes(b"unknown")
            with self.assertRaises(registration_store.StoreUnavailable):
                registration_store.RegistrationStore(
                    db,
                    free_bytes=lambda _fd: 2 * 1024**3,
                    _test_profile_seal=(
                        registration_store._TEST_PROFILE_SEAL
                    ),
                )
            self.assertEqual(residue.read_bytes(), b"unknown")

    def test_low_free_refusal_writes_no_operation_and_self_clears(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db,
                measured_free_bytes=registration_store.FILESYSTEM_SAFETY_FLOOR - 1,
            ) as harness:
                with self.assertRaises(registration_store.InsufficientSpace):
                    harness.store.bootstrap(harness.control(), harness.candidate())
                self.assertEqual(
                    harness.store.table_count("registration_operation_audit"), 0
                )
                self.assertEqual(
                    harness.store.table_count("registration_protocol_epoch"), 0
                )
                harness.measured_free_bytes = 2 * 1024**3
                result = harness.store.bootstrap(
                    harness.control(), harness.candidate()
                )
                self.assertEqual(result.disposition, "COMMITTED")

    def test_low_free_open_refusal_preserves_exact_requested_tuple(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                store.install_member(
                    harness.data(),
                    candidate,
                    harness.identity(),
                    harness.clean_intent(),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                row = harness.connection.execute(
                    "SELECT m.member_id,m.member_tuple_hash,e.request_tuple_hash,"
                    "s.status_hash FROM registration_member m "
                    "JOIN registration_effect e ON e.effect_id=m.current_effect_id "
                    "JOIN registration_runtime_status s USING(member_id)"
                ).fetchone()
                before_ops = store.table_count("registration_operation_audit")
                harness.measured_free_bytes = (
                    registration_store.FILESYSTEM_SAFETY_FLOOR
                )
                with self.assertRaises(registration_store.InsufficientSpace):
                    store.open_effect(
                        harness.data(),
                        candidate,
                        member_id=row["member_id"],
                        expected_member_hash=row["member_tuple_hash"],
                        expected_effect_hash=row["request_tuple_hash"],
                        expected_status_hash=row["status_hash"],
                    )
                after = harness.connection.execute(
                    "SELECT m.member_tuple_hash,e.request_tuple_hash,s.status_hash "
                    "FROM registration_member m "
                    "JOIN registration_effect e ON e.effect_id=m.current_effect_id "
                    "JOIN registration_runtime_status s USING(member_id)"
                ).fetchone()
                self.assertEqual(
                    tuple(after),
                    (
                        row["member_tuple_hash"],
                        row["request_tuple_hash"],
                        row["status_hash"],
                    ),
                )
                self.assertEqual(
                    store.table_count("registration_operation_audit"),
                    before_ops,
                )

    def test_full_ioerr_resolution_uses_durable_authority_not_return_code(self) -> None:
        operation_id = "12" * 32
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                harness.inject_fault(
                    "before_commit",
                    registration_store.InjectedSQLiteFault(sqlite3.SQLITE_FULL),
                )
                with self.assertRaises(registration_store.InjectedSQLiteFault):
                    harness.store.bootstrap(
                        harness.control(),
                        harness.candidate(),
                        operation_id=operation_id,
                    )
                self.assertEqual(
                    harness.store.resolve_operation(
                        operation_id,
                        expected_revision=0,
                        expected_protocol_hash=None,
                    ),
                    "ABSENT",
                )
                self.assertEqual(
                    harness.store.table_count("registration_operation_audit"), 0
                )

        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                harness.inject_fault(
                    "after_commit",
                    registration_store.InjectedSQLiteFault(sqlite3.SQLITE_IOERR),
                )
                with self.assertRaises(registration_store.InjectedSQLiteFault):
                    harness.store.bootstrap(
                        harness.control(),
                        harness.candidate(),
                        operation_id=operation_id,
                    )
                self.assertEqual(
                    harness.store.resolve_operation(operation_id), "COMMITTED"
                )
                self.assertEqual(
                    harness.store.table_count("registration_operation_audit"), 1
                )

    def test_open_post_commit_fault_clears_executor_before_return(self) -> None:
        for point in ("after_commit", "before_grant_return"):
            with self.subTest(point=point), tempfile.TemporaryDirectory() as tmp:
                db = Path(tmp) / "state" / "registration-v1" / "registration.db"
                with RegistrationHarness.open(
                    db, measured_free_bytes=2 * 1024**3
                ) as harness:
                    store = harness.store
                    candidate = harness.candidate()
                    store.bootstrap(harness.control(), candidate)
                    store.activate(harness.control(), candidate)
                    store.install_member(
                        harness.data(),
                        candidate,
                        harness.identity(),
                        harness.clean_intent(),
                        sample_boot_id="boot-a",
                        sample_mono_ns=1,
                    )
                    row = harness.connection.execute(
                        "SELECT m.member_id,m.member_tuple_hash,"
                        "e.request_tuple_hash,s.status_hash "
                        "FROM registration_member m "
                        "JOIN registration_effect e "
                        "ON e.effect_id=m.current_effect_id "
                        "JOIN registration_runtime_status s USING(member_id)"
                    ).fetchone()
                    harness.inject_fault(point, RuntimeError(point))
                    with self.assertRaisesRegex(RuntimeError, point):
                        store.open_effect(
                            harness.data(),
                            candidate,
                            member_id=row["member_id"],
                            expected_member_hash=row["member_tuple_hash"],
                            expected_effect_hash=row["request_tuple_hash"],
                            expected_status_hash=row["status_hash"],
                            executor_secret=b"g" * 32,
                        )
                    status = harness.connection.execute(
                        "SELECT executor_token_hash,help_due,reason_code "
                        "FROM registration_runtime_status WHERE member_id=?",
                        (row["member_id"],),
                    ).fetchone()
                    self.assertEqual(
                        tuple(status), (None, 1, "RESOLVER_UNAVAILABLE")
                    )
                    self.assertEqual(
                        [
                            item[0]
                            for item in harness.connection.execute(
                                "SELECT operation_kind "
                                "FROM registration_operation_audit "
                                "WHERE target_member_id=? ORDER BY operation_seq",
                                (row["member_id"],),
                            )
                        ][-2:],
                        ["OPEN_EFFECT", "MARK_UNAVAILABLE"],
                    )

    def test_begin_drain_waits_for_grant_finalization_and_cleanup(self) -> None:
        for grant_kind in ("OPEN_EFFECT", "REACQUIRE_EFFECT"):
            with self.subTest(grant_kind=grant_kind), tempfile.TemporaryDirectory() as tmp:
                db = Path(tmp) / "state" / "registration-v1" / "registration.db"
                with RegistrationHarness.open(
                    db, measured_free_bytes=2 * 1024**3
                ) as harness:
                    candidate = harness.candidate()
                    harness.store.bootstrap(harness.control(), candidate)
                    harness.store.activate(harness.control(), candidate)
                    harness.store.install_member(
                        harness.data(),
                        candidate,
                        harness.identity(),
                        harness.clean_intent(),
                        sample_boot_id="boot-a",
                        sample_mono_ns=1,
                    )
                    member_id = harness.connection.execute(
                        "SELECT member_id FROM registration_member"
                    ).fetchone()[0]
                    if grant_kind == "REACQUIRE_EFFECT":
                        authority = harness.store.read_selected_authority(member_id)
                        opened = harness.store.open_effect(
                            harness.data(),
                            candidate,
                            member_id=member_id,
                            expected_member_hash=authority.member[
                                "member_tuple_hash"
                            ],
                            expected_effect_hash=authority.effect[
                                "request_tuple_hash"
                            ],
                            expected_status_hash=authority.status["status_hash"],
                            executor_secret=b"a" * 32,
                        )
                        harness.store.mark_unavailable(
                            harness.data(), candidate, opened.execution
                        )
                    authority = harness.store.read_selected_authority(member_id)

                    grant_paused = threading.Event()
                    release_grant = threading.Event()
                    drain_attempting = threading.Event()
                    drain_entered_transaction = threading.Event()
                    grant_errors: list[BaseException] = []
                    drain_errors: list[BaseException] = []
                    drain_results: list[registration_store.OperationResult] = []

                    def grant_fault(point: str) -> None:
                        if point == "before_grant_return":
                            grant_paused.set()
                            if not release_grant.wait(5):
                                raise AssertionError("grant barrier timed out")
                            raise RuntimeError("grant cleanup barrier")

                    def drain_fault(point: str) -> None:
                        if point == "before_begin":
                            drain_entered_transaction.set()

                    def open_thread_store(
                        fault: Callable[[str], None],
                    ) -> registration_store.RegistrationStore:
                        return registration_store.RegistrationStore(
                            db,
                            free_bytes=lambda _fd: 2 * 1024**3,
                            wall_ns=lambda: 2_000_000,
                            boot_id=lambda: "boot-a",
                            mono_ns=lambda: 10_000,
                            fault=fault,
                            _test_profile_seal=registration_store._TEST_PROFILE_SEAL,
                        )

                    def run_grant() -> None:
                        store = open_thread_store(grant_fault)
                        try:
                            arguments = {
                                "member_id": member_id,
                                "expected_member_hash": authority.member[
                                    "member_tuple_hash"
                                ],
                                "expected_effect_hash": authority.effect[
                                    "request_tuple_hash"
                                ],
                                "expected_status_hash": authority.status[
                                    "status_hash"
                                ],
                                "executor_secret": b"g" * 32,
                                "operation_id": (
                                    "a1" * 32
                                    if grant_kind == "OPEN_EFFECT"
                                    else "a2" * 32
                                ),
                            }
                            if grant_kind == "OPEN_EFFECT":
                                store.open_effect(
                                    harness.data(), candidate, **arguments
                                )
                            else:
                                store.reacquire_effect(
                                    harness.data(), candidate, **arguments
                                )
                        except BaseException as error:
                            grant_errors.append(error)
                        finally:
                            store.close()

                    def run_drain() -> None:
                        store = open_thread_store(drain_fault)
                        try:
                            drain_attempting.set()
                            drain_results.append(
                                store.begin_drain(
                                    harness.control(),
                                    candidate,
                                    operation_id="b1" * 32,
                                )
                            )
                        except BaseException as error:
                            drain_errors.append(error)
                        finally:
                            store.close()

                    grant_thread = threading.Thread(target=run_grant)
                    drain_thread = threading.Thread(target=run_drain)
                    grant_thread.start()
                    self.assertTrue(grant_paused.wait(5))
                    drain_thread.start()
                    self.assertTrue(drain_attempting.wait(5))
                    with self.assertRaises(registration_lock.LockBusy):
                        registration_lock.LockManager(
                            db.parent / "locks"
                        ).acquire_protocol(timeout=0)
                    self.assertFalse(drain_entered_transaction.is_set())
                    release_grant.set()
                    grant_thread.join(5)
                    drain_thread.join(5)
                    self.assertFalse(grant_thread.is_alive())
                    self.assertFalse(drain_thread.is_alive())
                    self.assertEqual(len(grant_errors), 1)
                    self.assertIsInstance(grant_errors[0], RuntimeError)
                    self.assertEqual(str(grant_errors[0]), "grant cleanup barrier")
                    self.assertEqual(drain_errors, [])
                    self.assertEqual(
                        [result.disposition for result in drain_results],
                        ["COMMITTED"],
                    )
                    self.assertTrue(drain_entered_transaction.is_set())
                    self.assertEqual(
                        harness.store.current_protocol()["mode"], "DRAINING"
                    )

    def test_sqlite_durability_profile_and_no_checkpoint_on_close(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            harness = RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            )
            store = harness.store
            pragmas = store.pragma_snapshot()
            self.assertEqual(pragmas["journal_mode"], "wal")
            self.assertEqual(pragmas["synchronous"], 2)
            self.assertEqual(pragmas["fullfsync"], 1)
            self.assertEqual(pragmas["checkpoint_fullfsync"], 1)
            self.assertEqual(pragmas["foreign_keys"], 1)
            self.assertEqual(pragmas["trusted_schema"], 0)
            self.assertEqual(pragmas["locking_mode"], "normal")
            self.assertTrue(pragmas["defensive"])
            harness.close()
            self.assertTrue(db.exists())
            self.assertEqual(db.stat().st_mode & 0o777, 0o600)

    def test_activate_and_install_all_three_requested_kinds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                store.bootstrap(harness.control(), candidate)
                activated = store.activate(harness.control(), candidate)
                self.assertEqual(activated.disposition, "COMMITTED")
                self.assertEqual(store.current_protocol()["mode"], "WRITABLE")

                intents = (
                    harness.clean_intent(ordinal=1),
                    harness.blocked_intent("BLOCKED_DIRTY", ordinal=2),
                    harness.blocked_intent("BLOCKED_OPERATION", ordinal=3),
                )
                expected_reasons = (
                    "REGISTRATION_REQUIRED",
                    "DIRTY_UNSUPPORTED",
                    "GIT_OPERATION_UNSUPPORTED",
                )
                for ordinal, (intent, reason) in enumerate(
                    zip(intents, expected_reasons), 1
                ):
                    result = store.install_member(
                        harness.data(),
                        candidate,
                        harness.identity(ordinal=ordinal),
                        intent,
                        sample_boot_id="boot-a",
                        sample_mono_ns=ordinal,
                    )
                    self.assertEqual(result.disposition, "COMMITTED")
                    row = harness.connection.execute(
                        "SELECT m.phase,m.member_epoch,s.reason_code,"
                        "s.executor_token_hash,e.request_kind "
                        "FROM registration_member m "
                        "JOIN registration_runtime_status s USING(member_id) "
                        "JOIN registration_effect e "
                        "ON e.effect_id=m.current_effect_id "
                        "WHERE m.member_tuple_hash=?",
                        (result.target_hash,),
                    ).fetchone()
                    self.assertEqual(
                        tuple(row),
                        ("REQUESTED", 1, reason, None, intent.request_kind),
                    )
                self.assertEqual(store.table_count("registration_member"), 3)
                self.assertEqual(
                    store.table_count("registration_runtime_status"), 3
                )

    def test_exact_duplicate_member_and_episode_converge_without_write(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                data = harness.data()
                identity_value = harness.identity()
                intent = harness.clean_intent()
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                installed = store.install_member(
                    data,
                    candidate,
                    identity_value,
                    intent,
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                before = store.table_count("registration_operation_audit")
                duplicate = store.install_member(
                    data,
                    candidate,
                    identity_value,
                    intent,
                    sample_boot_id="stale-observation",
                    sample_mono_ns=0,
                )
                self.assertEqual(duplicate, installed)
                self.assertEqual(
                    store.table_count("registration_operation_audit"), before
                )
                with self.assertRaises(registration_store.StaleAuthority):
                    store.install_member(
                        data,
                        candidate,
                        identity_value,
                        harness.clean_intent(ordinal=2),
                    )
                self.assertEqual(
                    store.table_count("registration_operation_audit"), before
                )

                member_id = harness.connection.execute(
                    "SELECT member_id FROM registration_member"
                ).fetchone()[0]
                source = registration_store.EpisodeSource(
                    conversation_id="conversation-duplicate",
                    generation_id="generation-duplicate",
                    source_contract="cursor-hook/v1",
                    source_event="beforeSubmitPrompt",
                    workspace_roots_hash="a" * 64,
                )
                bound = store.bind_episode(
                    data,
                    candidate,
                    member_id=member_id,
                    source=source,
                )
                before = store.table_count("registration_operation_audit")
                duplicate_bound = store.bind_episode(
                    data,
                    candidate,
                    member_id=member_id,
                    source=source,
                )
                self.assertEqual(duplicate_bound, bound)
                self.assertEqual(
                    store.table_count("registration_operation_audit"), before
                )

    def test_selected_revision_ignores_unrelated_member_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                for ordinal in (1, 2):
                    store.install_member(
                        harness.data(),
                        candidate,
                        harness.identity(ordinal=ordinal),
                        harness.clean_intent(ordinal=ordinal),
                        sample_boot_id="boot-a",
                        sample_mono_ns=ordinal,
                    )
                members = harness.connection.execute(
                    "SELECT m.member_id,m.member_tuple_hash,"
                    "e.request_tuple_hash,s.status_hash "
                    "FROM registration_member m "
                    "JOIN registration_effect e "
                    "ON e.effect_id=m.current_effect_id "
                    "JOIN registration_runtime_status s USING(member_id) "
                    "ORDER BY m.canonical_root"
                ).fetchall()
                selected_before = store.read_selected_revision(
                    members[0]["member_id"]
                )
                identity = harness.identity(ordinal=3)
                store.invalidate_requested(
                    harness.data(),
                    candidate,
                    member_id=members[1]["member_id"],
                    expected_member_hash=members[1]["member_tuple_hash"],
                    expected_effect_hash=members[1]["request_tuple_hash"],
                    expected_status_hash=members[1]["status_hash"],
                    basis=registration_store.BasisUpdate(
                        identity.policy_basis_hash,
                        identity.operation_basis_hash,
                        identity.lifecycle_basis_hash,
                        identity.current_basis_hash,
                    ),
                    intent=harness.clean_intent(ordinal=3),
                )
                self.assertEqual(
                    store.read_selected_revision(members[0]["member_id"]),
                    selected_before,
                )

    def test_open_effect_is_direct_cas_and_first_effect_is_paired_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                for ordinal in (1, 2):
                    store.install_member(
                        harness.data(),
                        candidate,
                        harness.identity(ordinal=ordinal),
                        harness.clean_intent(ordinal=ordinal),
                        sample_boot_id="boot-a",
                        sample_mono_ns=ordinal,
                    )
                rows = harness.connection.execute(
                    "SELECT m.member_id,m.member_tuple_hash,e.request_tuple_hash,"
                    "s.status_hash FROM registration_member m "
                    "JOIN registration_effect e ON e.effect_id=m.current_effect_id "
                    "JOIN registration_runtime_status s USING(member_id) "
                    "ORDER BY m.member_id"
                ).fetchall()

                first = rows[0]
                opened = store.open_effect(
                    harness.data(),
                    candidate,
                    member_id=first["member_id"],
                    expected_member_hash=first["member_tuple_hash"],
                    expected_effect_hash=first["request_tuple_hash"],
                    expected_status_hash=first["status_hash"],
                    executor_secret=b"a" * 32,
                )
                try:
                    store.verify_execution(opened.execution)
                    with self.assertRaises(
                        registration_store.AuthorizationError
                    ):
                        opened.execution.member_id = "00" * 32
                    transfer = (
                        registration_executor.StagedSecretTransfer.precreate(
                            clock_ns=harness._next_mono
                        )
                    )
                    self.addCleanup(transfer.close)
                    with self.assertRaises(
                        registration_store.AuthorizationError
                    ):
                        store.transfer_staged_execution(
                            opened.execution,
                            transfer,
                            deadline_ns=transfer.deadline_after(),
                        )
                    protocol = store.current_protocol()
                    self.assertEqual(
                        protocol["first_effect_operation_id"],
                        opened.operation.operation_id,
                    )
                    self.assertEqual(
                        protocol["first_effect_id"], opened.execution.effect_id
                    )
                    first_seq = protocol["protocol_seq"]
                finally:
                    opened.execution.close()

                second = rows[1]
                opened_second = store.open_effect(
                    harness.data(),
                    candidate,
                    member_id=second["member_id"],
                    expected_member_hash=second["member_tuple_hash"],
                    expected_effect_hash=second["request_tuple_hash"],
                    expected_status_hash=second["status_hash"],
                    executor_secret=b"b" * 32,
                )
                try:
                    self.assertEqual(
                        store.current_protocol()["protocol_seq"], first_seq
                    )
                finally:
                    opened_second.execution.close()
                with self.assertRaises(registration_store.StaleAuthority):
                    store.open_effect(
                        harness.data(),
                        candidate,
                        member_id=second["member_id"],
                        expected_member_hash=second["member_tuple_hash"],
                        expected_effect_hash=second["request_tuple_hash"],
                        expected_status_hash=second["status_hash"],
                        executor_secret=b"c" * 32,
                    )

    def test_action_replay_unavailable_and_same_effect_reacquire(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                store.install_member(
                    harness.data(),
                    candidate,
                    harness.identity(),
                    harness.clean_intent(),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                row = harness.connection.execute(
                    "SELECT m.member_id,m.member_tuple_hash,e.request_tuple_hash,"
                    "s.status_hash FROM registration_member m "
                    "JOIN registration_effect e ON e.effect_id=m.current_effect_id "
                    "JOIN registration_runtime_status s USING(member_id)"
                ).fetchone()
                opened = store.open_effect(
                    harness.data(),
                    candidate,
                    member_id=row["member_id"],
                    expected_member_hash=row["member_tuple_hash"],
                    expected_effect_hash=row["request_tuple_hash"],
                    expected_status_hash=row["status_hash"],
                    executor_secret=b"a" * 32,
                )
                first_action = store.append_action(
                    harness.data(),
                    candidate,
                    opened.execution,
                    observation_kind="OBSERVED_EXACT",
                    measured_postcondition_hash=harness.next_postcondition(),
                )
                self.assertEqual(first_action.disposition, "COMMITTED")
                action_count = store.table_count("registration_effect_action")
                unavailable = store.mark_unavailable(
                    harness.data(), candidate, opened.execution
                )
                self.assertEqual(unavailable.disposition, "COMMITTED")
                self.assertEqual(
                    store.table_count("registration_effect_action"), action_count
                )
                due = harness.connection.execute(
                    "SELECT m.member_tuple_hash,e.request_tuple_hash,s.status_hash,"
                    "m.member_id,e.effect_id "
                    "FROM registration_member m "
                    "JOIN registration_effect e ON e.effect_id=m.current_effect_id "
                    "JOIN registration_runtime_status s USING(member_id)"
                ).fetchone()
                reacquired = store.reacquire_effect(
                    harness.data(),
                    candidate,
                    member_id=due["member_id"],
                    expected_member_hash=due["member_tuple_hash"],
                    expected_effect_hash=due["request_tuple_hash"],
                    expected_status_hash=due["status_hash"],
                    executor_secret=b"b" * 32,
                )
                try:
                    self.assertEqual(
                        reacquired.execution.effect_id, due["effect_id"]
                    )
                    second_action = store.append_action(
                        harness.data(),
                        candidate,
                        reacquired.execution,
                        observation_kind="APPLIED_VERIFIED",
                        measured_postcondition_hash=harness.next_postcondition(),
                    )
                    self.assertEqual(second_action.disposition, "COMMITTED")
                    self.assertEqual(
                        store.table_count("registration_effect_action"), 2
                    )
                finally:
                    reacquired.execution.close()

    def test_fourth_recovery_cycle_returns_typed_zero_write_exhaustion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                store.install_member(
                    harness.data(),
                    candidate,
                    harness.identity(),
                    harness.clean_intent(),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                member_id = harness.connection.execute(
                    "SELECT member_id FROM registration_member"
                ).fetchone()[0]
                authority = store.read_selected_authority(member_id)
                execution = store.open_effect(
                    harness.data(),
                    candidate,
                    member_id=member_id,
                    expected_member_hash=authority.member["member_tuple_hash"],
                    expected_effect_hash=authority.effect["request_tuple_hash"],
                    expected_status_hash=authority.status["status_hash"],
                    executor_secret=b"a" * 32,
                ).execution
                for ordinal in range(3):
                    marked = store.mark_unavailable(
                        harness.data(), candidate, execution
                    )
                    self.assertIsInstance(
                        marked, registration_store.OperationResult
                    )
                    authority = store.read_selected_authority(member_id)
                    reacquired = store.reacquire_effect(
                        harness.data(),
                        candidate,
                        member_id=member_id,
                        expected_member_hash=authority.member[
                            "member_tuple_hash"
                        ],
                        expected_effect_hash=authority.effect[
                            "request_tuple_hash"
                        ],
                        expected_status_hash=authority.status["status_hash"],
                        executor_secret=bytes([ord("b") + ordinal]) * 32,
                    )
                    self.assertIsInstance(
                        reacquired, registration_store.ExecutionResult
                    )
                    execution = reacquired.execution
                before = {
                    table: store.table_count(table)
                    for table in registration_store.registration_schema.TABLE_NAMES
                }
                status_hash = store.read_selected_authority(member_id).status[
                    "status_hash"
                ]
                exhausted = store.mark_unavailable(
                    harness.data(), candidate, execution
                )
                self.assertIsInstance(
                    exhausted, registration_store.RecoveryReserveExhausted
                )
                self.assertEqual(exhausted.recovery_operation_count, "6")
                self.assertEqual(exhausted.recovery_bytes_consumed, "49152")
                self.assertEqual(exhausted.recovery_bytes_reserved, "49152")
                self.assertEqual(exhausted.status_hash, status_hash)
                self.assertFalse(execution.held)
                self.assertEqual(
                    {
                        table: store.table_count(table)
                        for table in registration_store.registration_schema.TABLE_NAMES
                    },
                    before,
                )
                with self.assertRaises(registration_store.AuthorizationError):
                    registration_store.RecoveryReserveExhausted(
                        protocol_hash="1" * 64,
                        staged_epoch_hash=None,
                        member_id="2" * 64,
                        effect_id="3" * 64,
                        member_tuple_hash="4" * 64,
                        status_hash="5" * 64,
                        executor_token_hash=None,
                        _seal=object(),
                    )

    def test_recovery_history_corruption_cannot_restore_reserve(
        self,
    ) -> None:
        cases = (
            (
                "mark-kind",
                "MARK_UNAVAILABLE",
                {"operation_kind": "SCHEDULE_STATUS"},
            ),
            (
                "reacquire-kind",
                "REACQUIRE_EFFECT",
                {"operation_kind": "SCHEDULE_STATUS"},
            ),
            (
                "mark-effect-selector",
                "MARK_UNAVAILABLE",
                {"target_effect_id": "f" * 64},
            ),
            (
                "reacquire-member-selector",
                "REACQUIRE_EFFECT",
                {"target_member_id": "e" * 64},
            ),
            (
                "mark-to-reacquire",
                "MARK_UNAVAILABLE",
                {"operation_kind": "REACQUIRE_EFFECT"},
            ),
            (
                "reacquire-to-mark",
                "REACQUIRE_EFFECT",
                {"operation_kind": "MARK_UNAVAILABLE"},
            ),
            (
                "mark-status-chain",
                "MARK_UNAVAILABLE",
                {"target_status_hash": "f" * 64},
            ),
            (
                "reacquire-status-chain",
                "REACQUIRE_EFFECT",
                {"expected_target_status_hash": "f" * 64},
            ),
            (
                "mark-token-chain",
                "MARK_UNAVAILABLE",
                {"target_executor_token_hash": "f" * 64},
            ),
            (
                "reacquire-staged-epoch",
                "REACQUIRE_EFFECT",
                {"target_staged_epoch_hash": "f" * 64},
            ),
            (
                "reacquire-effect-companion",
                "REACQUIRE_EFFECT",
                {"expected_target_effect_tuple_hash": "f" * 64},
            ),
            (
                "reacquire-member-companion",
                "REACQUIRE_EFFECT",
                {"expected_target_member_tuple_hash": "f" * 64},
            ),
        )
        for label, hidden_kind, mutation in cases:
            with (
                self.subTest(label=label),
                tempfile.TemporaryDirectory() as tmp,
            ):
                db = Path(tmp) / "state" / "registration-v1" / "registration.db"
                with RegistrationHarness.open(
                    db, measured_free_bytes=2 * 1024**3
                ) as harness:
                    store = harness.store
                    candidate = harness.candidate()
                    store.bootstrap(harness.control(), candidate)
                    store.activate(harness.control(), candidate)
                    store.install_member(
                        harness.data(),
                        candidate,
                        harness.identity(),
                        harness.clean_intent(),
                        sample_boot_id="boot-a",
                        sample_mono_ns=1,
                    )
                    member_id = harness.connection.execute(
                        "SELECT member_id FROM registration_member"
                    ).fetchone()[0]
                    authority = store.read_selected_authority(member_id)
                    execution = store.open_effect(
                        harness.data(),
                        candidate,
                        member_id=member_id,
                        expected_member_hash=authority.member[
                            "member_tuple_hash"
                        ],
                        expected_effect_hash=authority.effect[
                            "request_tuple_hash"
                        ],
                        expected_status_hash=authority.status["status_hash"],
                        executor_secret=b"a" * 32,
                    ).execution
                    try:
                        for ordinal in range(3):
                            store.mark_unavailable(
                                harness.data(), candidate, execution
                            )
                            authority = store.read_selected_authority(
                                member_id
                            )
                            reacquired = store.reacquire_effect(
                                harness.data(),
                                candidate,
                                member_id=member_id,
                                expected_member_hash=authority.member[
                                    "member_tuple_hash"
                                ],
                                expected_effect_hash=authority.effect[
                                    "request_tuple_hash"
                                ],
                                expected_status_hash=authority.status[
                                    "status_hash"
                                ],
                                executor_secret=bytes(
                                    [ord("b") + ordinal]
                                )
                                * 32,
                            )
                            self.assertIsInstance(
                                reacquired,
                                registration_store.ExecutionResult,
                            )
                            execution = reacquired.execution
                        hidden_operation_id = harness.connection.execute(
                            "SELECT operation_id "
                            "FROM registration_operation_audit "
                            "WHERE operation_kind=? "
                            "ORDER BY operation_seq LIMIT 1",
                            (hidden_kind,),
                        ).fetchone()[0]
                        external = sqlite3.connect(str(db))
                        try:
                            self._drop_all_registration_triggers(external)
                            external.execute(
                                "PRAGMA ignore_check_constraints=ON"
                            )
                            self._rewrite_operation_and_backlinks(
                                external,
                                hidden_operation_id,
                                **mutation,
                            )
                            external.commit()
                        finally:
                            external.close()
                        before = store.table_count(
                            "registration_operation_audit"
                        )
                        with self.assertRaises(
                            registration_store.SemanticClosureError
                        ):
                            store.mark_unavailable(
                                harness.data(), candidate, execution
                            )
                        self.assertEqual(
                            store.table_count(
                                "registration_operation_audit"
                            ),
                            before,
                        )
                    finally:
                        if execution.held:
                            execution.close()

    def test_staged_adopt_and_reacquire_faults_clear_with_draining_mark(self) -> None:
        for grant, point in (
            ("ADOPT_EFFECT", "after_commit"),
            ("ADOPT_EFFECT", "before_grant_return"),
            ("REACQUIRE_EFFECT", "after_commit"),
            ("REACQUIRE_EFFECT", "before_grant_return"),
        ):
            with (
                self.subTest(grant=grant, point=point),
                tempfile.TemporaryDirectory() as tmp,
            ):
                db = Path(tmp) / "state" / "registration-v1" / "registration.db"
                with RegistrationHarness.open(
                    db, measured_free_bytes=2 * 1024**3
                ) as harness:
                    store = harness.store
                    current = harness.candidate()
                    staged = harness.staged_candidate()
                    store.bootstrap(harness.control(), current)
                    store.activate(harness.control(), current)
                    store.install_member(
                        harness.data(),
                        current,
                        harness.identity(),
                        harness.clean_intent(),
                        sample_boot_id="boot-a",
                        sample_mono_ns=1,
                    )
                    member_id = harness.connection.execute(
                        "SELECT member_id FROM registration_member"
                    ).fetchone()[0]
                    authority = store.read_selected_authority(member_id)
                    opened = store.open_effect(
                        harness.data(),
                        current,
                        member_id=member_id,
                        expected_member_hash=authority.member[
                            "member_tuple_hash"
                        ],
                        expected_effect_hash=authority.effect[
                            "request_tuple_hash"
                        ],
                        expected_status_hash=authority.status["status_hash"],
                        executor_secret=b"a" * 32,
                    )
                    opened.execution.close()
                    store.begin_drain(harness.control(), current)
                    store.stage_next(
                        harness.control(),
                        current,
                        staged,
                        quiescence_proof_hash="9" * 64,
                    )
                    authority = store.read_selected_authority(member_id)
                    if grant == "ADOPT_EFFECT":
                        harness.inject_fault(
                            point, RuntimeError(f"{grant}:{point}")
                        )
                        with self.assertRaisesRegex(
                            RuntimeError, f"{grant}:{point}"
                        ):
                            store.adopt_effect(
                                harness.control(),
                                current,
                                member_id=member_id,
                                expected_member_hash=authority.member[
                                    "member_tuple_hash"
                                ],
                                expected_status_hash=authority.status[
                                    "status_hash"
                                ],
                                executor_secret=b"a" * 32,
                            )
                    else:
                        adopted = store.adopt_effect(
                            harness.control(),
                            current,
                            member_id=member_id,
                            expected_member_hash=authority.member[
                                "member_tuple_hash"
                            ],
                            expected_status_hash=authority.status["status_hash"],
                            executor_secret=b"a" * 32,
                        )
                        with self.assertRaises(registration_store.StaleAuthority):
                            store.mark_unavailable(
                                harness.data(), current, adopted.execution
                            )
                        with self.assertRaises(registration_store.StaleAuthority):
                            store.mark_unavailable(
                                harness.staged_data(),
                                replace(staged, profile_hash="0" * 64),
                                adopted.execution,
                            )
                        store.mark_unavailable(
                            harness.staged_data(), staged, adopted.execution
                        )
                        authority = store.read_selected_authority(member_id)
                        with self.assertRaises(registration_store.StaleAuthority):
                            store.reacquire_effect(
                                harness.data(),
                                current,
                                member_id=member_id,
                                expected_member_hash=authority.member[
                                    "member_tuple_hash"
                                ],
                                expected_effect_hash=authority.effect[
                                    "request_tuple_hash"
                                ],
                                expected_status_hash=authority.status[
                                    "status_hash"
                                ],
                                executor_secret=b"b" * 32,
                            )
                        harness.inject_fault(
                            point, RuntimeError(f"{grant}:{point}")
                        )
                        with self.assertRaisesRegex(
                            RuntimeError, f"{grant}:{point}"
                        ):
                            store.reacquire_effect(
                                harness.staged_data(),
                                staged,
                                member_id=member_id,
                                expected_member_hash=authority.member[
                                    "member_tuple_hash"
                                ],
                                expected_effect_hash=authority.effect[
                                    "request_tuple_hash"
                                ],
                                expected_status_hash=authority.status[
                                    "status_hash"
                                ],
                                executor_secret=b"b" * 32,
                            )
                    final = store.read_selected_authority(member_id)
                    self.assertIsNone(final.status["executor_token_hash"])
                    self.assertEqual(final.status["help_due"], 1)
                    self.assertEqual(final.protocol["mode"], "DRAINING")
                    self.assertEqual(
                        harness.connection.execute(
                            "SELECT operation_kind "
                            "FROM registration_operation_audit "
                            "ORDER BY operation_seq DESC LIMIT 1"
                        ).fetchone()[0],
                        "MARK_UNAVAILABLE",
                    )

    def test_staged_execution_transfer_moves_lock_and_secret_custody(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                current = harness.candidate()
                staged = harness.staged_candidate()
                store.bootstrap(harness.control(), current)
                store.activate(harness.control(), current)
                store.install_member(
                    harness.data(),
                    current,
                    harness.identity(),
                    harness.clean_intent(),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                member_id = harness.connection.execute(
                    "SELECT member_id FROM registration_member"
                ).fetchone()[0]
                authority = store.read_selected_authority(member_id)
                opened = store.open_effect(
                    harness.data(),
                    current,
                    member_id=member_id,
                    expected_member_hash=authority.member["member_tuple_hash"],
                    expected_effect_hash=authority.effect["request_tuple_hash"],
                    expected_status_hash=authority.status["status_hash"],
                    executor_secret=b"a" * 32,
                )
                opened.execution.close()
                store.begin_drain(harness.control(), current)
                store.stage_next(
                    harness.control(),
                    current,
                    staged,
                    quiescence_proof_hash="9" * 64,
                )
                authority = store.read_selected_authority(member_id)
                adopted = store.adopt_effect(
                    harness.control(),
                    current,
                    member_id=member_id,
                    expected_member_hash=authority.member["member_tuple_hash"],
                    expected_status_hash=authority.status["status_hash"],
                    executor_secret=b"a" * 32,
                )
                execution = adopted.execution
                obligations = store.unresolved_custody_obligations()
                self.assertEqual(
                    [item.operation_id for item in obligations],
                    [adopted.operation.operation_id],
                )
                no_receiver = (
                    registration_executor.StagedSecretTransfer.precreate(
                        clock_ns=harness._next_mono
                    )
                )
                with self.assertRaises(
                    registration_executor.SecretTransferError
                ) as failed_transfer:
                    store.transfer_staged_execution(
                        execution,
                        no_receiver,
                        deadline_ns=no_receiver.deadline_after(0.01),
                    )
                self.assertEqual(
                    getattr(failed_transfer.exception, "__notes__", []), []
                )
                self.assertFalse(execution.held)
                authority = store.read_selected_authority(member_id)
                self.assertIsNone(authority.status["executor_token_hash"])
                self.assertEqual(
                    authority.status["reason_code"], "RESOLVER_UNAVAILABLE"
                )
                self.assertEqual(store.unresolved_custody_obligations(), ())
                reacquired = store.reacquire_effect(
                    harness.staged_data(),
                    staged,
                    member_id=member_id,
                    expected_member_hash=authority.member["member_tuple_hash"],
                    expected_effect_hash=authority.effect["request_tuple_hash"],
                    expected_status_hash=authority.status["status_hash"],
                    executor_secret=b"b" * 32,
                )
                execution = reacquired.execution
                self.assertEqual(
                    [
                        item.operation_id
                        for item in store.unresolved_custody_obligations()
                    ],
                    [reacquired.operation.operation_id],
                )
                frame = registration_executor.StagedGrantFrame(
                    member_id=execution.member_id,
                    effect_id=execution.effect_id,
                    executor_token_hash=execution.executor_token_hash,
                    operation_id=execution.operation_id,
                    member_tuple_hash=execution.target_member_hash,
                    status_hash=execution.target_status_hash,
                    protocol_hash=execution.target_protocol_hash,
                    staged_epoch_hash=execution.target_staged_epoch_hash,
                )
                abandoned = (
                    registration_executor.StagedSecretTransfer.precreate(
                        clock_ns=harness._next_mono
                    )
                )
                abandoned_deadline = abandoned.deadline_after(0.05)
                received_ack = threading.Event()

                def receive_then_die() -> None:
                    received = abandoned.receive_frame(
                        deadline_ns=abandoned_deadline,
                        expected_frame_digest=frame.digest,
                    )
                    received_ack.set()
                    received.close()

                dead_receiver = threading.Thread(target=receive_then_die)
                dead_receiver.start()
                with self.assertRaises(
                    registration_executor.SecretTransferError
                ):
                    store.transfer_staged_execution(
                        execution,
                        abandoned,
                        deadline_ns=abandoned_deadline,
                    )
                dead_receiver.join(1)
                self.assertTrue(received_ack.is_set())
                self.assertFalse(dead_receiver.is_alive())
                self.assertFalse(execution.held)
                authority = store.read_selected_authority(member_id)
                self.assertIsNotNone(authority.status["executor_token_hash"])
                store.mark_dead_executor_unavailable(
                    harness.staged_data(),
                    staged,
                    member_id=member_id,
                    expected_status_hash=authority.status["status_hash"],
                )
                self.assertEqual(store.unresolved_custody_obligations(), ())
                authority = store.read_selected_authority(member_id)
                reacquired = store.reacquire_effect(
                    harness.staged_data(),
                    staged,
                    member_id=member_id,
                    expected_member_hash=authority.member["member_tuple_hash"],
                    expected_effect_hash=authority.effect["request_tuple_hash"],
                    expected_status_hash=authority.status["status_hash"],
                    executor_secret=b"c" * 32,
                )
                execution = reacquired.execution
                self.assertEqual(
                    [
                        item.operation_id
                        for item in store.unresolved_custody_obligations()
                    ],
                    [reacquired.operation.operation_id],
                )
                frame = registration_executor.StagedGrantFrame(
                    member_id=execution.member_id,
                    effect_id=execution.effect_id,
                    executor_token_hash=execution.executor_token_hash,
                    operation_id=execution.operation_id,
                    member_tuple_hash=execution.target_member_hash,
                    status_hash=execution.target_status_hash,
                    protocol_hash=execution.target_protocol_hash,
                    staged_epoch_hash=execution.target_staged_epoch_hash,
                )
                transfer = registration_executor.StagedSecretTransfer.precreate(
                    clock_ns=harness._next_mono
                )
                deadline = transfer.deadline_after(2)
                ready = threading.Event()
                target: dict[str, object] = {}

                def receive() -> None:
                    target_store = registration_store.RegistrationStore(
                        db,
                        free_bytes=lambda _fd: 2 * 1024**3,
                        boot_id=lambda: "boot-a",
                        mono_ns=harness._next_mono,
                        _test_profile_seal=registration_store._TEST_PROFILE_SEAL,
                    )
                    try:
                        ready.set()
                        received = target_store.receive_staged_execution(
                            transfer,
                            expected_frame_digest=frame.digest,
                            deadline_ns=deadline,
                        )
                        target["held"] = received.held
                        target["token"] = received.executor_token_hash
                        received.close()
                    except BaseException as error:
                        target["error"] = error
                    finally:
                        target_store.close()

                receiver = threading.Thread(target=receive)
                receiver.start()
                self.assertTrue(ready.wait(1))
                try:
                    store.transfer_staged_execution(
                        execution, transfer, deadline_ns=deadline
                    )
                finally:
                    receiver.join(2)
                    if execution.held:
                        execution.close()
                self.assertFalse(receiver.is_alive())
                self.assertNotIn("error", target)
                self.assertEqual(target["held"], True)
                self.assertEqual(
                    target["token"], execution.executor_token_hash
                )
                self.assertFalse(execution.held)
                self.assertEqual(store.unresolved_custody_obligations(), ())
                with registration_store.RegistrationStore(
                    db,
                    free_bytes=lambda _fd: 2 * 1024**3,
                    boot_id=lambda: "boot-a",
                    mono_ns=harness._next_mono,
                    _test_profile_seal=registration_store._TEST_PROFILE_SEAL,
                ) as restarted:
                    restarted_obligations = (
                        restarted.unresolved_custody_obligations()
                    )
                    self.assertEqual(
                        [item.operation_id for item in restarted_obligations],
                        [reacquired.operation.operation_id],
                    )
                authority = store.read_selected_authority(member_id)
                store.mark_dead_executor_unavailable(
                    harness.staged_data(),
                    staged,
                    member_id=member_id,
                    expected_status_hash=authority.status["status_hash"],
                )
                self.assertEqual(store.unresolved_custody_obligations(), ())

    def test_staged_custody_query_batches_more_than_eight_members(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=4 * 1024**3
            ) as harness:
                store = harness.store
                current = harness.candidate()
                staged = harness.staged_candidate()
                store.bootstrap(harness.control(), current)
                store.activate(harness.control(), current)
                secrets_by_member: dict[str, bytes] = {}
                for ordinal in range(1, 10):
                    store.install_member(
                        harness.data(),
                        current,
                        harness.identity(ordinal=ordinal),
                        harness.clean_intent(ordinal=ordinal),
                    )
                    member_id = harness.connection.execute(
                        "SELECT member_id FROM registration_member "
                        "WHERE canonical_root=?",
                        (f"/fixture/root-{ordinal}",),
                    ).fetchone()[0]
                    authority = store.read_selected_authority(member_id)
                    secret = bytes([ordinal]) * 32
                    opened = store.open_effect(
                        harness.data(),
                        current,
                        member_id=member_id,
                        expected_member_hash=authority.member[
                            "member_tuple_hash"
                        ],
                        expected_effect_hash=authority.effect[
                            "request_tuple_hash"
                        ],
                        expected_status_hash=authority.status["status_hash"],
                        executor_secret=secret,
                    )
                    opened.execution.close()
                    secrets_by_member[member_id] = secret
                store.begin_drain(harness.control(), current)
                store.stage_next(
                    harness.control(),
                    current,
                    staged,
                    quiescence_proof_hash="7" * 64,
                )
                operation_ids: dict[str, str] = {}
                for member_id in sorted(
                    secrets_by_member, key=lambda value: value.encode("utf-8")
                ):
                    authority = store.read_selected_authority(member_id)
                    adopted = store.adopt_effect(
                        harness.control(),
                        current,
                        member_id=member_id,
                        expected_member_hash=authority.member[
                            "member_tuple_hash"
                        ],
                        expected_status_hash=authority.status["status_hash"],
                        executor_secret=secrets_by_member[member_id],
                    )
                    operation_ids[member_id] = adopted.operation.operation_id
                    adopted.execution.close()
                obligations = store.unresolved_custody_obligations()
                self.assertEqual(len(obligations), 9)
                self.assertEqual(
                    [item.member_id for item in obligations],
                    sorted(
                        secrets_by_member,
                        key=lambda value: value.encode("utf-8"),
                    ),
                )
                self.assertEqual(
                    [item.operation_id for item in obligations],
                    [operation_ids[item.member_id] for item in obligations],
                )
                for item in obligations:
                    status = store.read_selected_authority(
                        item.member_id
                    ).status
                    store.mark_dead_executor_unavailable(
                        harness.staged_data(),
                        staged,
                        member_id=item.member_id,
                        expected_status_hash=status["status_hash"],
                    )
                self.assertEqual(store.unresolved_custody_obligations(), ())

    def test_seven_table_semantic_closure_rejects_tampered_rows(self) -> None:
        mutations = {
            "registration_protocol_epoch": (
                "UPDATE registration_protocol_epoch "
                "SET protocol_generation=protocol_generation+1"
            ),
            "registration_operation_audit": (
                "UPDATE registration_operation_audit "
                "SET expected_revision=expected_revision+1 "
                "WHERE operation_seq=(SELECT MAX(operation_seq) "
                "FROM registration_operation_audit)"
            ),
            "registration_member": (
                "UPDATE registration_member "
                "SET canonical_root=canonical_root||'-tampered'"
            ),
            "registration_effect": (
                "UPDATE registration_effect SET request_basis_hash='" + "c" * 64 + "'"
            ),
            "registration_effect_action": (
                "UPDATE registration_effect_action "
                "SET observed_wall_ns=observed_wall_ns+1"
            ),
            "registration_runtime_status": (
                "UPDATE registration_runtime_status "
                "SET status_version=status_version+1"
            ),
            "registration_episode": (
                "UPDATE registration_episode "
                "SET generation_id=generation_id||'-tampered'"
            ),
        }
        for table, statement in mutations.items():
            with self.subTest(table=table), tempfile.TemporaryDirectory() as tmp:
                db = Path(tmp) / "state" / "registration-v1" / "registration.db"
                with RegistrationHarness.open(
                    db, measured_free_bytes=2 * 1024**3
                ) as harness:
                    store = harness.store
                    candidate = harness.candidate()
                    store.bootstrap(harness.control(), candidate)
                    store.activate(harness.control(), candidate)
                    store.install_member(
                        harness.data(),
                        candidate,
                        harness.identity(),
                        harness.clean_intent(),
                        sample_boot_id="boot-a",
                        sample_mono_ns=1,
                    )
                    member_id = harness.connection.execute(
                        "SELECT member_id FROM registration_member"
                    ).fetchone()[0]
                    store.bind_episode(
                        harness.data(),
                        candidate,
                        member_id=member_id,
                        source=registration_store.EpisodeSource(
                            conversation_id="conversation-1",
                            generation_id="generation-1",
                            source_contract="cursor-hook/v1",
                            source_event="beforeSubmitPrompt",
                            workspace_roots_hash="a" * 64,
                        ),
                    )
                    episode_id = harness.connection.execute(
                        "SELECT episode_id FROM registration_episode"
                    ).fetchone()[0]
                    authority = store.read_selected_authority(
                        member_id, episode_id=episode_id
                    )
                    opened = store.open_effect(
                        harness.data(),
                        candidate,
                        member_id=member_id,
                        expected_member_hash=authority.member[
                            "member_tuple_hash"
                        ],
                        expected_effect_hash=authority.effect[
                            "request_tuple_hash"
                        ],
                        expected_status_hash=authority.status["status_hash"],
                        executor_secret=b"a" * 32,
                    )
                    store.append_action(
                        harness.data(),
                        candidate,
                        opened.execution,
                        observation_kind="OBSERVED_EXACT",
                        measured_postcondition_hash=harness.next_postcondition(),
                    )
                    opened.execution.close()
                    self.assertIsNotNone(
                        store.validate_semantic_closure(
                            member_id, episode_id=episode_id
                        )
                    )
                    external = sqlite3.connect(str(db), isolation_level=None)
                    try:
                        triggers = external.execute(
                            "SELECT name FROM sqlite_schema "
                            "WHERE type='trigger' AND tbl_name=?",
                            (table,),
                        ).fetchall()
                        for (trigger,) in triggers:
                            external.execute(
                                'DROP TRIGGER "' + trigger.replace('"', '""') + '"'
                            )
                        external.execute(statement)
                    finally:
                        external.close()
                    with self.assertRaises(registration_store.StoreError):
                        store.validate_semantic_closure(
                            member_id, episode_id=episode_id
                        )

    def test_open_effect_outcome_fields_are_null_total(self) -> None:
        mutations: dict[str, object] = {
            "outcome_kind": "SUCCESS",
            "outcome_helper_generation": 1,
            "outcome_tuple_hash": "a" * 64,
            "ledger_head_hash": "a" * 64,
            "first_conflict_event_seq": 1,
            "completion_blob": sqlite3.Binary(b"{}"),
            "completion_hash": "a" * 64,
            "final_basis_hash": "a" * 64,
            "proof_blob": sqlite3.Binary(b"{}"),
            "proof_hash": "a" * 64,
            "certificate_inputs_blob": sqlite3.Binary(b"{}"),
            "certificate_inputs_hash": "a" * 64,
            "certificate_hash": "a" * 64,
            "conflict_code": "ACTION_POSTCONDITION_DIVERGENT",
            "conflict_blob": sqlite3.Binary(b"{}"),
            "conflict_hash": "a" * 64,
            "superseded_by_effect_id": "a" * 64,
            "successor_transition_id": "a" * 64,
            "outcome_operation_seq": 1,
            "outcome_operation_id": "a" * 64,
            "outcome_operation_hash": "a" * 64,
        }
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                store.install_member(
                    harness.data(),
                    candidate,
                    harness.identity(),
                    harness.clean_intent(),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                member_id = harness.connection.execute(
                    "SELECT member_id FROM registration_member"
                ).fetchone()[0]
                external = sqlite3.connect(str(db))
                try:
                    self._drop_all_registration_triggers(external)
                    external.execute("PRAGMA ignore_check_constraints=ON")
                    for column, value in mutations.items():
                        with self.subTest(column=column):
                            external.execute(
                                f"UPDATE registration_effect SET {column}=? "
                                "WHERE effect_id=(SELECT current_effect_id "
                                "FROM registration_member)",
                                (value,),
                            )
                            external.commit()
                            with self.assertRaises(
                                registration_store.SemanticClosureError
                            ):
                                store.validate_semantic_closure(member_id)
                            external.execute(
                                f"UPDATE registration_effect SET {column}=NULL "
                                "WHERE effect_id=(SELECT current_effect_id "
                                "FROM registration_member)"
                            )
                            external.commit()
                finally:
                    external.close()
                self.assertIsNotNone(
                    store.validate_semantic_closure(member_id)
                )

    def test_protocol_semantic_totality_rejects_rehashed_mutations(self) -> None:
        mutations = (
            {"mode": "WRITABLE"},
            {"drain_boot_id": None},
            {"drain_deadline_mono_ns": None},
            {"transition_reason_code": "STAGE_NEXT"},
            {"quiescence_proof_hash": "a" * 64},
            {"runtime_capability_hash": "b" * 64},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                db = Path(tmp) / "state" / "registration-v1" / "registration.db"
                with RegistrationHarness.open(
                    db, measured_free_bytes=2 * 1024**3
                ) as harness:
                    store = harness.store
                    candidate = harness.candidate()
                    store.bootstrap(harness.control(), candidate)
                    store.activate(harness.control(), candidate)
                    store.begin_drain(harness.control(), candidate)
                    external = sqlite3.connect(str(db))
                    try:
                        self._drop_all_registration_triggers(external)
                        external.execute(
                            "PRAGMA ignore_check_constraints=ON"
                        )
                        self._rewrite_latest_protocol(
                            external, **mutation
                        )
                        external.commit()
                    finally:
                        external.close()
                    with self.assertRaises(
                        registration_store.SemanticClosureError
                    ):
                        store.current_protocol()

    def test_immediate_protocol_predecessor_is_semantically_validated(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                current = harness.candidate()
                store.bootstrap(harness.control(), current)
                store.activate(harness.control(), current)
                store.begin_drain(harness.control(), current)
                store.stage_next(
                    harness.control(),
                    current,
                    harness.staged_candidate(),
                    quiescence_proof_hash="9" * 64,
                )
                external = sqlite3.connect(str(db))
                external.row_factory = sqlite3.Row
                try:
                    self._drop_all_registration_triggers(external)
                    external.execute("PRAGMA ignore_check_constraints=ON")
                    latest_seq = external.execute(
                        "SELECT MAX(protocol_seq) "
                        "FROM registration_protocol_epoch"
                    ).fetchone()[0]
                    predecessor = dict(
                        external.execute(
                            "SELECT * FROM registration_protocol_epoch "
                            "WHERE protocol_seq=?",
                            (latest_seq - 1,),
                        ).fetchone()
                    )
                    predecessor["quiescence_proof_hash"] = "f" * 64
                    predecessor["protocol_hash"] = (
                        registration_hashes.derive(
                            "protocol_hash", predecessor
                        )
                    )
                    self._rewrite_operation_and_backlinks(
                        external,
                        predecessor["operation_id"],
                        target_protocol_hash=predecessor["protocol_hash"],
                    )
                    external.execute(
                        "UPDATE registration_protocol_epoch "
                        "SET quiescence_proof_hash=?,protocol_hash=? "
                        "WHERE protocol_seq=?",
                        (
                            predecessor["quiescence_proof_hash"],
                            predecessor["protocol_hash"],
                            predecessor["protocol_seq"],
                        ),
                    )
                    latest = dict(
                        external.execute(
                            "SELECT * FROM registration_protocol_epoch "
                            "WHERE protocol_seq=?",
                            (latest_seq,),
                        ).fetchone()
                    )
                    latest["previous_protocol_hash"] = predecessor[
                        "protocol_hash"
                    ]
                    latest["protocol_hash"] = registration_hashes.derive(
                        "protocol_hash", latest
                    )
                    self._rewrite_operation_and_backlinks(
                        external,
                        latest["operation_id"],
                        expected_protocol_hash=predecessor[
                            "protocol_hash"
                        ],
                        target_protocol_hash=latest["protocol_hash"],
                    )
                    external.execute(
                        "UPDATE registration_protocol_epoch "
                        "SET previous_protocol_hash=?,protocol_hash=? "
                        "WHERE protocol_seq=?",
                        (
                            latest["previous_protocol_hash"],
                            latest["protocol_hash"],
                            latest["protocol_seq"],
                        ),
                    )
                    external.commit()
                finally:
                    external.close()
                with self.assertRaises(
                    registration_store.SemanticClosureError
                ):
                    store.current_protocol()

    def test_noop_path_refuses_rehashed_protocol_corruption(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                store.install_member(
                    harness.data(),
                    candidate,
                    harness.identity(),
                    harness.clean_intent(),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                member_id = harness.connection.execute(
                    "SELECT member_id FROM registration_member"
                ).fetchone()[0]
                authority = store.read_selected_authority(member_id)
                external = sqlite3.connect(str(db))
                try:
                    self._drop_all_registration_triggers(external)
                    self._rewrite_latest_protocol(
                        external,
                        transition_reason_code="BEGIN_DRAIN",
                    )
                    external.commit()
                finally:
                    external.close()
                before = store.table_count("registration_operation_audit")
                with self.assertRaises(
                    registration_store.SemanticClosureError
                ):
                    store.invalidate_requested(
                        harness.data(),
                        candidate,
                        member_id=member_id,
                        expected_member_hash=authority.member[
                            "member_tuple_hash"
                        ],
                        expected_effect_hash=authority.effect[
                            "request_tuple_hash"
                        ],
                        expected_status_hash=authority.status["status_hash"],
                        basis=registration_store.BasisUpdate(
                            policy_basis_hash=authority.member[
                                "policy_basis_hash"
                            ],
                            operation_basis_hash=authority.member[
                                "operation_basis_hash"
                            ],
                            lifecycle_basis_hash=authority.member[
                                "lifecycle_basis_hash"
                            ],
                            current_basis_hash=authority.member[
                                "current_basis_hash"
                            ],
                        ),
                        intent=harness.clean_intent(),
                    )
                self.assertEqual(
                    store.table_count("registration_operation_audit"), before
                )

    def test_semantic_closure_rejects_jcs_backlink_and_action_chain_drift(
        self,
    ) -> None:
        for mutation in (
            "action_plan_blob",
            "observation_blob",
            "completion_blob",
            "member_backlink",
            "action_chain",
            "ready_relation",
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                db = Path(tmp) / "state" / "registration-v1" / "registration.db"
                with RegistrationHarness.open(
                    db, measured_free_bytes=2 * 1024**3
                ) as harness:
                    store = harness.store
                    candidate = harness.candidate()
                    store.bootstrap(harness.control(), candidate)
                    store.activate(harness.control(), candidate)
                    store.install_member(
                        harness.data(),
                        candidate,
                        harness.identity(),
                        harness.clean_intent(),
                        sample_boot_id="boot-a",
                        sample_mono_ns=1,
                    )
                    member_id = harness.connection.execute(
                        "SELECT member_id FROM registration_member"
                    ).fetchone()[0]
                    authority = store.read_selected_authority(member_id)
                    opened = store.open_effect(
                        harness.data(),
                        candidate,
                        member_id=member_id,
                        expected_member_hash=authority.member[
                            "member_tuple_hash"
                        ],
                        expected_effect_hash=authority.effect[
                            "request_tuple_hash"
                        ],
                        expected_status_hash=authority.status["status_hash"],
                        executor_secret=b"a" * 32,
                    )
                    action_count = {
                        "action_plan_blob": 0,
                        "member_backlink": 0,
                        "observation_blob": 1,
                        "action_chain": 2,
                        "completion_blob": 4,
                        "ready_relation": 4,
                    }[mutation]
                    for _index in range(action_count):
                        store.append_action(
                            harness.data(),
                            candidate,
                            opened.execution,
                            observation_kind="OBSERVED_EXACT",
                            measured_postcondition_hash=(
                                harness.next_postcondition(member_id)
                            ),
                        )
                    if mutation in {"completion_blob", "ready_relation"}:
                        store.close_success(
                            harness.data(),
                            candidate,
                            opened.execution,
                            final_basis_hash=(
                                harness.identity().current_basis_hash
                            ),
                        )
                    elif opened.execution.held:
                        opened.execution.close()
                    self.assertIsNotNone(
                        store.validate_semantic_closure(member_id)
                    )

                    external = sqlite3.connect(str(db), isolation_level=None)
                    external.row_factory = sqlite3.Row
                    try:
                        self._drop_all_registration_triggers(external)
                        if mutation in {
                            "action_plan_blob",
                            "observation_blob",
                            "completion_blob",
                        }:
                            table, column, where = {
                                "action_plan_blob": (
                                    "registration_effect",
                                    "action_plan_blob",
                                    "effect_id=(SELECT current_effect_id "
                                    "FROM registration_member)",
                                ),
                                "observation_blob": (
                                    "registration_effect_action",
                                    "observation_blob",
                                    "event_seq=1",
                                ),
                                "completion_blob": (
                                    "registration_effect",
                                    "completion_blob",
                                    "effect_id=(SELECT current_effect_id "
                                    "FROM registration_member)",
                                ),
                            }[mutation]
                            original = external.execute(
                                f"SELECT {column} FROM {table} WHERE {where}"
                            ).fetchone()[0]
                            external.execute(
                                f"UPDATE {table} SET {column}=? WHERE {where}",
                                (sqlite3.Binary(bytes(original) + b" "),),
                            )
                        elif mutation == "member_backlink":
                            external.execute(
                                "UPDATE registration_member "
                                "SET write_operation_seq=write_operation_seq+1"
                            )
                        elif mutation == "ready_relation":
                            status = dict(
                                external.execute(
                                    "SELECT * FROM "
                                    "registration_runtime_status"
                                ).fetchone()
                            )
                            status["reason_code"] = "STORE_UNAVAILABLE"
                            status["status_hash"] = (
                                registration_hashes.derive(
                                    "status_hash", status
                                )
                            )
                            operation_hash = (
                                self._rewrite_operation_and_backlinks(
                                    external,
                                    status["write_operation_id"],
                                    target_status_hash=status["status_hash"],
                                )
                            )
                            external.execute(
                                "UPDATE registration_runtime_status "
                                "SET reason_code=?,status_hash=?,"
                                "write_operation_hash=? WHERE member_id=?",
                                (
                                    status["reason_code"],
                                    status["status_hash"],
                                    operation_hash,
                                    status["member_id"],
                                ),
                            )
                            coherent = dict(
                                external.execute(
                                    "SELECT * FROM "
                                    "registration_runtime_status"
                                ).fetchone()
                            )
                            self.assertEqual(
                                registration_hashes.derive(
                                    "status_hash", coherent
                                ),
                                coherent["status_hash"],
                            )
                        else:
                            action = dict(
                                external.execute(
                                    "SELECT * FROM registration_effect_action "
                                    "WHERE event_seq=2"
                                ).fetchone()
                            )
                            action["prior_ledger_hash"] = "f" * 64
                            action["ledger_hash"] = registration_hashes.derive(
                                "ledger_hash", action
                            )
                            operation_hash = (
                                self._rewrite_operation_and_backlinks(
                                    external,
                                    action["write_operation_id"],
                                    target_action_ledger_hash=action[
                                        "ledger_hash"
                                    ],
                                )
                            )
                            external.execute(
                                "UPDATE registration_effect_action "
                                "SET prior_ledger_hash=?,ledger_hash=?,"
                                "write_operation_hash=? "
                                "WHERE effect_id=? AND event_seq=2",
                                (
                                    action["prior_ledger_hash"],
                                    action["ledger_hash"],
                                    operation_hash,
                                    action["effect_id"],
                                ),
                            )
                            coherent = dict(
                                external.execute(
                                    "SELECT * FROM registration_effect_action "
                                    "WHERE effect_id=? AND event_seq=2",
                                    (action["effect_id"],),
                                ).fetchone()
                            )
                            self.assertEqual(
                                registration_hashes.derive(
                                    "ledger_hash", coherent
                                ),
                                coherent["ledger_hash"],
                            )
                    finally:
                        external.close()
                    with self.assertRaises(registration_store.StoreError):
                        store.validate_semantic_closure(member_id)

    def test_semantic_closure_rejects_coherently_rehashed_descendant_lineage(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                store.install_member(
                    harness.data(),
                    candidate,
                    harness.identity(ordinal=1),
                    harness.clean_intent(ordinal=1),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                before = store.read_selected_authority(
                    harness.connection.execute(
                        "SELECT member_id FROM registration_member"
                    ).fetchone()[0]
                )
                changed = harness.identity(ordinal=2)
                store.invalidate_requested(
                    harness.data(),
                    candidate,
                    member_id=before.member["member_id"],
                    expected_member_hash=before.member["member_tuple_hash"],
                    expected_effect_hash=before.effect["request_tuple_hash"],
                    expected_status_hash=before.status["status_hash"],
                    basis=registration_store.BasisUpdate(
                        policy_basis_hash=changed.policy_basis_hash,
                        operation_basis_hash=changed.operation_basis_hash,
                        lifecycle_basis_hash=changed.lifecycle_basis_hash,
                        current_basis_hash=changed.current_basis_hash,
                    ),
                    intent=harness.clean_intent(ordinal=2),
                )
                authority = store.read_selected_authority(
                    before.member["member_id"]
                )
                predecessor = authority.predecessor_effect
                self.assertIsNotNone(predecessor)

                external = sqlite3.connect(str(db), isolation_level=None)
                external.row_factory = sqlite3.Row
                try:
                    self._drop_all_registration_triggers(external)
                    predecessor_row = dict(
                        external.execute(
                            "SELECT * FROM registration_effect "
                            "WHERE effect_id=?",
                            (predecessor["effect_id"],),
                        ).fetchone()
                    )
                    predecessor_row["superseded_by_effect_id"] = "f" * 64
                    predecessor_row["outcome_tuple_hash"] = (
                        registration_hashes.derive(
                            "outcome_tuple_hash", predecessor_row
                        )
                    )
                    operation_hash = self._rewrite_operation_and_backlinks(
                        external,
                        predecessor_row["outcome_operation_id"],
                        target_effect_outcome_hash=predecessor_row[
                            "outcome_tuple_hash"
                        ],
                    )
                    external.execute(
                        "UPDATE registration_effect "
                        "SET superseded_by_effect_id=?,"
                        "outcome_tuple_hash=?,outcome_operation_hash=? "
                        "WHERE effect_id=?",
                        (
                            predecessor_row["superseded_by_effect_id"],
                            predecessor_row["outcome_tuple_hash"],
                            operation_hash,
                            predecessor_row["effect_id"],
                        ),
                    )
                    coherent = dict(
                        external.execute(
                            "SELECT * FROM registration_effect "
                            "WHERE effect_id=?",
                            (predecessor_row["effect_id"],),
                        ).fetchone()
                    )
                    self.assertEqual(
                        registration_hashes.derive(
                            "outcome_tuple_hash", coherent
                        ),
                        coherent["outcome_tuple_hash"],
                    )
                finally:
                    external.close()
                with self.assertRaises(registration_store.StoreError):
                    store.validate_semantic_closure(
                        before.member["member_id"]
                    )

    def test_successor_transition_is_rederived_from_exact_companions(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                store.install_member(
                    harness.data(),
                    candidate,
                    harness.identity(ordinal=1),
                    harness.clean_intent(ordinal=1),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                member_id = harness.connection.execute(
                    "SELECT member_id FROM registration_member"
                ).fetchone()[0]
                authority = store.read_selected_authority(member_id)
                changed = harness.identity(ordinal=2)
                store.invalidate_requested(
                    harness.data(),
                    candidate,
                    member_id=member_id,
                    expected_member_hash=authority.member[
                        "member_tuple_hash"
                    ],
                    expected_effect_hash=authority.effect[
                        "request_tuple_hash"
                    ],
                    expected_status_hash=authority.status["status_hash"],
                    basis=registration_store.BasisUpdate(
                        policy_basis_hash=changed.policy_basis_hash,
                        operation_basis_hash=changed.operation_basis_hash,
                        lifecycle_basis_hash=changed.lifecycle_basis_hash,
                        current_basis_hash=changed.current_basis_hash,
                    ),
                    intent=harness.clean_intent(ordinal=2),
                )
                external = sqlite3.connect(str(db))
                external.row_factory = sqlite3.Row
                try:
                    self._drop_all_registration_triggers(external)
                    external.execute("PRAGMA ignore_check_constraints=ON")
                    successor = dict(
                        external.execute(
                            "SELECT * FROM registration_effect "
                            "WHERE effect_id=(SELECT current_effect_id "
                            "FROM registration_member)"
                        ).fetchone()
                    )
                    predecessor = dict(
                        external.execute(
                            "SELECT * FROM registration_effect "
                            "WHERE effect_id=?",
                            (successor["predecessor_effect_id"],),
                        ).fetchone()
                    )
                    operation = dict(
                        external.execute(
                            "SELECT * FROM registration_operation_audit "
                            "WHERE operation_id=?",
                            (predecessor["outcome_operation_id"],),
                        ).fetchone()
                    )
                    forged_cause = "CURRENT_CLOSURE_CHANGED"
                    forged_transition = (
                        registration_store.RegistrationStore
                        ._successor_transition_id(
                            operation_kind=operation["operation_kind"],
                            cause=forged_cause,
                            old_member_hash=operation[
                                "expected_target_member_tuple_hash"
                            ],
                            old_status_hash=operation[
                                "expected_target_status_hash"
                            ],
                            old_effect_hash=operation[
                                "expected_target_effect_tuple_hash"
                            ],
                            new_member_hash=operation[
                                "target_member_tuple_hash"
                            ],
                            new_status_hash=operation[
                                "target_status_hash"
                            ],
                            new_effect_hash=operation[
                                "target_effect_tuple_hash"
                            ],
                            old_epoch=predecessor["member_epoch"],
                            old_basis=predecessor["request_basis_hash"],
                            new_epoch=successor["member_epoch"],
                            new_basis=successor["request_basis_hash"],
                            old_effect_id=predecessor["effect_id"],
                            new_effect_id=successor["effect_id"],
                        )
                    )
                    predecessor["successor_transition_id"] = (
                        forged_transition
                    )
                    predecessor["outcome_tuple_hash"] = (
                        registration_hashes.derive(
                            "outcome_tuple_hash", predecessor
                        )
                    )
                    operation_hash = self._rewrite_operation_and_backlinks(
                        external,
                        operation["operation_id"],
                        target_transition_id=forged_transition,
                        target_cause_code=forged_cause,
                        target_effect_outcome_hash=predecessor[
                            "outcome_tuple_hash"
                        ],
                    )
                    external.execute(
                        "UPDATE registration_effect "
                        "SET successor_transition_id=?,outcome_tuple_hash=?,"
                        "outcome_operation_hash=? WHERE effect_id=?",
                        (
                            forged_transition,
                            predecessor["outcome_tuple_hash"],
                            operation_hash,
                            predecessor["effect_id"],
                        ),
                    )
                    external.commit()
                finally:
                    external.close()
                with self.assertRaises(
                    registration_store.SemanticClosureError
                ):
                    store.validate_semantic_closure(member_id)

    def test_semantic_closure_rejects_coherently_rehashed_adoption_lineage(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                current = harness.candidate()
                staged = harness.staged_candidate()
                store.bootstrap(harness.control(), current)
                store.activate(harness.control(), current)
                store.install_member(
                    harness.data(),
                    current,
                    harness.identity(),
                    harness.clean_intent(),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                member_id = harness.connection.execute(
                    "SELECT member_id FROM registration_member"
                ).fetchone()[0]
                authority = store.read_selected_authority(member_id)
                opened = store.open_effect(
                    harness.data(),
                    current,
                    member_id=member_id,
                    expected_member_hash=authority.member[
                        "member_tuple_hash"
                    ],
                    expected_effect_hash=authority.effect[
                        "request_tuple_hash"
                    ],
                    expected_status_hash=authority.status["status_hash"],
                    executor_secret=b"a" * 32,
                )
                opened.execution.close()
                store.begin_drain(harness.control(), current)
                store.stage_next(
                    harness.control(),
                    current,
                    staged,
                    quiescence_proof_hash="9" * 64,
                )
                authority = store.read_selected_authority(member_id)
                adopted = store.adopt_effect(
                    harness.control(),
                    current,
                    member_id=member_id,
                    expected_member_hash=authority.member[
                        "member_tuple_hash"
                    ],
                    expected_status_hash=authority.status["status_hash"],
                    executor_secret=b"a" * 32,
                )
                adopted.execution.close()
                authority = store.read_selected_authority(member_id)
                operation_id = authority.member["write_operation_id"]

                external = sqlite3.connect(str(db), isolation_level=None)
                external.row_factory = sqlite3.Row
                try:
                    self._drop_all_registration_triggers(external)
                    operation_hash = self._rewrite_operation_and_backlinks(
                        external,
                        operation_id,
                        lineage_effect_id="f" * 64,
                    )
                    operation = dict(
                        external.execute(
                            "SELECT * FROM registration_operation_audit "
                            "WHERE operation_id=?",
                            (operation_id,),
                        ).fetchone()
                    )
                    self.assertEqual(
                        registration_hashes.derive(
                            "operation_envelope_hash", operation
                        ),
                        operation_hash,
                    )
                finally:
                    external.close()
                with self.assertRaises(registration_store.StoreError):
                    store.validate_semantic_closure(member_id)

    def test_semantic_closure_rejects_coherently_rehashed_protocol_drift(
        self,
    ) -> None:
        for mutation in (
            "previous_protocol_hash",
            "staged_epoch_hash",
            "first_effect_lineage",
        ):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                db = Path(tmp) / "state" / "registration-v1" / "registration.db"
                with RegistrationHarness.open(
                    db, measured_free_bytes=2 * 1024**3
                ) as harness:
                    store = harness.store
                    current = harness.candidate()
                    store.bootstrap(harness.control(), current)
                    store.activate(harness.control(), current)
                    store.install_member(
                        harness.data(),
                        current,
                        harness.identity(),
                        harness.clean_intent(),
                        sample_boot_id="boot-a",
                        sample_mono_ns=1,
                    )
                    member_id = harness.connection.execute(
                        "SELECT member_id FROM registration_member"
                    ).fetchone()[0]
                    authority = store.read_selected_authority(member_id)
                    opened = store.open_effect(
                        harness.data(),
                        current,
                        member_id=member_id,
                        expected_member_hash=authority.member[
                            "member_tuple_hash"
                        ],
                        expected_effect_hash=authority.effect[
                            "request_tuple_hash"
                        ],
                        expected_status_hash=authority.status["status_hash"],
                        executor_secret=b"a" * 32,
                    )
                    opened.execution.close()
                    store.begin_drain(harness.control(), current)
                    store.stage_next(
                        harness.control(),
                        current,
                        harness.staged_candidate(),
                        quiescence_proof_hash="9" * 64,
                    )
                    self.assertIsNotNone(
                        store.validate_semantic_closure(member_id)
                    )

                    external = sqlite3.connect(str(db), isolation_level=None)
                    external.row_factory = sqlite3.Row
                    try:
                        self._drop_all_registration_triggers(external)
                        protocol = dict(
                            external.execute(
                                "SELECT * FROM registration_protocol_epoch "
                                "ORDER BY protocol_seq DESC LIMIT 1"
                            ).fetchone()
                        )
                        if mutation == "first_effect_lineage":
                            protocol["first_effect_id"] = "f" * 64
                            self._rewrite_operation_and_backlinks(
                                external,
                                protocol["first_effect_operation_id"],
                                target_effect_id=protocol[
                                    "first_effect_id"
                                ],
                            )
                            changed_column = "first_effect_id"
                        else:
                            protocol[mutation] = "f" * 64
                            changed_column = mutation
                        protocol["protocol_hash"] = (
                            registration_hashes.derive(
                                "protocol_hash", protocol
                            )
                        )
                        self._rewrite_operation_and_backlinks(
                            external,
                            protocol["operation_id"],
                            target_protocol_hash=protocol["protocol_hash"],
                        )
                        external.execute(
                            f"UPDATE registration_protocol_epoch "
                            f"SET {changed_column}=?,protocol_hash=? "
                            "WHERE protocol_seq=?",
                            (
                                protocol[changed_column],
                                protocol["protocol_hash"],
                                protocol["protocol_seq"],
                            ),
                        )
                        coherent = dict(
                            external.execute(
                                "SELECT * FROM registration_protocol_epoch "
                                "WHERE protocol_seq=?",
                                (protocol["protocol_seq"],),
                            ).fetchone()
                        )
                        self.assertEqual(
                            registration_hashes.derive(
                                "protocol_hash", coherent
                            ),
                            coherent["protocol_hash"],
                        )
                    finally:
                        external.close()
                    with self.assertRaises(registration_store.StoreError):
                        store.validate_semantic_closure(member_id)

    def test_semantic_closure_rejects_rehashed_authority_companion_drift(
        self,
    ) -> None:
        for mutation in (
            "operation_class",
            "executor_generation",
            "episode_generation",
        ):
            with (
                self.subTest(mutation=mutation),
                tempfile.TemporaryDirectory() as tmp,
            ):
                db = Path(tmp) / "state" / "registration-v1" / "registration.db"
                with RegistrationHarness.open(
                    db, measured_free_bytes=2 * 1024**3
                ) as harness:
                    store = harness.store
                    candidate = harness.candidate()
                    store.bootstrap(harness.control(), candidate)
                    store.activate(harness.control(), candidate)
                    store.install_member(
                        harness.data(),
                        candidate,
                        harness.identity(),
                        harness.clean_intent(),
                        sample_boot_id="boot-a",
                        sample_mono_ns=1,
                    )
                    member_id = harness.connection.execute(
                        "SELECT member_id FROM registration_member"
                    ).fetchone()[0]
                    episode = store.bind_episode(
                        harness.data(),
                        candidate,
                        member_id=member_id,
                        source=registration_store.EpisodeSource(
                            conversation_id="conversation-companion",
                            generation_id="generation-companion",
                            source_contract="cursor-hook/v1",
                            source_event="beforeSubmitPrompt",
                            workspace_roots_hash="a" * 64,
                        ),
                    )
                    episode_id = harness.connection.execute(
                        "SELECT episode_id FROM registration_episode"
                    ).fetchone()[0]
                    authority = store.read_selected_authority(member_id)
                    opened = store.open_effect(
                        harness.data(),
                        candidate,
                        member_id=member_id,
                        expected_member_hash=authority.member[
                            "member_tuple_hash"
                        ],
                        expected_effect_hash=authority.effect[
                            "request_tuple_hash"
                        ],
                        expected_status_hash=authority.status["status_hash"],
                        executor_secret=b"a" * 32,
                    )
                    opened.execution.close()
                    external = sqlite3.connect(str(db), isolation_level=None)
                    external.row_factory = sqlite3.Row
                    try:
                        self._drop_all_registration_triggers(external)
                        external.execute(
                            "PRAGMA ignore_check_constraints=ON"
                        )
                        if mutation == "operation_class":
                            operation_id = external.execute(
                                "SELECT write_operation_id "
                                "FROM registration_member"
                            ).fetchone()[0]
                            self._rewrite_operation_and_backlinks(
                                external,
                                operation_id,
                                operation_class="CONTROL",
                            )
                        elif mutation == "executor_generation":
                            status = dict(
                                external.execute(
                                    "SELECT * FROM registration_runtime_status"
                                ).fetchone()
                            )
                            status["executor_generation"] += 1
                            status["status_hash"] = (
                                registration_hashes.derive(
                                    "status_hash", status
                                )
                            )
                            operation_hash = (
                                self._rewrite_operation_and_backlinks(
                                    external,
                                    status["write_operation_id"],
                                    target_status_hash=status["status_hash"],
                                )
                            )
                            external.execute(
                                "UPDATE registration_runtime_status "
                                "SET executor_generation=?,status_hash=?,"
                                "write_operation_hash=? WHERE member_id=?",
                                (
                                    status["executor_generation"],
                                    status["status_hash"],
                                    operation_hash,
                                    member_id,
                                ),
                            )
                        else:
                            episode_row = dict(
                                external.execute(
                                    "SELECT * FROM registration_episode "
                                    "WHERE episode_id=?",
                                    (episode_id,),
                                ).fetchone()
                            )
                            episode_row["protocol_generation"] += 1
                            episode_row["envelope_hash"] = (
                                registration_hashes.derive(
                                    "episode_envelope_hash", episode_row
                                )
                            )
                            operation_hash = (
                                self._rewrite_operation_and_backlinks(
                                    external,
                                    episode.operation_id,
                                    target_episode_hash=episode_row[
                                        "envelope_hash"
                                    ],
                                )
                            )
                            external.execute(
                                "UPDATE registration_episode "
                                "SET protocol_generation=?,envelope_hash=?,"
                                "write_operation_hash=? WHERE episode_id=?",
                                (
                                    episode_row["protocol_generation"],
                                    episode_row["envelope_hash"],
                                    operation_hash,
                                    episode_id,
                                ),
                            )
                    finally:
                        external.close()
                    with self.assertRaises(registration_store.StoreError):
                        store.validate_semantic_closure(
                            member_id, episode_id=episode_id
                        )

    def test_success_and_logical_conflict_are_disjoint_and_reachable(self) -> None:
        for outcome in ("SUCCESS", "LOGICAL_CONFLICT"):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as tmp:
                db = Path(tmp) / "state" / "registration-v1" / "registration.db"
                with RegistrationHarness.open(
                    db, measured_free_bytes=2 * 1024**3
                ) as harness:
                    store = harness.store
                    candidate = harness.candidate()
                    store.bootstrap(harness.control(), candidate)
                    store.activate(harness.control(), candidate)
                    store.install_member(
                        harness.data(),
                        candidate,
                        harness.identity(),
                        harness.clean_intent(),
                        sample_boot_id="boot-a",
                        sample_mono_ns=1,
                    )
                    row = harness.connection.execute(
                        "SELECT m.member_id,m.member_tuple_hash,"
                        "e.request_tuple_hash,s.status_hash "
                        "FROM registration_member m "
                        "JOIN registration_effect e "
                        "ON e.effect_id=m.current_effect_id "
                        "JOIN registration_runtime_status s USING(member_id)"
                    ).fetchone()
                    opened = store.open_effect(
                        harness.data(),
                        candidate,
                        member_id=row["member_id"],
                        expected_member_hash=row["member_tuple_hash"],
                        expected_effect_hash=row["request_tuple_hash"],
                        expected_status_hash=row["status_hash"],
                        executor_secret=b"a" * 32,
                    )
                    if outcome == "SUCCESS":
                        for index in range(4):
                            store.append_action(
                                harness.data(),
                                candidate,
                                opened.execution,
                                observation_kind="OBSERVED_EXACT",
                                measured_postcondition_hash=(
                                    harness.next_postcondition()
                                ),
                            )
                        result = store.close_success(
                            harness.data(),
                            candidate,
                            opened.execution,
                            final_basis_hash=harness.identity().current_basis_hash,
                        )
                    else:
                        store.append_action(
                            harness.data(),
                            candidate,
                            opened.execution,
                            observation_kind="LOGICAL_CONFLICT",
                            measured_postcondition_hash="55" * 32,
                        )
                        result = store.close_conflict(
                            harness.data(),
                            candidate,
                            opened.execution,
                            conflict_code="PROOF_POSTCONDITION_DIVERGENT",
                            expected_hash="66" * 32,
                            observed_hash="77" * 32,
                        )
                    self.assertEqual(result.disposition, "COMMITTED")
                    closed = harness.connection.execute(
                        "SELECT m.phase,m.current_outcome_kind,"
                        "m.current_certificate_hash,m.current_conflict_hash,"
                        "e.outcome_kind,e.certificate_hash,e.conflict_hash "
                        "FROM registration_member m "
                        "JOIN registration_effect e "
                        "ON e.effect_id=m.current_effect_id"
                    ).fetchone()
                    self.assertEqual(closed["phase"], "RESOLVED")
                    self.assertEqual(closed["outcome_kind"], outcome)
                    if outcome == "SUCCESS":
                        self.assertIsNotNone(closed["certificate_hash"])
                        self.assertIsNone(closed["conflict_hash"])
                    else:
                        self.assertIsNone(closed["certificate_hash"])
                        self.assertIsNotNone(closed["conflict_hash"])

    def test_close_counter_reset_and_carry_are_outcome_sensitive(self) -> None:
        for outcome, pending, expected in (
            ("SUCCESS", False, (0, 0)),
            ("SUCCESS", True, (1, 1)),
            ("LOGICAL_CONFLICT", False, (1, 1)),
        ):
            with (
                self.subTest(outcome=outcome, pending=pending),
                tempfile.TemporaryDirectory() as tmp,
            ):
                db = Path(tmp) / "state" / "registration-v1" / "registration.db"
                with RegistrationHarness.open(
                    db, measured_free_bytes=2 * 1024**3
                ) as harness:
                    store = harness.store
                    candidate = harness.candidate()
                    store.bootstrap(harness.control(), candidate)
                    store.activate(harness.control(), candidate)
                    store.install_member(
                        harness.data(),
                        candidate,
                        harness.identity(),
                        harness.clean_intent(),
                        sample_boot_id="boot-a",
                        sample_mono_ns=1,
                    )
                    row = harness.connection.execute(
                        "SELECT m.member_id,m.member_tuple_hash,"
                        "e.request_tuple_hash,s.status_hash "
                        "FROM registration_member m "
                        "JOIN registration_effect e "
                        "ON e.effect_id=m.current_effect_id "
                        "JOIN registration_runtime_status s USING(member_id)"
                    ).fetchone()
                    opened = store.open_effect(
                        harness.data(),
                        candidate,
                        member_id=row["member_id"],
                        expected_member_hash=row["member_tuple_hash"],
                        expected_effect_hash=row["request_tuple_hash"],
                        expected_status_hash=row["status_hash"],
                    )
                    store.mark_unavailable(
                        harness.data(), candidate, opened.execution
                    )
                    due = harness.connection.execute(
                        "SELECT m.member_id,m.member_tuple_hash,"
                        "e.request_tuple_hash,s.status_hash "
                        "FROM registration_member m "
                        "JOIN registration_effect e "
                        "ON e.effect_id=m.current_effect_id "
                        "JOIN registration_runtime_status s USING(member_id)"
                    ).fetchone()
                    if pending:
                        identity = harness.identity(ordinal=2)
                        store.set_pending(
                            harness.data(),
                            candidate,
                            member_id=due["member_id"],
                            expected_member_hash=due["member_tuple_hash"],
                            expected_effect_hash=due["request_tuple_hash"],
                            expected_status_hash=due["status_hash"],
                            basis_hash=identity.current_basis_hash,
                            intent=harness.clean_intent(ordinal=2),
                        )
                        due = harness.connection.execute(
                            "SELECT m.member_id,m.member_tuple_hash,"
                            "e.request_tuple_hash,s.status_hash "
                            "FROM registration_member m "
                            "JOIN registration_effect e "
                            "ON e.effect_id=m.current_effect_id "
                            "JOIN registration_runtime_status s USING(member_id)"
                        ).fetchone()
                    execution = store.reacquire_effect(
                        harness.data(),
                        candidate,
                        member_id=due["member_id"],
                        expected_member_hash=due["member_tuple_hash"],
                        expected_effect_hash=due["request_tuple_hash"],
                        expected_status_hash=due["status_hash"],
                    ).execution
                    if outcome == "SUCCESS":
                        for _ in range(4):
                            store.append_action(
                                harness.data(),
                                candidate,
                                execution,
                                observation_kind="OBSERVED_EXACT",
                                measured_postcondition_hash=(
                                    harness.next_postcondition()
                                ),
                            )
                        store.close_success(
                            harness.data(),
                            candidate,
                            execution,
                            final_basis_hash=(
                                harness.identity().current_basis_hash
                            ),
                        )
                    else:
                        store.append_action(
                            harness.data(),
                            candidate,
                            execution,
                            observation_kind="LOGICAL_CONFLICT",
                            measured_postcondition_hash="ff" * 32,
                        )
                        store.close_conflict(
                            harness.data(),
                            candidate,
                            execution,
                            conflict_code="FINAL_BASIS_DIVERGENT",
                            expected_hash="ee" * 32,
                            observed_hash="ff" * 32,
                        )
                    counters = harness.connection.execute(
                        "SELECT unavailable_count,yield_count "
                        "FROM registration_runtime_status"
                    ).fetchone()
                    self.assertEqual(tuple(counters), expected)

    def test_drain_stage_cancel_advance_and_containment_edges(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                proof = "aa" * 32
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                store.begin_drain(harness.control(), candidate)
                with self.assertRaises(registration_store.StaleAuthority):
                    store.stage_next(
                        harness.control(),
                        candidate,
                        replace(
                            candidate,
                            storage_dev=candidate.storage_dev + 1,
                        ),
                        quiescence_proof_hash=proof,
                    )
                store.stage_next(
                    harness.control(),
                    candidate,
                    candidate,
                    quiescence_proof_hash=proof,
                )
                store.stage_next(
                    harness.control(),
                    candidate,
                    candidate,
                    quiescence_proof_hash=proof,
                )
                store.cancel_drain(
                    harness.control(),
                    candidate,
                    quiescence_proof_hash=proof,
                )
                self.assertEqual(store.current_protocol()["mode"], "DORMANT")

                store.activate(harness.control(), candidate)
                store.begin_drain(harness.control(), candidate)
                store.pre_effect_dormant(
                    harness.control(),
                    candidate,
                    absence_proof_hash="bb" * 32,
                )
                self.assertEqual(store.current_protocol()["mode"], "DORMANT")

                store.activate(harness.control(), candidate)
                store.begin_drain(harness.control(), candidate)
                store.stage_next(
                    harness.control(),
                    candidate,
                    candidate,
                    quiescence_proof_hash=proof,
                )
                old_device = store.current_protocol()["storage_dev"]
                store.advance_generation(
                    harness.control(),
                    candidate,
                    quiescence_proof_hash=proof,
                )
                current = store.current_protocol()
                self.assertEqual(current["mode"], "WRITABLE")
                self.assertEqual(current["protocol_generation"], 2)
                self.assertEqual(current["storage_dev"], old_device)

                store.begin_drain(harness.control(), candidate)
                harness.sample_boot_id = "boot-b"
                store.enter_containment(
                    harness.control(),
                    candidate,
                    reason="DRAIN_BOOT_CHANGED",
                )
                self.assertEqual(store.current_protocol()["mode"], "CONTAINMENT")
                store.begin_repair(harness.control(), candidate)
                self.assertEqual(store.current_protocol()["mode"], "DRAINING")

    def test_pre_effect_dormant_rejects_after_first_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                store.install_member(
                    harness.data(),
                    candidate,
                    harness.identity(),
                    harness.clean_intent(),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                row = harness.connection.execute(
                    "SELECT m.member_id,m.member_tuple_hash,e.request_tuple_hash,"
                    "s.status_hash FROM registration_member m "
                    "JOIN registration_effect e ON e.effect_id=m.current_effect_id "
                    "JOIN registration_runtime_status s USING(member_id)"
                ).fetchone()
                execution = store.open_effect(
                    harness.data(),
                    candidate,
                    member_id=row["member_id"],
                    expected_member_hash=row["member_tuple_hash"],
                    expected_effect_hash=row["request_tuple_hash"],
                    expected_status_hash=row["status_hash"],
                ).execution
                execution.close()
                store.begin_drain(harness.control(), candidate)
                with self.assertRaises(sqlite3.IntegrityError):
                    store.pre_effect_dormant(
                        harness.control(),
                        candidate,
                        absence_proof_hash="aa" * 32,
                    )

    def test_drain_refuses_clean_requested_effect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                store.install_member(
                    harness.data(),
                    candidate,
                    harness.identity(),
                    harness.clean_intent(),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                before = store.current_protocol()["protocol_hash"]
                with self.assertRaises(sqlite3.IntegrityError):
                    store.begin_drain(harness.control(), candidate)
                self.assertEqual(store.current_protocol()["protocol_hash"], before)

    def test_episode_binding_is_exact_and_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                installed = store.install_member(
                    harness.data(),
                    candidate,
                    harness.identity(),
                    harness.clean_intent(),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                member_id = harness.connection.execute(
                    "SELECT member_id FROM registration_member "
                    "WHERE member_tuple_hash=?",
                    (installed.target_hash,),
                ).fetchone()[0]
                result = store.bind_episode(
                    harness.data(),
                    candidate,
                    member_id=member_id,
                    source=registration_store.EpisodeSource(
                        conversation_id="conversation-1",
                        generation_id="generation-1",
                        source_contract="cursor-hook/v1",
                        source_event="beforeSubmitPrompt",
                        workspace_roots_hash="aa" * 32,
                    ),
                )
                self.assertEqual(result.disposition, "COMMITTED")
                with self.assertRaises(sqlite3.DatabaseError):
                    harness.connection.execute(
                        "UPDATE registration_episode SET generation_id='x'"
                    )

    def test_requested_invalidation_supersedes_without_executor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                store.install_member(
                    harness.data(),
                    candidate,
                    harness.identity(ordinal=1),
                    harness.clean_intent(ordinal=1),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                before = harness.connection.execute(
                    "SELECT m.member_id,m.member_tuple_hash,m.current_effect_id,"
                    "e.request_tuple_hash,s.status_hash "
                    "FROM registration_member m "
                    "JOIN registration_effect e ON e.effect_id=m.current_effect_id "
                    "JOIN registration_runtime_status s USING(member_id)"
                ).fetchone()
                changed = harness.identity(ordinal=2)
                result = store.invalidate_requested(
                    harness.data(),
                    candidate,
                    member_id=before["member_id"],
                    expected_member_hash=before["member_tuple_hash"],
                    expected_effect_hash=before["request_tuple_hash"],
                    expected_status_hash=before["status_hash"],
                    basis=registration_store.BasisUpdate(
                        policy_basis_hash=changed.policy_basis_hash,
                        operation_basis_hash=changed.operation_basis_hash,
                        lifecycle_basis_hash=changed.lifecycle_basis_hash,
                        current_basis_hash=changed.current_basis_hash,
                    ),
                    intent=harness.clean_intent(ordinal=2),
                )
                self.assertEqual(result.disposition, "COMMITTED")
                current = harness.connection.execute(
                    "SELECT member_epoch,phase,current_effect_id "
                    "FROM registration_member"
                ).fetchone()
                self.assertEqual(tuple(current)[:2], (2, "REQUESTED"))
                prior = harness.connection.execute(
                    "SELECT outcome_kind,superseded_by_effect_id "
                    "FROM registration_effect WHERE effect_id=?",
                    (before["current_effect_id"],),
                ).fetchone()
                self.assertEqual(prior["outcome_kind"], "SUPERSEDED")
                self.assertEqual(
                    prior["superseded_by_effect_id"], current["current_effect_id"]
                )

    def test_inflight_pending_set_and_replace_preserve_active_effect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                store.install_member(
                    harness.data(),
                    candidate,
                    harness.identity(ordinal=1),
                    harness.clean_intent(ordinal=1),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                initial = harness.connection.execute(
                    "SELECT m.member_id,m.member_tuple_hash,m.current_effect_id,"
                    "e.request_tuple_hash,s.status_hash "
                    "FROM registration_member m "
                    "JOIN registration_effect e ON e.effect_id=m.current_effect_id "
                    "JOIN registration_runtime_status s USING(member_id)"
                ).fetchone()
                opened = store.open_effect(
                    harness.data(),
                    candidate,
                    member_id=initial["member_id"],
                    expected_member_hash=initial["member_tuple_hash"],
                    expected_effect_hash=initial["request_tuple_hash"],
                    expected_status_hash=initial["status_hash"],
                    executor_secret=b"a" * 32,
                )
                active_effect = opened.execution.effect_id
                opened.execution.close()  # deterministic process-death fixture
                live = harness.connection.execute(
                    "SELECT m.member_id,m.member_tuple_hash,e.request_tuple_hash,"
                    "s.status_hash FROM registration_member m "
                    "JOIN registration_effect e ON e.effect_id=m.current_effect_id "
                    "JOIN registration_runtime_status s USING(member_id)"
                ).fetchone()
                second = harness.identity(ordinal=2)
                store.set_pending(
                    harness.data(),
                    candidate,
                    member_id=live["member_id"],
                    expected_member_hash=live["member_tuple_hash"],
                    expected_effect_hash=live["request_tuple_hash"],
                    expected_status_hash=live["status_hash"],
                    basis_hash=second.current_basis_hash,
                    intent=harness.clean_intent(ordinal=2),
                )
                pending = harness.connection.execute(
                    "SELECT m.member_id,m.member_tuple_hash,m.current_effect_id,"
                    "m.pending_effect_id,m.pending_effect_tuple_hash,s.status_hash "
                    "FROM registration_member m "
                    "JOIN registration_runtime_status s USING(member_id)"
                ).fetchone()
                self.assertEqual(pending["current_effect_id"], active_effect)
                old_pending = pending["pending_effect_id"]
                third = harness.identity(ordinal=3)
                store.replace_pending(
                    harness.data(),
                    candidate,
                    member_id=pending["member_id"],
                    expected_member_hash=pending["member_tuple_hash"],
                    expected_effect_hash=pending["pending_effect_tuple_hash"],
                    expected_status_hash=pending["status_hash"],
                    basis_hash=third.current_basis_hash,
                    intent=harness.clean_intent(ordinal=3),
                )
                replaced = harness.connection.execute(
                    "SELECT current_effect_id,pending_effect_id "
                    "FROM registration_member"
                ).fetchone()
                self.assertEqual(replaced["current_effect_id"], active_effect)
                self.assertNotEqual(replaced["pending_effect_id"], old_pending)
                superseded = harness.connection.execute(
                    "SELECT outcome_kind,superseded_by_effect_id "
                    "FROM registration_effect WHERE effect_id=?",
                    (old_pending,),
                ).fetchone()
                self.assertEqual(superseded["outcome_kind"], "SUPERSEDED")
                self.assertEqual(
                    superseded["superseded_by_effect_id"],
                    replaced["pending_effect_id"],
                )

    def test_resolved_pending_handoff_and_unchanged_success_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                store.install_member(
                    harness.data(),
                    candidate,
                    harness.identity(ordinal=1),
                    harness.clean_intent(ordinal=1),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                initial = harness.connection.execute(
                    "SELECT m.member_id,m.member_tuple_hash,e.request_tuple_hash,"
                    "s.status_hash FROM registration_member m "
                    "JOIN registration_effect e ON e.effect_id=m.current_effect_id "
                    "JOIN registration_runtime_status s USING(member_id)"
                ).fetchone()
                opened = store.open_effect(
                    harness.data(),
                    candidate,
                    member_id=initial["member_id"],
                    expected_member_hash=initial["member_tuple_hash"],
                    expected_effect_hash=initial["request_tuple_hash"],
                    expected_status_hash=initial["status_hash"],
                    executor_secret=b"a" * 32,
                )
                store.mark_unavailable(
                    harness.data(), candidate, opened.execution
                )
                unavailable = harness.connection.execute(
                    "SELECT m.member_id,m.member_tuple_hash,e.request_tuple_hash,"
                    "s.status_hash FROM registration_member m "
                    "JOIN registration_effect e ON e.effect_id=m.current_effect_id "
                    "JOIN registration_runtime_status s USING(member_id)"
                ).fetchone()
                pending_basis = harness.identity(ordinal=2)
                store.set_pending(
                    harness.data(),
                    candidate,
                    member_id=unavailable["member_id"],
                    expected_member_hash=unavailable["member_tuple_hash"],
                    expected_effect_hash=unavailable["request_tuple_hash"],
                    expected_status_hash=unavailable["status_hash"],
                    basis_hash=pending_basis.current_basis_hash,
                    intent=harness.clean_intent(ordinal=2),
                )
                due = harness.connection.execute(
                    "SELECT m.member_id,m.member_tuple_hash,e.request_tuple_hash,"
                    "s.status_hash FROM registration_member m "
                    "JOIN registration_effect e ON e.effect_id=m.current_effect_id "
                    "JOIN registration_runtime_status s USING(member_id)"
                ).fetchone()
                reacquired = store.reacquire_effect(
                    harness.data(),
                    candidate,
                    member_id=due["member_id"],
                    expected_member_hash=due["member_tuple_hash"],
                    expected_effect_hash=due["request_tuple_hash"],
                    expected_status_hash=due["status_hash"],
                    executor_secret=b"b" * 32,
                )
                for index in range(4):
                    store.append_action(
                        harness.data(),
                        candidate,
                        reacquired.execution,
                        observation_kind="OBSERVED_EXACT",
                        measured_postcondition_hash=harness.next_postcondition(),
                    )
                store.close_success(
                    harness.data(),
                    candidate,
                    reacquired.execution,
                    final_basis_hash=harness.identity().current_basis_hash,
                )
                resolved = harness.connection.execute(
                    "SELECT m.member_id,m.member_tuple_hash,m.pending_effect_id,"
                    "e.outcome_tuple_hash,s.status_hash "
                    "FROM registration_member m "
                    "JOIN registration_effect e ON e.effect_id=m.current_effect_id "
                    "JOIN registration_runtime_status s USING(member_id)"
                ).fetchone()
                self.assertIsNotNone(resolved["pending_effect_id"])
                store.handoff_resolved(
                    harness.data(),
                    candidate,
                    member_id=resolved["member_id"],
                    expected_member_hash=resolved["member_tuple_hash"],
                    expected_effect_hash=resolved["outcome_tuple_hash"],
                    expected_status_hash=resolved["status_hash"],
                    basis=registration_store.BasisUpdate(
                        policy_basis_hash=pending_basis.policy_basis_hash,
                        operation_basis_hash=pending_basis.operation_basis_hash,
                        lifecycle_basis_hash=pending_basis.lifecycle_basis_hash,
                        current_basis_hash=pending_basis.current_basis_hash,
                    ),
                )
                requested = harness.connection.execute(
                    "SELECT phase,member_epoch,current_effect_id,pending_effect_id "
                    "FROM registration_member"
                ).fetchone()
                self.assertEqual(requested["phase"], "REQUESTED")
                self.assertIsNone(requested["pending_effect_id"])
                successor_authority = store.read_selected_authority(
                    initial["member_id"]
                )
                successor = store.open_effect(
                    harness.data(),
                    candidate,
                    member_id=initial["member_id"],
                    expected_member_hash=successor_authority.member[
                        "member_tuple_hash"
                    ],
                    expected_effect_hash=successor_authority.effect[
                        "request_tuple_hash"
                    ],
                    expected_status_hash=successor_authority.status[
                        "status_hash"
                    ],
                    executor_secret=b"c" * 32,
                )
                self.assertIsInstance(
                    store.mark_unavailable(
                        harness.data(),
                        candidate,
                        successor.execution,
                    ),
                    registration_store.OperationResult,
                )

        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                store.install_member(
                    harness.data(),
                    candidate,
                    harness.identity(),
                    harness.clean_intent(),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                current = harness.connection.execute(
                    "SELECT m.member_id,m.member_tuple_hash,e.request_tuple_hash,"
                    "s.status_hash FROM registration_member m "
                    "JOIN registration_effect e ON e.effect_id=m.current_effect_id "
                    "JOIN registration_runtime_status s USING(member_id)"
                ).fetchone()
                execution = store.open_effect(
                    harness.data(),
                    candidate,
                    member_id=current["member_id"],
                    expected_member_hash=current["member_tuple_hash"],
                    expected_effect_hash=current["request_tuple_hash"],
                    expected_status_hash=current["status_hash"],
                ).execution
                for index in range(4):
                    store.append_action(
                        harness.data(),
                        candidate,
                        execution,
                        observation_kind="OBSERVED_EXACT",
                        measured_postcondition_hash=harness.next_postcondition(),
                    )
                store.close_success(
                    harness.data(),
                    candidate,
                    execution,
                    final_basis_hash=harness.identity().current_basis_hash,
                )
                stable = harness.connection.execute(
                    "SELECT m.member_id,m.member_tuple_hash,"
                    "e.outcome_tuple_hash,s.status_hash "
                    "FROM registration_member m "
                    "JOIN registration_effect e ON e.effect_id=m.current_effect_id "
                    "JOIN registration_runtime_status s USING(member_id)"
                ).fetchone()
                before_count = store.table_count(
                    "registration_operation_audit"
                )
                noop = store.handoff_resolved(
                    harness.data(),
                    candidate,
                    member_id=stable["member_id"],
                    expected_member_hash=stable["member_tuple_hash"],
                    expected_effect_hash=stable["outcome_tuple_hash"],
                    expected_status_hash=stable["status_hash"],
                )
                self.assertEqual(noop.disposition, "NOOP")
                self.assertEqual(
                    store.table_count("registration_operation_audit"),
                    before_count,
                )

    def test_adopt_replacement_handoff_starts_successor_recovery_budget(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                store.install_member(
                    harness.data(),
                    candidate,
                    harness.identity(),
                    harness.clean_intent(),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                member_id = harness.connection.execute(
                    "SELECT member_id FROM registration_member"
                ).fetchone()[0]
                authority = store.read_selected_authority(member_id)
                opened = store.open_effect(
                    harness.data(),
                    candidate,
                    member_id=member_id,
                    expected_member_hash=authority.member[
                        "member_tuple_hash"
                    ],
                    expected_effect_hash=authority.effect[
                        "request_tuple_hash"
                    ],
                    expected_status_hash=authority.status["status_hash"],
                    executor_secret=b"a" * 32,
                )
                store.mark_unavailable(
                    harness.data(), candidate, opened.execution
                )
                authority = store.read_selected_authority(member_id)
                pending_identity = harness.identity(ordinal=2)
                store.set_pending(
                    harness.data(),
                    candidate,
                    member_id=member_id,
                    expected_member_hash=authority.member[
                        "member_tuple_hash"
                    ],
                    expected_effect_hash=authority.effect[
                        "request_tuple_hash"
                    ],
                    expected_status_hash=authority.status["status_hash"],
                    basis_hash=pending_identity.current_basis_hash,
                    intent=harness.clean_intent(ordinal=2),
                )
                store.begin_drain(harness.control(), candidate)
                store.stage_next(
                    harness.control(),
                    candidate,
                    candidate,
                    quiescence_proof_hash="a" * 64,
                )
                authority = store.read_selected_authority(member_id)
                replacement_identity = harness.identity(ordinal=3)
                adopted = store.adopt_effect(
                    harness.control(),
                    candidate,
                    member_id=member_id,
                    expected_member_hash=authority.member[
                        "member_tuple_hash"
                    ],
                    expected_status_hash=authority.status["status_hash"],
                    replacement_intent=harness.clean_intent(ordinal=3),
                    replacement_basis_hash=(
                        replacement_identity.current_basis_hash
                    ),
                    executor_secret=b"b" * 32,
                )
                adopted.execution.close()
                authority = store.read_selected_authority(member_id)
                store.mark_dead_executor_unavailable(
                    harness.data(),
                    candidate,
                    member_id=member_id,
                    expected_status_hash=authority.status["status_hash"],
                )
                store.advance_generation(
                    harness.control(),
                    candidate,
                    quiescence_proof_hash="b" * 64,
                )
                authority = store.read_selected_authority(member_id)
                active = store.reacquire_effect(
                    harness.data(),
                    candidate,
                    member_id=member_id,
                    expected_member_hash=authority.member[
                        "member_tuple_hash"
                    ],
                    expected_effect_hash=authority.effect[
                        "request_tuple_hash"
                    ],
                    expected_status_hash=authority.status["status_hash"],
                    executor_secret=b"c" * 32,
                )
                for _ in range(4):
                    store.append_action(
                        harness.data(),
                        candidate,
                        active.execution,
                        observation_kind="OBSERVED_EXACT",
                        measured_postcondition_hash=(
                            harness.next_postcondition()
                        ),
                    )
                store.close_success(
                    harness.data(),
                    candidate,
                    active.execution,
                    final_basis_hash=harness.identity().current_basis_hash,
                )
                authority = store.read_selected_authority(member_id)
                store.handoff_resolved(
                    harness.data(),
                    candidate,
                    member_id=member_id,
                    expected_member_hash=authority.member[
                        "member_tuple_hash"
                    ],
                    expected_effect_hash=authority.effect[
                        "outcome_tuple_hash"
                    ],
                    expected_status_hash=authority.status["status_hash"],
                    basis=registration_store.BasisUpdate(
                        policy_basis_hash=(
                            replacement_identity.policy_basis_hash
                        ),
                        operation_basis_hash=(
                            replacement_identity.operation_basis_hash
                        ),
                        lifecycle_basis_hash=(
                            replacement_identity.lifecycle_basis_hash
                        ),
                        current_basis_hash=(
                            replacement_identity.current_basis_hash
                        ),
                    ),
                )
                authority = store.read_selected_authority(member_id)
                successor = store.open_effect(
                    harness.data(),
                    candidate,
                    member_id=member_id,
                    expected_member_hash=authority.member[
                        "member_tuple_hash"
                    ],
                    expected_effect_hash=authority.effect[
                        "request_tuple_hash"
                    ],
                    expected_status_hash=authority.status["status_hash"],
                    executor_secret=b"d" * 32,
                )
                self.assertIsInstance(
                    store.mark_unavailable(
                        harness.data(),
                        candidate,
                        successor.execution,
                    ),
                    registration_store.OperationResult,
                )

    def test_reboot_and_schedule_status_use_fresh_boot_fences(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                store.install_member(
                    harness.data(),
                    candidate,
                    harness.identity(),
                    harness.clean_intent(),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                row = harness.connection.execute(
                    "SELECT member_id,status_hash FROM registration_runtime_status"
                ).fetchone()
                harness.sample_boot_id = "boot-b"
                rebooted = store.reboot_status(
                    harness.data(),
                    candidate,
                    member_id=row["member_id"],
                    expected_status_hash=row["status_hash"],
                )
                status = harness.connection.execute(
                    "SELECT * FROM registration_runtime_status"
                ).fetchone()
                self.assertEqual(status["schedule_boot_id"], "boot-b")
                self.assertEqual(status["backoff_ns"], 0)
                scheduled = store.schedule_status(
                    harness.data(),
                    candidate,
                    member_id=row["member_id"],
                    expected_status_hash=rebooted.target_hash,
                    attempt_count=1,
                    backoff_ns=10,
                )
                status = harness.connection.execute(
                    "SELECT * FROM registration_runtime_status"
                ).fetchone()
                self.assertEqual(status["status_hash"], scheduled.target_hash)
                self.assertEqual(
                    status["next_due_mono_ns"],
                    status["observed_now_mono_ns"] + 10,
                )
                with self.assertRaises(registration_store.StaleAuthority):
                    store.reboot_status(
                        harness.data(),
                        candidate,
                        member_id=row["member_id"],
                        expected_status_hash=status["status_hash"],
                    )

    def test_staged_adoption_preserves_executor_and_single_hop_fence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                store.install_member(
                    harness.data(),
                    candidate,
                    harness.identity(),
                    harness.clean_intent(),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                before = harness.connection.execute(
                    "SELECT m.member_id,m.member_tuple_hash,e.request_tuple_hash,"
                    "s.status_hash FROM registration_member m "
                    "JOIN registration_effect e ON e.effect_id=m.current_effect_id "
                    "JOIN registration_runtime_status s USING(member_id)"
                ).fetchone()
                secret = b"a" * 32
                opened = store.open_effect(
                    harness.data(),
                    candidate,
                    member_id=before["member_id"],
                    expected_member_hash=before["member_tuple_hash"],
                    expected_effect_hash=before["request_tuple_hash"],
                    expected_status_hash=before["status_hash"],
                    executor_secret=secret,
                )
                opened.execution.close()  # staged transfer quiescence fixture
                store.begin_drain(harness.control(), candidate)
                store.stage_next(
                    harness.control(),
                    candidate,
                    candidate,
                    quiescence_proof_hash="aa" * 32,
                )
                current = harness.connection.execute(
                    "SELECT m.member_id,m.member_tuple_hash,"
                    "e.request_tuple_hash,s.status_hash "
                    "FROM registration_member m "
                    "JOIN registration_effect e "
                    "ON e.effect_id=m.current_effect_id "
                    "JOIN registration_runtime_status s USING(member_id)"
                ).fetchone()
                staged_protocol = store.current_protocol()
                self.assertIsNotNone(staged_protocol)
                missing_adoption = "de" * 32
                predecessor = {
                    "operation_id": missing_adoption,
                    "member_id": current["member_id"],
                    "expected_member_hash": current["member_tuple_hash"],
                    "expected_effect_hash": current["request_tuple_hash"],
                    "expected_status_hash": current["status_hash"],
                    "expected_protocol_hash": staged_protocol[
                        "protocol_hash"
                    ],
                    "expected_staged_epoch_hash": staged_protocol[
                        "staged_epoch_hash"
                    ],
                }
                self.assertEqual(
                    store.resolve_adoption(**predecessor), "ABSENT"
                )
                self.assertEqual(
                    store.resolve_adoption(
                        **{
                            **predecessor,
                            "expected_status_hash": "ed" * 32,
                        }
                    ),
                    "UNAVAILABLE",
                )
                adopted = store.adopt_effect(
                    harness.control(),
                    candidate,
                    member_id=current["member_id"],
                    expected_member_hash=current["member_tuple_hash"],
                    expected_status_hash=current["status_hash"],
                    executor_secret=secret,
                )
                try:
                    store.verify_execution(adopted.execution)
                    before_ack = store.table_count(
                        "registration_operation_audit"
                    )
                    self.assertEqual(
                        store.resolve_adoption(
                            operation_id=adopted.operation.operation_id,
                            member_id=current["member_id"],
                            expected_member_hash=current["member_tuple_hash"],
                            expected_effect_hash=current["request_tuple_hash"],
                            expected_status_hash=current["status_hash"],
                            expected_protocol_hash=staged_protocol[
                                "protocol_hash"
                            ],
                            expected_staged_epoch_hash=staged_protocol[
                                "staged_epoch_hash"
                            ],
                        ),
                        "ALREADY_APPLIED",
                    )
                    self.assertEqual(
                        store.table_count("registration_operation_audit"),
                        before_ack,
                    )
                    row = harness.connection.execute(
                        "SELECT m.helper_generation,s.executor_generation "
                        "FROM registration_member m "
                        "JOIN registration_runtime_status s USING(member_id)"
                    ).fetchone()
                    self.assertEqual(tuple(row), (2, 2))
                finally:
                    adopted.execution.close()
                with self.assertRaises(sqlite3.IntegrityError):
                    store.stage_next(
                        harness.control(),
                        candidate,
                        candidate,
                        quiescence_proof_hash="cc" * 32,
                    )
                with self.assertRaises(sqlite3.IntegrityError):
                    store.cancel_drain(
                        harness.control(),
                        candidate,
                        quiescence_proof_hash="cc" * 32,
                    )
                with self.assertRaises(registration_store.StaleAuthority):
                    store.advance_generation(
                        harness.control(),
                        candidate,
                        quiescence_proof_hash="bb" * 32,
                    )
                staged_dead = harness.connection.execute(
                    "SELECT member_id,status_hash "
                    "FROM registration_runtime_status"
                ).fetchone()
                store.mark_dead_executor_unavailable(
                    harness.data(),
                    candidate,
                    member_id=staged_dead["member_id"],
                    expected_status_hash=staged_dead["status_hash"],
                )
                store.advance_generation(
                    harness.control(),
                    candidate,
                    quiescence_proof_hash="bb" * 32,
                )
                self.assertEqual(
                    store.resolve_adoption(
                        operation_id=adopted.operation.operation_id,
                        member_id=current["member_id"],
                        expected_member_hash=current["member_tuple_hash"],
                        expected_effect_hash=current["request_tuple_hash"],
                        expected_status_hash=current["status_hash"],
                        expected_protocol_hash=staged_protocol[
                            "protocol_hash"
                        ],
                        expected_staged_epoch_hash=staged_protocol[
                            "staged_epoch_hash"
                        ],
                    ),
                    "ALREADY_APPLIED",
                )
                due = harness.connection.execute(
                    "SELECT m.member_id,m.member_tuple_hash,e.request_tuple_hash,"
                    "s.status_hash FROM registration_member m "
                    "JOIN registration_effect e ON e.effect_id=m.current_effect_id "
                    "JOIN registration_runtime_status s USING(member_id)"
                ).fetchone()
                reacquired = store.reacquire_effect(
                    harness.data(),
                    candidate,
                    member_id=due["member_id"],
                    expected_member_hash=due["member_tuple_hash"],
                    expected_effect_hash=due["request_tuple_hash"],
                    expected_status_hash=due["status_hash"],
                    executor_secret=b"b" * 32,
                )
                store.verify_execution(reacquired.execution)
                reacquired.execution.close()
                with self.assertRaises(sqlite3.IntegrityError):
                    store.begin_drain(harness.control(), candidate)

    def test_no_pending_adoption_retains_active_effect_reservation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                store.install_member(
                    harness.data(),
                    candidate,
                    harness.identity(),
                    harness.clean_intent(),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                row = harness.connection.execute(
                    "SELECT m.member_id,m.member_tuple_hash,e.request_tuple_hash,"
                    "s.status_hash FROM registration_member m "
                    "JOIN registration_effect e ON e.effect_id=m.current_effect_id "
                    "JOIN registration_runtime_status s USING(member_id)"
                ).fetchone()
                secret = b"a" * 32
                execution = store.open_effect(
                    harness.data(),
                    candidate,
                    member_id=row["member_id"],
                    expected_member_hash=row["member_tuple_hash"],
                    expected_effect_hash=row["request_tuple_hash"],
                    expected_status_hash=row["status_hash"],
                    executor_secret=secret,
                ).execution
                execution.close()
                store.begin_drain(harness.control(), candidate)
                store.stage_next(
                    harness.control(),
                    candidate,
                    candidate,
                    quiescence_proof_hash="aa" * 32,
                )
                current = harness.connection.execute(
                    "SELECT m.member_id,m.member_tuple_hash,s.status_hash "
                    "FROM registration_member m "
                    "JOIN registration_runtime_status s USING(member_id)"
                ).fetchone()
                active_reservation = 3 * 64 * 1024
                harness.measured_free_bytes = (
                    registration_store.FILESYSTEM_SAFETY_FLOOR
                    + registration_store.MAX_CONTROL_RESERVE
                    + registration_store.PROJECTED_DB_BYTES["ADOPT_EFFECT"]
                    + active_reservation
                    - 1
                )
                before = store.table_count("registration_operation_audit")
                with self.assertRaises(registration_store.InsufficientSpace):
                    store.adopt_effect(
                        harness.control(),
                        candidate,
                        member_id=current["member_id"],
                        expected_member_hash=current["member_tuple_hash"],
                        expected_status_hash=current["status_hash"],
                        executor_secret=secret,
                    )
                self.assertEqual(
                    store.table_count("registration_operation_audit"), before
                )

    def test_ambiguous_operation_resolvers_read_durable_authority(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                bootstrap = store.bootstrap(harness.control(), candidate)
                self.assertEqual(
                    store.resolve_operation(bootstrap.operation_id), "COMMITTED"
                )
                self.assertEqual(
                    store.resolve_operation("ff" * 32), "UNAVAILABLE"
                )
                store.activate(harness.control(), candidate)
                store.install_member(
                    harness.data(),
                    candidate,
                    harness.identity(ordinal=1),
                    harness.clean_intent(ordinal=1),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                before = harness.connection.execute(
                    "SELECT m.member_id,m.member_tuple_hash,e.request_tuple_hash,"
                    "s.status_hash FROM registration_member m "
                    "JOIN registration_effect e ON e.effect_id=m.current_effect_id "
                    "JOIN registration_runtime_status s USING(member_id)"
                ).fetchone()
                changed = harness.identity(ordinal=2)
                applied = store.invalidate_requested(
                    harness.data(),
                    candidate,
                    member_id=before["member_id"],
                    expected_member_hash=before["member_tuple_hash"],
                    expected_effect_hash=before["request_tuple_hash"],
                    expected_status_hash=before["status_hash"],
                    basis=registration_store.BasisUpdate(
                        policy_basis_hash=changed.policy_basis_hash,
                        operation_basis_hash=changed.operation_basis_hash,
                        lifecycle_basis_hash=changed.lifecycle_basis_hash,
                        current_basis_hash=changed.current_basis_hash,
                    ),
                    intent=harness.clean_intent(ordinal=2),
                )
                self.assertEqual(
                    store.resolve_successor(
                        operation_id=applied.operation_id,
                        member_id=before["member_id"],
                        expected_member_hash=before["member_tuple_hash"],
                        target_member_hash=applied.target_hash,
                    ),
                    "APPLIED",
                )
                advanced = store.read_selected_authority(before["member_id"])
                later = store.open_effect(
                    harness.data(),
                    candidate,
                    member_id=before["member_id"],
                    expected_member_hash=advanced.member["member_tuple_hash"],
                    expected_effect_hash=advanced.effect["request_tuple_hash"],
                    expected_status_hash=advanced.status["status_hash"],
                    executor_secret=b"a" * 32,
                )
                try:
                    self.assertEqual(
                        store.resolve_successor(
                            operation_id=applied.operation_id,
                            member_id=before["member_id"],
                            expected_member_hash=before["member_tuple_hash"],
                            target_member_hash=applied.target_hash,
                        ),
                        "APPLIED",
                    )
                finally:
                    later.execution.close()
                self.assertEqual(
                    store.resolve_successor(
                        operation_id="fe" * 32,
                        member_id=before["member_id"],
                        expected_member_hash=before["member_tuple_hash"],
                        target_member_hash="fd" * 32,
                    ),
                    "OBSOLETE",
                )

    def test_operation_resolver_validates_direct_episode_companion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                store.install_member(
                    harness.data(),
                    candidate,
                    harness.identity(),
                    harness.clean_intent(),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                member_id = harness.connection.execute(
                    "SELECT member_id FROM registration_member"
                ).fetchone()[0]
                bound = store.bind_episode(
                    harness.data(),
                    candidate,
                    member_id=member_id,
                    source=registration_store.EpisodeSource(
                        conversation_id="conversation-resolver",
                        generation_id="generation-resolver",
                        source_contract="cursor-hook/v1",
                        source_event="beforeSubmitPrompt",
                        workspace_roots_hash="a" * 64,
                    ),
                )
                self.assertEqual(
                    store.resolve_operation(bound.operation_id), "COMMITTED"
                )
                external = sqlite3.connect(str(db))
                try:
                    self._drop_all_registration_triggers(external)
                    external.execute(
                        "UPDATE registration_episode "
                        "SET generation_id=generation_id||'-corrupt'"
                    )
                    external.commit()
                finally:
                    external.close()
                self.assertEqual(
                    store.resolve_operation(bound.operation_id), "PARTIAL"
                )

    def test_close_and_reacquire_four_way_normal_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                store.install_member(
                    harness.data(),
                    candidate,
                    harness.identity(),
                    harness.clean_intent(),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                row = harness.connection.execute(
                    "SELECT m.member_id,m.member_tuple_hash,m.current_effect_id,"
                    "e.request_tuple_hash,s.status_hash "
                    "FROM registration_member m "
                    "JOIN registration_effect e ON e.effect_id=m.current_effect_id "
                    "JOIN registration_runtime_status s USING(member_id)"
                ).fetchone()
                opened = store.open_effect(
                    harness.data(),
                    candidate,
                    member_id=row["member_id"],
                    expected_member_hash=row["member_tuple_hash"],
                    expected_effect_hash=row["request_tuple_hash"],
                    expected_status_hash=row["status_hash"],
                )
                store.mark_unavailable(
                    harness.data(), candidate, opened.execution
                )
                due = harness.connection.execute(
                    "SELECT m.member_id,m.member_tuple_hash,m.current_effect_id,"
                    "e.request_tuple_hash,s.status_hash "
                    "FROM registration_member m "
                    "JOIN registration_effect e ON e.effect_id=m.current_effect_id "
                    "JOIN registration_runtime_status s USING(member_id)"
                ).fetchone()
                self.assertEqual(
                    store.resolve_reacquire(
                        operation_id="aa" * 32,
                        member_id=due["member_id"],
                        effect_id=due["current_effect_id"],
                        old_status_hash=due["status_hash"],
                    ),
                    "ABSENT",
                )
                reacquired = store.reacquire_effect(
                    harness.data(),
                    candidate,
                    member_id=due["member_id"],
                    expected_member_hash=due["member_tuple_hash"],
                    expected_effect_hash=due["request_tuple_hash"],
                    expected_status_hash=due["status_hash"],
                )
                self.assertEqual(
                    store.resolve_reacquire(
                        operation_id=reacquired.operation.operation_id,
                        member_id=due["member_id"],
                        effect_id=due["current_effect_id"],
                        old_status_hash=due["status_hash"],
                    ),
                    "COMMITTED",
                )
                for index in range(4):
                    store.append_action(
                        harness.data(),
                        candidate,
                        reacquired.execution,
                        observation_kind="OBSERVED_EXACT",
                        measured_postcondition_hash=harness.next_postcondition(),
                    )
                self.assertEqual(
                    store.resolve_reacquire(
                        operation_id=reacquired.operation.operation_id,
                        member_id=due["member_id"],
                        effect_id=due["current_effect_id"],
                        old_status_hash=due["status_hash"],
                    ),
                    "COMMITTED",
                )
                self.assertEqual(
                    store.resolve_close(
                        operation_id="bb" * 32,
                        member_id=due["member_id"],
                        effect_id=due["current_effect_id"],
                    ),
                    "ABSENT",
                )
                closed = store.close_success(
                    harness.data(),
                    candidate,
                    reacquired.execution,
                    final_basis_hash=harness.identity().current_basis_hash,
                )
                self.assertEqual(
                    store.resolve_close(
                        operation_id=closed.operation_id,
                        member_id=due["member_id"],
                        effect_id=due["current_effect_id"],
                    ),
                    "COMMITTED_SUCCESS",
                )
                self.assertEqual(
                    store.resolve_reacquire(
                        operation_id=reacquired.operation.operation_id,
                        member_id=due["member_id"],
                        effect_id=due["current_effect_id"],
                        old_status_hash=due["status_hash"],
                    ),
                    "COMMITTED",
                )
                authority = store.read_selected_authority(due["member_id"])
                changed = harness.identity(ordinal=2)
                store.handoff_resolved(
                    harness.data(),
                    candidate,
                    member_id=due["member_id"],
                    expected_member_hash=authority.member[
                        "member_tuple_hash"
                    ],
                    expected_effect_hash=authority.effect[
                        "outcome_tuple_hash"
                    ],
                    expected_status_hash=authority.status["status_hash"],
                    cause="BASIS_CHANGED",
                    basis=registration_store.BasisUpdate(
                        policy_basis_hash=changed.policy_basis_hash,
                        operation_basis_hash=changed.operation_basis_hash,
                        lifecycle_basis_hash=changed.lifecycle_basis_hash,
                        current_basis_hash=changed.current_basis_hash,
                    ),
                    intent=harness.clean_intent(ordinal=2),
                )
                second = store.read_selected_authority(due["member_id"])
                second_open = store.open_effect(
                    harness.data(),
                    candidate,
                    member_id=due["member_id"],
                    expected_member_hash=second.member["member_tuple_hash"],
                    expected_effect_hash=second.effect["request_tuple_hash"],
                    expected_status_hash=second.status["status_hash"],
                    executor_secret=b"d" * 32,
                )
                for _index in range(4):
                    store.append_action(
                        harness.data(),
                        candidate,
                        second_open.execution,
                        observation_kind="OBSERVED_EXACT",
                        measured_postcondition_hash=(
                            harness.next_postcondition(due["member_id"])
                        ),
                    )
                store.close_success(
                    harness.data(),
                    candidate,
                    second_open.execution,
                    final_basis_hash=changed.current_basis_hash,
                )
                second = store.read_selected_authority(due["member_id"])
                changed_again = harness.identity(ordinal=3)
                store.handoff_resolved(
                    harness.data(),
                    candidate,
                    member_id=due["member_id"],
                    expected_member_hash=second.member[
                        "member_tuple_hash"
                    ],
                    expected_effect_hash=second.effect[
                        "outcome_tuple_hash"
                    ],
                    expected_status_hash=second.status["status_hash"],
                    cause="BASIS_CHANGED",
                    basis=registration_store.BasisUpdate(
                        policy_basis_hash=changed_again.policy_basis_hash,
                        operation_basis_hash=(
                            changed_again.operation_basis_hash
                        ),
                        lifecycle_basis_hash=(
                            changed_again.lifecycle_basis_hash
                        ),
                        current_basis_hash=changed_again.current_basis_hash,
                    ),
                    intent=harness.clean_intent(ordinal=3),
                )
                self.assertEqual(
                    store.resolve_close(
                        operation_id=closed.operation_id,
                        member_id=due["member_id"],
                        effect_id=due["current_effect_id"],
                    ),
                    "COMMITTED_SUCCESS",
                )
                self.assertEqual(
                    store.resolve_reacquire(
                        operation_id=reacquired.operation.operation_id,
                        member_id=due["member_id"],
                        effect_id=due["current_effect_id"],
                        old_status_hash=due["status_hash"],
                    ),
                    "COMMITTED",
                )

    def test_ar_typed_provider_values_validate_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                basis = _fresh_basis(harness, 1)
                with self.assertRaises(ValueError):
                    registration_store.FreshMemberBasis(
                        identity=basis.identity,
                        intent=replace(
                            basis.intent,
                            request_basis_hash="cd" * 32,
                        ),
                        workspace_roots_hash=basis.workspace_roots_hash,
                    )
                with self.assertRaises(ValueError):
                    registration_store.FreshMemberBasis(
                        identity=basis.identity,
                        intent=basis.intent,
                        workspace_roots_hash="A" * 64,
                    )

                first = registration_store.SameBootCandidate(
                    member_id="1" * 64,
                    status_hash="2" * 64,
                    executor_token_hash="3" * 64,
                    executor_generation=1,
                )
                second = registration_store.SameBootCandidate(
                    member_id="4" * 64,
                    status_hash="5" * 64,
                    executor_token_hash="6" * 64,
                    executor_generation=2,
                )
                with self.assertRaises(ValueError):
                    registration_store.SameBootCandidate(
                        member_id=first.member_id,
                        status_hash=first.status_hash,
                        executor_token_hash=first.executor_token_hash,
                        executor_generation=True,
                    )
                with self.assertRaises(ValueError):
                    registration_store.SameBootSnapshot(
                        boot_id="boot-a",
                        protocol_seq=True,
                        protocol_hash="7" * 64,
                        candidates=(),
                    )
                with self.assertRaises(ValueError):
                    registration_store.SameBootSnapshot(
                        boot_id="boot-a",
                        protocol_seq=1,
                        protocol_hash="7" * 64,
                        candidates=(second, first),
                    )
                with self.assertRaises(ValueError):
                    registration_store.SameBootSnapshot(
                        boot_id="boot-a",
                        protocol_seq=1,
                        protocol_hash="7" * 64,
                        candidates=[first],
                    )
                with self.assertRaises(ValueError):
                    registration_store.R1ScopeSelection(
                        authorized_same_boot=None,
                        authorized_due=None,
                        authorized_reboot=None,
                        outside_scope_same_boot=0,
                        outside_scope_due=False,
                        outside_scope_reboot=False,
                    )

    def test_ar_member_scope_lifecycle_and_fresh_basis_refuse_safely(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                member_id = _member_id(harness.identity())
                before = store.table_count("registration_operation_audit")

                with self.assertRaises(
                    registration_store.AuthorizationError
                ):
                    registration_store.MemberMutationScope(
                        store,
                        member_id,
                        5.0,
                        _seal=object(),
                    )
                for label, invalid_timeout in (
                    ("boolean", True),
                    ("negative", -1),
                    ("nan", float("nan")),
                    ("infinite", float("inf")),
                    ("above-thread-limit", 1e300),
                    ("integer-overflow", 10**10_000),
                ):
                    with self.subTest(timeout=label):
                        with self.assertRaises(ValueError):
                            store.member_mutation_scope(
                                member_id,
                                timeout_seconds=invalid_timeout,
                            )

                scope = store.member_mutation_scope(member_id)
                with scope:
                    with self.assertRaisesRegex(RuntimeError, "collector failed"):
                        scope.collect_fresh_basis(
                            lambda: (_ for _ in ()).throw(
                                RuntimeError("collector failed")
                            )
                        )
                    self.assertEqual(
                        store.table_count("registration_operation_audit"),
                        before,
                    )
                    with self.assertRaises(registration_store.AuthorizationError):
                        scope.collect_fresh_basis(lambda: object())
                    with self.assertRaises(registration_store.StaleAuthority):
                        scope.collect_fresh_basis(
                            lambda: registration_store.FreshMemberBasis(
                                identity=harness.identity(ordinal=2),
                                intent=harness.clean_intent(ordinal=2),
                                workspace_roots_hash="ab" * 32,
                            )
                        )

                    old_basis = scope.collect_fresh_basis(
                        lambda: _fresh_basis(harness, 1)
                    )
                    fresh_basis = scope.collect_fresh_basis(
                        lambda: _fresh_basis(harness, 2)
                    )
                    with self.assertRaises(registration_store.StaleAuthority):
                        scope.install_member(
                            harness.data(),
                            candidate,
                            old_basis,
                        )

                    thread_errors: list[BaseException] = []

                    def wrong_thread() -> None:
                        try:
                            scope.collect_fresh_basis(
                                lambda: _fresh_basis(harness, 2)
                            )
                        except BaseException as error:
                            thread_errors.append(error)

                    thread = threading.Thread(target=wrong_thread)
                    thread.start()
                    thread.join(1)
                    self.assertFalse(thread.is_alive())
                    self.assertEqual(len(thread_errors), 1)
                    self.assertIsInstance(
                        thread_errors[0],
                        registration_store.AuthorizationError,
                    )

                    with mock.patch.object(
                        registration_store.os,
                        "getpid",
                        return_value=os.getpid() + 1,
                    ):
                        with self.assertRaises(
                            registration_store.AuthorizationError
                        ):
                            scope.collect_fresh_basis(
                                lambda: _fresh_basis(harness, 2)
                            )

                    read_descriptor, write_descriptor = os.pipe()
                    child_pid = os.fork()
                    if child_pid == 0:
                        os.close(read_descriptor)
                        try:
                            scope.collect_fresh_basis(
                                lambda: _fresh_basis(harness, 2)
                            )
                            outcome = b"unexpected-success"
                        except BaseException as error:
                            outcome = type(error).__name__.encode("ascii")
                        try:
                            os.write(write_descriptor, outcome)
                        finally:
                            os.close(write_descriptor)
                        os._exit(0)
                    os.close(write_descriptor)
                    try:
                        fork_outcome = os.read(read_descriptor, 128)
                    finally:
                        os.close(read_descriptor)
                    _waited_pid, child_status = os.waitpid(child_pid, 0)
                    self.assertTrue(os.WIFEXITED(child_status))
                    self.assertEqual(
                        fork_outcome, b"AuthorizationError"
                    )
                    with self.assertRaises(TypeError):
                        pickle.dumps(scope)

                    busy: list[BaseException] = []

                    def contend() -> None:
                        try:
                            with store.member_mutation_scope(
                                member_id, timeout_seconds=0
                            ):
                                pass
                        except BaseException as error:
                            busy.append(error)

                    contender = threading.Thread(target=contend)
                    contender.start()
                    contender.join(1)
                    self.assertFalse(contender.is_alive())
                    self.assertEqual(len(busy), 1)
                    self.assertIsInstance(busy[0], registration_lock.LockBusy)
                    self.assertEqual(
                        store.table_count("registration_operation_audit"),
                        before,
                    )

                    installed = scope.install_member(
                        harness.data(),
                        candidate,
                        fresh_basis,
                    )
                    self.assertEqual(installed.disposition, "COMMITTED")

                with self.assertRaises(registration_store.AuthorizationError):
                    scope.collect_fresh_basis(
                        lambda: _fresh_basis(harness, 2)
                    )
                with self.assertRaises(TypeError):
                    pickle.dumps(scope)

                before = store.table_count("registration_operation_audit")
                loss_scope = store.member_mutation_scope(member_id)
                with loss_scope:
                    self.assertIsNotNone(loss_scope._held_lock)
                    loss_scope._held_lock.release()
                    with self.assertRaises(
                        registration_store.AuthorizationError
                    ):
                        loss_scope.collect_fresh_basis(
                            lambda: _fresh_basis(harness, 2)
                        )
                self.assertEqual(
                    store.table_count("registration_operation_audit"),
                    before,
                )

                other_db = (
                    Path(tmp)
                    / "other"
                    / "registration-v1"
                    / "registration.db"
                )
                with RegistrationHarness.open(
                    other_db, measured_free_bytes=2 * 1024**3
                ) as other:
                    with other.store.member_mutation_scope(
                        member_id
                    ) as other_scope:
                        self.assertIsNotNone(other_scope._held_lock)
                        with self.assertRaises(
                            registration_store.AuthorizationError
                        ):
                            store.install_member(
                                harness.data(),
                                candidate,
                                fresh_basis.identity,
                                fresh_basis.intent,
                                _member_lock=other_scope._held_lock,
                            )
                self.assertEqual(
                    store.table_count("registration_operation_audit"),
                    before,
                )

    def test_ar_scoped_mutations_preserve_direct_transition_semantics(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                data = harness.data()
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                member_id = _member_id(harness.identity())

                with store.member_mutation_scope(member_id) as scope:
                    basis = scope.collect_fresh_basis(
                        lambda: _fresh_basis(harness, 1)
                    )
                    installed = scope.install_member(
                        data,
                        candidate,
                        basis,
                    )
                    self.assertEqual(installed.disposition, "COMMITTED")
                    before = store.table_count(
                        "registration_operation_audit"
                    )
                    duplicate = scope.install_member(
                        data,
                        candidate,
                        basis,
                    )
                    self.assertEqual(duplicate.disposition, "COMMITTED")
                    self.assertEqual(
                        duplicate.operation_id, installed.operation_id
                    )
                    self.assertEqual(
                        store.table_count("registration_operation_audit"),
                        before,
                    )

                    source = registration_store.EpisodeSource(
                        conversation_id="conversation-ar",
                        generation_id="generation-ar",
                        source_contract="cursor-hook/v1",
                        source_event="beforeSubmitPrompt",
                        workspace_roots_hash=basis.workspace_roots_hash,
                    )
                    bound = scope.bind_episode(
                        data,
                        candidate,
                        basis,
                        source=source,
                    )
                    self.assertEqual(bound.disposition, "COMMITTED")
                    before = store.table_count(
                        "registration_operation_audit"
                    )
                    self.assertEqual(
                        scope.bind_episode(
                            data,
                            candidate,
                            basis,
                            source=source,
                        ).disposition,
                        "COMMITTED",
                    )
                    self.assertEqual(
                        store.table_count("registration_operation_audit"),
                        before,
                    )
                    with self.assertRaises(
                        registration_store.StaleAuthority
                    ):
                        scope.bind_episode(
                            data,
                            candidate,
                            basis,
                            source=replace(
                                source,
                                workspace_roots_hash="cd" * 32,
                            ),
                        )

                authority = store.read_selected_authority(member_id)
                with store.member_mutation_scope(member_id) as scope:
                    changed = scope.collect_fresh_basis(
                        lambda: _fresh_basis(harness, 2)
                    )
                    invalidated = scope.invalidate_requested(
                        data,
                        candidate,
                        changed,
                        expected_member_hash=authority.member[
                            "member_tuple_hash"
                        ],
                        expected_effect_hash=authority.effect[
                            "request_tuple_hash"
                        ],
                        expected_status_hash=authority.status["status_hash"],
                    )
                    self.assertEqual(invalidated.disposition, "COMMITTED")

                authority = store.read_selected_authority(member_id)
                opened = store.open_effect(
                    data,
                    candidate,
                    member_id=member_id,
                    expected_member_hash=authority.member[
                        "member_tuple_hash"
                    ],
                    expected_effect_hash=authority.effect[
                        "request_tuple_hash"
                    ],
                    expected_status_hash=authority.status["status_hash"],
                    executor_secret=b"a" * 32,
                )
                store.mark_unavailable(
                    data,
                    candidate,
                    opened.execution,
                )
                authority = store.read_selected_authority(member_id)
                with store.member_mutation_scope(member_id) as scope:
                    pending = scope.collect_fresh_basis(
                        lambda: _fresh_basis(harness, 3)
                    )
                    set_result = scope.set_pending(
                        data,
                        candidate,
                        pending,
                        expected_member_hash=authority.member[
                            "member_tuple_hash"
                        ],
                        expected_effect_hash=authority.effect[
                            "request_tuple_hash"
                        ],
                        expected_status_hash=authority.status["status_hash"],
                    )
                    self.assertEqual(set_result.disposition, "COMMITTED")

                authority = store.read_selected_authority(member_id)
                self.assertIsNotNone(authority.pending_effect)
                with store.member_mutation_scope(member_id) as scope:
                    replacement = scope.collect_fresh_basis(
                        lambda: _fresh_basis(harness, 4)
                    )
                    replace_result = scope.replace_pending(
                        data,
                        candidate,
                        replacement,
                        expected_member_hash=authority.member[
                            "member_tuple_hash"
                        ],
                        expected_effect_hash=authority.pending_effect[
                            "request_tuple_hash"
                        ],
                        expected_status_hash=authority.status["status_hash"],
                    )
                    self.assertEqual(
                        replace_result.disposition, "COMMITTED"
                    )
                    replaced = store.read_selected_authority(member_id)
                    self.assertIsNotNone(replaced.pending_effect)
                    before = store.table_count(
                        "registration_operation_audit"
                    )
                    no_replacement = scope.replace_pending(
                        data,
                        candidate,
                        replacement,
                        expected_member_hash=replaced.member[
                            "member_tuple_hash"
                        ],
                        expected_effect_hash=replaced.pending_effect[
                            "request_tuple_hash"
                        ],
                        expected_status_hash=replaced.status["status_hash"],
                    )
                    self.assertEqual(no_replacement.disposition, "NOOP")
                    self.assertEqual(
                        store.table_count("registration_operation_audit"),
                        before,
                    )

                authority = store.read_selected_authority(member_id)
                active = store.reacquire_effect(
                    data,
                    candidate,
                    member_id=member_id,
                    expected_member_hash=authority.member[
                        "member_tuple_hash"
                    ],
                    expected_effect_hash=authority.effect[
                        "request_tuple_hash"
                    ],
                    expected_status_hash=authority.status["status_hash"],
                    executor_secret=b"c" * 32,
                )
                for _ in range(4):
                    store.append_action(
                        data,
                        candidate,
                        active.execution,
                        observation_kind="OBSERVED_EXACT",
                        measured_postcondition_hash=(
                            harness.next_postcondition()
                        ),
                    )
                store.close_success(
                    data,
                    candidate,
                    active.execution,
                    final_basis_hash=changed.identity.current_basis_hash,
                )
                authority = store.read_selected_authority(member_id)
                with store.member_mutation_scope(member_id) as scope:
                    current = scope.collect_fresh_basis(
                        lambda: _fresh_basis(harness, 4)
                    )
                    handoff = scope.handoff_resolved(
                        data,
                        candidate,
                        current,
                        expected_member_hash=authority.member[
                            "member_tuple_hash"
                        ],
                        expected_effect_hash=authority.effect[
                            "outcome_tuple_hash"
                        ],
                        expected_status_hash=authority.status["status_hash"],
                    )
                    self.assertEqual(handoff.disposition, "COMMITTED")
                    successor = store.read_selected_authority(member_id)
                    newer = scope.collect_fresh_basis(
                        lambda: _fresh_basis(harness, 5)
                    )
                    second_invalidation = scope.invalidate_requested(
                        data,
                        candidate,
                        newer,
                        expected_member_hash=successor.member[
                            "member_tuple_hash"
                        ],
                        expected_effect_hash=successor.effect[
                            "request_tuple_hash"
                        ],
                        expected_status_hash=successor.status[
                            "status_hash"
                        ],
                    )
                    self.assertEqual(
                        second_invalidation.disposition, "COMMITTED"
                    )

                authority = store.read_selected_authority(member_id)
                live = store.open_effect(
                    data,
                    candidate,
                    member_id=member_id,
                    expected_member_hash=authority.member[
                        "member_tuple_hash"
                    ],
                    expected_effect_hash=authority.effect[
                        "request_tuple_hash"
                    ],
                    expected_status_hash=authority.status["status_hash"],
                    executor_secret=b"b" * 32,
                )
                live.execution.close()
                authority = store.read_selected_authority(member_id)
                with store.member_mutation_scope(member_id) as scope:
                    marked = scope.mark_dead_executor_unavailable(
                        data,
                        candidate,
                        expected_status_hash=authority.status[
                            "status_hash"
                        ],
                    )
                    self.assertIsInstance(
                        marked, registration_store.OperationResult
                    )
                final = store.read_selected_authority(member_id)
                self.assertIsNone(final.status["executor_token_hash"])
                self.assertIsNotNone(
                    store.validate_semantic_closure(member_id)
                )

    def test_ar_two_processes_converge_on_under_lock_fresh_basis(self) -> None:
        context = multiprocessing.get_context("spawn")
        for order in ((1, 2), (2, 1)):
            with self.subTest(order=order), tempfile.TemporaryDirectory() as tmp:
                db = Path(tmp) / "state" / "registration-v1" / "registration.db"
                with RegistrationHarness.open(
                    db, measured_free_bytes=2 * 1024**3
                ) as harness:
                    candidate = harness.candidate()
                    harness.store.bootstrap(harness.control(), candidate)
                    harness.store.activate(harness.control(), candidate)
                    before = harness.store.table_count(
                        "registration_operation_audit"
                    )

                shared_ordinal = context.Value(
                    "i", 1 if order == (1, 2) else 2
                )
                first_attempting = context.Event()
                first_entered = context.Event()
                release_first = context.Event()
                second_attempting = context.Event()
                second_entered = context.Event()
                results = context.Queue()
                first = context.Process(
                    target=_scope_install_process,
                    args=(
                        str(db),
                        shared_ordinal,
                        first_attempting,
                        first_entered,
                        release_first,
                        order[0],
                        "e1" * 32,
                        results,
                    ),
                )
                second = context.Process(
                    target=_scope_install_process,
                    args=(
                        str(db),
                        shared_ordinal,
                        second_attempting,
                        second_entered,
                        None,
                        order[1],
                        "e2" * 32,
                        results,
                    ),
                )
                first.start()
                self.assertTrue(first_entered.wait(5))
                second.start()
                self.assertTrue(second_attempting.wait(5))
                self.assertFalse(second_entered.wait(0.1))
                shared_ordinal.value = 2
                release_first.set()
                first.join(10)
                second.join(10)
                self.assertFalse(first.is_alive())
                self.assertFalse(second.is_alive())
                observed = [results.get(timeout=2), results.get(timeout=2)]
                self.assertTrue(
                    all(result[0] == "ok" for result in observed),
                    observed,
                )
                self.assertEqual(
                    {result[1] for result in observed},
                    {"COMMITTED"},
                )
                self.assertEqual(len({result[2] for result in observed}), 1)
                self.assertEqual(
                    {result[-2] for result in observed}, set(order)
                )
                with RegistrationHarness.open(
                    db, measured_free_bytes=2 * 1024**3
                ) as harness:
                    expected_hash = _fresh_basis(
                        harness, 2
                    ).identity.current_basis_hash
                    self.assertEqual(
                        {result[-1] for result in observed},
                        {expected_hash},
                    )
                    member_id = _member_id(harness.identity())
                    authority = harness.store.read_selected_authority(
                        member_id
                    )
                    self.assertEqual(
                        authority.member["current_basis_hash"],
                        expected_hash,
                    )
                    self.assertEqual(
                        harness.store.table_count(
                            "registration_operation_audit"
                        ),
                        before + 1,
                    )

    def test_ar_same_boot_snapshot_is_complete_validated_and_read_only(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=4 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                data = harness.data()
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                empty = store.select_same_boot_snapshot(boot_id="boot-a")
                self.assertEqual(empty.candidates, ())

                expected: dict[str, tuple[str, int]] = {}
                for ordinal in range(1, 11):
                    identity_value, _, _ = _install_member(
                        harness,
                        ordinal,
                        sample_boot_id="boot-a",
                    )
                    member_id = _member_id(identity_value)
                    authority = store.read_selected_authority(member_id)
                    opened = store.open_effect(
                        data,
                        candidate,
                        member_id=member_id,
                        expected_member_hash=authority.member[
                            "member_tuple_hash"
                        ],
                        expected_effect_hash=authority.effect[
                            "request_tuple_hash"
                        ],
                        expected_status_hash=authority.status[
                            "status_hash"
                        ],
                        executor_secret=ordinal.to_bytes(32, "big"),
                    )
                    opened.execution.close()
                    authority = store.read_selected_authority(member_id)
                    expected[member_id] = (
                        authority.status["executor_token_hash"],
                        authority.status["executor_generation"],
                    )
                    if ordinal in {1, 8, 9, 10}:
                        before = store.table_count(
                            "registration_operation_audit"
                        )
                        snapshot = store.select_same_boot_snapshot(
                            boot_id="boot-a"
                        )
                        self.assertEqual(
                            [item.member_id for item in snapshot.candidates],
                            sorted(expected),
                        )
                        self.assertEqual(
                            len(snapshot.candidates), ordinal
                        )
                        protocol = store.current_protocol()
                        self.assertIsNotNone(protocol)
                        self.assertEqual(
                            snapshot.protocol_seq,
                            protocol["protocol_seq"],
                        )
                        self.assertEqual(
                            snapshot.protocol_hash,
                            protocol["protocol_hash"],
                        )
                        for item in snapshot.candidates:
                            self.assertEqual(
                                (
                                    item.executor_token_hash,
                                    item.executor_generation,
                                ),
                                expected[item.member_id],
                            )
                        self.assertEqual(
                            store.table_count(
                                "registration_operation_audit"
                            ),
                            before,
                        )

                victim = sorted(expected)[0]
                external = sqlite3.connect(str(db))
                try:
                    self._drop_all_registration_triggers(external)
                    external.execute(
                        "UPDATE registration_runtime_status "
                        "SET status_hash=? WHERE member_id=?",
                        ("f" * 64, victim),
                    )
                    external.commit()
                finally:
                    external.close()
                before = store.table_count("registration_operation_audit")
                with self.assertRaises(registration_store.StoreUnavailable):
                    store.select_same_boot_snapshot(boot_id="boot-a")
                with self.assertRaises(registration_store.StoreUnavailable):
                    store.select_r1_scope(
                        victim,
                        "boot-a",
                        1_000_000,
                    )
                self.assertEqual(
                    store.table_count("registration_operation_audit"),
                    before,
                )

    def test_ar_r1_scope_positions_and_independent_outside_flags(self) -> None:
        for universe in ("same_boot", "due", "reboot"):
            with self.subTest(universe=universe), tempfile.TemporaryDirectory() as tmp:
                db = (
                    Path(tmp)
                    / "state"
                    / "registration-v1"
                    / "registration.db"
                )
                with RegistrationHarness.open(
                    db, measured_free_bytes=4 * 1024**3
                ) as harness:
                    store = harness.store
                    candidate = harness.candidate()
                    data = harness.data()
                    store.bootstrap(harness.control(), candidate)
                    store.activate(harness.control(), candidate)
                    member_ids: list[str] = []
                    for ordinal in range(1, 10):
                        boot = "boot-old" if universe == "reboot" else "boot-a"
                        identity_value, _, _ = _install_member(
                            harness,
                            ordinal,
                            sample_boot_id=boot,
                        )
                        member_id = _member_id(identity_value)
                        member_ids.append(member_id)
                        if universe == "same_boot":
                            authority = store.read_selected_authority(
                                member_id
                            )
                            opened = store.open_effect(
                                data,
                                candidate,
                                member_id=member_id,
                                expected_member_hash=authority.member[
                                    "member_tuple_hash"
                                ],
                                expected_effect_hash=authority.effect[
                                    "request_tuple_hash"
                                ],
                                expected_status_hash=authority.status[
                                    "status_hash"
                                ],
                                executor_secret=ordinal.to_bytes(32, "big"),
                            )
                            opened.execution.close()
                        if ordinal == 1:
                            single = store.select_r1_scope(
                                member_id,
                                "boot-a",
                                1_000_000,
                            )
                            single_values = {
                                "same_boot": single.authorized_same_boot,
                                "due": single.authorized_due,
                                "reboot": single.authorized_reboot,
                            }
                            self.assertEqual(
                                single_values[universe].member_id,
                                member_id,
                            )
                            self.assertFalse(
                                single.outside_scope_same_boot
                            )
                            self.assertFalse(single.outside_scope_due)
                            self.assertFalse(single.outside_scope_reboot)

                    member_ids.sort()
                    before = store.table_count(
                        "registration_operation_audit"
                    )
                    for position in (0, 7, 8):
                        selected = store.select_r1_scope(
                            member_ids[position],
                            "boot-a",
                            1_000_000,
                        )
                        values = {
                            "same_boot": selected.authorized_same_boot,
                            "due": selected.authorized_due,
                            "reboot": selected.authorized_reboot,
                        }
                        flags = {
                            "same_boot": (
                                selected.outside_scope_same_boot
                            ),
                            "due": selected.outside_scope_due,
                            "reboot": selected.outside_scope_reboot,
                        }
                        self.assertEqual(
                            values[universe].member_id,
                            member_ids[position],
                        )
                        self.assertTrue(flags[universe])
                        for other in set(values) - {universe}:
                            self.assertIsNone(values[other])
                            self.assertFalse(flags[other])
                    self.assertEqual(
                        store.table_count("registration_operation_audit"),
                        before,
                    )
                    with self.assertRaises(ValueError):
                        store.select_r1_scope(
                            member_ids[0], "boot-a", True
                        )
                    with self.assertRaises(ValueError):
                        store.select_r1_scope(
                            "bad", "boot-a", 1_000_000
                        )
                    with self.assertRaises(ValueError):
                        store.list_due_candidates(
                            boot_id="boot-a",
                            now_mono_ns=1_000_000,
                            limit=9,
                        )

    def test_ar_same_boot_snapshot_is_coherent_under_protocol_change(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=4 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                control = harness.control()
                store.bootstrap(control, candidate)
                store.activate(control, candidate)
                initial = store.current_protocol()
                self.assertIsNotNone(initial)
                entered = threading.Event()
                release = threading.Event()
                writer_ready = threading.Event()
                writer_done = threading.Event()
                writer_errors: list[BaseException] = []
                original_validate = store._validate_protocol_row
                delayed = False

                def delayed_validate(*args, **kwargs):
                    nonlocal delayed
                    result = original_validate(*args, **kwargs)
                    if not delayed:
                        delayed = True
                        entered.set()
                        if not release.wait(5):
                            raise RuntimeError("selector release timed out")
                    return result

                def writer() -> None:
                    try:
                        with registration_store.RegistrationStore(
                            db,
                            free_bytes=lambda _fd: 4 * 1024**3,
                            boot_id=lambda: "boot-a",
                            mono_ns=lambda: 100,
                            _test_profile_seal=(
                                registration_store._TEST_PROFILE_SEAL
                            ),
                        ) as other:
                            writer_ready.set()
                            if not entered.wait(5):
                                raise RuntimeError("selector never entered")
                            other.begin_drain(control, candidate)
                    except BaseException as error:
                        writer_errors.append(error)
                    finally:
                        release.set()
                        writer_done.set()

                thread = threading.Thread(target=writer)
                thread.start()
                self.assertTrue(writer_ready.wait(5))
                store._validate_protocol_row = delayed_validate
                try:
                    old = store.select_same_boot_snapshot(boot_id="boot-a")
                finally:
                    store._validate_protocol_row = original_validate
                self.assertTrue(writer_done.wait(5))
                thread.join(1)
                self.assertFalse(thread.is_alive())
                self.assertEqual(writer_errors, [])
                self.assertEqual(old.candidates, ())
                self.assertEqual(
                    old.protocol_hash, initial["protocol_hash"]
                )
                new = store.select_same_boot_snapshot(boot_id="boot-a")
                self.assertEqual(new.candidates, ())
                self.assertGreater(new.protocol_seq, old.protocol_seq)
                self.assertNotEqual(new.protocol_hash, old.protocol_hash)

    def test_ar_selector_transaction_is_coherent_under_concurrent_status_write(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=4 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                data = harness.data()
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                member_ids: list[str] = []
                for ordinal in (1, 2):
                    identity_value, _, _ = _install_member(
                        harness,
                        ordinal,
                        sample_boot_id="boot-a",
                    )
                    member_id = _member_id(identity_value)
                    authority = store.read_selected_authority(member_id)
                    opened = store.open_effect(
                        data,
                        candidate,
                        member_id=member_id,
                        expected_member_hash=authority.member[
                            "member_tuple_hash"
                        ],
                        expected_effect_hash=authority.effect[
                            "request_tuple_hash"
                        ],
                        expected_status_hash=authority.status["status_hash"],
                        executor_secret=ordinal.to_bytes(32, "big"),
                    )
                    opened.execution.close()
                    member_ids.append(member_id)

                victim = sorted(member_ids)[-1]
                victim_status = store.read_selected_authority(victim).status[
                    "status_hash"
                ]
                entered = threading.Event()
                release = threading.Event()
                writer_ready = threading.Event()
                writer_done = threading.Event()
                writer_errors: list[BaseException] = []
                original_validate = store._validate_semantic_closure_tx
                calls = 0

                def delayed_validate(*args, **kwargs):
                    nonlocal calls
                    result = original_validate(*args, **kwargs)
                    calls += 1
                    if calls == 1:
                        entered.set()
                        if not release.wait(5):
                            raise RuntimeError("selector release timed out")
                    return result

                def writer() -> None:
                    try:
                        with registration_store.RegistrationStore(
                            db,
                            free_bytes=lambda _fd: 4 * 1024**3,
                            boot_id=lambda: "boot-a",
                            mono_ns=lambda: 100,
                            _test_profile_seal=(
                                registration_store._TEST_PROFILE_SEAL
                            ),
                        ) as other:
                            writer_ready.set()
                            if not entered.wait(5):
                                raise RuntimeError("selector never entered")
                            other.mark_dead_executor_unavailable(
                                data,
                                candidate,
                                member_id=victim,
                                expected_status_hash=victim_status,
                            )
                    except BaseException as error:
                        writer_errors.append(error)
                    finally:
                        release.set()
                        writer_done.set()

                thread = threading.Thread(target=writer)
                thread.start()
                self.assertTrue(writer_ready.wait(5))
                store._validate_semantic_closure_tx = delayed_validate
                try:
                    old = store.select_same_boot_snapshot(boot_id="boot-a")
                finally:
                    store._validate_semantic_closure_tx = original_validate
                self.assertTrue(writer_done.wait(5))
                thread.join(1)
                self.assertFalse(thread.is_alive())
                self.assertEqual(writer_errors, [])
                self.assertEqual(
                    [item.member_id for item in old.candidates],
                    sorted(member_ids),
                )
                new = store.select_same_boot_snapshot(boot_id="boot-a")
                self.assertEqual(
                    [item.member_id for item in new.candidates],
                    [
                        member_id
                        for member_id in sorted(member_ids)
                        if member_id != victim
                    ],
                )

                original_validate = store._validate_semantic_closure_tx
                before = store.table_count("registration_operation_audit")
                store._validate_semantic_closure_tx = (
                    lambda *_args, **_kwargs: (_ for _ in ()).throw(
                        sqlite3.OperationalError("injected selector fault")
                    )
                )
                try:
                    with self.assertRaises(
                        registration_store.StoreUnavailable
                    ):
                        store.select_r1_scope(
                            member_ids[0],
                            "boot-a",
                            1_000_000,
                        )
                finally:
                    store._validate_semantic_closure_tx = original_validate
                self.assertEqual(
                    store.table_count("registration_operation_audit"),
                    before,
                )

    def test_store_failure_contains_only_after_containment_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                operation_id = "ab" * 32
                predecessor_revision = store.table_count(
                    "registration_operation_audit"
                )
                predecessor_protocol_hash = store.current_protocol()[
                    "protocol_hash"
                ]
                harness.inject_fault(
                    "before_commit",
                    registration_store.InjectedSQLiteFault(
                        sqlite3.SQLITE_IOERR
                    ),
                )
                with self.assertRaises(registration_store.InjectedSQLiteFault):
                    store.begin_drain(
                        harness.control(),
                        candidate,
                        operation_id=operation_id,
                    )
                self.assertEqual(
                    store.resolve_operation(
                        operation_id,
                        expected_revision=predecessor_revision,
                        expected_protocol_hash=predecessor_protocol_hash,
                    ),
                    "ABSENT",
                )
                self.assertEqual(store.current_protocol()["mode"], "WRITABLE")
                contained = store.enter_containment(
                    harness.control(), candidate, reason="STORE_FAILURE"
                )
                self.assertEqual(contained.disposition, "COMMITTED")
                self.assertEqual(
                    store.current_protocol()["mode"], "CONTAINMENT"
                )


if __name__ == "__main__":
    unittest.main()
