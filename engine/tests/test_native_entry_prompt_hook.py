"""Hard-deadline prompt adapter and finish-composite acceptance tests."""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from engine import native_entry_prompt_adapter as adapter


_ROOT = Path(__file__).resolve().parents[2]
_ADAPTER = _ROOT / "engine" / "native_entry_prompt_adapter.py"
_COMPOSITE = _ROOT / "kernel" / "hooks" / "before-submit-prompt-with-entry.sh"
_FINISH = _ROOT / "kernel" / "hooks" / "before-submit-prompt.sh"


class TestNativeEntryPromptAdapter(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="awa-prompt-adapter.")
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    @staticmethod
    def _alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def test_adapter_success_missing_and_failure_are_quiet(self) -> None:
        payload = b'{"prompt":"private-adapter-prompt"}'
        cases = (
            [sys.executable, "-c", "import sys; sys.stdin.buffer.read()"],
            [str(self.root / "missing-worker")],
            [sys.executable, "-c", "import sys; sys.exit(9)"],
        )
        for command in cases:
            with self.subTest(command=command):
                started = time.monotonic()
                result = adapter._supervise(
                    payload,
                    command=command,
                    budget_seconds=2.0,
                )
                self.assertIsNone(result)
                self.assertLess(time.monotonic() - started, 2.0)

    def test_adapter_deadline_kills_worker_process_group(self) -> None:
        pidfile = self.root / "pids.json"
        worker = self.root / "tree.py"
        worker.write_text(
            "import json,os,signal,subprocess,sys,time\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            "child=subprocess.Popen([sys.executable,'-c',"
            "'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            "time.sleep(30)'])\n"
            "open(sys.argv[1],'w').write(json.dumps([os.getpid(),child.pid]))\n"
            "sys.stdin.buffer.read()\n"
            "time.sleep(30)\n",
            encoding="utf-8",
        )
        started = time.monotonic()
        adapter._supervise(
            b'{"prompt":"never-in-argv-or-env-4f87"}',
            command=[sys.executable, str(worker), str(pidfile)],
            budget_seconds=2.0,
        )
        elapsed = time.monotonic() - started
        self.assertLessEqual(elapsed, 2.15)
        self.assertTrue(pidfile.is_file())
        pids = json.loads(pidfile.read_text(encoding="utf-8"))
        for _ in range(50):
            if not any(self._alive(pid) for pid in pids):
                break
            time.sleep(0.01)
        self.assertFalse(any(self._alive(pid) for pid in pids), pids)

    def test_adapter_cleans_descendants_after_worker_leader_exits(self) -> None:
        pidfile = self.root / "orphan-pids.json"
        worker = self.root / "orphan.py"
        worker.write_text(
            "import json,os,subprocess,sys,time\n"
            "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'])\n"
            "open(sys.argv[1],'w').write(json.dumps([os.getpid(),child.pid]))\n",
            encoding="utf-8",
        )
        pids: list[int] = []
        try:
            adapter._supervise(
                b'{"prompt":"leader-exit-cleanup"}',
                command=[sys.executable, str(worker), str(pidfile)],
                budget_seconds=1.0,
            )
            self.assertTrue(pidfile.is_file())
            pids = json.loads(pidfile.read_text(encoding="utf-8"))
            for _ in range(50):
                if not any(self._alive(pid) for pid in pids):
                    break
                time.sleep(0.01)
            self.assertFalse(any(self._alive(pid) for pid in pids), pids)
        finally:
            for pid in pids:
                with contextlib.suppress(ProcessLookupError):
                    os.kill(pid, signal.SIGKILL)

    def test_adapter_source_never_places_payload_in_argv_env_or_files(self) -> None:
        marker = "private-payload-marker-90e1"
        captured: dict = {}

        class FakeProcess:
            pid = os.getpid()

            def communicate(self, *, input, timeout):
                captured["input"] = input
                captured["timeout"] = timeout
                return b"", b""

            def poll(self):
                return 0

        def fake_popen(command, **kwargs):
            captured["command"] = command
            captured["kwargs"] = kwargs
            return FakeProcess()

        with mock.patch.object(
            adapter.subprocess,
            "Popen",
            side_effect=fake_popen,
        ), mock.patch.object(adapter, "_signal_group"):
            adapter._supervise(
                json.dumps({"prompt": marker}).encode(),
                command=[sys.executable, "-c", "pass"],
                budget_seconds=2.0,
            )
        self.assertEqual(
            captured["input"],
            json.dumps({"prompt": marker}).encode(),
        )
        self.assertNotIn(marker, "\0".join(captured["command"]))
        self.assertNotIn(
            marker,
            "\0".join(
                f"{key}={value}"
                for key, value in captured["kwargs"]["env"].items()
            ),
        )
        self.assertIs(captured["kwargs"]["close_fds"], True)
        self.assertIs(captured["kwargs"]["start_new_session"], True)
        self.assertEqual(captured["kwargs"]["stdout"], subprocess.DEVNULL)
        self.assertEqual(captured["kwargs"]["stderr"], subprocess.DEVNULL)

    def test_oversized_input_is_ignored_without_worker(self) -> None:
        with mock.patch.object(
            adapter,
            "_supervise",
            side_effect=AssertionError("worker must not start"),
        ):
            self.assertEqual(
                adapter.main(stdin=(b"x" * (adapter.MAX_PAYLOAD_BYTES + 1))),
                0,
            )


class TestBeforeSubmitPromptComposite(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="awa-prompt-hook.")
        self.root = Path(self._tmp.name)
        self.runtime = self.root / "runtime"
        hooks = self.runtime / "kernel" / "hooks"
        engine = self.runtime / "engine"
        consumer = self.runtime / "consumer"
        hooks.mkdir(parents=True)
        engine.mkdir()
        consumer.mkdir()
        shutil.copy2(_FINISH, hooks / _FINISH.name)
        shutil.copy2(_COMPOSITE, hooks / _COMPOSITE.name)
        shutil.copy2(_ADAPTER, engine / _ADAPTER.name)
        (engine / "__init__.py").write_text("", encoding="utf-8")
        (consumer / "finish_current.py").write_text(
            "#!/usr/bin/env python3\n"
            "import hashlib,json,sys\n"
            "raw=sys.stdin.buffer.read()\n"
            "mode=sys.argv[1]\n"
            "if mode=='hook':\n"
            " print(json.dumps({'continue':True,'payload_sha256':"
            "hashlib.sha256(raw).hexdigest()},sort_keys=True))\n",
            encoding="utf-8",
        )
        for path in (
            hooks / _FINISH.name,
            hooks / _COMPOSITE.name,
            consumer / "finish_current.py",
        ):
            path.chmod(0o700)
        self.env = {
            **os.environ,
            "HOME": str(self.root / "home"),
            "XDG_STATE_HOME": str(self.root / "state"),
            "PYTHONDONTWRITEBYTECODE": "1",
        }

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(self, script: Path, payload: bytes) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(script)],
            input=payload,
            capture_output=True,
            env=self.env,
            timeout=8,
        )

    def _assert_parity(self, payload: bytes) -> float:
        hooks = self.runtime / "kernel" / "hooks"
        expected = self._run(hooks / _FINISH.name, payload)
        started = time.monotonic()
        actual = self._run(hooks / _COMPOSITE.name, payload)
        elapsed = time.monotonic() - started
        self.assertEqual(
            (actual.returncode, actual.stdout, actual.stderr),
            (expected.returncode, expected.stdout, expected.stderr),
        )
        return elapsed

    def test_success_missing_failure_and_timeout_preserve_finish_bytes(self) -> None:
        payload = json.dumps(
            {
                "hook_event_name": "beforeSubmitPrompt",
                "workspace_roots": [str(self.root)],
                "conversation_id": "conversation",
                "generation_id": "generation",
                "prompt": "Close",
                "attachments": [],
            },
            separators=(",", ":"),
        ).encode()
        worker = self.runtime / "engine" / "native_entry.py"
        cases = {
            "success": "import sys; sys.stdin.buffer.read()\n",
            "failure": "raise SystemExit(7)\n",
            "killed": (
                "import os,signal\n"
                "os.kill(os.getpid(),signal.SIGKILL)\n"
            ),
            "timeout": (
                "import signal,time\n"
                "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                "time.sleep(30)\n"
            ),
        }
        for name, source in cases.items():
            with self.subTest(name=name):
                worker.write_text(source, encoding="utf-8")
                elapsed = self._assert_parity(payload)
                self.assertLessEqual(elapsed, 3.5)

        worker.write_text(
            "import sys; sys.stdin.buffer.read()\n",
            encoding="utf-8",
        )
        self.assertLess(
            self._assert_parity(payload + b"\n \t\r\n"),
            2.0,
        )
        oversized = (
            b'{"prompt":"'
            + (b"x" * (adapter.MAX_PAYLOAD_BYTES + 8192))
            + b'"}\n'
        )
        self.assertLess(self._assert_parity(oversized), 2.0)

        installed_adapter = self.runtime / "engine" / _ADAPTER.name
        adapter_bytes = installed_adapter.read_bytes()
        installed_adapter.write_text(
            "import os,signal\n"
            "os.kill(os.getpid(),signal.SIGKILL)\n",
            encoding="utf-8",
        )
        try:
            self.assertLess(self._assert_parity(payload), 1.5)
        finally:
            installed_adapter.write_bytes(adapter_bytes)

        worker.unlink()
        self.assertLess(self._assert_parity(payload), 2.0)
        absent_adapter = installed_adapter.with_suffix(".absent")
        installed_adapter.rename(absent_adapter)
        try:
            self.assertLess(self._assert_parity(payload), 1.5)
        finally:
            absent_adapter.rename(installed_adapter)


if __name__ == "__main__":
    unittest.main()
