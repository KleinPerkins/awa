from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable, Mapping

from engine import registration_hashes, registration_store
from engine.tests.registration_harness import RegistrationHarness


def _insert_row(
    connection: sqlite3.Connection,
    table: str,
    row: Mapping[str, Any],
) -> None:
    columns = tuple(row)
    connection.execute(
        f"INSERT INTO {table}({','.join(columns)}) "
        f"VALUES({','.join('?' for _ in columns)})",
        tuple(row[column] for column in columns),
    )


def _update_status(
    connection: sqlite3.Connection,
    row: Mapping[str, Any],
    *,
    expected_status_hash: str,
) -> None:
    columns = tuple(column for column in row if column != "subject_key")
    cursor = connection.execute(
        "UPDATE registration_runtime_status SET "
        + ",".join(f"{column}=?" for column in columns)
        + " WHERE subject_key=? AND status_hash IS ?",
        (
            *(row[column] for column in columns),
            row["subject_key"],
            expected_status_hash,
        ),
    )
    if cursor.rowcount != 1:
        raise AssertionError("status replay did not select exactly one row")


def _trigger_sql(
    connection: sqlite3.Connection, trigger: str
) -> str:
    row = connection.execute(
        "SELECT sql FROM sqlite_schema WHERE type='trigger' AND name=?",
        (trigger,),
    ).fetchone()
    if row is None or not isinstance(row[0], str):
        raise AssertionError(f"missing trigger {trigger}")
    return row[0]


def _without_trigger(
    connection: sqlite3.Connection,
    trigger: str,
    action: Callable[[], None],
) -> None:
    sql = _trigger_sql(connection, trigger)
    connection.execute(f'DROP TRIGGER "{trigger}"')
    action()
    connection.execute(sql)


@unittest.skipUnless(
    sqlite3.sqlite_version_info >= registration_store.MIN_SQLITE_VERSION,
    "ADR 0026 requires stock SQLite >=3.51.3",
)
class RegistrationStagedPredicateTest(unittest.TestCase):
    def _backup(
        self, source: sqlite3.Connection, path: Path
    ) -> None:
        destination = sqlite3.connect(str(path))
        try:
            source.backup(destination)
        finally:
            destination.close()

    def _clone(self, path: Path) -> sqlite3.Connection:
        source = sqlite3.connect(str(path))
        clone = sqlite3.connect(":memory:")
        try:
            source.backup(clone)
        finally:
            source.close()
        clone.row_factory = sqlite3.Row
        clone.execute("PRAGMA ignore_check_constraints=ON")
        return clone

    def _assert_replay_succeeds(
        self,
        base: Path,
        operation: Mapping[str, Any],
        status: Mapping[str, Any],
    ) -> None:
        connection = self._clone(base)
        try:
            old_hash = connection.execute(
                "SELECT status_hash FROM registration_runtime_status "
                "WHERE subject_key=?",
                (status["subject_key"],),
            ).fetchone()[0]
            connection.execute("BEGIN")
            _insert_row(
                connection, "registration_operation_audit", operation
            )
            _update_status(
                connection, status, expected_status_hash=old_hash
            )
            connection.execute("COMMIT")
        finally:
            connection.close()

    def _assert_operation_rejected(
        self,
        base: Path,
        operation: Mapping[str, Any],
        *,
        changes: Mapping[str, Any] | None = None,
        prepare: Callable[[sqlite3.Connection], None] | None = None,
    ) -> None:
        connection = self._clone(base)
        try:
            if prepare is not None:
                connection.execute("BEGIN")
                prepare(connection)
                connection.execute("COMMIT")
            candidate = dict(operation)
            if changes:
                candidate.update(changes)
            candidate["operation_envelope_hash"] = (
                registration_hashes.derive(
                    "operation_envelope_hash", candidate
                )
            )
            before = connection.execute(
                "SELECT COUNT(*) FROM registration_operation_audit"
            ).fetchone()[0]
            connection.execute("BEGIN")
            with self.assertRaises(sqlite3.IntegrityError):
                _insert_row(
                    connection,
                    "registration_operation_audit",
                    candidate,
                )
            connection.execute("ROLLBACK")
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM registration_operation_audit"
                ).fetchone()[0],
                before,
            )
        finally:
            connection.close()

    def _assert_status_rejected(
        self,
        base: Path,
        operation: Mapping[str, Any],
        status: Mapping[str, Any],
        *,
        prepare: Callable[[sqlite3.Connection], None] | None = None,
        status_changes: Mapping[str, Any] | None = None,
    ) -> None:
        connection = self._clone(base)
        try:
            old_hash = connection.execute(
                "SELECT status_hash FROM registration_runtime_status "
                "WHERE subject_key=?",
                (status["subject_key"],),
            ).fetchone()[0]
            candidate_status = dict(status)
            if status_changes:
                candidate_status.update(status_changes)
                candidate_status["status_hash"] = (
                    registration_hashes.derive(
                        "status_hash", candidate_status
                    )
                )
            candidate_operation = dict(operation)
            candidate_operation["target_status_hash"] = candidate_status[
                "status_hash"
            ]
            candidate_operation["operation_envelope_hash"] = (
                registration_hashes.derive(
                    "operation_envelope_hash", candidate_operation
                )
            )
            candidate_status["write_operation_hash"] = (
                candidate_operation["operation_envelope_hash"]
            )
            before = dict(
                connection.execute(
                    "SELECT * FROM registration_runtime_status "
                    "WHERE subject_key=?",
                    (status["subject_key"],),
                ).fetchone()
            )
            connection.execute("BEGIN")
            _without_trigger(
                connection,
                "trg_operation_audit_insert",
                lambda: _insert_row(
                    connection,
                    "registration_operation_audit",
                    candidate_operation,
                ),
            )
            if prepare is not None:
                prepare(connection)
            with self.assertRaises(sqlite3.IntegrityError):
                _update_status(
                    connection,
                    candidate_status,
                    expected_status_hash=old_hash,
                )
            connection.execute("ROLLBACK")
            self.assertEqual(
                dict(
                    connection.execute(
                        "SELECT * FROM registration_runtime_status "
                        "WHERE subject_key=?",
                        (status["subject_key"],),
                    ).fetchone()
                ),
                before,
            )
        finally:
            connection.close()

    def test_every_sql_v2_staged_recovery_predicate_is_necessary(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "state" / "registration-v1" / "registration.db"
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
                    staged_candidate=staged,
                    executor_secret=secret,
                )
                adopt_id = adopted.operation.operation_id
                effect_id = adopted.execution.effect_id
                pre_mark = root / "pre-mark.db"
                self._backup(harness.connection, pre_mark)
                marked = store.mark_unavailable(
                    harness.staged_data(),
                    staged,
                    adopted.execution,
                )
                self.assertIsInstance(
                    marked, registration_store.OperationResult
                )
                mark_operation = dict(
                    harness.connection.execute(
                        "SELECT * FROM registration_operation_audit "
                        "WHERE operation_id=?",
                        (marked.operation_id,),
                    ).fetchone()
                )
                mark_status = dict(
                    harness.connection.execute(
                        "SELECT * FROM registration_runtime_status "
                        "WHERE member_id=?",
                        (member_id,),
                    ).fetchone()
                )
                pre_reacquire = root / "pre-reacquire.db"
                self._backup(harness.connection, pre_reacquire)
                authority = store.read_selected_authority(member_id)
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
                    executor_secret=b"b" * 32,
                )
                self.assertIsInstance(
                    reacquired, registration_store.ExecutionResult
                )
                reacquire_operation = dict(
                    harness.connection.execute(
                        "SELECT * FROM registration_operation_audit "
                        "WHERE operation_id=?",
                        (reacquired.operation.operation_id,),
                    ).fetchone()
                )
                reacquire_status = dict(
                    harness.connection.execute(
                        "SELECT * FROM registration_runtime_status "
                        "WHERE member_id=?",
                        (member_id,),
                    ).fetchone()
                )

                self._assert_replay_succeeds(
                    pre_mark, mark_operation, mark_status
                )
                self._assert_replay_succeeds(
                    pre_reacquire,
                    reacquire_operation,
                    reacquire_status,
                )

                current_data = harness.data().writer_capability_hash
                operation_mutations = {
                    "staged-runtime": {
                        "runtime_capability_hash": (
                            current.runtime_capability_hash
                        )
                    },
                    "staged-writer-binary": {
                        "writer_binary_hash": current.writer_binary_hash
                    },
                    "staged-profile": {
                        "profile_hash": current.profile_hash
                    },
                    "staged-writer-capability": {
                        "writer_capability_receipt_hash": current_data
                    },
                    "staged-epoch": {
                        "target_staged_epoch_hash": "f" * 64
                    },
                    "member-selector": {"target_member_id": "f" * 64},
                    "effect-selector": {"target_effect_id": "f" * 64},
                    "executor-selector": {
                        "target_executor_token_hash": "f" * 64
                    },
                    "exact-recovery-projection": {
                        "projected_db_growth_bytes": 8_193
                    },
                    "non-recovery-data-in-draining": {
                        "operation_kind": "SCHEDULE_STATUS",
                        "runtime_capability_hash": (
                            current.runtime_capability_hash
                        ),
                        "writer_binary_hash": current.writer_binary_hash,
                        "profile_hash": current.profile_hash,
                        "writer_capability_receipt_hash": current_data,
                    },
                }
                for label, changes in operation_mutations.items():
                    with self.subTest(trigger="operation", predicate=label):
                        self._assert_operation_rejected(
                            pre_mark,
                            mark_operation,
                            changes=changes,
                        )

                def mutate_guarded(
                    trigger: str,
                    statement: str,
                    parameters: tuple[Any, ...] = (),
                ) -> Callable[[sqlite3.Connection], None]:
                    return lambda connection: _without_trigger(
                        connection,
                        trigger,
                        lambda: connection.execute(
                            statement, parameters
                        ),
                    )

                operation_state_kills = {
                    "member-phase": mutate_guarded(
                        "trg_member_update_state_machine",
                        "UPDATE registration_member SET phase='REQUESTED' "
                        "WHERE member_id=?",
                        (member_id,),
                    ),
                    "member-staged-generation": mutate_guarded(
                        "trg_member_update_state_machine",
                        "UPDATE registration_member "
                        "SET helper_generation=1 WHERE member_id=?",
                        (member_id,),
                    ),
                    "effect-open": mutate_guarded(
                        "trg_effect_close",
                        "UPDATE registration_effect "
                        "SET outcome_kind='SUCCESS' WHERE effect_id=?",
                        (effect_id,),
                    ),
                    "mark-executor-generation": mutate_guarded(
                        "trg_runtime_status_update",
                        "UPDATE registration_runtime_status "
                        "SET executor_generation=1 WHERE member_id=?",
                        (member_id,),
                    ),
                    "adopt-lineage": lambda connection: connection.execute(
                        "UPDATE registration_operation_audit "
                        "SET lineage_effect_id=? WHERE operation_id=?",
                        ("f" * 64, adopt_id),
                    ),
                }
                for label, prepare in operation_state_kills.items():
                    with self.subTest(trigger="operation", predicate=label):
                        self._assert_operation_rejected(
                            pre_mark,
                            mark_operation,
                            prepare=prepare,
                        )

                reacquire_state_kills = {
                    "reacquire-old-token-null": mutate_guarded(
                        "trg_runtime_status_update",
                        "UPDATE registration_runtime_status "
                        "SET executor_token_hash=?,executor_boot_id=?,"
                        "executor_generation=? WHERE member_id=?",
                        ("f" * 64, "boot-a", 2, member_id),
                    ),
                    "reacquire-help-due": mutate_guarded(
                        "trg_runtime_status_update",
                        "UPDATE registration_runtime_status "
                        "SET help_due=0 WHERE member_id=?",
                        (member_id,),
                    ),
                }
                for label, prepare in reacquire_state_kills.items():
                    with self.subTest(trigger="operation", predicate=label):
                        self._assert_operation_rejected(
                            pre_reacquire,
                            reacquire_operation,
                            prepare=prepare,
                        )

                staged_protocol_seq = mark_operation["protocol_seq"]
                staged_status_kills = {
                    "adopt-kind": lambda connection: connection.execute(
                        "UPDATE registration_operation_audit "
                        "SET operation_kind='ADVANCE_GENERATION' "
                        "WHERE operation_id=?",
                        (adopt_id,),
                    ),
                    "adopt-member": lambda connection: connection.execute(
                        "UPDATE registration_operation_audit "
                        "SET target_member_id=? WHERE operation_id=?",
                        ("f" * 64, adopt_id),
                    ),
                    "adopt-lineage": lambda connection: connection.execute(
                        "UPDATE registration_operation_audit "
                        "SET lineage_effect_id=? WHERE operation_id=?",
                        ("f" * 64, adopt_id),
                    ),
                    "adopt-staged-epoch": lambda connection: connection.execute(
                        "UPDATE registration_operation_audit "
                        "SET target_staged_epoch_hash=? WHERE operation_id=?",
                        ("f" * 64, adopt_id),
                    ),
                    "adopt-member-tuple": lambda connection: (
                        connection.execute(
                            "UPDATE registration_operation_audit "
                            "SET target_member_tuple_hash=? "
                            "WHERE operation_id=?",
                            ("f" * 64, adopt_id),
                        )
                    ),
                    "receiver-generation": lambda connection: (
                        connection.execute(
                            "UPDATE registration_protocol_epoch "
                            "SET staged_generation=99 "
                            "WHERE protocol_seq=?",
                            (staged_protocol_seq,),
                        )
                    ),
                    "member-receiver-generation": mutate_guarded(
                        "trg_member_update_state_machine",
                        "UPDATE registration_member "
                        "SET helper_generation=1 WHERE member_id=?",
                        (member_id,),
                    ),
                }
                for label, prepare in staged_status_kills.items():
                    with self.subTest(
                        trigger="reacquire-status", predicate=label
                    ):
                        self._assert_status_rejected(
                            pre_reacquire,
                            reacquire_operation,
                            reacquire_status,
                            prepare=prepare,
                        )

                with self.subTest(
                    trigger="reacquire-status",
                    predicate="receiver-executor-generation",
                ):
                    self._assert_status_rejected(
                        pre_reacquire,
                        reacquire_operation,
                        reacquire_status,
                        status_changes={"executor_generation": 1},
                    )
                reacquire_status_kills = {
                    "receiver-executor-token": {
                        "executor_token_hash": None
                    },
                    "receiver-executor-boot": {
                        "executor_boot_id": "boot-z"
                    },
                    "receiver-schedule-boot": {
                        "schedule_boot_id": "boot-a"
                    },
                }
                for label, changes in reacquire_status_kills.items():
                    with self.subTest(
                        trigger="reacquire-status", predicate=label
                    ):
                        self._assert_status_rejected(
                            pre_reacquire,
                            reacquire_operation,
                            reacquire_status,
                            status_changes=changes,
                        )

                mark_status_kills = {
                    "staged-old-executor-generation": mutate_guarded(
                        "trg_runtime_status_update",
                        "UPDATE registration_runtime_status "
                        "SET executor_generation=1 WHERE member_id=?",
                        (member_id,),
                    ),
                    "member-helper-generation": mutate_guarded(
                        "trg_member_update_state_machine",
                        "UPDATE registration_member "
                        "SET helper_generation=1 WHERE member_id=?",
                        (member_id,),
                    ),
                    "adopt-kind": lambda connection: connection.execute(
                        "UPDATE registration_operation_audit "
                        "SET operation_kind='ADVANCE_GENERATION' "
                        "WHERE operation_id=?",
                        (adopt_id,),
                    ),
                    "adopt-member": lambda connection: connection.execute(
                        "UPDATE registration_operation_audit "
                        "SET target_member_id=? WHERE operation_id=?",
                        ("f" * 64, adopt_id),
                    ),
                    "adopt-lineage": lambda connection: connection.execute(
                        "UPDATE registration_operation_audit "
                        "SET lineage_effect_id=? WHERE operation_id=?",
                        ("f" * 64, adopt_id),
                    ),
                    "adopt-staged-epoch": (
                        lambda connection: connection.execute(
                            "UPDATE registration_operation_audit "
                            "SET target_staged_epoch_hash=? "
                            "WHERE operation_id=?",
                            ("f" * 64, adopt_id),
                        )
                    ),
                    "adopt-member-tuple": (
                        lambda connection: connection.execute(
                            "UPDATE registration_operation_audit "
                            "SET target_member_tuple_hash=? "
                            "WHERE operation_id=?",
                            ("f" * 64, adopt_id),
                        )
                    ),
                }
                for label, prepare in mark_status_kills.items():
                    with self.subTest(
                        trigger="mark-status", predicate=label
                    ):
                        self._assert_status_rejected(
                            pre_mark,
                            mark_operation,
                            mark_status,
                            prepare=prepare,
                        )

                execution = reacquired.execution
                for ordinal in range(2):
                    store.mark_unavailable(
                        harness.staged_data(), staged, execution
                    )
                    authority = store.read_selected_authority(member_id)
                    recovered = store.reacquire_effect(
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
                        executor_secret=bytes([ord("c") + ordinal]) * 32,
                    )
                    self.assertIsInstance(
                        recovered, registration_store.ExecutionResult
                    )
                    execution = recovered.execution
                six_operation_state = root / "six-recovery.db"
                self._backup(harness.connection, six_operation_state)
                current_status = dict(
                    harness.connection.execute(
                        "SELECT * FROM registration_runtime_status "
                        "WHERE member_id=?",
                        (member_id,),
                    ).fetchone()
                )
                seventh = dict(mark_operation)
                revision = store.table_count(
                    "registration_operation_audit"
                )
                sample_mono = harness._next_mono()
                next_status = dict(current_status)
                next_status.update(
                    {
                        "status_version": (
                            int(current_status["status_version"]) + 1
                        ),
                        "schedule_boot_id": "boot-a",
                        "observed_now_mono_ns": sample_mono,
                        "next_due_mono_ns": sample_mono,
                        "due_since_mono_ns": sample_mono,
                        "attempt_count": min(
                            255,
                            int(current_status["attempt_count"] or 0) + 1,
                        ),
                        "backoff_ns": 0,
                        "help_due": 1,
                        "executor_token_hash": None,
                        "executor_boot_id": None,
                        "executor_generation": None,
                        "unavailable_count": 3,
                        "yield_count": 3,
                        "reason_code": "RESOLVER_UNAVAILABLE",
                    }
                )
                next_status["status_hash"] = registration_hashes.derive(
                    "status_hash", next_status
                )
                seventh.update(
                    {
                        "operation_seq": revision + 1,
                        "operation_id": "f0" * 32,
                        "expected_revision": revision,
                        "target_executor_token_hash": current_status[
                            "executor_token_hash"
                        ],
                        "expected_target_status_hash": current_status[
                            "status_hash"
                        ],
                        "target_status_hash": next_status["status_hash"],
                        "sample_mono_ns": sample_mono,
                        "created_wall_ns": harness._next_wall(),
                    }
                )
                seventh["operation_envelope_hash"] = (
                    registration_hashes.derive(
                        "operation_envelope_hash", seventh
                    )
                )
                with self.subTest(
                    trigger="operation", predicate="six-operation-limit"
                ):
                    self._assert_operation_rejected(
                        six_operation_state, seventh
                    )

                def isolate_recovery_count(
                    connection: sqlite3.Connection,
                ) -> None:
                    connection.execute(
                        "UPDATE registration_operation_audit "
                        "SET projected_db_growth_bytes=0 "
                        "WHERE operation_kind IN"
                        "('MARK_UNAVAILABLE','REACQUIRE_EFFECT') "
                        "AND target_effect_id=?",
                        (effect_id,),
                    )

                def isolate_recovery_sum(
                    connection: sqlite3.Connection,
                ) -> None:
                    connection.execute(
                        "UPDATE registration_operation_audit "
                        "SET operation_kind='SCHEDULE_STATUS' "
                        "WHERE operation_id=("
                        "SELECT operation_id "
                        "FROM registration_operation_audit "
                        "WHERE operation_kind IN"
                        "('MARK_UNAVAILABLE','REACQUIRE_EFFECT') "
                        "AND target_effect_id=? ORDER BY operation_seq "
                        "LIMIT 1)",
                        (effect_id,),
                    )
                    connection.execute(
                        "UPDATE registration_operation_audit "
                        "SET projected_db_growth_bytes=16384 "
                        "WHERE operation_id=("
                        "SELECT operation_id "
                        "FROM registration_operation_audit "
                        "WHERE operation_kind IN"
                        "('MARK_UNAVAILABLE','REACQUIRE_EFFECT') "
                        "AND target_effect_id=? ORDER BY operation_seq "
                        "LIMIT 1)",
                        (effect_id,),
                    )

                with self.subTest(
                    trigger="operation",
                    predicate="six-operation-count-limit",
                ):
                    self._assert_operation_rejected(
                        six_operation_state,
                        seventh,
                        prepare=isolate_recovery_count,
                    )
                with self.subTest(
                    trigger="operation",
                    predicate="recovery-byte-sum-limit",
                ):
                    self._assert_operation_rejected(
                        six_operation_state,
                        seventh,
                        prepare=isolate_recovery_sum,
                    )
                if execution.held:
                    execution.close()

            writable_db = (
                root
                / "writable"
                / "state"
                / "registration-v1"
                / "registration.db"
            )
            with RegistrationHarness.open(
                writable_db, measured_free_bytes=2 * 1024**3
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
                    staged_candidate=staged,
                    executor_secret=b"a" * 32,
                )
                adopted.execution.close()
                dead = harness.connection.execute(
                    "SELECT status_hash FROM registration_runtime_status "
                    "WHERE member_id=?",
                    (member_id,),
                ).fetchone()
                store.mark_dead_executor_unavailable(
                    harness.staged_data(),
                    staged,
                    member_id=member_id,
                    expected_status_hash=dead["status_hash"],
                )
                store.advance_generation(
                    harness.control(),
                    current,
                    quiescence_proof_hash="a" * 64,
                    staged_candidate=staged,
                )
                writable_pre_reacquire = root / "writable-pre-reacquire.db"
                self._backup(
                    harness.connection, writable_pre_reacquire
                )
                authority = store.read_selected_authority(member_id)
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
                    executor_secret=b"b" * 32,
                )
                writable_operation = dict(
                    harness.connection.execute(
                        "SELECT * FROM registration_operation_audit "
                        "WHERE operation_id=?",
                        (reacquired.operation.operation_id,),
                    ).fetchone()
                )
                writable_status = dict(
                    harness.connection.execute(
                        "SELECT * FROM registration_runtime_status "
                        "WHERE member_id=?",
                        (member_id,),
                    ).fetchone()
                )
                self._assert_replay_succeeds(
                    writable_pre_reacquire,
                    writable_operation,
                    writable_status,
                )
                adopted_operation = dict(
                    harness.connection.execute(
                        "SELECT * FROM registration_operation_audit "
                        "WHERE operation_id=?",
                        (adopted.operation.operation_id,),
                    ).fetchone()
                )
                source_protocol_seq = adopted_operation["protocol_seq"]
                effect_id = reacquired.execution.effect_id
                writable_status_kills = {
                    "adopt-kind": lambda connection: connection.execute(
                        "UPDATE registration_operation_audit "
                        "SET operation_kind='ADVANCE_GENERATION' "
                        "WHERE operation_id=?",
                        (adopted.operation.operation_id,),
                    ),
                    "adopt-member": lambda connection: connection.execute(
                        "UPDATE registration_operation_audit "
                        "SET target_member_id=? WHERE operation_id=?",
                        ("f" * 64, adopted.operation.operation_id),
                    ),
                    "adopt-lineage": lambda connection: connection.execute(
                        "UPDATE registration_operation_audit "
                        "SET lineage_effect_id=? WHERE operation_id=?",
                        ("f" * 64, adopted.operation.operation_id),
                    ),
                    "adopt-generation": lambda connection: (
                        connection.execute(
                            "UPDATE registration_operation_audit "
                            "SET expected_generation=99 "
                            "WHERE operation_id=?",
                            (adopted.operation.operation_id,),
                        )
                    ),
                    "adopt-action-plan": lambda connection: (
                        connection.execute(
                            "UPDATE registration_operation_audit "
                            "SET target_action_plan_hash=? "
                            "WHERE operation_id=?",
                            ("f" * 64, adopted.operation.operation_id),
                        )
                    ),
                    "adopt-staged-epoch": lambda connection: (
                        connection.execute(
                            "UPDATE registration_operation_audit "
                            "SET target_staged_epoch_hash=? "
                            "WHERE operation_id=?",
                            ("f" * 64, adopted.operation.operation_id),
                        )
                    ),
                    "source-protocol-generation": lambda connection: (
                        connection.execute(
                            "UPDATE registration_protocol_epoch "
                            "SET protocol_generation=99 "
                            "WHERE protocol_seq=?",
                            (source_protocol_seq,),
                        )
                    ),
                    "source-runtime": lambda connection: connection.execute(
                        "UPDATE registration_protocol_epoch "
                        "SET runtime_capability_hash=? "
                        "WHERE protocol_seq=?",
                        ("f" * 64, source_protocol_seq),
                    ),
                    "receiver-runtime": lambda connection: (
                        connection.execute(
                            "UPDATE registration_protocol_epoch "
                            "SET staged_runtime_capability_hash=? "
                            "WHERE protocol_seq=?",
                            ("f" * 64, source_protocol_seq),
                        )
                    ),
                    "receiver-generation": lambda connection: (
                        connection.execute(
                            "UPDATE registration_protocol_epoch "
                            "SET staged_generation=99 "
                            "WHERE protocol_seq=?",
                            (source_protocol_seq,),
                        )
                    ),
                    "effect-source-generation": mutate_guarded(
                        "trg_effect_close",
                        "UPDATE registration_effect "
                        "SET required_protocol_generation=99 "
                        "WHERE effect_id=?",
                        (effect_id,),
                    ),
                    "effect-source-runtime": mutate_guarded(
                        "trg_effect_close",
                        "UPDATE registration_effect "
                        "SET required_runtime_capability_hash=? "
                        "WHERE effect_id=?",
                        ("f" * 64, effect_id),
                    ),
                }
                for label, prepare in writable_status_kills.items():
                    with self.subTest(
                        trigger="writable-reacquire-status",
                        predicate=label,
                    ):
                        self._assert_status_rejected(
                            writable_pre_reacquire,
                            writable_operation,
                            writable_status,
                            prepare=prepare,
                        )
                reacquired.execution.close()


if __name__ == "__main__":
    unittest.main()
