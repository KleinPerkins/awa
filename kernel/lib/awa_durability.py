#!/usr/bin/env python3
"""AWA kernel physical-durability primitives.

Stdlib only.  Every critical kernel namespace writer uses these functions so a
successful return has one meaning on every call site: contents and the
containing namespace have both been synchronously persisted.  Darwin requires
``F_FULLFSYNC`` after ``fsync`` for files *and* directories; absence or failure
is an error, never a silent downgrade.
"""

from __future__ import annotations

import errno
import fcntl
import os
import stat
import sys
from typing import Callable


DIR_MODE = 0o700
FILE_MODE = 0o600


def _absolute(path: str) -> str:
    """Normalize trusted system-prefix links without following a private-path link.

    Darwin exposes roots such as ``/var`` and ``/tmp`` as root-owned links.  They must resolve for
    component-by-component directory creation, but a user-owned link anywhere below that trusted
    prefix is an unsafe namespace substitution.  Preserve the final component so every caller's
    no-follow open/lstat/replace/unlink applies to the name itself.
    """
    absolute = os.path.abspath(os.fspath(path))
    drive, tail = os.path.splitdrive(absolute)
    parts = [part for part in tail.split(os.sep) if part]
    if not parts:
        return drive + os.sep
    cursor = drive + os.sep
    for part in parts[:-1]:
        candidate = os.path.join(cursor, part)
        try:
            st = os.lstat(candidate)
        except FileNotFoundError:
            cursor = candidate
            continue
        if stat.S_ISLNK(st.st_mode):
            if getattr(st, "st_uid", -1) != 0:
                raise OSError(
                    errno.ELOOP,
                    "durability path refuses an untrusted symbolic-link component",
                )
            cursor = os.path.realpath(candidate)
        else:
            cursor = candidate
    return os.path.join(cursor, parts[-1])


def _retry_eintr(call: Callable, *args):
    while True:
        try:
            return call(*args)
        except OSError as exc:
            if exc.errno != errno.EINTR:
                raise


def _sync_fd(fd: int) -> None:
    """Synchronously persist an already-open regular file or directory."""
    _retry_eintr(os.fsync, fd)
    if sys.platform == "darwin":
        full_sync = getattr(fcntl, "F_FULLFSYNC", None)
        if full_sync is None:
            raise OSError(
                errno.ENOTSUP,
                "Darwin F_FULLFSYNC is unavailable; durability cannot be certified",
            )
        _retry_eintr(fcntl.fcntl, fd, full_sync)


def write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        try:
            written = os.write(fd, view)
        except OSError as exc:
            if exc.errno == errno.EINTR:
                continue
            raise
        if written <= 0:
            raise OSError(errno.EIO, "short durable write")
        view = view[written:]


def _open_nofollow(path: str, *, directory: bool) -> int:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if directory:
        flags |= getattr(os, "O_DIRECTORY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    return os.open(path, flags)


def sync_directory(path: str) -> None:
    absolute = _absolute(path)
    fd = _open_nofollow(absolute, directory=True)
    try:
        st = os.fstat(fd)
        if not stat.S_ISDIR(st.st_mode):
            raise OSError(errno.ENOTDIR, "durability target is not a directory")
        _sync_fd(fd)
    finally:
        os.close(fd)


def sync_regular(path: str) -> None:
    absolute = _absolute(path)
    fd = _open_nofollow(absolute, directory=False)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise OSError(errno.EINVAL, "durability target is not a regular file")
        _sync_fd(fd)
    finally:
        os.close(fd)


def sync_parent(path: str) -> None:
    sync_directory(os.path.dirname(_absolute(path)))


def adopt_visible(path: str) -> None:
    """Explicitly re-sync one already-visible file/directory and its parent.

    This is the recovery operation for a prior process that made a namespace
    change visible but could not certify its parent-directory sync.
    """
    absolute = _absolute(path)
    st = os.lstat(absolute)
    if stat.S_ISLNK(st.st_mode):
        raise OSError(errno.ELOOP, "durability adoption refuses symbolic links")
    if stat.S_ISREG(st.st_mode):
        sync_regular(absolute)
    elif stat.S_ISDIR(st.st_mode):
        sync_directory(absolute)
    else:
        raise OSError(errno.EINVAL, "durability adoption refuses special files")
    sync_parent(absolute)


def _path_components(path: str) -> list[str]:
    absolute = _absolute(path)
    drive, tail = os.path.splitdrive(absolute)
    parts = [part for part in tail.split(os.sep) if part]
    cursor = drive + os.sep
    out = []
    for part in parts:
        cursor = os.path.join(cursor, part)
        out.append(cursor)
    return out


def ensure_private_directory(path: str, mode: int = DIR_MODE) -> None:
    """Create missing components one at a time and durably publish each one."""
    absolute = _absolute(path)
    components = _path_components(absolute)
    if not components:
        raise OSError(errno.EINVAL, "private directory cannot be filesystem root")
    first_missing = len(components)
    for index, component in enumerate(components):
        try:
            st = os.lstat(component)
        except FileNotFoundError:
            first_missing = index
            break
        if not stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode):
            raise OSError(errno.ENOTDIR, "private directory path is not a real directory")

    for component in components[first_missing:]:
        parent = os.path.dirname(component)
        try:
            os.mkdir(component, mode)
        except FileExistsError:
            st = os.lstat(component)
            if not stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode):
                raise OSError(
                    errno.ENOTDIR,
                    "private directory raced with a non-directory",
                )
        os.chmod(component, mode)
        sync_directory(component)
        sync_directory(parent)

    final_st = os.lstat(absolute)
    if not stat.S_ISDIR(final_st.st_mode) or stat.S_ISLNK(final_st.st_mode):
        raise OSError(errno.ENOTDIR, "private directory is not a real directory")
    os.chmod(absolute, mode)
    sync_directory(absolute)
    sync_parent(absolute)


def atomic_private_replace(
    path: str,
    data: bytes,
    *,
    file_mode: int = FILE_MODE,
    dir_mode: int = DIR_MODE,
) -> None:
    """Complete-write, sync, replace, and parent-sync one private file."""
    absolute = _absolute(path)
    parent = os.path.dirname(absolute)
    ensure_private_directory(parent, dir_mode)
    temporary = (
        absolute
        + ".tmp."
        + str(os.getpid())
        + "."
        + os.urandom(8).hex()
    )
    fd = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        file_mode,
    )
    replaced = False
    try:
        os.fchmod(fd, file_mode)
        write_all(fd, data)
        _sync_fd(fd)
    finally:
        os.close(fd)
    try:
        os.replace(temporary, absolute)
        replaced = True
        sync_directory(parent)
    finally:
        if not replaced:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def create_private_exclusive(
    path: str,
    data: bytes,
    *,
    file_mode: int = FILE_MODE,
    dir_mode: int = DIR_MODE,
) -> None:
    """Durably create a one-use private file with ``O_EXCL``."""
    absolute = _absolute(path)
    parent = os.path.dirname(absolute)
    ensure_private_directory(parent, dir_mode)
    try:
        fd = os.open(
            absolute,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
            file_mode,
        )
    except FileExistsError:
        # A prior attempt may have made the one-use name visible before its parent sync failed.
        # Re-adopt that exact name before the caller is allowed to classify it as consumed.
        adopt_visible(absolute)
        raise
    try:
        os.fchmod(fd, file_mode)
        write_all(fd, data)
        _sync_fd(fd)
    finally:
        os.close(fd)
    sync_directory(parent)


def durable_unlink(path: str, *, missing_ok: bool = True) -> bool:
    """Unlink and persist the containing namespace.

    A parent-sync failure is propagated even though the name may already be
    absent in-process.  Callers must not treat that visibility as durability.
    """
    absolute = _absolute(path)
    try:
        os.unlink(absolute)
    except FileNotFoundError:
        if missing_ok:
            sync_parent(absolute)
            return False
        raise
    sync_parent(absolute)
    return True


def durable_rmdir(path: str, *, missing_ok: bool = True) -> bool:
    absolute = _absolute(path)
    try:
        os.rmdir(absolute)
    except FileNotFoundError:
        if missing_ok:
            sync_parent(absolute)
            return False
        raise
    sync_parent(absolute)
    return True


def durable_adopt(source: str, destination: str) -> None:
    """Atomically adopt a prepared file/directory and persist both namespaces."""
    source_abs = _absolute(source)
    destination_abs = _absolute(destination)
    source_parent = os.path.dirname(source_abs)
    destination_parent = os.path.dirname(destination_abs)
    os.replace(source_abs, destination_abs)
    adopt_visible(destination_abs)
    if source_parent != destination_parent:
        sync_directory(source_parent)
