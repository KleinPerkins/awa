"""Phase 4: watcher/daemon single-instance + quarantine-ref cleanup/retention."""

from __future__ import annotations

import time
import unittest

from engine import daemon as daemon_mod, state as state_mod
from engine.tests.helpers import EngineTestCase


class TestSingleInstance(EngineTestCase):
    def test_second_instance_refused(self):
        first = daemon_mod.SingleInstance()
        first.acquire()
        try:
            self.assertTrue(first.is_running())
            second = daemon_mod.SingleInstance()
            with self.assertRaises(daemon_mod.AlreadyRunning):
                second.acquire()
        finally:
            first.release()
        # after release, a new instance can start
        third = daemon_mod.SingleInstance()
        third.acquire()
        third.release()

    def test_status_when_not_running(self):
        inst = daemon_mod.SingleInstance()
        self.assertFalse(inst.status()["running"])


class TestQuarantineCleanup(EngineTestCase):
    def test_expired_ref_cleaned_fresh_kept(self):
        past = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 86400))
        future = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 86400))
        with state_mod.State() as st:
            st.record_quarantine_ref("refs/awa/repo/awa1-old", "/r/.git", retire_after=past)
            st.record_quarantine_ref("refs/awa/repo/awa1-new", "/r/.git", retire_after=future)
            cleaned = daemon_mod.cleanup_quarantine_refs(st)
            self.assertEqual(cleaned, ["refs/awa/repo/awa1-old"])
            remaining = {r["ref"] for r in st.quarantine_refs()}
            self.assertEqual(remaining, {"refs/awa/repo/awa1-new"})

    def test_expiry_is_utc_not_local(self):
        """Regression: expiry parsing must treat `retire_after` as UTC. A `time.mktime`-based
        parse silently reinterprets the UTC string as LOCAL time, skewing expiry by the host's
        UTC offset (bug reproduced live in PDT: ~7h drift). A tight 1-hour margin — far smaller
        than any real UTC offset — turns that skew into a wrong verdict on any non-UTC host,
        unlike the ±24h margins above which happen to absorb it."""
        just_expired = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3600))
        not_yet = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 3600))
        with state_mod.State() as st:
            st.record_quarantine_ref("refs/awa/repo/awa1-just-old", "/r/.git", retire_after=just_expired)
            st.record_quarantine_ref("refs/awa/repo/awa1-not-yet", "/r/.git", retire_after=not_yet)
            cleaned = daemon_mod.cleanup_quarantine_refs(st)
            self.assertEqual(cleaned, ["refs/awa/repo/awa1-just-old"])

    def test_never_touches_non_quarantine_ref(self):
        past = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 86400))
        with state_mod.State() as st:
            # a malformed row pointing at a heads ref must never be cleaned
            st.conn.execute(
                "INSERT INTO quarantine_refs(ref,lease_id,git_common_dir,created_at,retire_after) "
                "VALUES(?,?,?,?,?)",
                ("refs/heads/main", None, "/r/.git", "t0", past),
            )
            cleaned = daemon_mod.cleanup_quarantine_refs(st)
            self.assertEqual(cleaned, [])

    def test_run_once_summary(self):
        with state_mod.State() as st:
            summary = daemon_mod.run_once(st)
            self.assertIn("quarantine_cleaned", summary)
            self.assertIn("active_leases", summary)


if __name__ == "__main__":
    unittest.main()
