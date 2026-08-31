"""Bash-hook parity for the option-aware wrapper-skip + brace-group fixes (#2, #7).

`engine/guard.py` and `kernel/hooks/worktree-guard.sh` ship TWO mirror implementations of the
mutating-command detector. `test_guard.py` proves the engine mirror; this drives the ACTUAL
bash hook (the load-bearing beforeShellExecution gate) end-to-end so a wrapper-obscured
mutation still returns the enforced `deny` on an included primary checkout — proving the kernel
mirror got the same fix. Cursor enforces `deny` (it treats `ask` as non-blocking — L4), so the
one case where prevention must happen returns deny; `ask` is retained only for genuine
uncertainty (unparseable payload), a Cloud/background agent degrades to allow, and afterFileEdit
allows (observation-only). No host dependency: a temp git repo under a temp governed root.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from consumer import finish_current as finish_ux
from engine import guard as engine_guard
from engine.tests.guard_boundary_profile import GUARD_BOUNDARY_CASES
from engine.tests.installed_guard_canaries import (
    full_installed_matrix_requested,
)
from engine.tests.git_guard_command_corpus import (
    GIT_MUTATING_FAMILY_COMMANDS,
    GIT_READONLY_FAMILY_COMMANDS,
    PRIMARY_MAINTENANCE_ALLOW_SHAPES,
    PRIMARY_MAINTENANCE_NEAR_MISS_DENY,
    PRIMARY_MAINTENANCE_STATE_ALLOW_CASES,
    PRIMARY_MAINTENANCE_STATE_CASES,
    PRIMARY_MAINTENANCE_UNRELATED_ALLOW,
)

_REPO = Path(__file__).resolve().parent.parent.parent
_GUARD = _REPO / "kernel" / "hooks" / "worktree-guard.sh"

_IDENT = ("-c", "user.email=49759187+KleinPerkins@users.noreply.github.com",
          "-c", "user.name=KleinPerkins")

_POLICY = """\
version: 1
governed_roots:
  - {root}
default: include
include:
  - '*'
exclude:
  - .
detectors:
  governed_markers:
    - _ops/POLICY.md
  foreign_hook_frameworks:
    - husky
"""


class TestBashGuardWrapperParity(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="awa-hook-wrap.")
        self.root = Path(self._tmp.name)
        self.repo = self.root / "proj"
        self.repo.mkdir()
        env = dict(os.environ)
        for k in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE",
                  "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES"):
            env.pop(k, None)
        self._git_env = env
        self._git("init", "-q", str(self.repo))
        (self.repo / "f").write_text("#\n", encoding="utf-8")
        self._git("-C", str(self.repo), "add", "f")
        self._git("-C", str(self.repo), *_IDENT, "commit", "-qm", "init")
        self._git("-C", str(self.repo), "branch", "-M", "main")
        self.remote = self.root / "origin.git"
        self._git("init", "-q", "--bare", str(self.remote))
        self._git("-C", str(self.repo), "remote", "add", "origin", str(self.remote))
        self._git("-C", str(self.repo), "push", "-q", "-u", "origin", "main")
        self.policy = self.root / "policy.yml"
        self.policy.write_text(_POLICY.format(root=self.root), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _git(self, *args):
        return subprocess.run(["git", *args], check=True, capture_output=True,
                              text=True, env=self._git_env)

    def _guard(
        self,
        command: str,
        *,
        repo: Path | None = None,
        guard_path: Path = _GUARD,
        env_updates: dict | None = None,
    ) -> dict:
        return self._guard_payload(
            {"cwd": str(repo or self.repo), "command": command},
            env_updates=env_updates,
            guard_path=guard_path,
        )

    def _guard_payload(
        self,
        payload: dict,
        env_updates: dict | None = None,
        guard_path: Path = _GUARD,
    ) -> dict:
        env = dict(os.environ)
        for name in (
                "CURSOR_BACKGROUND_AGENT", "CURSOR_CLOUD_AGENT", "IS_BACKGROUND_AGENT",
                "is_background_agent", "AWA_FORCE_CLOUD", "cloud_agent_identity_broker",
                "CURSOR_AGENT_IDENTITY_BROKER"):
            env.pop(name, None)
        env["AWA_GOVERNED_ROOT"] = str(self.root)
        env["AWA_POLICY"] = str(self.policy)
        if env_updates:
            env.update(env_updates)
        proc = subprocess.run([str(guard_path)], input=json.dumps(payload), capture_output=True,
                              text=True, env=env)
        return json.loads(proc.stdout)

    def _make_maintenance_repo(self, name: str):
        repo = self.root / name
        remote = self.root / "{0}.git".format(name)
        repo.mkdir()
        self._git("init", "-q", str(repo))
        (repo / "f").write_text("#\n", encoding="utf-8")
        self._git("-C", str(repo), "add", "f")
        self._git("-C", str(repo), *_IDENT, "commit", "-qm", "init")
        self._git("-C", str(repo), "branch", "-M", "main")
        self._git("init", "-q", "--bare", str(remote))
        self._git("-C", str(repo), "remote", "add", "origin", str(remote))
        self._git("-C", str(repo), "push", "-q", "-u", "origin", "main")
        return repo, remote

    def _advance_remote(self, remote: Path, name: str) -> None:
        source = self.root / "{0}-source".format(name)
        self._git("clone", "-q", str(remote), str(source))
        (source / "remote.txt").write_text("remote\n", encoding="utf-8")
        self._git("-C", str(source), "add", "-A")
        self._git("-C", str(source), *_IDENT, "commit", "-qm", "remote")
        self._git("-C", str(source), "push", "-q", "origin", "main")

    def _state_drift_git_environment(
        self,
        repo: Path,
        mutation: str,
        target_oid: str = "",
    ) -> dict:
        wrapper_dir = self.root / "state-drift-wrapper-{0}-{1}".format(
            mutation,
            repo.name,
        )
        wrapper_dir.mkdir()
        wrapper = wrapper_dir / "git"
        wrapper.write_text(
            "#!/bin/sh\n"
            "\"$AWA_TEST_M3B_REAL_GIT\" \"$@\"\n"
            "rc=$?\n"
            "trigger=no\n"
            "case \"$AWA_TEST_M3B_MUTATION:$*\" in\n"
            "  config:*\" config --null --list\"*|"
            "operation:*\" config --null --list\"*) trigger=yes ;;\n"
            "  head:*\" status --porcelain=v2 \"*|"
            "dirty:*\" status --porcelain=v2 \"*|"
            "upstream:*\" status --porcelain=v2 \"*) trigger=yes ;;\n"
            "esac\n"
            "if [ \"$trigger\" = yes ]; then\n"
            "    if (set -C; : >\"$AWA_TEST_M3B_ONCE\") 2>/dev/null; then\n"
            "      case \"$AWA_TEST_M3B_MUTATION\" in\n"
            "        head) printf '%s\\n' \"$AWA_TEST_M3B_TARGET\" "
            ">\"$AWA_TEST_M3B_REPO/.git/refs/heads/main\" ;;\n"
            "        dirty) printf 'drift\\n' >\"$AWA_TEST_M3B_REPO/drift\" ;;\n"
            "        upstream)\n"
            "          mkdir -p \"$AWA_TEST_M3B_REPO/.git/refs/remotes/origin\"\n"
            "          printf '%s\\n' \"$AWA_TEST_M3B_TARGET\" "
            ">\"$AWA_TEST_M3B_REPO/.git/refs/remotes/origin/main\"\n"
            "          ;;\n"
            "        config) printf '\\n# drift\\n' >>\"$AWA_TEST_M3B_REPO/.git/config\" ;;\n"
            "        operation) \"$AWA_TEST_M3B_REAL_GIT\" -C "
            "\"$AWA_TEST_M3B_REPO\" rev-parse HEAD "
            ">\"$AWA_TEST_M3B_REPO/.git/MERGE_HEAD\" ;;\n"
            "        *) exit 70 ;;\n"
            "      esac\n"
            "    fi\n"
            "fi\n"
            "exit \"$rc\"\n",
            encoding="utf-8",
        )
        wrapper.chmod(0o700)
        real_git = shutil.which("git")
        self.assertIsNotNone(real_git)
        return {
            "PATH": str(wrapper_dir) + os.pathsep + os.environ.get("PATH", ""),
            "AWA_TEST_M3B_REAL_GIT": str(real_git),
            "AWA_TEST_M3B_ONCE": str(wrapper_dir / "once"),
            "AWA_TEST_M3B_MUTATION": mutation,
            "AWA_TEST_M3B_REPO": str(repo),
            "AWA_TEST_M3B_TARGET": target_oid,
        }

    def _apply_primary_maintenance_state(
        self,
        repo: Path,
        remote: Path,
        case: str,
    ) -> None:
        git_dir = repo / ".git"
        if case == "dirty_tracked":
            (repo / "f").write_text("dirty\n", encoding="utf-8")
        elif case == "dirty_untracked":
            (repo / "untracked.txt").write_text("dirty\n", encoding="utf-8")
        elif case == "dirty_skip_worktree":
            self._git("-C", str(repo), "update-index", "--skip-worktree", "f")
            (repo / "f").write_text("hidden dirty\n", encoding="utf-8")
            self.assertEqual(
                self._git("-C", str(repo), "status", "--porcelain").stdout,
                "",
            )
        elif case == "dirty_assume_unchanged":
            self._git("-C", str(repo), "update-index", "--assume-unchanged", "f")
            (repo / "f").write_text("hidden dirty\n", encoding="utf-8")
            self.assertEqual(
                self._git("-C", str(repo), "status", "--porcelain").stdout,
                "",
            )
        elif case == "detached":
            self._git("-C", str(repo), "checkout", "-q", "--detach")
        elif case == "missing_upstream":
            subprocess.run(
                ["git", "-C", str(repo), "config", "--unset-all", "branch.main.remote"],
                capture_output=True,
                env=self._git_env,
            )
            subprocess.run(
                ["git", "-C", str(repo), "config", "--unset-all", "branch.main.merge"],
                capture_output=True,
                env=self._git_env,
            )
        elif case == "local_upstream":
            self._git("-C", str(repo), "config", "branch.main.remote", ".")
            self._git(
                "-C",
                str(repo),
                "config",
                "branch.main.merge",
                "refs/heads/main",
            )
        elif case == "unsafe_fetch_destination":
            self._git(
                "-C",
                str(repo),
                "config",
                "--unset-all",
                "remote.origin.fetch",
            )
            self._git(
                "-C",
                str(repo),
                "config",
                "--add",
                "remote.origin.fetch",
                "+refs/heads/*:refs/heads/*",
            )
        elif case == "stale_fetch_mapping":
            self._git(
                "-C",
                str(repo),
                "config",
                "--unset-all",
                "remote.origin.fetch",
            )
            self._git(
                "-C",
                str(repo),
                "config",
                "--add",
                "remote.origin.fetch",
                "+refs/heads/release/*:refs/remotes/origin/release/*",
            )
        elif case == "local_ahead":
            (repo / "local.txt").write_text("local\n", encoding="utf-8")
            self._git("-C", str(repo), "add", "-A")
            self._git("-C", str(repo), *_IDENT, "commit", "-qm", "local ahead")
        elif case == "diverged":
            (repo / "local.txt").write_text("local\n", encoding="utf-8")
            self._git("-C", str(repo), "add", "-A")
            self._git("-C", str(repo), *_IDENT, "commit", "-qm", "local side")
            self._advance_remote(remote, "diverged-{0}".format(repo.name))
            self._git("-C", str(repo), "fetch", "-q", "origin")
        elif case == "merge_in_progress":
            (git_dir / "MERGE_HEAD").write_text(
                self._git("-C", str(repo), "rev-parse", "HEAD").stdout,
                encoding="utf-8",
            )
        elif case == "rebase_in_progress":
            (git_dir / "rebase-merge").mkdir()
        elif case == "cherry_pick_in_progress":
            (git_dir / "CHERRY_PICK_HEAD").write_text(
                self._git("-C", str(repo), "rev-parse", "HEAD").stdout,
                encoding="utf-8",
            )
        elif case == "revert_in_progress":
            (git_dir / "REVERT_HEAD").write_text(
                self._git("-C", str(repo), "rev-parse", "HEAD").stdout,
                encoding="utf-8",
            )
        elif case == "am_in_progress":
            (git_dir / "rebase-apply").mkdir()
        elif case == "sequencer_in_progress":
            (git_dir / "sequencer").mkdir()
        elif case == "bisect_in_progress":
            (git_dir / "BISECT_LOG").write_text("bisect\n", encoding="utf-8")
        elif case in {"wrong_remote", "wrong_ref", "risky_environment"}:
            pass
        else:
            self.fail("unknown primary-maintenance state case: {0}".format(case))

    def _install_guard(self) -> Path:
        override = os.environ.get("AWA_TEST_INSTALLED_GUARD_OVERRIDE")
        if override:
            guard = Path(override)
            self.assertTrue(guard.is_file())
            return guard
        home = self.root / "installed-home"
        data = home / ".local" / "share"
        config = home / ".config"
        state = home / ".local" / "state"
        for path in (home, data, config, state):
            path.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        env.update(
            {
                "HOME": str(home),
                "XDG_DATA_HOME": str(data),
                "XDG_CONFIG_HOME": str(config),
                "XDG_STATE_HOME": str(state),
            }
        )
        subprocess.run(
            [str(_REPO / "install.sh")],
            cwd=str(_REPO),
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        installed = data / "awa" / "current" / "kernel" / "hooks" / "worktree-guard.sh"
        self.assertTrue(installed.is_file())
        return installed

    def test_wrapper_mutating_forms_deny(self):
        for cmd in ("nice -n 10 git commit -am x", "env -C /r git commit",
                    "env -i git commit", "sudo -u root git commit",
                    "xargs -I{} git commit", "xargs -I {} git commit",
                    "timeout 5 git commit", "timeout -s KILL 5 git commit",
                    "ionice -c 3 git commit", "chrt -b 0 git commit",
                    "stdbuf -oL git commit", "{ git commit; }",
                    "nice -n 10 rm -rf x",
                    'bash -c "git commit -am x"',
                    "builtin git commit",
                    "doas git commit",
                    'script -c "git commit" /dev/null'):
            resp = self._guard(cmd)
            self.assertEqual(resp.get("permission"), "deny", cmd)
            # frozen deny_shape
            self.assertIn("user_message", resp)
            self.assertIn("agent_message", resp)

    def test_wrapper_readonly_forms_allow(self):
        for cmd in ("timeout 5 git status", "nice -n 10 ls -la",
                    "sudo -u root git status", "{ git status; }",
                    'bash -c "git status"'):
            resp = self._guard(cmd)
            self.assertEqual(resp.get("permission"), "allow", cmd)

    def test_hook_allows_readonly_git_family_forms(self):
        for cmd in GIT_READONLY_FAMILY_COMMANDS:
            resp = self._guard(cmd)
            self.assertEqual(resp.get("permission"), "allow", cmd)

    def test_hook_still_denies_mutating_git_family_forms(self):
        for cmd in GIT_MUTATING_FAMILY_COMMANDS:
            resp = self._guard(cmd)
            self.assertEqual(resp.get("permission"), "deny", cmd)
            self.assertIn("user_message", resp)
            self.assertIn("agent_message", resp)

    def test_primary_maintenance_command_corpus_engine_source_installed_parity(self):
        installed = (
            self._install_guard()
            if full_installed_matrix_requested()
            else None
        )
        for expected, commands in (
            ("allow", PRIMARY_MAINTENANCE_ALLOW_SHAPES),
            ("allow", PRIMARY_MAINTENANCE_UNRELATED_ALLOW),
            ("deny", PRIMARY_MAINTENANCE_NEAR_MISS_DENY),
        ):
            for cmd in commands:
                with self.subTest(expected=expected, cmd=cmd):
                    engine = engine_guard.decide_shell(
                        str(self.repo),
                        cmd,
                        str(self.policy),
                    )
                    source = self._guard(cmd)
                    self.assertEqual(engine.permission, expected, (cmd, engine.reason))
                    self.assertEqual(source.get("permission"), expected, (cmd, source))
                    if installed is not None:
                        role_resolved = self._guard(cmd, guard_path=installed)
                        self.assertEqual(
                            role_resolved.get("permission"),
                            expected,
                            (cmd, role_resolved),
                        )
                    if expected == "deny":
                        self.assertIn(
                            engine.reason,
                            {
                                engine_guard._PRIMARY_MAINTENANCE_MESSAGES[
                                    "unsupported_form"
                                ],
                                engine_guard._PRIMARY_MAINTENANCE_MESSAGES[
                                    "wrong_upstream"
                                ],
                            },
                            cmd,
                        )
                        responses = [source]
                        if installed is not None:
                            responses.append(role_resolved)
                        for response in responses:
                            self.assertEqual(
                                response.get("user_message"),
                                engine.reason,
                                cmd,
                            )
                            self.assertEqual(
                                response.get("agent_message"),
                                engine.reason,
                                cmd,
                            )

    def test_primary_maintenance_state_corpus_engine_source_installed_parity(self):
        installed = (
            self._install_guard()
            if full_installed_matrix_requested()
            else None
        )
        for index, (case, cmd, reason_code) in enumerate(
            PRIMARY_MAINTENANCE_STATE_CASES
        ):
            with self.subTest(case=case, cmd=cmd):
                repo, remote = self._make_maintenance_repo(
                    "maintenance-state-{0}".format(index)
                )
                self._apply_primary_maintenance_state(repo, remote, case)
                env_updates = {"GIT_CONFIG_COUNT": "0"} if case == "risky_environment" else {}
                with mock.patch.dict(os.environ, env_updates):
                    engine = engine_guard.decide_shell(
                        str(repo),
                        cmd,
                        str(self.policy),
                    )
                source = self._guard(
                    cmd,
                    repo=repo,
                    env_updates=env_updates,
                )
                message = engine_guard._PRIMARY_MAINTENANCE_MESSAGES[reason_code]
                self.assertEqual(engine.permission, "deny", (case, engine.reason))
                self.assertEqual(engine.reason, message, case)
                responses = [source]
                if installed is not None:
                    responses.append(
                        self._guard(
                            cmd,
                            repo=repo,
                            guard_path=installed,
                            env_updates=env_updates,
                        )
                    )
                for response in responses:
                    self.assertEqual(response.get("permission"), "deny", (case, response))
                    self.assertEqual(response.get("user_message"), message, case)
                    self.assertEqual(response.get("agent_message"), message, case)

    def test_primary_fetch_state_allow_corpus_engine_source_installed_parity(self):
        installed = (
            self._install_guard()
            if full_installed_matrix_requested()
            else None
        )
        for index, (case, cmd) in enumerate(PRIMARY_MAINTENANCE_STATE_ALLOW_CASES):
            with self.subTest(case=case, cmd=cmd):
                repo, remote = self._make_maintenance_repo(
                    "maintenance-fetch-state-{0}".format(index)
                )
                self._apply_primary_maintenance_state(repo, remote, case)
                engine = engine_guard.decide_shell(
                    str(repo),
                    cmd,
                    str(self.policy),
                )
                source = self._guard(cmd, repo=repo)
                self.assertEqual(engine.permission, "allow", (case, engine.reason))
                self.assertEqual(source, {"permission": "allow"}, case)
                if installed is not None:
                    role_resolved = self._guard(
                        cmd,
                        repo=repo,
                        guard_path=installed,
                    )
                    self.assertEqual(role_resolved, {"permission": "allow"}, case)

    def test_primary_maintenance_hook_state_drift_uses_uncertainty_path(self):
        installed = self._install_guard()
        message = engine_guard._PRIMARY_MAINTENANCE_MESSAGES[
            "inspection_failed"
        ]
        for index, mutation in enumerate(
            ("head", "dirty", "upstream", "config", "operation")
        ):
            for boundary, guard_path in (
                ("source", _GUARD),
                ("installed", installed),
            ):
                with self.subTest(mutation=mutation, boundary=boundary):
                    repo, remote = self._make_maintenance_repo(
                        "hook-drift-{0}-{1}".format(index, boundary)
                    )
                    target_oid = ""
                    if mutation in {"head", "upstream"}:
                        self._advance_remote(
                            remote,
                            "hook-drift-{0}-{1}".format(index, boundary),
                        )
                        target_oid = self._git(
                            "-C",
                            str(repo),
                            "ls-remote",
                            "origin",
                            "refs/heads/main",
                        ).stdout.split()[0]
                        self._git(
                            "-C",
                            str(repo),
                            "fetch",
                            "-q",
                            "--no-write-fetch-head",
                            str(remote),
                            target_oid,
                        )
                    response = self._guard(
                        "git fetch",
                        repo=repo,
                        guard_path=guard_path,
                        env_updates=self._state_drift_git_environment(
                            repo,
                            mutation,
                            target_oid,
                        ),
                    )
                    self.assertEqual(response.get("permission"), "deny", response)
                    self.assertEqual(response.get("user_message"), message)
                    self.assertEqual(response.get("agent_message"), message)

    def test_primary_maintenance_hook_second_invocation_observes_dirty_state(self):
        installed = self._install_guard()
        for boundary, guard_path in (
            ("source", _GUARD),
            ("installed", installed),
        ):
            with self.subTest(boundary=boundary):
                repo, _remote = self._make_maintenance_repo(
                    "hook-live-dirty-{0}".format(boundary)
                )
                self.assertEqual(
                    self._guard(
                        "git fetch",
                        repo=repo,
                        guard_path=guard_path,
                    ),
                    {"permission": "allow"},
                )
                (repo / "dirty").write_text("dirty\n", encoding="utf-8")
                response = self._guard(
                    "git fetch",
                    repo=repo,
                    guard_path=guard_path,
                )
                self.assertEqual(response.get("permission"), "deny", response)
                self.assertEqual(
                    response.get("user_message"),
                    engine_guard._PRIMARY_MAINTENANCE_MESSAGES["dirty"],
                )

    def test_incomplete_hook_context_preserves_uncached_fallback_verdict(self):
        installed = self._install_guard()
        wrapper_dir = self.root / "incomplete-context-wrapper"
        wrapper_dir.mkdir()
        wrapper = wrapper_dir / "git"
        real_git = shutil.which("git")
        self.assertIsNotNone(real_git)
        wrapper.write_text(
            "#!/bin/sh\n"
            "case \" $* \" in\n"
            "  *\" status --porcelain=v2 \"*) exit 70 ;;\n"
            "esac\n"
            "exec \"$AWA_TEST_M3B_REAL_GIT\" \"$@\"\n",
            encoding="utf-8",
        )
        wrapper.chmod(0o700)
        env_updates = {
            "PATH": str(wrapper_dir) + os.pathsep + os.environ.get("PATH", ""),
            "AWA_TEST_M3B_REAL_GIT": str(real_git),
        }
        for boundary, guard_path in (
            ("source", _GUARD),
            ("installed", installed),
        ):
            with self.subTest(boundary=boundary):
                repo, _remote = self._make_maintenance_repo(
                    "hook-context-fallback-{0}".format(boundary)
                )
                self.assertEqual(
                    self._guard(
                        "git fetch",
                        repo=repo,
                        guard_path=guard_path,
                        env_updates=env_updates,
                    ),
                    {"permission": "allow"},
                )
                (repo / "dirty").write_text("dirty\n", encoding="utf-8")
                denied = self._guard(
                    "git fetch",
                    repo=repo,
                    guard_path=guard_path,
                    env_updates=env_updates,
                )
                self.assertEqual(denied.get("permission"), "deny", denied)
                self.assertEqual(
                    denied.get("user_message"),
                    engine_guard._PRIMARY_MAINTENANCE_MESSAGES["dirty"],
                )

    def test_m3_profile_manifest_matches_source_and_installed_permissions(self):
        installed = self._install_guard()
        for index, case in enumerate(GUARD_BOUNDARY_CASES):
            with self.subTest(case=case.label):
                repo, remote = self._make_maintenance_repo(
                    "m3-profile-{0}".format(index)
                )
                if case.state_fixture != "clean":
                    self._apply_primary_maintenance_state(
                        repo,
                        remote,
                        case.state_fixture,
                    )
                source = self._guard(case.command, repo=repo)
                role_resolved = self._guard(
                    case.command,
                    repo=repo,
                    guard_path=installed,
                )
                self.assertEqual(
                    source.get("permission"),
                    case.expected_permission,
                    (case.label, source),
                )
                self.assertEqual(
                    role_resolved.get("permission"),
                    case.expected_permission,
                    (case.label, role_resolved),
                )

    def test_hook_internal_parser_failure_still_fails_open(self):
        shim_dir = self.root / "python-failure-shim"
        shim_dir.mkdir()
        shim = shim_dir / "python3"
        shim.write_text(
            "#!/bin/sh\n"
            "if [ -n \"${HOOK_INPUT:-}\" ]; then exit 70; fi\n"
            + "exec \"{0}\" \"$@\"\n".format(
                subprocess.list2cmdline([os.sys.executable])
            ),
            encoding="utf-8",
        )
        shim.chmod(0o755)
        response = self._guard(
            "git fetch",
            env_updates={
                "PATH": "{0}:{1}".format(shim_dir, os.environ.get("PATH", "")),
            },
        )
        self.assertEqual(response, {"permission": "allow"})

    def test_hook_git_family_target_ambiguity_denies(self):
        for cmd in (
            "git branch -C /tmp copied",
            f"git -C /tmp config --file {self.repo}/.git/config user.name changed",
            f"git -C /tmp submodule foreach 'rm -rf {self.repo}'",
            f"git -C /tmp push {self.repo} HEAD:refs/heads/changed",
        ):
            resp = self._guard(cmd)
            self.assertEqual(resp.get("permission"), "deny", cmd)
            self.assertIn("user_message", resp)
            self.assertIn("agent_message", resp)

    def test_hook_keeps_python_39_compatible_annotations(self):
        hook_source = _GUARD.read_text(encoding="utf-8")
        self.assertNotIn(" | None", hook_source)

    def test_empty_cwd_falls_back_to_workspace_roots(self):
        """Regression (incident 2026-07-06): Cursor's REAL beforeShellExecution payload sends
        `cwd: ""` plus `workspace_roots: [...]` (plural, snake_case, a list) whenever the
        caller relies on the chat's default root instead of an explicit override — the common
        case for a chat rooted directly in the target checkout. The old fallback chain only
        checked `workspaceRoot` (singular, camelCase, absent from the real payload) and fell
        through to `os.getcwd()` (the hook script's OWN directory, never the target repo),
        silently misclassifying an included primary as outside any governed root -> ALLOW.
        This must DENY, exactly like the explicit-cwd form."""
        resp = self._guard_payload({
            "command": "git commit -am x",
            "cwd": "",
            "workspace_roots": [str(self.repo)],
        })
        self.assertEqual(resp.get("permission"), "deny")
        self.assertIn("user_message", resp)
        self.assertIn("agent_message", resp)

    def test_missing_cwd_key_falls_back_to_workspace_roots(self):
        """Same fix, payload shape with no `cwd` key at all (not just empty string)."""
        resp = self._guard_payload({
            "command": "git commit -am x",
            "workspace_roots": [str(self.repo)],
        })
        self.assertEqual(resp.get("permission"), "deny")

    def test_workspace_roots_readonly_still_allows(self):
        """The gate must not over-deny: a read-only command via workspace_roots allows."""
        resp = self._guard_payload({
            "command": "git status",
            "cwd": "",
            "workspace_roots": [str(self.repo)],
        })
        self.assertEqual(resp.get("permission"), "allow")

    def test_same_conversation_mode_transition_is_rechecked(self):
        """Incident 2026-07-15 classification lock: AWA has no per-chat guard cache.

        Reuse the exact conversation/session payload while changing only the tool-owned
        mode file. Each hook process must resolve current policy again: OFF allows, then
        restored ON denies. This does not simulate Cursor spawning the hook; it proves
        the AWA code path cannot preserve the earlier OFF decision in chat-local state.
        """
        modes = self.root / "modes.yml"
        self.policy.write_text(
            _POLICY.format(root=self.root) + "modes_file: modes.yml\n",
            encoding="utf-8",
        )
        payload = {
            "conversation_id": "same-conversation",
            "session_id": "same-conversation",
            "generation_id": "mode-transition",
            "command": "git commit --allow-empty -m mode-transition",
            "cwd": "",
            "workspace_roots": [str(self.repo)],
        }

        modes.write_text(
            "schema: awa-modes/v1\ndefault_mode: on\nmodes:\n  proj: off\n",
            encoding="utf-8",
        )
        self.assertEqual(self._guard_payload(payload).get("permission"), "allow")

        modes.write_text(
            "schema: awa-modes/v1\ndefault_mode: on\nmodes:\n  proj: on\n",
            encoding="utf-8",
        )
        response = self._guard_payload(payload)
        self.assertEqual(response.get("permission"), "deny")
        self.assertIn("user_message", response)
        self.assertIn("agent_message", response)

    def test_cloud_background_agent_payload_allows(self):
        """Cloud/background agent degrades to ALLOW *before* the deny branch: a Cursor Cloud VM
        is an already-isolated, own-branch clone — a mutating command there must not be blocked.
        Signalled here by the payload `is_background_agent` flag."""
        resp = self._guard_payload({
            "command": "git commit -am x",
            "cwd": str(self.repo),
            "is_background_agent": True,
        })
        self.assertEqual(resp.get("permission"), "allow")

    def test_cloud_push_allow_response_contains_no_instruction_or_authorization(self):
        """Cloud is outside the primary-checkout gate: AWA returns only permission=allow.

        It does not prompt the model to push, represent operator authorization, or originate any
        commit/push reminder. Prompt provenance and the agent's later command choice are host-side.
        """
        resp = self._guard_payload({
            "command": "git push origin main",
            "cwd": str(self.repo),
            "is_background_agent": True,
        })
        self.assertEqual(resp, {"permission": "allow"})

    def test_cloud_identity_broker_payload_allows(self):
        """Same degrade-to-allow, signalled by a present cloud_agent_identity_broker handle."""
        resp = self._guard_payload({
            "command": "git commit -am x",
            "cwd": str(self.repo),
            "cloud_agent_identity_broker": "broker-handle-xyz",
        })
        self.assertEqual(resp.get("permission"), "allow")

    def test_false_broker_payload_does_not_allow(self):
        """Desktop sessionStart often carries broker:false — must NOT cloud-degrade."""
        for broker in (False, 0, "false", "0", ""):
            with self.subTest(broker=broker):
                resp = self._guard_payload({
                    "command": "git commit -am x",
                    "cwd": str(self.repo),
                    "cloud_agent_identity_broker": broker,
                })
                self.assertEqual(resp.get("permission"), "deny", broker)

    def test_false_broker_env_does_not_allow(self):
        env = dict(os.environ)
        env["AWA_GOVERNED_ROOT"] = str(self.root)
        env["AWA_POLICY"] = str(self.policy)
        env["cloud_agent_identity_broker"] = "false"
        proc = subprocess.run([str(_GUARD)],
                              input=json.dumps({"command": "git commit -am x", "cwd": str(self.repo)}),
                              capture_output=True, text=True, env=env)
        self.assertEqual(json.loads(proc.stdout).get("permission"), "deny")

    def test_background_and_broker_context_parity_matrix(self):
        affirmative = (True, 1, "true", "opaque-handle", {"handle": "opaque"}, ["opaque"])
        false_like = (None, False, 0, "", "false", "0", "no", "off", {}, [])
        base = {"command": "git commit -am x", "cwd": str(self.repo)}
        for field in ("is_background_agent", "cloud_agent_identity_broker"):
            for nested in (False, True):
                for value, expected in (
                        *((item, True) for item in affirmative),
                        *((item, False) for item in false_like)):
                    with self.subTest(
                            field=field, nested=nested, value=repr(value)):
                        payload = dict(base)
                        if nested:
                            payload["tool_input"] = {field: value}
                        else:
                            payload[field] = value
                        permission = self._guard_payload(payload).get("permission")
                        self.assertEqual(permission, "allow" if expected else "deny")
                        self.assertEqual(finish_ux._unsupported(payload), expected)

            for value, expected in (
                    ("opaque-env-handle", True), ("true", True), ("1", True),
                    ("", False), ("false", False), ("0", False),
                    ("no", False), ("off", False)):
                with self.subTest(field=field, environment=value):
                    permission = self._guard_payload(
                        base, env_updates={field: value}).get("permission")
                    self.assertEqual(permission, "allow" if expected else "deny")
                    with mock.patch.dict(
                            os.environ, {field: value}, clear=True):
                        self.assertEqual(
                            engine_guard._is_cloud(str(self.repo)), expected)
                        self.assertEqual(finish_ux._unsupported(base), expected)

    def test_classifier_unavailable_asks_not_denies(self):
        """classify_context fail-safe (include + reason fail-safe: ask) must ASK, not DENY."""
        installed = self._install_guard()
        for label, guard, lib in (
            ("source", _GUARD, _REPO / "kernel" / "lib" / "awa_policy.py"),
            (
                "installed",
                installed,
                installed.parent.parent / "lib" / "awa_policy.py",
            ),
        ):
            with self.subTest(boundary=label):
                override = (
                    label == "installed"
                    and os.environ.get("AWA_TEST_INSTALLED_GUARD_OVERRIDE")
                )
                orig_mode = None if override else lib.stat().st_mode
                try:
                    if orig_mode is not None:
                        lib.chmod(0o000)
                    resp = self._guard_payload(
                        {
                            "command": "git commit -am x",
                            "cwd": str(self.repo),
                        },
                        guard_path=guard,
                    )
                    self.assertEqual(resp.get("permission"), "ask")
                    self.assertIn("user_message", resp)
                    self.assertIn("agent_message", resp)
                finally:
                    if orig_mode is not None:
                        lib.chmod(orig_mode)

    def test_cloud_env_flag_allows(self):
        """Same degrade-to-allow, signalled by an env flag (AWA_FORCE_CLOUD)."""
        env = dict(os.environ)
        env["AWA_GOVERNED_ROOT"] = str(self.root)
        env["AWA_POLICY"] = str(self.policy)
        env["AWA_FORCE_CLOUD"] = "1"
        proc = subprocess.run([str(_GUARD)],
                              input=json.dumps({"command": "git commit -am x", "cwd": str(self.repo)}),
                              capture_output=True, text=True, env=env)
        self.assertEqual(json.loads(proc.stdout).get("permission"), "allow")

    def test_after_file_edit_allows(self):
        """afterFileEdit is observation-only (Cursor ignores any permission there — L4): a file
        edit on an included primary must ALLOW (the hook records a detection receipt, never a
        no-op ask/deny). Payload carries a file path and NO command."""
        resp = self._guard_payload({
            "hook_event_name": "afterFileEdit",
            "cwd": str(self.repo),
            "file_path": str(self.repo / "f"),
        })
        self.assertEqual(resp.get("permission"), "allow")

    def test_unparseable_payload_on_included_primary_asks(self):
        """Genuine uncertainty is retained as `ask` (an honest no-op — Cursor ignores it, so it
        never silently downgrades to allow, but never pretends to block): an UNPARSEABLE payload
        whose resolved cwd is an included primary returns ask, not deny."""
        env = dict(os.environ)
        env["AWA_GOVERNED_ROOT"] = str(self.root)
        env["AWA_POLICY"] = str(self.policy)
        installed = self._install_guard()
        for label, guard in (("source", _GUARD), ("installed", installed)):
            with self.subTest(boundary=label):
                proc = subprocess.run(
                    [str(guard)],
                    input="{not valid json",
                    capture_output=True,
                    text=True,
                    env=env,
                    cwd=str(self.repo),
                )
                resp = json.loads(proc.stdout)
                self.assertEqual(resp.get("permission"), "ask")
                self.assertIn("user_message", resp)
                self.assertIn("agent_message", resp)

    # ---- ADR 0001: target-path-aware mutation scope (bash-hook parity) ---------
    def test_target_outside_governed_root_allows(self):
        outside = os.path.join(tempfile.gettempdir(), "awa-guard-precision-hook-outside.txt")
        resp = self._guard("rm -f %s" % outside)
        self.assertEqual(resp.get("permission"), "allow")

    def test_target_inside_primary_still_denies(self):
        resp = self._guard("rm -f f")
        self.assertEqual(resp.get("permission"), "deny")
        # frozen deny_shape
        self.assertIn("user_message", resp)
        self.assertIn("agent_message", resp)

    def test_git_dash_c_target_parity(self):
        other = self.root / "other-repo"
        other.mkdir()
        self._git("init", "-q", str(other))
        (other / "f").write_text("#\n", encoding="utf-8")
        self._git("-C", str(other), "add", "f")
        self._git("-C", str(other), *_IDENT, "commit", "-qm", "init")
        self._git("-C", str(other), "remote", "add", "origin",
                  "git@github.com:KleinPerkins/awa-hook-wrap-other.git")
        resp = self._guard("git -C %s commit -am x" % other)
        self.assertEqual(resp.get("permission"), "deny")

        wt = self.root / "proj.wt"
        self._git("-C", str(self.repo), "worktree", "add", "-q", "-b", "feat/x", str(wt), "main")
        resp2 = self._guard("git -C %s commit -am x" % wt)
        self.assertEqual(resp2.get("permission"), "allow")

    def test_git_dir_flag_not_masked_by_trailing_safe_work_tree(self):
        """A trailing safe --work-tree must not launder an earlier --git-dir that still
        points at the protected primary: git honors BOTH flags together, so the commit's
        objects/refs still land in the protected primary's git-dir even though the
        checked-out files come from the safe work tree. Bash-hook parity for
        engine/tests/test_guard.py's identical regression."""
        safe_wt = tempfile.mkdtemp(prefix="awa-hook-wrap-safe-wt.")
        try:
            resp = self._guard(
                "git --git-dir=%s/.git --work-tree=%s commit -am x" % (self.repo, safe_wt))
            self.assertEqual(resp.get("permission"), "deny")
        finally:
            shutil.rmtree(safe_wt, ignore_errors=True)

    # ---- ADR 0001 §2/§4: .git-internal targets are inside the protected primary ----
    # Parity for engine/tests/test_guard.py: git's own --is-inside-work-tree semantics
    # exclude .git/, so `classify_dir` (cd .git && dev-worktree.sh status) returns a
    # non-empty "classification: not-git" that was (wrongly) trusted as "not protected"
    # -> `rm -rf .git/objects` on a protected primary was ALLOWED. Reattribution to the
    # enclosing work tree fixes both mirrors identically.
    def test_dotgit_internal_targets_deny(self):
        for rel in (".git", ".git/config", ".git/HEAD", ".git/refs",
                    ".git/objects", ".git/objects/pack", ".git/hooks/pre-commit"):
            resp = self._guard("rm -rf %s" % rel)
            self.assertEqual(resp.get("permission"), "deny", rel)
            # frozen deny_shape
            self.assertIn("user_message", resp)
            self.assertIn("agent_message", resp)

    def test_dotgit_internal_target_in_excluded_repo_allows(self):
        """No over-blocking (requirement 1): a .git-internal path inside a NON-included
        (here self-governed -> exclude) repo must still ALLOW -- reattribution classifies
        the ENCLOSING repo normally, it does not blanket-deny every .git-shaped path."""
        excluded = self.root / "excluded"
        excluded.mkdir()
        self._git("init", "-q", str(excluded))
        (excluded / "f").write_text("#\n", encoding="utf-8")
        (excluded / "_ops").mkdir()
        (excluded / "_ops" / "POLICY.md").write_text("policy\n", encoding="utf-8")
        self._git("-C", str(excluded), "add", "-A")
        self._git("-C", str(excluded), *_IDENT, "commit", "-qm", "init")
        self._git("-C", str(excluded), "remote", "add", "origin",
                  "git@github.com:KleinPerkins/awa-hook-wrap-excluded.git")
        for rel in ("", "objects", "config"):
            target = excluded / ".git" / rel if rel else excluded / ".git"
            resp = self._guard("rm -rf %s" % target)
            self.assertEqual(resp.get("permission"), "allow", rel)

    def test_linked_worktree_dotgit_file_target_allows(self):
        """Requirement 3: a linked worktree's .git is a FILE, redirected to the worktree
        root (a Safe Workspace) by dir_for_probe BEFORE reattribution -> stays ALLOW."""
        wt = self.root / "proj.wt"
        self._git("-C", str(self.repo), "worktree", "add", "-q", "-b", "feat/dg", str(wt), "main")
        self.assertTrue((wt / ".git").is_file())  # sanity: worktree .git really is a file
        resp = self._guard("rm -rf %s" % (wt / ".git"))
        self.assertEqual(resp.get("permission"), "allow")


if __name__ == "__main__":
    unittest.main()
