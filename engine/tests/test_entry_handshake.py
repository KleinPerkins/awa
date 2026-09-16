"""M2.4 metadata-only Safe-Workspace handoff acceptance tests."""

from __future__ import annotations

import json
import os
import fcntl
import stat
import subprocess
import threading
import unittest
from pathlib import Path
from unittest import mock

from engine import integrity
from engine.tests.helpers import EngineTestCase, git
from kernel.lib import awa_handoff


_ROOT = Path(__file__).resolve().parents[2]
_ENSURE = _ROOT / "kernel" / "bin" / "dev-worktree.sh"
_HOOK = _ROOT / "kernel" / "hooks" / "awa-session-handoff.sh"


class TestEntryHandshake(EngineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.repo = Path(self.make_seeded_repo("handoff-source"))
        self.policy = Path(self._tmp.name) / "policy.yml"
        self.policy.write_text(
            "version: 1\n"
            f"governed_roots:\n  - {self.repo.parent}\n"
            "default: include\n"
            "default_mode: on\n"
            "include:\n  - '*'\n"
            "exclude: []\n",
            encoding="utf-8",
        )
        self.env = {
            **os.environ,
            "HOME": str(Path(self._tmp.name) / "home"),
            "XDG_STATE_HOME": str(self.state_home),
            "XDG_DATA_HOME": str(Path(self._tmp.name) / "data"),
            "XDG_CONFIG_HOME": str(Path(self._tmp.name) / "config"),
            "AWA_POLICY": str(self.policy),
            "AWA_GOVERNED_ROOT": str(self.repo.parent),
            "PYTHONDONTWRITEBYTECODE": "1",
        }

    def _ensure(self, name: str = "one", *, json_output: bool = False):
        target = Path(self._tmp.name) / "worktrees" / name
        command = [
            "bash",
            str(_ENSURE),
            "ensure",
            "--branch",
            f"feat/{name}",
            "--path",
            str(target),
        ]
        if json_output:
            command.append("--json")
        result = subprocess.run(
            command,
            cwd=self.repo,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result, target

    def _hook(self, payload: object, *, cwd: Path, env: dict | None = None):
        return subprocess.run(
            ["bash", str(_HOOK)],
            input=json.dumps(payload),
            cwd=cwd,
            env=env or self.env,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_ensure_records_handoff_intent_not_success(self):
        result, target = self._ensure(json_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["action"], "created")
        self.assertEqual(output["handoff"], "pending")
        self.assertEqual(output["rootPath"], str(target.resolve()))
        self.assertNotIn("move_agent_to_root", output)
        self.assertNotIn("success", result.stdout.lower())
        self.assertNotIn("mover", result.stdout.lower())

        record = awa_handoff.read_record()
        self.assertEqual(record["status"], "pending")
        self.assertEqual(record["root"], str(target.resolve()))
        self.assertEqual(record["branch"], "feat/one")
        self.assertEqual(record["head"], git(str(target), "rev-parse", "HEAD").stdout.strip())
        self.assertEqual(
            record["git_common_dir"],
            str(Path(git(str(target), "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()).resolve()),
        )
        self.assertEqual(
            set(record),
            {
                "schema",
                "handoff_id",
                "generation",
                "status",
                "root",
                "branch",
                "git_common_dir",
                "head",
                "timestamp",
            },
        )
        path = awa_handoff.record_path()
        raw = path.read_text(encoding="utf-8")
        for forbidden in ("prompt", "operator", "environment", "secret", "session_success"):
            self.assertNotIn(forbidden, raw)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)

    def test_ensure_copy_requires_agents_window_worktree_selection(self):
        result, target = self._ensure()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Cursor Agents Window", result.stdout)
        self.assertIn("Worktree", result.stdout)
        self.assertIn(str(target.resolve()), result.stdout)
        self.assertNotIn("move_agent_to_root", result.stdout)
        self.assertNotIn("relocat", result.stdout.lower())

    def test_sessionstart_exact_match_closes_and_absent_is_quiet(self):
        absent = self._hook(
            {"hook_event_name": "sessionStart", "workspace_roots": [str(self.repo)]},
            cwd=self.repo,
        )
        self.assertEqual((absent.returncode, absent.stdout, absent.stderr), (0, "", ""))

        _, target = self._ensure()
        closed = self._hook(
            {"hook_event_name": "sessionStart", "workspace_roots": [str(target)]},
            cwd=target,
        )
        self.assertEqual((closed.returncode, closed.stdout, closed.stderr), (0, "", ""))
        record = awa_handoff.read_record()
        self.assertEqual(record["status"], "closed")
        self.assertEqual(integrity._collect_facts(None, profile="fast", now=1.0).handoff_state, "closed")

    def test_mismatch_malformed_ambiguous_drift_and_symlink_preserve_fail_open(self):
        _, target = self._ensure()
        pending = awa_handoff.read_record()
        variants = [
            {"hook_event_name": "sessionStart", "workspace_roots": [str(self.repo)]},
            {
                "hook_event_name": "sessionStart",
                "workspace_roots": [str(target), str(self.repo)],
            },
            {"hook_event_name": "sessionStart", "workspace_roots": [123]},
        ]
        for payload in variants:
            with self.subTest(payload=payload):
                result = self._hook(payload, cwd=target)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(awa_handoff.read_record(), pending)

        git(str(target), "checkout", "-q", "-b", "feat/drift")
        result = self._hook(
            {"hook_event_name": "sessionStart", "workspace_roots": [str(target)]},
            cwd=target,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(awa_handoff.read_record(), pending)

        record_path = awa_handoff.record_path()
        saved = record_path.read_bytes()
        record_path.unlink()
        symlink_target = record_path.parent / "outside.json"
        symlink_target.write_bytes(saved)
        record_path.symlink_to(symlink_target)
        result = self._hook(
            {"hook_event_name": "sessionStart", "workspace_roots": [str(target)]},
            cwd=target,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(symlink_target.read_bytes(), saved)
        self.assertEqual(awa_handoff.read_state(), "unknown")

    def test_malformed_record_is_unknown_and_never_auto_closed(self):
        path = awa_handoff.record_path()
        path.parent.mkdir(parents=True, mode=0o700)
        path.write_text('{"schema":', encoding="utf-8")
        before = path.read_bytes()
        result = self._hook(
            {"hook_event_name": "sessionStart", "workspace_roots": [str(self.repo)]},
            cwd=self.repo,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(awa_handoff.read_state(), "unknown")
        facts = integrity._collect_facts(None, profile="fast", now=1.0)
        self.assertEqual(facts.handoff_state, "unknown")

    def test_repeated_and_concurrent_producers_are_monotonic(self):
        target = Path(self.add_worktree(str(self.repo), "feat/direct"))
        first = awa_handoff.create_pending(str(target))
        again = awa_handoff.create_pending(str(target))
        self.assertEqual(first, again)

        targets = []
        for index in range(2):
            path = Path(self._tmp.name) / f"concurrent-{index}"
            git(
                str(self.repo),
                "worktree",
                "add",
                "-q",
                "-b",
                f"feat/concurrent-{index}",
                str(path),
                "main",
            )
            targets.append(path)
        records = []
        errors = []

        def produce(path):
            try:
                records.append(awa_handoff.create_pending(str(path)))
            except Exception as exc:  # pragma: no cover - assertion reports details
                errors.append(exc)

        threads = [threading.Thread(target=produce, args=(path,)) for path in targets]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        self.assertFalse(errors)
        self.assertEqual(sorted(record["generation"] for record in records), [2, 3])
        self.assertEqual(awa_handoff.read_record()["generation"], 3)

    def test_close_cas_crash_never_overwrites_newer_record(self):
        first_target = Path(self.add_worktree(str(self.repo), "feat/first"))
        second_target = Path(self._tmp.name) / "second-worktree"
        git(
            str(self.repo),
            "worktree",
            "add",
            "-q",
            "-b",
            "feat/second",
            str(second_target),
            "main",
        )
        first = awa_handoff.create_pending(str(first_target))
        second = awa_handoff.create_pending(str(second_target))
        self.assertGreater(second["generation"], first["generation"])
        self.assertFalse(awa_handoff.close_pending(first))
        self.assertEqual(awa_handoff.read_record(), second)
        with mock.patch.object(
            awa_handoff,
            "_atomic_replace",
            side_effect=OSError("crash before replace"),
        ):
            self.assertFalse(awa_handoff.consume_session_start(
                {"workspace_roots": [str(second_target)]}
            ))
        self.assertEqual(awa_handoff.read_record(), second)

    def test_lock_contention_is_fail_open_and_preserves_pending(self):
        _, target = self._ensure()
        pending = awa_handoff.read_record()
        lock = awa_handoff.lock_path()
        fd = os.open(lock, os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self._hook(
                {"hook_event_name": "sessionStart", "workspace_roots": [str(target)]},
                cwd=target,
            )
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))
        self.assertEqual(awa_handoff.read_record(), pending)

    def test_writer_uses_atomic_durable_replace_and_dedicated_lock(self):
        target = Path(self.add_worktree(str(self.repo), "feat/durable"))
        durability = awa_handoff._durability_module()
        with mock.patch.object(
            durability,
            "atomic_private_replace",
            wraps=durability.atomic_private_replace,
        ) as atomic:
            awa_handoff.create_pending(str(target))
        atomic.assert_called_once()
        self.assertEqual(Path(atomic.call_args.args[0]), awa_handoff.record_path())
        self.assertEqual(awa_handoff.lock_path().parent, awa_handoff.handoff_dir())
        self.assertNotEqual(awa_handoff.lock_path(), self.state_home / "awa" / "integrity" / ".lock")


if __name__ == "__main__":
    unittest.main()
