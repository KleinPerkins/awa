"""lease.py — .awa/lease.json (awa-lease/v1) writer/reader (frozen contract).

The lease is the on-disk claim that a worktree is an AWA-managed Safe Workspace.
Its identity is the derived hash (identity.lease_id), NEVER a bare pid. The file is
written under the worktree at `.awa/lease.json` with S4 perms; the same record is
mirrored into the durable SQLite state so the engine can discover orphaned leases
without walking the filesystem.

Required keys (frozen awa-contract.v1.json): schema, lease_id, worktree_path,
branch, git_common_dir, boot_id, created_at. pid is informational only.
"""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import stat
import time
from pathlib import Path

from . import identity, paths

SCHEMA = "awa-lease/v1"
REQUIRED_KEYS = (
    "schema", "lease_id", "worktree_path", "branch", "git_common_dir",
    "boot_id", "created_at",
)


def lease_path(worktree_path: str) -> Path:
    return Path(worktree_path) / ".awa" / "lease.json"


def build_lease(worktree_path: str, branch: str, git_common_dir: str,
                *, base_ref: str | None = None, head: str | None = None,
                boot: str | None = None) -> dict:
    boot = boot if boot is not None else identity.boot_id()
    lid = identity.lease_id(worktree_path, branch, git_common_dir, boot)
    return {
        "schema": SCHEMA,
        "lease_id": lid,
        "worktree_path": os.path.abspath(worktree_path),
        "branch": branch,
        "git_common_dir": os.path.abspath(git_common_dir),
        "boot_id": boot,
        "base_ref": base_ref,
        "head": head,
        "status": "active",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pid": os.getpid(),  # informational ONLY (never the identity — §H6).
    }


def validate(lease: dict) -> list[str]:
    """Return a list of contract violations ([] == valid)."""
    errs: list[str] = []
    for k in REQUIRED_KEYS:
        if k not in lease:
            errs.append(f"missing required key: {k}")
    if lease.get("schema") != SCHEMA:
        errs.append(f"schema must be {SCHEMA!r}, got {lease.get('schema')!r}")
    # identity must equal the derived hash (not a bare pid).
    if all(k in lease for k in ("worktree_path", "branch", "git_common_dir", "boot_id")):
        expect = identity.lease_id(
            lease["worktree_path"], lease["branch"], lease["git_common_dir"], lease["boot_id"]
        )
        if lease.get("lease_id") != expect:
            errs.append("lease_id does not match hash(worktree_path+branch+common_dir+boot_id)")
    lid = lease.get("lease_id", "")
    if lid.isdigit():
        errs.append("lease_id must not be a bare pid")
    return errs


def write_lease(worktree_path: str, lease: dict) -> Path:
    errs = validate(lease)
    if errs:
        raise ValueError("invalid lease: " + "; ".join(errs))
    lp = lease_path(worktree_path)
    paths.ensure_dir(lp.parent)
    paths.write_private(lp, json.dumps(lease, indent=2, sort_keys=False) + "\n")
    return lp


def _write_all(fd: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        written = os.write(fd, data[offset:])
        if written <= 0:
            raise OSError("short lease write")
        offset += written


def _private_awa_dir(worktree_path: str) -> tuple[Path, int]:
    root = Path(os.path.abspath(os.path.expanduser(worktree_path)))
    root_meta = root.lstat()
    if (
        root.is_symlink()
        or not stat.S_ISDIR(root_meta.st_mode)
        or os.path.realpath(str(root)) != str(root)
    ):
        raise OSError("worktree root is not one canonical real directory")
    directory = root / ".awa"
    try:
        directory.mkdir(mode=paths.DIR_MODE)
    except FileExistsError:
        pass
    metadata = directory.lstat()
    if (
        directory.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != paths.DIR_MODE
        or metadata.st_uid != os.getuid()
    ):
        raise OSError("AWA lease directory is not one owned private directory")
    flags = os.O_RDONLY
    flags |= getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(str(directory), flags)
    opened = os.fstat(fd)
    if (
        not stat.S_ISDIR(opened.st_mode)
        or (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino)
    ):
        os.close(fd)
        raise OSError("AWA lease directory changed during open")
    return directory, fd


def create_lease(worktree_path: str, lease: dict) -> Path:
    """Atomically publish a new lease without following or replacing existing state."""
    errs = validate(lease)
    if errs:
        raise ValueError("invalid lease: " + "; ".join(errs))
    directory, directory_fd = _private_awa_dir(worktree_path)
    target_name = "lease.json"
    temp_name = f".lease.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    temp_fd = -1
    linked = False
    try:
        temp_fd = os.open(
            temp_name,
            flags,
            paths.FILE_MODE,
            dir_fd=directory_fd,
        )
        os.fchmod(temp_fd, paths.FILE_MODE)
        payload = (
            json.dumps(lease, indent=2, sort_keys=False) + "\n"
        ).encode("utf-8")
        _write_all(temp_fd, payload)
        os.fsync(temp_fd)
        os.close(temp_fd)
        temp_fd = -1
        # link(2) is the portable no-replace publication primitive: it fails with
        # EEXIST instead of replacing malformed, mismatched, or symlinked state.
        os.link(
            temp_name,
            target_name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
            follow_symlinks=False,
        )
        linked = True
        os.fsync(directory_fd)
        os.unlink(temp_name, dir_fd=directory_fd)
        os.fsync(directory_fd)
        return directory / target_name
    finally:
        if temp_fd >= 0:
            os.close(temp_fd)
        if not linked:
            try:
                os.unlink(temp_name, dir_fd=directory_fd)
                os.fsync(directory_fd)
            except FileNotFoundError:
                pass
            except OSError:
                pass
        os.close(directory_fd)


def replace_lease(
    worktree_path: str,
    lease: dict,
    *,
    expected_lease_id: str,
) -> Path:
    """Atomically replace one already-validated lease without following links."""
    errs = validate(lease)
    if errs:
        raise ValueError("invalid lease: " + "; ".join(errs))
    if not isinstance(expected_lease_id, str) or not expected_lease_id:
        raise ValueError("expected lease identity required")
    directory, directory_fd = _private_awa_dir(worktree_path)
    read_flags = os.O_RDONLY
    read_flags |= getattr(os, "O_CLOEXEC", 0)
    read_flags |= getattr(os, "O_NONBLOCK", 0)
    read_flags |= getattr(os, "O_NOFOLLOW", 0)
    temp_name = f".lease.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    temp_fd = -1
    try:
        current_fd = os.open("lease.json", read_flags, dir_fd=directory_fd)
        try:
            current_meta = os.fstat(current_fd)
            if (
                not stat.S_ISREG(current_meta.st_mode)
                or stat.S_IMODE(current_meta.st_mode) != paths.FILE_MODE
                or current_meta.st_uid != os.getuid()
            ):
                raise OSError("existing lease is not one owned private file")
            current_raw = os.read(current_fd, 65_537)
        finally:
            os.close(current_fd)
        if len(current_raw) > 65_536:
            raise OSError("existing lease is oversized")
        try:
            current = json.loads(current_raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise OSError("existing lease is malformed") from exc
        if (
            not isinstance(current, dict)
            or validate(current)
            or current.get("lease_id") != expected_lease_id
        ):
            raise OSError("existing lease identity changed")

        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        temp_fd = os.open(
            temp_name,
            flags,
            paths.FILE_MODE,
            dir_fd=directory_fd,
        )
        os.fchmod(temp_fd, paths.FILE_MODE)
        payload = (
            json.dumps(lease, indent=2, sort_keys=False) + "\n"
        ).encode("utf-8")
        _write_all(temp_fd, payload)
        os.fsync(temp_fd)
        os.close(temp_fd)
        temp_fd = -1
        os.replace(
            temp_name,
            "lease.json",
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        os.fsync(directory_fd)
        return directory / "lease.json"
    finally:
        if temp_fd >= 0:
            os.close(temp_fd)
        with contextlib.suppress(OSError):
            os.unlink(temp_name, dir_fd=directory_fd)
        os.close(directory_fd)


def read_lease(worktree_path: str) -> dict | None:
    lp = lease_path(worktree_path)
    if not lp.exists():
        return None
    try:
        return json.loads(lp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
