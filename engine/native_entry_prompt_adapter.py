#!/usr/bin/env python3
"""Quiet hard-deadline supervisor for first-prompt native entry recovery."""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence


MAX_PAYLOAD_BYTES = 64 * 1024
HARD_BUDGET_SECONDS = 2.0
_CLEANUP_RESERVE_SECONDS = 0.04


class _TerminationRequested(BaseException):
    """Turn hook-process termination into contained worker cleanup."""


def _request_termination(_number: int, _frame: object) -> None:
    raise _TerminationRequested()


@contextlib.contextmanager
def _contained_termination_signals():
    previous: dict[int, object] = {}
    for number in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
        try:
            previous[number] = signal.signal(number, _request_termination)
        except (OSError, ValueError):
            continue
    try:
        yield
    finally:
        for number, handler in previous.items():
            with contextlib.suppress(OSError, ValueError):
                signal.signal(number, handler)


def _signal_group(process: subprocess.Popen, number: int) -> None:
    with contextlib.suppress(OSError, ProcessLookupError):
        os.killpg(process.pid, number)


def _bounded_wait(process: subprocess.Popen, deadline: float) -> None:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return
    with contextlib.suppress(subprocess.TimeoutExpired):
        process.wait(timeout=remaining)


def _supervise(
    payload: bytes,
    *,
    command: Sequence[str] | None = None,
    budget_seconds: float = HARD_BUDGET_SECONDS,
) -> None:
    """Run one worker with payload only on stdin and leave no live descendants."""
    started = time.monotonic()
    hard_deadline = started + max(0.05, float(budget_seconds))
    reserve = min(
        _CLEANUP_RESERVE_SECONDS,
        max(0.02, float(budget_seconds) / 4),
    )
    worker_deadline = hard_deadline - reserve
    root = Path(__file__).resolve().parents[1]
    worker = list(command) if command is not None else [
        sys.executable,
        "-B",
        "-m",
        "engine.native_entry",
        "--deadline-monotonic",
        f"{worker_deadline:.9f}",
    ]
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    prior_pythonpath = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = (
        str(root)
        if not prior_pythonpath
        else str(root) + os.pathsep + prior_pythonpath
    )
    process: subprocess.Popen | None = None
    try:
        if time.monotonic() >= worker_deadline:
            return
        process = subprocess.Popen(
            worker,
            cwd=str(root),
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
        timeout = max(0.001, worker_deadline - time.monotonic())
        process.communicate(input=payload, timeout=timeout)
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    finally:
        if process is not None:
            # The leader may exit after spawning a descendant. Signal the
            # process group even when Popen has already reaped that leader.
            _signal_group(process, signal.SIGTERM)
            if process.poll() is None:
                _bounded_wait(
                    process,
                    min(hard_deadline, time.monotonic() + reserve / 2),
                )
            _signal_group(process, signal.SIGKILL)
            if process.poll() is None:
                _bounded_wait(process, hard_deadline)
        if process is not None and process.poll() is None:
            # The group has already received SIGKILL. A zero-time wait avoids
            # extending the hook deadline while allowing an exited leader to
            # be reaped when the status is immediately available.
            with contextlib.suppress(subprocess.TimeoutExpired):
                process.wait(timeout=0)
    return None


def main(
    argv: list[str] | None = None,
    *,
    stdin: bytes | None = None,
) -> int:
    if list(argv if argv is not None else sys.argv[1:]):
        return 0
    try:
        with _contained_termination_signals():
            raw = (
                stdin
                if stdin is not None
                else sys.stdin.buffer.read(MAX_PAYLOAD_BYTES + 1)
            )
            if not isinstance(raw, bytes) or len(raw) > MAX_PAYLOAD_BYTES:
                return 0
            _supervise(raw)
    except BaseException:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
