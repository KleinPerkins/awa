"""M3 guard-boundary profiling, parity, and installed-layering gates."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engine.tests import guard_boundary_profile
from engine.tests import suite_runner
from engine.tests import verification_contract


class GuardBoundaryProfileTest(unittest.TestCase):
    def test_all_boundaries_consume_same_case_ids(self):
        expected = tuple(
            case.label for case in guard_boundary_profile.GUARD_BOUNDARY_CASES
        )
        reports = {
            "engine": guard_boundary_profile.run_engine_cases(
                guard_boundary_profile.GUARD_BOUNDARY_CASES
            ),
            "source": guard_boundary_profile.run_source_hook_cases(
                guard_boundary_profile.GUARD_BOUNDARY_CASES
            ),
            "installed": guard_boundary_profile.run_installed_hook_cases(
                guard_boundary_profile.GUARD_BOUNDARY_CASES
            ),
            "owner": guard_boundary_profile.run_owner_mode_cases(
                guard_boundary_profile.GUARD_BOUNDARY_CASES
            ),
        }
        expected_outcomes = {
            case.label: case.expected_permission
            for case in guard_boundary_profile.GUARD_BOUNDARY_CASES
        }
        self.assertEqual(
            len(
                {
                    report["case_manifest_sha256"]
                    for report in reports.values()
                }
            ),
            1,
        )
        for boundary, report in reports.items():
            with self.subTest(boundary=boundary):
                verification_contract.validate_guard_boundary_profile(report)
                self.assertEqual(tuple(report["case_ids"]), expected)
                self.assertEqual(report["outcomes"], expected_outcomes)
                self.assertTrue(report["passed"])

    def test_git_counter_reports_scope_and_never_changes_verdicts(self):
        plain = guard_boundary_profile.run_source_hook_cases(
            guard_boundary_profile.GUARD_BOUNDARY_CASES
        )
        counted = guard_boundary_profile.run_source_hook_cases(
            guard_boundary_profile.GUARD_BOUNDARY_CASES,
            count_git=True,
        )
        self.assertEqual(plain["outcomes"], counted["outcomes"])
        self.assertEqual(
            counted["counter_scope"],
            guard_boundary_profile.GIT_COUNTER_SCOPE,
        )
        self.assertGreater(counted["git_processes"], 0)

    def test_cases_use_distinct_private_home_and_xdg_roots(self):
        observed = []
        original = guard_boundary_profile._private_environment

        def capture(root):
            environment = original(root)
            observed.append(
                tuple(
                    environment[name]
                    for name in (
                        "HOME",
                        "XDG_DATA_HOME",
                        "XDG_CONFIG_HOME",
                        "XDG_STATE_HOME",
                        "XDG_CACHE_HOME",
                        "TMPDIR",
                    )
                )
            )
            return environment

        with mock.patch.object(
            guard_boundary_profile,
            "_private_environment",
            side_effect=capture,
        ):
            report = guard_boundary_profile.run_engine_cases(
                guard_boundary_profile.GUARD_BOUNDARY_CASES
            )
        self.assertTrue(report["passed"])
        case_roots = observed
        self.assertEqual(
            len(case_roots),
            len(guard_boundary_profile.GUARD_BOUNDARY_CASES),
        )
        for index in range(6):
            self.assertEqual(
                len({roots[index] for roots in case_roots}),
                len(case_roots),
            )

    def test_profile_validator_rejects_unknown_key(self):
        report = guard_boundary_profile.run_engine_cases(
            guard_boundary_profile.GUARD_BOUNDARY_CASES
        )
        report["surprise"] = True
        with self.assertRaises(verification_contract.ContractError):
            verification_contract.validate_guard_boundary_profile(report)

    def test_cli_writes_valid_profile_document(self):
        with tempfile.TemporaryDirectory(prefix="awa-m3-profile-cli.") as raw:
            output = Path(raw) / "profile.json"
            result = guard_boundary_profile.main(
                [
                    "--boundary",
                    "engine",
                    "--count-git",
                    "--json-out",
                    str(output),
                ]
            )
            self.assertEqual(result, 0)
            document = json.loads(output.read_text(encoding="utf-8"))
            verification_contract.validate_guard_boundary_profile(document)
            self.assertEqual(document["boundary"], "engine")
            self.assertEqual(
                document["counter_scope"],
                guard_boundary_profile.GIT_COUNTER_SCOPE,
            )

    def test_deliberate_guard_break_is_detected(self):
        with tempfile.TemporaryDirectory(prefix="awa-m3-profile-break.") as raw:
            broken_guard = Path(raw) / "broken-guard.sh"
            broken_guard.write_text(
                "#!/bin/sh\nprintf '%s\\n' '{\"permission\":\"allow\"}'\n",
                encoding="utf-8",
            )
            broken_guard.chmod(0o700)
            report = guard_boundary_profile.run_source_hook_cases(
                guard_boundary_profile.GUARD_BOUNDARY_CASES,
                guard_path=broken_guard,
            )
        self.assertFalse(report["passed"])
        self.assertNotEqual(
            report["outcomes"]["mutation_deny"],
            report["expected_outcomes"]["mutation_deny"],
        )

    def test_installed_decision_requires_every_identity_and_canary_gate(self):
        identity = guard_boundary_profile.probe_installed_identity()
        canaries = {
            name: True
            for name in guard_boundary_profile.INSTALLED_DECISION_CANARIES
        }
        self.assertEqual(
            guard_boundary_profile.installed_matrix_decision(
                identity,
                canaries,
                full_engine_kernel_parity=True,
            ),
            "byte_identity_plus_canaries",
        )

        for installed_key in (
            "installed_guard_sha256",
            "installed_checker_sha256",
            "installed_policy_sha256",
            "installed_python",
            "installed_bash",
        ):
            with self.subTest(identity=installed_key):
                changed = copy.deepcopy(identity)
                changed[installed_key] = "different"
                self.assertEqual(
                    guard_boundary_profile.installed_matrix_decision(
                        changed,
                        canaries,
                        full_engine_kernel_parity=True,
                    ),
                    "retain_full",
                )

        for canary in guard_boundary_profile.INSTALLED_DECISION_CANARIES:
            with self.subTest(canary=canary):
                changed = dict(canaries)
                changed[canary] = False
                self.assertEqual(
                    guard_boundary_profile.installed_matrix_decision(
                        identity,
                        changed,
                        full_engine_kernel_parity=True,
                    ),
                    "retain_full",
                )

        self.assertEqual(
            guard_boundary_profile.installed_matrix_decision(
                identity,
                canaries,
                full_engine_kernel_parity=False,
            ),
            "retain_full",
        )

    def test_installed_decision_canaries_are_closed_and_suite_loadable(self):
        self.assertEqual(
            set(guard_boundary_profile.INSTALLED_DECISION_CANARY_TESTS),
            set(guard_boundary_profile.INSTALLED_DECISION_CANARIES),
        )
        inventory = set(suite_runner.discover_test_ids())
        for name, test_id in (
            guard_boundary_profile.INSTALLED_DECISION_CANARY_TESTS.items()
        ):
            with self.subTest(canary=name):
                self.assertIn(test_id, inventory)

    def test_installed_decision_rejects_unclosed_canary_input(self):
        identity = guard_boundary_profile.probe_installed_identity()
        canaries = {
            name: True
            for name in guard_boundary_profile.INSTALLED_DECISION_CANARIES
        }
        canaries["surprise"] = True
        with self.assertRaises(ValueError):
            guard_boundary_profile.installed_matrix_decision(
                identity,
                canaries,
                full_engine_kernel_parity=True,
            )


if __name__ == "__main__":
    unittest.main()
