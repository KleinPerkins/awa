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
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from consumer import finish_current as finish_ux
from engine import guard as engine_guard

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
        self._git("-C", str(self.repo), "remote", "add", "origin",
                  "git@github.com:KleinPerkins/awa-hook-wrap.git")
        self.policy = self.root / "policy.yml"
        self.policy.write_text(_POLICY.format(root=self.root), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _git(self, *args):
        subprocess.run(["git", *args], check=True, capture_output=True,
                       text=True, env=self._git_env)

    def _guard(self, command: str) -> dict:
        return self._guard_payload({"cwd": str(self.repo), "command": command})

    def _guard_payload(self, payload: dict, env_updates: dict | None = None) -> dict:
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
        proc = subprocess.run([str(_GUARD)], input=json.dumps(payload), capture_output=True,
                              text=True, env=env)
        return json.loads(proc.stdout)

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
        lib = _REPO / "kernel" / "lib" / "awa_policy.py"
        orig_mode = lib.stat().st_mode
        try:
            lib.chmod(0o000)
            resp = self._guard_payload({
                "command": "git commit -am x",
                "cwd": str(self.repo),
            })
            self.assertEqual(resp.get("permission"), "ask")
            self.assertIn("user_message", resp)
            self.assertIn("agent_message", resp)
        finally:
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
        proc = subprocess.run([str(_GUARD)], input="{not valid json",
                              capture_output=True, text=True, env=env, cwd=str(self.repo))
        resp = json.loads(proc.stdout)
        self.assertEqual(resp.get("permission"), "ask")
        self.assertIn("user_message", resp)
        self.assertIn("agent_message", resp)


if __name__ == "__main__":
    unittest.main()
