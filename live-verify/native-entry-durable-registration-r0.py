#!/usr/bin/env python3
"""Exact-head disposable-only R0 harness for ADR 0025 Body C.

`--check` validates harness packaging and performs no install/protocol write.
`--run` is intentionally reserved for the separately authorized post-merge
R0 execution.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CUTS = [f"C{value}" for value in range(8)]
SCHEMA = "awa-registration-r0-harness/v1"


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
        "cuts": CUTS,
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
    with tempfile.TemporaryDirectory(prefix="awa-r0.") as raw:
        home = Path(raw).resolve()
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(home),
            "TMPDIR": str(home / "tmp"),
            "XDG_DATA_HOME": str(home / ".local/share"),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_STATE_HOME": str(home / ".local/state"),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        (home / "tmp").mkdir(mode=0o700)
        commands = (
            [
                sys.executable,
                "-m",
                "unittest",
                "-v",
                "engine.tests.test_registration_installer_c",
                "engine.tests.test_registration_hook_runtime_c",
                "engine.tests.test_registration_host_c",
                "engine.tests.test_registration_receiver_c",
                "engine.tests.test_registration_projection_c",
                "engine.tests.test_registration_independence_c",
                "engine.tests.test_hook_owner_v4_matrix",
            ],
            ["bash", "./install.sh"],
            ["bash", "./install.sh"],
            ["bash", "./install.sh", "--repair"],
            ["bash", "./install.sh", "--doctor"],
            ["bash", "./install.sh", "--uninstall"],
        )
        evidence = []
        for command in commands:
            result = subprocess.run(
                command,
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=900,
            )
            evidence.append(
                {"command": command, "returncode": result.returncode}
            )
            if result.returncode != 0:
                return _emit(
                    {
                        "schema": SCHEMA,
                        "executed": True,
                        "predeployment_evidence": "absent",
                        "rollout_stage": "NONE",
                        "cuts": CUTS,
                        "exact_head": head,
                        "evidence": evidence,
                        "error": "R0 disposable fixture failed",
                        "live_state_changed": False,
                    },
                    1,
                )
    return _emit(
        {
            "schema": SCHEMA,
            "executed": True,
            "predeployment_evidence": "R0",
            "rollout_stage": "NONE",
            "cuts": CUTS,
            "exact_head": head,
            "evidence": evidence,
            "live_state_changed": False,
        }
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
