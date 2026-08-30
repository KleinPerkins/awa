"""M2-A deterministic process-worker and equivalence tests."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from engine.tests import suite_runner, verification_contract


_MODULE_A = "engine.tests.test_redact"
_MODULE_B = "engine.tests.test_identity_paths"
_TEST_A = (
    "engine.tests.test_redact.TestRedact.test_secret_assignment_redacted"
)
_TEST_B = (
    "engine.tests.test_identity_paths.TestIdentity."
    "test_common_dir_key_stable_and_short"
)
_ISOLATION_NAMES = (
    "TMPDIR",
    "XDG_CONFIG_HOME",
    "XDG_STATE_HOME",
    "XDG_CACHE_HOME",
)
_RECEIPT_ENV_NAMES = (
    "AWA_TEST_RECEIPT",
    "AWA_TEST_PRIOR_RECEIPT",
)


@contextlib.contextmanager
def _isolated_main_environment(**values):
    """Keep nested CLI probes independent from an outer campaign receipt."""

    with mock.patch.dict(os.environ):
        for name in _RECEIPT_ENV_NAMES:
            os.environ.pop(name, None)
        os.environ.update(values)
        yield


def _inventory_digest(test_ids) -> str:
    return hashlib.sha256("\n".join(tuple(test_ids)).encode("utf-8")).hexdigest()


def worker_doc(module, test_ids, *, resource=None, records=None) -> dict:
    test_ids = tuple(sorted(test_ids))
    if records is None:
        records = [
            {
                "test_id": test_id,
                "module": module,
                "outcome": "passed",
                "skip_reason": None,
                "elapsed_ms": 1,
            }
            for test_id in test_ids
        ]
    return {
        "schema": verification_contract.WORKER_SCHEMA,
        "module": module,
        "inventory_sha256": _inventory_digest(test_ids),
        "records": records,
        "outcome": "passed",
        "elapsed_ms": 1,
        "resource": resource
        or {"user_ms": 1, "system_ms": 1, "max_rss_kb": 1},
    }


def _prior_receipt() -> dict:
    records = (
        {
            "test_id": _TEST_B,
            "module": _MODULE_B,
            "outcome": "passed",
            "skip_reason": None,
            "elapsed_ms": 1000,
        },
        {
            "test_id": _TEST_A,
            "module": _MODULE_A,
            "outcome": "passed",
            "skip_reason": None,
            "elapsed_ms": 10,
        },
    )
    run = {
        "outcome": "passed",
        "elapsed_ms": 1010,
        "counts": {
            "passed": 2,
            "failure": 0,
            "error": 0,
            "skipped": 0,
            "expected_failure": 0,
            "unexpected_success": 0,
        },
    }
    context = {
        "command": ["python3", "-B", "-m", "engine.tests.suite_runner"],
        "selectors": [_TEST_A, _TEST_B],
        "platform": "test",
        "architecture": "test",
        "logical_cpu_count": 1,
        "load_note": "test",
        "generated_at_utc": "2026-08-29T00:00:00+00:00",
        "resource": {"user_ms": 1, "system_ms": 1, "max_rss_kb": 1},
    }
    identity = {"head": "a" * 40, "clean": True}
    return suite_runner.build_receipt(
        identity,
        identity,
        tuple(sorted((_TEST_A, _TEST_B))),
        records,
        "focused",
        1,
        run,
        context,
    )


def _write_process(path: Path, text: str, *, delay: float = 0.0):
    code = (
        "import time\n"
        "from pathlib import Path\n"
        f"time.sleep({delay!r})\n"
        f"Path({str(path)!r}).write_text({text!r}, encoding='utf-8')\n"
    )
    return (sys.executable, "-c", code)


def _fault_factory(mode, processes):
    def factory(command, **kwargs):
        output = Path(command[command.index("--worker-json") + 1])
        module = command[command.index("--worker-module") + 1]
        if mode == "crash":
            replacement = (sys.executable, "-c", "raise SystemExit(7)")
        elif mode == "timeout":
            replacement = (sys.executable, "-c", "import time; time.sleep(60)")
        elif mode == "signal":
            replacement = (
                sys.executable,
                "-c",
                "import os, signal; os.kill(os.getpid(), signal.SIGTERM)",
            )
        elif mode == "partial":
            replacement = _write_process(output, '{"schema":')
        elif mode == "malformed":
            replacement = _write_process(output, "not-json")
        elif mode == "missing":
            replacement = (sys.executable, "-c", "pass")
        elif mode == "extra":
            doc = worker_doc(
                "engine.tests.test_extra",
                ("engine.tests.test_extra.Case.test_x",),
            )
            replacement = _write_process(output, json.dumps(doc))
        elif mode == "inventory":
            doc = worker_doc(module, (f"{module}.FakeCase.test_not_selected",))
            replacement = _write_process(output, json.dumps(doc))
        elif mode == "oversized":
            code = (
                "from pathlib import Path\n"
                f"Path({str(output)!r}).write_bytes("
                f"b'x' * {verification_contract.MAX_WORKER_JSON_BYTES + 1})\n"
            )
            replacement = (sys.executable, "-c", code)
        else:
            raise AssertionError(f"unknown fault mode: {mode}")
        process = subprocess.Popen(replacement, **kwargs)
        processes.append(process)
        return process

    return factory


def _document_factory(documents, processes, delays=None):
    delays = delays or {}

    def factory(command, **kwargs):
        output = Path(command[command.index("--worker-json") + 1])
        module = command[command.index("--worker-module") + 1]
        replacement = _write_process(
            output,
            json.dumps(documents[module]),
            delay=delays.get(module, 0.0),
        )
        process = subprocess.Popen(replacement, **kwargs)
        processes.append(process)
        return process

    return factory


class ParallelEquivalenceTest(unittest.TestCase):
    def _ensure_reaped(self, processes) -> None:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=2)

    def test_schedule_is_longest_first_then_name(self) -> None:
        modules = (
            "engine.tests.test_a",
            "engine.tests.test_b",
            "engine.tests.test_c",
        )
        prior = {
            "engine.tests.test_a": 10,
            "engine.tests.test_b": 20,
            "engine.tests.test_c": 20,
        }
        self.assertEqual(
            suite_runner.schedule_modules(modules, prior),
            (
                "engine.tests.test_b",
                "engine.tests.test_c",
                "engine.tests.test_a",
            ),
        )

    def test_group_by_module_is_sorted_and_exact(self) -> None:
        self.assertEqual(
            suite_runner.group_by_module((_TEST_B, _TEST_A)),
            {_MODULE_A: (_TEST_A,), _MODULE_B: (_TEST_B,)},
        )

    def test_worker_command_is_one_python_module_process(self) -> None:
        output = Path("/tmp/awa-worker.json")
        self.assertEqual(
            suite_runner.worker_command(_MODULE_A, output),
            (
                sys.executable,
                "-B",
                "-m",
                "engine.tests.suite_runner",
                "--worker-module",
                _MODULE_A,
                "--worker-json",
                str(output),
            ),
        )

    def test_serial_and_all_worker_counts_emit_identical_manifests(self) -> None:
        selectors = (_TEST_A, _TEST_B)
        serial = suite_runner.run_serial(selectors, io.StringIO())
        for jobs in (1, 2, 4):
            with self.subTest(jobs=jobs):
                parallel = suite_runner.run_parallel(
                    selectors, jobs, None, io.StringIO()
                )
                self.assertEqual(serial["inventory"], parallel["inventory"])
                self.assertEqual(serial["outcomes"], parallel["outcomes"])
                self.assertEqual(
                    tuple(parallel["outcomes"]), tuple(sorted(selectors))
                )

    def test_prior_receipt_schedules_longest_module_first(self) -> None:
        launches = []

        def recording_factory(command, **kwargs):
            launches.append(command[command.index("--worker-module") + 1])
            return subprocess.Popen(command, **kwargs)

        result = suite_runner.run_parallel(
            (_MODULE_A, _MODULE_B),
            1,
            _prior_receipt(),
            io.StringIO(),
            worker_factory=recording_factory,
        )
        self.assertEqual(result["outcome"], "passed")
        self.assertEqual(launches, [_MODULE_B, _MODULE_A])

    def test_every_worker_fault_fails_overall_and_reaps_processes(self) -> None:
        for mode in (
            "crash",
            "timeout",
            "signal",
            "partial",
            "malformed",
            "missing",
            "extra",
            "inventory",
            "oversized",
        ):
            with self.subTest(mode=mode):
                processes = []
                self.addCleanup(self._ensure_reaped, processes)
                timeout = 0.05 if mode == "timeout" else 2.0
                result = suite_runner.run_parallel(
                    (_TEST_A,),
                    2,
                    None,
                    io.StringIO(),
                    worker_factory=_fault_factory(mode, processes),
                    worker_timeout_s=timeout,
                )
                self.assertEqual(result["outcome"], "error")
                self.assertTrue(processes)
                self.assertTrue(all(proc.poll() is not None for proc in processes))

    def test_valid_worker_test_failure_is_aggregated_not_retried(self) -> None:
        record = {
            "test_id": _TEST_A,
            "module": _MODULE_A,
            "outcome": "failure",
            "skip_reason": None,
            "elapsed_ms": 1,
        }
        document = worker_doc(
            _MODULE_A,
            (_TEST_A,),
            records=[record],
        )
        document["outcome"] = "failure"
        processes = []
        self.addCleanup(self._ensure_reaped, processes)
        result = suite_runner.run_parallel(
            (_TEST_A,),
            2,
            None,
            io.StringIO(),
            worker_factory=_document_factory(
                {_MODULE_A: document}, processes
            ),
        )
        self.assertEqual(result["outcome"], "failure")
        self.assertNotIn("runner_error", result)
        self.assertEqual(len(processes), 1)

    def test_valid_json_with_partial_default_inventory_is_rejected(self) -> None:
        inventory = suite_runner.discover_test_ids((_MODULE_A,))
        record = {
            "test_id": inventory[0],
            "module": _MODULE_A,
            "outcome": "failure",
            "skip_reason": None,
            "elapsed_ms": 1,
        }
        document = worker_doc(
            _MODULE_A,
            inventory,
            records=[record],
        )
        document["outcome"] = "failure"
        processes = []
        self.addCleanup(self._ensure_reaped, processes)
        result = suite_runner.run_parallel(
            (_MODULE_A,),
            2,
            None,
            io.StringIO(),
            worker_factory=_document_factory(
                {_MODULE_A: document}, processes
            ),
        )
        self.assertEqual(result["outcome"], "error")
        self.assertIn("inventory mismatch", result["runner_error"])

    def test_duplicate_test_id_from_two_workers_is_rejected(self) -> None:
        duplicate = "same.Case.test_x"
        docs = {
            "engine.tests.test_a": worker_doc(
                "engine.tests.test_a", (duplicate,)
            ),
            "engine.tests.test_b": worker_doc(
                "engine.tests.test_b", (duplicate,)
            ),
        }
        with self.assertRaisesRegex(suite_runner.RunnerError, "duplicate test id"):
            suite_runner.aggregate_worker_records(tuple(docs), docs)

    def test_aggregate_is_sorted_and_preserves_skip_reason(self) -> None:
        skipped = {
            "test_id": "z.Case.test_skip",
            "module": "z",
            "outcome": "skipped",
            "skip_reason": "intentional",
            "elapsed_ms": 2,
        }
        docs = {
            "z": worker_doc("z", (skipped["test_id"],), records=[skipped]),
            "a": worker_doc("a", ("a.Case.test_pass",)),
        }
        records = suite_runner.aggregate_worker_records(("z", "a"), docs)
        self.assertEqual(
            [record["test_id"] for record in records],
            ["a.Case.test_pass", "z.Case.test_skip"],
        )
        self.assertEqual(records[1]["skip_reason"], "intentional")

    def test_worker_contract_is_closed_and_size_bounded(self) -> None:
        unknown = worker_doc(_MODULE_A, (_TEST_A,))
        unknown["surprise"] = True
        with self.assertRaises(verification_contract.ContractError):
            verification_contract.validate_worker(unknown)

        oversized = worker_doc(_MODULE_A, (_TEST_A,))
        oversized["records"][0]["outcome"] = "skipped"
        oversized["records"][0]["skip_reason"] = (
            "x" * verification_contract.MAX_WORKER_JSON_BYTES
        )
        with self.assertRaisesRegex(
            verification_contract.ContractError, "worker document is too large"
        ):
            verification_contract.validate_worker(oversized)

    def test_workers_use_distinct_private_temp_and_xdg_roots(self) -> None:
        seen = []
        processes = []
        parent_environment = {
            name: os.environ.get(name)
            for name in ("HOME",) + _ISOLATION_NAMES
        }

        def recording_factory(command, **kwargs):
            env = kwargs["env"]
            roots = {name: Path(env[name]) for name in _ISOLATION_NAMES}
            seen.append(
                {
                    "module": command[command.index("--worker-module") + 1],
                    "home": env.get("HOME"),
                    "roots": roots,
                }
            )
            self.assertTrue(all(path.is_dir() for path in roots.values()))
            process = subprocess.Popen(command, **kwargs)
            processes.append(process)
            return process

        self.addCleanup(self._ensure_reaped, processes)
        result = suite_runner.run_parallel(
            (_MODULE_A, _MODULE_B),
            2,
            None,
            io.StringIO(),
            worker_factory=recording_factory,
        )
        self.assertEqual(result["outcome"], "passed")
        self.assertEqual(len(seen), 2)
        self.assertEqual({row["module"] for row in seen}, {_MODULE_A, _MODULE_B})
        self.assertTrue(
            all(row["home"] == parent_environment["HOME"] for row in seen)
        )
        for name in _ISOLATION_NAMES:
            paths = [row["roots"][name] for row in seen]
            self.assertEqual(len(set(paths)), 2)
            self.assertTrue(all(not path.exists() for path in paths))
            if parent_environment[name] is not None:
                self.assertTrue(
                    all(str(path) != parent_environment[name] for path in paths)
                )
        self.assertEqual(
            {
                name: os.environ.get(name)
                for name in ("HOME",) + _ISOLATION_NAMES
            },
            parent_environment,
        )

    def test_parent_sums_child_cpu_and_uses_max_child_rss(self) -> None:
        ids_a = suite_runner.discover_test_ids((_MODULE_A,))
        ids_b = suite_runner.discover_test_ids((_MODULE_B,))
        documents = {
            _MODULE_A: worker_doc(
                _MODULE_A,
                ids_a,
                resource={"user_ms": 10, "system_ms": 20, "max_rss_kb": 7},
            ),
            _MODULE_B: worker_doc(
                _MODULE_B,
                ids_b,
                resource={"user_ms": 3, "system_ms": 4, "max_rss_kb": 11},
            ),
        }
        processes = []
        self.addCleanup(self._ensure_reaped, processes)
        result = suite_runner.run_parallel(
            (_MODULE_A, _MODULE_B),
            2,
            None,
            io.StringIO(),
            worker_factory=_document_factory(documents, processes),
        )
        self.assertEqual(result["outcome"], "passed")
        self.assertEqual(
            result["resource"],
            {"user_ms": 13, "system_ms": 24, "max_rss_kb": 11},
        )

    def test_stop_worker_escalates_to_kill_and_reaps(self) -> None:
        process = subprocess.Popen(
            (
                sys.executable,
                "-c",
                "import signal, time\n"
                "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                "print('ready', flush=True)\n"
                "time.sleep(60)\n",
            ),
            stdout=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(self._ensure_reaped, [process])
        self.assertEqual(process.stdout.readline().strip(), "ready")
        with mock.patch.object(
            suite_runner, "WORKER_STOP_GRACE_SECONDS", 0.05
        ):
            suite_runner.stop_worker(process)
        self.assertIsNotNone(process.poll())
        process.stdout.close()

    def test_keyboard_interrupt_terminates_and_reaps_active_worker(self) -> None:
        processes = []

        class InterruptingProcess:
            def __init__(self, process):
                self._process = process
                self._interrupt = True

            def poll(self):
                if self._interrupt:
                    self._interrupt = False
                    raise KeyboardInterrupt
                return self._process.poll()

            def __getattr__(self, name):
                return getattr(self._process, name)

        def factory(command, **kwargs):
            process = subprocess.Popen(
                (sys.executable, "-c", "import time; time.sleep(60)"),
                **kwargs,
            )
            processes.append(process)
            return InterruptingProcess(process)

        self.addCleanup(self._ensure_reaped, processes)
        with self.assertRaises(KeyboardInterrupt):
            suite_runner.run_parallel(
                (_TEST_A,),
                2,
                None,
                io.StringIO(),
                worker_factory=factory,
            )
        self.assertTrue(all(process.poll() is not None for process in processes))

    def test_default_main_path_remains_serial(self) -> None:
        serial_result = {"outcome": "passed"}
        outer_receipts = {
            "AWA_TEST_RECEIPT": "/outer/campaign-receipt.json",
            "AWA_TEST_PRIOR_RECEIPT": "/outer/prior-receipt.json",
        }
        with mock.patch.dict(
            os.environ, outer_receipts
        ), _isolated_main_environment(), mock.patch.object(
            suite_runner, "run_serial", return_value=serial_result
        ) as serial, mock.patch.object(
            suite_runner, "run_parallel"
        ) as parallel:
            self.assertEqual(suite_runner.main(("--", _TEST_A)), 0)
        serial.assert_called_once()
        parallel.assert_not_called()

    def test_parallel_cli_writes_valid_jobs_two_receipt(self) -> None:
        identity = {"head": "a" * 40, "clean": True}
        with _isolated_main_environment(), mock.patch.object(
            suite_runner, "source_identity", return_value=identity
        ), mock.patch.object(
            suite_runner, "runner_digest", return_value="b" * 64
        ):
            with tempfile.TemporaryDirectory(
                prefix="awa-parallel-receipt."
            ) as temporary:
                target = Path(temporary) / "receipt.json"
                result = suite_runner.main(
                    (
                        "--jobs",
                        "2",
                        "--json-out",
                        str(target),
                        "--lane",
                        "focused",
                        "--",
                        _TEST_A,
                        _TEST_B,
                    )
                )
                self.assertEqual(result, 0)
                receipt = json.loads(
                    target.read_text(encoding="utf-8")
                )
        verification_contract.validate_receipt(receipt)
        self.assertEqual(receipt["jobs"], 2)
        self.assertEqual(receipt["test_count"], 2)
        self.assertIn("--jobs", receipt["context"]["command"])

    def test_parallel_cli_loads_validated_prior_receipt(self) -> None:
        prior = _prior_receipt()
        parallel_result = {"outcome": "passed"}
        with tempfile.TemporaryDirectory(
            prefix="awa-parallel-prior."
        ) as temporary:
            target = Path(temporary) / "prior.json"
            target.write_text(json.dumps(prior), encoding="utf-8")
            with _isolated_main_environment(
                AWA_TEST_PRIOR_RECEIPT=str(target)
            ), mock.patch.object(
                suite_runner,
                "run_parallel",
                return_value=parallel_result,
            ) as parallel:
                self.assertEqual(
                    suite_runner.main(
                        ("--jobs", "2", "--", _TEST_A, _TEST_B)
                    ),
                    0,
                )
        self.assertEqual(parallel.call_args.args[2], prior)

    def test_parallel_cli_rejects_malformed_prior_before_worker_launch(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="awa-parallel-prior."
        ) as temporary:
            target = Path(temporary) / "prior.json"
            target.write_text("not-json", encoding="utf-8")
            stderr = io.StringIO()
            with _isolated_main_environment(
                AWA_TEST_PRIOR_RECEIPT=str(target)
            ), mock.patch.object(
                suite_runner, "run_parallel"
            ) as parallel, mock.patch.object(
                suite_runner.sys, "stderr", stderr
            ):
                self.assertEqual(
                    suite_runner.main(
                        ("--jobs", "2", "--", _TEST_A, _TEST_B)
                    ),
                    2,
                )
        parallel.assert_not_called()
        self.assertIn("prior receipt is malformed JSON", stderr.getvalue())

    def test_completed_peer_is_reaped_when_another_worker_times_out(self) -> None:
        ids_b = suite_runner.discover_test_ids((_MODULE_B,))
        processes = []

        def factory(command, **kwargs):
            module = command[command.index("--worker-module") + 1]
            output = Path(command[command.index("--worker-json") + 1])
            if module == _MODULE_A:
                replacement = (
                    sys.executable,
                    "-c",
                    "import time; time.sleep(60)",
                )
            else:
                replacement = _write_process(
                    output, json.dumps(worker_doc(_MODULE_B, ids_b))
                )
            process = subprocess.Popen(replacement, **kwargs)
            processes.append(process)
            return process

        self.addCleanup(self._ensure_reaped, processes)
        result = suite_runner.run_parallel(
            (_MODULE_A, _MODULE_B),
            2,
            None,
            io.StringIO(),
            worker_factory=factory,
            worker_timeout_s=0.2,
        )
        self.assertEqual(result["outcome"], "error")
        self.assertEqual(len(processes), 2)
        self.assertTrue(all(process.poll() is not None for process in processes))

    def test_slow_completed_output_cannot_delay_sibling_timeout_cleanup(self) -> None:
        processes = {}
        document = worker_doc(_MODULE_A, (_TEST_A,))

        def factory(command, **kwargs):
            module = command[command.index("--worker-module") + 1]
            output = Path(command[command.index("--worker-json") + 1])
            replacement = (
                _write_process(output, json.dumps(document))
                if module == _MODULE_A
                else (sys.executable, "-c", "import time; time.sleep(60)")
            )
            process = subprocess.Popen(replacement, **kwargs)
            processes[module] = process
            return process

        self.addCleanup(
            lambda: self._ensure_reaped(list(processes.values()))
        )
        original_emit = suite_runner._emit_worker_log
        sibling_state_at_emit = []

        def slow_emit(state, stream):
            if state.module == _MODULE_A:
                sibling_state_at_emit.append(processes[_MODULE_B].poll())
                time.sleep(0.4)
            original_emit(state, stream)

        with mock.patch.object(
            suite_runner, "_emit_worker_log", side_effect=slow_emit
        ):
            result = suite_runner.run_parallel(
                (_TEST_A, _TEST_B),
                2,
                None,
                io.StringIO(),
                worker_factory=factory,
                worker_timeout_s=0.3,
            )
        self._ensure_reaped(list(processes.values()))
        self.assertEqual(result["outcome"], "error")
        self.assertIn("timed out", result["runner_error"])
        self.assertEqual(len(sibling_state_at_emit), 1)
        self.assertIsNotNone(sibling_state_at_emit[0])

    def test_already_complete_worker_is_not_late_at_first_observation(self) -> None:
        document = worker_doc(_MODULE_A, (_TEST_A,))
        processes = []

        def completed_factory(command, **kwargs):
            output = Path(command[command.index("--worker-json") + 1])
            process = subprocess.Popen(
                _write_process(output, json.dumps(document)),
                **kwargs,
            )
            processes.append(process)
            process.wait(timeout=2)
            time.sleep(0.03)
            return process

        self.addCleanup(self._ensure_reaped, processes)
        result = suite_runner.run_parallel(
            (_TEST_A,),
            2,
            None,
            io.StringIO(),
            worker_factory=completed_factory,
            worker_timeout_s=0.01,
        )
        self.assertEqual(result["outcome"], "passed")

    def test_parallel_failfast_refuses_before_starting_worker(self) -> None:
        starts = []
        processes = []

        def factory(command, **kwargs):
            starts.append(tuple(command))
            process = subprocess.Popen(command, **kwargs)
            processes.append(process)
            return process

        self.addCleanup(self._ensure_reaped, processes)
        options = suite_runner.UnittestOptions(
            selectors=(_TEST_A,),
            failfast=True,
        )
        with self.assertRaisesRegex(ValueError, "--jobs 1"):
            suite_runner.run_parallel(
                (_TEST_A,),
                2,
                None,
                io.StringIO(),
                worker_factory=factory,
                options=options,
            )
        self.assertEqual(starts, [])
        result = suite_runner.run_parallel(
            (_TEST_A,),
            1,
            None,
            io.StringIO(),
            worker_factory=factory,
            options=options,
        )
        self.assertEqual(result["outcome"], "passed")
        self.assertEqual(len(starts), 1)
        self.assertTrue(all(process.poll() is not None for process in processes))

    def test_cli_parallel_failfast_refuses_and_jobs_one_remains_serial(self) -> None:
        stderr = io.StringIO()
        with _isolated_main_environment(), mock.patch.object(
            suite_runner, "_launch_worker"
        ) as launch, mock.patch.object(suite_runner.sys, "stderr", stderr):
            result = suite_runner.main(
                ("--jobs", "2", "--failfast", "--", _TEST_A)
            )
        self.assertEqual(result, 2)
        self.assertIn("--jobs 1", stderr.getvalue())
        launch.assert_not_called()

        serial_result = {"outcome": "passed"}
        with _isolated_main_environment(), mock.patch.object(
            suite_runner, "run_serial", return_value=serial_result
        ) as serial, mock.patch.object(suite_runner, "run_parallel") as parallel:
            self.assertEqual(
                suite_runner.main(
                    ("--jobs", "1", "--failfast", "--", _TEST_A)
                ),
                0,
            )
        self.assertTrue(serial.call_args.kwargs["options"].failfast)
        parallel.assert_not_called()


if __name__ == "__main__":
    unittest.main()
