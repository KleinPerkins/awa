"""M1-A.1: status-last integrity store and live read-only SQLite path."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sqlite3
import stat
import unittest
from pathlib import Path
from unittest import mock

from engine import integrity, paths, state as state_mod
from engine.tests.helpers import EngineTestCase


class TestIntegrityStore(EngineTestCase):
    def _status(self, overall: str = "green") -> dict:
        return {
            "overall": overall,
            "invariants": [],
            "triggers": {},
            "orphans": {
                "worktrees": 0,
                "leases_unreconciled": 0,
                "sessions_dangling": 0,
                "husks": 0,
            },
            "recovery": {
                "last_status": "ok",
                "needs_repair": 0,
                "quarantine_count": 0,
            },
            "alert": {
                "last_transition": None,
                "attempted": [],
                "delivered": {"native": "accepted", "slack": "opted_out"},
            },
        }

    def commit(self, gen: int, overall: str = "green") -> dict:
        actual = integrity._commit(self._status(overall), profile="deep", trigger="cli")
        self.assertEqual(actual, gen)
        committed = integrity.read_status()
        self.assertIsNotNone(committed)
        return committed

    def _replace_cut(self, target: Path) -> None:
        original = os.replace

        def cut(src, dst):
            if Path(dst) == target:
                raise OSError(f"crash cut before {target.name}")
            return original(src, dst)

        with mock.patch.object(integrity.os, "replace", side_effect=cut):
            with self.assertRaises(OSError):
                integrity._commit(self._status("degraded"), profile="deep", trigger="cli")

    def _assert_artifact_cut(self, child: str) -> None:
        before = self.commit(1)
        extension = "html" if child == "console" else "json"
        target = paths.integrity_dir() / child / f"2.{extension}"
        self._replace_cut(target)
        after = integrity.read_status()
        self.assertEqual(after, before)
        referenced = {
            ref["path"] for ref in after["artifacts"].values()
        }
        orphans = {
            str(p.relative_to(paths.integrity_dir()))
            for p in paths.integrity_dir().glob("*/2.*")
        }
        self.assertTrue(orphans)
        self.assertTrue(orphans.isdisjoint(referenced))
        self.commit(2, "degraded")

    def test_status_last_and_private_and_versioned(self):
        status_doc = self.commit(1)
        status_path = paths.integrity_status_path()
        self.assertEqual(stat.S_IMODE(status_path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(paths.integrity_dir().stat().st_mode), 0o700)
        self.assertEqual(status_doc["schema"], integrity.SCHEMA)
        self.assertEqual(status_doc["generation"], 1)
        for name, ref in status_doc["artifacts"].items():
            with self.subTest(name=name):
                artifact = paths.integrity_dir() / ref["path"]
                self.assertTrue(artifact.is_file(), artifact)
                self.assertEqual(stat.S_IMODE(artifact.stat().st_mode), 0o600)
                self.assertEqual(
                    hashlib.sha256(artifact.read_bytes()).hexdigest(),
                    ref["sha256"],
                )

    def test_crash_before_status_replace_keeps_prev(self):
        before = self.commit(1)
        self._replace_cut(paths.integrity_status_path())
        self.assertEqual(integrity.read_status(), before)
        referenced = {
            ref["path"] for ref in before["artifacts"].values()
        }
        orphans = {
            str(p.relative_to(paths.integrity_dir()))
            for p in paths.integrity_dir().glob("*/2.*")
        }
        self.assertEqual(len(orphans), 4)
        self.assertTrue(orphans.isdisjoint(referenced))
        self.commit(2, "degraded")

    def test_child_dir_fsynced_after_each_artifact_rename(self):
        fsynced: list[Path] = []
        original = integrity._fsync_dir

        def record(path: Path) -> None:
            fsynced.append(path.resolve())
            original(path)

        with mock.patch.object(integrity, "_fsync_dir", side_effect=record):
            self.commit(1)

        root = paths.integrity_dir().resolve()
        self.assertIn(root, fsynced)
        for child in ("history", "public", "console", "outbox"):
            self.assertIn((root / child).resolve(), fsynced, child)

    def test_crash_cut_after_history_rename_before_public(self):
        self._assert_artifact_cut("public")

    def test_crash_cut_after_public_rename_before_console(self):
        self._assert_artifact_cut("console")

    def test_crash_cut_after_console_rename_before_outbox(self):
        self._assert_artifact_cut("outbox")

    def test_crash_cut_after_all_artifacts_before_status_replace(self):
        before = self.commit(1)
        self._replace_cut(paths.integrity_status_path())
        self.assertEqual(integrity.read_status(), before)
        self.commit(2, "degraded")

    def test_prune_unlink_fsyncs_child_dir(self):
        self.commit(1)
        events: list[tuple[str, Path]] = []
        original_unlink = os.unlink
        original_fsync_dir = integrity._fsync_dir

        def record_unlink(path, *args, **kwargs):
            events.append(("unlink", Path(path).resolve()))
            return original_unlink(path, *args, **kwargs)

        def record_fsync_dir(path: Path):
            events.append(("fsync", path.resolve()))
            return original_fsync_dir(path)

        with mock.patch.object(integrity, "HISTORY_MAX", 1), \
                mock.patch.object(
                    integrity.os, "unlink", side_effect=record_unlink
                ), mock.patch.object(
                    integrity, "_fsync_dir", side_effect=record_fsync_dir
                ):
            self.commit(2)

        root = paths.integrity_dir().resolve()
        for child in ("history", "public", "console", "outbox"):
            child_path = root / child
            unlink_at = next(
                i for i, event in enumerate(events)
                if event == ("unlink", child_path / f"1.{('html' if child == 'console' else 'json')}")
            )
            self.assertIn(("fsync", child_path), events[unlink_at + 1 :], child)

    def test_reader_ignores_unreferenced_artifact(self):
        committed = self.commit(1)
        stray = paths.integrity_dir() / "public" / "999.json"
        stray.write_text('{"stray":true}\n', encoding="utf-8")
        os.chmod(stray, 0o600)
        self.assertEqual(integrity.read_status(), committed)
        self.assertNotIn("999.json", json.dumps(integrity.read_status()))

    def test_stale_generation_refused(self):
        for gen in range(1, 6):
            self.commit(gen)
        stale = self._status()
        stale["generation"] = 4
        with self.assertRaises(integrity.StaleGenerationError):
            integrity._commit(stale, profile="deep", trigger="cli")
        self.assertEqual(integrity.read_status()["generation"], 5)

    def test_missing_or_malformed_reads_none(self):
        self.assertIsNone(integrity.read_status())
        paths.ensure_dir(paths.integrity_dir())
        paths.integrity_status_path().write_text('{"schema":', encoding="utf-8")
        self.assertIsNone(integrity.read_status())

    def test_ro_conn_sees_wal_only_row_and_refuses_write(self):
        with state_mod.State() as live:
            live.conn.execute(
                "INSERT INTO events(ts,lease_id,kind,detail) VALUES(?,?,?,?)",
                ("2026-08-24T00:00:00Z", None, "wal-only", "visible"),
            )
            self.assertTrue(Path(str(live.db_path) + "-wal").exists())
            ro = integrity._ro_conn()
            try:
                row = ro.execute(
                    "SELECT kind FROM events WHERE kind='wal-only'"
                ).fetchone()
                self.assertEqual(row["kind"], "wal-only")
                with self.assertRaises(sqlite3.OperationalError):
                    ro.execute("CREATE TABLE x(a)")
            finally:
                ro.close()

    def test_full_write_no_short_bytes(self):
        original = os.write

        def short_write(fd: int, data: bytes) -> int:
            return original(fd, data[: max(1, min(7, len(data)))])

        with mock.patch.object(integrity.os, "write", side_effect=short_write):
            committed = self.commit(1)
        decoded = json.loads(paths.integrity_status_path().read_text(encoding="utf-8"))
        self.assertEqual(decoded, committed)
        for ref in committed["artifacts"].values():
            artifact = paths.integrity_dir() / ref["path"]
            self.assertEqual(
                hashlib.sha256(artifact.read_bytes()).hexdigest(),
                ref["sha256"],
            )

    def test_only_commit_acquires_lock(self):
        acquires = 0

        @contextlib.contextmanager
        def fake_lock():
            nonlocal acquires
            acquires += 1
            yield

        with mock.patch.object(integrity, "_integrity_lock", fake_lock):
            self.commit(1)
            integrity.read_status()
        self.assertEqual(acquires, 1)


if __name__ == "__main__":
    unittest.main()
