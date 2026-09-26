"""ADR 0024 hook-owner v3 preference and compatibility matrix."""

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


_ROOT = Path(__file__).resolve().parents[2]
_INSTALL_HOOKS = _ROOT / "kernel" / "hooks" / "install-hooks.sh"
_DOCTOR = _ROOT / "kernel" / "bin" / "dev-worktree.sh"
_V1 = _ROOT / "contracts" / "awa-contract.v1.json"
_V2 = _ROOT / "contracts" / "awa-hook-owner.v2.json"
_V3 = _ROOT / "contracts" / "awa-hook-owner.v3.json"
_BASE = "ff978ade5ff9c7604f58f4b3810b1cd75ea3287f"


class TestHookOwnerV3Matrix(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="awa-hook-owner-v3.")
        self.root = Path(self._tmp.name)
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
        self._tmp.cleanup()

    def _run(
        self,
        *args: str,
        script: Path = _INSTALL_HOOKS,
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

    def _runtime(self, name: str, *, version: int) -> Path:
        runtime = self.root / name
        shutil.copytree(_ROOT / "kernel", runtime / "kernel")
        (runtime / "contracts").mkdir()
        shutil.copy2(_V1, runtime / "contracts" / _V1.name)
        if version >= 2:
            shutil.copy2(_V2, runtime / "contracts" / _V2.name)
        if version >= 3:
            shutil.copy2(_V3, runtime / "contracts" / _V3.name)
        (runtime / "consumer").mkdir()
        shutil.copy2(
            _ROOT / "consumer" / "finish_current.py",
            runtime / "consumer" / "finish_current.py",
        )
        (runtime / "engine").mkdir()
        for name in ("native_entry.py", "native_entry_prompt_adapter.py"):
            shutil.copy2(_ROOT / "engine" / name, runtime / "engine" / name)
        return runtime

    def test_v3_contract_composes_effective_v1_v2_roles(self) -> None:
        v3 = json.loads(_V3.read_text(encoding="utf-8"))
        self.assertEqual(v3["schema"], "awa-hook-owner/v3")
        self.assertEqual(v3["version"], 3)
        self.assertEqual(v3["successor_of"], "awa-hook-owner/v2")
        self.assertEqual(
            v3["v2_contract"],
            "contracts/awa-hook-owner.v2.json",
        )
        self.assertEqual(v3["supersedes_roles"], ["finish.prompt-recall"])
        self.assertIs(v3["external_real_hook_file_writes"], False)
        self.assertEqual(len(v3["roles"]), 1)
        role = v3["roles"][0]
        self.assertEqual(role["id"], "finish.prompt-recall-with-entry")
        self.assertEqual(role["event"], "beforeSubmitPrompt")
        self.assertEqual(
            role["direct_command_role"],
            "kernel/hooks/before-submit-prompt-with-entry.sh",
        )
        self.assertEqual(
            role["entry"],
            {
                "type": "command",
                "matcher": "UserPromptSubmit",
                "timeout": 20,
                "failClosed": False,
            },
        )
        self.assertTrue(integrity._valid_v3_hook_contract(_ROOT, v3))

    def test_direct_projection_prefers_v3_and_removes_old_finish_row(self) -> None:
        installed = self._run()
        self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
        checked = self._run("--check")
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        self.assertIn("awa-hook-owner/v3", checked.stdout)
        hooks = json.loads(self.hooks.read_text(encoding="utf-8"))["hooks"]
        prompt_rows = hooks["beforeSubmitPrompt"]
        self.assertEqual(len(prompt_rows), 1)
        self.assertEqual(
            prompt_rows[0]["command"],
            str(
                (
                    _ROOT
                    / "kernel"
                    / "hooks"
                    / "before-submit-prompt-with-entry.sh"
                ).resolve()
            ),
        )
        self.assertEqual(sum(len(rows) for rows in hooks.values()), 7)
        self.assertNotIn(
            str((_ROOT / "kernel" / "hooks" / "before-submit-prompt.sh").resolve()),
            [row.get("command") for row in prompt_rows],
        )

    def test_v1_and_v2_fallbacks_remain_installable(self) -> None:
        expected = {
            1: ("awa-hook-owner/v1", "before-submit-prompt.sh"),
            2: ("awa-hook-owner/v2", "before-submit-prompt.sh"),
        }
        for version, (contract, prompt_name) in expected.items():
            with self.subTest(version=version):
                runtime = self._runtime(f"runtime-v{version}", version=version)
                target = self.root / f"hooks-v{version}" / "hooks.json"
                result = self._run(
                    script=runtime / "kernel" / "hooks" / "install-hooks.sh",
                    hooks=target,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                checked = self._run(
                    "--check",
                    script=runtime / "kernel" / "hooks" / "install-hooks.sh",
                    hooks=target,
                )
                self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
                self.assertIn(contract, checked.stdout)
                rows = json.loads(target.read_text(encoding="utf-8"))["hooks"]
                self.assertTrue(
                    rows["beforeSubmitPrompt"][0]["command"].endswith(prompt_name)
                )

    def test_v1_v2_bytes_remain_at_bound_head(self) -> None:
        for relative in (
            "contracts/awa-contract.v1.json",
            "contracts/awa-hook-owner.v2.json",
        ):
            expected = subprocess.run(
                ["git", "show", f"{_BASE}:{relative}"],
                cwd=_ROOT,
                check=True,
                capture_output=True,
            ).stdout
            self.assertEqual((_ROOT / relative).read_bytes(), expected)

    def test_invalid_shipped_v3_never_falls_back_to_v2(self) -> None:
        runtime = self._runtime("invalid-v3", version=3)
        (runtime / "contracts" / _V3.name).write_text(
            '{"schema":"awa-hook-owner/v3","roles":[]}\n',
            encoding="utf-8",
        )
        target = self.root / "invalid-v3-hooks" / "hooks.json"
        installed = self._run(
            script=runtime / "kernel" / "hooks" / "install-hooks.sh",
            hooks=target,
        )
        self.assertNotEqual(installed.returncode, 0)
        self.assertFalse(target.parent.exists())
        self.assertIsNone(integrity._effective_hook_roles(runtime))

    def test_external_mode_is_zero_access_with_v3_present(self) -> None:
        blocked = self.root / "not-a-directory"
        blocked.write_text("sentinel\n", encoding="utf-8")
        target = blocked / "hooks.json"
        before = blocked.stat()
        for args in ((), ("--check",)):
            result = self._run(*args, owner="external", hooks=target)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
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

    def test_doctor_prefers_v3_and_lists_compatibility(self) -> None:
        result = subprocess.run(
            ["bash", str(_DOCTOR), "doctor"],
            cwd=_ROOT,
            capture_output=True,
            text=True,
            env=self.env,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("preferred: awa-hook-owner/v3", result.stdout)
        self.assertIn("compatibility: awa-hook-owner/v2", result.stdout)
        self.assertIn("compatibility: awa-hook-owner/v1", result.stdout)
        self.assertIn("finish.prompt-recall-with-entry", result.stdout)


if __name__ == "__main__":
    unittest.main()
