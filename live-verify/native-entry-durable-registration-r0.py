#!/usr/bin/env python3
"""Exact-head disposable-only R0 harness for accepted ADR 0026 Body C.

`--check` validates packaging and reports no R0 evidence. `--run` cannot
self-authorize; the separately gated post-merge driver must supply the exact
signed throwaway authority added at Gate 6.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine import registration_projection  # noqa: E402


SCHEMA = "awa-registration-r0-harness/v2"


def _emit(value: dict, code: int = 0) -> int:
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))
    return code


def _check_payload() -> dict:
    required = (
        ROOT / "contracts/awa-hook-owner.v4.json",
        ROOT / "engine/registration_projection.py",
        ROOT / "engine/registration_hook_runtime.py",
        ROOT / "engine/registration_installer.py",
        ROOT / "engine/registration_host.py",
        ROOT / "engine/registration_receiver.py",
        ROOT / "engine/registration_launcher.py",
        ROOT / "kernel/hooks/awa-registration-admission.sh",
        ROOT / "kernel/hooks/awa-registration-startup.sh",
        ROOT / "kernel/bin/awa-registration-tick.sh",
        ROOT / "kernel/bin/awa-registration-receiver.sh",
        ROOT
        / "live-verify/native-entry-durable-registration-body-c-desktop-uat.sh",
    )
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    return {
        "schema": SCHEMA,
        "executed": False,
        "predeployment_evidence": "absent",
        "rollout_stage": "NONE",
        "cuts": [],
        "barrier_catalog": list(registration_projection.R0_BARRIERS),
        "barrier_catalog_complete": False,
        "process_kill_complete": False,
        "receiver_continuity_complete": False,
        "governed_live_manifest_before_hash": None,
        "governed_live_manifest_after_hash": None,
        "throwaway_target_manifest_hash": None,
        "external_write_observer": "unavailable",
        "external_write_observation_hash": None,
        "cut_evidence_hash": None,
        "claim_scope": "FINITE_GOVERNED_SURFACES_AND_OBSERVED_TARGETS",
        "missing": missing,
        "final_r0_requires_merged_exact_head": True,
        "live_state_changed": False,
    }


def _run(expected_head: str) -> int:
    if not expected_head or len(expected_head) != 40:
        return _emit(
            {
                **_check_payload(),
                "error": "an exact merged --expected-head is required",
            },
            2,
        )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if head != expected_head or status:
        return _emit(
            {
                **_check_payload(),
                "error": "R0 requires the exact clean merged head",
                "observed_head": head,
            },
            2,
        )
    return _emit(
        {
            **_check_payload(),
            "exact_head": head,
            "error": (
                "R0 requires a separately supplied Gate 6 throwaway "
                "authority and detached owner signature"
            ),
        },
        2,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--expected-head", default="")
    args = parser.parse_args(argv)
    if args.check:
        payload = _check_payload()
        return _emit(payload, 0 if not payload["missing"] else 1)
    return _run(args.expected_head)


if __name__ == "__main__":
    raise SystemExit(main())
