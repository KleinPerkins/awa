"""Measured stdlib unittest runner for AWA.

The direct internal CLI defaults to serial; the ordinary ``run-tests.sh``
entrypoint supplies the owner-approved two-worker default. Module workers use
isolated Python processes, and every receipt remains descriptive evidence only.
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import math
import os
import platform
import re
import resource
import shlex
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence, TextIO, Tuple

from . import verification_contract


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_DIGEST_PATHS = (
    "engine/tests/run-tests.sh",
    "engine/tests/suite_runner.py",
    "engine/tests/verification_contract.py",
)
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MODULE_NAME = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$"
)
_PRIOR_RECEIPT_ENV = "AWA_TEST_PRIOR_RECEIPT"
_WORKER_SELECTION_ENV = "AWA_TEST_WORKER_SELECTION"
_WORKER_SELECTION_SCHEMA = "awa-test-worker-selection/v1"
_WORKER_POLL_SECONDS = 0.01
WORKER_STOP_GRACE_SECONDS = 5.0


class RunnerError(RuntimeError):
    """A module worker failed or returned ambiguous evidence."""


@dataclasses.dataclass(frozen=True)
class UnittestOptions:
    selectors: Tuple[str, ...] = ()
    verbosity: int = 1
    failfast: bool = False
    buffer: bool = False
    catch: bool = False
    name_patterns: Tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class RunnerArguments:
    list_ids: bool
    json_out: Optional[Path]
    jobs: int
    selectors_env: Optional[str]
    lane: Optional[str]
    unittest_args: Tuple[str, ...]
    worker_module: Optional[str] = None
    worker_json: Optional[Path] = None
    help: bool = False


@dataclasses.dataclass
class _WorkerState:
    module: str
    expected_ids: Tuple[str, ...]
    process: subprocess.Popen
    output_path: Path
    log_path: Path
    deadline: float


def validate_jobs(value: int) -> int:
    if type(value) is not int or value not in (1, 2, 4):
        raise ValueError("--jobs must be one of 1, 2, or 4")
    return value


def _select_pattern(pattern: str) -> str:
    if not pattern:
        raise ValueError("-k requires a non-empty pattern")
    return pattern if "*" in pattern else f"*{pattern}*"


def _parse_unittest_args(args: Sequence[str]) -> UnittestOptions:
    selectors = []
    patterns = []
    verbosity = 1
    failfast = False
    buffer = False
    catch = False
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in ("-v", "--verbose"):
            verbosity = 2
        elif arg in ("-q", "--quiet"):
            verbosity = 0
        elif arg in ("-f", "--failfast"):
            failfast = True
        elif arg in ("-b", "--buffer"):
            buffer = True
        elif arg in ("-c", "--catch"):
            catch = True
        elif arg == "-k":
            index += 1
            if index >= len(args):
                raise ValueError("-k requires a pattern")
            patterns.append(_select_pattern(args[index]))
        elif arg.startswith("-k="):
            patterns.append(_select_pattern(arg.split("=", 1)[1]))
        elif arg.startswith("-"):
            raise ValueError(f"unsupported unittest argument: {arg}")
        elif not arg:
            raise ValueError("test selectors must not be empty")
        else:
            selectors.append(arg)
        index += 1
    return UnittestOptions(
        selectors=tuple(selectors),
        verbosity=verbosity,
        failfast=failfast,
        buffer=buffer,
        catch=catch,
        name_patterns=tuple(patterns),
    )


def _loader(name_patterns: Sequence[str] = ()) -> unittest.TestLoader:
    loader = unittest.TestLoader()
    if name_patterns:
        loader.testNamePatterns = list(name_patterns)
    return loader


def _load_suite(
    selectors: Sequence[str] = (),
    name_patterns: Sequence[str] = (),
) -> unittest.TestSuite:
    loader = _loader(name_patterns)
    if selectors:
        return loader.loadTestsFromNames(tuple(selectors))
    return loader.discover(
        str(REPO_ROOT / "engine" / "tests"),
        pattern="test_*.py",
        top_level_dir=str(REPO_ROOT),
    )


def iter_cases(suite: Iterable) -> Iterable[unittest.TestCase]:
    """Yield every leaf TestCase from unittest's nested suite structure."""

    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from iter_cases(item)
        else:
            yield item


def discover_test_ids(
    selectors: Sequence[str] = (),
    name_patterns: Sequence[str] = (),
) -> Tuple[str, ...]:
    suite = _load_suite(selectors, name_patterns)
    return tuple(sorted({case.id() for case in iter_cases(suite)}))


def inventory_from_unittest_args(args: Sequence[str]) -> Tuple[str, ...]:
    options = _parse_unittest_args(tuple(args))
    return discover_test_ids(options.selectors, options.name_patterns)


def _module_from_test_id(test_id: str) -> str:
    if not isinstance(test_id, str) or not test_id:
        raise RunnerError("test id must be a non-empty string")
    parts = test_id.rsplit(".", 2)
    if len(parts) != 3 or not _MODULE_NAME.fullmatch(parts[0]):
        raise RunnerError(f"cannot determine module for test id: {test_id!r}")
    return parts[0]


def group_by_module(test_ids: Sequence[str]) -> dict:
    """Group exact test IDs into deterministic module work units."""

    grouped = {}
    seen = set()
    for test_id in sorted(test_ids):
        if test_id in seen:
            raise RunnerError(f"duplicate test id: {test_id}")
        seen.add(test_id)
        module = _module_from_test_id(test_id)
        grouped.setdefault(module, []).append(test_id)
    return {
        module: tuple(grouped[module])
        for module in sorted(grouped)
    }


def schedule_modules(
    modules: Sequence[str],
    prior_ms: Mapping[str, int],
) -> Tuple[str, ...]:
    """Schedule longest prior module first, breaking ties by module name."""

    unique = tuple(modules)
    if len(unique) != len(set(unique)):
        raise RunnerError("module schedule contains a duplicate module")

    def duration(module: str) -> int:
        value = prior_ms.get(module, 0)
        if type(value) is not int or value < 0:
            raise ValueError("prior module durations must be non-negative integers")
        return value

    return tuple(sorted(unique, key=lambda name: (-duration(name), name)))


def _inventory_sha256(test_ids: Sequence[str]) -> str:
    return hashlib.sha256("\n".join(tuple(test_ids)).encode("utf-8")).hexdigest()


def worker_command(module: str, output: Path) -> Tuple[str, ...]:
    return (
        sys.executable,
        "-B",
        "-m",
        "engine.tests.suite_runner",
        "--worker-module",
        module,
        "--worker-json",
        str(output),
    )


class TimingResult(unittest.TextTestResult):
    """Text result with one stable record and visible timer per started test."""

    _OUTCOME_PRIORITY = {
        "passed": 0,
        "expected_failure": 0,
        "skipped": 1,
        "failure": 2,
        "unexpected_success": 2,
        "error": 3,
    }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.records = []
        self._started = {}
        self._outcomes = {}
        self._skip_reasons = {}
        self._recorded_unstarted = set()

    @staticmethod
    def _test_id(test: unittest.TestCase) -> str:
        try:
            return test.id()
        except AttributeError:
            return str(test)

    @staticmethod
    def _module(test: unittest.TestCase) -> str:
        module = getattr(test.__class__, "__module__", "")
        return module or "unknown"

    def startTest(self, test: unittest.TestCase) -> None:
        super().startTest(test)
        test_id = self._test_id(test)
        self._started[test_id] = time.monotonic()
        self.stream.writeln(f"START {test_id}")

    def _set_outcome(
        self,
        test: unittest.TestCase,
        outcome: str,
        skip_reason: Optional[str] = None,
    ) -> None:
        test_id = self._test_id(test)
        previous = self._outcomes.get(test_id)
        if previous is None or (
            self._OUTCOME_PRIORITY[outcome] > self._OUTCOME_PRIORITY[previous]
        ):
            self._outcomes[test_id] = outcome
        if outcome == "skipped":
            self._skip_reasons[test_id] = skip_reason or ""

    def _record_unstarted(self, test: unittest.TestCase, outcome: str) -> None:
        test_id = self._test_id(test)
        if test_id in self._started or test_id in self._recorded_unstarted:
            return
        self.records.append(
            {
                "test_id": test_id,
                "module": self._module(test),
                "outcome": outcome,
                "skip_reason": (
                    self._skip_reasons.get(test_id) if outcome == "skipped" else None
                ),
                "elapsed_ms": 0,
            }
        )
        self._recorded_unstarted.add(test_id)

    def addSuccess(self, test: unittest.TestCase) -> None:
        self._set_outcome(test, "passed")
        super().addSuccess(test)

    def addFailure(self, test: unittest.TestCase, err) -> None:
        self._set_outcome(test, "failure")
        super().addFailure(test, err)
        self._record_unstarted(test, "failure")

    def addError(self, test: unittest.TestCase, err) -> None:
        self._set_outcome(test, "error")
        super().addError(test, err)
        self._record_unstarted(test, "error")

    def addSkip(self, test: unittest.TestCase, reason: str) -> None:
        self._set_outcome(test, "skipped", reason)
        super().addSkip(test, reason)
        self._record_unstarted(test, "skipped")

    def addExpectedFailure(self, test: unittest.TestCase, err) -> None:
        self._set_outcome(test, "expected_failure")
        super().addExpectedFailure(test, err)

    def addUnexpectedSuccess(self, test: unittest.TestCase) -> None:
        self._set_outcome(test, "unexpected_success")
        super().addUnexpectedSuccess(test)

    def addSubTest(self, test: unittest.TestCase, subtest, err) -> None:
        if err is not None:
            outcome = (
                "failure"
                if issubclass(err[0], test.failureException)
                else "error"
            )
            self._set_outcome(test, outcome)
        super().addSubTest(test, subtest, err)

    def stopTest(self, test: unittest.TestCase) -> None:
        test_id = self._test_id(test)
        started = self._started.pop(test_id, time.monotonic())
        elapsed = max(0.0, time.monotonic() - started)
        outcome = self._outcomes.pop(test_id, "passed")
        record = {
            "test_id": test_id,
            "module": self._module(test),
            "outcome": outcome,
            "skip_reason": (
                self._skip_reasons.pop(test_id, "") if outcome == "skipped" else None
            ),
            "elapsed_ms": int(round(elapsed * 1000)),
        }
        self.records.append(record)
        self.stream.writeln(f"[{elapsed:.1f}s] END {test_id}")
        super().stopTest(test)


def _normalized_rss_kb(value: float) -> int:
    rss = max(0, int(value))
    return rss // 1024 if sys.platform == "darwin" else rss


def _usage_snapshot() -> dict:
    own = resource.getrusage(resource.RUSAGE_SELF)
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    return {
        "user": own.ru_utime + children.ru_utime,
        "system": own.ru_stime + children.ru_stime,
        "max_rss_kb": max(
            _normalized_rss_kb(own.ru_maxrss),
            _normalized_rss_kb(children.ru_maxrss),
        ),
    }


def _usage_delta(before: Mapping[str, object], after: Mapping[str, object]) -> dict:
    return {
        "user_ms": max(0, int(round((after["user"] - before["user"]) * 1000))),
        "system_ms": max(
            0, int(round((after["system"] - before["system"]) * 1000))
        ),
        "max_rss_kb": int(after["max_rss_kb"]),
    }


def _run_outcome(counts: Mapping[str, int]) -> str:
    if counts["error"]:
        return "error"
    if counts["failure"] or counts["unexpected_success"]:
        return "failure"
    return "passed"


def summarize_timings(records: Sequence[Mapping[str, object]], limit: int = 20) -> dict:
    if type(limit) is not int or limit <= 0:
        raise ValueError("timing summary limit must be a positive integer")
    modules = {}
    for record in records:
        module = str(record["module"])
        current = modules.setdefault(module, {"elapsed_ms": 0, "test_count": 0})
        current["elapsed_ms"] += int(record["elapsed_ms"])
        current["test_count"] += 1
    module_rows = [
        {
            "module": module,
            "elapsed_ms": values["elapsed_ms"],
            "test_count": values["test_count"],
        }
        for module, values in modules.items()
    ]
    module_rows.sort(key=lambda item: (-item["elapsed_ms"], item["module"]))
    slowest = sorted(
        (dict(record) for record in records),
        key=lambda item: (-int(item["elapsed_ms"]), str(item["test_id"])),
    )
    return {
        "modules": module_rows[:limit],
        "slowest_tests": slowest[:limit],
    }


def _write_timing_summary(summary: Mapping[str, object], stream: TextIO) -> None:
    stream.write("\nSLOWEST TESTS\n")
    for record in summary["slowest_tests"]:
        stream.write(f"{record['elapsed_ms']:>8}ms  {record['test_id']}\n")
    stream.write("SLOWEST MODULES\n")
    for module in summary["modules"]:
        stream.write(
            f"{module['elapsed_ms']:>8}ms  {module['module']} "
            f"({module['test_count']} tests)\n"
        )
    flush = getattr(stream, "flush", None)
    if flush is not None:
        flush()


def run_serial(
    selectors: Sequence[str],
    stream: TextIO,
    *,
    options: Optional[UnittestOptions] = None,
) -> dict:
    options = options or UnittestOptions(selectors=tuple(selectors))
    if tuple(selectors) != options.selectors:
        raise ValueError("selectors and unittest options disagree")
    suite = _load_suite(options.selectors, options.name_patterns)
    inventory = tuple(sorted({case.id() for case in iter_cases(suite)}))
    before_usage = _usage_snapshot()
    started = time.monotonic()
    runner = unittest.TextTestRunner(
        stream=stream,
        verbosity=options.verbosity,
        failfast=options.failfast,
        buffer=options.buffer,
        resultclass=TimingResult,
    )
    if options.catch:
        unittest.installHandler()
    result = runner.run(suite)
    elapsed_ms = int(round(max(0.0, time.monotonic() - started) * 1000))
    resource_usage = _usage_delta(before_usage, _usage_snapshot())
    records = sorted(result.records, key=lambda item: item["test_id"])
    counts = {name: 0 for name in verification_contract.OUTCOMES}
    for record in records:
        counts[record["outcome"]] += 1
    outcome = _run_outcome(counts)
    run = {"outcome": outcome, "elapsed_ms": elapsed_ms, "counts": counts}
    summary = summarize_timings(records)
    _write_timing_summary(summary, stream)
    outcomes = {
        record["test_id"]: {
            "module": record["module"],
            "outcome": record["outcome"],
            "skip_reason": record["skip_reason"],
        }
        for record in records
    }
    return {
        "outcome": outcome,
        "inventory": inventory,
        "outcomes": outcomes,
        "records": tuple(records),
        "run": run,
        "summary": summary,
        "resource": resource_usage,
    }


def _prior_module_durations(
    prior_receipt: Optional[Mapping[str, object]],
) -> dict:
    if prior_receipt is None:
        return {}
    verification_contract.validate_receipt(prior_receipt)
    durations = {}
    for record in prior_receipt["records"]:
        module = record["module"]
        durations[module] = durations.get(module, 0) + record["elapsed_ms"]
    return durations


def worker_timeout_seconds(
    module: str,
    prior_ms: Mapping[str, int],
    override: Optional[float],
) -> float:
    if override is not None:
        value = float(override)
        if not math.isfinite(value):
            raise ValueError("worker timeout must be finite")
        return max(0.01, min(value, 1800.0))
    prior = prior_ms.get(module, 0)
    if type(prior) is not int or prior < 0:
        raise ValueError("prior module durations must be non-negative integers")
    prior_s = prior / 1000.0
    return float(max(300, min(int(prior_s * 4) or 300, 1800)))


def _reap_until(
    processes: Sequence[subprocess.Popen],
    deadline: float,
) -> list:
    remaining = list(processes)
    while remaining:
        pending = []
        for process in remaining:
            if process.poll() is None:
                pending.append(process)
            else:
                process.wait()
        if not pending:
            return []
        if time.monotonic() >= deadline:
            return pending
        time.sleep(_WORKER_POLL_SECONDS)
        remaining = pending
    return []


def _stop_processes(processes: Sequence[subprocess.Popen]) -> None:
    running = []
    for process in processes:
        if process.poll() is None:
            running.append(process)
        else:
            process.wait()
    if not running:
        return
    for process in running:
        try:
            process.terminate()
        except OSError:
            pass
    grace = max(0.01, float(WORKER_STOP_GRACE_SECONDS))
    running = _reap_until(running, time.monotonic() + grace)
    if not running:
        return
    for process in running:
        try:
            process.kill()
        except OSError:
            pass
    running = _reap_until(running, time.monotonic() + grace)
    if running:
        raise RunnerError("worker could not be killed and reaped")


def stop_worker(process: subprocess.Popen) -> None:
    """Terminate, bounded-kill, and reap one worker process."""

    _stop_processes((process,))


def _read_bounded_json(path: Path, maximum: int, label: str) -> object:
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise RunnerError(f"{label} is missing") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise RunnerError(f"{label} must be a regular file")
    if metadata.st_size <= 0:
        raise RunnerError(f"{label} is empty or partial")
    if metadata.st_size > maximum:
        raise RunnerError(f"{label} exceeds {maximum} bytes")
    try:
        with path.open("rb") as handle:
            payload = handle.read(maximum + 1)
    except OSError as exc:
        raise RunnerError(f"unable to read {label}: {exc}") from exc
    if len(payload) > maximum:
        raise RunnerError(f"{label} exceeds {maximum} bytes")

    def closed_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise RunnerError(f"{label} contains a duplicate JSON key")
            result[key] = value
        return result

    try:
        return json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=closed_object,
        )
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise RunnerError(f"{label} is malformed JSON") from exc


def _worker_selection_document(
    module: str,
    test_ids: Sequence[str],
    options: UnittestOptions,
) -> dict:
    return {
        "schema": _WORKER_SELECTION_SCHEMA,
        "module": module,
        "test_ids": list(test_ids),
        "verbosity": options.verbosity,
        "failfast": options.failfast,
        "buffer": options.buffer,
        "catch": options.catch,
    }


def _read_worker_selection(module: str) -> UnittestOptions:
    selection_path = os.environ.get(_WORKER_SELECTION_ENV)
    if selection_path is None:
        return UnittestOptions(selectors=(module,))
    value = _read_bounded_json(
        Path(selection_path),
        verification_contract.MAX_WORKER_JSON_BYTES,
        "worker selection",
    )
    expected_keys = {
        "schema",
        "module",
        "test_ids",
        "verbosity",
        "failfast",
        "buffer",
        "catch",
    }
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise RunnerError("worker selection keys mismatch")
    if value["schema"] != _WORKER_SELECTION_SCHEMA:
        raise RunnerError("worker selection schema mismatch")
    if value["module"] != module:
        raise RunnerError("worker selection module mismatch")
    test_ids = value["test_ids"]
    if (
        not isinstance(test_ids, list)
        or any(not isinstance(item, str) or not item for item in test_ids)
        or test_ids != sorted(set(test_ids))
    ):
        raise RunnerError("worker selection test IDs must be sorted and unique")
    grouped = group_by_module(test_ids)
    if set(grouped) != {module}:
        raise RunnerError("worker selection contains another module")
    verbosity = value["verbosity"]
    if type(verbosity) is not int or verbosity not in (0, 1, 2):
        raise RunnerError("worker selection verbosity is invalid")
    for name in ("failfast", "buffer", "catch"):
        if type(value[name]) is not bool:
            raise RunnerError(f"worker selection {name} must be boolean")
    return UnittestOptions(
        selectors=tuple(test_ids),
        verbosity=verbosity,
        failfast=value["failfast"],
        buffer=value["buffer"],
        catch=value["catch"],
    )


def _worker_document(module: str, result: Mapping[str, object]) -> dict:
    document = {
        "schema": verification_contract.WORKER_SCHEMA,
        "module": module,
        "inventory_sha256": _inventory_sha256(result["inventory"]),
        "records": [dict(record) for record in result["records"]],
        "outcome": result["outcome"],
        "elapsed_ms": result["run"]["elapsed_ms"],
        "resource": dict(result["resource"]),
    }
    verification_contract.validate_worker(document)
    return document


def _run_worker(module: str, output: Path, stream: TextIO) -> None:
    if not _MODULE_NAME.fullmatch(module):
        raise RunnerError("worker module must be a dotted Python module name")
    options = _read_worker_selection(module)
    result = run_serial(options.selectors, stream, options=options)
    write_atomic_json(output, _worker_document(module, result))


def _read_worker_document(path: Path) -> dict:
    value = _read_bounded_json(
        path,
        verification_contract.MAX_WORKER_JSON_BYTES,
        "worker result",
    )
    verification_contract.validate_worker(value)
    return dict(value)


def aggregate_worker_records(
    expected_modules: Sequence[str],
    worker_docs: Mapping[str, Mapping[str, object]],
    expected_inventory: Optional[Mapping[str, Sequence[str]]] = None,
    *,
    allow_partial: bool = False,
) -> list:
    expected = tuple(expected_modules)
    if len(expected) != len(set(expected)):
        raise RunnerError("expected modules contain a duplicate module")
    if set(worker_docs) != set(expected):
        raise RunnerError("missing or extra worker result")
    if (
        expected_inventory is not None
        and set(expected_inventory) != set(expected)
    ):
        raise RunnerError("expected worker inventory keys mismatch")
    records = []
    for module in sorted(expected):
        document = worker_docs[module]
        verification_contract.validate_worker(document)
        if document["module"] != module:
            raise RunnerError("worker module mismatch")
        if expected_inventory is not None:
            expected_ids = tuple(expected_inventory[module])
            if document["inventory_sha256"] != _inventory_sha256(expected_ids):
                raise RunnerError(f"worker inventory mismatch: {module}")
            actual_ids = tuple(
                record["test_id"] for record in document["records"]
            )
            unexpected = sorted(set(actual_ids) - set(expected_ids))
            if unexpected:
                raise RunnerError(
                    "worker returned an unselected test id: "
                    + ",".join(unexpected)
                )
            if actual_ids != expected_ids and not allow_partial:
                raise RunnerError(f"worker inventory mismatch: {module}")
        records.extend(dict(record) for record in document["records"])
    seen = set()
    duplicates = set()
    for record in records:
        test_id = record["test_id"]
        if test_id in seen:
            duplicates.add(test_id)
        seen.add(test_id)
    if duplicates:
        raise RunnerError(
            "duplicate test id: " + ",".join(sorted(duplicates))
        )
    return sorted(records, key=lambda item: item["test_id"])


def _emit_worker_log(state: _WorkerState, stream: TextIO) -> None:
    try:
        with state.log_path.open(
            "r", encoding="utf-8", errors="replace"
        ) as handle:
            first = True
            for line in handle:
                if first:
                    stream.write(f"\nWORKER {state.module}\n")
                    first = False
                stream.write(line)
    except FileNotFoundError:
        return
    flush = getattr(stream, "flush", None)
    if flush is not None:
        flush()


def _worker_environment(root: Path, selection: Path) -> dict:
    environment = os.environ.copy()
    private_roots = {
        "TMPDIR": root / "tmp",
        "XDG_CONFIG_HOME": root / "config",
        "XDG_STATE_HOME": root / "state",
        "XDG_CACHE_HOME": root / "cache",
        "XDG_DATA_HOME": root / "data",
    }
    for path in private_roots.values():
        path.mkdir(mode=0o700)
        path.chmod(0o700)
    for name, path in private_roots.items():
        environment[name] = str(path)
    environment[_WORKER_SELECTION_ENV] = str(selection)
    environment.pop(_PRIOR_RECEIPT_ENV, None)
    environment.pop("AWA_TEST_RECEIPT", None)
    pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = str(REPO_ROOT) + (
        os.pathsep + pythonpath if pythonpath else ""
    )
    return environment


def _launch_worker(
    module: str,
    expected_ids: Tuple[str, ...],
    index: int,
    root: Path,
    options: UnittestOptions,
    prior_ms: Mapping[str, int],
    worker_timeout_s: Optional[float],
    worker_factory,
) -> _WorkerState:
    worker_root = root / f"worker-{index:04d}"
    worker_root.mkdir(mode=0o700)
    worker_root.chmod(0o700)
    output = worker_root / "result.json"
    log = worker_root / "output.log"
    selection = worker_root / "selection.json"
    write_atomic_json(
        selection,
        _worker_selection_document(module, expected_ids, options),
    )
    environment = _worker_environment(worker_root, selection)
    command = worker_command(module, output)
    timeout = worker_timeout_seconds(module, prior_ms, worker_timeout_s)
    launched_at = time.monotonic()
    process = None
    try:
        with log.open("wb") as log_handle:
            process = worker_factory(
                command,
                cwd=str(REPO_ROOT),
                env=environment,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
            )
        return _WorkerState(
            module=module,
            expected_ids=expected_ids,
            process=process,
            output_path=output,
            log_path=log,
            deadline=launched_at + timeout,
        )
    except BaseException:
        if process is not None:
            stop_worker(process)
        raise


def _worker_resources(
    worker_docs: Mapping[str, Mapping[str, object]],
) -> dict:
    return {
        "user_ms": sum(
            document["resource"]["user_ms"]
            for document in worker_docs.values()
        ),
        "system_ms": sum(
            document["resource"]["system_ms"]
            for document in worker_docs.values()
        ),
        "max_rss_kb": max(
            (
                document["resource"]["max_rss_kb"]
                for document in worker_docs.values()
            ),
            default=0,
        ),
    }


def _parallel_error_result(
    inventory: Tuple[str, ...],
    elapsed_ms: int,
    message: str,
    resource_usage: Mapping[str, int],
    stream: TextIO,
) -> dict:
    stream.write(f"\nWORKER ERROR: {message}\n")
    flush = getattr(stream, "flush", None)
    if flush is not None:
        flush()
    counts = {name: 0 for name in verification_contract.OUTCOMES}
    counts["error"] = 1
    return {
        "outcome": "error",
        "inventory": inventory,
        "outcomes": {},
        "records": (),
        "run": {
            "outcome": "error",
            "elapsed_ms": elapsed_ms,
            "counts": counts,
        },
        "summary": {"modules": [], "slowest_tests": []},
        "resource": dict(resource_usage),
        "runner_error": message,
    }


def _consume_completed_workers(
    states: Sequence[_WorkerState],
    stream: TextIO,
    worker_docs: dict,
) -> None:
    """Emit and validate completed workers only when no sibling is active."""

    for state in states:
        _emit_worker_log(state, stream)
    for state in states:
        returncode = state.process.returncode
        if returncode is not None and returncode < 0:
            raise RunnerError(
                f"worker terminated by signal {-returncode}: {state.module}"
            )
        if returncode != 0:
            raise RunnerError(
                f"worker exited nonzero ({returncode}): {state.module}"
            )
    for state in states:
        worker_docs[state.module] = _read_worker_document(
            state.output_path
        )


def run_parallel(
    selectors: Sequence[str],
    jobs: int,
    prior_receipt: Optional[Mapping[str, object]],
    stream: TextIO,
    worker_factory=None,
    worker_timeout_s: Optional[float] = None,
    *,
    options: Optional[UnittestOptions] = None,
) -> dict:
    """Run each selected unittest module in one isolated Python process."""

    validate_jobs(jobs)
    options = options or UnittestOptions(selectors=tuple(selectors))
    if tuple(selectors) != options.selectors:
        raise ValueError("selectors and unittest options disagree")
    if jobs > 1 and options.failfast:
        raise ValueError(
            "--failfast is serial-only; use --jobs 1 for failfast semantics"
        )
    inventory = discover_test_ids(options.selectors, options.name_patterns)
    grouped = group_by_module(inventory)
    prior_ms = _prior_module_durations(prior_receipt)
    scheduled = schedule_modules(tuple(grouped), prior_ms)
    factory = worker_factory or subprocess.Popen
    started_at = time.monotonic()
    worker_docs = {}
    active = {}
    completed_pending = []
    started_states = []
    result = None

    with tempfile.TemporaryDirectory(prefix="awa-test-workers.") as temporary:
        root = Path(temporary)
        root.chmod(0o700)
        pending = list(scheduled)
        launch_index = 0

        def launch_available() -> None:
            nonlocal launch_index
            while pending and len(active) < jobs:
                module = pending.pop(0)
                state = None
                try:
                    state = _launch_worker(
                        module,
                        grouped[module],
                        launch_index,
                        root,
                        options,
                        prior_ms,
                        worker_timeout_s,
                        factory,
                    )
                    active[module] = state
                except BaseException:
                    if state is not None:
                        stop_worker(state.process)
                    raise
                launch_index += 1
                started_states.append(state)

        try:
            while pending or active or completed_pending:
                if not active:
                    if completed_pending:
                        batch = tuple(completed_pending)
                        completed_pending.clear()
                        _consume_completed_workers(
                            batch, stream, worker_docs
                        )
                    launch_available()
                    if not active:
                        continue

                observed_at = time.monotonic()
                ready = []
                running = []
                for state in active.values():
                    if state.process.poll() is not None:
                        ready.append(state)
                    else:
                        running.append(state)
                expired = [
                    state
                    for state in running
                    if observed_at >= state.deadline
                ]
                for state in ready:
                    state.process.wait()
                    del active[state.module]
                    completed_pending.append(state)
                if expired:
                    raise RunnerError(
                        "worker timed out: "
                        + ",".join(sorted(state.module for state in expired))
                    )
                for state in ready:
                    returncode = state.process.returncode
                    if returncode is not None and returncode < 0:
                        raise RunnerError(
                            f"worker terminated by signal {-returncode}: "
                            f"{state.module}"
                        )
                    if returncode != 0:
                        raise RunnerError(
                            f"worker exited nonzero ({returncode}): "
                            f"{state.module}"
                        )
                if not active:
                    continue
                launch_available()
                if ready:
                    continue
                if active:
                    next_deadline = min(
                        state.deadline for state in active.values()
                    )
                    time.sleep(
                        min(
                            _WORKER_POLL_SECONDS,
                            max(0.0, next_deadline - observed_at),
                        )
                    )

            leftovers = [
                state
                for state in started_states
                if state.process.poll() is None
            ]
            if leftovers:
                raise RunnerError("leftover worker process")
            records = aggregate_worker_records(
                scheduled,
                worker_docs,
                expected_inventory=grouped,
                allow_partial=options.failfast,
            )
            counts = {
                name: 0 for name in verification_contract.OUTCOMES
            }
            for record in records:
                counts[record["outcome"]] += 1
            outcome = _run_outcome(counts)
            elapsed_ms = int(
                round(max(0.0, time.monotonic() - started_at) * 1000)
            )
            summary = summarize_timings(records)
            _write_timing_summary(summary, stream)
            outcomes = {
                record["test_id"]: {
                    "module": record["module"],
                    "outcome": record["outcome"],
                    "skip_reason": record["skip_reason"],
                }
                for record in records
            }
            result = {
                "outcome": outcome,
                "inventory": inventory,
                "outcomes": outcomes,
                "records": tuple(records),
                "run": {
                    "outcome": outcome,
                    "elapsed_ms": elapsed_ms,
                    "counts": counts,
                },
                "summary": summary,
                "resource": _worker_resources(worker_docs),
            }
        except (
            OSError,
            RunnerError,
            ValueError,
            verification_contract.ContractError,
        ) as exc:
            states = list(active.values())
            queued = list(completed_pending)
            cleanup_error = None
            try:
                _stop_processes(
                    tuple(state.process for state in states)
                )
            except RunnerError as stop_exc:
                cleanup_error = stop_exc
            for state in queued + states:
                _emit_worker_log(state, stream)
            active.clear()
            completed_pending.clear()
            message = str(exc)
            if cleanup_error is not None:
                message += f"; cleanup failed: {cleanup_error}"
            elapsed_ms = int(
                round(max(0.0, time.monotonic() - started_at) * 1000)
            )
            result = _parallel_error_result(
                inventory,
                elapsed_ms,
                message,
                _worker_resources(worker_docs),
                stream,
            )
        except BaseException:
            states = list(active.values())
            queued = list(completed_pending)
            cleanup_error = None
            try:
                _stop_processes(
                    tuple(state.process for state in states)
                )
            except BaseException as stop_exc:
                cleanup_error = stop_exc
            finally:
                for state in queued + states:
                    _emit_worker_log(state, stream)
                active.clear()
                completed_pending.clear()
            if cleanup_error is not None:
                try:
                    sys.stderr.write(
                        f"suite-runner: worker cleanup failed: {cleanup_error}\n"
                    )
                except Exception:
                    pass
            raise

    if result is None:
        raise RunnerError("parallel runner produced no result")
    return result


def _git(*args: str, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def source_identity(root: Path = REPO_ROOT) -> dict:
    head = _git("rev-parse", "--verify", "HEAD", cwd=root)
    if head.returncode != 0 or not head.stdout.strip():
        raise RuntimeError("unable to resolve verification source HEAD")
    status = _git(
        "status",
        "--porcelain=v2",
        "--untracked-files=all",
        cwd=root,
    )
    if status.returncode != 0:
        raise RuntimeError("unable to inspect verification source state")
    return {"head": head.stdout.strip(), "clean": not bool(status.stdout)}


def _git_version() -> str:
    process = subprocess.run(
        ["git", "--version"],
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0 or not process.stdout.strip():
        raise RuntimeError("unable to read Git version")
    return process.stdout.strip()


def runner_digest(paths: Sequence[str] = RUNNER_DIGEST_PATHS) -> str:
    digest = hashlib.sha256()
    for relative in sorted(paths):
        path = REPO_ROOT / relative
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def build_receipt(
    before_identity: Mapping[str, object],
    after_identity: Mapping[str, object],
    inventory: Sequence[str],
    records: Sequence[Mapping[str, object]],
    lane: str,
    jobs: int,
    run: Mapping[str, object],
    context: Mapping[str, object],
) -> dict:
    inventory_tuple = tuple(inventory)
    if inventory_tuple != tuple(sorted(set(inventory_tuple))):
        raise verification_contract.ContractError(
            "inventory must be sorted and contain unique test IDs"
        )
    inventory_bytes = "\n".join(inventory_tuple).encode("utf-8")
    stable = (
        before_identity == after_identity
        and before_identity.get("clean") is True
        and after_identity.get("clean") is True
    )
    receipt = {
        "schema": verification_contract.RECEIPT_SCHEMA,
        "head_before": before_identity["head"],
        "head_after": after_identity["head"],
        "source_clean_before": before_identity["clean"],
        "source_clean_after": after_identity["clean"],
        "source_state": "stable" if stable else "unstable",
        "reusable": bool(stable and run["outcome"] == "passed"),
        "authorizes_skip": False,
        "lane": lane,
        "jobs": jobs,
        "python": platform.python_version(),
        "git": _git_version(),
        "runner_sha256": runner_digest(),
        "inventory_sha256": hashlib.sha256(inventory_bytes).hexdigest(),
        "test_count": len(inventory_tuple),
        "records": sorted(
            (dict(record) for record in records),
            key=lambda item: item["test_id"],
        ),
        "run": {
            "outcome": run["outcome"],
            "elapsed_ms": run["elapsed_ms"],
            "counts": dict(run["counts"]),
        },
        "context": {
            "command": list(context["command"]),
            "selectors": list(context["selectors"]),
            "platform": context["platform"],
            "architecture": context["architecture"],
            "logical_cpu_count": context["logical_cpu_count"],
            "load_note": context["load_note"],
            "generated_at_utc": context["generated_at_utc"],
            "resource": dict(context["resource"]),
        },
    }
    verification_contract.validate_receipt(receipt)
    return receipt


def write_atomic_json(path: Path, value: Mapping[str, object]) -> None:
    target = Path(path)
    parent = target.parent
    if not parent.is_dir():
        raise ValueError(f"receipt parent directory does not exist: {parent}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=str(parent),
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temporary), str(target))
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _take_value(args: Sequence[str], index: int, flag: str) -> Tuple[str, int]:
    index += 1
    if index >= len(args):
        raise ValueError(f"{flag} requires a value")
    return args[index], index


def _parse_runner_args(argv: Sequence[str]) -> RunnerArguments:
    list_ids = False
    json_out = None
    jobs = 1
    selectors_env = None
    lane = None
    worker_module = None
    worker_json = None
    unittest_args = []
    help_requested = False
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--":
            unittest_args.extend(argv[index + 1 :])
            break
        if arg in ("-h", "--help"):
            help_requested = True
        elif arg == "--list-ids":
            list_ids = True
        elif arg == "--json-out":
            value, index = _take_value(argv, index, arg)
            json_out = Path(value)
        elif arg.startswith("--json-out="):
            json_out = Path(arg.split("=", 1)[1])
        elif arg == "--jobs":
            value, index = _take_value(argv, index, arg)
            try:
                jobs = int(value)
            except ValueError as exc:
                raise ValueError("--jobs must be an integer") from exc
        elif arg.startswith("--jobs="):
            try:
                jobs = int(arg.split("=", 1)[1])
            except ValueError as exc:
                raise ValueError("--jobs must be an integer") from exc
        elif arg == "--selectors-env":
            selectors_env, index = _take_value(argv, index, arg)
        elif arg.startswith("--selectors-env="):
            selectors_env = arg.split("=", 1)[1]
        elif arg == "--lane":
            lane, index = _take_value(argv, index, arg)
        elif arg.startswith("--lane="):
            lane = arg.split("=", 1)[1]
        elif arg == "--worker-module":
            worker_module, index = _take_value(argv, index, arg)
        elif arg.startswith("--worker-module="):
            worker_module = arg.split("=", 1)[1]
        elif arg == "--worker-json":
            value, index = _take_value(argv, index, arg)
            worker_json = Path(value)
        elif arg.startswith("--worker-json="):
            worker_json = Path(arg.split("=", 1)[1])
        else:
            unittest_args.append(arg)
        index += 1
    return RunnerArguments(
        list_ids=list_ids,
        json_out=json_out,
        jobs=jobs,
        selectors_env=selectors_env,
        lane=lane,
        unittest_args=tuple(unittest_args),
        worker_module=worker_module,
        worker_json=worker_json,
        help=help_requested,
    )


def _usage() -> str:
    return (
        "usage: python3 -m engine.tests.suite_runner "
        "[--list-ids] [--json-out PATH] [--jobs 1|2|4] "
        "[--selectors-env NAME] [--lane LANE] [-- unittest-args]\n"
    )


def _receipt_target(arguments: RunnerArguments) -> Optional[Path]:
    from_environment = os.environ.get("AWA_TEST_RECEIPT")
    if arguments.json_out is not None and from_environment:
        environment_path = Path(from_environment)
        if arguments.json_out != environment_path:
            raise ValueError("--json-out and AWA_TEST_RECEIPT disagree")
    return arguments.json_out or (Path(from_environment) if from_environment else None)


def _prior_receipt_from_environment() -> Optional[dict]:
    raw = os.environ.get(_PRIOR_RECEIPT_ENV)
    if raw is None:
        return None
    if not raw:
        raise ValueError(f"{_PRIOR_RECEIPT_ENV} must be a non-empty path")
    value = _read_bounded_json(
        Path(raw),
        verification_contract.MAX_RECEIPT_JSON_BYTES,
        "prior receipt",
    )
    verification_contract.validate_receipt(value)
    return dict(value)


def _arguments_from_environment(arguments: RunnerArguments) -> Tuple[str, ...]:
    if arguments.selectors_env is None:
        return arguments.unittest_args
    name = arguments.selectors_env
    if not _ENV_NAME.fullmatch(name):
        raise ValueError("--selectors-env requires an environment variable name")
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        raise ValueError(f"{name} must contain at least one test selector")
    if arguments.unittest_args:
        raise ValueError("--selectors-env cannot be combined with direct unittest arguments")
    try:
        return tuple(shlex.split(raw))
    except ValueError as exc:
        raise ValueError(f"{name} contains invalid shell-like quoting") from exc


def invocation_runs_full_inventory(argv: Sequence[str] = ()) -> bool:
    """Return whether one successful invocation executes the full engine inventory."""
    arguments = _parse_runner_args(tuple(argv))
    if (
        arguments.help
        or arguments.list_ids
        or arguments.worker_module is not None
        or arguments.worker_json is not None
    ):
        return False
    validate_jobs(arguments.jobs)
    options = _parse_unittest_args(_arguments_from_environment(arguments))
    return not options.selectors and not options.name_patterns


def _effective_command(options: UnittestOptions, jobs: int) -> list:
    command = ["python3", "-B", "-m", "engine.tests.suite_runner"]
    if jobs != 1:
        command.extend(("--jobs", str(jobs)))
    if options.verbosity == 2:
        command.append("--verbose")
    elif options.verbosity == 0:
        command.append("--quiet")
    if options.failfast:
        command.append("--failfast")
    if options.buffer:
        command.append("--buffer")
    if options.catch:
        command.append("--catch")
    for pattern in options.name_patterns:
        command.extend(("-k", pattern))
    if options.selectors:
        command.append("--")
        command.extend(options.selectors)
    return command


def _context(
    options: UnittestOptions,
    jobs: int,
    resource_usage: Mapping[str, int],
) -> dict:
    load_note = os.environ.get("AWA_TEST_LOAD_NOTE") or "not_provided"
    if len(load_note) > 500 or any(ord(char) < 32 for char in load_note):
        raise ValueError("AWA_TEST_LOAD_NOTE must be at most 500 printable characters")
    return {
        "command": _effective_command(options, jobs),
        "selectors": list(options.selectors),
        "platform": sys.platform or "unknown",
        "architecture": platform.machine() or "unknown",
        "logical_cpu_count": os.cpu_count() or 1,
        "load_note": load_note,
        "generated_at_utc": datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(),
        "resource": dict(resource_usage),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    raw_args = tuple(sys.argv[1:] if argv is None else argv)
    try:
        arguments = _parse_runner_args(raw_args)
        if arguments.help:
            sys.stdout.write(_usage())
            return 0
        validate_jobs(arguments.jobs)
        worker_requested = (
            arguments.worker_module is not None
            or arguments.worker_json is not None
        )
        if worker_requested:
            if (
                arguments.worker_module is None
                or arguments.worker_json is None
            ):
                raise ValueError(
                    "--worker-module and --worker-json must be used together"
                )
            if (
                arguments.list_ids
                or arguments.json_out is not None
                or arguments.selectors_env is not None
                or arguments.lane is not None
                or arguments.unittest_args
                or arguments.jobs != 1
            ):
                raise ValueError(
                    "worker mode cannot be combined with runner options"
                )
            _run_worker(
                arguments.worker_module,
                arguments.worker_json,
                sys.stderr,
            )
            return 0
        unittest_args = _arguments_from_environment(arguments)
        options = _parse_unittest_args(unittest_args)
        if arguments.list_ids:
            if _receipt_target(arguments) is not None:
                raise ValueError("--list-ids cannot write a test receipt")
            for test_id in discover_test_ids(
                options.selectors, options.name_patterns
            ):
                print(test_id)
            return 0
        target = _receipt_target(arguments)
        before = source_identity() if target is not None else None
        if arguments.jobs == 1:
            result = run_serial(
                options.selectors,
                sys.stderr,
                options=options,
            )
        else:
            prior_receipt = _prior_receipt_from_environment()
            result = run_parallel(
                options.selectors,
                arguments.jobs,
                prior_receipt,
                sys.stderr,
                options=options,
            )
        after = source_identity() if target is not None else None
        if "runner_error" in result:
            return 2
        if target is not None:
            lane = arguments.lane or (
                "focused" if options.selectors else "pre-pr"
            )
            receipt = build_receipt(
                before,
                after,
                result["inventory"],
                result["records"],
                lane,
                arguments.jobs,
                result["run"],
                _context(options, arguments.jobs, result["resource"]),
            )
            write_atomic_json(target, receipt)
        return 0 if result["outcome"] == "passed" else 1
    except (
        OSError,
        RuntimeError,
        ValueError,
        verification_contract.ContractError,
    ) as exc:
        sys.stderr.write(f"suite-runner: error: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
