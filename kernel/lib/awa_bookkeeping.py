#!/usr/bin/env python3
"""Validate and remove only AWA-owned in-worktree bookkeeping.

The cleanup kernel may tolerate ``.awa/lease.json`` only when the directory contains exactly that
one engine-authored, private, identity-matching file. Any uncertainty or additional content is
operator work and remains subject to the ordinary dirty/ignored-file safety gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from dataclasses import dataclass

SCHEMA = "awa-lease/v1"
REQUIRED_KEYS = (
    "schema",
    "lease_id",
    "worktree_path",
    "branch",
    "git_common_dir",
    "boot_id",
    "created_at",
)
MAX_LEASE_BYTES = 64 * 1024
_SEP = "\x1f"


@dataclass(frozen=True)
class Check:
    ok: bool
    reason: str


def _expected_lease_id(
    worktree_path: str,
    branch: str,
    git_common_dir: str,
    boot_id: str,
) -> str:
    material = _SEP.join(
        (
            os.path.abspath(worktree_path),
            branch,
            os.path.abspath(git_common_dir),
            boot_id,
        )
    )
    return "awa1-" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def _open_bookkeeping(root: str) -> tuple[int | None, dict[str, object] | None, Check]:
    awa_dir = os.path.join(root, ".awa")
    dir_fd: int | None = None
    try:
        flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
        dir_fd = os.open(awa_dir, flags)
        awa_stat = os.fstat(dir_fd)
        if not stat.S_ISDIR(awa_stat.st_mode):
            raise OSError("AWA bookkeeping path is not a directory")
        if awa_stat.st_uid != os.geteuid() or stat.S_IMODE(awa_stat.st_mode) != 0o700:
            return dir_fd, None, Check(False, "awa-directory-not-private-owned")
        if os.listdir(dir_fd) != ["lease.json"]:
            return dir_fd, None, Check(False, "awa-directory-has-unowned-content")
        lease_stat = os.stat("lease.json", dir_fd=dir_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(lease_stat.st_mode)
            or lease_stat.st_nlink != 1
        ):
            return dir_fd, None, Check(False, "lease-not-private-regular-file")
        if lease_stat.st_uid != os.geteuid() or stat.S_IMODE(lease_stat.st_mode) != 0o600:
            return dir_fd, None, Check(False, "lease-not-private-owned")
        if lease_stat.st_size <= 0 or lease_stat.st_size > MAX_LEASE_BYTES:
            return dir_fd, None, Check(False, "lease-size-invalid")
        file_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        file_fd = os.open("lease.json", file_flags, dir_fd=dir_fd)
        with os.fdopen(file_fd, "rb") as handle:
            opened_stat = os.fstat(handle.fileno())
            if (opened_stat.st_dev, opened_stat.st_ino) != (lease_stat.st_dev, lease_stat.st_ino):
                return dir_fd, None, Check(False, "lease-changed-during-read")
            raw = handle.read(MAX_LEASE_BYTES + 1)
        if len(raw) != lease_stat.st_size:
            return dir_fd, None, Check(False, "lease-changed-during-read")
        lease = json.loads(raw)
    except (FileNotFoundError, NotADirectoryError):
        if dir_fd is not None:
            os.close(dir_fd)
        return None, None, Check(False, "bookkeeping-absent")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        if dir_fd is not None:
            os.close(dir_fd)
        return None, None, Check(False, "bookkeeping-unreadable")
    return dir_fd, lease, Check(True, "bookkeeping-readable")


def _validate_payload(
    lease: dict[str, object] | None,
    root: str,
    branch: str,
    common_dir: str,
) -> Check:
    if not isinstance(lease, dict) or any(key not in lease for key in REQUIRED_KEYS):
        return Check(False, "lease-contract-invalid")
    for key in ("lease_id", "worktree_path", "branch", "git_common_dir", "boot_id", "created_at"):
        if not isinstance(lease.get(key), str) or not lease[key]:
            return Check(False, "lease-contract-invalid")
    if lease.get("schema") != SCHEMA:
        return Check(False, "lease-schema-invalid")
    expected_id = _expected_lease_id(
        lease["worktree_path"],
        lease["branch"],
        lease["git_common_dir"],
        lease["boot_id"],
    )
    if lease["lease_id"] != expected_id:
        return Check(False, "lease-identity-invalid")
    if os.path.abspath(lease["worktree_path"]) != os.path.abspath(root):
        return Check(False, "lease-worktree-mismatch")
    if lease["branch"] != branch:
        return Check(False, "lease-branch-mismatch")
    if os.path.abspath(lease["git_common_dir"]) != os.path.abspath(common_dir):
        return Check(False, "lease-common-dir-mismatch")
    return Check(True, "validated-awa-lease")


def validate(root: str, branch: str, common_dir: str) -> Check:
    dir_fd, lease, opened = _open_bookkeeping(root)
    try:
        if not opened.ok:
            return opened
        return _validate_payload(lease, root, branch, common_dir)
    finally:
        if dir_fd is not None:
            os.close(dir_fd)


def remove(root: str, branch: str, common_dir: str) -> Check:
    dir_fd, lease, opened = _open_bookkeeping(root)
    try:
        if not opened.ok:
            return opened
        checked = _validate_payload(lease, root, branch, common_dir)
        if not checked.ok:
            return checked
        try:
            os.unlink("lease.json", dir_fd=dir_fd)
        except OSError:
            return Check(False, "bookkeeping-changed-during-remove")
        return Check(True, "removed-awa-lease")
    finally:
        if dir_fd is not None:
            os.close(dir_fd)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("verb", choices=("validate", "remove"))
    parser.add_argument("--root", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--common-dir", required=True)
    args = parser.parse_args()
    fn = validate if args.verb == "validate" else remove
    result = fn(args.root, args.branch, args.common_dir)
    print(json.dumps({"ok": result.ok, "reason": result.reason}, sort_keys=True))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
