"""Measured stdlib unittest runner for AWA.

M1 is intentionally serial.  Receipts are descriptive evidence only and are
machine-validated before they are written.
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import os
import platform
import re
import resource
import shlex
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
    help: bool = False


def validate_jobs(value: int) -> int:
    if type(value) is not int or value != 1:
        raise ValueError("M2 sharding is not enabled; use --jobs 1")
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
        help=help_requested,
    )


def _usage() -> str:
    return (
        "usage: python3 -m engine.tests.suite_runner "
        "[--list-ids] [--json-out PATH] [--jobs 1] "
        "[--selectors-env NAME] [--lane LANE] [-- unittest-args]\n"
    )


def _receipt_target(arguments: RunnerArguments) -> Optional[Path]:
    from_environment = os.environ.get("AWA_TEST_RECEIPT")
    if arguments.json_out is not None and from_environment:
        environment_path = Path(from_environment)
        if arguments.json_out != environment_path:
            raise ValueError("--json-out and AWA_TEST_RECEIPT disagree")
    return arguments.json_out or (Path(from_environment) if from_environment else None)


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


def _effective_command(options: UnittestOptions) -> list:
    command = ["python3", "-B", "-m", "engine.tests.suite_runner"]
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


def _context(options: UnittestOptions, resource_usage: Mapping[str, int]) -> dict:
    load_note = os.environ.get("AWA_TEST_LOAD_NOTE") or "not_provided"
    if len(load_note) > 500 or any(ord(char) < 32 for char in load_note):
        raise ValueError("AWA_TEST_LOAD_NOTE must be at most 500 printable characters")
    return {
        "command": _effective_command(options),
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
        result = run_serial(options.selectors, sys.stderr, options=options)
        after = source_identity() if target is not None else None
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
                _context(options, result["resource"]),
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
