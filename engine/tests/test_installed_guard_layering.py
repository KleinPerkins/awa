"""M3-A.2 installed-guard layering and full-fallback contract."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from engine.tests import suite_runner
from engine.tests.guard_boundary_profile import probe_installed_identity
from engine.tests.installed_guard_canaries import (
    INSTALLED_GUARD_CANARIES,
    LayeringError,
    load_m3_boundary_manifest,
    run_installed_matrix,
    verify_installed_identity,
)


class InstalledGuardLayeringTest(unittest.TestCase):
    def test_canary_registry_covers_every_accepted_boundary(self):
        required = {
            "direct_allow",
            "direct_deny",
            "external_allow",
            "external_deny",
            "uncertainty",
            "maintenance",
            "malformed",
            "owner_mode",
            "kernel_off",
        }
        self.assertEqual(required, set(INSTALLED_GUARD_CANARIES))
        inventory = set(suite_runner.discover_test_ids())
        for test_id in INSTALLED_GUARD_CANARIES.values():
            self.assertIn(test_id, inventory)

    def test_byte_or_interpreter_mismatch_refuses_layered_mode(self):
        identity = probe_installed_identity()
        for field in ("installed_guard_sha256", "installed_python"):
            with self.subTest(field=field):
                changed = dict(identity)
                changed[field] += "-changed"
                with self.assertRaisesRegex(
                    LayeringError, "full installed matrix required"
                ):
                    verify_installed_identity(changed)

    def test_full_fallback_manifest_matches_pre_layering_manifest(self):
        before = load_m3_boundary_manifest("installed")
        after = run_installed_matrix(
            env={"AWA_FULL_INSTALLED_GUARD_MATRIX": "1"}
        )
        self.assertEqual(before["case_ids"], after["case_ids"])
        self.assertEqual(before["outcomes"], after["outcomes"])
        self.assertEqual(before["skips"], after["skips"])


class InstalledGuardKernelOffCanary(unittest.TestCase):
    def test_engine_is_unimportable_in_kernel_off_canary(self):
        with tempfile.TemporaryDirectory(
            prefix="awa-installed-kernel-off."
        ) as raw:
            root = Path(raw)
            empty = root / "empty-pythonpath"
            empty.mkdir()
            env = {
                name: os.environ[name]
                for name in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR")
                if name in os.environ
            }
            env["PYTHONPATH"] = os.environ.get(
                "AWA_TEST_KERNEL_OFF_PYTHONPATH",
                str(empty),
            )
            result = subprocess.run(
                ["python3", "-c", "import engine"],
                cwd=str(empty),
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
