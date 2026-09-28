"""ADR 0025 process-scoped protocol/member lock order."""

from __future__ import annotations

import errno
import fcntl
import os
import stat
import threading
import time
from dataclasses import dataclass
from pathlib import Path


class LockError(RuntimeError):
    pass


class LockBusy(LockError):
    pass


class LockOrderError(LockError):
    pass


_LOCAL = threading.local()
_MAP_GUARD = threading.Lock()
_PROCESS_LOCKS: dict[str, threading.Lock] = {}


def _process_lock(key: str) -> threading.Lock:
    with _MAP_GUARD:
        return _PROCESS_LOCKS.setdefault(key, threading.Lock())


def _held() -> dict[str, str | None]:
    value = getattr(_LOCAL, "held", None)
    if value is None:
        value = {"protocol": None, "member": None}
        _LOCAL.held = value
    return value


def _secure_lock_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = os.lstat(path)
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise LockError("registration lock directory is not private")


@dataclass
class HeldLock:
    key: str
    path: Path
    descriptor: int
    process_lock: threading.Lock
    kind: str
    _released: bool = False

    @property
    def held(self) -> bool:
        return not self._released

    def verify(self) -> None:
        if self._released:
            raise LockError("lock is no longer held")
        descriptor = os.fstat(self.descriptor)
        parent_fd = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            named = os.stat(
                self.path.name,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
        finally:
            os.close(parent_fd)
        if (
            descriptor.st_dev,
            descriptor.st_ino,
            descriptor.st_mode,
            descriptor.st_uid,
            descriptor.st_nlink,
        ) != (
            named.st_dev,
            named.st_ino,
            named.st_mode,
            named.st_uid,
            named.st_nlink,
        ):
            raise LockError("lock object identity changed")
        if (
            not stat.S_ISREG(descriptor.st_mode)
            or stat.S_IMODE(descriptor.st_mode) != 0o600
            or descriptor.st_uid != os.geteuid()
            or descriptor.st_nlink != 1
        ):
            raise LockError("lock object permissions changed")

    def release(self) -> None:
        if self._released:
            return
        held = _held()
        try:
            fcntl.flock(self.descriptor, fcntl.LOCK_UN)
        finally:
            os.close(self.descriptor)
            self.process_lock.release()
            held[self.kind] = None
            self._released = True

    def __enter__(self) -> "HeldLock":
        return self

    def __exit__(self, *_: object) -> None:
        self.release()


class LockManager:
    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        _secure_lock_dir(self.directory)

    def _acquire(
        self, *, kind: str, key: str, timeout: float
    ) -> HeldLock:
        held = _held()
        if kind == "protocol":
            if held["protocol"] is not None or held["member"] is not None:
                raise LockOrderError("protocol lock must be acquired first")
        elif kind == "member":
            if held["member"] is not None:
                raise LockOrderError("a second member lock is forbidden")
        else:
            raise LockOrderError("unknown lock kind")
        process = _process_lock(str(self.directory / key))
        if not process.acquire(timeout=max(0.0, timeout)):
            raise LockBusy(f"{kind} process lock busy")
        descriptor = -1
        try:
            flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
            old_umask = os.umask(0o077)
            try:
                descriptor = os.open(self.directory / key, flags, 0o600)
            finally:
                os.umask(old_umask)
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_uid != os.geteuid()
                or info.st_nlink != 1
            ):
                raise LockError("invalid registration lock object")
            deadline = time.monotonic() + max(0.0, timeout)
            while True:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as exc:
                    if exc.errno not in (
                        errno.EWOULDBLOCK,
                        errno.EAGAIN,
                        errno.EACCES,
                    ):
                        raise
                    if time.monotonic() >= deadline:
                        raise LockBusy(f"{kind} kernel lock busy") from exc
                    time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))
            held[kind] = key
            result = HeldLock(
                key=key,
                path=self.directory / key,
                descriptor=descriptor,
                process_lock=process,
                kind=kind,
            )
            result.verify()
            return result
        except Exception:
            if descriptor >= 0:
                os.close(descriptor)
            process.release()
            raise

    def acquire_protocol(self, *, timeout: float = 5.0) -> HeldLock:
        return self._acquire(kind="protocol", key="protocol.lock", timeout=timeout)

    def acquire_member(self, member_id: str, *, timeout: float = 5.0) -> HeldLock:
        if (
            len(member_id) != 64
            or any(char not in "0123456789abcdef" for char in member_id)
        ):
            raise LockError("member id must be lowercase 64-hex")
        return self._acquire(
            kind="member", key=f"member-{member_id}.lock", timeout=timeout
        )
