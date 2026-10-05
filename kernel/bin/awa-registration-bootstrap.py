#!/usr/bin/env python3
"""Root-owned, stdlib-only registration platform parent.

This module intentionally imports no AWA product package.  It verifies and
retains installed authority, reconciles durable spawn intent, and is the sole
ordinary-spawn parent for the private-runtime child.
"""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import dataclasses
import errno
import fcntl
import hashlib
import json
import os
import pwd
import re
import secrets
import select
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable, Iterable, Mapping, NamedTuple, Protocol


INSTALL_ROOT = Path("/Library/Application Support/AWA")
ENTRYPOINT_PATH = INSTALL_ROOT / "bin/awa-registration"
BOOTSTRAP_PATH = INSTALL_ROOT / "bootstrap/v1/bootstrap.py"
CHILD_PATH = INSTALL_ROOT / "bootstrap/v1/child.py"
CURRENT_PATH = INSTALL_ROOT / "runtime/current.v1"
RUNTIME_VERSIONS = INSTALL_ROOT / "runtime/versions"
RUNTIME_LOCKS = INSTALL_ROOT / "runtime/locks"
PLATFORM_PYTHON = "/usr/bin/python3"
SSH_KEYGEN = "/usr/bin/ssh-keygen"
OWNER_PRINCIPAL = "KleinPerkins"
OWNER_SIGNERS_V2 = (
    'KleinPerkins namespaces="awa-private-runtime-release-envelope-v1,'
    'awa-registration-owner-gate-v3" ssh-ed25519 '
    "AAAAC3NzaC1lZDI1NTE5AAAAIE+scgn2qp86lkQWcVDpJ+SXT/pVF0DntlxGVnmnFyEp\n"
).encode("ascii")
ROUTES = ("admission", "receiver", "startup", "tick")
FD_ASSIGNMENTS = {
    "control": 3,
    "runtime_manifest": 4,
    "awa_import_manifest": 5,
    "signed_authority": 6,
    "current": 7,
    "launch": 8,
}
MINIMUM_REMAP_FD = 10
COMMON_MEASUREMENT_FILES = (
    "bootstrap.py",
    "child.py",
    "entrypoint",
)
RUNTIME_MANIFEST_FIELDS = {
    "schema",
    "source_lock_sha256",
    "normalizer_source_sha256",
    "signing_recipe_source_sha256",
    "record_framing_digest",
    "records",
}
RUNTIME_RECORD_FIELDS = {"path", "mode", "size", "sha256", "macho"}
CURRENT_FIELDS = {
    "schema",
    "epoch",
    "active_manifest_sha256",
    "previous_manifest_sha256",
    "active_release_envelope_digest",
    "installed_at_wall_ns",
    "installer_audit_digest",
    "predecessor_current_digest",
    "current_digest",
}
RELEASE_FIELDS = {
    "schema",
    "repository",
    "exact_head",
    "source_lock_sha256",
    "normalizer_source_sha256",
    "signing_recipe_source_sha256",
    "capability_digest",
    "sqlite_compile_options_hash",
    "runtime_manifest_sha256",
    "signature_inventory_sha256",
    "archive_sha256",
    "archive_size",
    "sbom_sha256",
    "license_inventory_sha256",
    "qualification_packet_digest",
    "minimum_epoch",
    "release_envelope_digest",
}
OWNER_GATE_FIELDS = {
    "schema",
    "repository",
    "authorized_by",
    "deployment_scope",
    "direct_receipt_body_hash",
    "candidate_digest",
    "bundle_digest",
    "bundle_projection_hash",
    "import_manifest_hash",
    "source_lock_sha256",
    "runtime_release_envelope_digest",
    "runtime_manifest_sha256",
    "signature_inventory_sha256",
    "capability_digest",
    "qualification_packet_digest",
    "denial_proof_vector_hash",
    "installed_file_hash",
    "wrapper_runtime_hash",
    "bootstrap_contract_hash",
    "private_runtime_contract_hash",
    "privileged_envelope_contract_hash",
    "admin_audit_contract_hash",
    "installer_identity_hash",
    "installer_capability_hash",
    "allowed_signers_contract_path_hash",
    "allowed_signers_contract_hash",
    "signer_public_key_sha256",
    "signer_fingerprint",
    "key_enrollment_digest",
    "key_current_enrollment_hash",
    "accepted_v6_normalized_digest",
    "implementation_exact_head",
    "canonical_root_hash",
    "member_id",
    "harness_root_hash",
    "authorized",
}
IMPORT_MANIFEST_FIELDS = {"schema", "entry_modules", "records"}
IMPORT_RECORD_FIELDS = {"path", "role", "mode", "size", "sha256"}
REQUIRED_PYTHON_APIS = (
    "fcntl.flock",
    "os.O_NOFOLLOW",
    "os.fstat",
    "sqlite3.Connection.setconfig",
    "sqlite3.SQLITE_DBCONFIG_DEFENSIVE",
    "sqlite3.SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE",
)
CAPABILITY_PROBE_SOURCE = r'''
import fcntl
import os
import platform
import sqlite3
import sys
import tempfile

required = (
    hasattr(fcntl, "flock"),
    hasattr(os, "O_NOFOLLOW"),
    hasattr(os, "fstat"),
    hasattr(sqlite3.Connection, "setconfig"),
    hasattr(sqlite3, "SQLITE_DBCONFIG_DEFENSIVE"),
    hasattr(sqlite3, "SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE"),
)
if not all(required):
    raise RuntimeError("required private-runtime API unavailable")
with tempfile.TemporaryDirectory(prefix="awa-capability-probe.") as directory:
    database = os.path.join(directory, "probe.sqlite3")
    connection = sqlite3.connect(database)
    try:
        journal_mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA fullfsync=ON")
        connection.execute("PRAGMA checkpoint_fullfsync=ON")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA locking_mode=NORMAL")
        connection.setconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE, True)
        connection.setconfig(sqlite3.SQLITE_DBCONFIG_TRUSTED_SCHEMA, False)
        connection.setconfig(sqlite3.SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE, True)
        source_id = connection.execute("SELECT sqlite_source_id()").fetchone()[0]
        options = sorted(
            {row[0] for row in connection.execute("PRAGMA compile_options")},
            key=lambda value: value.encode("utf-8"),
        )
        probe_result = {
            "platform": sys.platform,
            "os_build": platform.platform(),
            "python_implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
            "sqlite_runtime_version": sqlite3.sqlite_version,
            "sqlite_source_id": source_id,
            "sqlite_vfs_name": "unix",
            "journal_mode": str(journal_mode).lower(),
            "synchronous": "full",
            "fullfsync": bool(connection.execute("PRAGMA fullfsync").fetchone()[0]),
            "checkpoint_fullfsync": bool(connection.execute("PRAGMA checkpoint_fullfsync").fetchone()[0]),
            "foreign_keys": bool(connection.execute("PRAGMA foreign_keys").fetchone()[0]),
            "connection_setconfig_available": True,
            "sqlite_dbconfig_defensive_available": True,
            "defensive": bool(connection.getconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE)),
            "trusted_schema": bool(connection.getconfig(sqlite3.SQLITE_DBCONFIG_TRUSTED_SCHEMA)),
            "locking_mode": str(connection.execute("PRAGMA locking_mode").fetchone()[0]).lower(),
            "nofollow_available": True,
            "checkpoint_on_close": not bool(connection.getconfig(sqlite3.SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE)),
            "compile_options": options,
        }
    finally:
        connection.close()
'''.strip() + "\n"
SPAWN_PHASES = ("PREPARED", "SPAWNED", "READY", "GO", "PRODUCT")
ALL_PHASES = SPAWN_PHASES + ("TERMINAL",)
TERMINAL_REASONS = (
    "NORMAL_EXIT",
    "NATURAL_EXIT_RECONCILED",
    "REBOOT_CLEARED",
    "SPAWN_FAILED",
)
CONFIRMED_INERT_MESSAGE = (
    "Interrupted AWA bootstrap residue was detected. AWA remains inactive. "
    "Wait for the process to exit or restart the Mac."
)
AMBIGUOUS_RESIDUE_MESSAGE = (
    "AWA found ambiguous interrupted-bootstrap state. AWA remains inactive. "
    "Restart the Mac before trying again."
)
HEX64 = re.compile(r"^[0-9a-f]{64}$")
UINT = re.compile(r"^(?:0|[1-9][0-9]*)$")
INTENT_FIELDS = (
    "schema",
    "phase",
    "nonce",
    "route",
    "private_executable_path",
    "private_executable_sha256",
    "runtime_manifest_sha256",
    "version_lock_identity",
    "parent_pid",
    "parent_pidversion",
    "child_pid",
    "child_pidversion",
    "mapped_vnode_dev",
    "mapped_vnode_ino",
    "boot_identity",
    "prepared_wall_ns",
    "published_wall_ns",
    "terminal_reason",
    "intent_digest",
)


class ProtocolRefusal(RuntimeError):
    pass


class MeasurementRefusal(RuntimeError):
    pass


def canonical_bytes(value: object) -> bytes:
    def validate(item: object) -> None:
        if item is None or isinstance(item, (str, bool)):
            return
        if type(item) is int:
            if item < 0 or item > (1 << 64) - 1:
                raise ValueError("integer outside unsigned 64-bit")
            return
        if isinstance(item, list):
            for child in item:
                validate(child)
            return
        if isinstance(item, dict):
            if not all(isinstance(key, str) for key in item):
                raise ValueError("non-text object key")
            for child in item.values():
                validate(child)
            return
        raise ValueError("unsupported canonical JSON type")

    validate(value)
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_lf_bytes(value: object) -> bytes:
    return canonical_bytes(value) + b"\n"


def parse_canonical_lf(raw: bytes, *, maximum: int = 4 * 1024 * 1024) -> object:
    if (
        not isinstance(raw, bytes)
        or not 2 <= len(raw) <= maximum
        or not raw.endswith(b"\n")
        or raw.endswith(b"\n\n")
        or b"\r" in raw
        or b"\0" in raw
        or raw.startswith(b"\xef\xbb\xbf")
    ):
        raise ValueError("authority framing refused")

    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate authority key: {key}")
            result[key] = value
        return result

    value = json.loads(
        raw[:-1].decode("utf-8", "strict"),
        object_pairs_hook=pairs,
        parse_float=lambda _: (_ for _ in ()).throw(
            ValueError("floating-point authority refused")
        ),
        parse_constant=lambda _: (_ for _ in ()).throw(
            ValueError("non-finite authority refused")
        ),
    )
    if canonical_lf_bytes(value) != raw:
        raise ValueError("authority is not canonical JCS+LF")
    return value


def authority_digest(domain: str, value: Mapping[str, object]) -> str:
    return hashlib.sha256(
        domain.encode("ascii") + b"\0" + canonical_lf_bytes(dict(value))
    ).hexdigest()


def _is_hex64(value: object) -> bool:
    return isinstance(value, str) and HEX64.fullmatch(value) is not None


def _decimal(value: object, name: str) -> int:
    if not isinstance(value, str) or UINT.fullmatch(value) is None:
        raise ValueError(f"{name} is not canonical unsigned decimal text")
    number = int(value)
    if number > (1 << 64) - 1:
        raise ValueError(f"{name} outside unsigned range")
    return number


class FdAction(NamedTuple):
    operation: str
    role: str
    source: int
    target: int


def plan_fd_remap(sources: Mapping[str, int]) -> tuple[FdAction, ...]:
    if set(sources) != set(FD_ASSIGNMENTS):
        raise ValueError("descriptor role set mismatch")
    raw = list(sources.values())
    if (
        any(type(fd) is not int or fd < 0 for fd in raw)
        or len(set(raw)) != len(raw)
    ):
        raise ValueError("descriptor sources must be distinct nonnegative ints")
    actions: list[FdAction] = []
    high_by_role: dict[str, int] = {}
    next_high = max(MINIMUM_REMAP_FD, max(raw, default=-1) + 1)
    occupied = set(raw) | set(FD_ASSIGNMENTS.values())
    for role in FD_ASSIGNMENTS:
        while next_high in occupied:
            next_high += 1
        high_by_role[role] = next_high
        occupied.add(next_high)
        actions.append(
            FdAction("duplicate_high", role, sources[role], next_high)
        )
        next_high += 1
    for role, target in FD_ASSIGNMENTS.items():
        actions.append(FdAction("map_fixed", role, high_by_role[role], target))
    for role, source in high_by_role.items():
        actions.append(FdAction("close_high", role, source, -1))
    return tuple(actions)


def plan_fd_remap_v2(sources: Mapping[int, int]) -> tuple[FdAction, ...]:
    targets = tuple(sorted(sources))
    if (
        not targets
        or targets != tuple(range(3, max(targets) + 1))
        or any(type(value) is not int or value < 0 for value in sources.values())
        or len(set(sources.values())) != len(sources)
    ):
        raise ValueError("v2 descriptor source/target set mismatch")
    floor = max(targets) + 1
    occupied = set(targets) | set(sources.values())
    actions: list[FdAction] = []
    high: dict[int, int] = {}
    next_fd = max(floor, max(occupied, default=-1) + 1)
    for target in targets:
        while next_fd in occupied:
            next_fd += 1
        high[target] = next_fd
        occupied.add(next_fd)
        actions.append(
            FdAction("duplicate_high", str(target), sources[target], next_fd)
        )
        next_fd += 1
    actions.extend(
        FdAction("map_fixed", str(target), high[target], target)
        for target in targets
    )
    actions.extend(
        FdAction("close_high", str(target), high[target], -1)
        for target in targets
    )
    return tuple(actions)


@dataclasses.dataclass(frozen=True)
class DescriptorRecordV2:
    fd: str
    role: str
    kind: str
    logical_name: str | None
    relative_path: str
    owner_module: str | None
    mode: str
    size: str | None
    sha256: str | None
    st_dev: str
    st_ino: str
    st_nlink: str

    def __post_init__(self) -> None:
        number = _decimal(self.fd, "descriptor fd")
        _decimal(self.st_dev, "descriptor device")
        _decimal(self.st_ino, "descriptor inode")
        _decimal(self.st_nlink, "descriptor link count")
        if number < 9 or self.kind not in {"REGULAR", "DIRECTORY"}:
            raise ValueError("descriptor identity is invalid")
        if self.kind == "DIRECTORY":
            if (
                number != 10
                or self.role != "PRODUCT_BUNDLE_DIRECTORY"
                or self.mode != "0755"
                or any(
                    value is not None
                    for value in (
                        self.logical_name, self.owner_module,
                        self.size, self.sha256,
                    )
                )
            ):
                raise ValueError("bundle directory descriptor is invalid")
        else:
            if (
                self.mode != "0444"
                or self.logical_name is None
                or self.size is None
                or self.sha256 is None
                or _decimal(self.size, "descriptor size") > 8 * 1024 * 1024
                or not _is_hex64(self.sha256)
                or self.st_nlink != "1"
            ):
                raise ValueError("regular descriptor metadata is invalid")

    def to_mapping(self) -> dict[str, object]:
        return {
            field.name: getattr(self, field.name)
            for field in dataclasses.fields(self)
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "DescriptorRecordV2":
        if set(value) != {field.name for field in dataclasses.fields(cls)}:
            raise ValueError("descriptor record fields are not exact")
        return cls(**dict(value))


@dataclasses.dataclass(frozen=True)
class LaunchContextV2:
    schema: str
    route: str
    nonce: str
    expected_parent_pid: str
    exact_head: str
    runtime_manifest_sha256: str
    runtime_current_digest: str
    product_current_digest: str
    bundle_digest: str
    bundle_projection_hash: str
    direct_receipt_digest: str
    owner_gate_digest: str
    import_manifest_hash: str
    host_authority_digest: str
    writer_capability_hash: str
    control_fd: str
    runtime_manifest_fd: str
    import_manifest_fd: str
    owner_gate_fd: str
    runtime_current_fd: str
    launch_context_fd: str
    product_current_fd: str
    bundle_directory_fd: str
    bundle_manifest_fd: str
    bundle_projection_fd: str
    direct_receipt_fd: str
    host_authority_fd: str
    writer_capability_fd: str
    descriptor_records: tuple[DescriptorRecordV2, ...]
    descriptor_count: str
    descriptor_bytes: str
    launch_context_digest: str

    @classmethod
    def create(
        cls,
        *,
        route: str,
        nonce: str,
        expected_parent_pid: str,
        exact_head: str,
        runtime_manifest_sha256: str,
        runtime_current_digest: str,
        product_current_digest: str,
        bundle_digest: str,
        bundle_projection_hash: str,
        direct_receipt_digest: str,
        owner_gate_digest: str,
        import_manifest_hash: str,
        host_authority_digest: str,
        writer_capability_hash: str,
        descriptor_records: tuple[DescriptorRecordV2, ...],
    ) -> "LaunchContextV2":
        body = {
            "schema": "awa-registration-launch-context/v2",
            "route": route, "nonce": nonce,
            "expected_parent_pid": expected_parent_pid,
            "exact_head": exact_head,
            "runtime_manifest_sha256": runtime_manifest_sha256,
            "runtime_current_digest": runtime_current_digest,
            "product_current_digest": product_current_digest,
            "bundle_digest": bundle_digest,
            "bundle_projection_hash": bundle_projection_hash,
            "direct_receipt_digest": direct_receipt_digest,
            "owner_gate_digest": owner_gate_digest,
            "import_manifest_hash": import_manifest_hash,
            "host_authority_digest": host_authority_digest,
            "writer_capability_hash": writer_capability_hash,
            "control_fd": "3", "runtime_manifest_fd": "4",
            "import_manifest_fd": "5", "owner_gate_fd": "6",
            "runtime_current_fd": "7", "launch_context_fd": "8",
            "product_current_fd": "9", "bundle_directory_fd": "10",
            "bundle_manifest_fd": "11", "bundle_projection_fd": "12",
            "direct_receipt_fd": "13", "host_authority_fd": "14",
            "writer_capability_fd": "15",
            "descriptor_records": [
                record.to_mapping() for record in descriptor_records
            ],
            "descriptor_count": str(len(descriptor_records)),
            "descriptor_bytes": str(sum(
                int(record.size or "0") for record in descriptor_records
            )),
        }
        result = cls(
            **{**body, "descriptor_records": descriptor_records},
            launch_context_digest=authority_digest(
                "awa-registration-launch-context/v2", body
            ),
        )
        result._validate()
        return result

    def _validate(self) -> None:
        if (
            self.schema != "awa-registration-launch-context/v2"
            or self.route not in {"ADMISSION", "RECEIVER", "STARTUP", "TICK"}
            or not _is_hex64(self.nonce)
            or re.fullmatch(r"[0-9a-f]{40}", self.exact_head) is None
        ):
            raise ValueError("launch context identity is invalid")
        for name in (
            "runtime_manifest_sha256", "runtime_current_digest",
            "product_current_digest", "bundle_digest",
            "bundle_projection_hash", "direct_receipt_digest",
            "owner_gate_digest", "import_manifest_hash",
            "host_authority_digest", "writer_capability_hash",
        ):
            if not _is_hex64(getattr(self, name)):
                raise ValueError("launch context digest is invalid")
        fds = [int(record.fd) for record in self.descriptor_records]
        if (
            fds != list(range(9, 9 + len(fds)))
            or len(fds) > 512
            or self.descriptor_count != str(len(fds))
            or int(self.descriptor_bytes) > 64 * 1024 * 1024
        ):
            raise ValueError("launch descriptor closure is invalid")
        body = self.to_mapping()
        claim = body.pop("launch_context_digest")
        if claim != authority_digest("awa-registration-launch-context/v2", body):
            raise ValueError("launch context digest mismatch")

    def to_mapping(self) -> dict[str, object]:
        result = {
            field.name: getattr(self, field.name)
            for field in dataclasses.fields(self)
        }
        result["descriptor_records"] = [
            record.to_mapping() for record in self.descriptor_records
        ]
        return result

    def to_bytes(self) -> bytes:
        return canonical_lf_bytes(self.to_mapping())

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "LaunchContextV2":
        if set(value) != {field.name for field in dataclasses.fields(cls)}:
            raise ValueError("launch context fields are not exact")
        converted = dict(value)
        records = converted["descriptor_records"]
        if not isinstance(records, list):
            raise ValueError("descriptor records are invalid")
        converted["descriptor_records"] = tuple(
            DescriptorRecordV2.from_mapping(item) for item in records
        )
        result = cls(**converted)
        result._validate()
        return result

    @classmethod
    def from_bytes(cls, raw: bytes) -> "LaunchContextV2":
        value = json.loads(raw)
        result = cls.from_mapping(value)
        if result.to_bytes() != raw:
            raise ValueError("launch context framing mismatch")
        return result


def apply_fd_remap(sources: Mapping[str, int]) -> tuple[int, ...]:
    """Apply the collision-free plan in the current pre-exec process."""

    actions = plan_fd_remap(sources)
    opened: list[int] = []
    try:
        high: dict[str, int] = {}
        for action in actions:
            if action.operation != "duplicate_high":
                continue
            duplicated = fcntl.fcntl(
                action.source, fcntl.F_DUPFD_CLOEXEC, MINIMUM_REMAP_FD
            )
            if duplicated < MINIMUM_REMAP_FD:
                raise ProtocolRefusal("high descriptor duplication failed")
            high[action.role] = duplicated
            opened.append(duplicated)
        if len(set(high.values())) != len(FD_ASSIGNMENTS):
            raise ProtocolRefusal("high descriptor collision")
        for role, target in FD_ASSIGNMENTS.items():
            os.dup2(high[role], target, inheritable=True)
        return tuple(high.values())
    except BaseException:
        for descriptor in reversed(opened):
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise


@dataclasses.dataclass(frozen=True)
class ChildSpawnPlan:
    argv: tuple[str, ...]
    environment: dict[str, str]
    fixed_fds: frozenset[int]


def build_child_spawn_plan(
    *,
    private_python: str,
    route: str,
    parent_pid: int,
    nonce: str,
) -> ChildSpawnPlan:
    if route not in ROUTES:
        raise ValueError("route token refused")
    if not os.path.isabs(private_python):
        raise ValueError("private Python path must be absolute")
    if type(parent_pid) is not int or parent_pid <= 0:
        raise ValueError("parent PID must be positive")
    if not _is_hex64(nonce):
        raise ValueError("spawn nonce must be lowercase 64-hex")
    argv = (
        private_python,
        "-I",
        "-S",
        "-B",
        str(CHILD_PATH),
        "--route",
        route,
        "--expected-parent-pid",
        str(parent_pid),
        "--nonce",
        nonce,
    )
    environment = {
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
        "AWA_REGISTRATION_SPAWN_NONCE": nonce,
    }
    return ChildSpawnPlan(
        argv=argv,
        environment=environment,
        fixed_fds=frozenset(FD_ASSIGNMENTS.values()),
    )


class ParentBarrier:
    """Pure model of the nonce-bound READY/GO/IMPORT_READY protocol."""

    def __init__(self) -> None:
        self._events: list[str] = []
        self._aborted = False

    @property
    def events(self) -> tuple[str, ...]:
        return tuple(self._events)

    @property
    def complete(self) -> bool:
        return self._events == [
            "READY",
            "PARENT_REVERIFIED",
            "GO",
            "IMPORT_READY",
            "PRODUCT",
            "TERMINAL",
        ]

    @property
    def refused(self) -> bool:
        return self._aborted

    def _need(self, expected: list[str]) -> None:
        if self._aborted or self._events != expected:
            raise ProtocolRefusal("barrier order refused")

    def child_ready(self) -> None:
        self._need([])
        self._events.append("READY")

    def parent_reverify(self) -> None:
        self._need(["READY"])
        self._events.append("PARENT_REVERIFIED")

    def parent_send_go(self) -> None:
        self._need(["READY", "PARENT_REVERIFIED"])
        self._events.append("GO")

    def child_import_ready(self) -> None:
        self._need(["READY", "PARENT_REVERIFIED", "GO"])
        self._events.append("IMPORT_READY")

    def child_product_imported(self) -> None:
        self._need(["READY", "PARENT_REVERIFIED", "GO", "IMPORT_READY"])
        self._events.append("PRODUCT")

    def child_done(self) -> None:
        self._need(
            [
                "READY",
                "PARENT_REVERIFIED",
                "GO",
                "IMPORT_READY",
                "PRODUCT",
            ]
        )
        self._events.append("TERMINAL")

    def child_abort(self, event: str) -> None:
        if event not in {"WATCHDOG_TIMEOUT", "PARENT_DEAD", "CHANNEL_EOF"}:
            raise ProtocolRefusal("unknown child abort")
        if self._aborted or "PRODUCT" in self._events:
            raise ProtocolRefusal("abort is not a pre-product transition")
        self._events.append(event)
        self._aborted = True


@dataclasses.dataclass(frozen=True)
class VnodeIdentity:
    device: int
    inode: int
    mode: int
    uid: int
    gid: int
    link_count: int
    size: int


def verify_mapped_vnode(expected: VnodeIdentity, observed: VnodeIdentity) -> None:
    if expected != observed:
        raise MeasurementRefusal("mapped vnode identity drift")
    if (
        not stat.S_ISREG(observed.mode)
        or observed.uid != 0
        or observed.gid != 0
        or observed.link_count != 1
    ):
        raise MeasurementRefusal("mapped vnode metadata refused")


@dataclasses.dataclass(frozen=True)
class FileExpectation:
    sha256: str
    mode: int
    size: int
    device: int
    inode: int
    uid: int
    gid: int
    link_count: int

    @classmethod
    def from_path(cls, path: Path) -> "FileExpectation":
        metadata = path.lstat()
        return cls(
            hashlib.sha256(path.read_bytes()).hexdigest(),
            stat.S_IMODE(metadata.st_mode),
            metadata.st_size,
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_uid,
            metadata.st_gid,
            metadata.st_nlink,
        )


def verify_common_measurement(
    root: Path, expected: Mapping[str, FileExpectation]
) -> None:
    if set(expected) != set(COMMON_MEASUREMENT_FILES):
        raise MeasurementRefusal("measurement file set mismatch")
    for relative in COMMON_MEASUREMENT_FILES:
        path = root / relative
        if path.is_symlink():
            raise MeasurementRefusal("measurement symlink refused")
        metadata = path.lstat()
        wanted = expected[relative]
        observed = FileExpectation.from_path(path)
        if observed != wanted:
            raise MeasurementRefusal(f"measurement drift: {relative}")
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) not in {0o444, 0o555}
        ):
            raise MeasurementRefusal(f"measurement metadata refused: {relative}")


@dataclasses.dataclass
class RetainedFile:
    path: Path
    descriptor: int
    raw: bytes
    identity: tuple[int, ...]
    expected_uid: int
    expected_gid: int
    expected_mode: int

    @classmethod
    def open(
        cls,
        path: Path,
        *,
        expected_uid: int,
        expected_gid: int,
        expected_mode: int,
        limit: int,
    ) -> "RetainedFile":
        before = path.lstat()
        if (
            path.is_symlink()
            or not stat.S_ISREG(before.st_mode)
            or before.st_uid != expected_uid
            or before.st_gid != expected_gid
            or stat.S_IMODE(before.st_mode) != expected_mode
            or before.st_nlink != 1
            or not 1 <= before.st_size <= limit
        ):
            raise MeasurementRefusal(f"unsafe installed file: {path}")
        descriptor = os.open(
            path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            opened = os.fstat(descriptor)
            identity = (
                opened.st_dev,
                opened.st_ino,
                opened.st_mode,
                opened.st_uid,
                opened.st_gid,
                opened.st_nlink,
                opened.st_size,
                opened.st_mtime_ns,
            )
            if identity != (
                before.st_dev,
                before.st_ino,
                before.st_mode,
                before.st_uid,
                before.st_gid,
                before.st_nlink,
                before.st_size,
                before.st_mtime_ns,
            ):
                raise MeasurementRefusal("installed file open/rebind drift")
            chunks: list[bytes] = []
            remaining = opened.st_size
            while remaining:
                chunk = os.read(descriptor, min(remaining, 65_536))
                if not chunk:
                    raise MeasurementRefusal("installed file truncated")
                chunks.append(chunk)
                remaining -= len(chunk)
            retained = cls(
                path,
                descriptor,
                b"".join(chunks),
                identity,
                expected_uid,
                expected_gid,
                expected_mode,
            )
            retained.reverify()
            os.lseek(descriptor, 0, os.SEEK_SET)
            return retained
        except BaseException:
            os.close(descriptor)
            raise

    def reverify(self) -> None:
        opened = os.fstat(self.descriptor)
        visible = self.path.lstat()
        opened_identity = (
            opened.st_dev,
            opened.st_ino,
            opened.st_mode,
            opened.st_uid,
            opened.st_gid,
            opened.st_nlink,
            opened.st_size,
            opened.st_mtime_ns,
        )
        visible_identity = (
            visible.st_dev,
            visible.st_ino,
            visible.st_mode,
            visible.st_uid,
            visible.st_gid,
            visible.st_nlink,
            visible.st_size,
            visible.st_mtime_ns,
        )
        if (
            opened_identity != self.identity
            or visible_identity != self.identity
            or self.path.is_symlink()
        ):
            raise MeasurementRefusal(f"retained file drifted: {self.path}")

    def close(self) -> None:
        os.close(self.descriptor)


def verify_root_owned_ancestry(path: Path) -> None:
    current = path.parent
    while True:
        metadata = current.lstat()
        if (
            current.is_symlink()
            or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != 0
            or metadata.st_gid != 0
            or metadata.st_mode & 0o022
        ):
            raise MeasurementRefusal(
                f"installed ancestor metadata refused: {current}"
            )
        if current.parent == current:
            return
        current = current.parent


def _relative_manifest_path(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value.startswith("/")
        or "\\" in value
        or "\0" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
        or os.path.normpath(value) != value
    ):
        raise MeasurementRefusal("manifest path refused")
    return value


def _validate_hex_fields(value: Mapping[str, object], fields: Iterable[str]) -> None:
    for field in fields:
        if not _is_hex64(value.get(field)):
            raise MeasurementRefusal(f"{field} is not lowercase 64-hex")


def _runtime_manifest_digest(value: Mapping[str, object]) -> str:
    return hashlib.sha256(
        b"awa-private-runtime-manifest/v1\0"
        + canonical_bytes(dict(value))
    ).hexdigest()


def _import_manifest_digest(raw: bytes) -> str:
    return hashlib.sha256(
        b"awa-registration-import-manifest/v1\0" + raw[:-1]
    ).hexdigest()


def _verify_payload_records(
    root: Path,
    manifest: Mapping[str, object],
    *,
    expected_uid: int = 0,
    expected_gid: int = 0,
) -> dict[str, FileExpectation]:
    if (
        set(manifest) != RUNTIME_MANIFEST_FIELDS
        or manifest.get("schema") != "awa-private-runtime-manifest/v1"
        or not isinstance(manifest.get("records"), list)
    ):
        raise MeasurementRefusal("runtime manifest schema refused")
    expected: dict[str, FileExpectation] = {}
    prior: bytes | None = None
    framing = bytearray()
    for record in manifest["records"]:
        if not isinstance(record, dict) or set(record) != RUNTIME_RECORD_FIELDS:
            raise MeasurementRefusal("runtime manifest record refused")
        relative = _relative_manifest_path(record["path"])
        encoded = relative.encode("utf-8")
        if prior is not None and encoded <= prior:
            raise MeasurementRefusal("runtime manifest records unsorted")
        prior = encoded
        mode = record["mode"]
        size = record["size"]
        digest = record["sha256"]
        if (
            mode not in {"444", "555"}
            or not isinstance(size, str)
            or UINT.fullmatch(size) is None
            or not _is_hex64(digest)
            or type(record["macho"]) is not bool
        ):
            raise MeasurementRefusal("runtime manifest metadata refused")
        path = root / relative
        parent = path.parent
        while parent != root.parent:
            parent_metadata = parent.lstat()
            if (
                parent.is_symlink()
                or not stat.S_ISDIR(parent_metadata.st_mode)
                or parent_metadata.st_uid != expected_uid
                or parent_metadata.st_gid != expected_gid
                or stat.S_IMODE(parent_metadata.st_mode) != 0o755
            ):
                raise MeasurementRefusal("runtime payload ancestor refused")
            if parent == root:
                break
            parent = parent.parent
        retained = RetainedFile.open(
            path,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
            expected_mode=int(mode, 8),
            limit=1 << 30,
        )
        try:
            if (
                len(retained.raw) != int(size)
                or hashlib.sha256(retained.raw).hexdigest() != digest
            ):
                raise MeasurementRefusal("runtime payload hash drift")
            opened = os.fstat(retained.descriptor)
            expected[relative] = FileExpectation(
                digest,
                int(mode, 8),
                int(size),
                opened.st_dev,
                opened.st_ino,
                opened.st_uid,
                opened.st_gid,
                opened.st_nlink,
            )
        finally:
            retained.close()
        framing.extend(encoded)
        framing.extend(b"\0" + mode.encode("ascii"))
        framing.extend(b"\0" + size.encode("ascii"))
        framing.extend(b"\0" + digest.encode("ascii"))
        framing.extend(b"\0" + (b"1" if record["macho"] else b"0") + b"\n")
    if (
        manifest.get("record_framing_digest")
        != hashlib.sha256(framing).hexdigest()
    ):
        raise MeasurementRefusal("runtime manifest framing digest refused")
    return expected


def verify_owner_signature(
    message: bytes,
    signature: bytes,
    *,
    namespace: str,
) -> None:
    if namespace not in {
        "awa-private-runtime-release-envelope-v1",
        "awa-registration-owner-gate-v3",
    }:
        raise MeasurementRefusal("owner signature namespace refused")
    if (
        not message.endswith(b"\n")
        or not 1 <= len(signature) <= 1_048_576
        or b"BEGIN SSH SIGNATURE" not in signature
    ):
        raise MeasurementRefusal("owner signature framing refused")
    with tempfile.TemporaryDirectory(prefix="awa-owner-verify.") as raw:
        root = Path(raw)
        signers = root / "allowed-signers"
        detached = root / "authority.sig"
        signers.write_bytes(OWNER_SIGNERS_V2)
        detached.write_bytes(signature)
        signers.chmod(0o600)
        detached.chmod(0o600)
        result = subprocess.run(
            [
                SSH_KEYGEN,
                "-Y",
                "verify",
                "-f",
                str(signers),
                "-I",
                OWNER_PRINCIPAL,
                "-n",
                namespace,
                "-s",
                str(detached),
            ],
            input=message,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"},
            check=False,
            timeout=10,
        )
    if result.returncode != 0:
        raise MeasurementRefusal("owner signature verification failed")


def _validate_current(raw: bytes) -> dict:
    value = parse_canonical_lf(raw, maximum=65_536)
    if (
        not isinstance(value, dict)
        or set(value) != CURRENT_FIELDS
        or value.get("schema") != "awa-private-runtime-current/v1"
    ):
        raise MeasurementRefusal("current authority schema refused")
    body = dict(value)
    claimed = body.pop("current_digest", None)
    if claimed != authority_digest("awa-private-runtime-current/v1", body):
        raise MeasurementRefusal("current authority digest refused")
    if (
        not isinstance(value["epoch"], str)
        or UINT.fullmatch(value["epoch"]) is None
        or int(value["epoch"]) < 1
    ):
        raise MeasurementRefusal("current epoch refused")
    _validate_hex_fields(
        value,
        (
            "active_manifest_sha256",
            "active_release_envelope_digest",
            "installer_audit_digest",
            "predecessor_current_digest",
            "current_digest",
        ),
    )
    previous = value["previous_manifest_sha256"]
    if previous is not None and not _is_hex64(previous):
        raise MeasurementRefusal("current previous manifest refused")
    return value


def _validate_release(raw: bytes, current: Mapping[str, object]) -> dict:
    value = parse_canonical_lf(raw, maximum=1_048_576)
    if (
        not isinstance(value, dict)
        or set(value) != RELEASE_FIELDS
        or value.get("schema") != "awa-private-runtime-release-envelope/v1"
        or value.get("repository") != "KleinPerkins/awa"
    ):
        raise MeasurementRefusal("release envelope schema refused")
    body = dict(value)
    claimed = body.pop("release_envelope_digest", None)
    if claimed != authority_digest(
        "awa-private-runtime-release-envelope/v1", body
    ):
        raise MeasurementRefusal("release envelope digest refused")
    if claimed != current["active_release_envelope_digest"]:
        raise MeasurementRefusal("current/release envelope mismatch")
    return value


def _validate_owner_gate(
    raw: bytes,
    *,
    current: Mapping[str, object],
    runtime_manifest_digest: str,
    import_manifest_digest: str,
) -> dict:
    value = parse_canonical_lf(raw, maximum=1_048_576)
    if (
        not isinstance(value, dict)
        or set(value) != OWNER_GATE_FIELDS
        or value.get("schema") != "awa-registration-owner-gate/v3"
        or value.get("repository") != "KleinPerkins/awa"
        or value.get("authorized_by") != "KleinPerkins"
        or value.get("authorized") is not True
        or value.get("runtime_manifest_sha256") != runtime_manifest_digest
        or value.get("import_manifest_hash") != import_manifest_digest
        or value.get("runtime_release_envelope_digest")
        != current["active_release_envelope_digest"]
    ):
        raise MeasurementRefusal("owner gate authority refused")
    return value


def _verify_import_manifest(
    raw: bytes,
    *,
    payload: Mapping[str, FileExpectation],
) -> dict:
    value = parse_canonical_lf(raw, maximum=8 * 1024 * 1024)
    if (
        not isinstance(value, dict)
        or set(value) != IMPORT_MANIFEST_FIELDS
        or value.get("schema") != "awa-registration-import-manifest/v1"
        or not isinstance(value.get("entry_modules"), list)
        or not isinstance(value.get("records"), list)
    ):
        raise MeasurementRefusal("AWA import manifest schema refused")
    prior: bytes | None = None
    for record in value["records"]:
        if not isinstance(record, dict) or set(record) != IMPORT_RECORD_FIELDS:
            raise MeasurementRefusal("AWA import manifest record refused")
        relative = _relative_manifest_path(record["path"])
        encoded = canonical_bytes(record)
        if prior is not None and encoded <= prior:
            raise MeasurementRefusal("AWA import records unsorted")
        prior = encoded
        expected = payload.get(relative)
        if (
            expected is None
            or record.get("role") not in {"PACKAGE_INITIALIZER", "MODULE"}
            or record.get("mode") != str(expected.mode)
            or record.get("size") != str(expected.size)
            or record.get("sha256") != expected.sha256
        ):
            raise MeasurementRefusal("AWA import record/payload mismatch")
    return value


@contextlib.contextmanager
def load_installed_launch_authority(
    *,
    route: str,
    nonce: str,
    install_root: Path = INSTALL_ROOT,
    expected_uid: int = 0,
    expected_gid: int = 0,
) -> Iterable[RetainedLaunchAuthority]:
    """Open, validate, lock, and retain one immutable installed generation."""

    if route not in ROUTES or not _is_hex64(nonce):
        raise ProtocolRefusal("installed launch request refused")
    current_path = install_root / "runtime/current.v1"
    if expected_uid == 0 and expected_gid == 0:
        verify_root_owned_ancestry(current_path)
    with contextlib.ExitStack() as stack:
        current_file = RetainedFile.open(
            current_path,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
            expected_mode=0o444,
            limit=65_536,
        )
        stack.callback(current_file.close)
        current = _validate_current(current_file.raw)
        manifest_digest = str(current["active_manifest_sha256"])
        version_root = install_root / "runtime/versions" / manifest_digest
        prefix = f"awa-private-runtime-{manifest_digest}"
        paths = {
            "runtime_manifest": version_root / f"{prefix}.manifest.json",
            "release": version_root / f"{prefix}.release-envelope.json",
            "release_signature": version_root
            / f"{prefix}.release-envelope.sig",
            "awa_import_manifest": version_root
            / "awa-registration-import-manifest-v1.json",
            "owner_gate": version_root
            / "awa-registration-owner-gate-v3.json",
            "owner_gate_signature": version_root
            / "awa-registration-owner-gate-v3.sig",
            "private_python": version_root
            / "Python.app/Contents/MacOS/Python",
            "version_lock": install_root
            / "runtime/locks"
            / f"{manifest_digest}.lock",
        }
        retained: dict[str, RetainedFile] = {}
        for role, path in paths.items():
            if expected_uid == 0 and expected_gid == 0:
                verify_root_owned_ancestry(path)
            mode = 0o555 if role == "private_python" else 0o444
            limit = (
                1 << 30
                if role in {"private_python", "runtime_manifest"}
                else 8 * 1024 * 1024
            )
            retained[role] = RetainedFile.open(
                path,
                expected_uid=expected_uid,
                expected_gid=expected_gid,
                expected_mode=mode,
                limit=limit,
            )
            stack.callback(retained[role].close)
        fcntl.flock(
            retained["version_lock"].descriptor,
            fcntl.LOCK_SH | fcntl.LOCK_NB,
        )
        stack.callback(
            fcntl.flock,
            retained["version_lock"].descriptor,
            fcntl.LOCK_UN,
        )
        runtime_value = parse_canonical_lf(
            retained["runtime_manifest"].raw,
            maximum=1 << 30,
        )
        if not isinstance(runtime_value, dict):
            raise MeasurementRefusal("runtime manifest is not an object")
        if _runtime_manifest_digest(runtime_value) != manifest_digest:
            raise MeasurementRefusal("active runtime manifest mismatch")
        payload = _verify_payload_records(version_root, runtime_value)
        _verify_import_manifest(
            retained["awa_import_manifest"].raw,
            payload=payload,
        )
        import_digest = _import_manifest_digest(
            retained["awa_import_manifest"].raw
        )
        release = _validate_release(retained["release"].raw, current)
        if release["runtime_manifest_sha256"] != manifest_digest:
            raise MeasurementRefusal("release/runtime manifest mismatch")
        verify_owner_signature(
            retained["release"].raw,
            retained["release_signature"].raw,
            namespace="awa-private-runtime-release-envelope-v1",
        )
        gate = _validate_owner_gate(
            retained["owner_gate"].raw,
            current=current,
            runtime_manifest_digest=manifest_digest,
            import_manifest_digest=import_digest,
        )
        verify_owner_signature(
            retained["owner_gate"].raw,
            retained["owner_gate_signature"].raw,
            namespace="awa-registration-owner-gate-v3",
        )
        executable_digest = hashlib.sha256(
            retained["private_python"].raw
        ).hexdigest()
        executable_record = payload.get(
            "Python.app/Contents/MacOS/Python"
        )
        if (
            executable_record is None
            or executable_record.sha256 != executable_digest
        ):
            raise MeasurementRefusal("private executable manifest mismatch")
        lock_metadata = os.fstat(retained["version_lock"].descriptor)
        lock_identity = hashlib.sha256(
            b"awa-registration-version-lock/v1\0"
            + str(lock_metadata.st_dev).encode("ascii")
            + b"\0"
            + str(lock_metadata.st_ino).encode("ascii")
            + b"\0"
            + str(lock_metadata.st_mode).encode("ascii")
            + b"\0"
            + manifest_digest.encode("ascii")
        ).hexdigest()
        gate_digest = hashlib.sha256(
            b"awa-registration-owner-gate/v3\0"
            + retained["owner_gate"].raw[:-1]
        ).hexdigest()
        launch_body = {
            "schema": "awa-registration-launch/v1",
            "nonce": nonce,
            "route": route,
            "current_digest": current["current_digest"],
            "runtime_manifest_sha256": manifest_digest,
            "runtime_release_envelope_digest": current[
                "active_release_envelope_digest"
            ],
            "owner_gate_digest": gate_digest,
            "import_manifest_hash": import_digest,
            "private_executable_sha256": executable_digest,
            "version_lock_identity": lock_identity,
        }
        launch = dict(launch_body)
        launch["launch_digest"] = authority_digest(
            "awa-registration-launch/v1", launch_body
        )
        launch_path: Path | None = None
        descriptor: int | None = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix="awa-registration-launch.",
                suffix=".json",
                delete=False,
            ) as handle:
                launch_path = Path(handle.name)
                handle.write(canonical_lf_bytes(launch))
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(launch_path, 0o600)
            launch_file = RetainedFile.open(
                launch_path,
                expected_uid=os.getuid(),
                expected_gid=os.getgid(),
                expected_mode=0o600,
                limit=65_536,
            )
            descriptor = launch_file.descriptor

            def reverify() -> None:
                current_file.reverify()
                for file in retained.values():
                    file.reverify()
                launch_file.reverify()
                if _validate_current(current_file.raw) != current:
                    raise MeasurementRefusal("current bytes changed")

            executable_stat = os.fstat(
                retained["private_python"].descriptor
            )
            authority = RetainedLaunchAuthority(
                private_python=str(paths["private_python"]),
                private_executable_sha256=executable_digest,
                runtime_manifest_sha256=manifest_digest,
                version_lock_identity=lock_identity,
                authority_fds={
                    "runtime_manifest": retained[
                        "runtime_manifest"
                    ].descriptor,
                    "awa_import_manifest": retained[
                        "awa_import_manifest"
                    ].descriptor,
                    "signed_authority": retained["owner_gate"].descriptor,
                    "current": current_file.descriptor,
                    "launch": descriptor,
                },
                executable_vnode=VnodeIdentity(
                    executable_stat.st_dev,
                    executable_stat.st_ino,
                    executable_stat.st_mode,
                    executable_stat.st_uid,
                    executable_stat.st_gid,
                    executable_stat.st_nlink,
                    executable_stat.st_size,
                ),
                reverify=reverify,
            )
            authority.validate()
            yield authority
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if launch_path is not None:
                try:
                    launch_path.unlink()
                except FileNotFoundError:
                    pass


def measure_private_runtime(root: Path, manifest_path: Path) -> dict:
    """Canonical common build/launch capability measurement."""

    if (
        not root.is_absolute()
        or root.is_symlink()
        or not root.is_dir()
        or not manifest_path.is_absolute()
        or manifest_path.is_symlink()
        or not manifest_path.is_file()
    ):
        raise MeasurementRefusal("measurement paths refused")
    executable = root / "Python.app/Contents/MacOS/Python"
    if Path(sys.executable) != executable:
        raise MeasurementRefusal("measurement interpreter mismatch")
    manifest_raw = manifest_path.read_bytes()
    manifest = parse_canonical_lf(manifest_raw, maximum=64 * 1024 * 1024)
    if not isinstance(manifest, dict):
        raise MeasurementRefusal("measurement manifest refused")
    payload = _verify_payload_records(
        root,
        manifest,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )
    expected = payload.get("Python.app/Contents/MacOS/Python")
    if expected is None:
        raise MeasurementRefusal("measurement executable is unmanifested")
    raw = executable.read_bytes()
    if (
        hashlib.sha256(raw).hexdigest() != expected.sha256
        or len(raw) != expected.size
    ):
        raise MeasurementRefusal("measurement executable drift")
    namespace: dict[str, object] = {}
    exec(
        compile(
            CAPABILITY_PROBE_SOURCE,
            "<awa-private-runtime-capability-probe>",
            "exec",
        ),
        namespace,
    )
    probe = namespace.get("probe_result")
    if not isinstance(probe, dict):
        raise MeasurementRefusal("capability probe emitted no result")
    options = probe.pop("compile_options", None)
    if (
        not isinstance(options, list)
        or options != sorted(set(options), key=lambda value: value.encode())
        or "ENABLE_FTS5" not in options
        or options.count("THREADSAFE=1") != 1
        or any(
            value.startswith("THREADSAFE=") and value != "THREADSAFE=1"
            for value in options
        )
    ):
        raise MeasurementRefusal("SQLite compile options refused")
    compile_options = {
        "schema": "awa-registration-sqlite-compile-options/v1",
        "options": options,
    }
    compile_digest = authority_digest(
        "awa-registration-sqlite-compile-options/v1", compile_options
    )
    capability = {
        "schema": "awa-registration-python-capability/v1",
        **probe,
        "required_python_apis": list(REQUIRED_PYTHON_APIS),
        "sqlite_compile_options_hash": compile_digest,
        "probe_program_hash": hashlib.sha256(
            CAPABILITY_PROBE_SOURCE.encode("utf-8")
        ).hexdigest(),
    }
    if (
        set(capability)
        != {
            "schema",
            "platform",
            "os_build",
            "python_implementation",
            "python_version",
            "required_python_apis",
            "sqlite_runtime_version",
            "sqlite_source_id",
            "sqlite_compile_options_hash",
            "sqlite_vfs_name",
            "journal_mode",
            "synchronous",
            "fullfsync",
            "checkpoint_fullfsync",
            "foreign_keys",
            "connection_setconfig_available",
            "sqlite_dbconfig_defensive_available",
            "defensive",
            "trusted_schema",
            "locking_mode",
            "nofollow_available",
            "checkpoint_on_close",
            "probe_program_hash",
        }
        or capability["platform"] != "darwin"
        or capability["python_implementation"] != "CPython"
        or capability["python_version"] != "3.14.8"
        or capability["sqlite_runtime_version"] != "3.53.1"
    ):
        raise MeasurementRefusal("private runtime exact capability refused")
    capability_digest = authority_digest(
        "awa-registration-python-capability/v1", capability
    )
    libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
    libc._dyld_image_count.restype = ctypes.c_uint32
    libc._dyld_get_image_name.argtypes = [ctypes.c_uint32]
    libc._dyld_get_image_name.restype = ctypes.c_char_p
    images = []
    escapes = []
    allowed = (
        str(root) + "/",
        "/System/Library/",
        "/usr/lib/",
    )
    for index in range(int(libc._dyld_image_count())):
        raw_name = libc._dyld_get_image_name(index)
        if raw_name is None:
            raise MeasurementRefusal("loaded image name unavailable")
        name = os.path.realpath(raw_name.decode("utf-8", "strict"))
        images.append(name)
        if not any(name.startswith(prefix) for prefix in allowed):
            escapes.append(name)
    images = sorted(set(images), key=lambda value: value.encode())
    escapes = sorted(set(escapes), key=lambda value: value.encode())
    if escapes:
        raise MeasurementRefusal("private runtime dependency escape")
    metadata = executable.stat()
    return {
        "schema": "awa-registration-private-runtime-measurement/v1",
        "runtime_manifest_sha256": _runtime_manifest_digest(manifest),
        "private_executable_path": str(executable),
        "private_executable_sha256": expected.sha256,
        "private_executable_dev": str(metadata.st_dev),
        "private_executable_ino": str(metadata.st_ino),
        "capability": capability,
        "capability_digest": capability_digest,
        "compile_options": compile_options,
        "compile_options_digest": compile_digest,
        "loaded_images": images,
        "dependency_escapes": escapes,
    }


def pidversion(
    pid: int, start_seconds: int, start_microseconds: int, boot_identity: str
) -> str:
    for name, value in (
        ("pid", pid),
        ("start_seconds", start_seconds),
        ("start_microseconds", start_microseconds),
    ):
        if type(value) is not int or value < 0:
            raise ValueError(f"{name} must be unsigned")
    preimage = (
        b"awa-darwin-pidversion/v1\0"
        + str(pid).encode("ascii")
        + b"\0"
        + str(start_seconds).encode("ascii")
        + b"\0"
        + str(start_microseconds).encode("ascii")
        + b"\0"
        + boot_identity.encode("ascii")
    )
    return hashlib.sha256(preimage).hexdigest()


def boot_identity(seconds: int, microseconds: int) -> str:
    if (
        type(seconds) is not int
        or type(microseconds) is not int
        or seconds < 0
        or microseconds < 0
    ):
        raise ValueError("boot time must be unsigned")
    return hashlib.sha256(
        b"awa-darwin-boot-identity/v1\0"
        + str(seconds).encode("ascii")
        + b"\0"
        + str(microseconds).encode("ascii")
    ).hexdigest()


class _ProcBsdInfo(ctypes.Structure):
    _fields_ = [
        ("pbi_flags", ctypes.c_uint32),
        ("pbi_status", ctypes.c_uint32),
        ("pbi_xstatus", ctypes.c_uint32),
        ("pbi_pid", ctypes.c_uint32),
        ("pbi_ppid", ctypes.c_uint32),
        ("pbi_uid", ctypes.c_uint32),
        ("pbi_gid", ctypes.c_uint32),
        ("pbi_ruid", ctypes.c_uint32),
        ("pbi_rgid", ctypes.c_uint32),
        ("pbi_svuid", ctypes.c_uint32),
        ("pbi_svgid", ctypes.c_uint32),
        ("rfu_1", ctypes.c_uint32),
        ("pbi_comm", ctypes.c_char * 16),
        ("pbi_name", ctypes.c_char * 32),
        ("pbi_nfiles", ctypes.c_uint32),
        ("pbi_pgid", ctypes.c_uint32),
        ("pbi_pjobc", ctypes.c_uint32),
        ("e_tdev", ctypes.c_uint32),
        ("e_tpgid", ctypes.c_uint32),
        ("pbi_nice", ctypes.c_int32),
        ("pbi_start_tvsec", ctypes.c_uint64),
        ("pbi_start_tvusec", ctypes.c_uint64),
    ]


class _ProcRegionInfo(ctypes.Structure):
    _fields_ = [
        ("pri_protection", ctypes.c_uint32),
        ("pri_max_protection", ctypes.c_uint32),
        ("pri_inheritance", ctypes.c_uint32),
        ("pri_flags", ctypes.c_uint32),
        ("pri_offset", ctypes.c_uint64),
        ("pri_behavior", ctypes.c_uint32),
        ("pri_user_wired_count", ctypes.c_uint32),
        ("pri_user_tag", ctypes.c_uint32),
        ("pri_pages_resident", ctypes.c_uint32),
        ("pri_pages_shared_now_private", ctypes.c_uint32),
        ("pri_pages_swapped_out", ctypes.c_uint32),
        ("pri_pages_dirtied", ctypes.c_uint32),
        ("pri_ref_count", ctypes.c_uint32),
        ("pri_shadow_depth", ctypes.c_uint32),
        ("pri_share_mode", ctypes.c_uint32),
        ("pri_private_pages_resident", ctypes.c_uint32),
        ("pri_shared_pages_resident", ctypes.c_uint32),
        ("pri_obj_id", ctypes.c_uint32),
        ("pri_depth", ctypes.c_uint32),
        ("pri_address", ctypes.c_uint64),
        ("pri_size", ctypes.c_uint64),
    ]


class _VinfoStat(ctypes.Structure):
    _fields_ = [
        ("vst_dev", ctypes.c_uint32),
        ("vst_mode", ctypes.c_uint16),
        ("vst_nlink", ctypes.c_uint16),
        ("vst_ino", ctypes.c_uint64),
        ("vst_uid", ctypes.c_uint32),
        ("vst_gid", ctypes.c_uint32),
        ("vst_atime", ctypes.c_int64),
        ("vst_atimensec", ctypes.c_int64),
        ("vst_mtime", ctypes.c_int64),
        ("vst_mtimensec", ctypes.c_int64),
        ("vst_ctime", ctypes.c_int64),
        ("vst_ctimensec", ctypes.c_int64),
        ("vst_birthtime", ctypes.c_int64),
        ("vst_birthtimensec", ctypes.c_int64),
        ("vst_size", ctypes.c_int64),
        ("vst_blocks", ctypes.c_int64),
        ("vst_blksize", ctypes.c_int32),
        ("vst_flags", ctypes.c_uint32),
        ("vst_gen", ctypes.c_uint32),
        ("vst_rdev", ctypes.c_uint32),
        ("vst_qspare", ctypes.c_int64 * 2),
    ]


class _Fsid(ctypes.Structure):
    _fields_ = [("val", ctypes.c_int32 * 2)]


class _VnodeInfo(ctypes.Structure):
    _fields_ = [
        ("vi_stat", _VinfoStat),
        ("vi_type", ctypes.c_int),
        ("vi_pad", ctypes.c_int),
        ("vi_fsid", _Fsid),
    ]


class _VnodeInfoPath(ctypes.Structure):
    _fields_ = [
        ("vip_vi", _VnodeInfo),
        ("vip_path", ctypes.c_char * 1024),
    ]


class _ProcRegionWithPathInfo(ctypes.Structure):
    _fields_ = [
        ("prp_prinfo", _ProcRegionInfo),
        ("prp_vip", _VnodeInfoPath),
    ]


class _Timeval(ctypes.Structure):
    _fields_ = [
        ("tv_sec", ctypes.c_long),
        ("tv_usec", ctypes.c_int),
    ]


def _darwin_libraries() -> tuple[ctypes.CDLL, ctypes.CDLL]:
    if sys.platform != "darwin":
        raise ProtocolRefusal("Darwin process APIs are unavailable")
    libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
    libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
    libproc.proc_pidinfo.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint64,
        ctypes.c_void_p,
        ctypes.c_int,
    ]
    libproc.proc_pidinfo.restype = ctypes.c_int
    libproc.proc_pidpath.argtypes = [
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint32,
    ]
    libproc.proc_pidpath.restype = ctypes.c_int
    libc.sysctlbyname.argtypes = [
        ctypes.c_char_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.c_void_p,
        ctypes.c_size_t,
    ]
    libc.sysctlbyname.restype = ctypes.c_int
    libc.csops.argtypes = [
        ctypes.c_int,
        ctypes.c_uint,
        ctypes.c_void_p,
        ctypes.c_size_t,
    ]
    libc.csops.restype = ctypes.c_int
    return libproc, libc


def native_boot_identity() -> str:
    _, libc = _darwin_libraries()
    value = _Timeval()
    size = ctypes.c_size_t(ctypes.sizeof(value))
    if libc.sysctlbyname(
        b"kern.boottime",
        ctypes.byref(value),
        ctypes.byref(size),
        None,
        0,
    ) != 0 or size.value != ctypes.sizeof(value):
        raise ProtocolRefusal("boot identity unavailable")
    return boot_identity(int(value.tv_sec), int(value.tv_usec))


def native_bsd_info(pid: int) -> _ProcBsdInfo:
    if type(pid) is not int or pid <= 0:
        raise ProtocolRefusal("process PID refused")
    libproc, _ = _darwin_libraries()
    info = _ProcBsdInfo()
    result = libproc.proc_pidinfo(
        pid,
        3,
        0,
        ctypes.byref(info),
        ctypes.sizeof(info),
    )
    if result != ctypes.sizeof(info) or info.pbi_pid != pid:
        raise ProtocolRefusal("process identity unavailable")
    return info


def native_pidversion(pid: int, boot_id: str) -> str | None:
    try:
        first = native_bsd_info(pid)
        second = native_bsd_info(pid)
    except ProtocolRefusal:
        return None
    identity = (
        first.pbi_pid,
        first.pbi_uid,
        first.pbi_start_tvsec,
        first.pbi_start_tvusec,
    )
    if identity != (
        second.pbi_pid,
        second.pbi_uid,
        second.pbi_start_tvsec,
        second.pbi_start_tvusec,
    ):
        return None
    return pidversion(
        pid,
        int(first.pbi_start_tvsec),
        int(first.pbi_start_tvusec),
        boot_id,
    )


def native_process_path(pid: int) -> str:
    libproc, _ = _darwin_libraries()
    buffer = ctypes.create_string_buffer(4096)
    length = libproc.proc_pidpath(pid, buffer, len(buffer))
    if length <= 0 or length >= len(buffer):
        raise ProtocolRefusal("process path unavailable")
    return buffer.value.decode("utf-8", "strict")


def native_mapped_vnode(pid: int, expected_path: str) -> VnodeIdentity:
    if native_process_path(pid) != expected_path:
        raise MeasurementRefusal("spawned executable path mismatch")
    libproc, _ = _darwin_libraries()
    address = 0
    for _ in range(4096):
        info = _ProcRegionWithPathInfo()
        result = libproc.proc_pidinfo(
            pid,
            8,
            address,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if result == 0:
            break
        if result != ctypes.sizeof(info):
            raise MeasurementRefusal("mapped vnode observation truncated")
        region = info.prp_prinfo
        if region.pri_size <= 0 or region.pri_address < address:
            raise MeasurementRefusal("mapped region sequence refused")
        raw_path = bytes(info.prp_vip.vip_path).split(b"\0", 1)[0]
        if raw_path:
            try:
                path = raw_path.decode("utf-8", "strict")
            except UnicodeError as exc:
                raise MeasurementRefusal("mapped path is not UTF-8") from exc
            if path == expected_path:
                metadata = info.prp_vip.vip_vi.vi_stat
                return VnodeIdentity(
                    int(metadata.vst_dev),
                    int(metadata.vst_ino),
                    int(metadata.vst_mode),
                    int(metadata.vst_uid),
                    int(metadata.vst_gid),
                    int(metadata.vst_nlink),
                    int(metadata.vst_size),
                )
        next_address = int(region.pri_address + region.pri_size)
        if next_address <= address:
            raise MeasurementRefusal("mapped region overflow")
        address = next_address
    raise MeasurementRefusal("private executable mapped vnode absent")


def native_cdhash(pid: int) -> str:
    _, libc = _darwin_libraries()
    value = (ctypes.c_ubyte * 20)()
    if libc.csops(pid, 5, value, len(value)) != 0:
        raise MeasurementRefusal("process CDHash unavailable")
    raw = bytes(value)
    if raw == b"\0" * 20:
        raise MeasurementRefusal("process CDHash is empty")
    return raw.hex()


@dataclasses.dataclass(frozen=True)
class SpawnIntent:
    schema: str
    phase: str
    nonce: str
    route: str
    private_executable_path: str
    private_executable_sha256: str
    runtime_manifest_sha256: str
    version_lock_identity: str
    parent_pid: str
    parent_pidversion: str
    child_pid: str | None
    child_pidversion: str | None
    mapped_vnode_dev: str | None
    mapped_vnode_ino: str | None
    boot_identity: str
    prepared_wall_ns: str
    published_wall_ns: str | None
    terminal_reason: str | None
    intent_digest: str

    @classmethod
    def create(
        cls,
        *,
        nonce: str,
        route: str,
        phase: str,
        boot_id: str,
        parent_pid: int,
        parent_pidversion: str,
        child_pid: int | None,
        child_pidversion: str | None,
        private_executable_path: str,
        private_executable_sha256: str,
        runtime_manifest_sha256: str,
        version_lock_identity: str,
        mapped_vnode_dev: str | None,
        mapped_vnode_ino: str | None,
        created_wall_ns: str,
        updated_wall_ns: str | None,
        terminal_reason: str | None = None,
    ) -> "SpawnIntent":
        body = {
            "schema": "awa-registration-spawn-intent/v1",
            "phase": phase,
            "nonce": nonce,
            "route": route,
            "private_executable_path": private_executable_path,
            "private_executable_sha256": private_executable_sha256,
            "runtime_manifest_sha256": runtime_manifest_sha256,
            "version_lock_identity": version_lock_identity,
            "parent_pid": str(parent_pid),
            "parent_pidversion": parent_pidversion,
            "child_pid": str(child_pid) if child_pid is not None else None,
            "child_pidversion": child_pidversion,
            "mapped_vnode_dev": mapped_vnode_dev,
            "mapped_vnode_ino": mapped_vnode_ino,
            "boot_identity": boot_id,
            "prepared_wall_ns": created_wall_ns,
            "published_wall_ns": updated_wall_ns,
            "terminal_reason": terminal_reason,
        }
        body["intent_digest"] = authority_digest(
            "awa-registration-spawn-intent/v1", body
        )
        value = cls(**body)
        value.validate()
        return value

    def validate(self) -> None:
        if self.schema != "awa-registration-spawn-intent/v1":
            raise ValueError("spawn-intent schema mismatch")
        if self.phase not in ALL_PHASES or self.route not in ROUTES:
            raise ValueError("spawn-intent enum mismatch")
        if not _is_hex64(self.nonce):
            raise ValueError("spawn-intent nonce malformed")
        if not os.path.isabs(self.private_executable_path):
            raise ValueError("spawn-intent executable must be absolute")
        for name in (
            "private_executable_sha256",
            "runtime_manifest_sha256",
            "version_lock_identity",
            "parent_pidversion",
            "boot_identity",
            "intent_digest",
        ):
            if not _is_hex64(getattr(self, name)):
                raise ValueError(f"spawn-intent {name} malformed")
        if self.child_pidversion is not None and not _is_hex64(
            self.child_pidversion
        ):
            raise ValueError("spawn-intent child pidversion malformed")
        if (self.mapped_vnode_dev is None) != (self.mapped_vnode_ino is None):
            raise ValueError("spawn-intent mapped vnode is partial")
        _decimal(self.parent_pid, "parent_pid")
        _decimal(self.prepared_wall_ns, "prepared_wall_ns")
        for name in (
            "child_pid",
            "mapped_vnode_dev",
            "mapped_vnode_ino",
            "published_wall_ns",
        ):
            value = getattr(self, name)
            if value is not None:
                _decimal(value, name)
        if self.phase == "PREPARED":
            if any(
                value is not None
                for value in (
                    self.child_pid,
                    self.child_pidversion,
                    self.mapped_vnode_dev,
                    self.mapped_vnode_ino,
                    self.published_wall_ns,
                    self.terminal_reason,
                )
            ):
                raise ValueError("PREPARED intent contains child/terminal state")
        if self.phase in {"SPAWNED", "READY", "GO", "PRODUCT"}:
            if self.child_pid is None or self.published_wall_ns is None:
                raise ValueError("spawned intent lacks child/publication state")
            if self.terminal_reason is not None:
                raise ValueError("nonterminal intent has terminal reason")
        if self.phase == "TERMINAL":
            if self.terminal_reason not in TERMINAL_REASONS:
                raise ValueError("terminal intent reason mismatch")
        body = self.to_mapping()
        claimed = body.pop("intent_digest")
        if claimed != authority_digest("awa-registration-spawn-intent/v1", body):
            raise ValueError("spawn-intent digest mismatch")

    @classmethod
    def from_bytes(cls, raw: bytes) -> "SpawnIntent":
        value = parse_canonical_lf(raw, maximum=65_536)
        if not isinstance(value, dict) or set(value) != set(INTENT_FIELDS):
            raise ValueError("spawn-intent field set mismatch")
        intent = cls(**value)
        intent.validate()
        return intent

    def to_bytes(self) -> bytes:
        return canonical_lf_bytes(self.to_mapping())

    def to_mapping(self) -> dict:
        return {
            field.name: getattr(self, field.name)
            for field in dataclasses.fields(self)
        }

    def transition(self, phase: str, **values: object) -> "SpawnIntent":
        order = {
            "PREPARED": 0,
            "SPAWNED": 1,
            "READY": 2,
            "GO": 3,
            "PRODUCT": 4,
            "TERMINAL": 5,
        }
        if phase not in order or order[phase] != order[self.phase] + 1:
            if not (self.phase != "TERMINAL" and phase == "TERMINAL"):
                raise ValueError("spawn-intent transition is not monotonic")
        mapping = self.to_mapping()
        mapping["phase"] = phase
        if phase == "SPAWNED":
            for key in (
                "child_pid",
                "child_pidversion",
                "mapped_vnode_dev",
                "mapped_vnode_ino",
            ):
                supplied = values.get(key)
                if key == "child_pid" and supplied is not None:
                    supplied = str(supplied)
                mapping[key] = supplied
            mapping["published_wall_ns"] = values.get(
                "published_wall_ns", self.prepared_wall_ns
            )
        if phase == "TERMINAL":
            mapping["terminal_reason"] = values.get("terminal_reason")
        mapping["intent_digest"] = authority_digest(
            "awa-registration-spawn-intent/v1",
            {
                key: value
                for key, value in mapping.items()
                if key != "intent_digest"
            },
        )
        value = SpawnIntent(**mapping)
        value.validate()
        return value


class InMemoryIntentStore:
    def __init__(self, intents: Iterable[SpawnIntent] = ()) -> None:
        self._values = {intent.nonce: intent for intent in intents}
        self.archived: dict[str, SpawnIntent] = {}
        self.events: list[str] = []

    def __contains__(self, nonce: str) -> bool:
        return nonce in self._values

    def __getitem__(self, nonce: str) -> SpawnIntent:
        return self._values[nonce]

    def values(self) -> tuple[SpawnIntent, ...]:
        return tuple(
            self._values[key]
            for key in sorted(self._values, key=lambda item: item.encode())
        )

    def create(self, intent: SpawnIntent) -> None:
        if intent.nonce in self._values or intent.phase != "PREPARED":
            raise ValueError("intent creation refused")
        self._values[intent.nonce] = intent
        self.events.extend(
            ("create:PREPARED", "sync:file", "sync:directory")
        )

    def transition(self, nonce: str, phase: str, **values: object) -> None:
        current = self._values[nonce]
        self._values[nonce] = current.transition(phase, **values)
        self.events.extend(
            (f"transition:{phase}", "sync:file", "sync:directory")
        )

    def archive(self, nonce: str, terminal_reason: str) -> None:
        current = self._values[nonce]
        if current.phase != "TERMINAL":
            current = current.transition(
                "TERMINAL", terminal_reason=terminal_reason
            )
        self.archived[nonce] = current
        del self._values[nonce]
        self.events.extend(("archive", "sync:file", "sync:directory"))


class IntentStore(Protocol):
    def values(self) -> tuple[SpawnIntent, ...]: ...

    def create(self, intent: SpawnIntent) -> None: ...

    def transition(self, nonce: str, phase: str, **values: object) -> None: ...

    def archive(self, nonce: str, terminal_reason: str) -> None: ...


class FilesystemIntentStore:
    """Invoking-user-owned, no-symlink, fsync-durable spawn intent store."""

    MAX_RECORDS = 64

    def __init__(
        self,
        directory: Path,
        *,
        expected_uid: int,
        create: bool = True,
    ) -> None:
        if not directory.is_absolute() or expected_uid < 0:
            raise ProtocolRefusal("intent store location refused")
        self.directory = directory
        self.expected_uid = expected_uid
        if create:
            self._create_directory()
        self._validate_directory()
        self._lock_path = self.directory / ".lock"

    @classmethod
    def for_uid(cls, uid: int | None = None) -> "FilesystemIntentStore":
        selected_uid = os.getuid() if uid is None else uid
        if type(selected_uid) is not int or selected_uid < 0:
            raise ProtocolRefusal("intent UID refused")
        record = pwd.getpwuid(selected_uid)
        home = Path(record.pw_dir)
        if (
            not home.is_absolute()
            or home.is_symlink()
            or home.resolve(strict=True) != home
            or home.lstat().st_uid != selected_uid
        ):
            raise ProtocolRefusal("intent home authority refused")
        directory = (
            home
            / ".local/share/awa/registration-runtime/spawn-intents/v1"
        )
        return cls(directory, expected_uid=selected_uid)

    def _create_directory(self) -> None:
        missing: list[Path] = []
        current = self.directory
        while not current.exists():
            missing.append(current)
            if current.parent == current:
                raise ProtocolRefusal("intent directory ancestry refused")
            current = current.parent
        if current.is_symlink() or not current.is_dir():
            raise ProtocolRefusal("intent directory ancestor refused")
        for path in reversed(missing):
            path.mkdir(mode=0o700)
            os.chmod(path, 0o700)
            self._sync_directory(path.parent)

    def _validate_directory(self) -> None:
        metadata = self.directory.lstat()
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or self.directory.is_symlink()
            or metadata.st_uid != self.expected_uid
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            raise ProtocolRefusal("intent directory metadata refused")
        current = self.directory
        while current.parent != current:
            metadata = current.lstat()
            if current.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
                raise ProtocolRefusal("intent directory symlink refused")
            if current == Path(pwd.getpwuid(self.expected_uid).pw_dir):
                break
            current = current.parent

    @staticmethod
    def _sync_directory(path: Path) -> None:
        descriptor = os.open(
            path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        )
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _record_path(self, nonce: str) -> Path:
        if not _is_hex64(nonce):
            raise ProtocolRefusal("intent nonce refused")
        return self.directory / f"{nonce}.json"

    def _lock(self) -> int:
        descriptor = os.open(
            self._lock_path,
            os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != self.expected_uid
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            os.close(descriptor)
            raise ProtocolRefusal("intent lock metadata refused")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        return descriptor

    @staticmethod
    def _unlock(descriptor: int) -> None:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

    def _read_path(self, path: Path) -> SpawnIntent:
        descriptor = os.open(
            path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            before = os.fstat(descriptor)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid != self.expected_uid
                or before.st_nlink != 1
                or stat.S_IMODE(before.st_mode) != 0o600
                or not 2 <= before.st_size <= 65_536
            ):
                raise ProtocolRefusal("intent record metadata refused")
            raw = bytearray()
            remaining = before.st_size
            while remaining:
                chunk = os.read(descriptor, min(remaining, 65_536))
                if not chunk:
                    raise ProtocolRefusal("intent record truncated")
                raw.extend(chunk)
                remaining -= len(chunk)
            after = os.fstat(descriptor)
            identity = (
                before.st_dev,
                before.st_ino,
                before.st_mode,
                before.st_uid,
                before.st_nlink,
                before.st_size,
                before.st_mtime_ns,
            )
            if identity != (
                after.st_dev,
                after.st_ino,
                after.st_mode,
                after.st_uid,
                after.st_nlink,
                after.st_size,
                after.st_mtime_ns,
            ):
                raise ProtocolRefusal("intent record changed while reading")
        finally:
            os.close(descriptor)
        intent = SpawnIntent.from_bytes(bytes(raw))
        if path.name != f"{intent.nonce}.json":
            raise ProtocolRefusal("intent record name mismatch")
        return intent

    def _read_nonce_unlocked(self, nonce: str) -> SpawnIntent:
        try:
            return self._read_path(self._record_path(nonce))
        except FileNotFoundError as exc:
            raise ProtocolRefusal("intent record missing") from exc

    def _write_atomic(
        self, intent: SpawnIntent, *, no_replace: bool
    ) -> None:
        intent.validate()
        raw = intent.to_bytes()
        destination = self._record_path(intent.nonce)
        temporary = self.directory / (
            f".{intent.nonce}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
        )
        descriptor = os.open(
            temporary,
            os.O_CREAT
            | os.O_EXCL
            | os.O_WRONLY
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            offset = 0
            while offset < len(raw):
                written = os.write(descriptor, raw[offset:])
                if written <= 0:
                    raise ProtocolRefusal("intent record write failed")
                offset += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        try:
            if no_replace:
                os.link(temporary, destination, follow_symlinks=False)
                os.unlink(temporary)
            else:
                os.replace(temporary, destination)
            self._sync_directory(self.directory)
        except BaseException:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            raise

    def values(self) -> tuple[SpawnIntent, ...]:
        lock = self._lock()
        try:
            names = []
            for entry in self.directory.iterdir():
                if entry.name == ".lock":
                    continue
                if (
                    not entry.name.endswith(".json")
                    or not _is_hex64(entry.name[:-5])
                ):
                    raise ProtocolRefusal("unknown intent store residue")
                names.append(entry)
            if len(names) > self.MAX_RECORDS:
                raise ProtocolRefusal("spawn-intent overflow")
            return tuple(
                self._read_path(path)
                for path in sorted(names, key=lambda item: item.name.encode())
            )
        finally:
            self._unlock(lock)

    def __contains__(self, nonce: str) -> bool:
        try:
            self._record_path(nonce).lstat()
            return True
        except FileNotFoundError:
            return False

    def __getitem__(self, nonce: str) -> SpawnIntent:
        lock = self._lock()
        try:
            return self._read_nonce_unlocked(nonce)
        finally:
            self._unlock(lock)

    def create(self, intent: SpawnIntent) -> None:
        if intent.phase != "PREPARED":
            raise ProtocolRefusal("intent creation must be PREPARED")
        lock = self._lock()
        try:
            self._write_atomic(intent, no_replace=True)
        finally:
            self._unlock(lock)

    def transition(self, nonce: str, phase: str, **values: object) -> None:
        lock = self._lock()
        try:
            current = self._read_nonce_unlocked(nonce)
            successor = current.transition(phase, **values)
            self._write_atomic(successor, no_replace=False)
            rebound = self._read_nonce_unlocked(nonce)
            if rebound != successor:
                raise ProtocolRefusal("intent transition rebind failed")
        finally:
            self._unlock(lock)

    def archive(self, nonce: str, terminal_reason: str) -> None:
        current = self[nonce]
        if current.phase == "TERMINAL":
            return
        self.transition(
            nonce, "TERMINAL", terminal_reason=terminal_reason
        )


@dataclasses.dataclass(frozen=True)
class RetainedLaunchAuthority:
    private_python: str
    private_executable_sha256: str
    runtime_manifest_sha256: str
    version_lock_identity: str
    authority_fds: Mapping[str, int]
    executable_vnode: VnodeIdentity
    reverify: Callable[[], None]

    def validate(self) -> None:
        if (
            not os.path.isabs(self.private_python)
            or not _is_hex64(self.private_executable_sha256)
            or not _is_hex64(self.runtime_manifest_sha256)
            or not _is_hex64(self.version_lock_identity)
            or set(self.authority_fds)
            != set(FD_ASSIGNMENTS) - {"control"}
            or any(
                type(value) is not int or value < 0
                for value in self.authority_fds.values()
            )
            or len(set(self.authority_fds.values()))
            != len(self.authority_fds)
        ):
            raise ProtocolRefusal("retained launch authority refused")


@dataclasses.dataclass
class SpawnedChild:
    pid: int
    pidversion: str
    mapped_vnode: VnodeIdentity
    channel: socket.socket
    direct_child: bool = True


class ParentSpawnBackend(Protocol):
    parent_pid: int
    parent_pidversion: str
    boot_identity: str

    def now_ns(self) -> str: ...

    def spawn(
        self,
        plan: ChildSpawnPlan,
        authority: RetainedLaunchAuthority,
    ) -> SpawnedChild: ...

    def receive_line(
        self, child: SpawnedChild, *, timeout_seconds: float
    ) -> bytes: ...

    def send_line(self, child: SpawnedChild, value: bytes) -> None: ...

    def child_identity_is_continuous(self, child: SpawnedChild) -> bool: ...

    def wait(self, child: SpawnedChild) -> int: ...

    def terminate_and_reap(self, child: SpawnedChild) -> None: ...

    def close(self, child: SpawnedChild) -> None: ...


def run_supervised_spawn(
    *,
    route: str,
    nonce: str,
    authority: RetainedLaunchAuthority,
    store: IntentStore,
    backend: ParentSpawnBackend,
) -> int:
    """Execute the exact PREPARED→PRODUCT protocol as the original parent."""

    authority.validate()
    authority.reverify()
    plan = build_child_spawn_plan(
        private_python=authority.private_python,
        route=route,
        parent_pid=backend.parent_pid,
        nonce=nonce,
    )
    prepared = SpawnIntent.create(
        nonce=nonce,
        route=route,
        phase="PREPARED",
        boot_id=backend.boot_identity,
        parent_pid=backend.parent_pid,
        parent_pidversion=backend.parent_pidversion,
        child_pid=None,
        child_pidversion=None,
        private_executable_path=authority.private_python,
        private_executable_sha256=authority.private_executable_sha256,
        runtime_manifest_sha256=authority.runtime_manifest_sha256,
        version_lock_identity=authority.version_lock_identity,
        mapped_vnode_dev=None,
        mapped_vnode_ino=None,
        created_wall_ns=backend.now_ns(),
        updated_wall_ns=None,
    )
    store.create(prepared)
    child: SpawnedChild | None = None
    product_authorized = False
    try:
        child = backend.spawn(plan, authority)
        verify_mapped_vnode(authority.executable_vnode, child.mapped_vnode)
        store.transition(
            nonce,
            "SPAWNED",
            child_pid=child.pid,
            child_pidversion=child.pidversion,
            mapped_vnode_dev=str(child.mapped_vnode.device),
            mapped_vnode_ino=str(child.mapped_vnode.inode),
            published_wall_ns=backend.now_ns(),
        )
        expected_ready = f"READY {nonce}\n".encode("ascii")
        if (
            backend.receive_line(child, timeout_seconds=5.0)
            != expected_ready
        ):
            raise ProtocolRefusal("child READY barrier refused")
        if not backend.child_identity_is_continuous(child):
            raise ProtocolRefusal("child identity changed before GO")
        authority.reverify()
        store.transition(nonce, "READY")
        backend.send_line(child, f"GO {nonce}\n".encode("ascii"))
        store.transition(nonce, "GO")
        expected_import = f"IMPORT_READY {nonce}\n".encode("ascii")
        if (
            backend.receive_line(child, timeout_seconds=5.0)
            != expected_import
        ):
            raise ProtocolRefusal("child IMPORT_READY barrier refused")
        if not backend.child_identity_is_continuous(child):
            raise ProtocolRefusal("child identity changed at import barrier")
        authority.reverify()
        store.transition(nonce, "PRODUCT")
        product_authorized = True
        result = backend.wait(child)
        expected_terminal = f"TERMINAL {nonce} {result}\n".encode("ascii")
        if (
            backend.receive_line(child, timeout_seconds=1.0)
            != expected_terminal
        ):
            raise ProtocolRefusal("child terminal barrier refused")
        store.transition(
            nonce, "TERMINAL", terminal_reason="NORMAL_EXIT"
        )
        return result
    except BaseException:
        if child is not None and backend.child_identity_is_continuous(child):
            backend.terminate_and_reap(child)
        current = next(
            (item for item in store.values() if item.nonce == nonce),
            None,
        )
        if current is not None and current.phase != "TERMINAL":
            store.transition(
                nonce, "TERMINAL", terminal_reason="SPAWN_FAILED"
            )
        if product_authorized:
            raise ProtocolRefusal("authorized product child failed")
        raise
    finally:
        if child is not None:
            backend.close(child)


class DarwinPosixSpawnBackend:
    """Ordinary Darwin posix_spawn backend with CLOEXEC_DEFAULT."""

    POSIX_SPAWN_CLOEXEC_DEFAULT = 0x4000

    def __init__(
        self,
        *,
        parent_pidversion: str,
        boot_id: str,
        observe_pidversion: Callable[[int], str | None],
        observe_mapped_vnode: Callable[[int, str], VnodeIdentity],
    ) -> None:
        if sys.platform != "darwin":
            raise ProtocolRefusal("Darwin spawn backend is unavailable")
        if not _is_hex64(parent_pidversion) or not _is_hex64(boot_id):
            raise ProtocolRefusal("parent process identity refused")
        self.parent_pid = os.getpid()
        self.parent_pidversion = parent_pidversion
        self.boot_identity = boot_id
        self._observe_pidversion = observe_pidversion
        self._observe_mapped_vnode = observe_mapped_vnode
        self._buffers: dict[int, bytearray] = {}
        self._waited: set[int] = set()
        self._libc = ctypes.CDLL(
            "/usr/lib/libSystem.B.dylib", use_errno=True
        )
        self._libc.posix_spawn_file_actions_init.argtypes = [
            ctypes.POINTER(ctypes.c_void_p)
        ]
        self._libc.posix_spawn_file_actions_adddup2.argtypes = [
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.c_int,
            ctypes.c_int,
        ]
        self._libc.posix_spawn_file_actions_addclose.argtypes = [
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.c_int,
        ]
        self._libc.posix_spawn_file_actions_destroy.argtypes = [
            ctypes.POINTER(ctypes.c_void_p)
        ]
        self._libc.posix_spawnattr_init.argtypes = [
            ctypes.POINTER(ctypes.c_void_p)
        ]
        self._libc.posix_spawnattr_setflags.argtypes = [
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.c_short,
        ]
        self._libc.posix_spawnattr_destroy.argtypes = [
            ctypes.POINTER(ctypes.c_void_p)
        ]
        self._libc.posix_spawn.argtypes = [
            ctypes.POINTER(ctypes.c_int),
            ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_char_p),
            ctypes.POINTER(ctypes.c_char_p),
        ]

    def now_ns(self) -> str:
        return str(time.time_ns())

    @staticmethod
    def _c_array(values: Iterable[str]) -> ctypes.Array:
        encoded = []
        for value in values:
            raw = value.encode("utf-8", "strict")
            if b"\0" in raw:
                raise ProtocolRefusal("spawn string contains NUL")
            encoded.append(raw)
        array_type = ctypes.c_char_p * (len(encoded) + 1)
        return array_type(*encoded, None)

    def _spawn_pid(
        self,
        executable: str,
        argv: tuple[str, ...],
        environment: Mapping[str, str],
        sources: Mapping[str, int],
    ) -> int:
        actions = ctypes.c_void_p()
        attributes = ctypes.c_void_p()
        high: list[int] = []
        file_actions_ready = False
        attributes_ready = False
        try:
            result = self._libc.posix_spawn_file_actions_init(
                ctypes.byref(actions)
            )
            if result:
                raise OSError(result, os.strerror(result))
            file_actions_ready = True
            occupied = set(sources.values()) | set(FD_ASSIGNMENTS.values())
            for role in FD_ASSIGNMENTS:
                minimum = MINIMUM_REMAP_FD
                while minimum in occupied:
                    minimum += 1
                descriptor = fcntl.fcntl(
                    sources[role], fcntl.F_DUPFD_CLOEXEC, minimum
                )
                if descriptor in occupied:
                    raise ProtocolRefusal("spawn high-fd collision")
                high.append(descriptor)
                occupied.add(descriptor)
                result = self._libc.posix_spawn_file_actions_adddup2(
                    ctypes.byref(actions),
                    descriptor,
                    FD_ASSIGNMENTS[role],
                )
                if result:
                    raise OSError(result, os.strerror(result))
                result = self._libc.posix_spawn_file_actions_addclose(
                    ctypes.byref(actions), descriptor
                )
                if result:
                    raise OSError(result, os.strerror(result))
            result = self._libc.posix_spawnattr_init(
                ctypes.byref(attributes)
            )
            if result:
                raise OSError(result, os.strerror(result))
            attributes_ready = True
            flags = ctypes.c_short(self.POSIX_SPAWN_CLOEXEC_DEFAULT)
            result = self._libc.posix_spawnattr_setflags(
                ctypes.byref(attributes), flags
            )
            if result:
                raise OSError(result, os.strerror(result))
            argv_array = self._c_array(argv)
            env_array = self._c_array(
                f"{key}={environment[key]}"
                for key in sorted(environment, key=lambda item: item.encode())
            )
            child_pid = ctypes.c_int()
            result = self._libc.posix_spawn(
                ctypes.byref(child_pid),
                executable.encode("utf-8"),
                ctypes.byref(actions),
                ctypes.byref(attributes),
                argv_array,
                env_array,
            )
            if result:
                raise OSError(result, os.strerror(result))
            return int(child_pid.value)
        finally:
            for descriptor in reversed(high):
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            if attributes_ready:
                self._libc.posix_spawnattr_destroy(
                    ctypes.byref(attributes)
                )
            if file_actions_ready:
                self._libc.posix_spawn_file_actions_destroy(
                    ctypes.byref(actions)
                )

    def spawn(
        self,
        plan: ChildSpawnPlan,
        authority: RetainedLaunchAuthority,
    ) -> SpawnedChild:
        parent_channel, child_channel = socket.socketpair(
            socket.AF_UNIX, socket.SOCK_STREAM
        )
        try:
            sources = {
                "control": child_channel.fileno(),
                **authority.authority_fds,
            }
            plan_fd_remap(sources)
            pid = self._spawn_pid(
                authority.private_python,
                plan.argv,
                plan.environment,
                sources,
            )
        except BaseException:
            parent_channel.close()
            child_channel.close()
            raise
        child_channel.close()
        observed_version = self._observe_pidversion(pid)
        if observed_version is None:
            try:
                os.kill(pid, signal.SIGKILL)
            finally:
                os.waitpid(pid, 0)
                parent_channel.close()
            raise ProtocolRefusal("spawned child pidversion unavailable")
        mapped = self._observe_mapped_vnode(pid, authority.private_python)
        self._buffers[pid] = bytearray()
        return SpawnedChild(
            pid=pid,
            pidversion=observed_version,
            mapped_vnode=mapped,
            channel=parent_channel,
        )

    def receive_line(
        self, child: SpawnedChild, *, timeout_seconds: float
    ) -> bytes:
        deadline = time.monotonic() + timeout_seconds
        buffer = self._buffers.setdefault(child.pid, bytearray())
        while True:
            newline = buffer.find(b"\n")
            if newline >= 0:
                result = bytes(buffer[: newline + 1])
                del buffer[: newline + 1]
                return result
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProtocolRefusal("child barrier timeout")
            readable, _, _ = select.select(
                [child.channel], [], [], remaining
            )
            if not readable:
                raise ProtocolRefusal("child barrier timeout")
            chunk = child.channel.recv(256)
            if not chunk:
                raise ProtocolRefusal("child control EOF")
            buffer.extend(chunk)
            if len(buffer) > 512:
                raise ProtocolRefusal("child barrier overflow")

    def send_line(self, child: SpawnedChild, value: bytes) -> None:
        if not value.endswith(b"\n") or len(value) > 128:
            raise ProtocolRefusal("parent barrier framing refused")
        child.channel.sendall(value)

    def child_identity_is_continuous(self, child: SpawnedChild) -> bool:
        return (
            child.direct_child
            and child.pid not in self._waited
            and self._observe_pidversion(child.pid) == child.pidversion
        )

    def wait(self, child: SpawnedChild) -> int:
        pid, status = os.waitpid(child.pid, 0)
        if pid != child.pid:
            raise ProtocolRefusal("unexpected child reaped")
        self._waited.add(child.pid)
        return os.waitstatus_to_exitcode(status)

    def terminate_and_reap(self, child: SpawnedChild) -> None:
        if not self.child_identity_is_continuous(child):
            return
        try:
            os.kill(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        try:
            waited, _ = os.waitpid(child.pid, 0)
            if waited == child.pid:
                self._waited.add(child.pid)
        except ChildProcessError:
            pass

    def close(self, child: SpawnedChild) -> None:
        self._buffers.pop(child.pid, None)
        try:
            child.channel.close()
        except OSError:
            pass


class FakeProcessObserver:
    """Read-only deterministic process observer used by local tests."""

    def __init__(
        self,
        current_boot: str,
        *,
        live: Mapping[tuple[int, str], bool] | None = None,
        scripted_liveness: Mapping[
            tuple[int, str], Iterable[bool]
        ] | None = None,
        wait_results: Mapping[tuple[int, str], bool] | None = None,
    ) -> None:
        self.current_boot = current_boot
        self.live = dict(live or {})
        self.scripted = {
            key: list(values) for key, values in (scripted_liveness or {}).items()
        }
        self.wait_results = dict(wait_results or {})
        self.observations: list[tuple[str, int, str]] = []
        self.signals: list[tuple[int, int]] = []

    def is_live(self, pid: int, version: str) -> bool:
        self.observations.append(("live", pid, version))
        key = (pid, version)
        scripted = self.scripted.get(key)
        if scripted:
            return scripted.pop(0)
        return self.live.get(key, False)

    def wait_natural_exit(self, pid: int, version: str) -> bool:
        self.observations.append(("wait", pid, version))
        return self.wait_results.get((pid, version), False)


class DarwinProcessObserver:
    """Read-only libproc/sysctl observer used by later-invocation recovery."""

    MAX_PIDS = 4096

    def __init__(self, *, uid: int | None = None) -> None:
        self.uid = os.getuid() if uid is None else uid
        if type(self.uid) is not int or self.uid < 0:
            raise ProtocolRefusal("observer UID refused")
        self.current_boot = native_boot_identity()
        self._libproc, self._libc = _darwin_libraries()
        self._libproc.proc_listpids.argtypes = [
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_int,
        ]
        self._libproc.proc_listpids.restype = ctypes.c_int
        self._libc.sysctl.argtypes = [
            ctypes.POINTER(ctypes.c_int),
            ctypes.c_uint,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.c_void_p,
            ctypes.c_size_t,
        ]
        self._libc.sysctl.restype = ctypes.c_int

    def _info(self, pid: int) -> _ProcBsdInfo | None:
        try:
            first = native_bsd_info(pid)
            second = native_bsd_info(pid)
        except ProtocolRefusal:
            return None
        if bytes(first) != bytes(second) or first.pbi_uid != self.uid:
            return None
        return second

    def is_live(self, pid: int, version: str) -> bool:
        info = self._info(pid)
        return (
            info is not None
            and info.pbi_status != 5
            and native_pidversion(pid, self.current_boot) == version
        )

    def _pids(self) -> tuple[int, ...]:
        capacity = self.MAX_PIDS
        values = (ctypes.c_int * capacity)()
        size = self._libproc.proc_listpids(
            4,
            self.uid,
            values,
            ctypes.sizeof(values),
        )
        if size < 0 or size % ctypes.sizeof(ctypes.c_int):
            raise ProtocolRefusal("UID process enumeration refused")
        count = size // ctypes.sizeof(ctypes.c_int)
        if count >= capacity:
            raise ProtocolRefusal("UID process enumeration overflow")
        return tuple(
            sorted(
                {int(values[index]) for index in range(count) if values[index] > 0}
            )
        )

    def _arguments(
        self, pid: int
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        size = ctypes.c_size_t()
        mib = (ctypes.c_int * 3)(1, 49, pid)
        if self._libc.sysctl(
            mib, 3, None, ctypes.byref(size), None, 0
        ) != 0 or not 4 <= size.value <= 4 * 1024 * 1024:
            raise ProtocolRefusal("process arguments unavailable")
        buffer = ctypes.create_string_buffer(size.value)
        if self._libc.sysctl(
            mib,
            3,
            buffer,
            ctypes.byref(size),
            None,
            0,
        ) != 0:
            raise ProtocolRefusal("process arguments changed")
        raw = bytes(buffer.raw[: size.value])
        argc = int.from_bytes(raw[:4], sys.byteorder, signed=True)
        if not 1 <= argc <= 64:
            raise ProtocolRefusal("process argc refused")
        cursor = 4

        def next_string() -> bytes:
            nonlocal cursor
            end = raw.find(b"\0", cursor)
            if end < 0:
                raise ProtocolRefusal("process argument framing refused")
            value = raw[cursor:end]
            cursor = end + 1
            return value

        next_string()
        while cursor < len(raw) and raw[cursor] == 0:
            cursor += 1
        argv = []
        for _ in range(argc):
            argv.append(next_string().decode("utf-8", "strict"))
        environment = []
        while cursor < len(raw):
            if raw[cursor] == 0:
                cursor += 1
                continue
            environment.append(next_string().decode("utf-8", "strict"))
        return tuple(argv), tuple(environment)

    @staticmethod
    def _expected_argv(intent: SpawnIntent) -> tuple[str, ...]:
        return (
            intent.private_executable_path,
            "-I",
            "-S",
            "-B",
            str(CHILD_PATH),
            "--route",
            intent.route,
            "--expected-parent-pid",
            intent.parent_pid,
            "--nonce",
            intent.nonce,
        )

    @staticmethod
    def _expected_environment(intent: SpawnIntent) -> tuple[str, ...]:
        return tuple(
            sorted(
                (
                    f"AWA_REGISTRATION_SPAWN_NONCE={intent.nonce}",
                    "LANG=C",
                    "LC_ALL=C",
                    "PATH=/usr/bin:/bin",
                )
            )
        )

    def _matches_child(self, pid: int, intent: SpawnIntent) -> bool:
        info = self._info(pid)
        if info is None or info.pbi_status == 5:
            return False
        try:
            argv, environment = self._arguments(pid)
            path = native_process_path(pid)
            version = native_pidversion(pid, self.current_boot)
            mapped = native_mapped_vnode(
                pid, intent.private_executable_path
            )
            native_cdhash(pid)
        except (OSError, UnicodeError, ProtocolRefusal, MeasurementRefusal):
            return False
        if (
            argv != self._expected_argv(intent)
            or tuple(sorted(environment)) != self._expected_environment(intent)
            or path != intent.private_executable_path
            or int(info.pbi_ppid) not in {int(intent.parent_pid), 1}
            or version is None
        ):
            return False
        if intent.child_pid is not None and pid != int(intent.child_pid):
            return False
        if (
            intent.child_pidversion is not None
            and version != intent.child_pidversion
        ):
            return False
        if (
            intent.mapped_vnode_dev is not None
            and mapped.device != int(intent.mapped_vnode_dev)
        ) or (
            intent.mapped_vnode_ino is not None
            and mapped.inode != int(intent.mapped_vnode_ino)
        ):
            return False
        try:
            with open(intent.private_executable_path, "rb") as handle:
                digest = hashlib.sha256(handle.read()).hexdigest()
        except OSError:
            return False
        return digest == intent.private_executable_sha256

    def _nonce_related(self, pid: int, intent: SpawnIntent) -> bool:
        try:
            argv, environment = self._arguments(pid)
            return intent.nonce in argv or (
                f"AWA_REGISTRATION_SPAWN_NONCE={intent.nonce}"
                in environment
            )
        except (OSError, UnicodeError, ProtocolRefusal):
            return False

    def _scan(self, intent: SpawnIntent) -> tuple[tuple[int, str], ...] | None:
        exact: list[tuple[int, str]] = []
        ambiguous = False
        for pid in self._pids():
            if pid == os.getpid():
                continue
            related = self._nonce_related(pid, intent)
            if self._matches_child(pid, intent):
                version = native_pidversion(pid, self.current_boot)
                if version is None:
                    ambiguous = True
                else:
                    exact.append((pid, version))
            elif related:
                ambiguous = True
        if ambiguous or len(exact) > 1:
            return None
        return tuple(exact)

    def pair_is_coherent(self, intent: SpawnIntent) -> bool:
        matches = self._scan(intent)
        if matches is None:
            return False
        if intent.phase == "PREPARED":
            return len(matches) <= 1
        return (
            len(matches) == 1
            and intent.child_pid is not None
            and matches[0][0] == int(intent.child_pid)
            and matches[0][1] == intent.child_pidversion
        )

    def find_inert_candidate(
        self, intent: SpawnIntent
    ) -> tuple[str, tuple[int, str] | None]:
        matches = self._scan(intent)
        if matches is None:
            return "AMBIGUOUS", None
        if not matches:
            return "NONE", None
        return "EXACT_ONE", matches[0]

    def wait_natural_exit(self, pid: int, version: str) -> bool:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if not self.is_live(pid, version):
                return True
            time.sleep(0.1)
        return not self.is_live(pid, version)


@dataclasses.dataclass(frozen=True)
class ReconcileDecision:
    nonce: str
    outcome: str
    operator_message: str | None


class IntentReconciler:
    """Parent-first observation-only reconciler; it has no signal method."""

    def __init__(self, observer: FakeProcessObserver):
        self.observer = observer

    def reconcile(
        self, store: IntentStore
    ) -> tuple[ReconcileDecision, ...]:
        if len(store.values()) > 64:
            raise ProtocolRefusal("spawn-intent overflow")
        results: list[ReconcileDecision] = []
        for intent in store.values():
            if intent.phase == "TERMINAL":
                continue
            if intent.boot_identity != self.observer.current_boot:
                residue_scan = getattr(
                    self.observer, "find_inert_candidate", None
                )
                if residue_scan is not None:
                    scan_outcome, _ = residue_scan(intent)
                    if scan_outcome != "NONE":
                        results.append(
                            ReconcileDecision(
                                intent.nonce,
                                "RESIDUE_REFUSED",
                                AMBIGUOUS_RESIDUE_MESSAGE,
                            )
                        )
                        continue
                store.archive(intent.nonce, "REBOOT_CLEARED")
                results.append(
                    ReconcileDecision(intent.nonce, "REBOOT_CLEARED", None)
                )
                continue
            parent_live = self.observer.is_live(
                int(intent.parent_pid), intent.parent_pidversion
            )
            if parent_live:
                # This invocation never crosses from the live-parent branch to
                # absent even if the process exits during subsequent checks.
                pair_check = getattr(
                    self.observer, "pair_is_coherent", None
                )
                if pair_check is not None:
                    coherent = bool(pair_check(intent))
                else:
                    coherent = True
                if pair_check is None and intent.phase != "PREPARED":
                    coherent = (
                        intent.child_pid is not None
                        and intent.child_pidversion is not None
                        and self.observer.is_live(
                            int(intent.child_pid), intent.child_pidversion
                        )
                    )
                if not coherent:
                    results.append(
                        ReconcileDecision(
                            intent.nonce,
                            "RESIDUE_REFUSED",
                            AMBIGUOUS_RESIDUE_MESSAGE,
                        )
                    )
                else:
                    results.append(
                        ReconcileDecision(
                            intent.nonce,
                            "HEALTHY_PAIR_PRESERVED",
                            None,
                        )
                    )
                continue
            residue_scan = getattr(
                self.observer, "find_inert_candidate", None
            )
            if residue_scan is not None:
                scan_outcome, candidate = residue_scan(intent)
                if scan_outcome != "EXACT_ONE" or candidate is None:
                    results.append(
                        ReconcileDecision(
                            intent.nonce,
                            "RESIDUE_REFUSED",
                            AMBIGUOUS_RESIDUE_MESSAGE,
                        )
                    )
                    continue
                candidate_pid, candidate_version = candidate
                if self.observer.wait_natural_exit(
                    candidate_pid, candidate_version
                ):
                    unchanged = next(
                        (
                            value
                            for value in store.values()
                            if value.nonce == intent.nonce
                        ),
                        None,
                    )
                    rescanned, _ = residue_scan(intent)
                    if (
                        unchanged != intent
                        or self.observer.is_live(
                            int(intent.parent_pid),
                            intent.parent_pidversion,
                        )
                        or rescanned != "NONE"
                    ):
                        results.append(
                            ReconcileDecision(
                                intent.nonce,
                                "RESIDUE_REFUSED",
                                AMBIGUOUS_RESIDUE_MESSAGE,
                            )
                        )
                        continue
                    store.transition(
                        intent.nonce,
                        "TERMINAL",
                        terminal_reason="NATURAL_EXIT_RECONCILED",
                    )
                    results.append(
                        ReconcileDecision(
                            intent.nonce,
                            "NATURAL_EXIT_RECONCILED",
                            None,
                        )
                    )
                else:
                    results.append(
                        ReconcileDecision(
                            intent.nonce,
                            "RESIDUE_REFUSED",
                            CONFIRMED_INERT_MESSAGE,
                        )
                    )
                continue
            if intent.child_pid is None or intent.child_pidversion is None:
                results.append(
                    ReconcileDecision(
                        intent.nonce,
                        "RESIDUE_REFUSED",
                        AMBIGUOUS_RESIDUE_MESSAGE,
                    )
                )
                continue
            child_live = self.observer.is_live(
                int(intent.child_pid), intent.child_pidversion
            )
            if not child_live:
                # A same-boot missing PID alone is not proof that no
                # nonce-matching pre-watchdog process exists.
                results.append(
                    ReconcileDecision(
                        intent.nonce,
                        "RESIDUE_REFUSED",
                        AMBIGUOUS_RESIDUE_MESSAGE,
                    )
                )
                continue
            if self.observer.wait_natural_exit(
                int(intent.child_pid), intent.child_pidversion
            ):
                store.transition(
                    intent.nonce,
                    "TERMINAL",
                    terminal_reason="NATURAL_EXIT_RECONCILED",
                )
                results.append(
                    ReconcileDecision(
                        intent.nonce,
                        "NATURAL_EXIT_RECONCILED",
                        None,
                    )
                )
            else:
                results.append(
                    ReconcileDecision(
                        intent.nonce,
                        "RESIDUE_REFUSED",
                        CONFIRMED_INERT_MESSAGE,
                    )
                )
        return tuple(results)


def _installed_main(route: str) -> int:
    if route not in ROUTES:
        raise ProtocolRefusal("route refused")
    if (
        sys.executable != PLATFORM_PYTHON
        or not sys.flags.isolated
        or not sys.flags.no_site
        or not sys.dont_write_bytecode
        or os.environ
        != {"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"}
    ):
        raise MeasurementRefusal("platform interpreter boundary refused")
    with contextlib.ExitStack() as stack:
        for path in (ENTRYPOINT_PATH, BOOTSTRAP_PATH, CHILD_PATH):
            verify_root_owned_ancestry(path)
            retained = RetainedFile.open(
                path,
                expected_uid=0,
                expected_gid=0,
                expected_mode=0o555,
                limit=8 * 1024 * 1024,
            )
            stack.callback(retained.close)
        store = FilesystemIntentStore.for_uid()
        observer = DarwinProcessObserver()
        decisions = IntentReconciler(observer).reconcile(store)
        refusal = next(
            (
                decision.operator_message
                for decision in decisions
                if decision.outcome == "RESIDUE_REFUSED"
            ),
            None,
        )
        if refusal is not None:
            print(refusal, file=sys.stderr)
            raise ProtocolRefusal("spawn-intent reconciliation refused")
        nonce = secrets.token_hex(32)
        boot_id = observer.current_boot
        parent_version = native_pidversion(os.getpid(), boot_id)
        if parent_version is None:
            raise ProtocolRefusal("parent pidversion unavailable")

        def observe_mapped(pid: int, path: str) -> VnodeIdentity:
            native_cdhash(pid)
            return native_mapped_vnode(pid, path)

        backend = DarwinPosixSpawnBackend(
            parent_pidversion=parent_version,
            boot_id=boot_id,
            observe_pidversion=lambda pid: native_pidversion(pid, boot_id),
            observe_mapped_vnode=observe_mapped,
        )
        with load_installed_launch_authority(
            route=route,
            nonce=nonce,
        ) as authority:
            return run_supervised_spawn(
                route=route,
                nonce=nonce,
                authority=authority,
                store=store,
                backend=backend,
            )


def main(argv: list[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if len(values) == 3 and values[0] == "--measure-private-runtime":
        try:
            result = measure_private_runtime(
                Path(values[1]), Path(values[2])
            )
            sys.stdout.buffer.write(canonical_lf_bytes(result))
            return 0
        except (MeasurementRefusal, OSError, ValueError) as exc:
            print(f"awa-registration-bootstrap: {exc}", file=sys.stderr)
            return 1
    parser = argparse.ArgumentParser()
    parser.add_argument("route", choices=ROUTES)
    args = parser.parse_args(values)
    try:
        return _installed_main(args.route)
    except (ProtocolRefusal, MeasurementRefusal, OSError, ValueError) as exc:
        print(f"awa-registration-bootstrap: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
