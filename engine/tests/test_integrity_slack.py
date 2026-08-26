"""M1-D.1: opt-in Slack DM delivery with bounded, secret-safe transport."""

from __future__ import annotations

import contextlib
import io
import json
import os
import ssl
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from engine import cli, integrity, integrity_alert, integrity_slack, paths
from engine.tests.helpers import EngineTestCase


TOKEN = "xoxb-" + "12345678" + "-" + "abcdefgh"
USER_ID = "U12345678"
CHANNEL_ID = "D12345678"
PAYLOAD = {
    "schema": "awa-integrity-slack-alert/v1",
    "previous_overall": "green",
    "overall": "degraded",
}


class FakeHTTP:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, *, headers, body, timeout_s):
        self.calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "body": json.loads(body.decode("utf-8")),
                "timeout_s": timeout_s,
            }
        )
        if not self.responses:
            raise AssertionError("unexpected HTTP call")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        if callable(response):
            return response()
        return response


def response(status, payload, headers=None):
    return integrity_slack.HttpResponse(
        status=status,
        headers=headers or {},
        body=json.dumps(payload).encode("utf-8"),
    )


def accepted_http():
    return FakeHTTP(
        response(200, {"ok": True, "channel": {"id": CHANNEL_ID}}),
        response(200, {"ok": True, "channel": CHANNEL_ID}),
    )


class TestIntegritySlack(EngineTestCase):
    def _status(
        self,
        overall,
        *,
        transition_id,
        trigger="launchd",
        previous_overall="green",
    ):
        return {
            "schema": integrity.SCHEMA,
            "generated_at": "2026-08-25T00:00:00Z",
            "overall": overall,
            "profile": "deep",
            "trigger": trigger,
            "transition_id": transition_id,
            "release": {
                "version": "9.9.9",
                "commit": "/private/release/DO-NOT-DISCLOSE",
            },
            "invariants": [
                {
                    "id": "guard_safety",
                    "severity": "green",
                    "evidence": (
                        "/Users/operator/private/raw-evidence "
                        "DO-NOT-DISCLOSE"
                    ),
                    "raw_evidence": {"token": "DO-NOT-DISCLOSE"},
                    "checked_at": "2026-08-25T00:00:00Z",
                    "profile": "deep",
                },
                {
                    "id": "alert_delivery",
                    "severity": "green",
                    "evidence": "delivery available",
                    "checked_at": "2026-08-25T00:00:00Z",
                    "profile": "deep",
                },
            ],
            "triggers": {
                "launchd": {
                    "last_attempt": "2026-08-25T00:00:00Z",
                    "last_success": "2026-08-25T00:00:00Z",
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
                "delivered": {},
            },
            "fresh_until": "2026-08-26T00:00:00Z",
            "_previous_overall": previous_overall,
        }

    def _send(
        self,
        http,
        *,
        token_lookup=lambda _timeout_s: TOKEN,
        user_id=USER_ID,
        payload=PAYLOAD,
        timeout_s=0.5,
        max_retries=1,
    ):
        return integrity_slack.send(
            user_id,
            payload,
            token_lookup=token_lookup,
            http=http,
            timeout_s=timeout_s,
            max_retries=max_retries,
        )

    def _write_config(self, *, mode=0o600, user_id=USER_ID, extra=None):
        target = integrity_slack.config_path()
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        value = {
            "schema": integrity_slack.CONFIG_SCHEMA,
            "user_id": user_id,
        }
        if extra:
            value.update(extra)
        target.write_text(json.dumps(value), encoding="utf-8")
        target.chmod(mode)
        return target

    def _commit_without_dispatch(self, overall):
        status = self._status(
            overall,
            transition_id=None,
            trigger="launchd",
        )
        status.pop("schema")
        status.pop("_previous_overall")
        integrity._commit(status, profile="deep", trigger="launchd")
        committed = integrity.read_status()
        self.assertIsNotNone(committed)
        return committed

    def _closed_status(self, overall, *, schema=True):
        status = self._status(
            overall,
            transition_id=None,
            trigger="launchd",
        )
        status.pop("_previous_overall")
        status["release"]["commit"] = "synthetic"
        for item in status["invariants"]:
            item["evidence"] = "bounded reason"
            item.pop("raw_evidence", None)
        if not schema:
            status.pop("schema")
        return status

    def test_opted_out_when_no_token(self):
        http = mock.Mock()
        result = self._send(
            http,
            token_lookup=lambda _timeout_s: None,
        )
        self.assertEqual(result, "opted_out")
        http.assert_not_called()

    def test_open_then_postmessage_accepted(self):
        http = accepted_http()
        self.assertEqual(self._send(http), "accepted")
        self.assertEqual(
            [call["url"] for call in http.calls],
            [
                integrity_slack.CONVERSATIONS_OPEN_URL,
                integrity_slack.CHAT_POST_MESSAGE_URL,
            ],
        )
        self.assertEqual(http.calls[0]["body"], {"users": USER_ID})
        self.assertEqual(http.calls[1]["body"]["channel"], CHANNEL_ID)
        self.assertEqual(
            http.calls[1]["body"]["text"],
            "AWA integrity changed from green to degraded.",
        )
        self.assertEqual(
            http.calls[0]["headers"]["Authorization"],
            f"Bearer {TOKEN}",
        )

    def test_payload_redacted(self):
        previous = self._status("green", transition_id="older")
        current = self._status("degraded", transition_id="tid-redacted")
        captured = []
        outcomes = integrity_alert.dispatch(
            previous,
            current,
            native=lambda *_: True,
            slack=lambda payload: captured.append(payload) or "accepted",
        )
        self.assertEqual(
            outcomes,
            {"native": "accepted", "slack": "accepted"},
        )
        self.assertEqual(
            set(captured[0]),
            {"schema", "previous_overall", "overall"},
        )
        encoded = json.dumps(captured)
        self.assertNotIn("/Users/", encoded)
        self.assertNotIn("/private/", encoded)
        self.assertNotIn("DO-NOT-DISCLOSE", encoded)
        self.assertNotIn("evidence", encoded)
        self.assertNotIn(USER_ID, encoded)
        self.assertNotIn(TOKEN, encoded)

    def test_both_paths_fail_forces_red(self):
        previous = self._status("green", transition_id="older")
        current = self._status(
            "degraded",
            transition_id="tid-both-fail",
            trigger="cli",
        )
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            outcomes = integrity_alert.dispatch(
                previous,
                current,
                native=lambda *_: False,
                slack=lambda _payload: "failed",
            )
        self.assertEqual(
            outcomes,
            {"native": "failed", "slack": "failed"},
        )
        self.assertEqual(current["overall"], "red")
        self.assertEqual(
            stderr.getvalue(),
            "awa: integrity alert delivery failed on all configured paths\n",
        )
        self.assertNotIn("/Users/", stderr.getvalue())
        self.assertNotIn(TOKEN, stderr.getvalue())
        self.assertNotIn(USER_ID, stderr.getvalue())
        delivery = next(
            item
            for item in current["invariants"]
            if item["id"] == "alert_delivery"
        )
        self.assertEqual(delivery["severity"], "red")

        evaluated = self._status(
            "degraded",
            transition_id=None,
            trigger="cli",
        )
        evaluated.pop("_previous_overall")
        cli_stdout = io.StringIO()
        cli_stderr = io.StringIO()
        with mock.patch.object(
            integrity,
            "evaluate",
            return_value=evaluated,
        ), mock.patch.object(
            integrity_alert,
            "_native",
            return_value=False,
        ), mock.patch.object(
            integrity_slack,
            "send_configured",
            return_value="failed",
        ), contextlib.redirect_stdout(
            cli_stdout
        ), contextlib.redirect_stderr(
            cli_stderr
        ):
            code = cli.main(
                [
                    "integrity",
                    "verify",
                    "--profile",
                    "deep",
                    "--trigger",
                    "cli",
                ]
            )
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(cli_stdout.getvalue())["overall"], "red")
        self.assertEqual(
            cli_stderr.getvalue(),
            "awa: integrity alert delivery failed on all configured paths\n",
        )

    def test_trigger_fallback_is_only_visible_for_sync_cli(self):
        for trigger in ("launchd", "beforeShell", "stop"):
            with self.subTest(trigger=trigger):
                previous = self._status("green", transition_id="older")
                current = self._status(
                    "degraded",
                    transition_id=f"tid-{trigger}",
                    trigger=trigger,
                )
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    outcomes = integrity_alert.dispatch(
                        previous,
                        current,
                        native=lambda *_: False,
                        slack=lambda _payload: "failed",
                    )
                self.assertEqual(
                    outcomes,
                    {"native": "failed", "slack": "failed"},
                )
                self.assertEqual(current["overall"], "red")
                self.assertEqual(stderr.getvalue(), "")

    def test_one_path_success_truth_table(self):
        rows = (
            ("accepted", "failed"),
            ("failed", "accepted"),
            ("accepted", "accepted"),
        )
        for native_result, slack_result in rows:
            with self.subTest(
                native=native_result,
                slack=slack_result,
            ):
                previous = self._status("green", transition_id="older")
                current = self._status(
                    "degraded",
                    transition_id=f"tid-{native_result}-{slack_result}",
                )
                outcomes = integrity_alert.dispatch(
                    previous,
                    current,
                    native=lambda *_: native_result == "accepted",
                    slack=lambda _payload: slack_result,
                )
                self.assertEqual(
                    outcomes,
                    {"native": native_result, "slack": slack_result},
                )
                self.assertEqual(current["overall"], "degraded")

    def test_opted_out_truth_table(self):
        for native_result, expected_overall in (
            ("accepted", "degraded"),
            ("failed", "red"),
        ):
            with self.subTest(native=native_result):
                previous = self._status("green", transition_id="older")
                current = self._status(
                    "degraded",
                    transition_id=f"tid-optout-{native_result}",
                )
                outcomes = integrity_alert.dispatch(
                    previous,
                    current,
                    native=lambda *_: native_result == "accepted",
                    slack=lambda _payload: "opted_out",
                )
                self.assertEqual(
                    outcomes,
                    {"native": native_result, "slack": "opted_out"},
                )
                self.assertEqual(current["overall"], expected_overall)

    def test_opt_in_material_truth_table_persists_receipt_severity(self):
        cases = (
            {
                "name": "neither_present",
                "config": "missing",
                "token": "missing",
                "slack": "opted_out",
                "overall": "red",
                "lookup_calls": 0,
                "http_calls": 0,
            },
            {
                "name": "token_only_missing_user_config",
                "config": "missing",
                "token": "valid",
                "slack": "opted_out",
                "overall": "red",
                "lookup_calls": 0,
                "http_calls": 0,
            },
            {
                "name": "user_only",
                "config": "valid",
                "token": "missing",
                "slack": "opted_out",
                "overall": "red",
                "lookup_calls": 1,
                "http_calls": 0,
            },
            {
                "name": "invalid_token",
                "config": "valid",
                "token": "invalid",
                "slack": "opted_out",
                "overall": "red",
                "lookup_calls": 1,
                "http_calls": 0,
            },
            {
                "name": "invalid_user_id",
                "config": "invalid_user",
                "token": "valid",
                "slack": "opted_out",
                "overall": "red",
                "lookup_calls": 0,
                "http_calls": 0,
            },
            {
                "name": "unsafe_user_config_mode",
                "config": "unsafe_mode",
                "token": "valid",
                "slack": "opted_out",
                "overall": "red",
                "lookup_calls": 0,
                "http_calls": 0,
            },
            {
                "name": "malformed_user_config",
                "config": "malformed",
                "token": "valid",
                "slack": "opted_out",
                "overall": "red",
                "lookup_calls": 0,
                "http_calls": 0,
            },
            {
                "name": "both_valid",
                "config": "valid",
                "token": "valid",
                "slack": "accepted",
                "overall": "degraded",
                "lookup_calls": 1,
                "http_calls": 2,
            },
            {
                "name": "valid_opt_in_api_failure",
                "config": "valid",
                "token": "valid",
                "slack": "failed",
                "overall": "red",
                "lookup_calls": 1,
                "http_calls": 1,
            },
            {
                "name": "valid_user_keychain_operational_error",
                "config": "valid",
                "token": "error",
                "slack": "failed",
                "overall": "red",
                "lookup_calls": 1,
                "http_calls": 0,
            },
        )
        original_state = os.environ["XDG_STATE_HOME"]
        original_config = os.environ["XDG_CONFIG_HOME"]
        try:
            for case in cases:
                with self.subTest(case=case["name"]):
                    case_root = Path(self._tmp.name) / case["name"]
                    state_home = case_root / "state"
                    config_home = case_root / "config"
                    state_home.mkdir(parents=True)
                    config_home.mkdir(parents=True)
                    os.environ["XDG_STATE_HOME"] = str(state_home)
                    os.environ["XDG_CONFIG_HOME"] = str(config_home)

                    if case["config"] == "valid":
                        self._write_config()
                    elif case["config"] == "invalid_user":
                        self._write_config(user_id="C12345678")
                    elif case["config"] == "unsafe_mode":
                        self._write_config(mode=0o644)
                    elif case["config"] == "malformed":
                        target = integrity_slack.config_path()
                        target.parent.mkdir(parents=True, mode=0o700)
                        target.write_text("{", encoding="utf-8")
                        target.chmod(0o600)

                    if case["token"] == "valid":
                        lookup = mock.Mock(return_value=TOKEN)
                    elif case["token"] == "invalid":
                        lookup = mock.Mock(return_value="not-a-token")
                    elif case["token"] == "error":
                        lookup = mock.Mock(
                            side_effect=integrity_slack.TokenLookupError(
                                "Keychain token lookup failed"
                            )
                        )
                    else:
                        lookup = mock.Mock(return_value=None)

                    if case["name"] == "both_valid":
                        http = accepted_http()
                    elif case["name"] == "valid_opt_in_api_failure":
                        http = FakeHTTP(
                            response(
                                200,
                                {"ok": False, "error": "denied"},
                            )
                        )
                    else:
                        http = mock.Mock()

                    integrity._commit(
                        self._closed_status("green", schema=False),
                        profile="deep",
                        trigger="launchd",
                    )
                    stderr = io.StringIO()
                    stdout = io.StringIO()
                    with mock.patch.object(
                        integrity_alert,
                        "_native",
                        return_value=False,
                    ), mock.patch.object(
                        integrity_slack,
                        "_runtime_token_lookup",
                        lookup,
                    ), mock.patch.object(
                        integrity_slack,
                        "_default_http",
                        http,
                    ), contextlib.redirect_stderr(
                        stderr
                    ), contextlib.redirect_stdout(
                        stdout
                    ):
                        integrity._commit(
                            self._closed_status("degraded"),
                            profile="deep",
                            trigger="launchd",
                        )

                    current = integrity.read_status()
                    expected_outcomes = {
                        "native": "failed",
                        "slack": case["slack"],
                    }
                    self.assertEqual(
                        current["alert"]["delivered"],
                        expected_outcomes,
                    )
                    self.assertEqual(current["overall"], case["overall"])
                    receipt_ref = current["artifacts"]["receipt"]
                    receipt = json.loads(
                        (
                            paths.integrity_dir()
                            / receipt_ref["path"]
                        ).read_text(encoding="utf-8")
                    )
                    self.assertEqual(
                        receipt["outcomes"],
                        expected_outcomes,
                    )
                    self.assertEqual(
                        lookup.call_count,
                        case["lookup_calls"],
                    )
                    observed_http_calls = (
                        len(http.calls)
                        if isinstance(http, FakeHTTP)
                        else http.call_count
                    )
                    self.assertEqual(
                        observed_http_calls,
                        case["http_calls"],
                    )
                    self.assertEqual(stderr.getvalue(), "")
                    self.assertEqual(stdout.getvalue(), "")

                    artifacts = b"".join(
                        candidate.read_bytes()
                        for candidate in paths.integrity_dir().rglob("*")
                        if candidate.is_file()
                    )
                    self.assertNotIn(TOKEN.encode("ascii"), artifacts)
                    self.assertNotIn(USER_ID.encode("ascii"), artifacts)
                    self.assertNotIn(
                        str(integrity_slack.config_path()).encode("utf-8"),
                        artifacts,
                    )
        finally:
            os.environ["XDG_STATE_HOME"] = original_state
            os.environ["XDG_CONFIG_HOME"] = original_config

    def test_never_returning_transport_times_out(self):
        code = """
import json
import threading
import time
from engine import integrity_slack

def lookup(_timeout_s):
    return "xoxb-" + "12345678" + "-" + "abcdefgh"

def never_returns(url, *, headers, body, timeout_s):
    threading.Event().wait()

payload = {
    "schema": "awa-integrity-slack-alert/v1",
    "previous_overall": "green",
    "overall": "degraded",
}
started = time.monotonic()
result = integrity_slack.send(
    "U12345678",
    payload,
    token_lookup=lookup,
    http=never_returns,
    timeout_s=0.05,
    max_retries=0,
)
print(json.dumps({
    "result": result,
    "elapsed": time.monotonic() - started,
    "blocking_workers": [
        thread.name
        for thread in threading.enumerate()
        if thread.name.startswith("awa-integrity-slack-")
        and not thread.daemon
    ],
}))
"""
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
        started = time.monotonic()
        completed = subprocess.run(
            [sys.executable, "-c", code],
            env=env,
            capture_output=True,
            text=True,
            timeout=1.0,
            check=False,
        )
        elapsed = time.monotonic() - started
        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["result"], "failed")
        self.assertLess(report["elapsed"], 0.35)
        self.assertLess(elapsed, 0.75)
        self.assertEqual(report["blocking_workers"], [])

    def test_total_deadline_covers_both_calls(self):
        release = threading.Event()
        worker_names = []

        def open_response():
            time.sleep(0.03)
            return response(
                200,
                {"ok": True, "channel": {"id": CHANNEL_ID}},
            )

        def blocked_post():
            worker_names.append(threading.current_thread().name)
            release.wait()
            return response(200, {"ok": True, "channel": CHANNEL_ID})

        http = FakeHTTP(open_response, blocked_post)
        started = time.monotonic()
        try:
            result = self._send(
                http,
                timeout_s=0.07,
                max_retries=0,
            )
        finally:
            release.set()
        elapsed = time.monotonic() - started
        self.assertEqual(result, "failed")
        self.assertLess(elapsed, 0.3)
        self.assertEqual(len(http.calls), 2)
        self.assertTrue(worker_names)

    def test_total_deadline_includes_keychain_lookup(self):
        release = threading.Event()
        http = mock.Mock()

        def blocked_lookup(_timeout_s):
            release.wait()
            return TOKEN

        started = time.monotonic()
        try:
            result = self._send(
                http,
                token_lookup=blocked_lookup,
                timeout_s=0.05,
                max_retries=0,
            )
        finally:
            release.set()
        self.assertEqual(result, "failed")
        self.assertLess(time.monotonic() - started, 0.3)
        http.assert_not_called()

    def test_total_deadline_covers_retries_and_backoff(self):
        http = FakeHTTP(
            response(
                429,
                {"ok": False, "error": "ratelimited"},
                {"Retry-After": "999999"},
            ),
            response(200, {"ok": True, "channel": {"id": CHANNEL_ID}}),
        )
        started = time.monotonic()
        result = self._send(
            http,
            timeout_s=0.04,
            max_retries=3,
        )
        self.assertEqual(result, "failed")
        self.assertLess(time.monotonic() - started, 0.2)
        self.assertEqual(len(http.calls), 1)

    def test_429_retry_after_capped(self):
        http = FakeHTTP(
            response(
                429,
                {"ok": False, "error": "ratelimited"},
                {"Retry-After": "999999"},
            ),
            response(200, {"ok": True, "channel": {"id": CHANNEL_ID}}),
            response(200, {"ok": True, "channel": CHANNEL_ID}),
        )
        sleeps = []
        with mock.patch.object(
            integrity_slack,
            "_sleep",
            side_effect=lambda delay: sleeps.append(delay),
        ):
            self.assertEqual(
                self._send(http, max_retries=1),
                "accepted",
            )
        self.assertEqual(sleeps, [integrity_slack.MAX_RETRY_AFTER_SECONDS])
        self.assertEqual(len(http.calls), 3)

    def test_retry_after_invalid_and_huge_are_bounded(self):
        for value in ("invalid", "-1", "nan", "inf", "999999"):
            with self.subTest(value=value):
                http = FakeHTTP(
                    response(
                        429,
                        {"ok": False},
                        {"rEtRy-AfTeR": value},
                    ),
                    response(
                        200,
                        {"ok": True, "channel": {"id": CHANNEL_ID}},
                    ),
                    response(
                        200,
                        {"ok": True, "channel": CHANNEL_ID},
                    ),
                )
                sleeps = []
                with mock.patch.object(
                    integrity_slack,
                    "_sleep",
                    side_effect=lambda delay: sleeps.append(delay),
                ):
                    result = self._send(http, max_retries=1)
                self.assertEqual(result, "accepted")
                self.assertEqual(len(sleeps), 1)
                self.assertGreaterEqual(sleeps[0], 0)
                self.assertLessEqual(
                    sleeps[0],
                    integrity_slack.MAX_RETRY_AFTER_SECONDS,
                )

    def test_retry_count_is_bounded(self):
        http = FakeHTTP(
            *[
                response(429, {"ok": False}, {"Retry-After": "0"})
                for _ in range(10)
            ]
        )
        self.assertEqual(
            self._send(http, max_retries=2),
            "failed",
        )
        self.assertEqual(len(http.calls), 3)

    def test_socket_denied_is_failed_not_crash(self):
        for error in (
            PermissionError("socket denied"),
            ssl.SSLError("TLS denied"),
            OSError("transport unavailable"),
        ):
            with self.subTest(error=type(error).__name__), mock.patch.object(
                integrity_slack.urllib.request,
                "urlopen",
                side_effect=error,
            ):
                result = self._send(
                    integrity_slack._default_http,
                    max_retries=0,
                )
            self.assertEqual(result, "failed")

    def test_transport_exception_never_leaks_or_crashes(self):
        secret = f"{TOKEN}:{USER_ID}"
        stderr = io.StringIO()
        stdout = io.StringIO()
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(stdout):
            result = self._send(
                FakeHTTP(RuntimeError(secret)),
                max_retries=0,
            )
        self.assertEqual(result, "failed")
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(stdout.getvalue(), "")

    def test_malformed_and_ok_false_responses_fail(self):
        malformed = integrity_slack.HttpResponse(
            status=200,
            headers={},
            body=b"{",
        )
        cases = (
            FakeHTTP(response(200, {"ok": False, "error": "denied"})),
            FakeHTTP(response(200, {"ok": True})),
            FakeHTTP(malformed),
            FakeHTTP(
                response(
                    200,
                    {"ok": True, "channel": {"id": CHANNEL_ID}},
                ),
                response(200, {"ok": False, "error": "denied"}),
            ),
            FakeHTTP(
                response(
                    200,
                    {"ok": True, "channel": {"id": CHANNEL_ID}},
                ),
                response(200, {"ok": True}),
            ),
        )
        for http in cases:
            with self.subTest(calls=len(http.responses)):
                self.assertEqual(
                    self._send(http, max_retries=0),
                    "failed",
                )

    def test_non_dm_channel_is_refused(self):
        http = FakeHTTP(
            response(200, {"ok": True, "channel": {"id": "C12345678"}})
        )
        self.assertEqual(
            self._send(http, max_retries=0),
            "failed",
        )
        self.assertEqual(len(http.calls), 1)

    def test_user_and_channel_injection_are_refused(self):
        invalid_users = (
            "",
            "C12345678",
            "U123\nInjected",
            "U12345678, U87654321",
            USER_ID + "\r\nX-Test: injected",
        )
        for user_id in invalid_users:
            with self.subTest(user_id=repr(user_id)):
                http = mock.Mock()
                self.assertEqual(
                    self._send(http, user_id=user_id),
                    "opted_out",
                )
                http.assert_not_called()

        http = mock.Mock()
        self.assertEqual(
            self._send(
                http,
                token_lookup=lambda _timeout_s: TOKEN + "\r\nX-Test: injected",
            ),
            "opted_out",
        )
        http.assert_not_called()

    def test_payload_schema_is_closed(self):
        cases = (
            "not-a-dict",
            {},
            {**PAYLOAD, "raw_evidence": "DO-NOT-DISCLOSE"},
            {**PAYLOAD, "overall": "green"},
            {**PAYLOAD, "previous_overall": "/Users/operator/private"},
        )
        for payload in cases:
            with self.subTest(payload=payload):
                http = mock.Mock()
                self.assertEqual(
                    self._send(http, payload=payload),
                    "failed",
                )
                http.assert_not_called()

    def test_private_0600_config_is_required(self):
        target = self._write_config(mode=0o600)
        self.assertEqual(
            integrity_slack.load_configured_user_id(),
            USER_ID,
        )
        target.chmod(0o644)
        self.assertIsNone(integrity_slack.load_configured_user_id())

    def test_config_symlink_and_non_closed_schema_are_refused(self):
        target = self._write_config(mode=0o600)
        real = target.with_name("real.json")
        target.replace(real)
        target.symlink_to(real)
        self.assertIsNone(integrity_slack.load_configured_user_id())
        target.unlink()
        real.unlink()

        self._write_config(mode=0o600, extra={"token": TOKEN})
        self.assertIsNone(integrity_slack.load_configured_user_id())

    def test_keychain_lookup_uses_fixed_argv_without_shell(self):
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=(TOKEN + "\n").encode("ascii"),
            stderr=b"",
        )
        with mock.patch.object(
            integrity_slack.subprocess,
            "run",
            return_value=completed,
        ) as run:
            self.assertEqual(
                integrity_slack._keychain_token_lookup(0.5),
                TOKEN,
            )
        args, kwargs = run.call_args
        self.assertEqual(
            args[0][:2],
            ["security", "find-generic-password"],
        )
        self.assertIn("-w", args[0])
        self.assertNotIn(TOKEN, args[0])
        self.assertNotIn(USER_ID, args[0])
        self.assertFalse(kwargs.get("shell", False))
        self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)
        self.assertLessEqual(kwargs["timeout"], 0.5)

    def test_keychain_not_found_is_opted_out(self):
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=integrity_slack.KEYCHAIN_NOT_FOUND_EXIT,
            stdout=b"",
            stderr=b"",
        )
        with mock.patch.object(
            integrity_slack.subprocess,
            "run",
            return_value=completed,
        ):
            lookup = integrity_slack._keychain_token_lookup
            self.assertEqual(
                self._send(mock.Mock(), token_lookup=lookup),
                "opted_out",
            )

    def test_keychain_timeout_error_has_no_secret_leak(self):
        secret = f"{TOKEN}:{USER_ID}"

        def lookup(_timeout_s):
            raise subprocess.TimeoutExpired(
                ["security", "find-generic-password"],
                0.01,
                output=secret,
                stderr=secret,
            )

        stderr = io.StringIO()
        stdout = io.StringIO()
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(stdout):
            result = self._send(
                mock.Mock(),
                token_lookup=lookup,
                max_retries=0,
            )
        self.assertEqual(result, "failed")
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(stdout.getvalue(), "")

    def test_exact_receipt_outcomes_and_no_secret_artifacts(self):
        self._commit_without_dispatch("green")
        evaluated = self._status(
            "degraded",
            transition_id=None,
            trigger="launchd",
        )
        evaluated.pop("_previous_overall")
        with mock.patch.object(
            integrity_alert,
            "_native",
            return_value=False,
        ), mock.patch.object(
            integrity_slack,
            "load_configured_user_id",
            return_value=USER_ID,
        ), mock.patch.object(
            integrity_slack,
            "send",
            return_value="accepted",
        ) as send:
            integrity._commit(
                evaluated,
                profile="deep",
                trigger="launchd",
            )
        send.assert_called_once()
        current = integrity.read_status()
        self.assertEqual(
            current["alert"]["delivered"],
            {"native": "failed", "slack": "accepted"},
        )
        self.assertEqual(current["overall"], "degraded")
        receipt_ref = current["artifacts"]["receipt"]
        receipt = json.loads(
            (paths.integrity_dir() / receipt_ref["path"]).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            receipt["outcomes"],
            {"native": "failed", "slack": "accepted"},
        )
        all_artifacts = b"".join(
            candidate.read_bytes()
            for candidate in paths.integrity_dir().rglob("*")
            if candidate.is_file()
        )
        self.assertNotIn(TOKEN.encode("ascii"), all_artifacts)
        self.assertNotIn(USER_ID.encode("ascii"), all_artifacts)
        for name in ("public", "console", "outbox", "receipt"):
            payloads = b"".join(
                candidate.read_bytes()
                for candidate in (paths.integrity_dir() / name).glob("*")
                if candidate.is_file()
            )
            self.assertNotIn(b"DO-NOT-DISCLOSE", payloads)

    def test_slack_success_closes_pending_and_prevents_duplicate_alert(self):
        self._commit_without_dispatch("green")
        evaluated = self._status(
            "degraded",
            transition_id=None,
            trigger="launchd",
        )
        evaluated.pop("_previous_overall")
        with mock.patch.object(
            integrity_alert,
            "_native",
            return_value=False,
        ), mock.patch.object(
            integrity_slack,
            "load_configured_user_id",
            return_value=USER_ID,
        ), mock.patch.object(
            integrity_slack,
            "send",
            return_value="accepted",
        ) as send:
            integrity._commit(
                evaluated,
                profile="deep",
                trigger="launchd",
            )
            same = self._status(
                "degraded",
                transition_id=None,
                trigger="launchd",
            )
            same.pop("_previous_overall")
            integrity._commit(
                same,
                profile="deep",
                trigger="launchd",
            )
        send.assert_called_once()
        current = integrity.read_status()
        self.assertEqual(
            current["alert"]["delivered"],
            {"native": "failed", "slack": "accepted"},
        )

    def test_stale_cas_does_not_duplicate_or_overwrite(self):
        self._commit_without_dispatch("green")
        stale = self._commit_without_dispatch("degraded")
        newer = self._commit_without_dispatch("red")
        before = paths.integrity_status_path().read_bytes()
        self.assertIsNone(
            integrity.commit_alert_receipt(
                stale["generation"],
                stale["transition_id"],
                {"native": "failed", "slack": "accepted"},
            )
        )
        self.assertEqual(paths.integrity_status_path().read_bytes(), before)
        self.assertEqual(integrity.read_status(), newer)

    def test_no_alert_recursion(self):
        self._commit_without_dispatch("green")
        evaluated = self._status(
            "degraded",
            transition_id=None,
            trigger="launchd",
        )
        evaluated.pop("_previous_overall")
        original_dispatch = integrity_alert.dispatch
        with mock.patch.object(
            integrity,
            "evaluate",
            side_effect=AssertionError("alert re-evaluated integrity"),
        ), mock.patch.object(
            integrity_alert,
            "_native",
            return_value=False,
        ), mock.patch.object(
            integrity_slack,
            "load_configured_user_id",
            return_value=USER_ID,
        ), mock.patch.object(
            integrity_slack,
            "send",
            return_value="failed",
        ), mock.patch.object(
            integrity_alert,
            "dispatch",
            wraps=original_dispatch,
        ) as dispatch:
            integrity._commit(
                evaluated,
                profile="deep",
                trigger="launchd",
            )
        dispatch.assert_called_once()
        current = integrity.read_status()
        self.assertEqual(
            current["alert"]["delivered"],
            {"native": "failed", "slack": "failed"},
        )
        self.assertEqual(current["overall"], "red")

    def test_timeout_workers_cannot_keep_interpreter_alive(self):
        before = {
            thread.ident
            for thread in threading.enumerate()
            if thread.is_alive() and not thread.daemon
        }
        release = threading.Event()

        def blocked_http(url, *, headers, body, timeout_s):
            release.wait()

        try:
            self.assertEqual(
                self._send(
                    blocked_http,
                    timeout_s=0.03,
                    max_retries=0,
                ),
                "failed",
            )
            after = {
                thread.ident
                for thread in threading.enumerate()
                if thread.is_alive() and not thread.daemon
            }
            self.assertEqual(after, before)
            workers = [
                thread
                for thread in threading.enumerate()
                if thread.name.startswith("awa-integrity-slack-")
            ]
            self.assertTrue(workers)
            self.assertTrue(all(thread.daemon for thread in workers))
        finally:
            release.set()


if __name__ == "__main__":
    unittest.main()
