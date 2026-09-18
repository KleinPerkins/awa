"""M3.1: ephemeral token-gated loopback integrity console server."""

from __future__ import annotations

import contextlib
import html
import http.client
import io
import json
import socket
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from engine import cli, integrity, integrity_server, paths
from engine.tests.helpers import EngineTestCase


class TestIntegrityServer(EngineTestCase):
    def _status(self) -> dict:
        generated = integrity._now_iso()
        return {
            "overall": "green",
            "generated_at": generated,
            "invariants": [
                {
                    "id": "guard_safety",
                    "severity": "green",
                    "evidence": "/private/evidence secret-value",
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
            "fresh_until": integrity._iso_at(time.time() + 3600),
        }

    def _commit_status(self) -> None:
        integrity._commit(self._status(), profile="deep", trigger="launchd")

    def _start(self, **kwargs):
        server = integrity_server.IntegrityConsoleServer(
            idle_timeout_s=kwargs.pop("idle_timeout_s", 0.8),
            **kwargs,
        )
        result = []
        thread = threading.Thread(
            target=lambda: result.append(server.serve()),
            name="test-integrity-console-server",
        )
        thread.start()

        def cleanup():
            server.close()
            thread.join(timeout=3)
            self.assertFalse(thread.is_alive())

        self.addCleanup(cleanup)
        return server, thread, result

    def _request(
        self,
        server,
        method: str,
        path: str,
        *,
        headers: dict | None = None,
        body: bytes | None = None,
    ):
        actual_headers = {"Host": server.authority}
        if headers:
            actual_headers.update(headers)
        connection = http.client.HTTPConnection(
            integrity_server.BIND_HOST,
            server.port,
            timeout=3,
        )
        connection.request(
            method,
            path,
            body=body,
            headers=actual_headers,
        )
        response = connection.getresponse()
        payload = response.read()
        values = response.getheaders()
        connection.close()
        return response.status, dict(values), payload

    def _raw_request(self, server, request: bytes) -> tuple[int, bytes]:
        with socket.create_connection(
            (integrity_server.BIND_HOST, server.port),
            timeout=3,
        ) as client:
            client.sendall(request)
            client.shutdown(socket.SHUT_WR)
            chunks = []
            while True:
                chunk = client.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
        raw = b"".join(chunks)
        status = int(raw.split(b" ", 2)[1])
        return status, raw

    def test_binds_loopback_only(self):
        server = integrity_server.IntegrityConsoleServer(idle_timeout_s=0.01)
        self.addCleanup(server.close)
        self.assertEqual(integrity_server.BIND_HOST, "127.0.0.1")
        self.assertEqual(server._httpd.server_address[0], "127.0.0.1")
        self.assertGreater(server.port, 0)
        self.assertEqual(server._httpd.socket.family, socket.AF_INET)

    def test_missing_or_wrong_token_rejected(self):
        self._commit_status()
        server, _thread, _result = self._start()
        missing = self._request(server, "GET", "/")[0:3:2]
        wrong = self._request(
            server,
            "GET",
            f"/{'x' * len(server.token)}/",
        )[0:3:2]
        self.assertEqual(missing, wrong)
        self.assertEqual(missing[0], 404)
        self.assertNotIn(server.token.encode(), missing[1])

    def test_wrong_host_or_origin_rejected(self):
        self._commit_status()
        server, _thread, _result = self._start()
        path = server.capability_path
        self.assertEqual(self._request(server, "GET", path)[0], 200)
        for host in (
            f"localhost:{server.port}",
            f"127.0.0.1:{server.port + 1}",
            "127.0.0.1",
            f"[::1]:{server.port}",
        ):
            self.assertEqual(
                self._request(server, "GET", path, headers={"Host": host})[0],
                404,
            )
        self.assertEqual(
            self._request(
                server,
                "GET",
                path,
                headers={"Origin": server.origin},
            )[0],
            200,
        )
        self.assertEqual(
            self._request(
                server,
                "GET",
                path,
                headers={"Origin": f"http://localhost:{server.port}"},
            )[0],
            404,
        )
        post_path = path + "run-checks-now"
        post_headers = {"Content-Type": "application/x-www-form-urlencoded"}
        self.assertEqual(
            self._request(
                server,
                "POST",
                post_path,
                headers=post_headers,
                body=b"",
            )[0],
            404,
        )
        self.assertEqual(
            self._request(
                server,
                "POST",
                post_path,
                headers={
                    **post_headers,
                    "Origin": f"http://localhost:{server.port}",
                },
                body=b"",
            )[0],
            404,
        )

    def test_rerun_is_post_only_and_calls_evaluator(self):
        self._commit_status()
        evaluator = mock.Mock(return_value=self._status())
        committer = mock.Mock(return_value=2)
        server, _thread, _result = self._start(
            evaluator=evaluator,
            committer=committer,
        )
        rerun = server.capability_path + "run-checks-now"
        self.assertEqual(self._request(server, "GET", rerun)[0], 404)
        evaluator.assert_not_called()
        status, headers, body = self._request(
            server,
            "POST",
            rerun,
            headers={
                "Origin": server.origin,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            body=b"",
        )
        self.assertEqual(status, 303)
        self.assertEqual(headers["Location"], "./")
        self.assertEqual(body, b"")
        evaluator.assert_called_once_with("deep", trigger="cli")
        committer.assert_called_once_with(
            evaluator.return_value,
            profile="deep",
            trigger="cli",
        )

    def test_no_destructive_route(self):
        self._commit_status()
        evaluator = mock.Mock()
        committer = mock.Mock()
        server, _thread, _result = self._start(
            evaluator=evaluator,
            committer=committer,
        )
        for route in (
            "repair",
            "quarantine",
            "lifecycle",
            "export",
            "recover",
            "../run-checks-now",
            "%72un-checks-now",
        ):
            for method in ("GET", "POST"):
                self.assertEqual(
                    self._request(
                        server,
                        method,
                        server.capability_path + route,
                        headers={
                            "Origin": server.origin,
                            "Content-Type": "application/x-www-form-urlencoded",
                        },
                        body=b"" if method == "POST" else None,
                    )[0],
                    404,
                )
        evaluator.assert_not_called()
        committer.assert_not_called()

    def test_idle_shutdown(self):
        self.assertEqual(integrity_server.DEFAULT_IDLE_TIMEOUT_S, 300.0)
        server, thread, result = self._start(idle_timeout_s=0.08)
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result, [integrity_server.ServeResult("idle", server.port)])
        self.assertTrue(server.closed)
        with self.assertRaises(OSError):
            socket.create_connection(
                (integrity_server.BIND_HOST, server.port),
                timeout=0.2,
            )

    def test_os_port_and_token_are_fresh_each_launch(self):
        first = integrity_server.IntegrityConsoleServer(idle_timeout_s=0.01)
        second = integrity_server.IntegrityConsoleServer(idle_timeout_s=0.01)
        self.addCleanup(first.close)
        self.addCleanup(second.close)
        self.assertGreater(first.port, 0)
        self.assertGreater(second.port, 0)
        self.assertNotEqual(first.token, second.token)
        self.assertNotEqual(first.capability_url, second.capability_url)
        self.assertTrue(first.capability_url.startswith("http://127.0.0.1:"))
        self.assertTrue(first.capability_url.endswith("/"))

    def test_get_rerenders_bounded_redacted_projection(self):
        for _ in range(integrity.HISTORY_MAX + 3):
            integrity._commit(
                self._status(),
                profile="deep",
                trigger="launchd",
            )
        server, _thread, _result = self._start()
        status_code, headers, body = self._request(
            server,
            "GET",
            server.capability_path,
        )
        page = body.decode("utf-8")
        self.assertEqual(status_code, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["Content-Type"], "text/html; charset=utf-8")
        self.assertNotIn("Access-Control-Allow", "\n".join(headers))
        self.assertIn("<form method=\"post\" action=\"run-checks-now\">", page)
        self.assertIn("Run checks now", page)
        self.assertIn(
            "Checks may take a moment; this page returns when complete.",
            page,
        )
        self.assertIn(
            "awa-engine integrity console --serve --open",
            page,
        )
        self.assertEqual(page.count(server.token), 1)
        self.assertNotIn(server.token, page.split("<main", 1)[1])
        self.assertNotIn("/private/evidence", page)
        self.assertNotIn("secret-value", page)
        self.assertEqual(
            page.count('class="severity green"'),
            integrity.HISTORY_MAX + 1,
        )
        self.assertIn(server.form_action_url, headers["Content-Security-Policy"])
        self.assertIn(
            html.escape(headers["Content-Security-Policy"], quote=True),
            page,
        )

    def test_each_get_reads_the_latest_committed_projection(self):
        self._commit_status()
        first_status = integrity.read_status()
        server, _thread, _result = self._start()
        first_page = self._request(
            server,
            "GET",
            server.capability_path,
        )[2].decode("utf-8")
        self.assertIn(
            f"generation {first_status['generation']}",
            first_page,
        )
        changed = self._status()
        changed["overall"] = "degraded"
        integrity._commit(changed, profile="deep", trigger="cli")
        second_status = integrity.read_status()
        second_page = self._request(
            server,
            "GET",
            server.capability_path,
        )[2].decode("utf-8")
        self.assertIn(
            f"generation {second_status['generation']}",
            second_page,
        )
        self.assertIn("AWA needs attention", second_page)
        self.assertNotEqual(first_page, second_page)

    def test_duplicate_malformed_and_proxy_headers_are_rejected(self):
        self._commit_status()
        server, _thread, _result = self._start()
        path = server.capability_path.encode()
        duplicate_host = (
            b"GET " + path + b" HTTP/1.1\r\n"
            + f"Host: {server.authority}\r\n".encode()
            + f"Host: {server.authority}\r\n\r\n".encode()
        )
        self.assertEqual(self._raw_request(server, duplicate_host)[0], 404)
        duplicate_origin = (
            b"GET " + path + b" HTTP/1.1\r\n"
            + f"Host: {server.authority}\r\n".encode()
            + f"Origin: {server.origin}\r\n".encode()
            + f"Origin: {server.origin}\r\n\r\n".encode()
        )
        self.assertEqual(self._raw_request(server, duplicate_origin)[0], 404)
        duplicate_length = (
            b"POST "
            + (server.capability_path + "run-checks-now").encode()
            + b" HTTP/1.1\r\n"
            + f"Host: {server.authority}\r\n".encode()
            + f"Origin: {server.origin}\r\n".encode()
            + b"Content-Type: application/x-www-form-urlencoded\r\n"
            + b"Content-Length: 0\r\nContent-Length: 0\r\n\r\n"
        )
        self.assertEqual(self._raw_request(server, duplicate_length)[0], 404)
        self.assertEqual(
            self._request(
                server,
                "GET",
                server.capability_path,
                headers={"X-Forwarded-Host": server.authority},
            )[0],
            404,
        )
        malformed = b"GET / HTTP/1.1\r\nBad Header\r\n\r\n"
        status, raw = self._raw_request(server, malformed)
        self.assertEqual(status, 404)
        self.assertNotIn(server.token.encode(), raw)

    def test_no_cors_options_or_open_method_set(self):
        self._commit_status()
        server, _thread, _result = self._start()
        for method in ("OPTIONS", "PUT", "PATCH", "DELETE", "HEAD"):
            status, headers, body = self._request(
                server,
                method,
                server.capability_path,
                headers={"Origin": server.origin},
            )
            self.assertEqual(status, 404)
            self.assertNotIn(b"Access-Control", body)
            self.assertFalse(
                any(name.lower().startswith("access-control") for name in headers)
            )

    def test_post_rejects_chunked_nonempty_or_oversized_body(self):
        self._commit_status()
        evaluator = mock.Mock()
        server, _thread, _result = self._start(evaluator=evaluator)
        path = server.capability_path + "run-checks-now"
        expected = {
            "Origin": server.origin,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        self.assertEqual(
            self._request(
                server,
                "POST",
                path,
                headers=expected,
                body=b"x=1",
            )[0],
            404,
        )
        raw = (
            f"POST {path} HTTP/1.1\r\nHost: {server.authority}\r\n"
            f"Origin: {server.origin}\r\n"
            "Content-Type: application/x-www-form-urlencoded\r\n"
            "Transfer-Encoding: chunked\r\n\r\n0\r\n\r\n"
        ).encode()
        self.assertEqual(self._raw_request(server, raw)[0], 404)
        oversized = (
            f"POST {path} HTTP/1.1\r\nHost: {server.authority}\r\n"
            f"Origin: {server.origin}\r\n"
            "Content-Type: application/x-www-form-urlencoded\r\n"
            f"Content-Length: {integrity_server.MAX_BODY_BYTES + 1}\r\n\r\n"
        ).encode()
        self.assertEqual(self._raw_request(server, oversized)[0], 404)
        evaluator.assert_not_called()

    def test_evaluator_failure_is_generic_and_closes_server(self):
        self._commit_status()
        evaluator = mock.Mock(side_effect=RuntimeError("SECRET /private/path"))
        server, thread, result = self._start(
            idle_timeout_s=2,
            evaluator=evaluator,
        )
        status, _headers, body = self._request(
            server,
            "POST",
            server.capability_path + "run-checks-now",
            headers={
                "Origin": server.origin,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            body=b"",
        )
        self.assertEqual(status, 500)
        page = body.decode("utf-8")
        self.assertIn("Checks could not complete", page)
        self.assertIn("Restart the console, then run checks again.", page)
        self.assertIn(
            "awa-engine integrity console --serve --open",
            page,
        )
        self.assertNotIn("<form", page)
        self.assertNotIn('data-component="ActionForm"', page)
        self.assertNotIn(b"SECRET", body)
        self.assertNotIn(server.token.encode(), body)
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result[0].reason, "error")
        self.assertTrue(server.closed)

    def test_committer_failure_uses_same_fatal_recovery_contract(self):
        self._commit_status()
        evaluator = mock.Mock(return_value=self._status())
        committer = mock.Mock(
            side_effect=RuntimeError("SECRET commit artifact path")
        )
        server, thread, result = self._start(
            idle_timeout_s=2,
            evaluator=evaluator,
            committer=committer,
        )
        status, _headers, body = self._request(
            server,
            "POST",
            server.capability_path + "run-checks-now",
            headers={
                "Origin": server.origin,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            body=b"",
        )
        page = body.decode("utf-8")
        self.assertEqual(status, 500)
        self.assertIn("Checks could not complete", page)
        self.assertIn("Restart the console, then run checks again.", page)
        self.assertNotIn("<form", page)
        self.assertNotIn("SECRET", page)
        self.assertNotIn(server.token, page)
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result[0].reason, "error")
        self.assertTrue(server.closed)

    def test_failed_browser_open_warns_then_live_get_post_still_work(self):
        self._commit_status()
        evaluator = mock.Mock(return_value=self._status())
        committer = mock.Mock(return_value=2)
        holder = {}
        ready = threading.Event()
        output_ready = threading.Event()
        stdout = io.StringIO()
        stderr = io.StringIO()
        result = []

        def run_server(*, on_started):
            server = integrity_server.IntegrityConsoleServer(
                idle_timeout_s=0.35,
                evaluator=evaluator,
                committer=committer,
            )
            holder["server"] = server
            ready.set()
            return server.serve(on_started=on_started)

        def run_cli():
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(
                stderr
            ):
                result.append(
                    cli.main(["integrity", "console", "--serve", "--open"])
                )
                output_ready.set()

        with mock.patch.object(
            integrity_server,
            "serve",
            side_effect=run_server,
        ), mock.patch.object(
            cli,
            "_open_console",
            return_value=False,
        ):
            thread = threading.Thread(target=run_cli)
            thread.start()
            self.assertTrue(ready.wait(timeout=2))
            server = holder["server"]
            deadline = time.monotonic() + 2
            while "\n" not in stdout.getvalue() and time.monotonic() < deadline:
                time.sleep(0.005)
            self.assertEqual(
                stdout.getvalue(),
                server.capability_url + "\n",
            )
            self.assertEqual(
                self._request(
                    server,
                    "GET",
                    server.capability_path,
                )[0],
                200,
            )
            self.assertEqual(
                self._request(
                    server,
                    "POST",
                    server.capability_path + "run-checks-now",
                    headers={
                        "Origin": server.origin,
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    body=b"",
                )[0],
                303,
            )
            thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertTrue(output_ready.is_set())
        self.assertEqual(result, [0])
        self.assertEqual(stdout.getvalue().count(server.capability_url), 1)
        self.assertEqual(
            stderr.getvalue(),
            "awa: browser could not be opened; use the printed console URL\n",
        )
        self.assertNotIn(server.token, stderr.getvalue())
        evaluator.assert_called_once_with("deep", trigger="cli")
        committer.assert_called_once()
        self.assertTrue(server.closed)

    def test_absent_status_get_then_post_then_valid_get(self):
        server, thread, _result = self._start(
            idle_timeout_s=1,
            evaluator=mock.Mock(return_value=self._status()),
            committer=integrity._commit,
        )
        status, _headers, body = self._request(
            server,
            "GET",
            server.capability_path,
        )
        page = body.decode("utf-8")
        self.assertEqual(status, 200)
        self.assertIn("No status yet", page)
        self.assertIn(
            "Run checks now to create the first private integrity status.",
            page,
        )
        self.assertIn(
            '<form method="post" action="run-checks-now">',
            page,
        )
        self.assertIn(
            "awa-engine integrity console --serve --open",
            page,
        )
        self.assertNotIn("GREEN", page)
        self.assertNotIn("Recent history", page)
        self.assertNotIn("Invariants", page)
        self.assertNotIn(server.token, page)
        self.assertTrue(thread.is_alive())

        status, headers, body = self._request(
            server,
            "POST",
            server.capability_path + "run-checks-now",
            headers={
                "Origin": server.origin,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            body=b"",
        )
        self.assertEqual(status, 303)
        self.assertEqual(headers["Location"], "./")
        self.assertEqual(body, b"")
        status, _headers, body = self._request(
            server,
            "GET",
            server.capability_path,
        )
        self.assertEqual(status, 200)
        self.assertIn("generation 1", body.decode("utf-8"))
        self.assertIn("AWA is healthy", body.decode("utf-8"))

    def test_corrupt_get_is_request_local_and_post_recovers(self):
        root = paths.ensure_dir(paths.integrity_dir())
        paths.integrity_status_path().write_text(
            '{"schema":"corrupt","secret":"DO NOT LEAK"}\n',
            encoding="utf-8",
        )
        server, thread, _result = self._start(
            idle_timeout_s=1,
            evaluator=mock.Mock(return_value=self._status()),
            committer=integrity._commit,
        )
        status, _headers, body = self._request(
            server,
            "GET",
            server.capability_path,
        )
        self.assertEqual(status, 503)
        page = body.decode("utf-8")
        self.assertIn("Status cannot be read", page)
        self.assertIn(
            '<form method="post" action="run-checks-now">',
            page,
        )
        self.assertIn("Checks may take a moment", page)
        self.assertNotIn(b"DO NOT LEAK", body)
        self.assertNotIn(
            server.token,
            page.split("<main", 1)[1],
        )
        self.assertTrue(thread.is_alive())
        paths.integrity_status_path().unlink()
        self.assertEqual(
            self._request(
                server,
                "POST",
                server.capability_path + "run-checks-now",
                headers={
                    "Origin": server.origin,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                body=b"",
            )[0],
            303,
        )
        self.assertEqual(
            self._request(
                server,
                "GET",
                server.capability_path,
            )[0],
            200,
        )
        self.assertTrue(root.is_dir())

    def test_transient_projection_read_error_is_request_local(self):
        self._commit_status()
        server, thread, _result = self._start()
        with mock.patch.object(
            integrity,
            "read_status",
            side_effect=OSError("SECRET transient path"),
        ):
            status, _headers, body = self._request(
                server,
                "GET",
                server.capability_path,
            )
        self.assertEqual(status, 503)
        page = body.decode("utf-8")
        self.assertIn("Status cannot be read", page)
        self.assertIn(
            '<form method="post" action="run-checks-now">',
            page,
        )
        self.assertNotIn(b"SECRET", body)
        self.assertNotIn(
            server.token,
            page.split("<main", 1)[1],
        )
        self.assertTrue(thread.is_alive())
        self.assertEqual(
            self._request(
                server,
                "GET",
                server.capability_path,
            )[0],
            200,
        )

    def test_malformed_parse_request_is_local_then_valid_get_works(self):
        self._commit_status()
        server, thread, _result = self._start()
        malformed = (
            b"GET /"
            + b"x" * 70_000
            + b" HTTP/1.1\r\n"
            + f"Host: {server.authority}\r\n\r\n".encode()
        )
        status, raw = self._raw_request(server, malformed)
        self.assertEqual(status, 404)
        self.assertNotIn(server.token.encode(), raw)
        self.assertTrue(thread.is_alive())
        self.assertEqual(
            self._request(
                server,
                "GET",
                server.capability_path,
            )[0],
            200,
        )

    def test_http_server_handle_error_is_request_local(self):
        self._commit_status()
        server, thread, _result = self._start()
        server._httpd.handle_error(None, None)
        self.assertFalse(server._fatal)
        self.assertTrue(thread.is_alive())
        self.assertEqual(
            self._request(
                server,
                "GET",
                server.capability_path,
            )[0],
            200,
        )

    def test_ambiguous_request_targets_reject_without_idle_reset(self):
        self._commit_status()
        evaluator = mock.Mock()
        server, _thread, _result = self._start(evaluator=evaluator)
        before = server._last_activity
        targets = (
            server.capability_url,
            server.capability_path[:-1] + "\\/",
            f"/{server.token}prefix/",
        )
        responses = []
        for target in targets:
            status, _headers, body = self._request(
                server,
                "GET",
                target,
            )
            responses.append((status, body))
            self.assertNotIn(server.token.encode(), body)
        self.assertEqual(
            responses,
            [(404, b"Request rejected.\n")] * 3,
        )
        self.assertEqual(server._last_activity, before)
        evaluator.assert_not_called()

    def test_non_ascii_get_target_is_generic_and_request_local(self):
        self._commit_status()
        server, thread, _result = self._start()
        raw_request = (
            b"GET /\xff/ HTTP/1.1\r\n"
            + f"Host: {server.authority}\r\n".encode()
            + f"Origin: {server.origin}\r\n\r\n".encode()
        )
        status, raw = self._raw_request(server, raw_request)
        self.assertEqual(status, 404)
        self.assertTrue(raw.endswith(b"Request rejected.\n"))
        self.assertNotIn(server.token.encode(), raw)
        self.assertTrue(thread.is_alive())
        self.assertEqual(
            self._request(
                server,
                "GET",
                server.capability_path,
            )[0],
            200,
        )

    def test_non_ascii_post_target_is_generic_then_valid_post_works(self):
        self._commit_status()
        evaluator = mock.Mock(return_value=self._status())
        committer = mock.Mock(return_value=2)
        server, thread, _result = self._start(
            evaluator=evaluator,
            committer=committer,
        )
        raw_request = (
            b"POST /\xff/ HTTP/1.1\r\n"
            + f"Host: {server.authority}\r\n".encode()
            + f"Origin: {server.origin}\r\n".encode()
            + b"Content-Type: application/x-www-form-urlencoded\r\n"
            + b"Content-Length: 0\r\n\r\n"
        )
        status, raw = self._raw_request(server, raw_request)
        self.assertEqual(status, 404)
        self.assertTrue(raw.endswith(b"Request rejected.\n"))
        self.assertNotIn(server.token.encode(), raw)
        evaluator.assert_not_called()
        committer.assert_not_called()
        self.assertTrue(thread.is_alive())
        self.assertEqual(
            self._request(
                server,
                "POST",
                server.capability_path + "run-checks-now",
                headers={
                    "Origin": server.origin,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                body=b"",
            )[0],
            303,
        )
        evaluator.assert_called_once_with("deep", trigger="cli")
        committer.assert_called_once()

    def test_rejected_traffic_does_not_extend_idle(self):
        server, thread, result = self._start(idle_timeout_s=0.18)
        started = time.monotonic()
        time.sleep(0.09)
        self.assertEqual(self._request(server, "GET", "/wrong/")[0], 404)
        thread.join(timeout=1)
        elapsed = time.monotonic() - started
        self.assertFalse(thread.is_alive())
        self.assertEqual(result[0].reason, "idle")
        self.assertLess(elapsed, 0.3)

    def test_valid_activity_extends_idle(self):
        self._commit_status()
        server, thread, result = self._start(idle_timeout_s=0.18)
        started = time.monotonic()
        time.sleep(0.11)
        self.assertEqual(
            self._request(server, "GET", server.capability_path)[0],
            200,
        )
        time.sleep(0.11)
        self.assertTrue(thread.is_alive())
        thread.join(timeout=1)
        elapsed = time.monotonic() - started
        self.assertFalse(thread.is_alive())
        self.assertEqual(result[0].reason, "idle")
        self.assertGreater(elapsed, 0.25)

    def test_token_not_persisted_by_real_rerun(self):
        self._commit_status()
        server, _thread, _result = self._start(
            evaluator=mock.Mock(return_value=self._status()),
            committer=integrity._commit,
        )
        self.assertEqual(
            self._request(
                server,
                "POST",
                server.capability_path + "run-checks-now",
                headers={
                    "Origin": server.origin,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                body=b"",
            )[0],
            303,
        )
        token = server.token.encode()
        for candidate in paths.integrity_dir().rglob("*"):
            if candidate.is_file():
                self.assertNotIn(token, candidate.read_bytes(), str(candidate))

    def test_interrupt_and_startup_error_close_socket(self):
        server = integrity_server.IntegrityConsoleServer(idle_timeout_s=1)
        with mock.patch.object(
            server._httpd,
            "handle_request",
            side_effect=KeyboardInterrupt,
        ):
            result = server.serve()
        self.assertEqual(result.reason, "interrupted")
        self.assertTrue(server.closed)

        failed = integrity_server.IntegrityConsoleServer(idle_timeout_s=1)
        result = failed.serve(
            on_started=mock.Mock(side_effect=RuntimeError("do not leak")),
        )
        self.assertEqual(result.reason, "error")
        self.assertTrue(failed.closed)

    def test_cli_serve_prints_once_and_never_auto_opens(self):
        def fake_serve(*, on_started):
            on_started("http://127.0.0.1:54321/capability/")
            return integrity_server.ServeResult("idle", 54321)

        stdout = io.StringIO()
        with mock.patch.object(
            integrity_server,
            "serve",
            side_effect=fake_serve,
        ), mock.patch.object(cli, "_open_console") as opener, (
            contextlib.redirect_stdout(stdout)
        ):
            code = cli.main(["integrity", "console", "--serve"])
        self.assertEqual(code, 0)
        self.assertEqual(
            stdout.getvalue(),
            "http://127.0.0.1:54321/capability/\n",
        )
        opener.assert_not_called()

    def test_real_cli_runs_real_server_to_idle_without_browser(self):
        real_serve = integrity_server.serve

        def short_serve(*, on_started):
            return real_serve(on_started=on_started, idle_timeout_s=0.05)

        stdout = io.StringIO()
        with mock.patch.object(
            integrity_server,
            "serve",
            side_effect=short_serve,
        ), mock.patch.object(cli, "_open_console") as opener, (
            contextlib.redirect_stdout(stdout)
        ):
            code = cli.main(["integrity", "console", "--serve"])
        self.assertEqual(code, 0)
        lines = stdout.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertRegex(
            lines[0],
            r"^http://127\.0\.0\.1:[1-9][0-9]*/[A-Za-z0-9_-]{32,}/$",
        )
        opener.assert_not_called()

    def test_cli_serve_open_uses_existing_browser_seam(self):
        def fake_serve(*, on_started):
            on_started("http://127.0.0.1:54321/capability/")
            return integrity_server.ServeResult("idle", 54321)

        with mock.patch.object(
            integrity_server,
            "serve",
            side_effect=fake_serve,
        ), mock.patch.object(
            cli,
            "_open_console",
            return_value=True,
        ) as opener, contextlib.redirect_stdout(io.StringIO()):
            code = cli.main(["integrity", "console", "--serve", "--open"])
        self.assertEqual(code, 0)
        opener.assert_called_once_with(
            "http://127.0.0.1:54321/capability/"
        )

    def test_cli_opener_exception_warns_without_aborting_server(self):
        def fake_serve(*, on_started):
            on_started("http://127.0.0.1:54321/capability/")
            return integrity_server.ServeResult("idle", 54321)

        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(
            integrity_server,
            "serve",
            side_effect=fake_serve,
        ), mock.patch.object(
            cli,
            "_open_console",
            side_effect=RuntimeError("SECRET capability failure"),
        ), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(
            stderr
        ):
            code = cli.main(["integrity", "console", "--serve", "--open"])
        self.assertEqual(code, 0)
        self.assertEqual(
            stdout.getvalue(),
            "http://127.0.0.1:54321/capability/\n",
        )
        self.assertEqual(
            stderr.getvalue(),
            "awa: browser could not be opened; use the printed console URL\n",
        )
        self.assertNotIn("SECRET", stderr.getvalue())

    def test_cli_server_error_is_generic(self):
        stderr = io.StringIO()
        with mock.patch.object(
            integrity_server,
            "serve",
            return_value=integrity_server.ServeResult("error", 54321),
        ), contextlib.redirect_stdout(io.StringIO()), (
            contextlib.redirect_stderr(stderr)
        ):
            code = cli.main(["integrity", "console", "--serve"])
        self.assertEqual(code, 3)
        self.assertEqual(
            stderr.getvalue(),
            "awa: private console server stopped after an error\n",
        )


if __name__ == "__main__":
    unittest.main()
