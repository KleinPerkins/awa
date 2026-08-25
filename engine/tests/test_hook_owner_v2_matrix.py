"""M1-C.1 hook-owner v2 preference, v1 fallback, and external boundary."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]
_INSTALL = _ROOT / "install.sh"
_INSTALL_HOOKS = _ROOT / "kernel" / "hooks" / "install-hooks.sh"
_DOCTOR = _ROOT / "kernel" / "bin" / "dev-worktree.sh"
_V1 = _ROOT / "contracts" / "awa-contract.v1.json"
_V2 = _ROOT / "contracts" / "awa-hook-owner.v2.json"
_M1_B_HEAD = "f42e6d5d77fb0244ae616109fbef261b530e3cb4"
_V1_IDS = (
    "worktree.session-context",
    "worktree.shell-guard",
    "worktree.file-observer",
    "recovery.maintenance",
    "finish.prompt-recall",
)
_V2_IDS = (
    "worktree.shell-guard-composite",
    "worktree.stop-observer",
    "worktree.session-handoff",
)


def _expected_row(root: Path, role: dict) -> dict:
    row = dict(role["entry"])
    row["command"] = str((root / role["direct_command_role"]).resolve())
    return row


class TestHookOwnerV2Matrix(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="awa-hook-owner-v2.")
        self.root = Path(self._tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.hooks = self.root / "selected-hooks" / "hooks.json"
        self.env = os.environ.copy()
        for key in tuple(self.env):
            if key.startswith("AWA_") or key in {
                "XDG_DATA_HOME",
                "XDG_CONFIG_HOME",
                "XDG_STATE_HOME",
                "GIT_DIR",
                "GIT_WORK_TREE",
                "GIT_INDEX_FILE",
                "GIT_OBJECT_DIRECTORY",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES",
            }:
                self.env.pop(key, None)
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

    def _run_installer(
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
            [str(script), *args],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )

    def _v1_only_runtime(self) -> Path:
        runtime = self.root / "v1-only-runtime"
        (runtime / "kernel").mkdir(parents=True)
        shutil.copytree(
            _ROOT / "kernel" / "hooks",
            runtime / "kernel" / "hooks",
        )
        (runtime / "contracts").mkdir()
        shutil.copy2(_V1, runtime / "contracts" / _V1.name)
        (runtime / "consumer").mkdir()
        shutil.copy2(
            _ROOT / "consumer" / "finish_current.py",
            runtime / "consumer" / "finish_current.py",
        )
        return runtime

    def test_v2_prefers_and_validates_when_shipped(self):
        installed = self._run_installer()
        self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
        checked = self._run_installer("--check")
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        hooks = json.loads(self.hooks.read_text(encoding="utf-8"))["hooks"]
        v1_roles = json.loads(_V1.read_text(encoding="utf-8"))["hook_ownership"][
            "roles"
        ]
        v2 = json.loads(_V2.read_text(encoding="utf-8"))
        effective = [
            role
            for role in v1_roles
            if role["id"] not in set(v2["supersedes_roles"])
        ] + v2["roles"]
        for role in effective:
            self.assertIn(_expected_row(_ROOT, role), hooks[role["event"]], role["id"])
        self.assertEqual(sum(len(rows) for rows in hooks.values()), 7)
        old_guard = str(
            (_ROOT / "kernel" / "hooks" / "worktree-guard.sh").resolve()
        )
        self.assertNotIn(
            old_guard,
            [
                row.get("command")
                for row in hooks.get("beforeShellExecution", [])
                if isinstance(row, dict)
            ],
        )

        static = subprocess.run(
            [str(_INSTALL), "--check"],
            capture_output=True,
            text=True,
            env=self.env,
            timeout=180,
        )
        self.assertEqual(static.returncode, 0, static.stdout + static.stderr)
        self.assertIn("awa-hook-owner/v2", static.stdout)

        invalid_runtime = self._v1_only_runtime()
        (invalid_runtime / "contracts" / _V2.name).write_text(
            '{"schema":"awa-hook-owner/v2","roles":[]}\n',
            encoding="utf-8",
        )
        invalid_hooks = self.root / "invalid-v2" / "hooks.json"
        invalid = self._run_installer(
            script=invalid_runtime / "kernel" / "hooks" / "install-hooks.sh",
            hooks=invalid_hooks,
        )
        self.assertNotEqual(invalid.returncode, 0)
        self.assertFalse(invalid_hooks.parent.exists())

    def test_v1_compat_tests_retained(self):
        baseline = subprocess.run(
            ["git", "show", f"{_M1_B_HEAD}:contracts/awa-contract.v1.json"],
            cwd=_ROOT,
            check=True,
            capture_output=True,
        ).stdout
        self.assertEqual(_V1.read_bytes(), baseline)
        legacy_tests = (
            _ROOT / "engine" / "tests" / "test_hook_owner_modes.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "test_contract_declares_exact_five_roles_and_direct_default",
            legacy_tests,
        )

        runtime = self._v1_only_runtime()
        legacy_hooks = self.root / "legacy" / "hooks.json"
        installed = self._run_installer(
            script=runtime / "kernel" / "hooks" / "install-hooks.sh",
            hooks=legacy_hooks,
        )
        self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
        owner = json.loads(_V1.read_text(encoding="utf-8"))["hook_ownership"]
        hooks = json.loads(legacy_hooks.read_text(encoding="utf-8"))["hooks"]
        self.assertEqual(tuple(role["id"] for role in owner["roles"]), _V1_IDS)
        for role in owner["roles"]:
            self.assertIn(
                _expected_row(runtime, role),
                hooks[role["event"]],
                role["id"],
            )
        self.assertEqual(sum(len(rows) for rows in hooks.values()), 5)

    def test_session_handoff_role_declared_in_v2(self):
        contract = json.loads(_V2.read_text(encoding="utf-8"))
        self.assertEqual(contract["schema"], "awa-hook-owner/v2")
        self.assertEqual(contract["successor_of"], "awa-hook-owner/v1")
        self.assertEqual(
            tuple(role["id"] for role in contract["roles"]),
            _V2_IDS,
        )
        roles = {role["id"]: role for role in contract["roles"]}
        handoff = roles["worktree.session-handoff"]
        self.assertEqual(handoff["event"], "sessionStart")
        self.assertEqual(
            handoff["direct_command_role"],
            "kernel/hooks/awa-session-handoff.sh",
        )
        self.assertEqual(handoff["dormant_until_milestone"], "M2.4")
        self.assertEqual(
            handoff["entry"],
            {
                "type": "command",
                "timeout": 5,
                "failClosed": False,
            },
        )

    def test_external_mode_is_zero_access(self):
        source = _INSTALL_HOOKS.read_text(encoding="utf-8")
        external_exit = source.index(
            'printf \'%s\\n\' "install-hooks: hook owner external; '
            'selected hook file not inspected by AWA"'
        )
        self.assertLess(external_exit, source.index('SCRIPT_DIR="'))
        self.assertLess(external_exit, source.index('HOOKS_JSON="'))

        blocked_component = self.root / "not-a-directory"
        blocked_component.write_text("sentinel\n", encoding="utf-8")
        impossible = blocked_component / "hooks.json"
        before = blocked_component.stat()
        installed = self._run_installer(owner="external", hooks=impossible)
        checked = self._run_installer(
            "--check",
            owner="external",
            hooks=impossible,
        )
        after = blocked_component.stat()
        self.assertEqual(installed.returncode, 0, installed.stderr)
        self.assertEqual(checked.returncode, 0, checked.stderr)
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
        self.assertEqual(blocked_component.read_bytes(), b"sentinel\n")

    def test_install_hooks_does_not_render_external_rows(self):
        target = self.root / "external-parent" / "hooks.json"
        installed = self._run_installer(owner="external", hooks=target)
        self.assertEqual(installed.returncode, 0, installed.stderr)
        self.assertEqual(
            installed.stdout,
            "install-hooks: hook owner external; "
            "selected hook file not inspected by AWA\n",
        )
        self.assertNotIn("beforeShellExecution", installed.stdout)
        self.assertNotIn("sessionStart", installed.stdout)
        self.assertNotIn("stop", installed.stdout)
        self.assertFalse(target.parent.exists())

    def test_direct_refuses_symlink_hook_destination(self):
        target = self.root / "sentinel.json"
        original = (
            b'{"version":1,"hooks":{"beforeReadFile":'
            b'[{"command":"/foreign/sentinel","type":"command"}]}}\n'
        )
        target.write_bytes(original)
        self.hooks.parent.mkdir(parents=True)
        self.hooks.symlink_to(target)
        result = self._run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(target.read_bytes(), original)
        self.assertTrue(self.hooks.is_symlink())
        self.assertFalse(list(target.parent.glob("sentinel.json.bak-*")))

    def test_doctor_reports_v2_role_matrix(self):
        result = subprocess.run(
            [str(_DOCTOR), "doctor"],
            cwd=_ROOT,
            capture_output=True,
            text=True,
            env=self.env,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("== hook-owner role matrix ==", result.stdout)
        self.assertIn("preferred: awa-hook-owner/v2", result.stdout)
        for role_id in _V2_IDS:
            self.assertIn(role_id, result.stdout)
        self.assertIn("compatibility: awa-hook-owner/v1", result.stdout)


if __name__ == "__main__":
    unittest.main()
