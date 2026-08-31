"""Advisory verification-performance policy.

Warnings describe timing, inventory, or source-boundary process growth.  They
never authorize a skipped check and never replace an authoritative exit status.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Mapping, Optional, Sequence, TextIO

from engine.tests import suite_runner, verification_contract


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASELINE = Path(__file__).with_name("performance-baseline.v1.json")
PROFILE_SOURCE = Path(__file__).with_name("guard_boundary_profile.py")


def _sha256(parts: Sequence[bytes]) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(len(part).to_bytes(8, "big"))
        digest.update(part)
    return digest.hexdigest()


def performance_producer_sha256() -> str:
    """Bind process evidence to both producer and validator contract source."""

    return _sha256(
        (
            PROFILE_SOURCE.read_bytes(),
            Path(verification_contract.__file__).read_bytes(),
        )
    )


def workload_sha256(
    lane: str,
    command: Sequence[str],
    selectors: Sequence[str],
    jobs: int,
) -> str:
    body = json.dumps(
        {
            "lane": lane,
            "command": list(command),
            "selectors": list(selectors),
            "jobs": jobs,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def load_baseline(path: Path = DEFAULT_BASELINE) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    verification_contract.validate_performance_baseline(value)
    return value


def module_durations_from_receipt(receipt: Mapping[str, object]) -> dict[str, int]:
    return suite_runner.module_durations_ms(receipt["records"])


def observation_from_receipt(
    receipt: Mapping[str, object],
    process_measurement: Optional[Mapping[str, object]] = None,
) -> dict:
    verification_contract.validate_receipt(receipt)
    context = receipt["context"]
    run = receipt["run"]
    lane = str(receipt["lane"])
    return {
        "head": receipt["head_after"],
        "inventory_sha256": receipt["inventory_sha256"],
        "python": receipt["python"],
        "git": receipt["git"],
        "lane": lane,
        "jobs": receipt["jobs"],
        "test_count": receipt["test_count"],
        "outcome": run["outcome"],
        "elapsed_ms": run["elapsed_ms"],
        "load_note": context["load_note"],
        "workload_sha256": workload_sha256(
            lane,
            context["command"],
            context["selectors"],
            receipt["jobs"],
        ),
        "module_durations_ms": module_durations_from_receipt(receipt),
        "process_measurement": (
            dict(process_measurement)
            if process_measurement is not None
            else None
        ),
    }


def process_measurement_from_profile(
    profile: Mapping[str, object],
) -> dict:
    verification_contract.validate_guard_boundary_profile(profile)
    if profile["boundary"] != "source":
        raise verification_contract.ContractError(
            "process profile must use the source boundary"
        )
    if profile["counter_scope"] != "PATH-resolved git children only":
        raise verification_contract.ContractError(
            "process profile did not count scoped Git children"
        )
    if profile["passed"] is not True:
        raise verification_contract.ContractError(
            "process profile did not pass"
        )
    source_digest = hashlib.sha256(PROFILE_SOURCE.read_bytes()).hexdigest()
    if profile["producer_sha256"] != source_digest:
        raise verification_contract.ContractError(
            "process profile producer does not match current source"
        )
    return {
        "status": "measured",
        "counter_scope": profile["counter_scope"],
        "producer_sha256": performance_producer_sha256(),
        "case_manifest_sha256": profile["case_manifest_sha256"],
        "git_processes": profile["git_processes"],
    }


def _warning(code: str, message: str, **context: object) -> dict:
    return {
        "severity": "warning",
        "code": code,
        "message": message,
        "context": dict(sorted(context.items())),
    }


def evaluate(
    observation: Mapping[str, object],
    baseline: Mapping[str, object],
    *,
    require_process: bool = False,
) -> tuple[dict, ...]:
    """Return deterministic warnings; findings never change the caller's status."""

    verification_contract.validate_performance_baseline(baseline)
    warnings = []
    required = (
        "head",
        "inventory_sha256",
        "python",
        "git",
        "lane",
        "jobs",
        "test_count",
        "outcome",
    )
    missing = sorted(
        key for key in required
        if observation.get(key) is None
    )
    if missing:
        warnings.append(_warning(
            "context_missing",
            "missing context: " + ",".join(missing),
        ))
    load_note = observation.get("load_note")
    if (
        not isinstance(load_note, str)
        or not load_note.strip()
        or load_note == "not_provided"
    ):
        warnings.append(_warning("load_context_missing", "missing load context"))

    lane_name = observation.get("lane")
    lane = baseline["lanes"].get(lane_name)
    if (
        lane_name in verification_contract.PERFORMANCE_LANES
        and lane["status"] == "accepted"
    ):
        if observation.get("workload_sha256") != lane["workload_sha256"]:
            warnings.append(_warning(
                "timing_not_comparable",
                "fixed workload not matched; timing not measured",
                lane=lane_name,
            ))
        elif (
            type(observation.get("elapsed_ms")) is int
            and observation["elapsed_ms"] > lane["warning_elapsed_ms"]
        ):
            warnings.append(_warning(
                "elapsed_growth",
                "wall time exceeded advisory budget",
                baseline_ms=lane["warning_elapsed_ms"],
                current_ms=observation["elapsed_ms"],
                lane=lane_name,
            ))

    count = observation.get("test_count")
    if type(count) is int and count > baseline["test_count"]:
        warnings.append(_warning(
            "inventory_growth",
            "test inventory grew",
            baseline=baseline["test_count"],
            current=count,
        ))

    process = observation.get("process_measurement")
    expected = baseline["process_measurement"]
    compatible = (
        expected["status"] == "measured"
        and isinstance(process, Mapping)
        and process.get("status") == "measured"
        and process.get("counter_scope") == expected["counter_scope"]
        and process.get("producer_sha256") == expected["producer_sha256"]
        and process.get("case_manifest_sha256")
        == expected["case_manifest_sha256"]
        and type(process.get("git_processes")) is int
    )
    if require_process and not compatible:
        warnings.append(_warning(
            "process_not_measured",
            "scoped Git process count not measured",
        ))
    elif (
        compatible
        and process["git_processes"] * 100
        > expected["git_processes"] * 120
    ):
        warnings.append(_warning(
            "process_growth",
            "scoped Git process count grew",
            baseline=expected["git_processes"],
            current=process["git_processes"],
        ))
    return tuple(warnings)


def _read_json(path: Path) -> object:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    receipt = subparsers.add_parser("evaluate-receipt")
    receipt.add_argument("--receipt", required=True, type=Path)
    receipt.add_argument("--process-profile", type=Path)
    receipt.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    lane = subparsers.add_parser("evaluate-lane")
    lane.add_argument("--lane", required=True, choices=("docs", "pre-pr"))
    lane.add_argument("--elapsed-ms", required=True, type=int)
    lane.add_argument("--receipt", type=Path)
    lane.add_argument("--process-profile", type=Path)
    lane.add_argument("--inventory-sha256")
    lane.add_argument("--test-count", type=int, default=0)
    lane.add_argument("--load-note", default="not_provided")
    lane.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    return parser


def _render(warnings: Sequence[Mapping[str, object]], stdout: TextIO) -> None:
    if not warnings:
        stdout.write("performance advisory: no findings\n")
        return
    for warning in warnings:
        stdout.write(
            f"performance advisory: {warning['message']} "
            f"({warning['code']})\n"
        )


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    try:
        arguments = _parser().parse_args(argv)
        baseline = load_baseline(arguments.baseline)
        if arguments.command == "evaluate-lane":
            lane = baseline["lanes"][arguments.lane]
            process = None
            require_process = arguments.process_profile is not None
            if arguments.process_profile is not None:
                try:
                    process = process_measurement_from_profile(
                        _read_json(arguments.process_profile)
                    )
                except (
                    OSError,
                    ValueError,
                    verification_contract.ContractError,
                ):
                    process = None
            if arguments.receipt is not None:
                current = observation_from_receipt(
                    _read_json(arguments.receipt), process
                )
                current["lane"] = arguments.lane
                current["elapsed_ms"] = arguments.elapsed_ms
            else:
                current = {
                    "head": baseline["head"],
                    "inventory_sha256": (
                        arguments.inventory_sha256
                        or baseline["inventory_sha256"]
                    ),
                    "python": baseline["python"],
                    "git": baseline["git"],
                    "lane": arguments.lane,
                    "jobs": 1,
                    "test_count": arguments.test_count,
                    "outcome": "passed",
                    "elapsed_ms": arguments.elapsed_ms,
                    "load_note": arguments.load_note,
                    "workload_sha256": lane["workload_sha256"],
                    "module_durations_ms": {},
                    "process_measurement": process,
                }
            warnings = evaluate(
                current, baseline, require_process=require_process
            )
        else:
            receipt = _read_json(arguments.receipt)
            process = None
            require_process = arguments.process_profile is not None
            if arguments.process_profile is not None:
                try:
                    process = process_measurement_from_profile(
                        _read_json(arguments.process_profile)
                    )
                except (
                    OSError,
                    ValueError,
                    verification_contract.ContractError,
                ):
                    process = None
            current = observation_from_receipt(receipt, process)
            warnings = evaluate(
                current, baseline, require_process=require_process
            )
        _render(warnings, stdout)
        return 0
    except (
        OSError,
        ValueError,
        verification_contract.ContractError,
    ) as exc:
        stderr.write(f"performance-policy: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
