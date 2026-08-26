#!/usr/bin/env python3
"""Detach and bound fail-open fast integrity observations.

The caller only starts a short-lived worker.  That worker coalesces rapid
invocations and runs the existing integrity CLI with closed descriptors and a
hard timeout.  No observer result can affect the hook that requested it.
"""

from __future__ import annotations

import fcntl
import math
import os
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path


_TRIGGERS = frozenset({"beforeShell", "stop"})
_DEFAULT_DEBOUNCE_SECONDS = 2.0
_DEFAULT_TIMEOUT_SECONDS = 10.0
_MAX_TIMEOUT_SECONDS = 30.0


def _number(
    name: str,
    default: float,
    *,
    minimum: float,
    maximum: float,
) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    if not math.isfinite(value):
        return default
    return min(maximum, max(minimum, value))


def _runtime_root() -> Path:
    configured = os.environ.get("AWA_HOME", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def _engine_path() -> Path:
    configured = os.environ.get("AWA_INTEGRITY_ENGINE", "").strip()
    if configured:
        return Path(configured).expanduser()
    return _runtime_root() / "bin" / "awa-engine.sh"


def _observer_dir() -> Path | None:
    configured = os.environ.get("XDG_STATE_HOME", "").strip()
    base = (
        Path(configured).expanduser()
        if configured
        else Path.home() / ".local" / "state"
    )
    target = base / "awa" / "integrity" / "hook-observer"
    try:
        if target.is_symlink():
            return None
        target.mkdir(mode=0o700, parents=True, exist_ok=True)
        if target.is_symlink() or not target.is_dir():
            return None
        os.chmod(str(target), 0o700)
    except OSError:
        return None
    return target


def _open_lock(trigger: str) -> int | None:
    root = _observer_dir()
    if root is None:
        return None
    flags = os.O_RDWR | os.O_CREAT
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = -1
    try:
        fd = os.open(str(root / f"{trigger}.lock"), flags, 0o600)
        mode = os.fstat(fd).st_mode
        if not stat.S_ISREG(mode):
            os.close(fd)
            return None
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
        return None
    return fd


def _read_last(fd: int) -> int | None:
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        raw = os.read(fd, 128)
        if len(raw) == 128:
            return None
        return int(raw.decode("ascii").strip())
    except (OSError, UnicodeError, ValueError):
        return None


def _write_last(fd: int, value: int) -> None:
    data = f"{value}\n".encode("ascii")
    os.lseek(fd, 0, os.SEEK_SET)
    os.ftruncate(fd, 0)
    view = memoryview(data)
    written = 0
    while written < len(view):
        count = os.write(fd, view[written:])
        if count <= 0:
            raise OSError("debounce write made no progress")
        written += count


def _run_engine(trigger: str, timeout_seconds: float) -> None:
    engine = _engine_path()
    if not engine.is_file() or not os.access(str(engine), os.X_OK):
        return
    process = subprocess.Popen(
        [
            str(engine),
            "integrity",
            "verify",
            "--profile",
            "fast",
            "--trigger",
            trigger,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            try:
                process.kill()
            except OSError:
                pass
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass


def _worker(trigger: str) -> None:
    lock_fd = _open_lock(trigger)
    if lock_fd is None:
        return
    try:
        debounce = _number(
            "AWA_INTEGRITY_DEBOUNCE_SECONDS",
            _DEFAULT_DEBOUNCE_SECONDS,
            minimum=0.0,
            maximum=300.0,
        )
        now = time.monotonic_ns()
        previous = _read_last(lock_fd)
        debounce_ns = int(debounce * 1_000_000_000)
        if (
            previous is not None
            and 0 <= now - previous < debounce_ns
        ):
            return
        _write_last(lock_fd, now)
        timeout = _number(
            "AWA_INTEGRITY_OBSERVER_TIMEOUT_SECONDS",
            _DEFAULT_TIMEOUT_SECONDS,
            minimum=0.05,
            maximum=_MAX_TIMEOUT_SECONDS,
        )
        _run_engine(trigger, timeout)
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(lock_fd)


def _detach(trigger: str) -> None:
    subprocess.Popen(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--worker",
            "--trigger",
            trigger,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    worker = False
    if args[:1] == ["--worker"]:
        worker = True
        args = args[1:]
    if len(args) != 2 or args[0] != "--trigger" or args[1] not in _TRIGGERS:
        return 0
    trigger = args[1]
    try:
        if worker:
            _worker(trigger)
        else:
            _detach(trigger)
    except Exception:
        # This observer is intentionally fail-open and has no safety authority.
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
