"""E-04 hook-file ownership contract, lifecycle, and release behavior parity.

Every lifecycle test uses an isolated HOME/XDG tree. The selected hook destination is
always a generic fixture path; no operator hook file or installed runtime is touched.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from engine.tests.guard_boundary_profile import (
    GUARD_BOUNDARY_CASES,
    run_owner_mode_cases,
)
from engine.tests.git_guard_command_corpus import (
    GIT_MUTATING_FAMILY_COMMANDS,
    GIT_READONLY_FAMILY_COMMANDS,
)


REPO = Path(__file__).resolve().parents[2]
INSTALL = REPO / "install.sh"
INSTALL_HOOKS = REPO / "kernel" / "hooks" / "install-hooks.sh"
GUARD = REPO / "kernel" / "hooks" / "worktree-guard.sh"
CONTRACT = REPO / "contracts" / "awa-contract.v1.json"
V2_CONTRACT = REPO / "contracts" / "awa-hook-owner.v2.json"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "hook-owner"
V150_COMMIT = "331e633027aa489c08f22b96c979fde36079e220"

ROLE_IDS = (
    "worktree.session-context",
    "worktree.shell-guard",
    "worktree.file-observer",
    "recovery.maintenance",
    "finish.prompt-recall",
)

V151_UNCHANGED_BEHAVIOR_SHA256 = {
    "kernel/hooks/worktree-session.sh":
        "1ea89ba2ad486510be7976d55771e09f7e9201119c4eed38a354ade6eed77938",
    "kernel/hooks/awa-recovery-maintenance.sh":
        "a49911ad61da905a384e5251cc4af1ad6beacc8243aa30b15c63b19f6998ef6c",
    "kernel/hooks/before-submit-prompt.sh":
        "d594519c8962a8cdb8d5adc8262a09a61c00ec074317b3d07be144823220da5a",
    "consumer/finish_current.py":
        "0e8b097a7f118ad71b8889de3cad4d04009fc3db2413bd122f4f4803cea4e26f",
}
V160_PRIMARY_MAINTENANCE_SHA256 = {
    "kernel/hooks/worktree-guard.sh":
        "4a1c81064fccf8ca8fb5bd82a4787fc6e6e17111d5fcc8c99e578cee11606974",
    "engine/tests/git_guard_command_corpus.py":
        "0ba21e1c7d2e8702a4b963ed8d08b8c90e993645200e7eaff23c867e7a2e36b5",
}

_UNSET = object()


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _mode(path):
    return stat.S_IMODE(Path(path).stat().st_mode)


def _fixture_bytes(name, runtime, host_root):
    raw = (FIXTURES / name).read_text(encoding="utf-8")
    return raw.replace("{{RUNTIME}}", str(runtime)).replace(
        "{{HOST_ROOT}}", str(host_root)).encode("utf-8")


def _expected_direct_hooks(runtime):
    hooks = Path(runtime) / "kernel" / "hooks"
    return {
        "sessionStart": [
            {
                "command": str((hooks / "worktree-session.sh").resolve()),
                "type": "command",
                "timeout": 5,
                "failClosed": False,
            },
            {
                "command": str((hooks / "awa-recovery-maintenance.sh").resolve()),
                "type": "command",
                "timeout": 5,
                "failClosed": False,
            },
            {
                "command": str((hooks / "awa-session-handoff.sh").resolve()),
                "type": "command",
                "timeout": 5,
                "failClosed": False,
            },
        ],
        "beforeShellExecution": [
            {
                "command": str(
                    (hooks / "worktree-guard-with-integrity.sh").resolve()),
                "type": "command",
                "timeout": 20,
                "failClosed": False,
            },
        ],
        "beforeSubmitPrompt": [
            {
                "command": str((hooks / "before-submit-prompt.sh").resolve()),
                "type": "command",
                "matcher": "UserPromptSubmit",
                "timeout": 20,
                "failClosed": False,
            },
        ],
        "afterFileEdit": [
            {
                "command": str((hooks / "worktree-guard.sh").resolve()),
                "type": "command",
                "timeout": 20,
            },
        ],
        "stop": [
            {
                "command": str((hooks / "awa-integrity-observer.sh").resolve()),
                "type": "command",
                "timeout": 5,
                "failClosed": False,
            },
        ],
    }


def _effective_direct_roles():
    v1 = json.loads(CONTRACT.read_text(encoding="utf-8"))["hook_ownership"]
    if not V2_CONTRACT.is_file():
        return v1["roles"]
    v2 = json.loads(V2_CONTRACT.read_text(encoding="utf-8"))
    superseded = set(v2["supersedes_roles"])
    return [
        role for role in v1["roles"] if role["id"] not in superseded
    ] + v2["roles"]


class HookOwnerSandbox(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="awa-hook-owner.")
        self.root = Path(self._tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.host_root = self.root / "host"
        self.host_root.mkdir()
        self.hooks = self.root / "selected-hooks" / "hooks.json"
        self.hooks.parent.mkdir()
        self.data_home = self.home / ".local" / "share"
        self.config_home = self.home / ".config"
        self.state_home = self.home / ".local" / "state"
        self.runtime = self.data_home / "awa" / "current"
        self.selection = self.config_home / "awa" / "hook-owner.json"
        self.pointer = self.data_home / "awa" / "release-pointer.json"
        self.env = dict(os.environ)
        for key in tuple(self.env):
            if key.startswith("AWA_") or key in {
                    "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME",
                    "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE",
                    "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES"}:
                self.env.pop(key, None)
        self.env.update({
            "HOME": str(self.home),
            "XDG_DATA_HOME": str(self.data_home),
            "XDG_CONFIG_HOME": str(self.config_home),
            "XDG_STATE_HOME": str(self.state_home),
            "AWA_HOOKS_JSON": str(self.hooks),
            "AWA_MCP_JSON": str(self.home / ".cursor" / "mcp.json"),
            "AWA_OPERATOR_RULE": str(self.home / ".cursor" / "rules" / "awa-operator.mdc"),
            "PYTHONDONTWRITEBYTECODE": "1",
        })

    def tearDown(self):
        self._tmp.cleanup()

    def run_install(self, *args, owner=_UNSET, hooks=None, env_updates=None, timeout=180):
        env = dict(self.env)
        env["AWA_HOOKS_JSON"] = str(hooks or self.hooks)
        if owner is _UNSET:
            env.pop("AWA_HOOK_OWNER", None)
        else:
            env["AWA_HOOK_OWNER"] = owner
        if env_updates:
            env.update(env_updates)
        return subprocess.run(
            [str(INSTALL), *args], env=env, capture_output=True, text=True,
            timeout=timeout)

    def run_hook_installer(
            self, *args, owner=_UNSET, hooks=None, script=INSTALL_HOOKS,
            timeout=60):
        env = dict(self.env)
        env["AWA_HOOKS_JSON"] = str(hooks or self.hooks)
        if owner is _UNSET:
            env.pop("AWA_HOOK_OWNER", None)
        else:
            env["AWA_HOOK_OWNER"] = owner
        return subprocess.run(
            [str(script), *args], env=env, capture_output=True,
            text=True, timeout=timeout)

    def seed_fixture(self, name, path=None):
        destination = Path(path or self.hooks)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(_fixture_bytes(name, self.runtime, self.host_root))
        return destination

    @staticmethod
    def hook_snapshot(path):
        path = Path(path)
        st = path.stat()
        backups = sorted(
            (p.name, _sha256(p), _mode(p))
            for p in path.parent.glob(path.name + ".bak-*"))
        return {
            "inode": st.st_ino,
            "mode": stat.S_IMODE(st.st_mode),
            "size": st.st_size,
            "mtime_ns": st.st_mtime_ns,
            "sha256": _sha256(path),
            "backups": backups,
        }

    def read_selection(self):
        return json.loads(self.selection.read_text(encoding="utf-8"))

    def read_pointer(self):
        return json.loads(self.pointer.read_text(encoding="utf-8"))


class TestHookOwnerContract(HookOwnerSandbox):
    def test_contract_declares_exact_five_roles_and_direct_default(self):
        owner = json.loads(CONTRACT.read_text(encoding="utf-8"))["hook_ownership"]
        self.assertEqual(owner["schema"], "awa-hook-owner/v1")
        self.assertEqual(owner["modes"], ["direct", "external"])
        self.assertEqual(owner["default_mode"], "direct")
        self.assertEqual(owner["selection_env"], "AWA_HOOK_OWNER")
        self.assertEqual(
            owner["selection_schema"], "awa-hook-owner-selection/v1")
        self.assertIs(owner["external_real_hook_file_writes"], False)
        self.assertEqual(tuple(role["id"] for role in owner["roles"]), ROLE_IDS)
        self.assertEqual(
            [role["event"] for role in owner["roles"]],
            ["sessionStart", "beforeShellExecution", "afterFileEdit",
             "sessionStart", "beforeSubmitPrompt"])
        self.assertEqual(len({role["id"] for role in owner["roles"]}), 5)

    def test_direct_installer_rows_equal_contract(self):
        staging = self.root / "contract-direct.json"
        installed = self.run_hook_installer(owner="direct", hooks=staging)
        self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
        checked = self.run_hook_installer("--check", owner="direct", hooks=staging)
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        hooks = json.loads(staging.read_text(encoding="utf-8"))["hooks"]
        for role in _effective_direct_roles():
            entry = dict(role["entry"])
            entry["command"] = str(
                (REPO / role["direct_command_role"]).resolve())
            self.assertIn(entry, hooks[role["event"]], role["id"])
        self.assertEqual(sum(len(rows) for rows in hooks.values()), 7)

    def test_hook_owner_fixtures_are_generic_and_token_bounded(self):
        for fixture in FIXTURES.iterdir():
            text = fixture.read_text(encoding="utf-8")
            for forbidden in (
                    "Klein" + "Perkins", "/Us" + "ers/",
                    "af" + "firm/", "skills/"):
                self.assertNotIn(forbidden, text, fixture.name)
            if fixture.name != "malformed.json":
                json.loads(text.replace("{{RUNTIME}}", "/runtime").replace(
                    "{{HOST_ROOT}}", "/host"))


class TestHookOwnerInstall(HookOwnerSandbox):
    def assert_selection(self, mode):
        expected = {
            "schema": "awa-hook-owner-selection/v1",
            "contract": "awa-hook-owner/v1",
            "mode": mode,
        }
        self.assertEqual(self.read_selection(), expected)
        self.assertEqual(_mode(self.selection), 0o600)
        expected_bytes = (json.dumps(expected, indent=2) + "\n").encode("ascii")
        self.assertEqual(self.selection.read_bytes(), expected_bytes)
        pointer = self.read_pointer()
        self.assertEqual(pointer["hook_owner_contract"], "awa-hook-owner/v1")
        self.assertEqual(pointer["hook_owner_mode"], mode)
        self.assertEqual(
            pointer["hook_owner_contract_sha256"],
            _sha256(self.runtime / "contracts" / "awa-contract.v1.json"))

    def test_clean_direct_install_creates_exact_seven_v2_roles(self):
        first = self.run_install()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        document = json.loads(self.hooks.read_text(encoding="utf-8"))
        self.assertEqual(document, {
            "version": 1,
            "hooks": _expected_direct_hooks(self.runtime),
        })
        self.assert_selection("direct")
        before = self.hook_snapshot(self.hooks)
        second = self.run_install()
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(self.hook_snapshot(self.hooks), before)

    def test_clean_external_install_creates_no_hook_file(self):
        self.hooks.parent.rmdir()
        installed = self.run_install(owner="external")
        self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
        self.assertFalse(self.hooks.exists())
        self.assertFalse(self.hooks.parent.exists())
        self.assert_selection("external")

    def test_external_switch_and_repair_leave_existing_hook_inode_bytes_and_backups_unchanged(
            self):
        self.seed_fixture("external-3-plus-3-plus-2.json")
        before = self.hook_snapshot(self.hooks)
        installed = self.run_install(owner="external")
        self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
        self.assertEqual(self.hook_snapshot(self.hooks), before)
        self.assert_selection("external")

        self.hooks.parent.chmod(0)
        try:
            repaired = self.run_install("--repair")
            doctor = self.run_install("--doctor")
            removed = self.run_install("--uninstall")
        finally:
            self.hooks.parent.chmod(0o700)
        self.assertEqual(repaired.returncode, 0, repaired.stdout + repaired.stderr)
        self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)
        self.assertEqual(removed.returncode, 0, removed.stdout + removed.stderr)
        self.assertEqual(self.hook_snapshot(self.hooks), before)

    def test_unset_repair_preserves_persisted_external_mode(self):
        installed = self.run_install(owner="external")
        self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
        original_installed_at = self.read_pointer()["installed_at"]
        repaired = self.run_install("--repair")
        self.assertEqual(repaired.returncode, 0, repaired.stdout + repaired.stderr)
        self.assert_selection("external")
        self.assertEqual(self.read_pointer()["installed_at"], original_installed_at)
        self.assertFalse(self.hooks.exists())

    def test_release_pointer_recovers_external_when_selection_is_absent(self):
        self.seed_fixture("foreign-sentinel.json")
        installed = self.run_install(owner="external")
        self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
        before = self.hook_snapshot(self.hooks)
        original_installed_at = self.read_pointer()["installed_at"]
        self.selection.unlink()

        repaired = self.run_install("--repair")
        self.assertEqual(repaired.returncode, 0, repaired.stdout + repaired.stderr)
        self.assert_selection("external")
        self.assertEqual(self.read_pointer()["installed_at"], original_installed_at)
        self.assertEqual(self.hook_snapshot(self.hooks), before)

    def test_version_150_upgrade_defaults_to_direct(self):
        self.seed_fixture("v1.5.0-direct.json")
        self.pointer.parent.mkdir(parents=True)
        self.pointer.write_text(json.dumps({
            "schema": "awa-release-pointer/v1",
            "version": "1.5.0",
            "source": "/source",
            "commit": V150_COMMIT,
            "runtime": str(self.runtime),
            "policy": str(self.runtime / "kernel" / "policy" /
                          "default-worktree-policy.yml"),
            "installed_at": "2026-01-01T00:00:00Z",
        }, indent=2) + "\n", encoding="utf-8")
        upgraded = self.run_install()
        self.assertEqual(upgraded.returncode, 0, upgraded.stdout + upgraded.stderr)
        self.assert_selection("direct")
        hooks = json.loads(self.hooks.read_text(encoding="utf-8"))["hooks"]
        expected = _expected_direct_hooks(self.runtime)
        for event, rows in expected.items():
            for row in rows:
                self.assertEqual(hooks[event].count(row), 1)
        self.assertEqual(
            hooks["beforeReadFile"][0]["command"],
            str(self.host_root / "foreign" / "read-observer.sh"))

    def test_invalid_or_malformed_selection_refuses_before_hook_mutation(self):
        self.seed_fixture("foreign-sentinel.json")
        before = self.hook_snapshot(self.hooks)
        for value in ("", "sideways"):
            with self.subTest(explicit=value):
                invalid = self.run_install(owner=value)
                self.assertEqual(
                    invalid.returncode, 2, invalid.stdout + invalid.stderr)
                self.assertEqual(
                    invalid.stderr.strip(),
                    "awa-install: hook-owner selection is invalid")
                self.assertEqual(self.hook_snapshot(self.hooks), before)
                self.assertFalse(self.selection.exists())

        self.selection.parent.mkdir(parents=True)
        self.selection.write_text("{ malformed", encoding="utf-8")
        malformed = self.run_install()
        self.assertEqual(malformed.returncode, 2, malformed.stdout + malformed.stderr)
        self.assertEqual(self.hook_snapshot(self.hooks), before)
        self.assertEqual(self.selection.read_text(encoding="utf-8"), "{ malformed")

        repaired = self.run_install(owner="external")
        self.assertEqual(repaired.returncode, 0, repaired.stdout + repaired.stderr)
        self.assertEqual(self.hook_snapshot(self.hooks), before)
        self.assert_selection("external")

    def test_malformed_selection_bearing_pointer_refuses_before_hook_mutation(self):
        self.seed_fixture("foreign-sentinel.json")
        before = self.hook_snapshot(self.hooks)
        self.pointer.parent.mkdir(parents=True)
        self.pointer.write_text(json.dumps({
            "schema": "awa-release-pointer/v1",
            "version": "1.5.1",
            "source": "/source",
            "commit": "a" * 40,
            "runtime": str(self.runtime),
            "policy": "/policy",
            "installed_at": "2026-01-01T00:00:00Z",
            "hook_owner_mode": "external",
        }), encoding="utf-8")
        malformed = self.run_install()
        self.assertEqual(malformed.returncode, 2, malformed.stdout + malformed.stderr)
        self.assertEqual(self.hook_snapshot(self.hooks), before)
        explicit = self.run_install(owner="external")
        self.assertEqual(explicit.returncode, 0, explicit.stdout + explicit.stderr)
        self.assert_selection("external")
        self.assertEqual(self.hook_snapshot(self.hooks), before)

    def test_unwritable_selection_parent_refuses_before_hook_mutation(self):
        self.seed_fixture("foreign-sentinel.json")
        before = self.hook_snapshot(self.hooks)
        self.selection.parent.mkdir(parents=True)
        default_policy = (
            self.runtime / "kernel" / "policy" / "default-worktree-policy.yml")
        env_file = self.selection.parent / "env"
        env_file.write_text(
            "# AWA environment — generated by install.sh. Source this to put AWA on your PATH.\n"
            f"export AWA_HOME=\"{self.runtime}\"\n"
            f"export AWA_POLICY=\"${{AWA_POLICY:-{default_policy}}}\"\n"
            "# export AWA_GOVERNED_ROOT=\"$HOME/your-governed-root\"   "
            "# optional; a host overlay sets this\n"
            f"export PATH=\"{self.runtime}/kernel/bin:{self.runtime}/bin:$PATH\"\n",
            encoding="utf-8")
        self.selection.parent.chmod(0o500)
        try:
            result = self.run_install(owner="direct")
        finally:
            self.selection.parent.chmod(0o700)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.hook_snapshot(self.hooks), before)
        self.assertFalse(self.selection.exists())

    def test_direct_malformed_hook_file_refuses_and_external_does_not_read_it(self):
        self.hooks.write_bytes((FIXTURES / "malformed.json").read_bytes())
        before = self.hook_snapshot(self.hooks)
        direct = self.run_install(owner="direct")
        self.assertNotEqual(direct.returncode, 0)
        self.assertEqual(self.hook_snapshot(self.hooks), before)

        external = self.run_install(owner="external")
        self.assertEqual(external.returncode, 0, external.stdout + external.stderr)
        self.assertEqual(self.hook_snapshot(self.hooks), before)

        inaccessible = self.root / "inaccessible-hooks"
        inaccessible.mkdir()
        blocked_hook = inaccessible / "hooks.json"
        blocked_hook.write_bytes((FIXTURES / "malformed.json").read_bytes())
        inaccessible.chmod(0)
        try:
            repaired = self.run_install("--repair", hooks=blocked_hook)
            doctor = self.run_install("--doctor", hooks=blocked_hook)
        finally:
            inaccessible.chmod(0o700)
        self.assertEqual(repaired.returncode, 0, repaired.stdout + repaired.stderr)
        self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)

    def test_doctor_reports_and_validates_selected_owner(self):
        direct = self.run_install()
        self.assertEqual(direct.returncode, 0, direct.stdout + direct.stderr)
        direct_doctor = self.run_install("--doctor")
        self.assertEqual(
            direct_doctor.returncode, 0, direct_doctor.stdout + direct_doctor.stderr)
        self.assertIn("hook owner selected: direct", direct_doctor.stdout)

        before = self.hook_snapshot(self.hooks)
        external = self.run_install(owner="external")
        self.assertEqual(external.returncode, 0, external.stdout + external.stderr)
        self.assertEqual(self.hook_snapshot(self.hooks), before)
        self.hooks.write_bytes((FIXTURES / "malformed.json").read_bytes())
        malformed_before = self.hook_snapshot(self.hooks)
        external_doctor = self.run_install("--doctor")
        self.assertEqual(
            external_doctor.returncode, 0,
            external_doctor.stdout + external_doctor.stderr)
        self.assertIn(
            "PASS  hook owner selected: external "
            "(host-managed; hook file not inspected by AWA)",
            external_doctor.stdout)
        self.assertEqual(self.hook_snapshot(self.hooks), malformed_before)

        pointer = self.read_pointer()
        pointer["hook_owner_contract_sha256"] = "0" * 64
        self.pointer.write_text(
            json.dumps(pointer, indent=2) + "\n", encoding="utf-8")
        drift = self.run_install("--doctor")
        self.assertNotEqual(drift.returncode, 0)
        self.assertEqual(self.hook_snapshot(self.hooks), malformed_before)

    def test_external_uninstall_never_writes_host_hook_file(self):
        self.seed_fixture("external-3-plus-3-plus-2.json")
        before = self.hook_snapshot(self.hooks)
        installed = self.run_install(owner="external")
        self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
        removed = self.run_install("--uninstall")
        self.assertEqual(removed.returncode, 0, removed.stdout + removed.stderr)
        self.assertEqual(self.hook_snapshot(self.hooks), before)
        self.assertIn("host must reconcile", removed.stderr)
        self.assertFalse(self.runtime.exists())
        self.assertFalse(self.selection.exists())

    def test_direct_uninstall_removes_only_owned_rows(self):
        self.seed_fixture("foreign-sentinel.json")
        installed = self.run_install()
        self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
        removed = self.run_install("--uninstall")
        self.assertEqual(removed.returncode, 0, removed.stdout + removed.stderr)
        hooks = json.loads(self.hooks.read_text(encoding="utf-8"))["hooks"]
        self.assertEqual(set(hooks), {"beforeReadFile"})
        self.assertEqual(
            hooks["beforeReadFile"][0]["command"],
            str(self.host_root / "foreign" / "sentinel.sh"))

    def test_direct_staging_override_builds_complete_rollback_candidate(self):
        self.seed_fixture("external-3-plus-3-plus-2.json")
        live_before = self.hook_snapshot(self.hooks)
        installed = self.run_install(owner="external")
        self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
        staging = self.root / "rollback" / "hooks.json"
        installed_hook_reconciler = (
            self.runtime / "kernel" / "hooks" / "install-hooks.sh")
        built = self.run_hook_installer(
            owner="direct", hooks=staging, script=installed_hook_reconciler)
        self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
        checked = self.run_hook_installer(
            "--check", owner="direct", hooks=staging,
            script=installed_hook_reconciler)
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        self.assertEqual(
            json.loads(staging.read_text(encoding="utf-8")),
            {"version": 1, "hooks": _expected_direct_hooks(self.runtime)})
        self.assertEqual(self.hook_snapshot(self.hooks), live_before)
        self.assert_selection("external")


class TestHookOwnerParity(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="awa-hook-owner-parity.")
        self.root = Path(self._tmp.name)
        self.repo = self.root / "project"
        self.repo.mkdir()
        self.git_env = dict(os.environ)
        for key in (
                "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE",
                "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES"):
            self.git_env.pop(key, None)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True,
                       env=self.git_env)
        (self.repo / "file").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo), "add", "file"],
                       check=True, env=self.git_env)
        subprocess.run([
            "git", "-C", str(self.repo),
            "-c", "user.email=fixture@example.invalid",
            "-c", "user.name=Fixture", "commit", "-qm", "init",
        ], check=True, env=self.git_env)
        subprocess.run(["git", "-C", str(self.repo), "branch", "-M", "main"],
                       check=True, env=self.git_env)
        subprocess.run([
            "git", "-C", str(self.repo), "remote", "add", "origin",
            "https://example.invalid/fixture/repository.git",
        ], check=True, env=self.git_env)
        self.policy = self.root / "policy.yml"
        self.policy.write_text(
            "version: 1\n"
            "governed_roots:\n"
            f"  - {self.root}\n"
            "default: include\n"
            "include:\n"
            "  - '*'\n"
            "exclude:\n"
            "  - .\n"
            "detectors:\n"
            "  governed_markers:\n"
            "    - _ops/POLICY.md\n"
            "  foreign_hook_frameworks:\n"
            "    - husky\n",
            encoding="utf-8")
        self.delegator = self.root / "host-policy-delegator.sh"
        self.delegator.write_text(
            "#!/usr/bin/env bash\n"
            "set -u\n"
            "target=\"${AWA_DELEGATE_TARGET:-}\"\n"
            "if [ ! -x \"$target\" ]; then\n"
            "  printf '%s\\n' '{\"permission\":\"allow\"}'\n"
            "  exit 0\n"
            "fi\n"
            "export AWA_POLICY=\"${AWA_EXTERNAL_POLICY:?}\"\n"
            "export AWA_GOVERNED_ROOT=\"${AWA_EXTERNAL_ROOT:?}\"\n"
            "exec \"$target\"\n",
            encoding="utf-8")
        self.delegator.chmod(0o755)

    def tearDown(self):
        self._tmp.cleanup()

    def run_guard(self, command, delegated=False, event="beforeShellExecution",
                  env_updates=None):
        env = dict(os.environ)
        for key in (
                "CURSOR_BACKGROUND_AGENT", "CURSOR_CLOUD_AGENT",
                "IS_BACKGROUND_AGENT", "is_background_agent", "AWA_FORCE_CLOUD",
                "cloud_agent_identity_broker", "CURSOR_AGENT_IDENTITY_BROKER"):
            env.pop(key, None)
        env.update({
            "AWA_POLICY": str(self.policy),
            "AWA_GOVERNED_ROOT": str(self.root),
            "AWA_EXTERNAL_POLICY": str(self.policy),
            "AWA_EXTERNAL_ROOT": str(self.root),
            "AWA_DELEGATE_TARGET": str(GUARD),
        })
        if env_updates:
            env.update(env_updates)
        payload = {
            "hook_event_name": event,
            "cwd": str(self.repo),
            "command": command,
            "file_path": str(self.repo / "file"),
        }
        executable = self.delegator if delegated else GUARD
        result = subprocess.run(
            [str(executable)], input=json.dumps(payload), capture_output=True,
            text=True, env=env, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_shared_git_corpus_matches_direct_and_generic_delegated_paths(self):
        for command in GIT_READONLY_FAMILY_COMMANDS:
            with self.subTest(kind="read", command=command):
                direct = self.run_guard(command)
                delegated = self.run_guard(command, delegated=True)
                self.assertEqual(direct, delegated)
                self.assertEqual(direct, {"permission": "allow"})
        for command in GIT_MUTATING_FAMILY_COMMANDS:
            with self.subTest(kind="write", command=command):
                direct = self.run_guard(command)
                delegated = self.run_guard(command, delegated=True)
                self.assertEqual(direct, delegated)
                self.assertEqual(direct["permission"], "deny")
                self.assertEqual(
                    set(direct), {"permission", "user_message", "agent_message"})

    def test_m3_profile_manifest_matches_owner_paths(self):
        report = run_owner_mode_cases(GUARD_BOUNDARY_CASES)
        self.assertTrue(report["passed"])
        self.assertEqual(
            report["outcomes"],
            {
                case.label: case.expected_permission
                for case in GUARD_BOUNDARY_CASES
            },
        )

    def test_hook_fail_open_and_after_file_edit_policy_match_both_paths(self):
        direct_edit = self.run_guard(
            "ignored", event="afterFileEdit")
        delegated_edit = self.run_guard(
            "ignored", delegated=True, event="afterFileEdit")
        self.assertEqual(direct_edit, {"permission": "allow"})
        self.assertEqual(direct_edit, delegated_edit)

        direct_cloud = self.run_guard(
            "git commit -am x", env_updates={"CURSOR_CLOUD_AGENT": "1"})
        delegated_cloud = self.run_guard(
            "git commit -am x", delegated=True,
            env_updates={"CURSOR_CLOUD_AGENT": "1"})
        self.assertEqual(direct_cloud, {"permission": "allow"})
        self.assertEqual(direct_cloud, delegated_cloud)

        missing_env = dict(os.environ)
        missing_env.update({
            "AWA_EXTERNAL_POLICY": str(self.policy),
            "AWA_EXTERNAL_ROOT": str(self.root),
            "AWA_DELEGATE_TARGET": str(self.root / "missing-guard"),
        })
        failed_open = subprocess.run(
            [str(self.delegator)], input=json.dumps({
                "hook_event_name": "beforeShellExecution",
                "cwd": str(self.repo),
                "command": "git commit -am x",
            }), capture_output=True, text=True, env=missing_env)
        self.assertEqual(failed_open.returncode, 0)
        self.assertEqual(json.loads(failed_open.stdout), {"permission": "allow"})

        owner = json.loads(CONTRACT.read_text(encoding="utf-8"))["hook_ownership"]
        roles = {role["id"]: role for role in owner["roles"]}
        self.assertIs(
            roles["worktree.shell-guard"]["entry"]["failClosed"], False)
        self.assertNotIn(
            "failClosed", roles["worktree.file-observer"]["entry"])

    def test_v151_unrelated_behavior_files_remain_byte_identical(self):
        for relative, expected in V151_UNCHANGED_BEHAVIOR_SHA256.items():
            with self.subTest(path=relative):
                self.assertEqual(_sha256(REPO / relative), expected)

    def test_v160_primary_maintenance_behavior_files_are_byte_identical(self):
        for relative, expected in V160_PRIMARY_MAINTENANCE_SHA256.items():
            with self.subTest(path=relative):
                self.assertEqual(_sha256(REPO / relative), expected)


if __name__ == "__main__":
    unittest.main()
