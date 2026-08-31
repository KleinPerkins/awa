"""Regression tests for the closed finish case/layer partition."""

from __future__ import annotations

import fcntl
import os
import socket
import subprocess
import time
import unittest
from dataclasses import FrozenInstanceError

from engine.tests import suite_runner
from .finish_case_manifest import (
    ALL_FINISH_CASES,
    PHYSICAL_CANARIES,
    finish_cases,
    run_pure_case,
)


REQUIRED_PHYSICAL_SEAMS = {
    "crash_cut",
    "fsync",
    "f_fullfsync",
    "retention",
    "publication",
    "stable_snapshot_recapture",
    "no_follow",
    "shared_lock",
    "removal_journal",
}


class FinishCaseManifestTest(unittest.TestCase):
    def test_every_finish_case_has_exactly_one_layer_and_oracle(self) -> None:
        ids = set()
        for case in ALL_FINISH_CASES:
            with self.subTest(case_id=case.case_id):
                self.assertIn(case.layer, ("pure", "physical"))
                self.assertTrue(case.oracle)
                self.assertNotIn(case.case_id, ids)
                ids.add(case.case_id)
        self.assertEqual(len(finish_cases(layer="pure")), 30)
        self.assertEqual(len(finish_cases(layer="physical")), 4)

    def test_case_inputs_expected_values_and_registry_are_immutable(self) -> None:
        case = ALL_FINISH_CASES[0]
        with self.assertRaises(FrozenInstanceError):
            case.layer = "physical"
        with self.assertRaises(TypeError):
            case.input["answer"] = "replaced"
        with self.assertRaises(TypeError):
            case.expected["accepted"] = False
        with self.assertRaises(TypeError):
            PHYSICAL_CANARIES["crash_cut"] = {}
        with self.assertRaises(TypeError):
            PHYSICAL_CANARIES["crash_cut"]["positive"] = "missing"

    def test_required_physical_seams_remain_real(self) -> None:
        self.assertEqual(REQUIRED_PHYSICAL_SEAMS, set(PHYSICAL_CANARIES))
        inventory = set(suite_runner.discover_test_ids())
        loader = unittest.defaultTestLoader
        for seam, pair in PHYSICAL_CANARIES.items():
            with self.subTest(seam=seam):
                self.assertEqual(set(pair), {"positive", "negative"})
                self.assertNotEqual(pair["positive"], pair["negative"])
                for polarity in ("positive", "negative"):
                    test_id = pair[polarity]
                    self.assertEqual(
                        loader.loadTestsFromName(test_id).countTestCases(), 1)
                    self.assertIn(test_id, inventory)

    def test_all_pure_cases_call_the_production_oracle(self) -> None:
        for case in finish_cases(layer="pure"):
            with self.subTest(case_id=case.case_id):
                self.assertEqual(run_pure_case(case), case.expected)

    def test_pure_cases_refuse_physical_access(self) -> None:
        case = finish_cases(layer="pure")[0]
        probes = {
            "open": lambda _values: open(os.devnull, encoding="utf-8"),
            "stat": lambda _values: os.stat(os.devnull),
            "subprocess": lambda _values: subprocess.run(
                ["git", "--version"], check=False),
            "lock": lambda _values: fcntl.flock(-1, fcntl.LOCK_EX),
            "clock": lambda _values: time.monotonic(),
            "socket": lambda _values: socket.socket(),
        }
        for name, adapter in probes.items():
            with self.subTest(name=name), self.assertRaisesRegex(
                    AssertionError, "physical access from pure case"):
                run_pure_case(case, adapter=adapter)

    def test_physical_case_cannot_enter_pure_runner(self) -> None:
        with self.assertRaisesRegex(
                AssertionError, "physical case cannot use pure runner"):
            run_pure_case(finish_cases(layer="physical")[0])


if __name__ == "__main__":
    unittest.main()
