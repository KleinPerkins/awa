"""M1-B.3: deterministic private static console and install boundary."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import html
import io
import json
import os
import re
import stat
import subprocess
import time
import unittest
from pathlib import Path
from unittest import mock

from engine import cli, integrity, integrity_console, paths
from engine.tests.helpers import EngineTestCase


_ROOT = Path(__file__).resolve().parents[2]
_INSTALL = _ROOT / "install.sh"


class TestIntegrityConsole(EngineTestCase):
    def _projection(self, **overrides) -> dict:
        value = {
            "schema": integrity.PUBLIC_SCHEMA,
            "generation": 7,
            "generated_at": "2026-08-25T00:00:00Z",
            "overall": "degraded",
            "invariants": [
                {
                    "id": "guard_safety",
                    "severity": "green",
                    "redacted_reason": "guard_safety is green",
                },
                {
                    "id": "surveillance_freshness",
                    "severity": "degraded",
                    "redacted_reason": "surveillance_freshness is degraded",
                },
            ],
            "orphans": {
                "worktrees": 2,
                "leases_unreconciled": 1,
                "sessions_dangling": 0,
                "husks": 0,
            },
            "recovery": {
                "last_status": "ok",
                "needs_repair": 0,
                "quarantine_count": 0,
            },
            "recent_history": [
                {
                    "generation": 6,
                    "overall": "green",
                    "generated_at": "2026-08-24T18:00:00Z",
                },
                {
                    "generation": 7,
                    "overall": "degraded",
                    "generated_at": "2026-08-25T00:00:00Z",
                },
            ],
            "last_checked_age_s": 0,
            "fresh_until": "2026-08-26T00:00:00Z",
        }
        value.update(overrides)
        return value

    def _script_and_csp(self, page: str) -> tuple[str, str]:
        script_matches = re.findall(
            r"<script>(.*?)</script>",
            page,
            flags=re.DOTALL,
        )
        self.assertEqual(len(script_matches), 1)
        csp_match = re.search(
            r'<meta http-equiv="Content-Security-Policy" content="([^"]+)">',
            page,
        )
        self.assertIsNotNone(csp_match)
        return script_matches[0], html.unescape(csp_match.group(1))

    def _status(self) -> dict:
        generated = integrity._now_iso()
        fresh = integrity._iso_at(time.time() + 3600)
        return {
            "overall": "green",
            "generated_at": generated,
            "invariants": [
                {
                    "id": "guard_safety",
                    "severity": "green",
                    "evidence": "safe",
                    "checked_at": generated,
                    "profile": "deep",
                }
            ],
            "triggers": {
                "launchd": {
                    "last_attempt": generated,
                    "last_success": generated,
                    "last_error": None,
                    "generation": 1,
                }
            },
            "orphans": {
                "worktrees": 0,
                "leases_unreconciled": 0,
                "sessions_dangling": 0,
                "husks": 0,
            },
            "recovery": {
                "last_status": "ok",
                "needs_repair": 0,
                "quarantine_count": 0,
            },
            "alert": {
                "last_transition": None,
                "attempted": [],
                "delivered": {
                    "native": "accepted",
                    "slack": "opted_out",
                },
            },
            "fresh_until": fresh,
        }

    def test_render_deterministic(self):
        first = integrity_console.render(self._projection())
        second = integrity_console.render(
            json.loads(json.dumps(self._projection()))
        )
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("<!doctype html>"))
        self.assertTrue(first.endswith("\n"))

    def test_self_contained_no_remote_assets(self):
        page = integrity_console.render(self._projection())
        lowered = page.lower()
        self.assertNotIn("http://", lowered)
        self.assertNotIn("https://", lowered)
        self.assertNotIn("<script src", lowered)
        self.assertNotIn("<link ", lowered)
        self.assertNotIn("<form", lowered)
        self.assertNotIn("<button", lowered)
        self.assertNotIn("reload file", lowered)
        script, csp = self._script_and_csp(page)
        digest = base64.b64encode(
            hashlib.sha256(script.encode("utf-8")).digest()
        ).decode("ascii")
        self.assertIn(f"'sha256-{digest}'", csp)
        self.assertIn("default-src 'none'", csp)
        self.assertIn("connect-src 'none'", csp)
        self.assertIn("form-action 'none'", csp)
        self.assertNotIn("'unsafe-inline'", csp)

    def test_script_injection_escaped(self):
        projection = self._projection()
        projection["invariants"][1]["redacted_reason"] = (
            "</script><img src=x onerror=alert(1)>\u2028\u2029"
        )
        projection["unexpected"] = "<script>alert(2)</script>"
        page = integrity_console.render(projection)
        self.assertNotIn("</script><img", page)
        self.assertNotIn("<img", page)
        self.assertNotIn("alert(1)", page)
        self.assertNotIn("alert(2)", page)
        self.assertNotIn("\u2028", page)
        self.assertNotIn("\u2029", page)
        self.assertNotIn("</script><script", page)

    def test_no_absolute_paths_or_secrets(self):
        projection = self._projection()
        projection["invariants"][0]["redacted_reason"] = (
            "/Users/operator/private DO NOT DISCLOSE"
        )
        projection["raw_evidence"] = {
            "path": "/private/config",
            "credential": "DO NOT DISCLOSE",
        }
        page = integrity_console.render(projection)
        self.assertNotIn("/Users/", page)
        self.assertNotIn("/private/", page)
        self.assertNotIn("DO NOT DISCLOSE", page)
        self.assertNotIn("raw_evidence", page)

    def test_clock_only_script_forces_stale_red_after_expiry(self):
        projection = self._projection()
        before = integrity_console.clock_state(
            projection,
            now_epoch=integrity._parse_iso(
                projection["fresh_until"]
            )
            - 1,
        )
        after = integrity_console.clock_state(
            projection,
            now_epoch=integrity._parse_iso(
                projection["fresh_until"]
            )
            + 1,
        )
        self.assertFalse(before["stale"])
        self.assertEqual(before["effective_overall"], "degraded")
        self.assertTrue(after["stale"])
        self.assertEqual(after["effective_overall"], "red")

        page = integrity_console.render(projection)
        script, _csp = self._script_and_csp(page)
        self.assertIn("Date.now()", script)
        self.assertIn("STALE / RED", script)
        for forbidden in (
            "fetch(",
            "eval(",
            "XMLHttpRequest",
            "WebSocket",
            "localStorage",
            "document.cookie",
            "innerHTML",
        ):
            self.assertNotIn(forbidden, script)

    def test_console_file_is_0600(self):
        integrity._commit(
            self._status(),
            profile="deep",
            trigger="launchd",
        )
        status = integrity.read_status()
        console = (
            paths.integrity_dir()
            / status["artifacts"]["console"]["path"]
        )
        public = json.loads(
            (
                paths.integrity_dir()
                / status["artifacts"]["public"]["path"]
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(stat.S_IMODE(console.stat().st_mode), 0o600)
        self.assertEqual(
            console.read_text(encoding="utf-8"),
            integrity_console.render(public),
        )

    def test_cli_console_reports_referenced_private_file(self):
        integrity._commit(
            self._status(),
            profile="deep",
            trigger="launchd",
        )
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = cli.main(["integrity", "console"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(
            payload["schema"],
            "awa-integrity-console/v1",
        )
        self.assertEqual(payload["overall"], "green")
        console = Path(payload["path"])
        self.assertTrue(console.is_file())
        self.assertEqual(stat.S_IMODE(console.stat().st_mode), 0o600)

    def test_cli_console_open_uses_referenced_file_only(self):
        integrity._commit(
            self._status(),
            profile="deep",
            trigger="launchd",
        )
        stdout = io.StringIO()
        with mock.patch.object(
            cli,
            "_open_console",
            return_value=True,
        ) as opener, contextlib.redirect_stdout(stdout):
            code = cli.main(["integrity", "console", "--open"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["opened"])
        opener.assert_called_once_with(Path(payload["path"]))

    def test_install_ships_assets_without_host_activation_or_hook_touch(self):
        root = Path(self._tmp.name) / "install"
        home = root / "home"
        fake_bin = root / "bin"
        hooks = root / "selected-hooks" / "hooks.json"
        trace = root / "launchctl.trace"
        home.mkdir(parents=True)
        fake_bin.mkdir(parents=True)
        hooks.parent.mkdir(parents=True)
        hooks.write_text(
            '{"version":1,"hooks":{"beforeReadFile":'
            '[{"command":"/foreign/sentinel.sh","type":"command"}]}}\n',
            encoding="utf-8",
        )
        before = hooks.read_bytes()
        fake_launchctl = fake_bin / "launchctl"
        fake_launchctl.write_text(
            f"#!/usr/bin/env bash\nprintf called > {str(trace)!r}\nexit 93\n",
            encoding="utf-8",
        )
        fake_launchctl.chmod(0o755)
        data_home = home / ".local" / "share"
        env = os.environ.copy()
        env.update(
            {
                "HOME": str(home),
                "XDG_DATA_HOME": str(data_home),
                "XDG_CONFIG_HOME": str(home / ".config"),
                "XDG_STATE_HOME": str(home / ".local" / "state"),
                "AWA_HOOK_OWNER": "external",
                "AWA_HOOKS_JSON": str(hooks),
                "AWA_MCP_JSON": str(home / ".cursor" / "mcp.json"),
                "AWA_OPERATOR_RULE": str(
                    home / ".cursor" / "rules" / "awa-operator.mdc"
                ),
                "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        result = subprocess.run(
            [str(_INSTALL)],
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        runtime = data_home / "awa" / "current"
        self.assertTrue(
            (runtime / "kernel" / "bin" / "awa-integrity-sweep.sh").is_file()
        )
        self.assertTrue(
            (
                runtime
                / "contracts"
                / "awa-integrity-schedule.v1.json"
            ).is_file()
        )
        self.assertTrue(
            (runtime / "engine" / "integrity_console.py").is_file()
        )
        self.assertFalse(trace.exists())
        self.assertEqual(hooks.read_bytes(), before)
        self.assertFalse(any(runtime.rglob("*.plist")))

    def test_patch_version_recomputed_from_live_v171(self):
        self.assertEqual(
            (_ROOT / "engine" / "__init__.py")
            .read_text(encoding="utf-8")
            .count('__version__ = "1.7.3"'),
            1,
        )
        self.assertIn(
            'version = "1.7.3"',
            (_ROOT / "pyproject.toml").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
