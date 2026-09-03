"""M1-C.1 hook observers preserve the guard and stay off its critical path."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


_ROOT = Path(__file__).resolve().parents[2]
_GUARD = _ROOT / "kernel" / "hooks" / "worktree-guard.sh"
_COMPOSITE = (
    _ROOT / "kernel" / "hooks" / "worktree-guard-with-integrity.sh"
)
_STOP = _ROOT / "kernel" / "hooks" / "awa-integrity-observer.sh"
_HANDOFF = _ROOT / "kernel" / "hooks" / "awa-session-handoff.sh"
_DETACHER = _ROOT / "engine" / "integrity_detach.py"
_ENGINE = _ROOT / "bin" / "awa-engine.sh"
_DETACHED_OBSERVER_DELAY_SECONDS = 60.0
_DETACHED_OBSERVER_TIMEOUT_SECONDS = 30.0
_HANG_TIMEOUT_SECONDS = 5.0
_HOOK_RETURN_TIMEOUT_SECONDS = 3.0
_IDENT = (
    "-c",
    "user.email=fixture@example.invalid",
    "-c",
    "user.name=Fixture",
)
_SAFE_FACTS = {
    "guard_primary_deny": True,
    "guard_cd_bypass_deny": True,
    "guard_linked_allow": True,
    "parity_ok": True,
    "hook_rows_present": True,
    "hook_fail_open": True,
    "mcp_matches": True,
    "release_matches": True,
    "recovery_last_status": "ok",
    "needs_repair": 0,
    "leases_unreconciled": 0,
    "sessions_dangling": 0,
    "husks": 0,
    "disposition_map": {},
    "handoff_state": "closed",
    "launchd_last_success_age_s": 0.0,
    "delivered": {"native": "accepted", "slack": "opted_out"},
}


class TestIntegrityHooks(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="awa-integrity-hooks.")
        self.root = Path(self._tmp.name)
        self.state_home = self.root / "state"
        self.tmpdir = self.root / "tmp with spaces"
        self.state_home.mkdir()
        self.tmpdir.mkdir()
        self.trace = self.root / "observer-trace.jsonl"
        self._observer_requested = False
        self.repo = self.root / "primary"
        self.repo.mkdir()
        self._git("init", "-q", str(self.repo))
        (self.repo / "f").write_text("base\n", encoding="utf-8")
        self._git("-C", str(self.repo), "add", "f")
        self._git("-C", str(self.repo), *_IDENT, "commit", "-qm", "init")
        self._git("-C", str(self.repo), "branch", "-M", "main")
        self._git(
            "-C",
            str(self.repo),
            "remote",
            "add",
            "origin",
            "https://example.invalid/fixture/repository.git",
        )
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
            encoding="utf-8",
        )
        self.fake_engine = self._write_fake_engine()
        self.env = self._base_env()

    def tearDown(self) -> None:
        try:
            if self._observer_requested:
                self._wait_for_records(1)
            self._stop_traced_processes()
        finally:
            self._tmp.cleanup()

    @staticmethod
    def _git(*args: str) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        for key in (
            "GIT_DIR",
            "GIT_WORK_TREE",
            "GIT_INDEX_FILE",
            "GIT_OBJECT_DIRECTORY",
            "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        ):
            env.pop(key, None)
        return subprocess.run(
            ["git", *args],
            check=True,
            capture_output=True,
            env=env,
        )

    def _base_env(self) -> dict[str, str]:
        env = os.environ.copy()
        for key in tuple(env):
            if key.startswith("AWA_") or key in {
                "CURSOR_BACKGROUND_AGENT",
                "CURSOR_CLOUD_AGENT",
                "IS_BACKGROUND_AGENT",
                "is_background_agent",
                "cloud_agent_identity_broker",
                "CURSOR_AGENT_IDENTITY_BROKER",
                "DEV_WORKTREE_GUARD_ALLOW_PRIMARY",
            }:
                env.pop(key, None)
        env.update(
            {
                "AWA_HOME": str(_ROOT),
                "AWA_GOVERNED_ROOT": str(self.root),
                "AWA_POLICY": str(self.policy),
                "AWA_INTEGRITY_ENGINE": str(self.fake_engine),
                "AWA_INTEGRITY_DEBOUNCE_SECONDS": "5",
                "AWA_INTEGRITY_OBSERVER_TIMEOUT_SECONDS": "2",
                "AWA_OBSERVER_TRACE": str(self.trace),
                "XDG_STATE_HOME": str(self.state_home),
                "TMPDIR": str(self.tmpdir),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        return env

    def _write_fake_engine(self) -> Path:
        bindir = self.root / "fake engine" / "bin"
        bindir.mkdir(parents=True)
        engine = bindir / "awa-engine.sh"
        engine.write_text(
            """#!/usr/bin/env python3
import json
import os
import sys
import time

record = {
    "argv": sys.argv[1:],
    "pid": os.getpid(),
    "sid": os.getsid(0),
    "fd_open": False,
}
fd_text = os.environ.get("AWA_TEST_INHERITED_FD", "")
if fd_text:
    try:
        os.write(int(fd_text), b"observer inherited caller fd")
    except OSError:
        pass
    else:
        record["fd_open"] = True
trace = os.environ.get("AWA_OBSERVER_TRACE")
if trace:
    with open(trace, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\\n")
        handle.flush()
mode = os.environ.get("AWA_FAKE_OBSERVER_MODE", "ok")
if mode == "hang":
    time.sleep(30)
elif mode == "sleep":
    time.sleep(float(os.environ.get("AWA_FAKE_OBSERVER_SLEEP", "0.5")))
elif mode == "crash":
    raise SystemExit(91)
raise SystemExit(0)
""",
            encoding="utf-8",
        )
        engine.chmod(0o755)
        return engine

    def _run(
        self,
        executable: Path,
        payload: bytes,
        *,
        env: dict[str, str] | None = None,
        pass_fds: tuple[int, ...] = (),
        timeout: float = 10,
    ) -> subprocess.CompletedProcess:
        if executable == _COMPOSITE:
            self._observer_requested = True
        argv = ["bash", str(executable)] if executable == _GUARD else [str(executable)]
        return subprocess.run(
            argv,
            input=payload,
            capture_output=True,
            env=env or self.env,
            pass_fds=pass_fds,
            timeout=timeout,
        )

    def _guard_pair(self, command: str):
        payload = json.dumps(
            {"cwd": str(self.repo), "command": command},
            separators=(",", ":"),
        ).encode("utf-8")
        standalone = self._run(_GUARD, payload)
        composite = self._run(_COMPOSITE, payload)
        return standalone, composite

    def _records(self) -> list[dict]:
        if not self.trace.exists():
            return []
        return [
            json.loads(line)
            for line in self.trace.read_text(encoding="utf-8").splitlines()
            if line
        ]

    def _wait_for_records(self, count: int, timeout: float = 3) -> list[dict]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            records = self._records()
            if len(records) >= count:
                return records
            time.sleep(0.02)
        return self._records()

    def _stop_traced_processes(self) -> None:
        pids = []
        for record in self._records():
            pid = record.get("pid")
            if type(pid) is not int:
                continue
            pids.append(pid)
            try:
                os.killpg(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                try:
                    os.kill(pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
        deadline = time.monotonic() + 1
        while any(self._pid_alive(pid) for pid in pids) and time.monotonic() < deadline:
            time.sleep(0.01)
        # Detached workers reap their engine child and exit immediately afterward.
        time.sleep(0.05)

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def test_beforeshell_returns_guard_bytes_verbatim(self):
        standalone, composite = self._guard_pair("git add f")
        self.assertIn(b'"permission": "deny"', standalone.stdout)
        self.assertEqual(composite.stdout, standalone.stdout)
        self.assertEqual(composite.stderr, standalone.stderr)
        self.assertEqual(composite.returncode, standalone.returncode)
        self.assertTrue(composite.stdout.endswith(b"\n"))

    def test_allow_payload_verbatim(self):
        standalone, composite = self._guard_pair("git status --short")
        self.assertEqual(json.loads(standalone.stdout), {"permission": "allow"})
        self.assertEqual(composite.stdout, standalone.stdout)
        self.assertEqual(composite.stderr, standalone.stderr)
        self.assertEqual(composite.returncode, standalone.returncode)
        self.assertTrue(composite.stdout.endswith(b"\n"))

    def test_guard_stderr_exit_and_trailing_newlines_verbatim(self):
        guard_dir = self.root / "guard with spaces"
        guard_dir.mkdir()
        guard = guard_dir / "standalone guard.sh"
        guard.write_text(
            "#!/usr/bin/env bash\n"
            "cat >/dev/null\n"
            "printf '{\"permission\":\"deny\"}\\n\\n'\n"
            "printf 'guard diagnostic\\n\\n' >&2\n"
            "exit 23\n",
            encoding="utf-8",
        )
        guard.chmod(0o755)
        env = dict(self.env)
        env["AWA_INTEGRITY_GUARD"] = str(guard)
        standalone = self._run(guard, b'{"command":"deny"}', env=env)
        composite = self._run(_COMPOSITE, b'{"command":"deny"}', env=env)
        self.assertEqual(composite.stdout, standalone.stdout)
        self.assertEqual(composite.stderr, standalone.stderr)
        self.assertEqual(composite.returncode, standalone.returncode)
        self.assertTrue(composite.stdout.endswith(b"\n\n"))
        self.assertTrue(composite.stderr.endswith(b"\n\n"))
        self.assertFalse(
            list(self.tmpdir.glob("awa-integrity-payload.*")),
            "composite payload temporary file leaked",
        )

    def test_observer_detached_nonblocking(self):
        read_fd, write_fd = os.pipe()
        self.addCleanup(os.close, read_fd)
        self.addCleanup(os.close, write_fd)
        os.set_inheritable(write_fd, True)
        env = dict(self.env)
        env.update(
            {
                "AWA_FAKE_OBSERVER_MODE": "sleep",
                "AWA_FAKE_OBSERVER_SLEEP": str(_DETACHED_OBSERVER_DELAY_SECONDS),
                "AWA_INTEGRITY_OBSERVER_TIMEOUT_SECONDS": str(
                    _DETACHED_OBSERVER_TIMEOUT_SECONDS
                ),
                "AWA_TEST_INHERITED_FD": str(write_fd),
            }
        )
        payload = json.dumps(
            {"cwd": str(self.repo), "command": "git status"},
            separators=(",", ":"),
        ).encode("utf-8")
        standalone = self._run(_GUARD, payload, env=env)
        result = self._run(
            _COMPOSITE,
            payload,
            env=env,
            pass_fds=(write_fd,),
            timeout=_HOOK_RETURN_TIMEOUT_SECONDS,
        )
        self.assertEqual(result.stdout, standalone.stdout)
        self.assertEqual(result.stderr, standalone.stderr)
        self.assertEqual(result.returncode, standalone.returncode)
        records = self._wait_for_records(1)
        self.assertEqual(len(records), 1)
        self.assertNotEqual(records[0]["sid"], os.getsid(0))
        self.assertFalse(records[0]["fd_open"])
        self.assertTrue(
            self._pid_alive(records[0]["pid"]),
            "observer exited before the detached hook returned",
        )
        source = _DETACHER.read_text(encoding="utf-8")
        self.assertIn("start_new_session=True", source)
        self.assertIn("close_fds=True", source)
        self.assertGreaterEqual(source.count("subprocess.DEVNULL"), 3)

    def test_observer_debounces(self):
        first = self._run(_COMPOSITE, b'{"command":"git status"}')
        second = self._run(_COMPOSITE, b'{"command":"git status"}')
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(len(self._wait_for_records(1)), 1)
        time.sleep(0.25)
        self.assertEqual(len(self._records()), 1)

    def test_hanging_observer_does_not_hang_hook(self):
        env = dict(self.env)
        env.update(
            {
                "AWA_FAKE_OBSERVER_MODE": "hang",
                "AWA_INTEGRITY_OBSERVER_TIMEOUT_SECONDS": str(_HANG_TIMEOUT_SECONDS),
            }
        )
        payload = json.dumps(
            {"cwd": str(self.repo), "command": "git status"},
            separators=(",", ":"),
        ).encode("utf-8")
        standalone = self._run(_GUARD, payload, env=env)
        composite = self._run(
            _COMPOSITE,
            payload,
            env=env,
            timeout=_HOOK_RETURN_TIMEOUT_SECONDS,
        )
        self.assertEqual(composite.stdout, standalone.stdout)
        self.assertEqual(composite.stderr, standalone.stderr)
        self.assertEqual(composite.returncode, standalone.returncode)
        records = self._wait_for_records(1)
        self.assertEqual(len(records), 1)
        pid = records[0]["pid"]
        self.assertTrue(
            self._pid_alive(pid),
            "observer timed out before the detached hook returned",
        )
        deadline = time.monotonic() + _HANG_TIMEOUT_SECONDS + 2
        while self._pid_alive(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertFalse(self._pid_alive(pid), "timed-out observer survived")

    def test_crashing_observer_does_not_affect_guard(self):
        env = dict(self.env)
        env["AWA_FAKE_OBSERVER_MODE"] = "crash"
        payload = b'{"command":"git status"}'
        standalone = self._run(_GUARD, payload, env=env)
        composite = self._run(_COMPOSITE, payload, env=env)
        self.assertEqual(composite.stdout, standalone.stdout)
        self.assertEqual(composite.stderr, standalone.stderr)
        self.assertEqual(composite.returncode, standalone.returncode)
        records = self._wait_for_records(1)
        self.assertEqual(len(records), 1)

    def test_stop_role_refreshes_status(self):
        env = dict(self.env)
        env.update(
            {
                "AWA_INTEGRITY_ENGINE": str(_ENGINE),
                "AWA_ENGINE_TEST_ACTIVE": "1",
                "AWA_INTEGRITY_TEST_FACTS_JSON": json.dumps(_SAFE_FACTS),
                "AWA_INTEGRITY_DEBOUNCE_SECONDS": "0",
                "AWA_INTEGRITY_OBSERVER_TIMEOUT_SECONDS": "5",
            }
        )
        seeded = subprocess.run(
            [
                str(_ENGINE),
                "integrity",
                "verify",
                "--profile",
                "deep",
                "--trigger",
                "launchd",
            ],
            capture_output=True,
            env=env,
            timeout=30,
        )
        self.assertEqual(seeded.returncode, 0, seeded.stderr)
        result = self._run(_STOP, b'{"hook_event_name":"stop"}', env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, b"")
        status_path = self.state_home / "awa" / "integrity" / "status.json"
        deadline = time.monotonic() + 5
        status = {}
        while time.monotonic() < deadline:
            try:
                status = json.loads(status_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                status = {}
            if status.get("trigger") == "stop":
                break
            time.sleep(0.05)
        self.assertEqual(status.get("trigger"), "stop")
        self.assertIsNotNone(status["triggers"]["stop"]["last_success"])

    def test_session_handoff_installed_dormant_noop(self):
        env = dict(self.env)
        before = sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*"))
        result = self._run(
            _HANDOFF,
            b'{"hook_event_name":"sessionStart","workspace_roots":[]}',
            env=env,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, b"")
        time.sleep(0.15)
        self.assertFalse(self.trace.exists())
        after = sorted(str(path.relative_to(self.root)) for path in self.root.rglob("*"))
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
