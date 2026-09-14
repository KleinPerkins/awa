"""M1-A.3: integrity verify/view CLI and exact severity exit codes."""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from engine import cli, integrity, integrity_repair, paths
from engine.tests.helpers import EngineTestCase


_CLI = str(Path(__file__).resolve().parents[2] / "bin" / "awa-engine.sh")

_SAFE_FACTS = {
    "guard_primary_deny": True,
    "guard_cd_bypass_deny": True,
    "guard_linked_allow": True,
    "parity_ok": True,
    "hook_rows_present": True,
    "hook_fail_open": True,
    "mcp_matches": True,
    "release_matches": True,
    "recovery_last_status": "ok",
    "needs_repair": 0,
    "leases_unreconciled": 0,
    "sessions_dangling": 0,
    "husks": 0,
    "disposition_map": {},
    "handoff_state": "closed",
    "launchd_last_success_age_s": 0.0,
    "delivered": {"native": "accepted", "slack": "opted_out"},
}


class TestIntegrityCli(EngineTestCase):
    def _facts(self, **overrides) -> dict:
        value = json.loads(json.dumps(_SAFE_FACTS))
        value.update(overrides)
        return value

    def _run(
        self,
        *args: str,
        facts: dict | None = None,
        state_home: Path | None = None,
    ) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env["AWA_ENGINE_TEST_ACTIVE"] = "1"
        if facts is not None:
            env["AWA_INTEGRITY_TEST_FACTS_JSON"] = json.dumps(facts)
        else:
            env.pop("AWA_INTEGRITY_TEST_FACTS_JSON", None)
        if state_home is not None:
            env["XDG_STATE_HOME"] = str(state_home)
        return subprocess.run(
            ["bash", _CLI, *args],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )

    def test_verify_exit_codes_exact(self):
        fixtures = (
            (self._facts(), 0, "green", 1),
            (self._facts(release_matches=False), 1, "degraded", 3),
            (self._facts(mcp_matches=False), 2, "red", 5),
        )
        for (
            observed,
            expected_code,
            expected_overall,
            expected_generation,
        ) in fixtures:
            with self.subTest(overall=expected_overall):
                proc = self._run(
                    "integrity",
                    "verify",
                    "--profile",
                    "deep",
                    "--trigger",
                    "launchd",
                    facts=observed,
                )
                self.assertEqual(proc.returncode, expected_code, proc.stderr)
                self.assertIn(integrity.SCHEMA, proc.stdout)
                payload = json.loads(proc.stdout)
                self.assertEqual(payload["overall"], expected_overall)
                self.assertEqual(
                    payload["generation"],
                    expected_generation,
                )
                if expected_overall != "green":
                    self.assertEqual(
                        payload["artifacts"]["receipt"]["gen"],
                        expected_generation,
                    )

    def test_view_exit_codes_exact(self):
        for observed, expected_code in (
            (self._facts(), 0),
            (self._facts(release_matches=False), 1),
            (self._facts(mcp_matches=False), 2),
        ):
            with self.subTest(expected_code=expected_code):
                verified = self._run(
                    "integrity",
                    "verify",
                    "--trigger",
                    "launchd",
                    facts=observed,
                )
                self.assertEqual(verified.returncode, expected_code, verified.stderr)
                viewed = self._run("integrity", "view")
                self.assertEqual(viewed.returncode, expected_code, viewed.stderr)
                self.assertEqual(
                    json.loads(viewed.stdout)["generation"],
                    json.loads(verified.stdout)["generation"],
                )

    def test_view_missing_or_malformed_or_stale_is_2(self):
        missing_home = self.state_home / "missing"
        missing = self._run("integrity", "view", state_home=missing_home)
        self.assertEqual(missing.returncode, 2)
        self.assertIn(integrity.SCHEMA, missing.stdout)

        malformed_home = self.state_home / "malformed"
        malformed_status = malformed_home / "awa" / "integrity" / "status.json"
        malformed_status.parent.mkdir(parents=True)
        malformed_status.write_text('{"schema":', encoding="utf-8")
        malformed = self._run(
            "integrity",
            "view",
            state_home=malformed_home,
        )
        self.assertEqual(malformed.returncode, 2)

        stale_status = {
            "overall": "green",
            "invariants": [],
            "triggers": {
                "launchd": {
                    "last_attempt": "2000-01-01T00:00:00Z",
                    "last_success": "2000-01-01T00:00:00Z",
                    "last_error": None,
                    "generation": 0,
                }
            },
            "orphans": {},
            "recovery": {},
            "alert": {},
        }
        integrity._commit(stale_status, profile="deep", trigger="cli")
        stale = self._run("integrity", "view")
        self.assertEqual(stale.returncode, 2)
        self.assertEqual(json.loads(stale.stdout)["overall"], "green")

    def test_default_profile_deep_but_trigger_required(self):
        verified = self._run(
            "integrity",
            "verify",
            "--trigger",
            "launchd",
            facts=self._facts(),
        )
        self.assertEqual(verified.returncode, 0, verified.stderr)
        self.assertEqual(json.loads(verified.stdout)["profile"], "deep")

        missing = self._run(
            "integrity",
            "verify",
            facts=self._facts(),
        )
        self.assertEqual(missing.returncode, 2)
        self.assertIn("--trigger", missing.stderr)

        invalid = self._run(
            "integrity",
            "verify",
            "--trigger",
            "unknown",
            facts=self._facts(),
        )
        self.assertEqual(invalid.returncode, 2)
        self.assertIn("invalid choice", invalid.stderr)

    def test_launchd_trigger_requires_deep_profile(self):
        invalid = self._run(
            "integrity",
            "verify",
            "--profile",
            "fast",
            "--trigger",
            "launchd",
            facts=self._facts(),
        )
        self.assertEqual(invalid.returncode, 2)
        self.assertEqual(
            json.loads(invalid.stdout)["error"],
            "launchd trigger requires deep profile",
        )
        self.assertIsNone(integrity.read_status())

    def test_repair_registered_but_export_and_sweep_remain_unregistered(self):
        repair = self._run("integrity", "repair", "plan")
        self.assertNotIn("invalid choice", repair.stderr)
        self.assertIn("awa-integrity-repair-plan/v1", repair.stdout)

        for verb in ("export", "sweep"):
            with self.subTest(verb=verb):
                proc = self._run("integrity", verb)
                self.assertEqual(proc.returncode, 2)
                self.assertEqual(proc.stdout, "")
                self.assertIn("invalid choice", proc.stderr)
                self.assertNotIn(integrity.SCHEMA, proc.stderr)

        console = self._run("integrity", "console")
        self.assertEqual(console.returncode, 2)
        self.assertIn("awa-integrity-console/v1", console.stdout)
        self.assertNotIn("invalid choice", console.stderr)

    def test_repair_apply_emits_fresh_plan_for_both_action_kinds(self):
        fresh_plan = {
            "schema": integrity_repair.PLAN_SCHEMA,
            "plan_digest": "b" * 64,
            "actions": [],
        }
        for kind in sorted(integrity_repair.ACTION_KINDS):
            with self.subTest(kind=kind):
                args = cli.build_parser().parse_args(
                    [
                        "integrity",
                        "repair",
                        "apply",
                        "--plan-digest",
                        "a" * 64,
                        "--action",
                        kind,
                        "--authorization",
                        "authorization",
                    ]
                )
                stdout = io.StringIO()
                with mock.patch.object(
                    cli.integrity_repair_mod,
                    "apply",
                    return_value={
                        "schema": "awa-integrity-repair-result/v1",
                        "kind": kind,
                        "result": "retired" if kind == "retire-bookkeeping" else "removed",
                        "fresh_plan": fresh_plan,
                    },
                ), contextlib.redirect_stdout(stdout):
                    code = args.fn(args)

                self.assertEqual(code, 0)
                payload = json.loads(stdout.getvalue())
                self.assertIs(payload["ok"], True)
                self.assertEqual(payload["fresh_plan"], fresh_plan)

    def test_repair_apply_reports_already_applied_when_fresh_plan_fails(self):
        args = cli.build_parser().parse_args(
            [
                "integrity",
                "repair",
                "apply",
                "--plan-digest",
                "a" * 64,
                "--action",
                "retire-bookkeeping",
                "--authorization",
                "authorization",
            ]
        )
        applied = {
            "schema": "awa-integrity-repair-result/v1",
            "kind": "retire-bookkeeping",
            "result": "retired",
        }
        stdout = io.StringIO()
        with mock.patch.object(
            cli.integrity_repair_mod,
            "apply",
            side_effect=integrity_repair.RepairAppliedPlanUnavailable(applied),
        ), contextlib.redirect_stdout(stdout):
            code = args.fn(args)

        self.assertEqual(code, 3)
        payload = json.loads(stdout.getvalue())
        self.assertIs(payload["ok"], False)
        self.assertIs(payload["applied"], True)
        self.assertEqual(payload["applied_result"], applied)

    def test_repair_apply_reports_post_removal_audit_failure_without_traceback(self):
        args = cli.build_parser().parse_args(
            [
                "integrity",
                "repair",
                "apply",
                "--plan-digest",
                "a" * 64,
                "--action",
                "remove-worktree",
                "--authorization",
                "authorization",
            ]
        )
        applied = {
            "schema": "awa-integrity-repair-result/v1",
            "kind": "remove-worktree",
            "result": "removed",
            "recovery_artifact_id": "artifact-1",
            "clean_receipt_id": "receipt-1",
        }
        stdout = io.StringIO()
        with mock.patch.object(
            cli.integrity_repair_mod,
            "apply",
            side_effect=integrity_repair.RepairAppliedPlanUnavailable(
                applied,
                incomplete_stage="audit-completion",
            ),
        ), contextlib.redirect_stdout(stdout):
            code = args.fn(args)

        self.assertEqual(code, 3)
        payload = json.loads(stdout.getvalue())
        self.assertIs(payload["applied"], True)
        self.assertEqual(payload["incomplete_stage"], "audit-completion")
        self.assertEqual(payload["applied_result"], applied)
        self.assertNotIn("Traceback", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
