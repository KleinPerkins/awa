"""M1-B.2: redacted projection, native dispatch, and receipt CAS."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import stat
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from engine import integrity, integrity_alert, paths
from engine.tests.helpers import EngineTestCase


class TestIntegrityAlert(EngineTestCase):
    def _status(
        self,
        overall: str,
        *,
        generated_at: str = "2026-08-25T00:00:00Z",
        transition_id: str | None = None,
        evidence: str = "bounded reason",
    ) -> dict:
        return {
            "schema": integrity.SCHEMA,
            "generated_at": generated_at,
            "overall": overall,
            "profile": "deep",
            "trigger": "launchd",
            "transition_id": transition_id,
            "release": {"version": "9.9.9", "commit": "/private/release/secret"},
            "invariants": [
                {
                    "id": "guard_safety",
                    "severity": "green",
                    "evidence": evidence,
                    "raw_evidence": {"token": "DO NOT DISCLOSE"},
                    "checked_at": generated_at,
                    "profile": "deep",
                },
                {
                    "id": "alert_delivery",
                    "severity": "green",
                    "evidence": "delivery available",
                    "checked_at": generated_at,
                    "profile": "deep",
                },
            ],
            "triggers": {
                "launchd": {
                    "last_attempt": generated_at,
                    "last_success": generated_at,
                    "last_error": None,
                    "generation": 1,
                }
            },
            "orphans": {
                "worktrees": 2,
                "leases_unreconciled": 1,
                "sessions_dangling": 0,
                "husks": 0,
                "private_path": "/Users/operator/repo",
            },
            "recovery": {
                "last_status": "ok",
                "needs_repair": 0,
                "quarantine_count": 1,
                "archive": "/private/recovery/archive.tar.gz",
            },
            "alert": {
                "last_transition": None,
                "attempted": [],
                "delivered": {
                    "native": "accepted",
                    "slack": "opted_out",
                },
                "token": "DO NOT DISCLOSE",
            },
            "fresh_until": "2026-08-26T00:00:00Z",
            "raw_evidence": "/Users/operator/private DO NOT DISCLOSE",
        }

    def _commit(self, overall: str) -> dict:
        value = self._status(overall)
        # Low-level fixture commits deliberately omit the evaluator schema marker so
        # dispatch is controlled explicitly by each receipt test.
        value.pop("schema", None)
        integrity._commit(value, profile="deep", trigger="launchd")
        committed = integrity.read_status()
        self.assertIsNotNone(committed)
        return committed

    def _receipt_files(self) -> list[Path]:
        directory = paths.integrity_dir() / "receipt"
        return sorted(directory.glob("*")) if directory.is_dir() else []

    def test_projection_has_no_paths_or_secrets(self):
        projection = integrity.public_projection(
            self._status(
                "degraded",
                evidence=(
                    "failed at /Users/operator/private/config "
                    "with credential DO NOT DISCLOSE"
                ),
            )
        )
        encoded = json.dumps(projection, sort_keys=True)
        self.assertEqual(projection["schema"], "awa-integrity-public/v1")
        self.assertNotIn("/Users/", encoded)
        self.assertNotIn("/private/", encoded)
        self.assertNotIn("DO NOT DISCLOSE", encoded)
        self.assertNotIn("raw_evidence", encoded)
        self.assertNotIn("release", projection)
        self.assertEqual(
            set(projection["invariants"][0]),
            {"id", "severity", "redacted_reason"},
        )
        self.assertEqual(
            set(projection["orphans"]),
            {
                "worktrees",
                "leases_unreconciled",
                "sessions_dangling",
                "husks",
            },
        )
        self.assertEqual(
            set(projection["recovery"]),
            {"last_status", "needs_repair", "quarantine_count"},
        )

    def test_projection_has_fresh_until(self):
        projection = integrity.public_projection(self._status("green"))
        self.assertEqual(
            projection["fresh_until"],
            "2026-08-26T00:00:00Z",
        )
        self.assertEqual(projection["last_checked_age_s"], 0)
        self.assertEqual(
            projection["recent_history"],
            [
                {
                    "generation": 0,
                    "overall": "green",
                    "generated_at": "2026-08-25T00:00:00Z",
                }
            ],
        )

    def test_worsening_attempts_native_records_accepted(self):
        previous = self._status("green", transition_id="older")
        current = self._status("degraded", transition_id="green->degraded#2")
        calls = []
        outcomes = integrity_alert.dispatch(
            previous,
            current,
            native=lambda title, body: calls.append((title, body)) or True,
            slack=None,
        )
        self.assertEqual(
            outcomes,
            {"native": "accepted", "slack": "opted_out"},
        )
        self.assertEqual(len(calls), 1)
        self.assertNotIn("/Users/", json.dumps(calls))
        self.assertNotIn("DO NOT DISCLOSE", json.dumps(calls))

    def test_no_worsening_silent(self):
        previous = self._status("green", transition_id="same")
        current = self._status("green", transition_id="same")
        native = mock.Mock(return_value=True)
        self.assertIsNone(
            integrity_alert.dispatch(
                previous,
                current,
                native=native,
                slack=None,
            )
        )
        native.assert_not_called()

    def test_transition_dedupe(self):
        previous = self._status("green", transition_id="older")
        current = self._status("degraded", transition_id="tid-2")
        native = mock.Mock(return_value=True)
        first = integrity_alert.dispatch(
            previous,
            current,
            native=native,
            slack=None,
        )
        second = integrity_alert.dispatch(
            previous,
            current,
            native=native,
            slack=None,
        )
        self.assertIsNotNone(first)
        self.assertIsNone(second)
        native.assert_called_once()

    def test_native_fail_only_while_nongreen_is_red(self):
        previous = self._status("green", transition_id="older")
        current = self._status("degraded", transition_id="tid-2")
        outcomes = integrity_alert.dispatch(
            previous,
            current,
            native=lambda *_: False,
            slack=None,
        )
        self.assertEqual(
            outcomes,
            {"native": "failed", "slack": "opted_out"},
        )
        self.assertEqual(current["overall"], "red")
        delivery = next(
            item
            for item in current["invariants"]
            if item["id"] == "alert_delivery"
        )
        self.assertEqual(delivery["severity"], "red")

    def test_never_returning_native_is_bounded_failed(self):
        previous = self._status("green", transition_id="older")
        current = self._status("degraded", transition_id="tid-timeout")

        def hangs(_title, _body):
            time.sleep(2)
            return True

        started = time.monotonic()
        with mock.patch.object(
            integrity_alert,
            "NATIVE_TIMEOUT_SECONDS",
            0.05,
        ):
            outcomes = integrity_alert.dispatch(
                previous,
                current,
                native=hangs,
                slack=None,
            )
        self.assertLess(time.monotonic() - started, 0.5)
        self.assertEqual(outcomes["native"], "failed")
        self.assertEqual(current["overall"], "red")

    def test_receipt_cas_advances_bookkeeping_generation_same_transition(self):
        self._commit("green")
        evaluation = self._commit("degraded")
        self.assertEqual(evaluation["generation"], 2)
        transition_id = evaluation["transition_id"]
        outcomes = integrity_alert.dispatch(
            self._status("green", transition_id="older"),
            evaluation,
            native=lambda *_: True,
            slack=None,
        )
        self.assertEqual(
            outcomes,
            {"native": "accepted", "slack": "opted_out"},
        )
        generation = integrity.commit_alert_receipt(
            2,
            transition_id,
            outcomes,
        )
        self.assertEqual(generation, 3)
        current = integrity.read_status()
        self.assertEqual(current["generation"], 3)
        self.assertEqual(current["transition_id"], transition_id)
        self.assertEqual(current["alert"]["delivered"], outcomes)
        self.assertEqual(current["artifacts"]["receipt"]["gen"], 3)
        self.assertEqual(current["artifacts"]["public"]["gen"], 3)
        self.assertEqual(current["artifacts"]["console"]["gen"], 3)
        self.assertEqual(current["artifacts"]["outbox"]["gen"], 2)
        outbox = json.loads(
            (
                paths.integrity_dir()
                / current["artifacts"]["outbox"]["path"]
            ).read_text(encoding="utf-8")
        )
        self.assertTrue(outbox["pending"])
        self.assertEqual(outbox["transition_id"], transition_id)
        receipt = (
            paths.integrity_dir()
            / current["artifacts"]["receipt"]["path"]
        )
        self.assertTrue(receipt.is_file())
        self.assertEqual(stat.S_IMODE(receipt.stat().st_mode), 0o600)

    def test_receipt_no_reevaluation_no_new_outbox_no_recursion(self):
        self._commit("green")
        evaluation = self._commit("degraded")
        transition_id = evaluation["transition_id"]
        outbox_before = sorted((paths.integrity_dir() / "outbox").iterdir())
        with mock.patch.object(
            integrity,
            "evaluate",
            side_effect=AssertionError("receipt re-evaluated"),
        ), mock.patch.object(
            integrity_alert,
            "dispatch",
            side_effect=AssertionError("receipt recursed"),
        ):
            generation = integrity.commit_alert_receipt(
                2,
                transition_id,
                {"native": "accepted", "slack": "opted_out"},
            )
        self.assertEqual(generation, 3)
        self.assertEqual(
            sorted((paths.integrity_dir() / "outbox").iterdir()),
            outbox_before,
        )

    def test_receipt_child_dirs_fsynced_after_each_rename(self):
        self._commit("green")
        evaluation = self._commit("degraded")
        fsynced = []
        original = integrity._fsync_dir

        def record(path):
            fsynced.append(path.resolve())
            return original(path)

        with mock.patch.object(
            integrity,
            "_fsync_dir",
            side_effect=record,
        ):
            self.assertEqual(
                integrity.commit_alert_receipt(
                    2,
                    evaluation["transition_id"],
                    {"native": "accepted", "slack": "opted_out"},
                ),
                3,
            )
        root = paths.integrity_dir().resolve()
        for child in ("receipt", "public", "console"):
            self.assertIn((root / child).resolve(), fsynced)
        self.assertIn(root, fsynced)

    def test_receipt_cas_mismatch_is_audited_not_overwriting(self):
        self._commit("green")
        stale_evaluation = self._commit("degraded")
        transition_id = stale_evaluation["transition_id"]
        newer = self._commit("red")
        before = paths.integrity_status_path().read_bytes()
        self.assertIsNone(
            integrity.commit_alert_receipt(
                2,
                transition_id,
                {"native": "accepted", "slack": "opted_out"},
            )
        )
        self.assertEqual(paths.integrity_status_path().read_bytes(), before)
        self.assertEqual(integrity.read_status(), newer)
        stale_audits = list(
            (paths.integrity_dir() / "receipt").glob("stale-*.json")
        )
        self.assertEqual(len(stale_audits), 1)
        self.assertEqual(stat.S_IMODE(stale_audits[0].stat().st_mode), 0o600)
        audit = json.loads(stale_audits[0].read_text(encoding="utf-8"))
        self.assertEqual(audit["result"], "stale")
        self.assertNotIn(transition_id, json.dumps(audit))

    def test_receipt_crash_before_status_replace_keeps_prev(self):
        self._commit("green")
        evaluation = self._commit("degraded")
        transition_id = evaluation["transition_id"]
        before = paths.integrity_status_path().read_bytes()
        original_replace = os.replace

        def crash(src, dst):
            if Path(dst) == paths.integrity_status_path():
                raise OSError("receipt status crash cut")
            return original_replace(src, dst)

        with mock.patch.object(integrity.os, "replace", side_effect=crash):
            with self.assertRaises(OSError):
                integrity.commit_alert_receipt(
                    2,
                    transition_id,
                    {"native": "accepted", "slack": "opted_out"},
                )
        self.assertEqual(paths.integrity_status_path().read_bytes(), before)
        self.assertEqual(integrity.read_status()["generation"], 2)
        self.assertTrue(
            (paths.integrity_dir() / "receipt" / "3.json").exists()
        )
        self.assertEqual(
            integrity.commit_alert_receipt(
                2,
                transition_id,
                {"native": "accepted", "slack": "opted_out"},
            ),
            3,
        )

    def test_receipt_retry_is_idempotent(self):
        self._commit("green")
        evaluation = self._commit("degraded")
        transition_id = evaluation["transition_id"]
        outcomes = {"native": "accepted", "slack": "opted_out"}
        self.assertEqual(
            integrity.commit_alert_receipt(2, transition_id, outcomes),
            3,
        )
        before = paths.integrity_status_path().read_bytes()
        files_before = self._receipt_files()
        self.assertIsNone(
            integrity.commit_alert_receipt(2, transition_id, outcomes)
        )
        self.assertEqual(paths.integrity_status_path().read_bytes(), before)
        self.assertEqual(self._receipt_files(), files_before)

    def test_receipt_cas_race_advances_once(self):
        self._commit("green")
        evaluation = self._commit("degraded")
        transition_id = evaluation["transition_id"]
        code = (
            "from engine import integrity;"
            f"integrity.commit_alert_receipt(2,{transition_id!r},"
            "{'native':'accepted','slack':'opted_out'})"
        )
        env = os.environ.copy()
        env["XDG_STATE_HOME"] = str(self.state_home)
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
        workers = [
            subprocess.Popen(
                [sys.executable, "-c", code],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for _ in range(2)
        ]
        results = [worker.communicate(timeout=15) for worker in workers]
        self.assertTrue(
            all(worker.returncode == 0 for worker in workers),
            results,
        )
        self.assertEqual(integrity.read_status()["generation"], 3)
        self.assertEqual(
            list((paths.integrity_dir() / "receipt").glob("[0-9]*.json")),
            [paths.integrity_dir() / "receipt" / "3.json"],
        )

    def test_evaluation_dispatch_runs_outside_lock_and_persists_receipt(self):
        first = self._status("green")
        integrity._commit(first, profile="deep", trigger="launchd")
        original_lock = integrity._integrity_lock
        lock_held = False

        @contextlib.contextmanager
        def tracked_lock():
            nonlocal lock_held
            with original_lock():
                lock_held = True
                try:
                    yield
                finally:
                    lock_held = False

        def native(_title, _body):
            self.assertFalse(lock_held)
            return True

        second = self._status("degraded")
        with mock.patch.object(
            integrity,
            "_integrity_lock",
            tracked_lock,
        ), mock.patch.object(integrity_alert, "_native", side_effect=native):
            evaluation_generation = integrity._commit(
                second,
                profile="deep",
                trigger="launchd",
            )
        self.assertEqual(evaluation_generation, 2)
        current = integrity.read_status()
        self.assertEqual(current["generation"], 3)
        self.assertEqual(
            current["alert"]["delivered"],
            {"native": "accepted", "slack": "opted_out"},
        )

    def _assert_dispatch_process_control_propagates(
        self,
        exception_type: type[BaseException],
    ) -> None:
        integrity._commit(
            self._status("green"),
            profile="deep",
            trigger="launchd",
        )
        with mock.patch.object(
            integrity_alert,
            "dispatch",
            side_effect=exception_type,
        ), self.assertRaises(exception_type):
            integrity._commit(
                self._status("degraded"),
                profile="deep",
                trigger="launchd",
            )
        current = integrity.read_status()
        self.assertEqual(current["generation"], 2)
        self.assertNotIn("receipt", current["artifacts"])

    def test_evaluation_dispatch_does_not_swallow_keyboard_interrupt(self):
        self._assert_dispatch_process_control_propagates(KeyboardInterrupt)

    def test_evaluation_dispatch_does_not_swallow_system_exit(self):
        self._assert_dispatch_process_control_propagates(SystemExit)


if __name__ == "__main__":
    unittest.main()
