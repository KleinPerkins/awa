"""Stable Body C router for one exact active versioned receiver."""

from __future__ import annotations

import os
import json
import stat
import sys
from pathlib import Path

from . import (
    paths,
    registration_installer,
    registration_jcs,
    registration_projection,
    registration_store,
)


_ROUTES = frozenset({"admission", "startup", "tick"})
_DENIAL_MESSAGE = (
    "AWA registration is unavailable until deployment authority is active."
)
_PROJECTION_FIELDS = {
    "schema",
    "candidate_digest",
    "receiver",
    "installed_file_hash",
    "direct_receipt_hash",
    "projection_file_generation",
}
_PROTOCOL_RECEIPT_FIELDS = (
    "profile_hash",
    "runtime_capability_hash",
    "writer_binary_hash",
    "writer_capability_hash",
    "tool_inventory_hash",
    "hook_projection_hash",
    "hook_matcher_mode",
    "hook_matcher_hash",
    "projection_receipt_hash",
    "projection_file_generation",
    "installer_identity_hash",
    "installer_capability_hash",
)


def _receipt_protocol_value(
    receipt: registration_projection.DirectReceipt,
    field: str,
) -> object:
    if field == "projection_receipt_hash":
        return receipt.digest
    if field == "projection_file_generation":
        return int(receipt.projection_file_generation)
    return getattr(receipt, field)


def _receiver_authority_state(
    receipt: registration_projection.DirectReceipt,
) -> str:
    if receipt.deployment_scope == "R0_THROWAWAY":
        return "DENY_ONLY"
    store = registration_store.RegistrationStore(
        paths.registration_db_path()
    )
    try:
        protocol = store.current_protocol()
    finally:
        store.close()
    if protocol is None:
        raise ValueError("registration protocol authority is absent")
    if (
        int(protocol["protocol_generation"])
        == int(receipt.protocol_generation)
        and protocol["schema_hash"] == receipt.schema_hash
        and all(
            protocol[field]
            == _receipt_protocol_value(receipt, field)
            for field in _PROTOCOL_RECEIPT_FIELDS
        )
    ):
        if protocol["mode"] != "WRITABLE":
            raise ValueError("current receiver is not WRITABLE")
        return "CURRENT"
    if (
        protocol["mode"] in {"DRAINING", "CONTAINMENT"}
        and protocol["staged_generation"]
        == int(receipt.protocol_generation)
        and protocol["staged_schema_hash"] == receipt.schema_hash
        and all(
            protocol[f"staged_{field}"]
            == _receipt_protocol_value(receipt, field)
            for field in _PROTOCOL_RECEIPT_FIELDS
        )
    ):
        return "DENY_ONLY"
    raise ValueError("receipt is neither current nor staged authority")


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


def _active_pointer_path() -> Path:
    configured = os.environ.get("AWA_REGISTRATION_ACTIVE_BUNDLE")
    if configured:
        value = Path(configured).expanduser()
    else:
        data = os.environ.get("XDG_DATA_HOME")
        if data:
            value = (
                Path(data)
                / "awa/registration-runtime/active-bundle.json"
            )
        else:
            home = os.environ.get("HOME")
            if not home:
                raise ValueError("registration runtime root unavailable")
            value = (
                Path(home)
                / ".local/share/awa/registration-runtime/"
                "active-bundle.json"
            )
    if (
        not value.is_absolute()
        or os.path.normpath(str(value)) != str(value)
        or os.path.realpath(value) != str(value)
    ):
        raise ValueError("active bundle pointer path is not canonical")
    return value


def _private_authority(path: Path, *, mode: int) -> bytes:
    metadata = path.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != mode
        or metadata.st_nlink != 1
        or metadata.st_size > 8 * 1024 * 1024
    ):
        raise ValueError("bundle authority identity is unsafe")
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        rebound = os.fstat(descriptor)
        if (metadata.st_dev, metadata.st_ino) != (
            rebound.st_dev,
            rebound.st_ino,
        ):
            raise ValueError("bundle authority changed")
        chunks = []
        remaining = 8 * 1024 * 1024 + 1
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after = os.fstat(descriptor)
        visible = path.lstat()
        identity = (
            rebound.st_dev,
            rebound.st_ino,
            rebound.st_mode,
            rebound.st_uid,
            rebound.st_nlink,
            rebound.st_size,
            rebound.st_mtime_ns,
        )
        if (
            len(raw) > 8 * 1024 * 1024
            or identity
            != (
                after.st_dev,
                after.st_ino,
                after.st_mode,
                after.st_uid,
                after.st_nlink,
                after.st_size,
                after.st_mtime_ns,
            )
            or identity
            != (
                visible.st_dev,
                visible.st_ino,
                visible.st_mode,
                visible.st_uid,
                visible.st_nlink,
                visible.st_size,
                visible.st_mtime_ns,
            )
        ):
            raise ValueError("bundle authority changed while reading")
        return raw
    finally:
        os.close(descriptor)


def _bundle_launcher(
    route: str,
) -> tuple[Path, tuple[str, ...], dict[str, str], bool]:
    if route not in _ROUTES:
        raise LookupError("unknown receiver route")
    pointer_path = _active_pointer_path()
    pointer = registration_projection.ActiveBundlePointer.from_bytes(
        _private_authority(pointer_path, mode=0o600)
    )
    root = pointer_path.parent
    bundle = root / pointer.bundle_relative_dir
    bundle.relative_to(root / "bundles")
    manifest = registration_projection.BundleManifest.from_bytes(
        _private_authority(bundle / "bundle-manifest.json", mode=0o600)
    )
    projection = registration_projection.BundleProjection.from_bytes(
        _private_authority(
            bundle / "bundle-projection.json", mode=0o600
        )
    )
    receipt = registration_projection.DirectReceipt.from_bytes(
        _private_authority(bundle / "direct-receipt.json", mode=0o600)
    )
    if (
        manifest.digest != pointer.bundle_digest
        or projection.digest != pointer.bundle_projection_hash
        or receipt.digest != pointer.direct_receipt_hash
        or manifest.generation != pointer.generation
        or projection.generation != pointer.generation
        or receipt.bundle_generation != pointer.generation
        or receipt.bundle_digest != pointer.bundle_digest
        or receipt.bundle_projection_hash
        != pointer.bundle_projection_hash
        or manifest.import_manifest_hash
        != receipt.import_manifest_hash
        or projection.import_manifest_hash
        != receipt.import_manifest_hash
        or receipt.external_interpreter_hash
        != pointer.external_interpreter_hash
        or manifest.external_interpreter_hash
        != pointer.external_interpreter_hash
        or projection.external_interpreter_hash
        != pointer.external_interpreter_hash
        or receipt.interpreter_capability_hash
        != pointer.interpreter_capability_hash
        or manifest.interpreter_capability_hash
        != pointer.interpreter_capability_hash
        or projection.interpreter_capability_hash
        != pointer.interpreter_capability_hash
        or manifest.allowed_signers_contract_hash
        != receipt.allowed_signers_contract_hash
        or projection.allowed_signers_contract_hash
        != receipt.allowed_signers_contract_hash
    ):
        raise ValueError("active bundle authority mismatch")
    config_path = bundle / "runtime-config.json"
    config = registration_projection.LauncherConfig.from_bytes(
        _private_authority(config_path, mode=0o600)
    )
    if (
        config.file_hash != projection.runtime_config_hash
        or config.external_interpreter_hash
        != pointer.external_interpreter_hash
        or config.interpreter_capability_hash
        != pointer.interpreter_capability_hash
        or config.import_manifest_hash != projection.import_manifest_hash
    ):
        raise ValueError("launcher config authority mismatch")
    by_path = {entry.path: entry for entry in manifest.entries}
    for relative in (
        projection.receiver_relative_path,
        projection.launcher_relative_path,
        "import-manifest.json",
        "runtime-config.json",
    ):
        entry = by_path.get(relative)
        if entry is None:
            raise ValueError("bundle execution entry is absent")
        path = bundle / relative
        payload = _private_authority(path, mode=int(entry.mode))
        if (
            len(payload) != int(entry.size)
            or __import__("hashlib").sha256(payload).hexdigest()
            != entry.sha256
        ):
            raise ValueError("bundle execution entry drifted")
    interpreter = Path(config.interpreter_path)
    receiver = bundle / projection.receiver_relative_path
    if (
        not interpreter.is_absolute()
        or os.path.realpath(interpreter) != str(interpreter)
    ):
        raise ValueError("signed interpreter path is not canonical")
    environment = {
        key: value
        for key, value in os.environ.items()
        if key
        in {
            "HOME",
            "TMPDIR",
            "XDG_CONFIG_HOME",
            "XDG_DATA_HOME",
            "XDG_STATE_HOME",
            "AWA_HOME",
            "AWA_HOST_POLICY",
        }
    }
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["AWA_REGISTRATION_INTERPRETER"] = str(interpreter)
    arguments = (
        str(receiver),
        route,
    )
    return (
        receiver,
        arguments,
        environment,
        _receiver_authority_state(receipt) == "DENY_ONLY",
    )


def _deny_only(route: str) -> int:
    if route != "admission":
        return 2
    raw = sys.stdin.buffer.read(65_537)
    if len(raw) > 65_536:
        return 1
    try:
        value = json.loads(raw.decode("utf-8", "strict"))
        event = value.get("hook_event_name")
    except (UnicodeError, json.JSONDecodeError, AttributeError):
        return 1
    if event == "subagentStart":
        response = {
            "permission": "deny",
            "user_message": _DENIAL_MESSAGE,
        }
    elif event in {
        "preToolUse",
        "beforeShellExecution",
        "beforeReadFile",
        "beforeMCPExecution",
        "beforeMCP",
    }:
        response = {
            "permission": "deny",
            "user_message": _DENIAL_MESSAGE,
            "agent_message": _DENIAL_MESSAGE,
        }
    else:
        return 1
    sys.stdout.buffer.write(
        (
            json.dumps(
                response,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            )
            + "\n"
        ).encode("ascii")
    )
    sys.stdout.buffer.flush()
    return 2


def private_runtime_main(
    argv: list[str] | None = None,
    *,
    authority_bytes: tuple[bytes, ...] | None = None,
) -> int:
    """Dispatch only after the platform child has completed v7 GO.

    Runtime selection, interpreter selection, owner verification, and durable
    spawn authority are intentionally absent here; the root-owned parent/child
    boundary has already retained and revalidated those exact descriptors.
    """

    arguments = list(argv if argv is not None else sys.argv[1:])
    if len(arguments) != 1 or arguments[0] not in {
        "admission",
        "receiver",
        "startup",
        "tick",
    }:
        return 2
    if (
        authority_bytes is None
        or len(authority_bytes) != 5
        or any(not isinstance(value, bytes) for value in authority_bytes)
    ):
        return 1
    try:
        from . import registration_host

        route = "admission" if arguments[0] == "receiver" else arguments[0]
        return int(registration_host.main([route]))
    except BaseException:
        return 1


def main(argv: list[str] | None = None) -> int:
    arguments = list(argv if argv is not None else sys.argv[1:])
    if len(arguments) != 1 or arguments[0] not in _ROUTES:
        return 2
    try:
        executable, command, environment, r0_deny_only = (
            _bundle_launcher(arguments[0])
        )
        if r0_deny_only:
            return _deny_only(arguments[0])
        os.execve(
            executable,
            list(command),
            environment,
        )
    except BaseException:
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
