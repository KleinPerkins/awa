"""Ephemeral, token-gated loopback server for the private integrity console."""

from __future__ import annotations

import hmac
import http.server
import json
import secrets
import socket
import socketserver
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import integrity, integrity_console, paths


BIND_HOST = "127.0.0.1"
DEFAULT_IDLE_TIMEOUT_S = 300.0
MAX_BODY_BYTES = 128
MAX_HEADER_BYTES = 16 * 1024
MAX_PUBLIC_BYTES = 512 * 1024
REQUEST_TIMEOUT_S = 2.0

_FORM_CONTENT_TYPE = "application/x-www-form-urlencoded"
_GENERIC_BODY = b"Request rejected.\n"
_ERROR_BODY = b"Integrity check failed.\n"
_GENERIC_CSP = (
    "default-src 'none'; base-uri 'none'; form-action 'none'; "
    "frame-ancestors 'none'"
)


@dataclass(frozen=True)
class ServeResult:
    reason: str
    port: int


class _LoopbackHTTPServer(http.server.HTTPServer):
    address_family = socket.AF_INET
    allow_reuse_address = False

    def server_bind(self) -> None:
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address
        self.server_name = str(host)
        self.server_port = int(port)

    def get_request(self):
        request, client_address = super().get_request()
        request.settimeout(REQUEST_TIMEOUT_S)
        return request, client_address

    def handle_error(self, request, client_address) -> None:
        owner = getattr(self, "owner", None)
        if owner is not None:
            owner._fatal = True


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = ""
    sys_version = ""

    def log_message(self, format: str, *args) -> None:
        return

    def log_error(self, format: str, *args) -> None:
        return

    def send_error(
        self,
        code: int,
        message: str | None = None,
        explain: str | None = None,
    ) -> None:
        self._respond(404, _GENERIC_BODY, content_type="text/plain; charset=utf-8")

    @property
    def _owner(self) -> "IntegrityConsoleServer":
        return self.server.owner

    def _header_values(self, name: str) -> list[str]:
        return list(self.headers.get_all(name, failobj=[]))

    def _headers_are_bounded(self) -> bool:
        total = 0
        for name, value in self.headers.raw_items():
            total += len(name.encode("utf-8", "replace"))
            total += len(value.encode("utf-8", "replace"))
            if "\r" in name or "\n" in name or "\r" in value or "\n" in value:
                return False
        return total <= MAX_HEADER_BYTES

    def _authority_valid(self, *, post: bool) -> bool:
        if not self._headers_are_bounded():
            return False
        host = self._header_values("Host")
        if host != [self._owner.authority]:
            return False
        origin = self._header_values("Origin")
        if post:
            if origin != [self._owner.origin]:
                return False
        elif origin and origin != [self._owner.origin]:
            return False
        for name in (
            "Forwarded",
            "X-Forwarded-For",
            "X-Forwarded-Host",
            "X-Forwarded-Proto",
        ):
            if self._header_values(name):
                return False
        return True

    def _route(self) -> str | None:
        parts = self.path.split("/")
        if len(parts) not in {3, 4} or parts[0] != "":
            return None
        supplied = parts[1]
        if not hmac.compare_digest(supplied, self._owner.token):
            return None
        if parts == ["", supplied, ""]:
            return "console"
        if parts == ["", supplied, "run-checks-now"]:
            return "run-checks-now"
        return None

    def _respond(
        self,
        status: int,
        body: bytes,
        *,
        content_type: str,
        csp: str = _GENERIC_CSP,
        location: str | None = None,
    ) -> None:
        self.close_connection = True
        self.send_response_only(status)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", csp)
        self.send_header("Content-Type", content_type)
        if location is not None:
            self.send_header("Location", location)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _reject(self) -> None:
        self._respond(404, _GENERIC_BODY, content_type="text/plain; charset=utf-8")

    def _common_framing_valid(self, *, post: bool) -> bool:
        if self._header_values("Transfer-Encoding"):
            return False
        lengths = self._header_values("Content-Length")
        if not post:
            return not lengths or lengths == ["0"]
        if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
            return False
        if lengths[0] != str(int(lengths[0])):
            return False
        return int(lengths[0]) <= MAX_BODY_BYTES

    def _read_projection(self) -> dict:
        status = integrity.read_status()
        if not isinstance(status, dict):
            raise RuntimeError("integrity status unavailable")
        artifacts = status.get("artifacts")
        reference = (
            artifacts.get("public") if isinstance(artifacts, dict) else None
        )
        if not isinstance(reference, dict) or not isinstance(
            reference.get("path"), str
        ):
            raise RuntimeError("integrity projection unavailable")
        target = paths.integrity_dir() / Path(reference["path"])
        with target.open("rb") as handle:
            raw = handle.read(MAX_PUBLIC_BYTES + 1)
        if len(raw) > MAX_PUBLIC_BYTES:
            raise RuntimeError("integrity projection unavailable")
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise RuntimeError("integrity projection unavailable")
        return value

    def _dispatch_get(self) -> None:
        if (
            not self._authority_valid(post=False)
            or not self._common_framing_valid(post=False)
            or self._route() != "console"
        ):
            self._reject()
            return
        projection = self._read_projection()
        page = integrity_console.render(
            projection,
            serve_action="run-checks-now",
            served_form_action=self._owner.form_action_url,
        ).encode("utf-8")
        self._respond(
            200,
            page,
            content_type="text/html; charset=utf-8",
            csp=self._owner.served_csp,
        )
        self._owner._touch()

    def _dispatch_post(self) -> None:
        if (
            not self._authority_valid(post=True)
            or not self._common_framing_valid(post=True)
            or self._route() != "run-checks-now"
        ):
            self._reject()
            return
        content_types = self._header_values("Content-Type")
        lengths = self._header_values("Content-Length")
        if content_types != [_FORM_CONTENT_TYPE] or lengths != ["0"]:
            self._reject()
            return
        self._owner._touch()
        evaluated = self._owner.evaluator("deep", trigger="cli")
        self._owner.committer(evaluated, profile="deep", trigger="cli")
        self._respond(
            303,
            b"",
            content_type="text/plain; charset=utf-8",
            location="./",
        )

    def _dispatch(self, method: str) -> None:
        if method == "GET":
            self._dispatch_get()
        elif method == "POST":
            self._dispatch_post()
        else:
            self._reject()

    def _dispatch_safely(self, method: str) -> None:
        try:
            self._dispatch(method)
        except (BrokenPipeError, ConnectionError, OSError):
            self._owner._fatal = True
        except Exception:
            try:
                self._respond(
                    500,
                    _ERROR_BODY,
                    content_type="text/plain; charset=utf-8",
                )
            except (BrokenPipeError, ConnectionError, OSError):
                pass
            self._owner._fatal = True

    def do_GET(self) -> None:
        self._dispatch_safely("GET")

    def do_POST(self) -> None:
        self._dispatch_safely("POST")

    def do_OPTIONS(self) -> None:
        self._dispatch_safely("OPTIONS")


class IntegrityConsoleServer:
    """One single-threaded, foreground-only loopback server instance."""

    def __init__(
        self,
        *,
        idle_timeout_s: float = DEFAULT_IDLE_TIMEOUT_S,
        evaluator: Callable = integrity.evaluate,
        committer: Callable = integrity._commit,
        token_factory: Callable[[], str] = lambda: secrets.token_urlsafe(32),
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if (
            not isinstance(idle_timeout_s, (int, float))
            or isinstance(idle_timeout_s, bool)
            or idle_timeout_s <= 0
        ):
            raise ValueError("idle timeout must be positive")
        token = token_factory()
        if (
            not isinstance(token, str)
            or len(token) < 32
            or not token.isascii()
            or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
                   for char in token)
        ):
            raise ValueError("invalid capability token")
        self.token = token
        self.idle_timeout_s = float(idle_timeout_s)
        self.evaluator = evaluator
        self.committer = committer
        self.clock = clock
        self._last_activity = clock()
        self._fatal = False
        self._closed = False
        self._httpd = _LoopbackHTTPServer((BIND_HOST, 0), _Handler)
        self._httpd.owner = self
        host, port = self._httpd.server_address
        if host != BIND_HOST or type(port) is not int or port <= 0:
            self._httpd.server_close()
            raise RuntimeError("loopback bind failed")
        self.port = port
        self.authority = f"{BIND_HOST}:{port}"
        self.origin = f"http://{self.authority}"
        self.capability_path = f"/{token}/"
        self.capability_url = f"{self.origin}{self.capability_path}"
        self.form_action_url = f"{self.capability_url}run-checks-now"
        self.served_csp = integrity_console.served_csp(
            self.form_action_url
        )

    @property
    def closed(self) -> bool:
        return self._closed

    def _touch(self) -> None:
        self._last_activity = self.clock()

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._httpd.server_close()

    def serve(
        self,
        *,
        on_started: Callable[[str], None] | None = None,
    ) -> ServeResult:
        reason = "idle"
        try:
            if on_started is not None:
                on_started(self.capability_url)
            while not self._fatal:
                remaining = self.idle_timeout_s - (
                    self.clock() - self._last_activity
                )
                if remaining <= 0:
                    break
                self._httpd.timeout = min(remaining, REQUEST_TIMEOUT_S)
                self._httpd.handle_request()
            if self._fatal:
                reason = "error"
        except KeyboardInterrupt:
            reason = "interrupted"
        except Exception:
            reason = "error"
        finally:
            self.close()
        return ServeResult(reason=reason, port=self.port)


def serve(
    *,
    on_started: Callable[[str], None] | None = None,
    idle_timeout_s: float = DEFAULT_IDLE_TIMEOUT_S,
    evaluator: Callable = integrity.evaluate,
    committer: Callable = integrity._commit,
    token_factory: Callable[[], str] = lambda: secrets.token_urlsafe(32),
    clock: Callable[[], float] = time.monotonic,
) -> ServeResult:
    server = IntegrityConsoleServer(
        idle_timeout_s=idle_timeout_s,
        evaluator=evaluator,
        committer=committer,
        token_factory=token_factory,
        clock=clock,
    )
    return server.serve(on_started=on_started)
