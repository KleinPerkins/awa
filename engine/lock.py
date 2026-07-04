"""lock.py — per-git-common-dir advisory lock = the real collision boundary (§H6).

Two agents can only collide by mutating the SAME git object store. All
state-mutating lease/recovery operations serialize on an flock over a lockfile
keyed by the canonical `git rev-parse --git-common-dir`. Branch/path uniqueness is
necessary but the common-dir lock is what actually prevents index/ref races.

`flock` is advisory + POSIX; the lockfile lives on local disk under the state root
(never a synced/network path). A blocking acquire waits; a non-blocking acquire
raises `LockBusy` so a second concurrent writer is refused rather than racing.
"""

from __future__ import annotations

import errno
import fcntl
import os
import time
from contextlib import contextmanager
from pathlib import Path

from . import identity, paths


class LockBusy(RuntimeError):
    """Raised when a non-blocking acquire finds the lock already held."""


def lockfile_for(git_common_dir: str) -> Path:
    key = identity.common_dir_key(git_common_dir)
    return paths.locks_dir() / f"common-{key}.lock"


@contextmanager
def common_dir_lock(git_common_dir: str, *, blocking: bool = True, timeout: float = 30.0):
    """Hold the advisory lock for `git_common_dir` for the duration of the block.

    blocking=True waits up to `timeout` seconds (then raises LockBusy); blocking=False
    fails immediately with LockBusy if another writer holds it.
    """
    paths.ensure_dir(paths.locks_dir())
    lf = lockfile_for(git_common_dir)
    fd = os.open(str(lf), os.O_RDWR | os.O_CREAT, paths.FILE_MODE)
    try:
        os.chmod(lf, paths.FILE_MODE)
    except OSError:
        pass
    acquired = False
    try:
        if blocking:
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES):
                        raise
                    if time.monotonic() >= deadline:
                        raise LockBusy(f"lock busy after {timeout:g}s: {lf}")
                    time.sleep(0.05)
        else:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except OSError as exc:
                if exc.errno in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES):
                    raise LockBusy(f"lock busy (non-blocking): {lf}") from exc
                raise
        # Record holder pid for diagnostics (never used as identity — see identity.py).
        try:
            os.ftruncate(fd, 0)
            os.write(fd, f"{os.getpid()}\n".encode("ascii"))
            os.fsync(fd)
        except OSError:
            pass
        yield lf
    finally:
        if acquired:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
        os.close(fd)
