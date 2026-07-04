"""Phase 1/2: identity + paths (lease identity floor, S4 perms, local-disk guard)."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from engine import identity, paths
from engine.tests.helpers import EngineTestCase


class TestIdentity(unittest.TestCase):
    def test_lease_id_deterministic_and_not_pid(self):
        a = identity.lease_id("/w/tree", "feat/x", "/repo/.git", boot="boot-123")
        b = identity.lease_id("/w/tree", "feat/x", "/repo/.git", boot="boot-123")
        self.assertEqual(a, b)
        self.assertTrue(a.startswith("awa1-"))
        self.assertFalse(a.isdigit(), "lease id must never be a bare pid")

    def test_lease_id_changes_with_any_component(self):
        base = identity.lease_id("/w/tree", "feat/x", "/repo/.git", boot="b1")
        self.assertNotEqual(base, identity.lease_id("/w/tree2", "feat/x", "/repo/.git", boot="b1"))
        self.assertNotEqual(base, identity.lease_id("/w/tree", "feat/y", "/repo/.git", boot="b1"))
        self.assertNotEqual(base, identity.lease_id("/w/tree", "feat/x", "/repo2/.git", boot="b1"))
        self.assertNotEqual(base, identity.lease_id("/w/tree", "feat/x", "/repo/.git", boot="b2"))

    def test_boot_id_nonempty_and_stable(self):
        self.assertTrue(identity.boot_id())
        self.assertEqual(identity.boot_id(), identity.boot_id())

    def test_common_dir_key_stable_and_short(self):
        k = identity.common_dir_key("/repo/.git")
        self.assertEqual(k, identity.common_dir_key("/repo/.git"))
        self.assertEqual(len(k), 24)


class TestPaths(EngineTestCase):
    def test_ensure_dir_and_write_private_modes(self):
        d = paths.awa_state_dir()
        paths.ensure_dir(d)
        self.assertEqual(oct(os.stat(d).st_mode & 0o777), "0o700")
        f = d / "x.txt"
        paths.write_private(f, "hello")
        self.assertEqual(oct(os.stat(f).st_mode & 0o777), "0o600")
        self.assertEqual(f.read_text(), "hello")

    def test_local_disk_ok_for_tmp(self):
        ok, _ = paths.is_local_disk(self.state_home)
        self.assertTrue(ok)

    def test_synced_marker_refused(self):
        fake = Path("/tmp/Library/Mobile Documents/com~apple~CloudDocs/awa")
        ok, reason = paths.is_local_disk(fake)
        self.assertFalse(ok)
        self.assertIn("cloud-synced", reason)


if __name__ == "__main__":
    unittest.main()
