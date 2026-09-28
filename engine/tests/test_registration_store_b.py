from __future__ import annotations

import tempfile
import sqlite3
import unittest
from pathlib import Path

from engine import registration_store
from engine.tests.registration_harness import RegistrationHarness


@unittest.skipUnless(
    sqlite3.sqlite_version_info >= registration_store.MIN_SQLITE_VERSION,
    "ADR 0025 requires stock SQLite >=3.51.3",
)
class BodyBTypedStoreReadTest(unittest.TestCase):
    def test_find_member_episode_and_due_order_are_typed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                expected = []
                for ordinal in range(1, 11):
                    identity = harness.identity(ordinal=ordinal)
                    store.install_member(
                        harness.data(),
                        candidate,
                        identity,
                        harness.clean_intent(ordinal=ordinal),
                        sample_boot_id="boot-a",
                        sample_mono_ns=ordinal,
                    )
                    member_id = store.find_member_id(identity)
                    self.assertIsNotNone(member_id)
                    expected.append((ordinal, member_id))
                due = store.list_due_candidates(
                    boot_id="boot-a", now_mono_ns=100, limit=8
                )
                self.assertEqual(len(due), 8)
                self.assertEqual(
                    [row.member_id for row in due],
                    [member_id for _ordinal, member_id in expected[:8]],
                )
                self.assertTrue(
                    all(row.phase == "REQUESTED" for row in due)
                )
                self.assertTrue(
                    all(row.status_hash for row in due)
                )

    def test_reboot_candidates_are_selected_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                identity = harness.identity()
                store.install_member(
                    harness.data(),
                    candidate,
                    identity,
                    harness.clean_intent(),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                before = store.table_count("registration_operation_audit")
                candidates = store.list_reboot_candidates("boot-b")
                self.assertEqual(len(candidates), 1)
                self.assertEqual(candidates[0].stored_boot_id, "boot-a")
                self.assertEqual(
                    store.table_count("registration_operation_audit"), before
                )

    def test_path_rename_cannot_create_duplicate_physical_member(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state" / "registration-v1" / "registration.db"
            with RegistrationHarness.open(
                db, measured_free_bytes=2 * 1024**3
            ) as harness:
                store = harness.store
                candidate = harness.candidate()
                store.bootstrap(harness.control(), candidate)
                store.activate(harness.control(), candidate)
                identity = harness.identity()
                store.install_member(
                    harness.data(),
                    candidate,
                    identity,
                    harness.clean_intent(),
                    sample_boot_id="boot-a",
                    sample_mono_ns=1,
                )
                moved = type(identity)(
                    **{
                        **identity.__dict__,
                        "canonical_root": "/fixture/moved-root",
                        "git_toplevel": "/fixture/moved-root",
                    }
                )
                before = store.table_count("registration_member")
                with self.assertRaises(registration_store.StaleAuthority):
                    store.find_member_id(moved)
                self.assertEqual(store.table_count("registration_member"), before)


if __name__ == "__main__":
    unittest.main()
