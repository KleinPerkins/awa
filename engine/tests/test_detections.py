"""Phase 6: engine-backed ingestion of the shell-gate's detection receipts."""

from __future__ import annotations

import json
import unittest

from engine import daemon as daemon_mod, paths, state as state_mod
from engine.tests.helpers import EngineTestCase


class TestDetectionIngest(EngineTestCase):
    def _write_receipt(self, path: str, repo: str) -> None:
        d = paths.detections_dir()
        paths.ensure_dir(d)
        with open(d / "receipts.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"kind": "primary-file-edit-detected",
                                 "time": "t", "path": path, "repo": repo}) + "\n")

    def test_ingest_folds_receipts_into_state(self):
        self._write_receipt("/repo/a.txt", "/repo")
        self._write_receipt("/repo/b.txt", "/repo")
        with state_mod.State() as st:
            n = daemon_mod.ingest_detection_receipts(st)
            self.assertEqual(n, 2)
            self.assertEqual(len(st.detections()), 2)

    def test_ingest_is_incremental_no_double_count(self):
        self._write_receipt("/repo/a.txt", "/repo")
        with state_mod.State() as st:
            self.assertEqual(daemon_mod.ingest_detection_receipts(st), 1)
            self.assertEqual(daemon_mod.ingest_detection_receipts(st), 0)  # nothing new
        self._write_receipt("/repo/c.txt", "/repo")
        with state_mod.State() as st:
            self.assertEqual(daemon_mod.ingest_detection_receipts(st), 1)
            self.assertEqual(len(st.detections()), 2)

    def test_run_once_reports_ingested(self):
        self._write_receipt("/repo/a.txt", "/repo")
        with state_mod.State() as st:
            summary = daemon_mod.run_once(st)
            self.assertEqual(summary["detections_ingested"], 1)


if __name__ == "__main__":
    unittest.main()
