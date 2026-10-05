"""Descriptor-bound macOS/APFS profile checks for ADR 0025 Body A."""

from __future__ import annotations

import ctypes
import fcntl
import hashlib
import os
import platform
import re
import sqlite3
import stat
import unicodedata
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, fields
from pathlib import Path
from typing import ClassVar, Iterator

from . import registration_jcs


MEASUREMENT_ORDER = (
    "ANCESTRY",
    "DESCRIPTOR_FS",
    "SQLITE_RUNTIME",
    "DB_OPEN",
    "PRAGMA_READBACK",
    "WAL_DURABILITY",
    "DEPENDENCY_DEVICES",
    "FINAL_DESCRIPTOR_RECHECK",
)
DESCRIPTOR_ROLES = (
    "state_parent",
    "db",
    "wal",
    "shm",
    "proof_parent",
    "projection_parent",
    "legacy_parent",
    "root",
    "git_dir",
    "git_common",
)
_HEX = re.compile(r"^[0-9a-f]{64}$")
_UNSIGNED = re.compile(r"^(0|[1-9][0-9]*)$")
_SIGNED = re.compile(r"^(0|-?[1-9][0-9]*)$")
_RECORD_KEYS = {
    "ordinal",
    "role",
    "component_hash",
    "st_dev",
    "st_ino",
    "st_mode",
    "st_uid",
    "st_gid",
    "st_nlink",
    "fd_flags",
    "nofollow",
    "fstype",
    "fsid_0",
    "fsid_1",
    "mount_flags",
}
_PROFILE_KEYS = {
    "schema",
    "measurement_order",
    "platform",
    "os_build",
    "apfs_fstype",
    "apfs_fsid_0",
    "apfs_fsid_1",
    "apfs_mount_flags",
    "sqlite_runtime_version",
    "sqlite_source_id",
    "sqlite_compile_options_hash",
    "sqlite_vfs_name",
    "journal_mode",
    "synchronous",
    "fullfsync",
    "checkpoint_fullfsync",
    "foreign_keys",
    "defensive",
    "trusted_schema",
    "locking_mode",
    "nofollow_available",
    "checkpoint_on_close",
    "state_parent_dev",
    "db_dev",
    "wal_dev",
    "shm_dev",
    "proof_parent_dev",
    "projection_parent_dev",
    "legacy_parent_dev",
    "root_dev",
    "git_dir_dev",
    "git_common_dev",
    "ancestry_hash",
    "descriptor_binding_hash",
}
REQUIRED_PYTHON_APIS = (
    "fcntl.flock",
    "os.O_NOFOLLOW",
    "os.fstat",
    "sqlite3.Connection.setconfig",
    "sqlite3.SQLITE_DBCONFIG_DEFENSIVE",
    "sqlite3.SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE",
)
_CAPABILITY_KEYS = {
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
_EXTERNAL_INTERPRETER_KEYS = {
    "schema",
    "selection_hash",
    "path",
    "path_hash",
    "ancestry_hash",
    "st_uid",
    "st_gid",
    "st_mode",
    "st_dev",
    "st_ino",
    "st_nlink",
    "st_size",
    "content_sha256",
    "capability_probe_hash",
    "probe_program_hash",
}
_INTERPRETER_CAPABILITY_SEAL = object()
_PROFILE_BINDING_SEAL = object()
_TYPED_PROFILE_BINDING_SEAL = object()


class ProfileError(RuntimeError):
    pass


def _authority_hash(domain: str, value: dict) -> str:
    return hashlib.sha256(
        domain.encode("ascii")
        + b"\0"
        + registration_jcs.canonical_bytes(value)
    ).hexdigest()


def _version(value: object, field: str) -> tuple[int, ...]:
    if not isinstance(value, str) or re.fullmatch(
        r"(0|[1-9][0-9]*)(?:\.(0|[1-9][0-9]*)){1,3}", value
    ) is None:
        raise ProfileError(f"{field} must be a canonical dotted version")
    return tuple(int(part) for part in value.split("."))


def python_capability_hash(capability: dict) -> str:
    if set(capability) != _CAPABILITY_KEYS:
        raise ProfileError("python capability key mismatch")
    if capability["schema"] != "awa-registration-python-capability/v1":
        raise ProfileError("python capability schema mismatch")
    if capability["required_python_apis"] != list(REQUIRED_PYTHON_APIS):
        raise ProfileError("python capability API inventory mismatch")
    for field in (
        "fullfsync",
        "checkpoint_fullfsync",
        "foreign_keys",
        "connection_setconfig_available",
        "sqlite_dbconfig_defensive_available",
        "defensive",
        "trusted_schema",
        "nofollow_available",
        "checkpoint_on_close",
    ):
        if type(capability[field]) is not bool:
            raise ProfileError(f"{field} must be boolean")
    for field in ("sqlite_compile_options_hash", "probe_program_hash"):
        if not isinstance(capability[field], str) or _HEX.fullmatch(
            capability[field]
        ) is None:
            raise ProfileError(f"{field} must be lowercase 64-hex")
    for field in (
        "platform",
        "os_build",
        "python_implementation",
        "sqlite_source_id",
        "sqlite_vfs_name",
        "journal_mode",
        "synchronous",
        "locking_mode",
    ):
        if not isinstance(capability[field], str) or not capability[field]:
            raise ProfileError(f"{field} must be nonempty text")
    _version(capability["python_version"], "python_version")
    _version(capability["sqlite_runtime_version"], "sqlite_runtime_version")
    return _authority_hash("awa-registration-python-capability/v1", capability)


@dataclass(frozen=True)
class InterpreterCapability:
    digest: str
    probe_program_hash: str
    python_version: str
    sqlite_runtime_version: str
    _seal: object

    def __post_init__(self) -> None:
        if self._seal is not _INTERPRETER_CAPABILITY_SEAL:
            raise ProfileError(
                "interpreter capability requires a validated probe"
            )


def validate_python_capability(capability: dict) -> InterpreterCapability:
    digest = python_capability_hash(capability)
    supported = (
        capability["platform"] == "darwin"
        and capability["python_implementation"] == "CPython"
        and _version(capability["python_version"], "python_version") >= (3, 12)
        and _version(
            capability["sqlite_runtime_version"], "sqlite_runtime_version"
        )
        >= (3, 51, 3)
        and capability["sqlite_vfs_name"] == "unix"
        and capability["journal_mode"] == "wal"
        and capability["synchronous"] == "full"
        and capability["fullfsync"] is True
        and capability["checkpoint_fullfsync"] is True
        and capability["foreign_keys"] is True
        and capability["connection_setconfig_available"] is True
        and capability["sqlite_dbconfig_defensive_available"] is True
        and capability["defensive"] is True
        and capability["trusted_schema"] is False
        and capability["locking_mode"] == "normal"
        and capability["nofollow_available"] is True
        and capability["checkpoint_on_close"] is False
    )
    if not supported:
        raise ProfileError("python capability is unsupported")
    return InterpreterCapability(
        digest=digest,
        probe_program_hash=capability["probe_program_hash"],
        python_version=capability["python_version"],
        sqlite_runtime_version=capability["sqlite_runtime_version"],
        _seal=_INTERPRETER_CAPABILITY_SEAL,
    )


def _validate_absolute_interpreter_path(value: object) -> str:
    if (
        not isinstance(value, str)
        or value != unicodedata.normalize("NFC", value)
        or not 1 <= len(value.encode("utf-8", "strict")) <= 4096
        or not value.startswith("/")
        or "\\" in value
        or any(ord(character) < 0x20 for character in value)
        or os.path.normpath(value) != value
        or any(part in {"", ".", ".."} for part in value.split("/")[1:])
    ):
        raise ProfileError("invalid interpreter path")
    return value


def external_interpreter_hash(
    record: dict,
    *,
    capability: InterpreterCapability | None = None,
) -> str:
    if set(record) != _EXTERNAL_INTERPRETER_KEYS:
        raise ProfileError("external interpreter key mismatch")
    if record["schema"] != "awa-registration-external-interpreter/v1":
        raise ProfileError("external interpreter schema mismatch")
    path = _validate_absolute_interpreter_path(record["path"])
    expected_path_hash = hashlib.sha256(
        b"awa-registration-interpreter-path/v1\0" + path.encode("utf-8")
    ).hexdigest()
    if record["path_hash"] != expected_path_hash:
        raise ProfileError("external interpreter path hash mismatch")
    for field in (
        "selection_hash",
        "path_hash",
        "ancestry_hash",
        "content_sha256",
        "capability_probe_hash",
        "probe_program_hash",
    ):
        if not isinstance(record[field], str) or _HEX.fullmatch(record[field]) is None:
            raise ProfileError(f"{field} must be lowercase 64-hex")
    for field in (
        "st_uid",
        "st_gid",
        "st_mode",
        "st_dev",
        "st_ino",
        "st_nlink",
        "st_size",
    ):
        _require_decimal(record[field])
    mode = int(record["st_mode"])
    if (
        not stat.S_ISREG(mode)
        or int(record["st_nlink"]) != 1
        or mode & stat.S_IXUSR == 0
        or mode & 0o022
    ):
        raise ProfileError("external interpreter file authority mismatch")
    if capability is not None and (
        record["capability_probe_hash"] != capability.digest
        or record["probe_program_hash"] != capability.probe_program_hash
    ):
        raise ProfileError("external interpreter capability binding mismatch")
    return _authority_hash("awa-registration-external-interpreter/v1", record)


def _sqlite_vfs_probe(path: Path) -> tuple[str, bool]:
    library = ctypes.CDLL(None, use_errno=True)
    database = ctypes.c_void_p()
    library.sqlite3_open_v2.argtypes = [
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_int,
        ctypes.c_char_p,
    ]
    library.sqlite3_open_v2.restype = ctypes.c_int
    flags = 0x00000001 | 0x01000000  # READONLY | NOFOLLOW
    opened = library.sqlite3_open_v2(
        os.fsencode(path),
        ctypes.byref(database),
        flags,
        None,
    )
    if opened != 0:
        if database:
            library.sqlite3_close_v2(database)
        raise ProfileError(
            f"stock SQLite NOFOLLOW probe failed with code {opened}"
        )
    name = ctypes.c_char_p()
    try:
        library.sqlite3_file_control.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_void_p,
        ]
        library.sqlite3_file_control.restype = ctypes.c_int
        result = library.sqlite3_file_control(
            database,
            b"main",
            12,  # SQLITE_FCNTL_VFSNAME
            ctypes.byref(name),
        )
        if result != 0 or not name.value:
            raise ProfileError(
                f"SQLite VFS-name probe failed with code {result}"
            )
        vfs_name = name.value.decode("ascii", "strict").lower()
        return vfs_name, True
    finally:
        if name.value:
            library.sqlite3_free.argtypes = [ctypes.c_void_p]
            library.sqlite3_free(name)
        library.sqlite3_close_v2(database)


def _require_decimal(value: object, *, signed: bool = False) -> None:
    pattern = _SIGNED if signed else _UNSIGNED
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ProfileError("noncanonical decimal field")


def descriptor_binding_hash(records: list[dict]) -> str:
    if len(records) != len(DESCRIPTOR_ROLES):
        raise ProfileError("descriptor role count mismatch")
    for ordinal, (record, role) in enumerate(zip(records, DESCRIPTOR_ROLES)):
        if set(record) != _RECORD_KEYS:
            raise ProfileError("descriptor record key mismatch")
        if record["ordinal"] != str(ordinal) or record["role"] != role:
            raise ProfileError("descriptor role order mismatch")
        if not isinstance(record["component_hash"], str) or _HEX.fullmatch(
            record["component_hash"]
        ) is None:
            raise ProfileError("descriptor component hash mismatch")
        for field in (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_uid",
            "st_gid",
            "st_nlink",
            "fd_flags",
            "mount_flags",
        ):
            _require_decimal(record[field])
        _require_decimal(record["fsid_0"], signed=True)
        _require_decimal(record["fsid_1"], signed=True)
        if not isinstance(record["nofollow"], bool):
            raise ProfileError("descriptor nofollow must be boolean")
        if record["fstype"] != "apfs":
            raise ProfileError("descriptor filesystem must be apfs")
    value = {
        "schema": "awa-registration-descriptor-binding/v1",
        "records": records,
    }
    return hashlib.sha256(
        b"awa-registration-descriptor-binding/v1\0"
        + registration_jcs.canonical_bytes(value)
    ).hexdigest()


def profile_hash(profile: dict) -> str:
    if set(profile) != _PROFILE_KEYS:
        raise ProfileError("profile key mismatch")
    if profile["schema"] != "awa-registration-profile/v2":
        raise ProfileError("profile schema mismatch")
    if profile["measurement_order"] != list(MEASUREMENT_ORDER):
        raise ProfileError("profile measurement order mismatch")
    if profile["platform"] != "darwin" or profile["apfs_fstype"] != "apfs":
        raise ProfileError("unsupported profile platform")
    for field in (
        "fullfsync",
        "checkpoint_fullfsync",
        "foreign_keys",
        "defensive",
        "trusted_schema",
        "nofollow_available",
        "checkpoint_on_close",
    ):
        if not isinstance(profile[field], bool):
            raise ProfileError(f"{field} must be boolean")
    for field in (
        "apfs_mount_flags",
        "state_parent_dev",
        "db_dev",
        "wal_dev",
        "shm_dev",
        "proof_parent_dev",
        "projection_parent_dev",
        "legacy_parent_dev",
        "root_dev",
        "git_dir_dev",
        "git_common_dev",
    ):
        _require_decimal(profile[field])
    for field in ("apfs_fsid_0", "apfs_fsid_1"):
        _require_decimal(profile[field], signed=True)
    for field in (
        "sqlite_compile_options_hash",
        "ancestry_hash",
        "descriptor_binding_hash",
    ):
        if not isinstance(profile[field], str) or _HEX.fullmatch(profile[field]) is None:
            raise ProfileError(f"{field} must be lowercase 64-hex")
    for field in (
        "os_build",
        "sqlite_runtime_version",
        "sqlite_source_id",
        "sqlite_vfs_name",
        "journal_mode",
        "synchronous",
        "locking_mode",
    ):
        if not isinstance(profile[field], str) or not profile[field]:
            raise ProfileError(f"{field} must be nonempty text")
    return hashlib.sha256(
        b"awa-registration-profile/v2\0"
        + registration_jcs.canonical_bytes(profile)
    ).hexdigest()


class _Fsid(ctypes.Structure):
    _fields_ = [("val", ctypes.c_int32 * 2)]


class _DarwinStatFs(ctypes.Structure):
    _fields_ = [
        ("f_bsize", ctypes.c_uint32),
        ("f_iosize", ctypes.c_int32),
        ("f_blocks", ctypes.c_uint64),
        ("f_bfree", ctypes.c_uint64),
        ("f_bavail", ctypes.c_uint64),
        ("f_files", ctypes.c_uint64),
        ("f_ffree", ctypes.c_uint64),
        ("f_fsid", _Fsid),
        ("f_owner", ctypes.c_uint32),
        ("f_type", ctypes.c_uint32),
        ("f_flags", ctypes.c_uint32),
        ("f_fssubtype", ctypes.c_uint32),
        ("f_fstypename", ctypes.c_char * 16),
        ("f_mntonname", ctypes.c_char * 1024),
        ("f_mntfromname", ctypes.c_char * 1024),
        ("f_flags_ext", ctypes.c_uint32),
        ("f_reserved", ctypes.c_uint32 * 7),
    ]


def _fstatfs(fd: int) -> tuple[str, int, int, int]:
    if platform.system() != "Darwin":
        raise ProfileError("M1 requires darwin")
    libc = ctypes.CDLL(None, use_errno=True)
    result = _DarwinStatFs()
    if libc.fstatfs(fd, ctypes.byref(result)) != 0:
        code = ctypes.get_errno()
        raise ProfileError(f"fstatfs failed: {os.strerror(code)}")
    fstype = bytes(result.f_fstypename).split(b"\0", 1)[0].decode("ascii").lower()
    return (
        fstype,
        int(result.f_fsid.val[0]),
        int(result.f_fsid.val[1]),
        int(result.f_flags),
    )


@dataclass
class BoundPath:
    path: Path
    kind: str
    required_mode: int
    fd: int
    parent_fd: int
    name: str
    descriptors: tuple[int, ...]
    identity: tuple[int, int, int, int, int, int]

    def close(self) -> None:
        for descriptor in reversed(self.descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass


def _identity(info: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        int(info.st_dev),
        int(info.st_ino),
        int(info.st_mode),
        int(info.st_uid),
        int(info.st_gid),
        int(info.st_nlink),
    )


def _validate_ancestor(info: os.stat_result) -> None:
    if not stat.S_ISDIR(info.st_mode):
        raise ProfileError("ancestor is not a directory")
    if info.st_uid not in (0, os.geteuid()):
        raise ProfileError("ancestor owner mismatch")
    if info.st_mode & 0o022:
        raise ProfileError("ancestor is group/other writable")


def _validate_final(info: os.stat_result, kind: str, required_mode: int) -> None:
    if info.st_uid != os.geteuid():
        raise ProfileError("bound object owner mismatch")
    if stat.S_IMODE(info.st_mode) != required_mode:
        raise ProfileError("bound object mode mismatch")
    if kind == "file":
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ProfileError("bound file type/link mismatch")
    elif kind == "directory":
        if not stat.S_ISDIR(info.st_mode):
            raise ProfileError("bound directory type mismatch")
    else:
        raise ProfileError("unknown bound path kind")


@contextmanager
def bind_secure_path(
    path: Path, *, kind: str, required_mode: int
) -> Iterator[BoundPath]:
    original = Path(path)
    if not original.is_absolute() or os.path.normpath(str(original)) != str(original):
        raise ProfileError("path must be normalized and absolute")
    canonical = Path(os.path.realpath(original))
    if canonical != original:
        raise ProfileError("path aliases or symlinks are unsupported")
    parts = canonical.parts
    if len(parts) < 2:
        raise ProfileError("root itself cannot be a bound target")
    descriptors: list[int] = []
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    root_fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    descriptors.append(root_fd)
    current_fd = root_fd
    try:
        _validate_ancestor(os.fstat(current_fd))
        for component in parts[1:-1]:
            next_fd = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | nofollow,
                dir_fd=current_fd,
            )
            descriptors.append(next_fd)
            current_fd = next_fd
            _validate_ancestor(os.fstat(current_fd))
        flags = os.O_RDONLY | nofollow
        if kind == "directory":
            flags |= os.O_DIRECTORY
        final_fd = os.open(parts[-1], flags, dir_fd=current_fd)
        descriptors.append(final_fd)
        info = os.fstat(final_fd)
        _validate_final(info, kind, required_mode)
        bound = BoundPath(
            path=canonical,
            kind=kind,
            required_mode=required_mode,
            fd=final_fd,
            parent_fd=current_fd,
            name=parts[-1],
            descriptors=tuple(descriptors),
            identity=_identity(info),
        )
        recheck_bound_path(bound)
        yield bound
    except OSError as exc:
        raise ProfileError(f"descriptor walk failed: {exc}") from exc
    finally:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass


def recheck_bound_path(bound: BoundPath) -> None:
    descriptor_info = os.fstat(bound.fd)
    try:
        path_info = os.stat(
            bound.name, dir_fd=bound.parent_fd, follow_symlinks=False
        )
    except OSError as exc:
        raise ProfileError("bound path disappeared") from exc
    _validate_final(descriptor_info, bound.kind, bound.required_mode)
    _validate_final(path_info, bound.kind, bound.required_mode)
    if _identity(descriptor_info) != bound.identity or _identity(path_info) != bound.identity:
        raise ProfileError("bound object identity changed")


@dataclass(frozen=True)
class DescriptorMeasurement:
    records: list[dict]
    fstype: str
    fsid_0: int
    fsid_1: int
    mount_flags: int
    st_dev: int
    digest: str


def measure_bound_targets(
    targets: list[tuple[str, Path, str, int]]
) -> DescriptorMeasurement:
    if tuple(role for role, *_ in targets) != DESCRIPTOR_ROLES:
        raise ProfileError("descriptor target order mismatch")
    records: list[dict] = []
    expected: tuple[str, int, int, int] | None = None
    expected_dev: int | None = None
    with ExitStack() as stack:
        bounds = [
            stack.enter_context(
                bind_secure_path(
                    path, kind=kind, required_mode=mode
                )
            )
            for _role, path, kind, mode in targets
        ]
        for ordinal, ((role, _path, _kind, _mode), bound) in enumerate(
            zip(targets, bounds)
        ):
            recheck_bound_path(bound)
            info = os.fstat(bound.fd)
            fs = _fstatfs(bound.fd)
            if fs[0] != "apfs":
                raise ProfileError("M1 requires APFS")
            if expected is None:
                expected = fs
                expected_dev = int(info.st_dev)
            if fs[:3] != expected[:3] or int(info.st_dev) != expected_dev:
                raise ProfileError("device/APFS tuple mismatch")
            records.append(
                {
                    "ordinal": str(ordinal),
                    "role": role,
                    "component_hash": hashlib.sha256(
                        b"awa-registration-component/v1\0"
                        + role.encode("ascii")
                    ).hexdigest(),
                    "st_dev": str(info.st_dev),
                    "st_ino": str(info.st_ino),
                    "st_mode": str(info.st_mode),
                    "st_uid": str(info.st_uid),
                    "st_gid": str(info.st_gid),
                    "st_nlink": str(info.st_nlink),
                    "fd_flags": str(fcntl.fcntl(bound.fd, fcntl.F_GETFL)),
                    "nofollow": bool(getattr(os, "O_NOFOLLOW", 0)),
                    "fstype": fs[0],
                    "fsid_0": str(fs[1]),
                    "fsid_1": str(fs[2]),
                    "mount_flags": str(fs[3]),
                }
            )
        for bound in bounds:
            recheck_bound_path(bound)
    assert expected is not None and expected_dev is not None
    return DescriptorMeasurement(
        records=records,
        fstype=expected[0],
        fsid_0=expected[1],
        fsid_1=expected[2],
        mount_flags=expected[3],
        st_dev=expected_dev,
        digest=descriptor_binding_hash(records),
    )


def free_bytes_for_fd(fd: int) -> int:
    values = os.fstatvfs(fd)
    return int(values.f_bavail) * int(values.f_frsize)


@dataclass(frozen=True)
class ProfileBinding:
    targets: tuple[tuple[str, Path, str, int], ...]
    descriptor_digest: str
    profile_object: dict
    digest: str
    storage_dev: int
    _seal: object

    def __post_init__(self) -> None:
        if self._seal is not _PROFILE_BINDING_SEAL:
            raise ProfileError("profile binding requires live measurement")
        if (
            tuple(role for role, *_rest in self.targets) != DESCRIPTOR_ROLES
            or self.profile_object.get("descriptor_binding_hash")
            != self.descriptor_digest
            or profile_hash(self.profile_object) != self.digest
            or type(self.storage_dev) is not int
            or self.storage_dev < 0
        ):
            raise ProfileError("profile binding measurement is inconsistent")

    @classmethod
    def measure(
        cls,
        connection: sqlite3.Connection,
        targets: list[tuple[str, Path, str, int]],
    ) -> "ProfileBinding":
        measurement = measure_bound_targets(targets)
        compile_options = sorted(
            {
                str(row[0])
                for row in connection.execute("PRAGMA compile_options").fetchall()
            },
            key=lambda value: value.encode("utf-8"),
        )
        compile_hash = hashlib.sha256(
            "".join(f"{value}\n" for value in compile_options).encode("utf-8")
        ).hexdigest()
        ancestry_hash = hashlib.sha256(
            b"awa-registration-ancestry/v1\0"
            + registration_jcs.canonical_bytes(
                {
                    "schema": "awa-registration-ancestry/v1",
                    "records": [
                        {
                            key: record[key]
                            for key in (
                                "ordinal",
                                "st_uid",
                                "st_mode",
                                "st_dev",
                                "st_ino",
                                "st_nlink",
                            )
                        }
                        for record in measurement.records
                    ],
                }
            )
        ).hexdigest()
        dev_by_role = {
            record["role"]: record["st_dev"] for record in measurement.records
        }
        db_path = next(
            path for role, path, _kind, _mode in targets if role == "db"
        )
        vfs_name, nofollow_available = _sqlite_vfs_probe(db_path)
        source_id = str(
            connection.execute("SELECT sqlite_source_id()").fetchone()[0]
        )
        profile = {
            "schema": "awa-registration-profile/v2",
            "measurement_order": list(MEASUREMENT_ORDER),
            "platform": "darwin",
            "os_build": platform.platform(),
            "apfs_fstype": measurement.fstype,
            "apfs_fsid_0": str(measurement.fsid_0),
            "apfs_fsid_1": str(measurement.fsid_1),
            "apfs_mount_flags": str(measurement.mount_flags),
            "sqlite_runtime_version": sqlite3.sqlite_version,
            "sqlite_source_id": source_id,
            "sqlite_compile_options_hash": compile_hash,
            "sqlite_vfs_name": vfs_name,
            "journal_mode": str(
                connection.execute("PRAGMA journal_mode").fetchone()[0]
            ).lower(),
            "synchronous": (
                "full"
                if int(connection.execute("PRAGMA synchronous").fetchone()[0])
                == 2
                else "unsupported"
            ),
            "fullfsync": bool(
                connection.execute("PRAGMA fullfsync").fetchone()[0]
            ),
            "checkpoint_fullfsync": bool(
                connection.execute("PRAGMA checkpoint_fullfsync").fetchone()[0]
            ),
            "foreign_keys": bool(
                connection.execute("PRAGMA foreign_keys").fetchone()[0]
            ),
            "defensive": bool(
                connection.getconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE)
            ),
            "trusted_schema": bool(
                connection.execute("PRAGMA trusted_schema").fetchone()[0]
            ),
            "locking_mode": str(
                connection.execute("PRAGMA locking_mode").fetchone()[0]
            ).lower(),
            "nofollow_available": nofollow_available,
            "checkpoint_on_close": not bool(
                connection.getconfig(
                    sqlite3.SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE
                )
            ),
            "state_parent_dev": dev_by_role["state_parent"],
            "db_dev": dev_by_role["db"],
            "wal_dev": dev_by_role["wal"],
            "shm_dev": dev_by_role["shm"],
            "proof_parent_dev": dev_by_role["proof_parent"],
            "projection_parent_dev": dev_by_role["projection_parent"],
            "legacy_parent_dev": dev_by_role["legacy_parent"],
            "root_dev": dev_by_role["root"],
            "git_dir_dev": dev_by_role["git_dir"],
            "git_common_dev": dev_by_role["git_common"],
            "ancestry_hash": ancestry_hash,
            "descriptor_binding_hash": measurement.digest,
        }
        digest = profile_hash(profile)
        return cls(
            targets=tuple(targets),
            descriptor_digest=measurement.digest,
            profile_object=profile,
            digest=digest,
            storage_dev=measurement.st_dev,
            _seal=_PROFILE_BINDING_SEAL,
        )

    def recheck(self, connection: sqlite3.Connection) -> int:
        current = ProfileBinding.measure(connection, list(self.targets))
        if (
            current.descriptor_digest != self.descriptor_digest
            or current.digest != self.digest
            or current.storage_dev != self.storage_dev
        ):
            raise ProfileError("profile/descriptor identity changed")
        state_parent = next(
            path for role, path, _kind, _mode in self.targets if role == "state_parent"
        )
        with bind_secure_path(
            state_parent, kind="directory", required_mode=0o700
        ) as bound:
            return free_bytes_for_fd(bound.fd)


@dataclass(frozen=True)
class TypedProfileBinding:
    profile: ProfileBinding
    interpreter_capability: InterpreterCapability
    external_interpreter_digest: str
    capability_bytes: bytes
    external_interpreter_bytes: bytes
    _seal: object
    role: ClassVar[str] = "UNSPECIFIED"

    def __post_init__(self) -> None:
        if self._seal is not _TYPED_PROFILE_BINDING_SEAL:
            raise ProfileError("typed profile requires validated bindings")
        if self.role not in {"CURRENT", "STAGED", "R0"}:
            raise ProfileError("unknown typed profile role")
        if not isinstance(self.profile, ProfileBinding):
            raise ProfileError("typed profile requires measured profile")
        if not isinstance(self.interpreter_capability, InterpreterCapability):
            raise ProfileError("typed profile requires interpreter capability")
        if _HEX.fullmatch(self.external_interpreter_digest) is None:
            raise ProfileError("typed profile interpreter hash mismatch")
        try:
            capability_object = registration_jcs.parse_canonical(
                self.capability_bytes
            )
            external_interpreter = registration_jcs.parse_canonical(
                self.external_interpreter_bytes
            )
        except registration_jcs.JcsError as error:
            raise ProfileError("typed profile evidence is invalid") from error
        if (
            not isinstance(capability_object, dict)
            or not isinstance(external_interpreter, dict)
            or validate_python_capability(capability_object)
            != self.interpreter_capability
            or external_interpreter_hash(
                external_interpreter,
                capability=self.interpreter_capability,
            )
            != self.external_interpreter_digest
        ):
            raise ProfileError("typed profile evidence mismatch")

    @classmethod
    def bind(
        cls,
        profile: ProfileBinding,
        capability_object: dict,
        external_interpreter: dict,
    ) -> "TypedProfileBinding":
        capability = validate_python_capability(capability_object)
        interpreter_digest = external_interpreter_hash(
            external_interpreter, capability=capability
        )
        return cls(
            profile,
            capability,
            interpreter_digest,
            registration_jcs.canonical_bytes(capability_object),
            registration_jcs.canonical_bytes(external_interpreter),
            _TYPED_PROFILE_BINDING_SEAL,
        )

    @property
    def digest(self) -> str:
        return self.profile.digest

    @property
    def storage_dev(self) -> int:
        return self.profile.storage_dev

    def recheck(
        self,
        connection: sqlite3.Connection,
        capability_object: dict | None = None,
        external_interpreter: dict | None = None,
    ) -> int:
        if (capability_object is None) != (external_interpreter is None):
            raise ProfileError(
                "interpreter capability recheck evidence is incomplete"
            )
        if capability_object is None:
            parsed_capability = registration_jcs.parse_canonical(
                self.capability_bytes
            )
            parsed_external = registration_jcs.parse_canonical(
                self.external_interpreter_bytes
            )
            if not isinstance(parsed_capability, dict) or not isinstance(
                parsed_external, dict
            ):
                raise ProfileError("typed profile evidence is invalid")
            capability_object = parsed_capability
            external_interpreter = parsed_external
        assert external_interpreter is not None
        capability = validate_python_capability(capability_object)
        interpreter_digest = external_interpreter_hash(
            external_interpreter, capability=capability
        )
        if (
            capability != self.interpreter_capability
            or interpreter_digest != self.external_interpreter_digest
        ):
            raise ProfileError("interpreter capability changed")
        return self.profile.recheck(connection)


class CurrentProfileBinding(TypedProfileBinding):
    role = "CURRENT"

    @classmethod
    def promote(
        cls, binding: "StagedProfileBinding"
    ) -> "CurrentProfileBinding":
        if type(binding) is not StagedProfileBinding:
            raise ProfileError("only a staged profile can become current")
        return cls(
            binding.profile,
            binding.interpreter_capability,
            binding.external_interpreter_digest,
            binding.capability_bytes,
            binding.external_interpreter_bytes,
            _TYPED_PROFILE_BINDING_SEAL,
        )


class StagedProfileBinding(TypedProfileBinding):
    role = "STAGED"


class R0ProfileBinding(TypedProfileBinding):
    role = "R0"


PRIVATE_RUNTIME_SOURCE_LOCK_SHA256 = (
    "a8b1415067e7b33c18ccc3c1d42e19ae27a9ad5784a7f294fffc562083762d72"
)
_PRIVATE_RUNTIME_BINDING_FIELDS = {
    "schema",
    "current_digest",
    "epoch",
    "runtime_manifest_sha256",
    "runtime_release_envelope_digest",
    "source_lock_sha256",
    "private_executable_path",
    "private_executable_sha256",
    "version_lock_identity",
    "capability_digest",
    "sqlite_compile_options_hash",
}


def validate_private_python_capability(
    capability: dict,
) -> InterpreterCapability:
    """Validate the exact v7 runtime profile, never a caller-selected Python."""

    result = validate_python_capability(capability)
    exact = (
        capability["platform"] == "darwin"
        and capability["python_implementation"] == "CPython"
        and capability["python_version"] == "3.14.8"
        and capability["sqlite_runtime_version"] == "3.53.1"
        and capability["required_python_apis"]
        == list(REQUIRED_PYTHON_APIS)
    )
    if not exact:
        raise ProfileError("private runtime capability differs from v7 source lock")
    if len(capability["os_build"].encode("utf-8")) > 128:
        raise ProfileError("private runtime OS build is too long")
    if len(capability["sqlite_source_id"].encode("utf-8")) > 512:
        raise ProfileError("private runtime SQLite source ID is too long")
    return result


@dataclass(frozen=True)
class PrivateRuntimeProfileBinding:
    schema: str
    current_digest: str
    epoch: str
    runtime_manifest_sha256: str
    runtime_release_envelope_digest: str
    source_lock_sha256: str
    private_executable_path: str
    private_executable_sha256: str
    version_lock_identity: str
    capability_digest: str
    sqlite_compile_options_hash: str

    def __post_init__(self) -> None:
        if self.schema != "awa-registration-private-runtime-profile/v1":
            raise ProfileError("private runtime profile schema mismatch")
        if (
            not isinstance(self.epoch, str)
            or _UNSIGNED.fullmatch(self.epoch) is None
            or int(self.epoch) < 1
        ):
            raise ProfileError("private runtime epoch must be positive")
        for name in _PRIVATE_RUNTIME_BINDING_FIELDS - {
            "schema",
            "epoch",
            "private_executable_path",
        }:
            value = getattr(self, name)
            if not isinstance(value, str) or _HEX.fullmatch(value) is None:
                raise ProfileError(f"{name} must be lowercase 64-hex")
        if self.source_lock_sha256 != PRIVATE_RUNTIME_SOURCE_LOCK_SHA256:
            raise ProfileError("private runtime source lock mismatch")
        expected_prefix = "/Library/Application Support/AWA/runtime/versions/"
        if not self.private_executable_path.startswith(expected_prefix):
            raise ProfileError("private executable is outside protected runtime")
        suffix = self.private_executable_path[len(expected_prefix) :]
        parts = suffix.split("/")
        if (
            len(parts) != 5
            or _HEX.fullmatch(parts[0]) is None
            or parts[1:] != ["Python.app", "Contents", "MacOS", "Python"]
            or parts[0] != self.runtime_manifest_sha256
        ):
            raise ProfileError("private executable path/manifest mismatch")

    @classmethod
    def from_mapping(
        cls, value: dict
    ) -> "PrivateRuntimeProfileBinding":
        if set(value) != _PRIVATE_RUNTIME_BINDING_FIELDS:
            raise ProfileError("private runtime profile field mismatch")
        return cls(**value)

    def to_mapping(self) -> dict[str, str]:
        return {
            field.name: getattr(self, field.name) for field in fields(self)
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            b"awa-registration-private-runtime-profile/v1\0"
            + registration_jcs.canonical_bytes(self.to_mapping())
            + b"\n"
        ).hexdigest()


def bind_measured_private_runtime(
    *,
    measurement: dict,
    capability: dict,
) -> PrivateRuntimeProfileBinding:
    """Bind only a bootstrap-produced measurement and exact capability."""

    binding = PrivateRuntimeProfileBinding.from_mapping(measurement)
    measured_capability = validate_private_python_capability(capability)
    if measured_capability.digest != binding.capability_digest:
        raise ProfileError("private runtime measurement/capability mismatch")
    if (
        capability["sqlite_compile_options_hash"]
        != binding.sqlite_compile_options_hash
    ):
        raise ProfileError("private runtime compile-options mismatch")
    return binding
