from __future__ import annotations

import multiprocessing
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from engine import registration_lock, registration_store
from engine.tests.registration_harness import RegistrationHarness


def _hold_member_lock(
    directory: str,
    member_id: str,
    acquired: multiprocessing.synchronize.Event,
    release: multiprocessing.synchronize.Event,
) -> None:
    manager = registration_lock.LockManager(Path(directory))
    with manager.acquire_member(member_id):
        acquired.set()
        release.wait(10)


def _acquire_then_die(
    directory: str,
    member_id: str,
    acquired: multiprocessing.synchronize.Event,
) -> None:
    manager = registration_lock.LockManager(Path(directory))
    manager.acquire_member(member_id)
    acquired.set()
    os._exit(0)


def _open_racer(
    db: str,
    member_id: str,
    member_hash: str,
    effect_hash: str,
    status_hash: str,
    ready: multiprocessing.synchronize.Event,
    start: multiprocessing.synchronize.Event,
    output: multiprocessing.queues.Queue,
    secret_byte: bytes,
) -> None:
    try:
        harness = RegistrationHarness.open(
            Path(db), measured_free_bytes=2 * 1024**3
        )
        ready.set()
        start.wait(10)
        try:
            result = harness.store.open_effect(
                harness.data(),
                harness.candidate(),
                member_id=member_id,
                expected_member_hash=member_hash,
                expected_effect_hash=effect_hash,
                expected_status_hash=status_hash,
                executor_secret=secret_byte * 32,
            )
        except registration_store.StaleAuthority:
            output.put("STALE")
        else:
            result.execution.close()
            output.put("COMMITTED")
        finally:
            harness.close()
    except Exception as exc:  # pragma: no cover - returned to parent
        output.put(f"ERROR:{type(exc).__name__}:{exc}")


@unittest.skipUnless(
    sqlite3.sqlite_version_info >= registration_store.MIN_SQLITE_VERSION,
    "ADR 0025 requires stock SQLite >=3.51.3",
)
class RegistrationLockTest(unittest.TestCase):
    def test_lock_order_forbids_protocol_after_member_and_second_member(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = registration_lock.LockManager(Path(tmp) / "locks")
            first = manager.acquire_member("11" * 32)
            try:
                with self.assertRaises(registration_lock.LockOrderError):
                    manager.acquire_member("22" * 32)
                with self.assertRaises(registration_lock.LockOrderError):
                    manager.acquire_protocol()
            finally:
                first.release()
            with manager.acquire_protocol():
                with manager.acquire_member("11" * 32):
                    pass

    def test_process_contention_and_death_release_without_sleep(self) -> None:
        context = multiprocessing.get_context("spawn")
        with tempfile.TemporaryDirectory() as tmp:
            directory = str(Path(tmp) / "locks")
            member_id = "11" * 32
            acquired = context.Event()
            release = context.Event()
            process = context.Process(
                target=_hold_member_lock,
                args=(directory, member_id, acquired, release),
            )
            process.start()
            self.assertTrue(acquired.wait(10))
            manager = registration_lock.LockManager(Path(directory))
            with self.assertRaises(registration_lock.LockBusy):
                manager.acquire_member(member_id, timeout=0)
            release.set()
            process.join(10)
            self.assertEqual(process.exitcode, 0)
            with manager.acquire_member(member_id, timeout=1):
                pass

            died = context.Event()
            process = context.Process(
                target=_acquire_then_die,
                args=(directory, member_id, died),
            )
            process.start()
            self.assertTrue(died.wait(10))
            process.join(10)
            self.assertEqual(process.exitcode, 0)
            with manager.acquire_member(member_id, timeout=1):
                pass


@unittest.skipUnless(
    sqlite3.sqlite_version_info >= registration_store.MIN_SQLITE_VERSION,
    "ADR 0025 requires stock SQLite >=3.51.3",
)
class RegistrationOpenRaceTest(unittest.TestCase):
    def test_two_process_open_race_has_one_committed_executor(self) -> None:
        context = multiprocessing.get_context("spawn")
        with tempfile.TemporaryDirectory() as tmp:
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
                row = harness.connection.execute(
                    "SELECT m.member_id,m.member_tuple_hash,"
                    "e.request_tuple_hash,s.status_hash "
                    "FROM registration_member m "
                    "JOIN registration_effect e "
                    "ON e.effect_id=m.current_effect_id "
                    "JOIN registration_runtime_status s USING(member_id)"
                ).fetchone()
                values = tuple(row)
            start = context.Event()
            ready_a = context.Event()
            ready_b = context.Event()
            output = context.Queue()
            processes = [
                context.Process(
                    target=_open_racer,
                    args=(
                        str(db),
                        *values,
                        ready,
                        start,
                        output,
                        secret,
                    ),
                )
                for ready, secret in ((ready_a, b"a"), (ready_b, b"b"))
            ]
            for process in processes:
                process.start()
            self.assertTrue(ready_a.wait(10))
            self.assertTrue(ready_b.wait(10))
            start.set()
            results = [output.get(timeout=15), output.get(timeout=15)]
            for process in processes:
                process.join(10)
                self.assertEqual(process.exitcode, 0)
            self.assertCountEqual(results, ["COMMITTED", "STALE"])
            connection = RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            )
            try:
                status = connection.connection.execute(
                    "SELECT executor_token_hash,status_version "
                    "FROM registration_runtime_status"
                ).fetchone()
                self.assertIsNotNone(status["executor_token_hash"])
                self.assertEqual(status["status_version"], 2)
                self.assertEqual(
                    connection.connection.execute(
                        "SELECT COUNT(*) FROM registration_operation_audit "
                        "WHERE operation_kind='OPEN_EFFECT'"
                    ).fetchone()[0],
                    1,
                )
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
