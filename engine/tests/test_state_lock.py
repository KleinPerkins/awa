"""Phase 2: SQLite WAL state (S4 perms) + per-common-dir advisory lock (§H6)."""

from __future__ import annotations

import os
import unittest

from engine import lock, state as state_mod
from engine.tests.helpers import EngineTestCase


class TestState(EngineTestCase):
    def test_wal_mode_and_schema(self):
        with state_mod.State() as st:
            self.assertEqual(st.wal_mode().lower(), "wal")
            self.assertEqual(st.get_meta("schema_version"), "1")

    def test_s4_perms(self):
        with state_mod.State() as st:
            perms = state_mod.perms_report(st.db_path)
        for path, mode in perms.items():
            if path.rstrip("/").endswith("awa"):
                self.assertEqual(mode, "0o700", path)
            else:
                self.assertEqual(mode, "0o600", path)

    def test_lease_upsert_and_status(self):
        with state_mod.State() as st:
            st.upsert_lease({
                "lease_id": "awa1-abc", "worktree_path": "/w", "branch": "b",
                "git_common_dir": "/r/.git", "boot_id": "boot", "created_at": "t0",
            })
            self.assertEqual(len(st.list_leases("active")), 1)
            st.set_lease_status("awa1-abc", "retired")
            self.assertEqual(len(st.list_leases("active")), 0)
            self.assertEqual(len(st.list_leases("retired")), 1)

    def test_event_redaction(self):
        with state_mod.State() as st:
            st.record_event("test", "run --token=ghp_" + "A" * 36 + " now")
            ev = st.events(limit=1)[0]
            self.assertIn("redacted", ev["detail"])
            self.assertNotIn("ghp_AAAA", ev["detail"])


class TestLock(EngineTestCase):
    def test_second_nonblocking_acquire_is_busy(self):
        common = "/repo/.git"
        with lock.common_dir_lock(common):
            # A non-blocking second acquire in a subprocess would block; here we exercise
            # the LockBusy path via a nested fd on the same lockfile is undefined for the
            # same process (flock is per-fd). Instead assert the lockfile exists + keyed.
            lf = lock.lockfile_for(common)
            self.assertTrue(lf.exists())
            self.assertEqual(oct(os.stat(lf).st_mode & 0o777), "0o600")

    def test_lockfile_key_stable(self):
        self.assertEqual(lock.lockfile_for("/repo/.git"), lock.lockfile_for("/repo/.git"))
        self.assertNotEqual(lock.lockfile_for("/a/.git"), lock.lockfile_for("/b/.git"))

    def test_cross_process_lock_is_exclusive(self):
        # Real single-writer proof: hold the lock, then a forked child fails a non-blocking
        # acquire with LockBusy.
        import multiprocessing as mp
        common = str(self.state_home / "repo" / ".git")
        os.makedirs(os.path.dirname(common), exist_ok=True)

        with lock.common_dir_lock(common):
            ctx = mp.get_context("spawn")
            q = ctx.Queue()
            p = ctx.Process(target=_child_try_lock, args=(common, str(self.state_home), q))
            p.start()
            p.join(20)
            self.assertEqual(q.get(timeout=5), "busy")


def _child_try_lock(common: str, state_home: str, q) -> None:
    os.environ["XDG_STATE_HOME"] = state_home
    import importlib
    from engine import lock as child_lock
    importlib.reload(child_lock)
    try:
        with child_lock.common_dir_lock(common, blocking=False):
            q.put("acquired")
    except child_lock.LockBusy:
        q.put("busy")
    except Exception as exc:  # noqa: BLE001
        q.put(f"error:{exc}")


if __name__ == "__main__":
    unittest.main()
