"""M6 advisory performance-policy and verification-lane wiring tests."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engine.tests import (
    guard_boundary_profile,
    performance_policy,
    suite_runner,
    verification_contract,
)


ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = Path(__file__).with_name("performance-baseline.v1.json")
NOEXEC_EVIDENCE = (
    "live-verify/RESULTS-noexec-repair-process-profile-20260903.md"
)
NOEXEC_HISTORICAL_SUBJECT_FILES = 264
NOEXEC_HISTORICAL_SUBJECT_SHA256 = (
    "c7f1aa8a6877ffd26897e15f1db43f70411f8bbfbc7064157e51d9752c805d47"
)


def baseline() -> dict:
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def accepted_lane_baseline(lane: str) -> dict:
    value = copy.deepcopy(baseline())
    value["status"] = "accepted"
    value["observation_count"] = 5
    value["session_count"] = 2
    value["machine_contexts"] = [
        {
            "platform": "fixture",
            "architecture": "fixture",
            "logical_cpu_count": 1,
            "load_note": "ordinary fixture load",
        },
        {
            "platform": "fixture",
            "architecture": "fixture",
            "logical_cpu_count": 1,
            "load_note": "second ordinary fixture load",
        },
    ]
    value["lanes"][lane].update({
        "status": "accepted",
        "observation_count": 5,
        "session_count": 2,
        "p90_ms": 100,
        "warning_elapsed_ms": 200,
    })
    return value


def observation(**updates) -> dict:
    value = {
        "head": "a" * 40,
        "inventory_sha256": "b" * 64,
        "python": "3.14.6",
        "git": "git version fixture",
        "lane": "pre-pr",
        "jobs": 2,
        "test_count": 1,
        "outcome": "passed",
        "elapsed_ms": 1,
        "load_note": "ordinary fixture load",
        "module_durations_ms": {},
        "process_measurement": None,
    }
    value.update(updates)
    return value


def messages(warnings) -> list[str]:
    return [item["message"] for item in warnings]


class PerformancePolicyTest(unittest.TestCase):
    def test_committed_baseline_is_closed_and_valid(self) -> None:
        value = baseline()
        verification_contract.validate_performance_baseline(value)
        for relative in value["evidence"]:
            with self.subTest(evidence=relative):
                self.assertTrue((ROOT / relative).is_file())
        self.assertEqual(
            value["process_measurement"]["producer_sha256"],
            performance_policy.performance_producer_sha256(),
        )
        self.assertEqual(
            value["lanes"]["docs"]["workload_sha256"],
            performance_policy.docs_workload_sha256(),
        )

    def test_noexec_evidence_matches_historical_subject_and_current_producers(
        self,
    ) -> None:
        self.assertIn(NOEXEC_EVIDENCE, baseline()["evidence"])
        evidence = (ROOT / NOEXEC_EVIDENCE).read_text(encoding="utf-8")

        def digest(label: str) -> str:
            match = re.search(
                rf"^- {re.escape(label)}: `([0-9a-f]{{64}})`$",
                evidence,
                flags=re.MULTILINE,
            )
            self.assertIsNotNone(match, label)
            return match.group(1)

        expected_identities = {
            "Raw profile producer": hashlib.sha256(
                performance_policy.PROFILE_SOURCE.read_bytes()
            ).hexdigest(),
            "Validator": hashlib.sha256(
                Path(verification_contract.__file__).read_bytes()
            ).hexdigest(),
            "Combined performance producer":
                performance_policy.performance_producer_sha256(),
            "Case manifest": guard_boundary_profile._case_manifest_sha256(
                guard_boundary_profile.GUARD_BOUNDARY_CASES
            ),
            "Source guard": hashlib.sha256(
                (ROOT / "kernel/hooks/worktree-guard.sh").read_bytes()
            ).hexdigest(),
            "Source checker": hashlib.sha256(
                (ROOT / "kernel/bin/dev-worktree.sh").read_bytes()
            ).hexdigest(),
            "Default policy": hashlib.sha256(
                (
                    ROOT
                    / "kernel/policy/default-worktree-policy.yml"
                ).read_bytes()
            ).hexdigest(),
        }
        for label, expected in expected_identities.items():
            self.assertEqual(digest(label), expected, label)

        count_match = re.search(
            r"^- Measured-subject files: `([0-9]+)`$",
            evidence,
            flags=re.MULTILINE,
        )
        self.assertIsNotNone(count_match)
        self.assertEqual(
            int(count_match.group(1)),
            NOEXEC_HISTORICAL_SUBJECT_FILES,
        )
        self.assertEqual(
            digest("Measured-subject SHA-256"),
            NOEXEC_HISTORICAL_SUBJECT_SHA256,
        )
        self.assertEqual(
            int(
                re.search(
                    r"^- Git processes: `([0-9]+)`$",
                    evidence,
                    flags=re.MULTILINE,
                ).group(1)
            ),
            baseline()["process_measurement"]["git_processes"],
        )

    def test_unrelated_tracked_candidate_keeps_historical_evidence_valid(
        self,
    ) -> None:
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "README.md"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(tracked.stdout, "README.md\n")

        readme = ROOT / "README.md"
        evidence_path = ROOT / NOEXEC_EVIDENCE
        source_guard = ROOT / "kernel/hooks/worktree-guard.sh"
        read_bytes = Path.read_bytes
        read_text = Path.read_text

        def candidate_bytes(path: Path) -> bytes:
            value = read_bytes(path)
            if path == readme:
                return value + b"\nUnrelated tracked candidate perturbation.\n"
            return value

        with mock.patch.object(Path, "read_bytes", candidate_bytes):
            self.test_noexec_evidence_matches_historical_subject_and_current_producers()

        def tampered_evidence(path: Path, *args, **kwargs) -> str:
            value = read_text(path, *args, **kwargs)
            if path == evidence_path:
                return value.replace(
                    NOEXEC_HISTORICAL_SUBJECT_SHA256,
                    "0" * 64,
                    1,
                )
            return value

        with mock.patch.object(Path, "read_text", tampered_evidence):
            with self.assertRaises(AssertionError):
                self.test_noexec_evidence_matches_historical_subject_and_current_producers()

        def drifted_producer(path: Path) -> bytes:
            value = read_bytes(path)
            if path == source_guard:
                return value + b"\n# bound producer drift\n"
            return value

        with mock.patch.object(Path, "read_bytes", drifted_producer):
            with self.assertRaises(AssertionError):
                self.test_noexec_evidence_matches_historical_subject_and_current_producers()

    def test_time_is_warning_only_and_context_is_required(self) -> None:
        current = observation(elapsed_ms=999999, load_note="")
        warnings = performance_policy.evaluate(current, baseline())
        self.assertIn("missing load context", messages(warnings))
        self.assertTrue(all(item["severity"] == "warning" for item in warnings))

    def test_inventory_and_process_growth_are_reported_not_hidden(self) -> None:
        expected = baseline()["process_measurement"]
        current = observation(
            test_count=baseline()["test_count"] + 50,
            process_measurement={
                "status": "measured",
                "counter_scope": expected["counter_scope"],
                "producer_sha256": expected["producer_sha256"],
                "case_manifest_sha256": expected["case_manifest_sha256"],
                "git_processes": expected["git_processes"] + 500,
            },
        )
        warning_messages = messages(performance_policy.evaluate(
            current, baseline(), require_process=True,
        ))
        self.assertIn("test inventory grew", warning_messages)
        self.assertIn("scoped Git process count grew", warning_messages)

    def test_missing_or_incompatible_process_measurement_is_not_zero(self) -> None:
        expected = baseline()["process_measurement"]
        for process in (
            None,
            {
                **expected,
                "producer_sha256": "f" * 64,
            },
        ):
            with self.subTest(process=process):
                self.assertIn(
                    "scoped Git process count not measured",
                    messages(performance_policy.evaluate(
                        observation(process_measurement=process),
                        baseline(),
                        require_process=True,
                    )),
                )

    def test_arbitrary_focused_run_has_no_lane_wide_time_budget(self) -> None:
        current = observation(lane="focused", elapsed_ms=999999999)
        self.assertNotIn(
            "wall time exceeded advisory budget",
            messages(performance_policy.evaluate(current, baseline())),
        )

    def test_hypothesis_lane_has_no_time_budget(self) -> None:
        value = copy.deepcopy(baseline())
        value["lanes"]["pre-pr"].update({
            "status": "hypothesis",
            "observation_count": 0,
            "session_count": 0,
            "p90_ms": None,
            "warning_elapsed_ms": None,
        })
        self.assertNotIn(
            "wall time exceeded advisory budget",
            messages(performance_policy.evaluate(
                observation(elapsed_ms=999999999), value,
            )),
        )

    def test_receipt_can_never_suppress_verification(self) -> None:
        for path in (
            ROOT / "Makefile",
            ROOT / "engine" / "tests" / "verify_lane.py",
            ROOT / "install.sh",
            ROOT / "live-verify" / "verify-live-verify.sh",
        ):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("authorizes_skip", source)
            self.assertNotIn('["reusable"]', source)
        source = Path(performance_policy.__file__).read_text(encoding="utf-8")
        self.assertNotIn("return_cached_pass", source)

    def test_baseline_contract_rejects_unknown_or_incomplete_shape(self) -> None:
        context_unknown = copy.deepcopy(baseline())
        context_unknown["machine_contexts"] = [{
            "platform": "fixture",
            "architecture": "fixture",
            "logical_cpu_count": 1,
            "load_note": "fixture",
            "session_id": "not-in-v1",
        }]
        context_unknown["session_count"] = 1
        for value in (
            dict(baseline(), surprise=True),
            dict(baseline(), process_measurement=None),
            context_unknown,
        ):
            with self.subTest(value=value), self.assertRaises(
                verification_contract.ContractError,
            ):
                verification_contract.validate_performance_baseline(value)

    def test_advisory_cli_exits_zero_for_findings(self) -> None:
        value = accepted_lane_baseline("docs")
        with tempfile.TemporaryDirectory(prefix="awa-performance-policy.") as tmp:
            path = Path(tmp) / "baseline.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            stdout = io.StringIO()
            rc = performance_policy.main(
                [
                    "evaluate-lane",
                    "--lane", "docs",
                    "--elapsed-ms", "999999999",
                    "--load-note", "ordinary fixture load",
                    "--baseline", str(path),
                ],
                stdout=stdout,
            )
            self.assertEqual(rc, 0)
            self.assertIn(
                "wall time exceeded advisory budget", stdout.getvalue()
            )

            value["lanes"]["docs"]["workload_sha256"] = "f" * 64
            path.write_text(json.dumps(value), encoding="utf-8")
            stdout = io.StringIO()
            rc = performance_policy.main(
                [
                    "evaluate-lane",
                    "--lane", "docs",
                    "--elapsed-ms", "999999999",
                    "--load-note", "ordinary fixture load",
                    "--baseline", str(path),
                ],
                stdout=stdout,
            )
        self.assertEqual(rc, 0)
        self.assertIn("fixed workload not matched", stdout.getvalue())
        self.assertNotIn(
            "wall time exceeded advisory budget", stdout.getvalue()
        )

    def test_malformed_baseline_is_cli_failure(self) -> None:
        with tempfile.TemporaryDirectory(prefix="awa-performance-policy.") as tmp:
            path = Path(tmp) / "baseline.json"
            path.write_text('{"schema":"wrong"}\n', encoding="utf-8")
            stderr = io.StringIO()
            rc = performance_policy.main(
                [
                    "evaluate-lane",
                    "--lane", "pre-pr",
                    "--elapsed-ms", "1",
                    "--baseline", str(path),
                ],
                stderr=stderr,
            )
        self.assertEqual(rc, 2)
        self.assertIn("performance-policy:", stderr.getvalue())

    def test_module_duration_map_is_complete_and_sorted(self) -> None:
        records = (
            {"module": "z", "elapsed_ms": 2},
            {"module": "a", "elapsed_ms": 3},
            {"module": "z", "elapsed_ms": 5},
        )
        self.assertEqual(
            suite_runner.module_durations_ms(records),
            {"a": 3, "z": 7},
        )

    def test_make_wiring_keeps_process_probe_explicit(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertIn("verify-performance:", makefile)
        verify_body, performance_body = makefile.split("verify-performance:", 1)
        self.assertNotIn("guard_boundary_profile", verify_body)
        self.assertIn(
            "python3 -B -m engine.tests.guard_boundary_profile",
            performance_body,
        )
        self.assertIn("--boundary source --count-git", performance_body)
        self.assertIn("AWA_PERFORMANCE_WARNINGS_DISABLED=1", performance_body)
        self.assertIn(
            " ".join(performance_policy.DOCS_WORKLOAD_COMMAND),
            makefile,
        )

    def test_make_verify_advisory_runs_after_authoritative_result(self) -> None:
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        verify_body = makefile.split("verify:", 1)[1].split("verify-docs:", 1)[0]
        self.assertLess(
            verify_body.index('echo "verify: OK"'),
            verify_body.index("performance_policy"),
        )
        for command in (
            "engine/tests/run-tests.sh",
            "bash ./install.sh --check",
            "live-verify/verify-live-verify.sh",
        ):
            self.assertLess(
                verify_body.index(command),
                verify_body.index("performance_policy"),
            )

    def test_runbook_covers_lane_and_rehearsal_selection(self) -> None:
        runbook = (
            ROOT / "docs" / "runbooks" / "verification-lanes.md"
        ).read_text(encoding="utf-8")
        normalized = " ".join(runbook.split())
        for phrase in (
            "non-authoritative",
            "every runtime, test, Makefile, or contract change",
            "make verify-install",
            "PM, router, finish, or retention",
            "complete transition rehearsal",
            "Do not run that complete finish matrix for unrelated changes",
            "LIVE-OPERATOR-RUNBOOK.md",
            "AWA_TEST_JOBS=1 make verify",
            "Receipts never skip",
            "paid GitHub Actions runner",
        ):
            self.assertIn(phrase, normalized)


if __name__ == "__main__":
    unittest.main(verbosity=2)
