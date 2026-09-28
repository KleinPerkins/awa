from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from engine import registration_executor, registration_store
from engine.tests.registration_harness import RegistrationHarness


@unittest.skipUnless(
    sqlite3.sqlite_version_info >= registration_store.MIN_SQLITE_VERSION,
    "ADR 0025 requires stock SQLite >=3.51.3",
)
class RegistrationStoreBootstrapTest(unittest.TestCase):
    def test_every_operation_has_nonzero_bounded_projection(self) -> None:
        self.assertEqual(len(registration_store.PROJECTED_DB_BYTES), 24)
        self.assertTrue(
            all(
                0 < value <= 16 * 1024**2
                for value in registration_store.PROJECTED_DB_BYTES.values()
            )
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
                    harness.store.resolve_operation(operation_id), "ABSENT"
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
                        registration_executor.StagedSecretTransfer.precreate()
                    )
                    opened.execution.transfer_staged(transfer)
                    self.assertEqual(
                        transfer.receive(opened.execution.executor_token_hash),
                        b"a" * 32,
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
                    "SELECT m.member_id,m.member_tuple_hash,s.status_hash "
                    "FROM registration_member m "
                    "JOIN registration_runtime_status s USING(member_id)"
                ).fetchone()
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
                store.advance_generation(
                    harness.control(),
                    candidate,
                    quiescence_proof_hash="bb" * 32,
                )
                dead = harness.connection.execute(
                    "SELECT member_id,status_hash FROM registration_runtime_status"
                ).fetchone()
                store.mark_dead_executor_unavailable(
                    harness.data(),
                    candidate,
                    member_id=dead["member_id"],
                    expected_status_hash=dead["status_hash"],
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
                    store.resolve_operation("ff" * 32), "ABSENT"
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
                self.assertEqual(
                    store.resolve_successor(
                        operation_id="fe" * 32,
                        member_id=before["member_id"],
                        expected_member_hash=before["member_tuple_hash"],
                        target_member_hash="fd" * 32,
                    ),
                    "OBSOLETE",
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
                    store.resolve_operation(operation_id), "ABSENT"
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
