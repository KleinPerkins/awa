"""Body C startup/tick, installer lifecycle, R0, and Desktop-UAT packaging."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ADMISSION = ROOT / "kernel/hooks/awa-registration-admission.sh"
STARTUP = ROOT / "kernel/hooks/awa-registration-startup.sh"
TICK = ROOT / "kernel/bin/awa-registration-tick.sh"
RECEIVER = ROOT / "kernel/bin/awa-registration-receiver.sh"
ENTRYPOINT = ROOT / "kernel/bin/awa-registration-entrypoint.sh"
R0 = ROOT / "live-verify/native-entry-durable-registration-r0.py"
DESKTOP_UAT = (
    ROOT
    / "live-verify/native-entry-durable-registration-body-c-desktop-uat.sh"
)


class RegistrationPackagingTest(unittest.TestCase):
    def test_shell_and_python_entrypoints_are_present_and_syntax_valid(
        self,
    ) -> None:
        for script in (
            ADMISSION,
            STARTUP,
            TICK,
            RECEIVER,
            DESKTOP_UAT,
        ):
            with self.subTest(script=script.name):
                self.assertTrue(script.is_file())
                self.assertTrue(os.access(script, os.X_OK))
                result = subprocess.run(
                    ["bash", "-n", str(script)],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
        compile_result = subprocess.run(
            [
                "python3",
                "-m",
                "py_compile",
                str(ROOT / "engine/registration_projection.py"),
                str(ROOT / "engine/registration_hook_runtime.py"),
                str(ROOT / "engine/registration_installer.py"),
                str(ROOT / "engine/registration_host.py"),
                str(ROOT / "engine/registration_receiver.py"),
                str(ROOT / "engine/registration_launcher.py"),
                str(R0),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            compile_result.returncode, 0, compile_result.stderr
        )

    def test_all_five_product_routes_are_posix_and_clear_shell_startup(self) -> None:
        for script in (ENTRYPOINT, ADMISSION, RECEIVER, STARTUP, TICK):
            with self.subTest(script=script.name):
                raw = script.read_bytes()
                self.assertTrue(raw.startswith(b"#!/bin/sh\n"))
                self.assertNotIn(b"/usr/bin/env", raw)
                self.assertNotIn(b"#!/bin/bash", raw)
                self.assertIn(b"unset ENV BASH_ENV", raw)
                result = subprocess.run(
                    ["/bin/sh", "-n", str(script)],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_runtime_wrapper_is_quiet_fail_open(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            scratch = Path(raw)
            for original in (ADMISSION, STARTUP):
                copied = scratch / original.name
                shutil.copy2(original, copied)
                copied.chmod(0o700)
                result = subprocess.run(
                    ["bash", str(copied)],
                    input=b'{"hook_event_name":"preToolUse"}',
                    capture_output=True,
                    timeout=5,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, b"")
                self.assertEqual(result.stderr, b"")

    def test_r0_harness_is_check_only_without_explicit_run(self) -> None:
        result = subprocess.run(
            ["python3", str(R0), "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(
            payload["schema"], "awa-registration-r0-harness/v2"
        )
        self.assertEqual(payload["predeployment_evidence"], "absent")
        self.assertEqual(payload["rollout_stage"], "NONE")
        self.assertFalse(payload["executed"])
        self.assertEqual(payload["cuts"], [])
        self.assertFalse(payload["barrier_catalog_complete"])
        self.assertFalse(payload["process_kill_complete"])
        self.assertFalse(payload["receiver_continuity_complete"])
        self.assertEqual(
            set(payload),
            {
                "schema",
                "executed",
                "predeployment_evidence",
                "rollout_stage",
                "cuts",
                "barrier_catalog",
                "barrier_catalog_complete",
                "process_kill_complete",
                "receiver_continuity_complete",
                "governed_live_manifest_before_hash",
                "governed_live_manifest_after_hash",
                "throwaway_target_manifest_hash",
                "external_write_observer",
                "external_write_observation_hash",
                "cut_evidence_hash",
                "claim_scope",
                "missing",
                "final_r0_requires_merged_exact_head",
                "live_state_changed",
            },
        )
        for field in (
            "governed_live_manifest_before_hash",
            "governed_live_manifest_after_hash",
            "throwaway_target_manifest_hash",
            "external_write_observation_hash",
            "cut_evidence_hash",
        ):
            with self.subTest(field=field):
                self.assertIsNone(payload[field])
        self.assertEqual(payload["external_write_observer"], "unavailable")
        self.assertEqual(
            payload["claim_scope"],
            "FINITE_GOVERNED_SURFACES_AND_OBSERVED_TARGETS",
        )
        self.assertEqual(payload["missing"], [])
        self.assertTrue(payload["final_r0_requires_merged_exact_head"])
        self.assertFalse(payload["live_state_changed"])
        self.assertEqual(
            payload["barrier_catalog"],
            [
                "C0.PREFLIGHT",
                "C1.BUNDLE_PUBLISHED",
                "C2.DRAIN_COMMITTED",
                "C2.STAGE_COMMITTED",
                "C2.DIRECT_PROOF",
                "C2.SHADOW_PROOF",
                "C3.POINTER_SWITCHED",
                "C3.POST_SWITCH_PROOF",
                "C3.OLD_ENTRY_DISABLED",
                "C4.ADOPT_COMMITTED",
                "C4.TRANSFER_RECEIVED",
                "C4.TRANSFER_ACTIVATED",
                "C4.MARK_COMMITTED",
                "C4.REACQUIRE_COMMITTED",
                "C5.RECONCILIATION_BATCH",
                "C5.CUSTODY_EMPTY",
                "C6.ADVANCE_COMMITTED",
                "C7.OLD_BUNDLE_REMOVED",
                "C7.RESIDUE_RECONCILED",
            ],
        )

    def test_r0_run_refuses_inertly_without_authority_or_side_effects(self) -> None:
        before = subprocess.run(
            [
                "git",
                "-c",
                "core.quotePath=true",
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout
        environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        result = subprocess.run(
            ["python3", str(R0), "--run"],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            timeout=60,
        )
        after = subprocess.run(
            [
                "git",
                "-c",
                "core.quotePath=true",
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(after, before)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["executed"])
        self.assertEqual(payload["predeployment_evidence"], "absent")
        self.assertEqual(payload["rollout_stage"], "NONE")
        self.assertEqual(payload["cuts"], [])
        self.assertFalse(payload["barrier_catalog_complete"])
        self.assertFalse(payload["process_kill_complete"])
        self.assertFalse(payload["receiver_continuity_complete"])
        self.assertFalse(payload["live_state_changed"])
        self.assertIn("exact merged --expected-head", payload["error"])

    def test_desktop_uat_script_defaults_to_non_mutating_check(self) -> None:
        result = subprocess.run(
            ["bash", str(DESKTOP_UAT), "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("preToolUse", result.stdout)
        self.assertIn("subagentStart", result.stdout)
        self.assertIn("R1 canary GO required", result.stdout)

    def test_static_installer_check_accepts_v4_assets(self) -> None:
        with tempfile.TemporaryDirectory(prefix="awa-body-c-check.") as raw:
            env = {
                **os.environ,
                "HOME": raw,
                "XDG_DATA_HOME": str(Path(raw) / ".local/share"),
                "XDG_CONFIG_HOME": str(Path(raw) / ".config"),
                "XDG_STATE_HOME": str(Path(raw) / ".local/state"),
            }
            result = subprocess.run(
                ["bash", str(ROOT / "install.sh"), "--check"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                env=env,
                timeout=120,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("awa-hook-owner/v4", result.stdout)


if __name__ == "__main__":
    unittest.main()
