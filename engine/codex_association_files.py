"""Small no-follow descriptor helpers shared by association probe and store.

All target names are policy checked before access. No realpath traversal, mkdir
repair, permission repair, or generic repository helper is used here.
"""
from __future__ import annotations

import contextlib
import errno
import fcntl
import os
import stat
import sys

from .codex_association import AssociationError, path_text


def close_all(fds, primary=None):
    error = primary
    for fd in reversed(fds):
        try:
            os.close(fd)
        except OSError as exc:
            if error is None:
                error = exc
    if primary is None and error is not None:
        raise error


def exchange_operation():
    """Return the qualified kernel exchange, never a check-then-rename fallback.

    Darwin: sys/stdio.h RENAME_SWAP=2, renameatx_np (macOS 10.12+).
    Linux qualification: renameat2 RENAME_EXCHANGE=2. Production host gating
    remains macOS-only. Both names survive an exchange for displaced proof.
    """
    import ctypes
    library = ctypes.CDLL(None, use_errno=True)
    name = "renameatx_np" if sys.platform == "darwin" else "renameat2" if sys.platform.startswith("linux") else None
    function = getattr(library, name, None) if name else None
    if function is None:
        raise OSError(errno.ENOTSUP, "atomic exchange unavailable")
    function.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    function.restype = ctypes.c_int
    def exchange(directory, source, target):
        if function(directory, os.fsencode(source), directory, os.fsencode(target), 2) != 0:
            raise OSError(ctypes.get_errno(), "atomic exchange failed")
    return exchange


class Access:
    def __init__(self, matcher):
        self.matcher = matcher

    def check(self, path):
        path_text(path)
        if self.matcher.classify(path).matched:
            raise AssociationError("policy_refused")

    @staticmethod
    def _kernel_path(fd):
        if sys.platform == "darwin":
            return fcntl.fcntl(fd, 50, b"\0" * 1024).split(b"\0", 1)[0].decode("utf-8")
        if sys.platform.startswith("linux"):
            return os.readlink("/proc/self/fd/" + str(fd))
        raise AssociationError("physical_identity_unavailable")

    @contextlib.contextmanager
    def directory(self, path, *, create=False, private_from=None):
        self.check(path)  # Refuse the complete target before even inspecting '/'.
        if len(path.split("/")) > 128:
            raise AssociationError("unsafe_state" if private_from else "physical_identity_unavailable")
        owned = []
        primary, entered = None, False
        try:
            fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            owned.append(fd)
            current = ""
            for part in path.strip("/").split("/") if path != "/" else []:
                current += "/" + part
                self.check(current)
                parent, made = fd, False
                try:
                    nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                except FileNotFoundError:
                    if not create:
                        raise
                    try:
                        os.mkdir(part, 0o700, dir_fd=fd)
                    except FileExistsError:
                        pass
                    nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    made = True
                owned.append(nxt)
                fd = nxt
                if private_from and (current == private_from or current.startswith(private_from + "/")):
                    self.private_directory(fd)
                if made:
                    # Entry creation must be durable too. Register the owned FD
                    # before these calls so every failure still closes it.
                    os.fsync(nxt)
                    os.fsync(parent)
            # A descriptor's kernel path verifies canonical spelling without
            # following another path (including case aliases on macOS).
            actual = self._kernel_path(fd)
            if actual != path:
                raise AssociationError("physical_identity_unavailable")
            entered = True
            yield fd
            # A renamed/replaced namespace or changed privacy cannot support a
            # success claim through the original (still-readable) descriptor.
            current = ""
            for index, part in enumerate(path.strip("/").split("/") if path != "/" else []):
                current += "/" + part
                held = owned[index + 1]
                if self._kernel_path(held) != current:
                    raise AssociationError("unsafe_state" if private_from else "identity_changed")
                st = os.fstat(held)
                named = os.stat(part, dir_fd=owned[index], follow_symlinks=False)
                if not stat.S_ISDIR(named.st_mode) or (st.st_dev, st.st_ino) != (named.st_dev, named.st_ino):
                    raise AssociationError("unsafe_state" if private_from else "identity_changed")
                if private_from and (current == private_from or current.startswith(private_from + "/")):
                    self.private_directory(held)
        except OSError as exc:
            primary = exc
            if private_from and not entered and not isinstance(exc, FileNotFoundError):
                raise AssociationError("unsafe_state") from exc
            raise
        except BaseException as exc:
            primary = exc
            raise
        finally:
            close_all(owned, primary)

    @staticmethod
    def private_directory(fd):
        st = os.fstat(fd)
        if st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o700:
            raise AssociationError("unsafe_state")

    @staticmethod
    def private_file(fd, path=None):
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid()
                or st.st_nlink != 1 or stat.S_IMODE(st.st_mode) != 0o600):
            raise AssociationError("unsafe_state")
        if path is not None and Access._kernel_path(fd) != path:
            raise AssociationError("unsafe_state")

    def directory_identity(self, path):
        with self.directory(path) as fd:
            st = os.fstat(fd)
            return st.st_dev, st.st_ino

    def read(self, path, cap, *, private=False, parent_fd=None):
        self.check(path)
        if parent_fd is None:
            with self.directory(os.path.dirname(path)) as directory:
                return self.read(path, cap, private=private, parent_fd=directory)
        try:
            fd = os.open(os.path.basename(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent_fd)
        except OSError as exc:
            if private and exc.errno in (errno.EACCES, errno.EPERM, errno.ENOTDIR, errno.EISDIR, errno.ELOOP):
                raise AssociationError("unsafe_state") from exc
            raise
        primary = None
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
                raise AssociationError("unsafe_state" if private else "physical_identity_unavailable")
            if private:
                self.private_file(fd, path)
            if st.st_size > cap:
                raise AssociationError("limit_exceeded" if private else "physical_identity_unavailable")
            chunks, size = [], 0
            while True:
                chunk = os.read(fd, min(65536, cap + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk); size += len(chunk)
                if size > cap:
                    raise AssociationError("limit_exceeded" if private else "physical_identity_unavailable")
            after = os.fstat(fd)
            named = os.stat(os.path.basename(path), dir_fd=parent_fd, follow_symlinks=False)
            identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            if identity(st) != identity(after) or identity(after) != identity(named):
                raise AssociationError("unsafe_state" if private else "identity_changed")
            if private:
                self.private_file(fd, path)
            return b"".join(chunks)
        except BaseException as exc:
            primary = exc
            raise
        finally:
            close_all([fd], primary)

    def exists(self, path):
        self.check(path)
        with self.directory(os.path.dirname(path)) as fd:
            try:
                os.stat(os.path.basename(path), dir_fd=fd, follow_symlinks=False)
                return True
            except FileNotFoundError:
                return False

    def locator(self, parent, value):
        if not value or "\n" in value or "\r" in value or "\0" in value:
            raise AssociationError("physical_identity_unavailable")
        target = os.path.normpath(value if value.startswith("/") else parent + "/" + value)
        self.check(target)
        return target
