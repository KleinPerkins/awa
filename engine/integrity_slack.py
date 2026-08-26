"""Opt-in, bounded Slack DM delivery for AWA integrity alerts.

The adapter accepts only a closed severity-transition payload.  The bot token is
looked up from macOS Keychain and the operator user id is read from a private
XDG config file; neither value is returned, logged, or persisted in integrity
artifacts.
"""

from __future__ import annotations

import itertools
import json
import math
import os
import queue
import re
import stat
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from . import paths


CONFIG_SCHEMA = "awa-integrity-slack-config/v1"
PAYLOAD_SCHEMA = "awa-integrity-slack-alert/v1"

CONVERSATIONS_OPEN_URL = "https://slack.com/api/conversations.open"
CHAT_POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"

KEYCHAIN_SERVICE = "awa-integrity-slack-bot-token"
KEYCHAIN_ACCOUNT = "awa-integrity"
KEYCHAIN_NOT_FOUND_EXIT = 44

DEFAULT_TIMEOUT_SECONDS = 5.0
MAX_TOTAL_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_RETRIES = 2
MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 0.05
MAX_RETRY_AFTER_SECONDS = 0.25
MAX_RESPONSE_BYTES = 64 * 1024
MAX_CONFIG_BYTES = 4096
MAX_TOKEN_BYTES = 1024

_USER_ID_RE = re.compile(r"[UW][A-Z0-9]{8,20}\Z")
_DM_CHANNEL_ID_RE = re.compile(r"D[A-Z0-9]{8,20}\Z")
_TOKEN_RE = re.compile(r"xoxb-[A-Za-z0-9_-]{8,500}\Z")
_SEVERITIES = frozenset({"green", "degraded", "red"})
_PREVIOUS_SEVERITIES = frozenset({*_SEVERITIES, "unknown"})
_WORKER_SEQUENCE = itertools.count(1)
_sleep = time.sleep


@dataclass(frozen=True)
class HttpResponse:
    """Closed response shape returned by the injectable HTTP transport."""

    status: int
    headers: Mapping[str, str]
    body: bytes


class TokenLookupError(RuntimeError):
    """A generic Keychain failure with no secret-bearing detail."""


@dataclass(frozen=True)
class _CallResult:
    completed: bool
    succeeded: bool
    value: object = None


def config_path() -> Path:
    """Canonical private operator config containing only the Slack user id."""
    return paths.config_home() / "awa" / "integrity-slack.json"


def _valid_user_id(value: object) -> bool:
    return isinstance(value, str) and _USER_ID_RE.fullmatch(value) is not None


def _valid_channel_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and _DM_CHANNEL_ID_RE.fullmatch(value) is not None
    )


def _valid_token(value: object) -> bool:
    return isinstance(value, str) and _TOKEN_RE.fullmatch(value) is not None


def load_configured_user_id(path: Path | None = None) -> str | None:
    """Read a regular, owner-held, exact-0600 closed config without following links."""
    target = config_path() if path is None else Path(path)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(str(target), flags)
    except OSError:
        return None
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != paths.FILE_MODE
            or info.st_uid != os.getuid()
            or info.st_size < 2
            or info.st_size > MAX_CONFIG_BYTES
        ):
            return None
        chunks = []
        remaining = MAX_CONFIG_BYTES + 1
        while remaining > 0:
            chunk = os.read(fd, min(remaining, 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > MAX_CONFIG_BYTES:
            return None
    except OSError:
        return None
    finally:
        os.close(fd)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if (
        not isinstance(value, dict)
        or set(value) != {"schema", "user_id"}
        or value.get("schema") != CONFIG_SCHEMA
        or not _valid_user_id(value.get("user_id"))
    ):
        return None
    return value["user_id"]


def _keychain_token_lookup(timeout_s: float) -> str | None:
    """Read the token using fixed argv; item-not-found is explicit opt-out."""
    try:
        completed = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-a",
                KEYCHAIN_ACCOUNT,
                "-s",
                KEYCHAIN_SERVICE,
                "-w",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=max(0.001, float(timeout_s)),
            check=False,
            shell=False,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        raise TokenLookupError("Keychain token lookup failed") from None
    if completed.returncode == KEYCHAIN_NOT_FOUND_EXIT:
        return None
    if completed.returncode != 0:
        raise TokenLookupError("Keychain token lookup failed")
    raw = completed.stdout
    if not isinstance(raw, bytes) or len(raw) > MAX_TOKEN_BYTES:
        raise TokenLookupError("Keychain token lookup failed")
    try:
        token = raw.rstrip(b"\r\n").decode("ascii")
    except UnicodeDecodeError:
        raise TokenLookupError("Keychain token lookup failed") from None
    if not token:
        return None
    if not _valid_token(token):
        raise TokenLookupError("Keychain token lookup failed")
    return token


def _runtime_token_lookup(timeout_s: float) -> str | None:
    # Existing engine tests explicitly isolate XDG state but macOS Keychain is
    # machine-global.  Never let a test-active evaluator query the real Keychain.
    if os.environ.get("AWA_ENGINE_TEST_ACTIVE") == "1":
        return None
    return _keychain_token_lookup(timeout_s)


def _default_http(
    url: str,
    *,
    headers: Mapping[str, str],
    body: bytes,
    timeout_s: float,
) -> HttpResponse:
    """Perform one fixed-endpoint JSON request with bounded connect/read timeout."""
    request = urllib.request.Request(
        url,
        data=body,
        headers=dict(headers),
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=max(0.001, float(timeout_s)),
        ) as opened:
            response_body = opened.read(MAX_RESPONSE_BYTES + 1)
            response_headers = {
                str(key): str(value)
                for key, value in opened.headers.items()
            }
            return HttpResponse(
                status=int(opened.status),
                headers=response_headers,
                body=response_body,
            )
    except urllib.error.HTTPError as exc:
        try:
            response_body = exc.read(MAX_RESPONSE_BYTES + 1)
        except Exception:
            response_body = b""
        response_headers = (
            {
                str(key): str(value)
                for key, value in exc.headers.items()
            }
            if exc.headers is not None
            else {}
        )
        return HttpResponse(
            status=int(exc.code),
            headers=response_headers,
            body=response_body,
        )


def _bounded_call(
    operation: Callable[[], object],
    timeout_s: float,
    *,
    role: str,
) -> _CallResult:
    """Bound any injected adapter without creating an interpreter-blocking worker."""
    if timeout_s <= 0:
        return _CallResult(False, False)
    result: queue.Queue[tuple[bool, object]] = queue.Queue(maxsize=1)

    def invoke() -> None:
        try:
            value = operation()
        except BaseException:
            item = (False, None)
        else:
            item = (True, value)
        try:
            result.put_nowait(item)
        except queue.Full:
            pass

    worker = threading.Thread(
        target=invoke,
        name=(
            f"awa-integrity-slack-{role}-"
            f"{next(_WORKER_SEQUENCE)}"
        ),
        daemon=True,
    )
    try:
        worker.start()
        worker.join(timeout_s)
    except RuntimeError:
        return _CallResult(True, False)
    if worker.is_alive():
        return _CallResult(False, False)
    try:
        succeeded, value = result.get_nowait()
    except queue.Empty:
        return _CallResult(True, False)
    return _CallResult(True, succeeded, value)


def _remaining(deadline: float) -> float:
    return max(0.0, deadline - time.monotonic())


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    wanted = name.lower()
    for key, value in headers.items():
        if str(key).lower() == wanted:
            return str(value)
    return None


def _retry_delay(
    response: HttpResponse | None,
    retry_number: int,
) -> float:
    fallback = min(
        MAX_RETRY_AFTER_SECONDS,
        BASE_BACKOFF_SECONDS * (2 ** max(0, retry_number)),
    )
    if response is None or response.status != 429:
        return fallback
    raw = _header_value(response.headers, "Retry-After")
    try:
        parsed = float(raw) if raw is not None else fallback
    except (TypeError, ValueError, OverflowError):
        return fallback
    if not math.isfinite(parsed) or parsed < 0:
        return fallback
    return min(parsed, MAX_RETRY_AFTER_SECONDS)


def _bounded_backoff(delay: float, deadline: float) -> bool:
    remaining = _remaining(deadline)
    if remaining <= 0:
        return False
    bounded = min(max(0.0, delay), remaining)
    if bounded:
        _sleep(bounded)
    return _remaining(deadline) > 0


def _coerce_response(value: object) -> HttpResponse | None:
    if not isinstance(value, HttpResponse):
        return None
    if (
        type(value.status) is not int
        or not isinstance(value.headers, Mapping)
        or not isinstance(value.body, bytes)
        or len(value.body) > MAX_RESPONSE_BYTES
    ):
        return None
    return value


def _request_json(
    url: str,
    request_body: dict,
    *,
    token: str,
    http: Callable,
    deadline: float,
    max_retries: int,
) -> dict | None:
    body = json.dumps(
        request_body,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    for attempt in range(max_retries + 1):
        remaining = _remaining(deadline)
        if remaining <= 0:
            return None
        call = _bounded_call(
            lambda: http(
                url,
                headers=headers,
                body=body,
                timeout_s=_remaining(deadline),
            ),
            remaining,
            role="http",
        )
        if not call.completed:
            return None
        response = _coerce_response(call.value) if call.succeeded else None
        retryable = (
            response is None
            or response.status == 429
            or 500 <= response.status <= 599
        )
        if retryable:
            if attempt >= max_retries:
                return None
            if not _bounded_backoff(
                _retry_delay(response, attempt),
                deadline,
            ):
                return None
            continue
        if not 200 <= response.status <= 299:
            return None
        try:
            decoded = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(decoded, dict) or decoded.get("ok") is not True:
            return None
        return decoded
    return None


def _closed_message(payload: object) -> str | None:
    if (
        not isinstance(payload, dict)
        or set(payload)
        != {"schema", "previous_overall", "overall"}
        or payload.get("schema") != PAYLOAD_SCHEMA
        or payload.get("previous_overall") not in _PREVIOUS_SEVERITIES
        or payload.get("overall") not in {"degraded", "red"}
    ):
        return None
    return (
        "AWA integrity changed from "
        f"{payload['previous_overall']} to {payload['overall']}."
    )


def send(
    user_id,
    payload,
    *,
    token_lookup,
    http,
    timeout_s,
    max_retries,
) -> str:
    """Attempt one bounded DM and return accepted, failed, or opted_out."""
    try:
        total_timeout = float(timeout_s)
    except (TypeError, ValueError, OverflowError):
        return "failed"
    if (
        not math.isfinite(total_timeout)
        or total_timeout <= 0
        or isinstance(timeout_s, bool)
        or type(max_retries) is not int
        or max_retries < 0
    ):
        return "failed"
    total_timeout = min(total_timeout, MAX_TOTAL_TIMEOUT_SECONDS)
    retries = min(max_retries, MAX_RETRIES)
    deadline = time.monotonic() + total_timeout

    # Missing/invalid opt-in material is opted out.  Refuse an invalid private
    # user config before touching machine-global Keychain.  A distinguishable
    # Keychain operational fault remains failed below: calling it opted out
    # would hide a broken lookup behind an operator choice that was never made.
    if not _valid_user_id(user_id):
        return "opted_out"
    lookup_remaining = _remaining(deadline)
    lookup = _bounded_call(
        lambda: token_lookup(_remaining(deadline)),
        lookup_remaining,
        role="keychain",
    )
    if not lookup.completed or not lookup.succeeded:
        return "failed"
    token = lookup.value
    if token is None or token == "":
        return "opted_out"
    if not _valid_token(token):
        return "opted_out"
    message = _closed_message(payload)
    if message is None:
        return "failed"

    try:
        opened = _request_json(
            CONVERSATIONS_OPEN_URL,
            {"users": user_id},
            token=token,
            http=http,
            deadline=deadline,
            max_retries=retries,
        )
    except Exception:
        return "failed"
    channel = opened.get("channel") if isinstance(opened, dict) else None
    channel_id = channel.get("id") if isinstance(channel, dict) else None
    if not _valid_channel_id(channel_id):
        return "failed"

    try:
        posted = _request_json(
            CHAT_POST_MESSAGE_URL,
            {"channel": channel_id, "text": message},
            token=token,
            http=http,
            deadline=deadline,
            max_retries=retries,
        )
    except Exception:
        return "failed"
    posted_channel = posted.get("channel") if isinstance(posted, dict) else None
    if not _valid_channel_id(posted_channel) or posted_channel != channel_id:
        return "failed"
    return "accepted"


def send_configured(payload) -> str:
    """Use the canonical private config and production adapters."""
    return send(
        load_configured_user_id(),
        payload,
        token_lookup=_runtime_token_lookup,
        http=_default_http,
        timeout_s=DEFAULT_TIMEOUT_SECONDS,
        max_retries=DEFAULT_MAX_RETRIES,
    )
