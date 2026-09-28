"""Stable Body C router for one exact active versioned receiver."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

from . import (
    registration_installer,
    registration_jcs,
    registration_projection,
)


_ROUTES = frozenset({"admission", "startup", "tick"})
_PROJECTION_FIELDS = {
    "schema",
    "candidate_digest",
    "receiver",
    "installed_file_hash",
    "direct_receipt_hash",
    "projection_file_generation",
}


def _projection_path() -> Path:
    configured = os.environ.get("AWA_REGISTRATION_PROJECTION")
    if configured:
        value = Path(configured).expanduser()
    else:
        data = os.environ.get("XDG_DATA_HOME")
        if data:
            value = (
                Path(data)
                / "awa/registration-runtime/active-projection.json"
            )
        else:
            home = os.environ.get("HOME")
            if not home:
                raise ValueError("registration projection root unavailable")
            value = (
                Path(home)
                / ".local/share/awa/registration-runtime/"
                "active-projection.json"
            )
    if (
        not value.is_absolute()
        or os.path.normpath(str(value)) != str(value)
        or os.path.realpath(value) != str(value)
    ):
        raise ValueError("registration projection path is not canonical")
    return value


def _private_projection(path: Path) -> dict:
    metadata = path.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_nlink != 1
        or metadata.st_size > 65_536
    ):
        raise ValueError("registration projection identity is unsafe")
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        rebound = os.fstat(descriptor)
        if (metadata.st_dev, metadata.st_ino) != (
            rebound.st_dev,
            rebound.st_ino,
        ):
            raise ValueError("registration projection changed")
        raw = os.read(descriptor, 65_537)
    finally:
        os.close(descriptor)
    if (
        not raw.endswith(b"\n")
        or raw.endswith(b"\n\n")
        or len(raw) > 65_536
    ):
        raise ValueError("registration projection bytes are malformed")
    value = registration_jcs.parse_canonical(raw[:-1])
    if (
        not isinstance(value, dict)
        or set(value) != _PROJECTION_FIELDS
        or value.get("schema")
        != registration_installer.RuntimeFileAuthority.PROJECTION_SCHEMA
        or registration_jcs.canonical_bytes(value) + b"\n" != raw
    ):
        raise ValueError("registration projection is not exact")
    return value


def _receiver(route: str) -> tuple[Path, dict]:
    if route not in _ROUTES:
        raise LookupError("unknown receiver route")
    projection_path = _projection_path()
    projection = _private_projection(projection_path)
    receipt = registration_installer.DirectReceiptStore(
        projection_path.parent / "direct-receipt.json"
    ).read()
    if (
        receipt.owner_mode != "DIRECT"
        or receipt.deployment_scope == "R0_THROWAWAY"
        or projection["candidate_digest"] != receipt.candidate_digest
        or projection["installed_file_hash"]
        != receipt.installed_file_hash
        or projection["direct_receipt_hash"] != receipt.digest
        or projection["projection_file_generation"]
        != receipt.projection_file_generation
    ):
        raise ValueError("receiver projection receipt mismatch")
    receiver = Path(str(projection["receiver"]))
    if (
        not receiver.is_absolute()
        or os.path.normpath(str(receiver)) != str(receiver)
        or os.path.realpath(receiver) != str(receiver)
    ):
        raise ValueError("receiver path is not canonical")
    receiver.relative_to(projection_path.parent / "receivers")
    metadata = receiver.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or metadata.st_nlink != 1
    ):
        raise ValueError("receiver identity is unsafe")
    if (
        registration_projection.installed_file_hash(receiver)
        != receipt.installed_file_hash
    ):
        raise ValueError("receiver bytes drifted")
    return receiver, projection


def main(argv: list[str] | None = None) -> int:
    arguments = list(argv if argv is not None else sys.argv[1:])
    if len(arguments) != 1 or arguments[0] not in _ROUTES:
        return 2
    try:
        receiver, _projection = _receiver(arguments[0])
        environment = dict(os.environ)
        os.execve(
            receiver,
            [str(receiver), arguments[0]],
            environment,
        )
    except BaseException:
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
