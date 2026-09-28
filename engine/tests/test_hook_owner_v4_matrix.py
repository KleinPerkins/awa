"""ADR 0025 Body C hook-owner v4 preference and compatibility matrix."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from engine import integrity


ROOT = Path(__file__).resolve().parents[2]
INSTALL_HOOKS = ROOT / "kernel" / "hooks" / "install-hooks.sh"
V1 = ROOT / "contracts" / "awa-contract.v1.json"
V2 = ROOT / "contracts" / "awa-hook-owner.v2.json"
V3 = ROOT / "contracts" / "awa-hook-owner.v3.json"
V4 = ROOT / "contracts" / "awa-hook-owner.v4.json"
BASE = "71e5a3e2c03d9ed09f9c76d5ec0f52da8e664c8c"


class TestHookOwnerV4Matrix(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="awa-hook-owner-v4.")
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.hooks = self.root / "selected" / "hooks.json"
        self.env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("AWA_")
            and key
            not in {
                "XDG_DATA_HOME",
                "XDG_CONFIG_HOME",
                "XDG_STATE_HOME",
                "GIT_DIR",
                "GIT_WORK_TREE",
                "GIT_INDEX_FILE",
                "GIT_OBJECT_DIRECTORY",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES",
            }
        }
        self.env.update(
            {
                "HOME": str(self.home),
                "XDG_DATA_HOME": str(self.home / ".local" / "share"),
                "XDG_CONFIG_HOME": str(self.home / ".config"),
                "XDG_STATE_HOME": str(self.home / ".local" / "state"),
                "AWA_HOOKS_JSON": str(self.hooks),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(
        self,
        *args: str,
        script: Path = INSTALL_HOOKS,
        owner: str = "direct",
        hooks: Path | None = None,
    ) -> subprocess.CompletedProcess:
        env = dict(self.env)
        env["AWA_HOOK_OWNER"] = owner
        env["AWA_HOOKS_JSON"] = str(hooks or self.hooks)
        return subprocess.run(
            ["bash", str(script), *args],
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
        )

    def _runtime(self, version: int) -> Path:
        runtime = self.root / f"runtime-v{version}"
        shutil.copytree(ROOT / "kernel", runtime / "kernel")
        (runtime / "contracts").mkdir()
        shutil.copy2(V1, runtime / "contracts" / V1.name)
        for predecessor, minimum in ((V2, 2), (V3, 3), (V4, 4)):
            if version >= minimum:
                shutil.copy2(
                    predecessor, runtime / "contracts" / predecessor.name
                )
        return runtime

    def test_v4_contract_adds_closed_catch_all_launch_and_startup_roles(
        self,
    ) -> None:
        contract = json.loads(V4.read_text(encoding="utf-8"))
        self.assertEqual(contract["schema"], "awa-hook-owner/v4")
        self.assertEqual(contract["version"], 4)
        self.assertEqual(contract["successor_of"], "awa-hook-owner/v3")
        self.assertEqual(contract["supersedes_roles"], [])
        self.assertIs(contract["external_real_hook_file_writes"], False)
        self.assertEqual(
            [
                (
                    role["id"],
                    role["event"],
                    role["entry"].get("matcher"),
                    role["entry"]["failClosed"],
                )
                for role in contract["roles"]
            ],
            [
                (
                    "registration.tool-admission",
                    "preToolUse",
                    "*",
                    False,
                ),
                (
                    "registration.subagent-admission",
                    "subagentStart",
                    "*",
                    False,
                ),
                (
                    "registration.startup-reconcile",
                    "sessionStart",
                    None,
                    False,
                ),
            ],
        )
        self.assertTrue(integrity._valid_v4_hook_contract(ROOT, contract))

    def test_direct_projection_prefers_v4_and_preserves_independent_roles(
        self,
    ) -> None:
        installed = self._run()
        self.assertEqual(installed.returncode, 0, installed.stderr)
        checked = self._run("--check")
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertIn("awa-hook-owner/v4", checked.stdout)
        hooks = json.loads(self.hooks.read_text(encoding="utf-8"))["hooks"]
        self.assertEqual(sum(len(rows) for rows in hooks.values()), 10)
        self.assertEqual(
            hooks["preToolUse"],
            [
                {
                    "type": "command",
                    "matcher": "*",
                    "timeout": 20,
                    "failClosed": False,
                    "command": str(
                        (
                            ROOT
                            / "kernel/hooks/awa-registration-admission.sh"
                        ).resolve()
                    ),
                }
            ],
        )
        self.assertEqual(len(hooks["beforeShellExecution"]), 1)
        self.assertEqual(len(hooks["beforeSubmitPrompt"]), 1)
        self.assertEqual(len(hooks["afterFileEdit"]), 1)

    def test_v1_through_v3_fallbacks_remain_installable(self) -> None:
        expected = {
            1: "awa-hook-owner/v1",
            2: "awa-hook-owner/v2",
            3: "awa-hook-owner/v3",
        }
        for version, contract in expected.items():
            with self.subTest(version=version):
                runtime = self._runtime(version)
                target = self.root / f"hooks-v{version}" / "hooks.json"
                result = self._run(
                    script=runtime / "kernel/hooks/install-hooks.sh",
                    hooks=target,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                checked = self._run(
                    "--check",
                    script=runtime / "kernel/hooks/install-hooks.sh",
                    hooks=target,
                )
                self.assertEqual(checked.returncode, 0, checked.stderr)
                self.assertIn(contract, checked.stdout)

    def test_invalid_shipped_v4_never_falls_back_to_v3(self) -> None:
        runtime = self._runtime(4)
        (runtime / "contracts" / V4.name).write_text(
            '{"schema":"awa-hook-owner/v4","roles":[]}\n',
            encoding="utf-8",
        )
        target = self.root / "invalid" / "hooks.json"
        result = self._run(
            script=runtime / "kernel/hooks/install-hooks.sh",
            hooks=target,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(target.parent.exists())
        self.assertIsNone(integrity._effective_hook_roles(runtime))

    def test_external_mode_rejects_before_selected_hook_file_access(self) -> None:
        blocked = self.root / "not-a-directory"
        blocked.write_text("sentinel\n", encoding="utf-8")
        target = blocked / "hooks.json"
        before = blocked.stat()
        for args in ((), ("--check",)):
            result = self._run(*args, owner="external", hooks=target)
            self.assertEqual(result.returncode, 0, result.stderr)
        after = blocked.stat()
        self.assertEqual(
            (
                before.st_ino,
                stat.S_IMODE(before.st_mode),
                before.st_size,
                before.st_mtime_ns,
            ),
            (
                after.st_ino,
                stat.S_IMODE(after.st_mode),
                after.st_size,
                after.st_mtime_ns,
            ),
        )
        self.assertEqual(blocked.read_bytes(), b"sentinel\n")

    def test_v1_v2_v3_and_protected_entry_bytes_are_unchanged(self) -> None:
        for relative in (
            "contracts/awa-contract.v1.json",
            "contracts/awa-hook-owner.v2.json",
            "contracts/awa-hook-owner.v3.json",
            "consumer/finish_current.py",
            "kernel/hooks/before-submit-prompt.sh",
            "kernel/hooks/worktree-guard.sh",
        ):
            expected = subprocess.run(
                ["git", "show", f"{BASE}:{relative}"],
                cwd=ROOT,
                check=True,
                capture_output=True,
            ).stdout
            self.assertEqual((ROOT / relative).read_bytes(), expected)


if __name__ == "__main__":
    unittest.main()
