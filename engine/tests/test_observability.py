"""K2 engine observability (NON-load-bearing): fold clean receipts into the timeline (D1) and
detect a vanished-but-unattributed Safe Workspace (D3).

These prove the engine OBSERVES kernel state (clean_receipt/v1 receipts + active_root/v1 root
records written by the engine-OFF kernel) without changing any gate/refusal decision — the engine
only reads the kernel's on-disk records and reflects them into its queryable timeline.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from engine import daemon as daemon_mod, paths, state as state_mod
from engine.tests.helpers import EngineTestCase


def _write_receipt(receipt_id: str, *, disposition: str, reason: str = "removed_kept_branch",
                   path: str = "", branch: str = "", time_iso: str = "2026-07-08T00:00:00Z",
                   archive: str = "", root_disposition: str = "") -> None:
    d = paths.receipts_dir()
    paths.ensure_dir(d)
    rec = {
        "schema": "clean_receipt/v1",
        "receipt_id": receipt_id,
        "time": time_iso,
        "verb": "clean",
        "disposition": disposition,
        "reason_code": reason,
        "message": "test receipt",
        "path": path,
        "branch": branch,
        "archive": archive,
        "root_disposition": root_disposition,
    }
    (d / f"clean-{receipt_id}.json").write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")


def _write_root(key: str, *, root_path: str, branch: str = "feat/x",
                common_dir: str = "/repo/.git") -> None:
    d = paths.roots_dir()
    paths.ensure_dir(d)
    rec = {
        "schema": "active_root/v1",
        "root_path": root_path,
        "git_common_dir": common_dir,
        "branch": branch,
        "last_heartbeat": "2026-07-08T00:00:00Z",
        "last_heartbeat_epoch": 1783468800,
    }
    (d / f"{key}.json").write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")


class TestCleanReceiptTimeline(EngineTestCase):
    """D1: kernel clean_receipt/v1 records fold into the engine's observable timeline."""

    def test_ingest_folds_and_is_idempotent(self):
        _write_receipt("r1", disposition="removed", path="/wt/a")
        _write_receipt("r2", disposition="refused", reason="active_root", path="/wt/b")
        with state_mod.State() as st:
            self.assertEqual(daemon_mod.ingest_clean_receipts(st), 2)
            self.assertEqual(daemon_mod.ingest_clean_receipts(st), 0)  # nothing new
            rows = st.clean_receipts()
            self.assertEqual(len(rows), 2)
            self.assertEqual({r["disposition"] for r in rows}, {"removed", "refused"})

    def test_non_receipt_json_is_ignored(self):
        d = paths.receipts_dir()
        paths.ensure_dir(d)
        (d / "clean-bogus.json").write_text('{"schema":"other/v1"}\n', encoding="utf-8")
        with state_mod.State() as st:
            self.assertEqual(daemon_mod.ingest_clean_receipts(st), 0)

    def test_timeline_merges_detections_and_clean_receipts_newest_first(self):
        _write_receipt("r1", disposition="removed", path="/wt/a",
                       time_iso="2026-07-08T10:00:00Z")
        with state_mod.State() as st:
            st.record_detection(repo="/repo", path="/repo/x.txt",
                                kind="primary-file-edit-detected")
            daemon_mod.ingest_clean_receipts(st)
            tl = daemon_mod.timeline(st)
            types = {e["type"] for e in tl}
            self.assertEqual(types, {"detection", "clean_receipt"})
            # sorted newest-first by ts (the detection's ts is "now" > the receipt's fixed ts).
            self.assertEqual(tl[0]["type"], "detection")

    def test_run_once_reports_clean_ingest(self):
        _write_receipt("r1", disposition="removed", path="/wt/a")
        with state_mod.State() as st:
            summary = daemon_mod.run_once(st)
            self.assertEqual(summary["clean_receipts_ingested"], 1)
            self.assertIn("missing_unattributed", summary)


class TestMissingUnattributed(EngineTestCase):
    """D3: a vanished Safe Workspace with no attributing clean receipt is detected."""

    def test_vanished_root_without_receipt_is_flagged(self):
        gone = str(self.data_home / "gone-wt")  # never created -> path does not exist
        _write_root("k1", root_path=gone)
        with state_mod.State() as st:
            found = daemon_mod.detect_missing_unattributed(st)
            self.assertEqual([f["path"] for f in found], [gone])
            # a deduplicated detection was recorded...
            self.assertTrue(st.detection_exists("worktree_missing_unattributed", gone))
            self.assertEqual(len(st.detections()), 1)
            # ...and a second pass does not double-record it.
            daemon_mod.detect_missing_unattributed(st)
            self.assertEqual(len(st.detections()), 1)

    def test_attributed_removal_is_not_flagged(self):
        gone = str(self.data_home / "removed-wt")
        _write_root("k2", root_path=gone)
        _write_receipt("rr", disposition="removed", path=gone)  # attributes the removal
        with state_mod.State() as st:
            found = daemon_mod.detect_missing_unattributed(st)
            self.assertEqual(found, [])
            self.assertFalse(st.detection_exists("worktree_missing_unattributed", gone))

    def test_present_root_is_not_flagged(self):
        present = str(self.data_home)  # exists
        _write_root("k3", root_path=present)
        with state_mod.State() as st:
            self.assertEqual(daemon_mod.detect_missing_unattributed(st), [])


if __name__ == "__main__":
    unittest.main()
