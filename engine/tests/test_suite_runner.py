"""M1-A verification-runner contract tests."""

from __future__ import annotations

import copy
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Optional
from unittest import mock

from engine.tests import suite_runner, verification_contract


_REDACT_MODULE = "engine.tests.test_redact"
_REDACT_IDS = (
    "engine.tests.test_redact.TestRedact.test_empty_and_clean_passthrough",
    "engine.tests.test_redact.TestRedact.test_env_secret_redacted",
    "engine.tests.test_redact.TestRedact.test_github_token_redacted",
    "engine.tests.test_redact.TestRedact.test_secret_assignment_redacted",
    "engine.tests.test_redact.TestRedact.test_url_credentials_redacted",
)


def _identity(head: str = "a" * 40, clean: bool = True) -> dict:
    return {"head": head, "clean": clean}


def _records() -> tuple:
    return (
        {
            "test_id": "a.Test.test_x",
            "module": "a",
            "outcome": "passed",
            "skip_reason": None,
            "elapsed_ms": 1,
        },
    )


def _passed_run() -> dict:
    return {
        "outcome": "passed",
        "elapsed_ms": 1,
        "counts": {
            "passed": 1,
            "failure": 0,
            "error": 0,
            "skipped": 0,
            "expected_failure": 0,
            "unexpected_success": 0,
        },
    }


def _context() -> dict:
    return {
        "command": ["python3", "-B", "-m", "engine.tests.suite_runner"],
        "selectors": ["a.Test.test_x"],
        "platform": "test",
        "architecture": "test",
        "logical_cpu_count": 1,
        "load_note": "test",
        "generated_at_utc": "2026-08-29T00:00:00+00:00",
        "resource": {"user_ms": 1, "system_ms": 1, "max_rss_kb": 1},
    }


def _receipt(
    before: Optional[dict] = None, after: Optional[dict] = None
) -> dict:
    identity = _identity()
    return suite_runner.build_receipt(
        before or identity,
        after or identity,
        ("a.Test.test_x",),
        _records(),
        "focused",
        1,
        _passed_run(),
        _context(),
    )


class SuiteRunnerTest(unittest.TestCase):
    def test_inventory_is_sorted_unique_and_stable(self) -> None:
        first = suite_runner.discover_test_ids((_REDACT_MODULE,))
        second = suite_runner.discover_test_ids((_REDACT_MODULE,))
        self.assertEqual(first, tuple(sorted(set(first))))
        self.assertEqual(first, second)
        self.assertEqual(first, _REDACT_IDS)

    def test_dirty_or_changed_source_receipt_is_never_reusable(self) -> None:
        cases = (
            (_identity(clean=False), _identity(clean=False)),
            (_identity(), _identity(head="b" * 40)),
            (_identity(), _identity(clean=False)),
        )
        for before, after in cases:
            with self.subTest(before=before, after=after):
                receipt = _receipt(before, after)
                self.assertFalse(receipt["reusable"])
                self.assertEqual(receipt["source_state"], "unstable")
                self.assertFalse(receipt["authorizes_skip"])

    def test_clean_stable_pass_is_reusable_but_never_authorizes_skip(self) -> None:
        receipt = _receipt()
        verification_contract.validate_receipt(receipt)
        self.assertTrue(receipt["reusable"])
        self.assertFalse(receipt["authorizes_skip"])
        self.assertEqual(receipt["source_state"], "stable")

    def test_receipt_validator_rejects_unknown_missing_and_wrong_type(self) -> None:
        mutations = []

        unknown = _receipt()
        unknown["surprise"] = True
        mutations.append(unknown)

        missing = _receipt()
        del missing["inventory_sha256"]
        mutations.append(missing)

        wrong_type = _receipt()
        wrong_type["jobs"] = "1"
        mutations.append(wrong_type)

        for value in mutations:
            with self.subTest(keys=tuple(sorted(value))):
                with self.assertRaises(verification_contract.ContractError):
                    verification_contract.validate_receipt(value)

    def test_receipt_validator_rejects_cross_field_mismatch(self) -> None:
        for field, value in (
            ("source_state", "unstable"),
            ("reusable", False),
            ("authorizes_skip", True),
            ("test_count", 2),
        ):
            receipt = _receipt()
            receipt[field] = value
            with self.subTest(field=field):
                with self.assertRaises(verification_contract.ContractError):
                    verification_contract.validate_receipt(receipt)

    def test_progress_names_case_and_elapsed_time(self) -> None:
        stream = io.StringIO()
        result = suite_runner.run_serial(
            (_REDACT_IDS[3],),
            stream,
        )
        self.assertEqual(result["outcome"], "passed")
        self.assertEqual(result["inventory"], (_REDACT_IDS[3],))
        self.assertIn(_REDACT_IDS[3], stream.getvalue())
        self.assertRegex(stream.getvalue(), r"\[[0-9]+\.[0-9]s\] END")

    def test_timing_summary_has_module_totals_and_stable_slowest_order(self) -> None:
        records = (
            {
                "test_id": "engine.tests.test_slow.Case.test_b",
                "module": "engine.tests.test_slow",
                "outcome": "passed",
                "skip_reason": None,
                "elapsed_ms": 500,
            },
            {
                "test_id": "engine.tests.test_fast.Case.test_c",
                "module": "engine.tests.test_fast",
                "outcome": "passed",
                "skip_reason": None,
                "elapsed_ms": 100,
            },
            {
                "test_id": "engine.tests.test_slow.Case.test_a",
                "module": "engine.tests.test_slow",
                "outcome": "passed",
                "skip_reason": None,
                "elapsed_ms": 500,
            },
        )
        summary = suite_runner.summarize_timings(records, limit=2)
        self.assertEqual(summary["modules"][0]["module"], "engine.tests.test_slow")
        self.assertEqual(summary["modules"][0]["elapsed_ms"], 1000)
        self.assertEqual(
            [item["test_id"] for item in summary["slowest_tests"]],
            [
                "engine.tests.test_slow.Case.test_a",
                "engine.tests.test_slow.Case.test_b",
            ],
        )

    def test_worker_count_other_than_one_is_refused_in_m1(self) -> None:
        self.assertEqual(suite_runner.validate_jobs(1), 1)
        for value in (0, 2, 4):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "M2 sharding is not enabled"):
                    suite_runner.validate_jobs(value)

    def test_existing_unittest_flags_remain_compatible(self) -> None:
        cases = (
            (("-v", _REDACT_MODULE), _REDACT_IDS),
            ((_REDACT_MODULE, "--failfast"), _REDACT_IDS),
            (
                ("-k", "secret_assignment", _REDACT_MODULE),
                (_REDACT_IDS[3],),
            ),
        )
        for args, expected in cases:
            with self.subTest(args=args):
                self.assertEqual(
                    suite_runner.inventory_from_unittest_args(args),
                    expected,
                )

    def test_full_inventory_classification_preserves_dashboard_gate(self) -> None:
        full_cases = (
            (),
            ("--jobs", "1"),
            ("--json-out", "/tmp/receipt.json", "--lane", "pre-pr"),
            ("--", "--verbose", "--failfast"),
        )
        filtered_cases = (
            ("--list-ids",),
            ("--", _REDACT_MODULE),
            (_REDACT_MODULE, "--failfast"),
            ("--", "-k", "secret_assignment"),
        )
        for args in full_cases:
            with self.subTest(args=args):
                self.assertTrue(
                    suite_runner.invocation_runs_full_inventory(args)
                )
        for args in filtered_cases:
            with self.subTest(args=args):
                self.assertFalse(
                    suite_runner.invocation_runs_full_inventory(args)
                )

    def test_selector_environment_is_classified_as_filtered(self) -> None:
        with mock.patch.dict(
            "os.environ",
            {"AWA_TEST_SELECTORS": _REDACT_MODULE},
        ):
            self.assertFalse(
                suite_runner.invocation_runs_full_inventory(
                    ("--selectors-env", "AWA_TEST_SELECTORS")
                )
            )

    def test_run_tests_dashboard_gate_uses_invocation_scope(self) -> None:
        run_tests = Path(__file__).with_name("run-tests.sh")
        with tempfile.TemporaryDirectory(prefix="awa-run-tests-scope.") as tmp:
            root = Path(tmp)
            bindir = root / "bin"
            bindir.mkdir()
            fake_python = bindir / "python3"
            fake_python.write_text(
                "#!/bin/sh\n"
                'printf "%s\\n" "$*" >> "$AWA_FAKE_PYTHON_LOG"\n'
                'case "$*" in\n'
                "  *invocation_runs_full_inventory*)\n"
                '    printf "%s\\n" "$AWA_FAKE_SCOPE"\n'
                "    ;;\n"
                "esac\n"
                "exit 0\n",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)
            log = root / "python.log"
            cases = (
                (
                    "full",
                    ("--jobs", "1", "--json-out", str(root / "receipt.json")),
                    True,
                ),
                ("filtered", ("--", _REDACT_MODULE), False),
            )
            for scope, args, expect_dashboard in cases:
                with self.subTest(scope=scope):
                    log.write_text("", encoding="utf-8")
                    env = os.environ.copy()
                    env.pop("AWA_ENGINE_TESTS_ACTIVE", None)
                    env.pop("BASH_ENV", None)
                    env.pop("ENV", None)
                    env.update(
                        {
                            "AWA_FAKE_PYTHON_LOG": str(log),
                            "AWA_FAKE_SCOPE": scope,
                            "PATH": str(bindir) + os.pathsep + "/usr/bin:/bin",
                        }
                    )
                    result = subprocess.run(
                        ["/bin/bash", str(run_tests), *args],
                        text=True,
                        capture_output=True,
                        check=False,
                        env=env,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    dashboard_ran = "dashboard/test_emitter.py" in log.read_text(
                        encoding="utf-8"
                    )
                    self.assertEqual(dashboard_ran, expect_dashboard)

    def test_unknown_unittest_flag_fails_loudly(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported unittest argument"):
            suite_runner.inventory_from_unittest_args(
                ("--not-a-real-flag", _REDACT_MODULE)
            )

    def test_atomic_json_output_has_no_temporary_residue(self) -> None:
        with tempfile.TemporaryDirectory(prefix="awa-suite-runner-test.") as tmp:
            target = Path(tmp) / "receipt.json"
            suite_runner.write_atomic_json(target, _receipt())
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), _receipt())
            self.assertEqual(tuple(Path(tmp).iterdir()), (target,))

    def test_validator_rejects_nested_unknown_key_and_unsorted_records(self) -> None:
        nested = _receipt()
        nested["context"]["resource"]["surprise"] = 1
        with self.assertRaises(verification_contract.ContractError):
            verification_contract.validate_receipt(nested)

        unsorted = _receipt()
        extra = copy.deepcopy(unsorted["records"][0])
        extra["test_id"] = "0.Test.test_first"
        unsorted["records"].append(extra)
        unsorted["test_count"] = 2
        unsorted["run"]["counts"]["passed"] = 2
        with self.assertRaisesRegex(
            verification_contract.ContractError, "records must be sorted"
        ):
            verification_contract.validate_receipt(unsorted)


if __name__ == "__main__":
    unittest.main()
