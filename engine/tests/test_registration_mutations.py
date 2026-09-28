from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from engine import registration_schema, registration_store
from engine.tests.registration_harness import RegistrationHarness


MEMBER_MUTATIONS = {
    "policy_basis_hash": "ab" * 32,
    "operation_basis_hash": "ac" * 32,
    "lifecycle_basis_hash": "ad" * 32,
    "current_basis_hash": "ae" * 32,
    "member_epoch": 2,
    "phase": "EFFECT_IN_FLIGHT",
    "current_effect_id": "af" * 32,
    "helper_generation": 2,
    "current_outcome_kind": "SUCCESS",
    "current_completion_hash": "b0" * 32,
    "current_proof_hash": "b1" * 32,
    "current_certificate_hash": "b2" * 32,
    "current_conflict_hash": "b3" * 32,
    "pending_effect_id": "b4" * 32,
    "pending_member_epoch": 2,
    "pending_basis_hash": "b5" * 32,
    "pending_effect_tuple_hash": "b6" * 32,
}
STATUS_MUTATIONS = {
    "member_epoch": 2,
    "current_effect_id": "c0" * 32,
    "schedule_boot_id": "changed-boot",
    "observed_now_mono_ns": 2,
    "next_due_mono_ns": 2,
    "due_since_mono_ns": 2,
    "attempt_count": 2,
    "backoff_ns": 1,
    "help_due": 1,
    "executor_token_hash": "c1" * 32,
    "executor_boot_id": "boot-a",
    "executor_generation": 1,
    "unavailable_count": 1,
    "yield_count": 1,
    "blocked_basis_fingerprint": "c2" * 32,
    "reason_code": "BASIS_UNSTABLE",
}


@unittest.skipUnless(
    sqlite3.sqlite_version_info >= registration_store.MIN_SQLITE_VERSION,
    "ADR 0025 requires stock SQLite >=3.51.3",
)
class RegistrationMutationKillTest(unittest.TestCase):
    def _fixture(self, directory: str) -> tuple[Path, str]:
        db = Path(directory) / "state" / "registration-v1" / "registration.db"
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
        return db, member_id

    def test_every_rejecting_trigger_uses_total_is_not_true_guard(self) -> None:
        connection = sqlite3.connect(":memory:")
        try:
            connection.executescript(registration_schema.canonical_sql_text())
            triggers = connection.execute(
                "SELECT name,sql FROM sqlite_schema WHERE type='trigger'"
            ).fetchall()
            self.assertEqual(len(triggers), 9)
            for name, sql in triggers:
                with self.subTest(trigger=name):
                    self.assertIn("IS NOT TRUE", sql)
                    self.assertIn("RAISE(ABORT", sql)
        finally:
            connection.close()

    def test_drain_tuple_rejects_half_null_and_null_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db, _member_id = self._fixture(tmp)
            connection = sqlite3.connect(str(db), isolation_level=None)
            try:
                for boot, deadline in (("boot", None), (None, 1)):
                    with self.subTest(boot=boot, deadline=deadline):
                        with self.assertRaises(sqlite3.IntegrityError):
                            connection.execute("BEGIN IMMEDIATE")
                            connection.execute(
                                "UPDATE registration_protocol_epoch "
                                "SET mode='DRAINING',drain_boot_id=?,"
                                "drain_deadline_mono_ns=? "
                                "WHERE protocol_seq=("
                                "SELECT MAX(protocol_seq) "
                                "FROM registration_protocol_epoch)",
                                (boot, deadline),
                            )
                        if connection.in_transaction:
                            connection.execute("ROLLBACK")
            finally:
                connection.close()

    def test_t03_and_t09_one_column_mutations_all_reject(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db, member_id = self._fixture(tmp)
            connection = sqlite3.connect(str(db), isolation_level=None)
            try:
                for table, mutations in (
                    ("registration_member", MEMBER_MUTATIONS),
                    ("registration_runtime_status", STATUS_MUTATIONS),
                ):
                    for column, value in mutations.items():
                        with self.subTest(table=table, column=column):
                            with self.assertRaises(sqlite3.IntegrityError):
                                connection.execute("BEGIN IMMEDIATE")
                                connection.execute(
                                    f"UPDATE {table} SET {column}=? "
                                    "WHERE member_id=?",
                                    (value, member_id),
                                )
                            if connection.in_transaction:
                                connection.execute("ROLLBACK")
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
