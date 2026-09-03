"""M1-B.1: session-independent deep sweep and host schedule contract."""

from __future__ import annotations

import json
import os
import signal
import stat
import subprocess
import unittest
from pathlib import Path

from engine import integrity
from engine.tests.helpers import EngineTestCase


_ROOT = Path(__file__).resolve().parents[2]
_SWEEP = _ROOT / "kernel" / "bin" / "awa-integrity-sweep.sh"
_SCHEDULE = _ROOT / "contracts" / "awa-integrity-schedule.v1.json"
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


class TestIntegritySweep(EngineTestCase):
    def _fake_root(
        self,
        *,
        executable: bool = True,
        broken_shebang: bool = False,
    ) -> Path:
        root = Path(self._tmp.name) / "fake-runtime"
        (root / "bin").mkdir(parents=True)
        engine = root / "bin" / "awa-engine.sh"
        engine.write_text(
            ("""#!/definitely/missing
""" if broken_shebang else """#!/usr/bin/env bash
""") + """
test "$1 $2 $3 $4 $5 $6" = \
"integrity verify --profile deep --trigger launchd" || exit 91
if [ "${FAKE_SIGNAL:-0}" = "1" ]; then
  kill -TERM "$$"
fi
exit "${FAKE_EXIT:-0}"
""",
            encoding="utf-8",
        )
        engine.chmod(0o755 if executable else 0o600)
        return root

    def _run(self, *, root: Path | None = None, **extra_env: str):
        env = os.environ.copy()
        env["AWA_HOME"] = str(root or _ROOT)
        env["XDG_STATE_HOME"] = str(self.state_home)
        env["AWA_ENGINE_TEST_ACTIVE"] = "1"
        env.update(extra_env)
        for name in (
            "CURSOR_SESSION_ID",
            "CURSOR_AGENT_ID",
            "CURSOR_TRACE_ID",
            "DEV_SESSION_ID",
        ):
            env.pop(name, None)
        return subprocess.run(
            ["bash", str(_SWEEP)],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )

    def test_schedule_contract_valid(self):
        contract = json.loads(_SCHEDULE.read_text(encoding="utf-8"))
        self.assertEqual(contract["schema"], "awa-integrity-schedule/v1")
        self.assertEqual(
            contract["label"],
            "com.kleinperkins.awa-integrity",
        )
        interval = contract["interval_seconds"]
        minimum = contract["minimum_interval_seconds"]
        maximum = contract["maximum_interval_seconds"]
        self.assertIs(type(interval), int)
        self.assertLessEqual(minimum, interval)
        self.assertLessEqual(interval, maximum)
        self.assertLessEqual(maximum, integrity.DEEP_BOUND_SECONDS)
        self.assertEqual(contract["profile"], "deep")
        self.assertEqual(contract["trigger"], "launchd")
        self.assertFalse(contract["ships_plist"])
        self.assertFalse(any(_ROOT.rglob("*.plist")))

    def test_sweep_returns_severity_verbatim_no_normalization(self):
        root = self._fake_root()
        for code in (0, 1, 2, 3, 47):
            with self.subTest(code=code):
                result = self._run(root=root, FAKE_EXIT=str(code))
                self.assertEqual(result.returncode, code, result.stderr)
        crashed = self._run(root=root, FAKE_SIGNAL="1")
        self.assertEqual(crashed.returncode, -signal.SIGTERM)

    def test_product_sweep_uses_bash_without_git_metadata(self):
        root = self._fake_root(broken_shebang=True)
        result = self._run(root=root, FAKE_EXIT="47")
        self.assertEqual(result.returncode, 47, result.stderr)

    def test_non_executable_runtime_engine_is_not_interpreted(self):
        root = self._fake_root(executable=False)
        result = self._run(root=root, FAKE_EXIT="47")
        self.assertNotEqual(result.returncode, 47)
        self.assertNotEqual(result.returncode, 0)

    def test_sweep_updates_launchd_trigger(self):
        result = self._run(
            AWA_INTEGRITY_TEST_FACTS_JSON=json.dumps(_SAFE_FACTS),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        status = integrity.read_status()
        self.assertIsNotNone(status)
        self.assertEqual(status["profile"], "deep")
        self.assertEqual(status["trigger"], "launchd")
        self.assertIsNotNone(
            status["triggers"]["launchd"]["last_attempt"],
        )

    def test_sweep_never_locks(self):
        root = self._fake_root()
        fake_bin = Path(self._tmp.name) / "fake-bin"
        fake_bin.mkdir()
        lock_trace = Path(self._tmp.name) / "lock-trace"
        flock = fake_bin / "flock"
        flock.write_text(
            f"#!/usr/bin/env bash\nprintf called > {str(lock_trace)!r}\nexit 88\n",
            encoding="utf-8",
        )
        flock.chmod(stat.S_IRWXU)
        result = self._run(
            root=root,
            PATH=f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(lock_trace.exists())
        self.assertNotIn("flock", _SWEEP.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
