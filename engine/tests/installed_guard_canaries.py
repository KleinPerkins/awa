"""Closed M3-A.2 installed-guard canary and fallback contract.

The ordinary suite may layer source/full coverage with installed canaries only
after a fresh source/install identity check. The complete accepted M3-A
installed manifest remains executable with the explicit full-matrix switch.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Mapping, Optional, Sequence

from .guard_boundary_profile import (
    GUARD_BOUNDARY_CASES,
    _case_manifest_sha256,
    installed_matrix_decision,
    probe_installed_identity,
    run_installed_hook_cases,
)


FULL_INSTALLED_MATRIX_ENV = "AWA_FULL_INSTALLED_GUARD_MATRIX"
FULL_INSTALLED_MATRIX_TARGET = "make verify-guard-installed-full"
REPO_ROOT = Path(__file__).resolve().parents[2]
M3_A_CASE_MANIFEST_SHA256 = (
    "eb4e7662f096cecc6d0a99717d71e1868552596f22abe1db61536e61d4476435"
)

INSTALLED_GUARD_CANARIES = {
    "direct_allow": (
        "engine.tests.test_guard_hook_wrappers.TestBashGuardWrapperParity."
        "test_m3_profile_manifest_matches_source_and_installed_permissions"
    ),
    "direct_deny": (
        "engine.tests.test_guard_hook_wrappers.TestBashGuardWrapperParity."
        "test_m3_profile_manifest_matches_source_and_installed_permissions"
    ),
    "external_allow": (
        "engine.tests.test_hook_owner_modes.TestHookOwnerParity."
        "test_installed_guard_owner_canaries"
    ),
    "external_deny": (
        "engine.tests.test_hook_owner_modes.TestHookOwnerParity."
        "test_installed_guard_owner_canaries"
    ),
    "uncertainty": (
        "engine.tests.test_guard_hook_wrappers.TestBashGuardWrapperParity."
        "test_classifier_unavailable_asks_not_denies"
    ),
    "maintenance": (
        "engine.tests.test_guard_hook_wrappers.TestBashGuardWrapperParity."
        "test_m3_profile_manifest_matches_source_and_installed_permissions"
    ),
    "malformed": (
        "engine.tests.test_guard_hook_wrappers.TestBashGuardWrapperParity."
        "test_unparseable_payload_on_included_primary_asks"
    ),
    "owner_mode": (
        "engine.tests.test_hook_owner_modes.TestHookOwnerParity."
        "test_installed_guard_owner_canaries"
    ),
    "kernel_off": (
        "engine.tests.test_installed_guard_layering."
        "InstalledGuardKernelOffCanary."
        "test_engine_is_unimportable_in_kernel_off_canary"
    ),
}


class LayeringError(RuntimeError):
    """Layered installed coverage is not eligible for this invocation."""


def _fallback_error(detail: str) -> LayeringError:
    return LayeringError(
        "{0}; full installed matrix required: {1}".format(
            detail, FULL_INSTALLED_MATRIX_TARGET
        )
    )


def verify_installed_identity(identity: Mapping[str, str]) -> None:
    """Fail closed unless the complete M3-A identity gate still selects layering."""

    try:
        decision = installed_matrix_decision(
            identity,
            {
                name: True
                for name in (
                    "direct_allow_deny",
                    "external_zero_access",
                    "installed_allow_deny",
                    "kernel_off",
                    "maintenance",
                    "malformed_input",
                    "owner_mode",
                    "source_engine_parity",
                    "uncertainty",
                )
            },
            full_engine_kernel_parity=True,
        )
    except (TypeError, ValueError) as error:
        raise _fallback_error("installed identity is invalid") from error
    if decision != "byte_identity_plus_canaries":
        raise _fallback_error("installed bytes or interpreters differ")


def verify_current_installed_identity() -> None:
    """Install privately and enforce the live source/install identity gate."""

    verify_installed_identity(probe_installed_identity())


def full_installed_matrix_requested(
    env: Optional[Mapping[str, str]] = None,
) -> bool:
    """Return the exact full-fallback selection; reject ambiguous values."""

    source = env if env is not None else os.environ
    value = source.get(FULL_INSTALLED_MATRIX_ENV, "0")
    if value == "1":
        return True
    if value in ("", "0"):
        return False
    raise _fallback_error(
        "{0} must be exactly 0 or 1".format(FULL_INSTALLED_MATRIX_ENV)
    )


def load_m3_boundary_manifest(boundary: str) -> dict:
    """Load the immutable accepted M3-A installed case manifest."""

    if boundary != "installed":
        raise ValueError("only the accepted installed boundary is available")
    digest = _case_manifest_sha256(GUARD_BOUNDARY_CASES)
    if digest != M3_A_CASE_MANIFEST_SHA256:
        raise _fallback_error("accepted M3-A case manifest digest differs")
    return {
        "case_ids": tuple(case.label for case in GUARD_BOUNDARY_CASES),
        "outcomes": {
            case.label: case.expected_permission
            for case in GUARD_BOUNDARY_CASES
        },
        "skips": (),
        "case_manifest_sha256": digest,
    }


def run_installed_matrix(
    env: Optional[Mapping[str, str]] = None,
) -> dict:
    """Execute the complete accepted installed manifest in explicit fallback mode."""

    if not full_installed_matrix_requested(env):
        raise _fallback_error("explicit fallback was not selected")
    accepted = load_m3_boundary_manifest("installed")
    report = run_installed_hook_cases(GUARD_BOUNDARY_CASES)
    if report["case_manifest_sha256"] != accepted["case_manifest_sha256"]:
        raise _fallback_error("full fallback manifest digest differs")
    return {
        "case_ids": tuple(report["case_ids"]),
        "outcomes": dict(report["outcomes"]),
        "skips": (),
        "case_manifest_sha256": report["case_manifest_sha256"],
    }


def prove_canaries_bite() -> dict:
    """Run every registered canary against an isolated wrong-verdict guard."""

    wrong_permissions = {
        "direct_allow": "deny",
        "direct_deny": "allow",
        "external_allow": "deny",
        "external_deny": "allow",
        "uncertainty": "allow",
        "maintenance": "deny",
        "malformed": "allow",
        "owner_mode": "allow",
        "kernel_off": "allow",
    }
    results = {}
    with tempfile.TemporaryDirectory(
        prefix="awa-installed-canary-breaks."
    ) as raw:
        root = Path(raw)
        for category in sorted(INSTALLED_GUARD_CANARIES):
            broken = root / ("broken-" + category + ".sh")
            broken.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' '{\"permission\":\""
                + wrong_permissions[category]
                + "\"}'\n",
                encoding="utf-8",
            )
            broken.chmod(0o700)
            env = dict(os.environ)
            env.update(
                {
                    "AWA_TEST_INSTALLED_GUARD_OVERRIDE": str(broken),
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONPATH": str(REPO_ROOT),
                }
            )
            if category == "kernel_off":
                env["AWA_TEST_KERNEL_OFF_PYTHONPATH"] = str(REPO_ROOT)
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "unittest",
                    INSTALLED_GUARD_CANARIES[category],
                    "-v",
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                env=env,
                timeout=300,
            )
            combined = result.stdout + result.stderr
            if (
                result.returncode == 0
                or "AssertionError" not in combined
                or "FAILED (failures=" not in combined
            ):
                raise LayeringError(
                    "installed canary did not bite cleanly: {0}".format(
                        category
                    )
                )
            results[category] = {
                "test_id": INSTALLED_GUARD_CANARIES[category],
                "wrong_permission": wrong_permissions[category],
                "biting": True,
            }
    return results


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-identity", action="store_true")
    parser.add_argument("--prove-biting", action="store_true")
    args = parser.parse_args(argv)
    if args.verify_identity == args.prove_biting:
        parser.error("select exactly one of --verify-identity or --prove-biting")
    if args.verify_identity:
        verify_current_installed_identity()
        print("installed guard identity: exact; layered canaries eligible")
    else:
        results = prove_canaries_bite()
        for category in sorted(results):
            print("installed guard canary bites: " + category)
    return 0


if __name__ == "__main__":
    sys.exit(main())
