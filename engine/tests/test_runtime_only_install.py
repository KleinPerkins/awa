"""The explicit runtime-only profile must never open shared host configuration."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import tempfile
import unittest

from engine import __version__ as TARGET_VERSION


ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "install.sh"
TREES = ("kernel", "engine", "dashboard", "contracts", "bin", "consumer")
FILES = ("pyproject.toml", "Makefile", "install.sh", "bootstrap.sh",
         "ARCHITECTURE.md", "README.md", "SECURITY.md", "LICENSE")


class RuntimeOnlyInstallTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="awa-runtime-only-")
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name).resolve() / "home"
        self.home.mkdir()
        self.runtime = self.home / "data/awa/current"
        self.runtime.mkdir(parents=True)
        for name in TREES:
            shutil.copytree(ROOT / name, self.runtime / name,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"))
        for name in FILES:
            shutil.copy2(ROOT / name, self.runtime / name)
        self.current_init = (ROOT / "engine/__init__.py").read_text()
        self.assertIn('__version__ = "' + TARGET_VERSION + '"', self.current_init)
        (self.runtime / "engine/__init__.py").write_text(
            self.current_init.replace('"' + TARGET_VERSION + '"', '"0.0.0"'))
        (self.runtime / "README.md").write_text("previous runtime\n")
        self.owner = self.home / "config/awa/hook-owner.json"
        self.owner.parent.mkdir(parents=True)
        self.owner.write_text(json.dumps({"schema": "awa-hook-owner-selection/v1",
                                         "contract": "awa-hook-owner/v1", "mode": "external"}))
        self.owner.chmod(0o600)
        self.pointer = self.home / "data/awa/release-pointer.json"
        self.previous = {
            "schema": "awa-release-pointer/v1", "version": "0.0.0",
            "source": str(ROOT), "commit": "1" * 40, "runtime": str(self.runtime),
            "policy": str(self.runtime / "kernel/policy/default-worktree-policy.yml"),
            "hook_owner_contract": "awa-hook-owner/v1", "hook_owner_mode": "external",
            "hook_owner_contract_sha256": hashlib.sha256(
                (self.runtime / "contracts/awa-contract.v1.json").read_bytes()).hexdigest(),
            "installed_at": "2020-01-01T00:00:00Z",
        }
        self.write_pointer()
        cursor = self.home / ".cursor"
        (cursor / "rules").mkdir(parents=True)
        # A read or copy of the MCP file would block. The bounded child process
        # group makes this a useful regression without leaving a stuck copier.
        os.mkfifo(cursor / "mcp.json", 0o600)
        (cursor / "hooks.json").write_text('{"unrelated":"preserve"}\n')
        (cursor / "rules/awa-operator.mdc").write_text("operator-owned projection\n")
        (self.owner.parent / "env").write_text("existing environment\n")
        self.state = self.home / "state/awa"
        self.state.mkdir(parents=True)
        self.state.chmod(0o755)
        (self.state / "sentinel").write_text("no state migration\n")
        temporary = self.home / "temporary"
        temporary.mkdir()
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith(("AWA_", "GIT_", "XDG_"))}
        self.env.update(HOME=str(self.home), XDG_DATA_HOME=str(self.home / "data"),
                        XDG_CONFIG_HOME=str(self.home / "config"),
                        XDG_STATE_HOME=str(self.home / "state"),
                        TMPDIR=str(temporary), PYTHONDONTWRITEBYTECODE="1")

    def write_pointer(self):
        self.pointer.write_text(json.dumps(self.previous, indent=2) + "\n")
        self.pointer.chmod(0o600)

    def source_commit(self):
        environment = dict(self.env, GIT_OPTIONAL_LOCKS="0", GIT_CONFIG_NOSYSTEM="1",
                           GIT_CONFIG_GLOBAL="/dev/null")
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, env=environment, text=True).strip()

    def protected(self):
        observed = {}
        for directory in (self.home / ".cursor", self.home / "config", self.home / "state",
                          self.home / "temporary"):
            for path in (directory, *sorted(directory.rglob("*"))):
                st = path.lstat()
                observed[str(path.relative_to(self.home))] = (
                    stat.S_IFMT(st.st_mode), stat.S_IMODE(st.st_mode),
                    path.read_bytes() if stat.S_ISREG(st.st_mode) else None,
                )
        return observed

    def run_installer(self, *, extra=None, script=None, arguments=("--runtime-only",)):
        environment = dict(self.env, **(extra or {}))
        command = (["bash", str(INSTALLER), *arguments] if script is None
                   else ["bash", "-c", script, "runtime-only-test", str(INSTALLER)])
        child = subprocess.Popen(command, cwd=ROOT, env=environment, text=True,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 start_new_session=True)
        try:
            out, err = child.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.communicate()
            self.fail("runtime-only profile attempted blocked host configuration access")
        return subprocess.CompletedProcess(command, child.returncode, out, err)

    def assert_refused_without_copy(self, result, protected, pointer):
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.runtime / "README.md").read_text(), "previous runtime\n")
        self.assertEqual(self.pointer.read_bytes(), pointer)
        self.assertEqual(self.protected(), protected)

    def test_advances_runtime_and_pointer_without_opening_mcp_or_changing_host_state(self):
        before = self.protected()
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.runtime / "README.md").read_bytes(), (ROOT / "README.md").read_bytes())
        self.assertEqual((self.runtime / "engine/__init__.py").read_text(), self.current_init)
        pointer = json.loads(self.pointer.read_text())
        self.assertEqual(pointer["version"], TARGET_VERSION)
        self.assertEqual(pointer["hook_owner_mode"], "external")
        self.assertEqual(pointer["source"], str(ROOT))
        self.assertEqual(pointer["commit"], self.source_commit())
        self.assertEqual(self.protected(), before)

    def test_direct_owner_cannot_be_overridden_to_external(self):
        self.owner.write_text(json.dumps({"schema": "awa-hook-owner-selection/v1",
                                         "contract": "awa-hook-owner/v1", "mode": "direct"}))
        before, pointer = self.protected(), self.pointer.read_bytes()
        result = self.run_installer(extra={"AWA_HOOK_OWNER": "external"})
        self.assert_refused_without_copy(result, before, pointer)

    def test_inherited_git_overrides_cannot_change_published_source_revision(self):
        before = self.protected()
        result = self.run_installer(extra={"GIT_DIR": str(self.home / "foreign-git"),
                                           "GIT_WORK_TREE": str(self.home)})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(self.pointer.read_text())["commit"], self.source_commit())
        self.assertEqual(self.protected(), before)

    def test_source_revision_drift_stops_pointer_publication_after_copy(self):
        before, pointer = self.protected(), self.pointer.read_bytes()
        counter = Path(self.temporary.name).resolve() / "resolver-count"
        script = ('. "$1"; resolve_source_commit() { '
                  'if [ -e "$RESOLVER_COUNT" ]; then printf "%040d\\n" 3; '
                  'else : > "$RESOLVER_COUNT"; printf "%040d\\n" 2; fi; }; do_runtime_only')
        result = self.run_installer(extra={"RESOLVER_COUNT": str(counter)}, script=script)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.pointer.read_bytes(), pointer)
        self.assertEqual(self.protected(), before)
        self.assertIn("source revision changed", result.stderr)

    def test_direct_environment_override_refuses_persisted_external_owner(self):
        before, pointer = self.protected(), self.pointer.read_bytes()
        self.assert_refused_without_copy(self.run_installer(extra={"AWA_HOOK_OWNER": "direct"}),
                                         before, pointer)

    def test_contract_change_refuses_before_any_runtime_copy(self):
        contract = self.runtime / "contracts/awa-contract.v1.json"
        contract.write_bytes(contract.read_bytes() + b"\n")
        before, pointer = self.protected(), self.pointer.read_bytes()
        self.assert_refused_without_copy(self.run_installer(), before, pointer)

    def test_added_source_contract_requires_full_host_reconciliation(self):
        (self.runtime / "contracts/awa-hook-owner.v4.json").unlink()
        before, pointer = self.protected(), self.pointer.read_bytes()
        self.assert_refused_without_copy(self.run_installer(), before, pointer)

    def test_downgrade_refuses_before_copy(self):
        self.previous["version"] = "99.0.0"
        self.write_pointer()
        (self.runtime / "engine/__init__.py").write_text(
            self.current_init.replace('"' + TARGET_VERSION + '"', '"99.0.0"'))
        before, pointer = self.protected(), self.pointer.read_bytes()
        self.assert_refused_without_copy(self.run_installer(), before, pointer)

    def test_another_source_path_refuses_before_copy(self):
        self.previous["source"] = str(self.home / "other-source")
        self.write_pointer()
        before, pointer = self.protected(), self.pointer.read_bytes()
        self.assert_refused_without_copy(self.run_installer(), before, pointer)

    def test_unknown_pointer_fields_refuse_before_copy(self):
        self.previous["unexpected"] = True
        self.write_pointer()
        before, pointer = self.protected(), self.pointer.read_bytes()
        self.assert_refused_without_copy(self.run_installer(), before, pointer)

    def test_duplicate_owner_keys_refuse_instead_of_selecting_the_last_mode(self):
        self.owner.write_text('{"schema":"awa-hook-owner-selection/v1",'
                              '"contract":"awa-hook-owner/v1",'
                              '"mode":"direct","mode":"external"}')
        before, pointer = self.protected(), self.pointer.read_bytes()
        self.assert_refused_without_copy(self.run_installer(), before, pointer)

    def test_matching_release_pointer_is_a_noop(self):
        self.previous["version"] = TARGET_VERSION
        environment = dict(self.env, GIT_OPTIONAL_LOCKS="0", GIT_CONFIG_NOSYSTEM="1",
                           GIT_CONFIG_GLOBAL="/dev/null")
        self.previous["commit"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, env=environment, text=True).strip()
        self.write_pointer()
        (self.runtime / "engine/__init__.py").write_text(self.current_init)
        (self.runtime / "README.md").write_bytes((ROOT / "README.md").read_bytes())
        before, pointer = self.protected(), self.pointer.read_bytes()
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("no runtime repair or host changes", result.stdout)
        self.assertEqual(self.pointer.read_bytes(), pointer)
        self.assertEqual(self.protected(), before)

    def test_contract_directory_link_refuses_without_following_it(self):
        shutil.rmtree(self.runtime / "contracts")
        (self.runtime / "contracts").symlink_to(self.home / ".cursor", target_is_directory=True)
        before, pointer = self.protected(), self.pointer.read_bytes()
        self.assert_refused_without_copy(self.run_installer(), before, pointer)

    def test_runtime_copy_destination_link_cannot_overwrite_host_configuration(self):
        destination = self.runtime / "README.md"
        destination.unlink()
        destination.symlink_to(self.home / ".cursor/rules/awa-operator.mdc")
        before, pointer = self.protected(), self.pointer.read_bytes()
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(destination.is_symlink())
        self.assertEqual(self.pointer.read_bytes(), pointer)
        self.assertEqual(self.protected(), before)

    def test_nested_runtime_link_refuses_without_copying(self):
        (self.runtime / "engine/host-link").symlink_to(self.home / ".cursor", target_is_directory=True)
        before, pointer = self.protected(), self.pointer.read_bytes()
        self.assert_refused_without_copy(self.run_installer(), before, pointer)

    def test_hard_linked_runtime_destination_cannot_change_host_configuration(self):
        destination = self.runtime / "README.md"
        destination.unlink()
        os.link(self.home / ".cursor/rules/awa-operator.mdc", destination)
        before, pointer = self.protected(), self.pointer.read_bytes()
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.pointer.read_bytes(), pointer)
        self.assertEqual(self.protected(), before)

    def test_mixed_runtime_only_arguments_never_fall_through_to_full_install(self):
        before, pointer = self.protected(), self.pointer.read_bytes()
        for arguments in [("--repair", "--runtime-only"), ("--runtime-only", "--repair")]:
            with self.subTest(arguments=arguments):
                result = self.run_installer(arguments=arguments)
                self.assert_refused_without_copy(result, before, pointer)
                self.assertIn("standalone profile", result.stderr)

    def test_missing_runtime_refuses_without_creating_it(self):
        shutil.rmtree(self.runtime)
        before, pointer = self.protected(), self.pointer.read_bytes()
        result = self.run_installer()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.runtime.exists())
        self.assertEqual(self.pointer.read_bytes(), pointer)
        self.assertEqual(self.protected(), before)

    def test_copy_failure_preserves_pointer_and_reports_incomplete_runtime(self):
        before, pointer = self.protected(), self.pointer.read_bytes()
        script = '. "$1"; awa_sync_tree() { return 42; }; do_runtime_only'
        result = self.run_installer(script=script)
        self.assert_refused_without_copy(result, before, pointer)
        self.assertIn("release pointer was not advanced", result.stderr)

    def test_top_level_copy_failure_does_not_get_swallowed_by_the_shell_condition(self):
        before, pointer = self.protected(), self.pointer.read_bytes()
        script = ('. "$1"; '
                  'install() { return 42; }; cp() { return 42; }; do_runtime_only')
        result = self.run_installer(script=script)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.pointer.read_bytes(), pointer)
        self.assertEqual(self.protected(), before)
        self.assertIn("release pointer was not advanced", result.stderr)

    def assert_tree_setup_failure(self, overrides):
        before, pointer = self.protected(), self.pointer.read_bytes()
        result = self.run_installer(script='. "$1"; ' + overrides + 'do_runtime_only')
        self.assert_refused_without_copy(result, before, pointer)
        self.assertIn("release pointer was not advanced", result.stderr)

    NO_RSYNC = ('command() { if [ "$1" = "-v" ] && [ "$2" = "rsync" ]; '
                'then return 1; fi; builtin command "$@"; }; ')

    def test_nested_initial_mkdir_failure_stops_before_rsync(self):
        self.assert_tree_setup_failure('mkdir() { return 42; }; '
                                      'rsync() { : > "$RUNTIME/rsync-reached"; return 0; }; ')
        self.assertFalse((self.runtime / "rsync-reached").exists())

    def test_nested_fallback_delete_failure_stops_before_successful_tar(self):
        self.assert_tree_setup_failure(self.NO_RSYNC +
                                      'rm() { return 42; }; tar() { return 0; }; ')

    def test_nested_fallback_mkdir_failure_stops_before_successful_tar(self):
        self.assert_tree_setup_failure(
            self.NO_RSYNC + 'calls=0; rm() { return 0; }; '
            'tar() { : > "$RUNTIME/tar-reached"; return 0; }; '
            'mkdir() { calls=$((calls + 1)); [ "$calls" -eq 1 ]; }; ')
        self.assertFalse((self.runtime / "tar-reached").exists())


if __name__ == "__main__":
    unittest.main()
