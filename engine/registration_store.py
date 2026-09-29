"""Transactional ADR 0025 registration authority (Body A).

This module owns the dedicated seven-table store, authenticated BOOTSTRAP and
CONTROL capabilities, DATA capability boundary, fresh write preflight, and
operation-envelope framing. Product routing and hook admission live outside
Body A.
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

from . import (
    identity,
    paths,
    registration_clock,
    registration_executor,
    registration_hashes,
    registration_jcs,
    registration_lock,
    registration_profile,
    registration_schema,
)


SCHEMA_SHA256 = registration_schema.SCHEMA_SHA256
FILESYSTEM_SAFETY_FLOOR = 1024**3
MAX_CONTROL_RESERVE = 14 * 1024**2
MIN_SQLITE_VERSION = (3, 51, 3)
ZERO_HASH = "0" * 64
PROJECTED_DB_BYTES = {
    "BOOTSTRAP": 1024**2,
    "INSTALL_MEMBER": 32 * 1024,
    "BIND_EPISODE": 8 * 1024,
    "REACQUIRE_EFFECT": 8 * 1024,
    "OPEN_EFFECT": 16 * 1024,
    "APPEND_ACTION": 8 * 1024,
    "CLOSE_SUCCESS": 16 * 1024,
    "CLOSE_CONFLICT": 16 * 1024,
    "INVALIDATE_REQUESTED": 32 * 1024,
    "SET_PENDING": 24 * 1024,
    "REPLACE_PENDING": 32 * 1024,
    "HANDOFF_RESOLVED": 32 * 1024,
    "MARK_UNAVAILABLE": 8 * 1024,
    "REBOOT_STATUS": 8 * 1024,
    "SCHEDULE_STATUS": 8 * 1024,
    "ACTIVATE": 16 * 1024,
    "BEGIN_DRAIN": 16 * 1024,
    "STAGE_NEXT": 16 * 1024,
    "CANCEL_DRAIN": 16 * 1024,
    "ADOPT_EFFECT": 64 * 1024,
    "ADVANCE_GENERATION": 16 * 1024,
    "PRE_EFFECT_DORMANT": 16 * 1024,
    "ENTER_CONTAINMENT": 16 * 1024,
    "BEGIN_REPAIR": 16 * 1024,
}

_PROTOCOL_COLUMNS = registration_hashes.PREIMAGES["protocol_hash"].columns
_OPERATION_COLUMNS = registration_hashes.PREIMAGES[
    "operation_envelope_hash"
].columns


class StoreError(RuntimeError):
    pass


class AuthorizationError(StoreError):
    pass


class InsufficientSpace(StoreError):
    pass


class StaleAuthority(StoreError):
    pass


class StoreUnavailable(StoreError):
    pass


class InjectedSQLiteFault(sqlite3.OperationalError):
    def __init__(self, code: int) -> None:
        if code not in {sqlite3.SQLITE_FULL, sqlite3.SQLITE_IOERR}:
            raise ValueError("only SQLITE_FULL/SQLITE_IOERR are injectable")
        super().__init__(
            "database or disk is full"
            if code == sqlite3.SQLITE_FULL
            else "disk I/O error"
        )
        self.sqlite_errorcode = code
        self.sqlite_errorname = (
            "SQLITE_FULL" if code == sqlite3.SQLITE_FULL else "SQLITE_IOERR"
        )


@dataclass(frozen=True)
class ProtocolCandidate:
    profile_hash: str
    runtime_capability_hash: str
    writer_binary_hash: str
    writer_capability_hash: str
    tool_inventory_hash: str
    hook_projection_hash: str
    hook_matcher_mode: str
    hook_matcher_hash: str
    projection_receipt_hash: str
    projection_file_generation: int
    installer_identity_hash: str
    installer_capability_hash: str
    storage_dev: int

    def __post_init__(self) -> None:
        for field in (
            "profile_hash",
            "runtime_capability_hash",
            "writer_binary_hash",
            "writer_capability_hash",
            "tool_inventory_hash",
            "hook_projection_hash",
            "hook_matcher_hash",
            "projection_receipt_hash",
            "installer_identity_hash",
            "installer_capability_hash",
        ):
            value = getattr(self, field)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(char not in "0123456789abcdef" for char in value)
            ):
                raise ValueError(f"{field} must be lowercase 64-hex")
        if self.hook_matcher_mode not in {"CATCH_ALL", "ENUMERATED"}:
            raise ValueError("invalid hook matcher mode")
        if self.projection_file_generation < 1 or self.storage_dev < 0:
            raise ValueError("invalid candidate generation/device")


_CONTROL_SEAL = object()
_DATA_SEAL = object()
_EXECUTION_SEAL = object()
_TEST_PROFILE_SEAL = object()
_CREATION_LOCK_SEAL = object()


class ControlCapability:
    __slots__ = (
        "installer_identity_hash",
        "installer_capability_hash",
        "protocol_lock_receipt_hash",
        "control_binding_hash",
        "_seal",
    )

    def __init__(
        self,
        *,
        installer_identity_hash: str,
        installer_capability_hash: str,
        protocol_lock_receipt_hash: str,
        control_binding_hash: str,
        _seal: object,
    ) -> None:
        if _seal is not _CONTROL_SEAL:
            raise AuthorizationError("CONTROL capability is installer-authenticated")
        object.__setattr__(self, "installer_identity_hash", installer_identity_hash)
        object.__setattr__(
            self, "installer_capability_hash", installer_capability_hash
        )
        object.__setattr__(
            self, "protocol_lock_receipt_hash", protocol_lock_receipt_hash
        )
        object.__setattr__(self, "control_binding_hash", control_binding_hash)
        object.__setattr__(self, "_seal", _seal)

    def __setattr__(self, _name: str, _value: object) -> None:
        raise AuthorizationError("CONTROL capability is immutable")


class DataCapability:
    __slots__ = ("writer_capability_hash", "_seal")

    def __init__(self, writer_capability_hash: str, *, _seal: object) -> None:
        if _seal is not _DATA_SEAL:
            raise AuthorizationError("DATA capability is writer-authenticated")
        object.__setattr__(self, "writer_capability_hash", writer_capability_hash)
        object.__setattr__(self, "_seal", _seal)

    def __setattr__(self, _name: str, _value: object) -> None:
        raise AuthorizationError("DATA capability is immutable")


def _domain_hash(domain: str, value: bytes) -> str:
    return hashlib.sha256(domain.encode("ascii") + b"\0" + value).hexdigest()


def authenticate_control(
    *,
    installer_identity: bytes,
    installer_capability: bytes,
    protocol_lock_receipt: bytes,
    control_binding: bytes,
    expected_identity_hash: str,
    expected_capability_hash: str,
) -> ControlCapability:
    identity_hash = _domain_hash(
        "awa-registration-installer-identity/v1", installer_identity
    )
    capability_hash = _domain_hash(
        "awa-registration-installer-capability/v1", installer_capability
    )
    if not secrets.compare_digest(identity_hash, expected_identity_hash):
        raise AuthorizationError("installer identity mismatch")
    if not secrets.compare_digest(capability_hash, expected_capability_hash):
        raise AuthorizationError("installer capability mismatch")
    return ControlCapability(
        installer_identity_hash=identity_hash,
        installer_capability_hash=capability_hash,
        protocol_lock_receipt_hash=_domain_hash(
            "awa-registration-protocol-lock/v1", protocol_lock_receipt
        ),
        control_binding_hash=_domain_hash(
            "awa-registration-control-binding/v1", control_binding
        ),
        _seal=_CONTROL_SEAL,
    )


def authenticate_data(
    writer_capability: bytes, expected_writer_capability_hash: str
) -> DataCapability:
    value = _domain_hash(
        "awa-registration-writer-capability/v1", writer_capability
    )
    if not secrets.compare_digest(value, expected_writer_capability_hash):
        raise AuthorizationError("writer capability mismatch")
    return DataCapability(value, _seal=_DATA_SEAL)


@dataclass(frozen=True)
class OperationResult:
    disposition: str
    operation_id: str
    operation_hash: str
    target_hash: str


class MemberExecution:
    """Opaque, non-serializable post-commit helper-I/O authority."""

    __slots__ = (
        "_store_identity",
        "_member_lock",
        "_secret",
        "member_id",
        "effect_id",
        "executor_token_hash",
        "operation_id",
        "target_member_hash",
        "target_effect_hash",
        "target_status_hash",
        "target_protocol_hash",
        "target_staged_epoch_hash",
        "_sealed",
    )

    def __init__(
        self,
        *,
        store_identity: int,
        member_lock: registration_lock.HeldLock,
        secret: bytes,
        member_id: str,
        effect_id: str,
        executor_token_hash: str,
        operation_id: str,
        target_member_hash: str,
        target_effect_hash: str,
        target_status_hash: str,
        target_protocol_hash: str,
        target_staged_epoch_hash: str | None = None,
        _seal: object,
    ) -> None:
        if _seal is not _EXECUTION_SEAL:
            raise AuthorizationError(
                "executor capability requires a committed granting operation"
            )
        if (
            _domain_hash("awa-registration-executor/v1", secret)
            != executor_token_hash
        ):
            raise AuthorizationError("executor secret/token mismatch")
        self._store_identity = store_identity
        self._member_lock = member_lock
        self._secret = bytearray(secret)
        self.member_id = member_id
        self.effect_id = effect_id
        self.executor_token_hash = executor_token_hash
        self.operation_id = operation_id
        self.target_member_hash = target_member_hash
        self.target_effect_hash = target_effect_hash
        self.target_status_hash = target_status_hash
        self.target_protocol_hash = target_protocol_hash
        self.target_staged_epoch_hash = target_staged_epoch_hash
        object.__setattr__(self, "_sealed", True)

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_sealed", False):
            raise AuthorizationError("executor capability is immutable")
        object.__setattr__(self, name, value)

    @property
    def held(self) -> bool:
        return self._member_lock.held

    def verify_owner(self, store: "RegistrationStore") -> None:
        if self._store_identity != id(store) or not self.held:
            raise AuthorizationError("executor capability is not live for this store")
        self._member_lock.verify()

    def close(self) -> None:
        for index in range(len(self._secret)):
            self._secret[index] = 0
        self._member_lock.release()

    def transfer_staged(
        self, transfer: registration_executor.StagedSecretTransfer
    ) -> None:
        if not self.held:
            raise AuthorizationError("executor capability is not live")
        payload = bytearray(self._secret)
        transfer.send(payload, self.executor_token_hash)
        for index in range(len(self._secret)):
            self._secret[index] = 0

    def __enter__(self) -> "MemberExecution":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def __reduce__(self) -> object:
        raise TypeError("executor capability is non-serializable")


@dataclass(frozen=True)
class ExecutionResult:
    operation: OperationResult
    execution: MemberExecution


@dataclass(frozen=True)
class SelectedAuthority:
    protocol: dict[str, Any]
    member: dict[str, Any]
    status: dict[str, Any]
    effect: dict[str, Any]
    actions: tuple[dict[str, Any], ...]
    episodes: tuple[dict[str, Any], ...]
    revision_token: tuple[Any, ...]


@dataclass(frozen=True)
class DueCandidate:
    member_id: str
    member_epoch: int
    phase: str
    effect_id: str
    member_tuple_hash: str
    effect_tuple_hash: str
    status_hash: str
    current_basis_hash: str
    pending_basis_hash: str | None
    due_since_mono_ns: int
    observed_now_mono_ns: int


@dataclass(frozen=True)
class RebootCandidate:
    member_id: str
    phase: str
    effect_id: str
    status_hash: str
    stored_boot_id: str


@dataclass(frozen=True)
class MemberIdentity:
    canonical_root: str
    root_dev: int
    root_ino: int
    git_toplevel: str
    git_dir: str
    git_dir_dev: int
    git_dir_ino: int
    git_common_dir: str
    git_common_dev: int
    git_common_ino: int
    proof_dev: int
    projection_dev: int
    legacy_state_dev: int
    physical_basis_hash: str
    git_basis_hash: str
    policy_basis_hash: str
    operation_basis_hash: str
    lifecycle_basis_hash: str
    current_basis_hash: str

    def __post_init__(self) -> None:
        for field in (
            "canonical_root",
            "git_toplevel",
            "git_dir",
            "git_common_dir",
        ):
            value = getattr(self, field)
            if (
                not isinstance(value, str)
                or not value.startswith("/")
                or "\x00" in value
                or len(value.encode("utf-8")) > 4096
                or os.path.normpath(value) != value
            ):
                raise ValueError(f"{field} must be an absolute path")
        devices = {
            self.root_dev,
            self.git_dir_dev,
            self.git_common_dev,
            self.proof_dev,
            self.projection_dev,
            self.legacy_state_dev,
        }
        if (
            any(isinstance(value, bool) or not isinstance(value, int) for value in devices)
            or len(devices) != 1
            or min(devices) < 0
        ):
            raise ValueError("member identity must be same-device")
        for field in ("root_ino", "git_dir_ino", "git_common_ino"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field} must be a nonnegative integer")
        for field in (
            "physical_basis_hash",
            "git_basis_hash",
            "policy_basis_hash",
            "operation_basis_hash",
            "lifecycle_basis_hash",
            "current_basis_hash",
        ):
            _require_hash(getattr(self, field), field)


@dataclass(frozen=True)
class ActionSpec:
    kind: str
    action_hash: str
    postcondition_hash: str

    def __post_init__(self) -> None:
        _require_hash(self.action_hash, "action_hash")
        _require_hash(self.postcondition_hash, "postcondition_hash")


@dataclass(frozen=True)
class EffectIntent:
    request_kind: str
    request_basis_hash: str
    actions: tuple[ActionSpec, ...]
    external_growth_reservation_bytes: int
    outcome_reservation_bytes: int
    successor_reservation_bytes: int
    blocked_basis_fingerprint: str | None = None

    def __post_init__(self) -> None:
        _require_hash(self.request_basis_hash, "request_basis_hash")
        if self.request_kind == "CLEAN_ELIGIBLE":
            if tuple(action.kind for action in self.actions) != (
                "PUBLISH_EFFECT_PROOF",
                "CONVERGE_LEGACY_LEASE",
                "CONVERGE_LEGACY_LIFECYCLE",
                "COLLECT_FINAL_BASIS",
            ):
                raise ValueError("clean effect must carry the exact four actions")
            if self.actions[3].postcondition_hash != self.request_basis_hash:
                raise ValueError(
                    "COLLECT_FINAL_BASIS must bind the request basis"
                )
            if self.blocked_basis_fingerprint is not None:
                raise ValueError("clean effect cannot carry blocked fingerprint")
        elif self.request_kind in {"BLOCKED_DIRTY", "BLOCKED_OPERATION"}:
            if self.actions or self.external_growth_reservation_bytes != 0:
                raise ValueError("blocked effect cannot reserve external actions")
            _require_hash(
                self.blocked_basis_fingerprint, "blocked_basis_fingerprint"
            )
        else:
            raise ValueError("unknown request kind")
        if not 0 <= self.external_growth_reservation_bytes <= 16 * 1024**2:
            raise ValueError("external reservation out of bounds")
        if not 1 <= self.outcome_reservation_bytes <= 1024**2:
            raise ValueError("outcome reservation out of bounds")
        if not 1 <= self.successor_reservation_bytes <= 1024**2:
            raise ValueError("successor reservation out of bounds")


_PROVENANCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


@dataclass(frozen=True)
class EpisodeSource:
    conversation_id: str
    generation_id: str
    source_contract: str
    source_event: str
    workspace_roots_hash: str

    def __post_init__(self) -> None:
        if _PROVENANCE.fullmatch(self.conversation_id) is None:
            raise ValueError("invalid conversation_id")
        if _PROVENANCE.fullmatch(self.generation_id) is None:
            raise ValueError("invalid generation_id")
        for field in ("source_contract", "source_event"):
            value = getattr(self, field)
            if (
                not isinstance(value, str)
                or not 1 <= len(value.encode("utf-8")) <= 128
                or "\x00" in value
            ):
                raise ValueError(f"invalid {field}")
        registration_jcs.canonical_bytes(
            {
                "source_contract": self.source_contract,
                "source_event": self.source_event,
            }
        )
        _require_hash(self.workspace_roots_hash, "workspace_roots_hash")


@dataclass(frozen=True)
class BasisUpdate:
    policy_basis_hash: str
    operation_basis_hash: str
    lifecycle_basis_hash: str
    current_basis_hash: str

    def __post_init__(self) -> None:
        for field in (
            "policy_basis_hash",
            "operation_basis_hash",
            "lifecycle_basis_hash",
            "current_basis_hash",
        ):
            _require_hash(getattr(self, field), field)


def _require_hash(value: object, field: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ValueError(f"{field} must be lowercase 64-hex")


class RegistrationStore:
    """One connection with a deny-by-default SQLite authorizer."""

    @classmethod
    def open_default(
        cls,
        *,
        profile_targets: list[tuple[str, Path, str, int]],
    ) -> "RegistrationStore":
        return cls(
            paths.registration_db_path(),
            profile_targets=profile_targets,
        )

    @classmethod
    def create_supported(
        cls,
        db_path: Path,
        *,
        profile_targets: list[tuple[str, Path, str, int]],
        control: ControlCapability,
    ) -> "RegistrationStore":
        manager = registration_lock.LockManager(Path(db_path).parent / "locks")
        with manager.acquire_protocol() as held:
            held.verify()
            return cls(
                db_path,
                profile_targets=profile_targets,
                _creation_control=control,
                _creation_lock_seal=_CREATION_LOCK_SEAL,
            )

    def __init__(
        self,
        db_path: Path,
        *,
        free_bytes: Callable[[int], int] | None = None,
        wall_ns: Callable[[], int] = time.time_ns,
        operation_ids: Callable[[], str] | None = None,
        boot_id: Callable[[], str] = identity.boot_id,
        mono_ns: Callable[[], int] = registration_clock.mach_continuous_time_ns,
        fault: Callable[[str], None] | None = None,
        profile_targets: list[tuple[str, Path, str, int]] | None = None,
        _test_profile_seal: object | None = None,
        _creation_control: ControlCapability | None = None,
        _creation_lock_seal: object | None = None,
    ) -> None:
        if sqlite3.sqlite_version_info < MIN_SQLITE_VERSION:
            raise StoreUnavailable(
                f"SQLite {sqlite3.sqlite_version} is below 3.51.3"
            )
        if not hasattr(sqlite3.Connection, "setconfig") or not all(
            hasattr(sqlite3, name)
            for name in (
                "SQLITE_DBCONFIG_DEFENSIVE",
                "SQLITE_DBCONFIG_TRUSTED_SCHEMA",
                "SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE",
            )
        ):
            raise StoreUnavailable(
                "SQLite defensive configuration controls are unavailable"
            )
        self.db_path = Path(db_path)
        if profile_targets is not None:
            self._validate_profile_targets(profile_targets)
        allow_test_profile = _test_profile_seal is _TEST_PROFILE_SEAL
        if _test_profile_seal is not None and not allow_test_profile:
            raise AuthorizationError("invalid test-profile capability")
        if free_bytes is None and profile_targets is None:
            raise StoreUnavailable("a supported profile or test harness is required")
        if allow_test_profile and free_bytes is None:
            raise StoreUnavailable("test profile needs a free-space provider")
        self._free_bytes = free_bytes
        self._wall_ns = wall_ns
        self._operation_ids = operation_ids or (lambda: secrets.token_hex(32))
        self._boot_id = boot_id
        self._mono_ns = mono_ns
        self._fault = fault or (lambda _point: None)
        self._authorizer_local = threading.local()
        self._closed = False
        self._allow_test_profile = allow_test_profile
        if _creation_control is not None and (
            not isinstance(_creation_control, ControlCapability)
            or _creation_control._seal is not _CONTROL_SEAL
        ):
            raise AuthorizationError("invalid store-creation capability")
        if _creation_control is not None and (
            _creation_lock_seal is not _CREATION_LOCK_SEAL
        ):
            raise AuthorizationError(
                "store creation requires the installer protocol lock"
            )
        if allow_test_profile:
            self._prepare_parent()
        else:
            self._prepare_supported_file(_creation_control)
        old_umask = os.umask(0o077)
        try:
            self._connection = sqlite3.connect(
                str(self.db_path),
                timeout=5.0,
                isolation_level=None,
            )
        finally:
            os.umask(old_umask)
        try:
            self._connection.row_factory = sqlite3.Row
            if not allow_test_profile:
                with registration_profile.bind_secure_path(
                    self.db_path, kind="file", required_mode=0o600
                ) as rebound:
                    if rebound.identity != self._initial_db_identity:
                        raise StoreUnavailable(
                            "database object changed across SQLite open"
                        )
            self._configure()
            existing_objects = self._connection.execute(
                "SELECT COUNT(*) FROM sqlite_schema "
                "WHERE name NOT LIKE 'sqlite_%'"
            ).fetchone()[0]
            if (
                not allow_test_profile
                and existing_objects == 0
                and _creation_control is None
            ):
                raise AuthorizationError(
                    "schema creation requires installer CONTROL"
                )
            registration_schema.install_or_verify(self._connection)
            self._tighten_files()
            self._locks = registration_lock.LockManager(
                self.db_path.parent / "locks"
            )
            self._profile_binding = (
                registration_profile.ProfileBinding.measure(
                    self._connection, profile_targets
                )
                if profile_targets is not None
                else None
            )
            if not allow_test_profile and self._profile_binding is None:
                raise StoreUnavailable(
                    "supported profile measurement is required"
                )
            self._connection.set_authorizer(self._authorize)
        except Exception:
            self._connection.close()
            self._closed = True
            raise

    def _test_connection(self, seal: object) -> sqlite3.Connection:
        if seal is not _TEST_PROFILE_SEAL:
            raise AuthorizationError("raw connection is outside the typed facade")
        return self._connection

    @property
    def measured_profile_hash(self) -> str | None:
        return (
            self._profile_binding.digest
            if self._profile_binding is not None
            else None
        )

    @property
    def measured_storage_dev(self) -> int | None:
        return (
            self._profile_binding.storage_dev
            if self._profile_binding is not None
            else None
        )

    def storage_ready(self) -> bool:
        """Fresh read-only profile/free-space readiness for aggregate status."""
        with self._read_scope():
            self._connection.execute("BEGIN")
            try:
                if self._profile_binding is not None:
                    measured = self._profile_binding.recheck(
                        self._connection
                    )
                else:
                    descriptor = os.open(
                        self.db_path,
                        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                    )
                    try:
                        assert self._free_bytes is not None
                        measured = int(self._free_bytes(descriptor))
                    finally:
                        os.close(descriptor)
                outstanding = self._outstanding_reservations()
                return measured >= (
                    FILESYSTEM_SAFETY_FLOOR
                    + MAX_CONTROL_RESERVE
                    + outstanding
                )
            finally:
                self._connection.execute("ROLLBACK")

    def _validate_profile_targets(
        self, targets: list[tuple[str, Path, str, int]]
    ) -> None:
        if tuple(role for role, *_ in targets) != (
            registration_profile.DESCRIPTOR_ROLES
        ):
            raise StoreUnavailable("profile target role order mismatch")
        by_role = {
            role: Path(path) for role, path, _kind, _mode in targets
        }
        expected = {
            "state_parent": self.db_path.parent,
            "db": self.db_path,
            "wal": Path(f"{self.db_path}-wal"),
            "shm": Path(f"{self.db_path}-shm"),
        }
        if any(by_role[role] != path for role, path in expected.items()):
            raise StoreUnavailable(
                "profile storage targets do not match registration database"
            )

    def _prepare_parent(self) -> None:
        missing: list[Path] = []
        cursor = self.db_path.parent
        while not cursor.exists():
            missing.append(cursor)
            cursor = cursor.parent
        for path in reversed(missing):
            path.mkdir(mode=0o700)
        for path in missing:
            os.chmod(path, 0o700)

    def _prepare_supported_file(
        self, creation_control: ControlCapability | None
    ) -> None:
        if not self.db_path.parent.exists():
            raise StoreUnavailable(
                "installer must pre-create the private registration directory"
            )
        with registration_profile.bind_secure_path(
            self.db_path.parent,
            kind="directory",
            required_mode=0o700,
        ) as parent:
            if not self.db_path.exists():
                if creation_control is None:
                    raise AuthorizationError(
                        "database creation requires installer CONTROL"
                    )
                flags = (
                    os.O_RDWR
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_NOFOLLOW", 0)
                )
                descriptor = os.open(
                    self.db_path.name,
                    flags,
                    0o600,
                    dir_fd=parent.fd,
                )
                os.close(descriptor)
            with registration_profile.bind_secure_path(
                self.db_path, kind="file", required_mode=0o600
            ) as bound:
                self._initial_db_identity = bound.identity

    def _configure(self) -> None:
        connection = self._connection
        connection.setconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE, True)
        connection.setconfig(sqlite3.SQLITE_DBCONFIG_TRUSTED_SCHEMA, False)
        connection.setconfig(sqlite3.SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE, True)
        mode = str(connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]).lower()
        if mode != "wal":
            raise StoreUnavailable("registration database refused WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA fullfsync=ON")
        connection.execute("PRAGMA checkpoint_fullfsync=ON")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("PRAGMA locking_mode=NORMAL")
        connection.execute("PRAGMA busy_timeout=5000")
        actual = self.pragma_snapshot(pre_authorizer=True)
        required = {
            "journal_mode": "wal",
            "synchronous": 2,
            "fullfsync": 1,
            "checkpoint_fullfsync": 1,
            "foreign_keys": 1,
            "trusted_schema": 0,
            "locking_mode": "normal",
            "defensive": True,
            "checkpoint_on_close": False,
        }
        if actual != required:
            raise StoreUnavailable(f"SQLite profile mismatch: {actual!r}")

    def pragma_snapshot(self, *, pre_authorizer: bool = False) -> dict[str, Any]:
        connection = self._connection
        result = {
            "journal_mode": str(
                connection.execute("PRAGMA journal_mode").fetchone()[0]
            ).lower(),
            "synchronous": int(
                connection.execute("PRAGMA synchronous").fetchone()[0]
            ),
            "fullfsync": int(connection.execute("PRAGMA fullfsync").fetchone()[0]),
            "checkpoint_fullfsync": int(
                connection.execute("PRAGMA checkpoint_fullfsync").fetchone()[0]
            ),
            "foreign_keys": int(
                connection.execute("PRAGMA foreign_keys").fetchone()[0]
            ),
            "trusted_schema": int(
                connection.execute("PRAGMA trusted_schema").fetchone()[0]
            ),
            "locking_mode": str(
                connection.execute("PRAGMA locking_mode").fetchone()[0]
            ).lower(),
            "defensive": bool(
                connection.getconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE)
            ),
            "checkpoint_on_close": not bool(
                connection.getconfig(sqlite3.SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE)
            ),
        }
        return result

    def _tighten_files(self) -> None:
        for suffix in ("", "-wal", "-shm"):
            path = Path(str(self.db_path) + suffix)
            if path.exists():
                os.chmod(path, 0o600)

    def _authorize(
        self,
        action: int,
        arg1: str | None,
        arg2: str | None,
        database: str | None,
        source: str | None,
    ) -> int:
        del database, source
        writes: frozenset[tuple[int, str]] = getattr(
            self._authorizer_local, "writes", frozenset()
        )
        active = bool(getattr(self._authorizer_local, "active", False))
        if action in {
            sqlite3.SQLITE_SELECT,
            sqlite3.SQLITE_READ,
            sqlite3.SQLITE_FUNCTION,
            sqlite3.SQLITE_RECURSIVE,
        }:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_PRAGMA:
            return sqlite3.SQLITE_OK if arg2 is None else sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_TRANSACTION:
            reading = bool(
                getattr(self._authorizer_local, "reading", False)
            )
            return (
                sqlite3.SQLITE_OK
                if active or reading
                else sqlite3.SQLITE_DENY
            )
        if arg1 is not None and (action, arg1) in writes and active:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    @contextmanager
    def _write_scope(
        self, writes: set[tuple[int, str]]
    ) -> Iterator[sqlite3.Connection]:
        if getattr(self._authorizer_local, "active", False):
            raise AuthorizationError("nested registration transaction")
        self._authorizer_local.active = True
        self._authorizer_local.writes = frozenset(writes)
        try:
            yield self._connection
        finally:
            self._authorizer_local.active = False
            self._authorizer_local.writes = frozenset()

    @contextmanager
    def _read_scope(self) -> Iterator[sqlite3.Connection]:
        if getattr(self._authorizer_local, "active", False) or getattr(
            self._authorizer_local, "reading", False
        ):
            raise AuthorizationError("nested registration transaction")
        self._authorizer_local.reading = True
        try:
            yield self._connection
        finally:
            self._authorizer_local.reading = False

    def _begin(self) -> int:
        self._fault("before_begin")
        self._connection.execute("BEGIN IMMEDIATE")
        self._fault("after_begin")
        if self._profile_binding is not None:
            value = self._profile_binding.recheck(self._connection)
        else:
            fd = os.open(
                self.db_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            )
            try:
                assert self._free_bytes is not None
                value = int(self._free_bytes(fd))
            finally:
                os.close(fd)
        if value < 0:
            raise StoreUnavailable("negative free-space measurement")
        return value

    def _commit(self) -> None:
        latest = self._connection.execute(
            "SELECT operation_id FROM registration_operation_audit "
            "ORDER BY operation_seq DESC LIMIT 1"
        ).fetchone()
        if latest is None or self.resolve_operation(latest["operation_id"]) != "COMMITTED":
            raise StoreError("mandatory operation closure SELECT failed")
        self._fault("before_commit")
        self._connection.execute("COMMIT")
        self._fault("after_commit")

    def _fresh_sample(self) -> tuple[str, int]:
        boot = self._boot_id()
        mono = self._mono_ns()
        if not isinstance(boot, str) or not boot or not isinstance(mono, int) or mono < 0:
            raise StoreUnavailable("boot/continuous-time sample unavailable")
        return boot, mono

    def _insert(self, table: str, row: Mapping[str, Any]) -> None:
        if table == "registration_operation_audit":
            self._preflight_operation_space(row)
        columns = tuple(row)
        sql = (
            f"INSERT INTO {table}({','.join(columns)}) "
            f"VALUES({','.join('?' for _ in columns)})"
        )
        self._fault(f"before_insert:{table}")
        self._connection.execute(sql, tuple(row[column] for column in columns))
        self._fault(f"after_insert:{table}")

    def _outstanding_reservations(
        self,
        *,
        excluded_effect_id: str | None = None,
        exclude_adopted_pending: bool = False,
        target_member_id: str | None = None,
    ) -> int:
        rows = self._connection.execute(
            "SELECT e.effect_id,e.outcome_kind,"
            "e.external_growth_reservation_bytes,e.outcome_reservation_bytes,"
            "e.successor_reservation_bytes,"
            "EXISTS(SELECT 1 FROM registration_member m "
            "WHERE m.current_effect_id=e.effect_id AND m.phase='RESOLVED') "
            "AS is_resolved_current,"
            "EXISTS(SELECT 1 FROM registration_member m "
            "WHERE m.member_id=? AND m.phase='EFFECT_IN_FLIGHT' "
            "AND m.pending_effect_id=e.effect_id) AS is_target_pending "
            "FROM registration_effect e",
            (target_member_id,),
        ).fetchall()
        total = 0
        for row in rows:
            if row["effect_id"] == excluded_effect_id:
                continue
            if exclude_adopted_pending and row["is_target_pending"]:
                continue
            if row["outcome_kind"] is None or row["is_resolved_current"]:
                if row["outcome_kind"] is None:
                    total += (
                        row["external_growth_reservation_bytes"]
                        + row["outcome_reservation_bytes"]
                        + row["successor_reservation_bytes"]
                    )
                else:
                    total += row["successor_reservation_bytes"]
        return int(total)

    def _preflight_operation_space(self, row: Mapping[str, Any]) -> None:
        kind = str(row["operation_kind"])
        measured = int(row["measured_free_bytes"])
        projected = int(row["projected_db_growth_bytes"])
        new_reservations = (
            int(row["new_external_reservation_bytes"])
            + int(row["new_outcome_reservation_bytes"])
            + int(row["new_successor_reservation_bytes"])
        )
        ordinary = {
            "BOOTSTRAP",
            "INSTALL_MEMBER",
            "BIND_EPISODE",
            "REACQUIRE_EFFECT",
            "OPEN_EFFECT",
            "SET_PENDING",
            "MARK_UNAVAILABLE",
            "REBOOT_STATUS",
            "SCHEDULE_STATUS",
        }
        consuming = {
            "APPEND_ACTION",
            "CLOSE_SUCCESS",
            "CLOSE_CONFLICT",
            "INVALIDATE_REQUESTED",
            "REPLACE_PENDING",
            "HANDOFF_RESOLVED",
        }
        if kind in ordinary:
            required = (
                FILESYSTEM_SAFETY_FLOOR
                + MAX_CONTROL_RESERVE
                + projected
                + self._outstanding_reservations()
                + new_reservations
            )
        elif kind in consuming:
            target = row["target_effect_id"]
            required = (
                FILESYSTEM_SAFETY_FLOOR
                + MAX_CONTROL_RESERVE
                + projected
                + self._outstanding_reservations(
                    excluded_effect_id=target
                )
                + new_reservations
            )
            target_row = self._connection.execute(
                "SELECT * FROM registration_effect WHERE effect_id=?",
                (target,),
            ).fetchone()
            if target_row is None:
                raise StaleAuthority("reservation target missing")
            if kind == "APPEND_ACTION":
                spent_projected = int(
                    self._connection.execute(
                        "SELECT COALESCE(SUM(projected_db_growth_bytes),0) "
                        "FROM registration_operation_audit "
                        "WHERE operation_kind='APPEND_ACTION' "
                        "AND target_effect_id=?",
                        (target,),
                    ).fetchone()[0]
                )
                spent_external = int(
                    self._connection.execute(
                        "SELECT COALESCE(SUM(external_growth_bytes),0) "
                        "FROM registration_effect_action WHERE effect_id=?",
                        (target,),
                    ).fetchone()[0]
                )
                remaining_outcome = (
                    target_row["outcome_reservation_bytes"]
                    - spent_projected
                    - projected
                )
                remaining_external = (
                    target_row["external_growth_reservation_bytes"]
                    - spent_external
                    - int(row["external_growth_bytes"])
                )
                if remaining_outcome < 0 or remaining_external < 0:
                    raise InsufficientSpace("effect reservation exhausted")
                required += (
                    target_row["successor_reservation_bytes"]
                    + remaining_outcome
                    + remaining_external
                )
            elif kind in {"CLOSE_SUCCESS", "CLOSE_CONFLICT"}:
                spent_projected = int(
                    self._connection.execute(
                        "SELECT COALESCE(SUM(projected_db_growth_bytes),0) "
                        "FROM registration_operation_audit "
                        "WHERE operation_kind='APPEND_ACTION' "
                        "AND target_effect_id=?",
                        (target,),
                    ).fetchone()[0]
                )
                if (
                    spent_projected + projected
                    > target_row["outcome_reservation_bytes"]
                ):
                    raise InsufficientSpace("outcome reservation exhausted")
                required += target_row["successor_reservation_bytes"]
            elif kind in {"INVALIDATE_REQUESTED", "REPLACE_PENDING"}:
                if projected > (
                    target_row["outcome_reservation_bytes"]
                    + target_row["successor_reservation_bytes"]
                ):
                    raise InsufficientSpace("successor reservation exhausted")
            elif kind == "HANDOFF_RESOLVED":
                if projected > target_row["successor_reservation_bytes"]:
                    raise InsufficientSpace("handoff reservation exhausted")
        elif row["operation_class"] == "CONTROL":
            exclude_pending = (
                kind == "ADOPT_EFFECT"
                and row["target_successor_effect_id"] is not None
            )
            if projected > 1024**2:
                raise InsufficientSpace("control transaction projection too large")
            required = (
                FILESYSTEM_SAFETY_FLOOR
                + int(row["control_reserve_bytes"])
                + projected
                + self._outstanding_reservations(
                    excluded_effect_id=(
                        row["target_effect_id"] if exclude_pending else None
                    ),
                    exclude_adopted_pending=exclude_pending,
                    target_member_id=row["target_member_id"],
                )
                + new_reservations
            )
        else:
            raise StoreError("operation kind has no free-space class")
        if measured < required:
            raise InsufficientSpace(
                f"measured {measured} below required {required}"
            )

    def _update_row(
        self,
        table: str,
        row: Mapping[str, Any],
        *,
        primary_key: str,
        expected_column: str,
        expected_value: Any,
    ) -> None:
        columns = tuple(column for column in row if column != primary_key)
        sql = (
            f"UPDATE {table} SET "
            + ",".join(f"{column}=?" for column in columns)
            + f" WHERE {primary_key}=? AND {expected_column} IS ?"
        )
        values = [row[column] for column in columns]
        values.extend((row[primary_key], expected_value))
        self._fault(f"before_update:{table}")
        cursor = self._connection.execute(sql, values)
        self._fault(f"after_update:{table}")
        if cursor.rowcount != 1:
            raise StaleAuthority(f"{table} compare-and-swap failed")

    def _operation_base(
        self,
        *,
        operation_id: str,
        operation_class: str,
        operation_kind: str,
        measured_free_bytes: int,
        projected_db_growth_bytes: int,
        candidate: ProtocolCandidate,
        control: ControlCapability | None,
        data: DataCapability | None,
        target_protocol_hash: str | None = None,
        overrides: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        current = self.current_protocol()
        revision = self.table_count("registration_operation_audit")
        projected_db_growth_bytes = max(
            projected_db_growth_bytes,
            PROJECTED_DB_BYTES[operation_kind],
        )
        row: dict[str, Any] = {column: None for column in _OPERATION_COLUMNS}
        row.update(
            {
                "operation_seq": revision + 1,
                "operation_id": operation_id,
                "operation_class": operation_class,
                "operation_kind": operation_kind,
                "expected_revision": revision,
                "protocol_seq": int(current["protocol_seq"]) if current else 0,
                "expected_mode": str(current["mode"]) if current else "NONE",
                "expected_generation": (
                    int(current["protocol_generation"]) if current else 0
                ),
                "expected_protocol_hash": (
                    str(current["protocol_hash"]) if current else None
                ),
                "runtime_capability_hash": candidate.runtime_capability_hash,
                "writer_binary_hash": candidate.writer_binary_hash,
                "profile_hash": candidate.profile_hash,
                "writer_capability_receipt_hash": (
                    data.writer_capability_hash if data else None
                ),
                "installer_identity_hash": (
                    control.installer_identity_hash if control else None
                ),
                "installer_capability_receipt_hash": (
                    control.installer_capability_hash if control else None
                ),
                "protocol_lock_receipt_hash": (
                    control.protocol_lock_receipt_hash if control else None
                ),
                "control_binding_hash": (
                    control.control_binding_hash if control else None
                ),
                "target_protocol_hash": target_protocol_hash,
                "measured_free_bytes": measured_free_bytes,
                "projected_db_growth_bytes": projected_db_growth_bytes,
                "external_growth_bytes": 0,
                "new_external_reservation_bytes": 0,
                "new_outcome_reservation_bytes": 0,
                "new_successor_reservation_bytes": 0,
                "control_reserve_bytes": MAX_CONTROL_RESERVE,
                "created_wall_ns": self._wall_ns(),
            }
        )
        if overrides:
            unknown = set(overrides) - set(row)
            if unknown:
                raise ValueError(f"unknown operation fields: {sorted(unknown)}")
            row.update(overrides)
        row["operation_envelope_hash"] = registration_hashes.derive(
            "operation_envelope_hash", row
        )
        return row

    def _build_effect(
        self,
        *,
        member_id: str,
        member_epoch: int,
        predecessor_effect_id: str | None,
        intent: EffectIntent,
        protocol_generation: int,
        runtime_capability_hash: str,
    ) -> dict[str, Any]:
        actions: list[dict[str, str]] = []
        action_blob: bytes | None = None
        action_plan_hash = ZERO_HASH
        if intent.request_kind == "CLEAN_ELIGIBLE":
            actions = [
                {
                    "ordinal": str(index),
                    "kind": action.kind,
                    "action_hash": action.action_hash,
                    "postcondition_hash": action.postcondition_hash,
                }
                for index, action in enumerate(intent.actions, 1)
            ]
            action_blob = registration_jcs.encode_blob(
                "action_plan",
                {
                    "actions": actions,
                    "external_growth_reservation_bytes": str(
                        intent.external_growth_reservation_bytes
                    ),
                    "outcome_reservation_bytes": str(
                        intent.outcome_reservation_bytes
                    ),
                    "successor_reservation_bytes": str(
                        intent.successor_reservation_bytes
                    ),
                },
            )
            action_plan_hash = _domain_hash(
                "awa-registration-action-plan/v1", action_blob
            )
        effect_id = registration_hashes.deterministic_id(
            "awa-reg-effect-v3",
            member_id,
            str(member_epoch),
            intent.request_kind,
            intent.request_basis_hash,
            action_plan_hash,
            str(protocol_generation),
            runtime_capability_hash,
        )
        row: dict[str, Any] = {
            "effect_id": effect_id,
            "member_id": member_id,
            "member_epoch": member_epoch,
            "request_kind": intent.request_kind,
            "request_basis_hash": intent.request_basis_hash,
            "predecessor_effect_id": predecessor_effect_id,
            "required_protocol_generation": protocol_generation,
            "required_runtime_capability_hash": runtime_capability_hash,
            "action_plan_hash": action_plan_hash,
            "action_plan_blob": action_blob,
            "required_action_count": 4 if actions else 0,
            "external_growth_reservation_bytes": (
                intent.external_growth_reservation_bytes
            ),
            "outcome_reservation_bytes": intent.outcome_reservation_bytes,
            "successor_reservation_bytes": intent.successor_reservation_bytes,
        }
        for index in range(1, 5):
            action = actions[index - 1] if actions else None
            row[f"action_{index}_kind"] = action["kind"] if action else None
            row[f"action_{index}_hash"] = (
                action["action_hash"] if action else None
            )
            row[f"postcondition_{index}_hash"] = (
                action["postcondition_hash"] if action else None
            )
        row["request_tuple_hash"] = registration_hashes.derive(
            "request_tuple_hash", row
        )
        row.update(
            {
                "created_operation_seq": None,
                "created_operation_id": None,
                "created_operation_hash": None,
                "outcome_kind": None,
                "outcome_helper_generation": None,
                "outcome_tuple_hash": None,
                "ledger_head_hash": None,
                "first_conflict_event_seq": None,
                "completion_blob": None,
                "completion_hash": None,
                "final_basis_hash": None,
                "proof_blob": None,
                "proof_hash": None,
                "certificate_inputs_blob": None,
                "certificate_inputs_hash": None,
                "certificate_hash": None,
                "conflict_code": None,
                "conflict_blob": None,
                "conflict_hash": None,
                "superseded_by_effect_id": None,
                "successor_transition_id": None,
                "outcome_operation_seq": None,
                "outcome_operation_id": None,
                "outcome_operation_hash": None,
            }
        )
        return row

    def _requested_status(
        self,
        old: Mapping[str, Any],
        *,
        member_epoch: int,
        effect: Mapping[str, Any],
        sample_boot_id: str,
        sample_mono_ns: int,
        version: int,
    ) -> dict[str, Any]:
        clean = effect["request_kind"] == "CLEAN_ELIGIBLE"
        status = dict(old)
        status.update(
            {
                "member_epoch": member_epoch,
                "current_effect_id": effect["effect_id"],
                "status_version": version,
                "schedule_boot_id": sample_boot_id if clean else None,
                "observed_now_mono_ns": sample_mono_ns if clean else None,
                "next_due_mono_ns": sample_mono_ns if clean else None,
                "due_since_mono_ns": sample_mono_ns if clean else None,
                "attempt_count": 0 if clean else None,
                "backoff_ns": 0 if clean else None,
                "help_due": 0,
                "executor_token_hash": None,
                "executor_boot_id": None,
                "executor_generation": None,
                "blocked_basis_fingerprint": (
                    None
                    if clean
                    else registration_hashes.deterministic_id(
                        "awa-reg-blocked-basis/v1",
                        effect["request_basis_hash"],
                        effect["request_kind"],
                    )
                ),
                "reason_code": (
                    "REGISTRATION_REQUIRED"
                    if clean
                    else (
                        "DIRTY_UNSUPPORTED"
                        if effect["request_kind"] == "BLOCKED_DIRTY"
                        else "GIT_OPERATION_UNSUPPORTED"
                    )
                ),
            }
        )
        status["status_hash"] = registration_hashes.derive(
            "status_hash", status
        )
        return status

    @staticmethod
    def _successor_transition_id(
        *,
        operation_kind: str,
        cause: str,
        old_member_hash: str,
        old_status_hash: str,
        old_effect_hash: str,
        new_member_hash: str,
        new_status_hash: str,
        new_effect_hash: str,
        old_epoch: int,
        old_basis: str,
        new_epoch: int,
        new_basis: str,
        old_effect_id: str,
        new_effect_id: str,
    ) -> str:
        return registration_hashes.deterministic_id(
            "awa-reg-successor-v4",
            operation_kind,
            cause,
            old_member_hash,
            old_status_hash,
            old_effect_hash,
            new_member_hash,
            new_status_hash,
            new_effect_hash,
            str(old_epoch),
            old_basis,
            str(new_epoch),
            new_basis,
            old_effect_id,
            new_effect_id,
        )

    def bootstrap(
        self,
        control: ControlCapability,
        candidate: ProtocolCandidate,
        *,
        operation_id: str | None = None,
        projected_db_growth_bytes: int = 0,
        _protocol_locked: bool = False,
    ) -> OperationResult:
        if not isinstance(control, ControlCapability) or control._seal is not _CONTROL_SEAL:
            raise AuthorizationError("invalid BOOTSTRAP control capability")
        if (
            control.installer_identity_hash != candidate.installer_identity_hash
            or control.installer_capability_hash
            != candidate.installer_capability_hash
        ):
            raise AuthorizationError("candidate/control mismatch")
        if self._profile_binding is not None and (
            candidate.profile_hash != self._profile_binding.digest
            or candidate.storage_dev != self._profile_binding.storage_dev
        ):
            raise StaleAuthority("candidate does not match measured profile")
        if not _protocol_locked:
            with self._locks.acquire_protocol() as held:
                held.verify()
                return self.bootstrap(
                    control,
                    candidate,
                    operation_id=operation_id,
                    projected_db_growth_bytes=projected_db_growth_bytes,
                    _protocol_locked=True,
                )
        operation_id = operation_id or self._operation_ids()
        if len(operation_id) != 64:
            raise ValueError("operation_id must be 64-hex")
        with self._write_scope(
            {
                (sqlite3.SQLITE_INSERT, "registration_operation_audit"),
                (sqlite3.SQLITE_INSERT, "registration_protocol_epoch"),
            }
        ):
            try:
                measured = self._begin()
                required = (
                    FILESYSTEM_SAFETY_FLOOR
                    + MAX_CONTROL_RESERVE
                    + projected_db_growth_bytes
                )
                if measured < required:
                    raise InsufficientSpace(
                        f"measured {measured} below required {required}"
                    )
                if self.table_count("registration_operation_audit") != 0:
                    raise StaleAuthority("registration authority already bootstrapped")
                protocol: dict[str, Any] = {
                    column: None for column in _PROTOCOL_COLUMNS
                }
                protocol.update(
                    {
                        "protocol_seq": 1,
                        "protocol_generation": 1,
                        "mode": "DORMANT",
                        "schema_hash": SCHEMA_SHA256,
                        "profile_hash": candidate.profile_hash,
                        "runtime_capability_hash": candidate.runtime_capability_hash,
                        "writer_binary_hash": candidate.writer_binary_hash,
                        "writer_capability_hash": candidate.writer_capability_hash,
                        "tool_inventory_hash": candidate.tool_inventory_hash,
                        "hook_projection_hash": candidate.hook_projection_hash,
                        "hook_matcher_mode": candidate.hook_matcher_mode,
                        "hook_matcher_hash": candidate.hook_matcher_hash,
                        "projection_receipt_hash": candidate.projection_receipt_hash,
                        "projection_file_generation": (
                            candidate.projection_file_generation
                        ),
                        "installer_identity_hash": (
                            candidate.installer_identity_hash
                        ),
                        "installer_capability_hash": (
                            candidate.installer_capability_hash
                        ),
                        "storage_dev": candidate.storage_dev,
                        "transition_kind": "BOOTSTRAP",
                        "transition_reason_code": "BOOTSTRAP",
                        "created_wall_ns": self._wall_ns(),
                    }
                )
                protocol_hash = registration_hashes.derive(
                    "protocol_hash", protocol
                )
                protocol["protocol_hash"] = protocol_hash
                protocol["operation_id"] = operation_id
                operation = self._operation_base(
                    operation_id=operation_id,
                    operation_class="BOOTSTRAP",
                    operation_kind="BOOTSTRAP",
                    measured_free_bytes=measured,
                    projected_db_growth_bytes=projected_db_growth_bytes,
                    candidate=candidate,
                    control=control,
                    data=None,
                    target_protocol_hash=protocol_hash,
                )
                self._insert("registration_operation_audit", operation)
                self._insert("registration_protocol_epoch", protocol)
                closure = self._connection.execute(
                    "SELECT p.protocol_hash,o.operation_envelope_hash "
                    "FROM registration_protocol_epoch p "
                    "JOIN registration_operation_audit o "
                    "ON o.operation_id=p.operation_id "
                    "WHERE p.protocol_seq=1 AND p.protocol_hash=? "
                    "AND o.operation_id=?",
                    (protocol_hash, operation_id),
                ).fetchone()
                if closure is None:
                    raise StoreError("BOOTSTRAP closure failed")
                self._commit()
                self._tighten_files()
                return OperationResult(
                    "COMMITTED",
                    operation_id,
                    str(operation["operation_envelope_hash"]),
                    protocol_hash,
                )
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def _require_current_candidate(
        self, candidate: ProtocolCandidate, *, mode: str | None = None
    ) -> dict[str, Any]:
        current = self.current_protocol()
        if current is None:
            raise StaleAuthority("registration authority is not bootstrapped")
        pairs = {
            "schema_hash": SCHEMA_SHA256,
            "profile_hash": candidate.profile_hash,
            "runtime_capability_hash": candidate.runtime_capability_hash,
            "writer_binary_hash": candidate.writer_binary_hash,
            "writer_capability_hash": candidate.writer_capability_hash,
            "tool_inventory_hash": candidate.tool_inventory_hash,
            "hook_projection_hash": candidate.hook_projection_hash,
            "hook_matcher_mode": candidate.hook_matcher_mode,
            "hook_matcher_hash": candidate.hook_matcher_hash,
            "projection_receipt_hash": candidate.projection_receipt_hash,
            "projection_file_generation": candidate.projection_file_generation,
            "installer_identity_hash": candidate.installer_identity_hash,
            "installer_capability_hash": candidate.installer_capability_hash,
            "storage_dev": candidate.storage_dev,
        }
        if any(current[key] != value for key, value in pairs.items()):
            raise StaleAuthority("candidate does not match current protocol")
        if mode is not None and current["mode"] != mode:
            raise StaleAuthority(
                f"expected protocol mode {mode}, got {current['mode']}"
            )
        return current

    @staticmethod
    def _require_control(
        control: ControlCapability, candidate: ProtocolCandidate
    ) -> None:
        if not isinstance(control, ControlCapability) or control._seal is not _CONTROL_SEAL:
            raise AuthorizationError("invalid CONTROL capability")
        if (
            control.installer_identity_hash != candidate.installer_identity_hash
            or control.installer_capability_hash
            != candidate.installer_capability_hash
        ):
            raise AuthorizationError("candidate/control mismatch")

    @staticmethod
    def _require_data(data: DataCapability, candidate: ProtocolCandidate) -> None:
        if not isinstance(data, DataCapability) or data._seal is not _DATA_SEAL:
            raise AuthorizationError("invalid DATA capability")
        if not secrets.compare_digest(
            data.writer_capability_hash, candidate.writer_capability_hash
        ):
            raise AuthorizationError("candidate/DATA mismatch")

    def activate(
        self,
        control: ControlCapability,
        candidate: ProtocolCandidate,
        *,
        operation_id: str | None = None,
        projected_db_growth_bytes: int = 0,
        _protocol_locked: bool = False,
    ) -> OperationResult:
        self._require_control(control, candidate)
        if not _protocol_locked:
            with self._locks.acquire_protocol() as held:
                held.verify()
                return self.activate(
                    control,
                    candidate,
                    operation_id=operation_id,
                    projected_db_growth_bytes=projected_db_growth_bytes,
                    _protocol_locked=True,
                )
        current = self._require_current_candidate(candidate, mode="DORMANT")
        operation_id = operation_id or self._operation_ids()
        with self._write_scope(
            {
                (sqlite3.SQLITE_INSERT, "registration_operation_audit"),
                (sqlite3.SQLITE_INSERT, "registration_protocol_epoch"),
            }
        ):
            try:
                measured = self._begin()
                protocol = {
                    column: current[column] for column in _PROTOCOL_COLUMNS
                }
                protocol.update(
                    {
                        "protocol_seq": int(current["protocol_seq"]) + 1,
                        "mode": "WRITABLE",
                        "transition_kind": "ACTIVATE",
                        "transition_reason_code": "ACTIVATE",
                        "previous_protocol_hash": current["protocol_hash"],
                        "absence_proof_hash": None,
                        "quiescence_proof_hash": None,
                        "created_wall_ns": self._wall_ns(),
                    }
                )
                target_hash = registration_hashes.derive(
                    "protocol_hash", protocol
                )
                protocol["protocol_hash"] = target_hash
                protocol["operation_id"] = operation_id
                protocol["first_effect_operation_id"] = current[
                    "first_effect_operation_id"
                ]
                operation = self._operation_base(
                    operation_id=operation_id,
                    operation_class="CONTROL",
                    operation_kind="ACTIVATE",
                    measured_free_bytes=measured,
                    projected_db_growth_bytes=projected_db_growth_bytes,
                    candidate=candidate,
                    control=control,
                    data=None,
                    target_protocol_hash=target_hash,
                )
                self._insert("registration_operation_audit", operation)
                self._insert("registration_protocol_epoch", protocol)
                closure = self._connection.execute(
                    "SELECT 1 FROM registration_protocol_epoch "
                    "WHERE protocol_hash=? AND mode='WRITABLE' "
                    "AND operation_id=?",
                    (target_hash, operation_id),
                ).fetchone()
                if closure is None:
                    raise StoreError("ACTIVATE closure failed")
                self._commit()
                self._tighten_files()
                return OperationResult(
                    "COMMITTED",
                    operation_id,
                    operation["operation_envelope_hash"],
                    target_hash,
                )
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def begin_drain(
        self,
        control: ControlCapability,
        candidate: ProtocolCandidate,
        *,
        operation_id: str | None = None,
    ) -> OperationResult:
        return self._control_protocol_transition(
            control,
            candidate,
            transition_kind="BEGIN_DRAIN",
            transition_reason="BEGIN_DRAIN",
            staged_candidate=None,
            quiescence_proof_hash=None,
            absence_proof_hash=None,
            operation_id=operation_id,
        )

    def stage_next(
        self,
        control: ControlCapability,
        candidate: ProtocolCandidate,
        staged_candidate: ProtocolCandidate,
        *,
        quiescence_proof_hash: str,
        operation_id: str | None = None,
    ) -> OperationResult:
        _require_hash(quiescence_proof_hash, "quiescence_proof_hash")
        return self._control_protocol_transition(
            control,
            candidate,
            transition_kind="STAGE_NEXT",
            transition_reason="STAGE_NEXT",
            staged_candidate=staged_candidate,
            quiescence_proof_hash=quiescence_proof_hash,
            absence_proof_hash=None,
            operation_id=operation_id,
        )

    def cancel_drain(
        self,
        control: ControlCapability,
        candidate: ProtocolCandidate,
        *,
        quiescence_proof_hash: str,
        operation_id: str | None = None,
    ) -> OperationResult:
        _require_hash(quiescence_proof_hash, "quiescence_proof_hash")
        return self._control_protocol_transition(
            control,
            candidate,
            transition_kind="CANCEL_DRAIN",
            transition_reason="CANCEL_DRAIN",
            staged_candidate=None,
            quiescence_proof_hash=quiescence_proof_hash,
            absence_proof_hash=None,
            operation_id=operation_id,
        )

    def advance_generation(
        self,
        control: ControlCapability,
        candidate: ProtocolCandidate,
        *,
        quiescence_proof_hash: str,
        operation_id: str | None = None,
    ) -> OperationResult:
        _require_hash(quiescence_proof_hash, "quiescence_proof_hash")
        return self._control_protocol_transition(
            control,
            candidate,
            transition_kind="ADVANCE_GENERATION",
            transition_reason="ADVANCE_GENERATION",
            staged_candidate=None,
            quiescence_proof_hash=quiescence_proof_hash,
            absence_proof_hash=None,
            operation_id=operation_id,
        )

    def pre_effect_dormant(
        self,
        control: ControlCapability,
        candidate: ProtocolCandidate,
        *,
        absence_proof_hash: str,
        operation_id: str | None = None,
    ) -> OperationResult:
        _require_hash(absence_proof_hash, "absence_proof_hash")
        return self._control_protocol_transition(
            control,
            candidate,
            transition_kind="PRE_EFFECT_DORMANT",
            transition_reason="PRE_EFFECT_DORMANT",
            staged_candidate=None,
            quiescence_proof_hash=None,
            absence_proof_hash=absence_proof_hash,
            operation_id=operation_id,
        )

    def enter_containment(
        self,
        control: ControlCapability,
        candidate: ProtocolCandidate,
        *,
        reason: str,
        operation_id: str | None = None,
    ) -> OperationResult:
        if reason not in {
            "DRAIN_BOOT_CHANGED",
            "DRAIN_TIMEOUT",
            "ADOPTION_FAILED",
            "STORE_FAILURE",
        }:
            raise ValueError("invalid containment reason")
        return self._control_protocol_transition(
            control,
            candidate,
            transition_kind="ENTER_CONTAINMENT",
            transition_reason=reason,
            staged_candidate=None,
            quiescence_proof_hash=None,
            absence_proof_hash=None,
            operation_id=operation_id,
        )

    def begin_repair(
        self,
        control: ControlCapability,
        candidate: ProtocolCandidate,
        *,
        operation_id: str | None = None,
    ) -> OperationResult:
        return self._control_protocol_transition(
            control,
            candidate,
            transition_kind="BEGIN_REPAIR",
            transition_reason="BEGIN_REPAIR",
            staged_candidate=None,
            quiescence_proof_hash=None,
            absence_proof_hash=None,
            operation_id=operation_id,
        )

    def _control_protocol_transition(
        self,
        control: ControlCapability,
        candidate: ProtocolCandidate,
        *,
        transition_kind: str,
        transition_reason: str,
        staged_candidate: ProtocolCandidate | None,
        quiescence_proof_hash: str | None,
        absence_proof_hash: str | None,
        operation_id: str | None,
        _protocol_locked: bool = False,
    ) -> OperationResult:
        self._require_control(control, candidate)
        if not _protocol_locked:
            with self._locks.acquire_protocol() as held:
                held.verify()
                return self._control_protocol_transition(
                    control,
                    candidate,
                    transition_kind=transition_kind,
                    transition_reason=transition_reason,
                    staged_candidate=staged_candidate,
                    quiescence_proof_hash=quiescence_proof_hash,
                    absence_proof_hash=absence_proof_hash,
                    operation_id=operation_id,
                    _protocol_locked=True,
                )
        current = self._require_current_candidate(candidate)
        operation_id = operation_id or self._operation_ids()
        with self._write_scope(
            {
                (sqlite3.SQLITE_INSERT, "registration_operation_audit"),
                (sqlite3.SQLITE_INSERT, "registration_protocol_epoch"),
            }
        ):
            try:
                measured = self._begin()
                sample_boot_id, sample_mono_ns = self._fresh_sample()
                protocol = {
                    column: current[column] for column in _PROTOCOL_COLUMNS
                }
                protocol.update(
                    {
                        "protocol_seq": int(current["protocol_seq"]) + 1,
                        "transition_kind": transition_kind,
                        "transition_reason_code": transition_reason,
                        "previous_protocol_hash": current["protocol_hash"],
                        "absence_proof_hash": absence_proof_hash,
                        "quiescence_proof_hash": quiescence_proof_hash,
                        "created_wall_ns": self._wall_ns(),
                    }
                )
                operation_staged_hash: str | None = current["staged_epoch_hash"]
                if transition_kind == "BEGIN_DRAIN":
                    if current["mode"] != "WRITABLE":
                        raise StaleAuthority("BEGIN_DRAIN requires WRITABLE")
                    protocol.update(
                        {
                            "mode": "DRAINING",
                            "drain_boot_id": sample_boot_id,
                            "drain_deadline_mono_ns": sample_mono_ns
                            + 5_000_000_000,
                        }
                    )
                elif transition_kind == "STAGE_NEXT":
                    if current["mode"] != "DRAINING" or staged_candidate is None:
                        raise StaleAuthority(
                            "STAGE_NEXT requires DRAINING and a candidate"
                        )
                    if (
                        sample_boot_id != current["drain_boot_id"]
                        or sample_mono_ns > current["drain_deadline_mono_ns"]
                    ):
                        raise StaleAuthority("drain sample expired or changed boot")
                    staged_fields = {
                        "staged_generation": int(
                            current["protocol_generation"]
                        )
                        + 1,
                        "staged_schema_hash": SCHEMA_SHA256,
                        "staged_profile_hash": staged_candidate.profile_hash,
                        "staged_runtime_capability_hash": (
                            staged_candidate.runtime_capability_hash
                        ),
                        "staged_writer_binary_hash": (
                            staged_candidate.writer_binary_hash
                        ),
                        "staged_writer_capability_hash": (
                            staged_candidate.writer_capability_hash
                        ),
                        "staged_tool_inventory_hash": (
                            staged_candidate.tool_inventory_hash
                        ),
                        "staged_hook_projection_hash": (
                            staged_candidate.hook_projection_hash
                        ),
                        "staged_hook_matcher_mode": (
                            staged_candidate.hook_matcher_mode
                        ),
                        "staged_hook_matcher_hash": (
                            staged_candidate.hook_matcher_hash
                        ),
                        "staged_projection_receipt_hash": (
                            staged_candidate.projection_receipt_hash
                        ),
                        "staged_projection_file_generation": (
                            staged_candidate.projection_file_generation
                        ),
                        "staged_installer_identity_hash": (
                            staged_candidate.installer_identity_hash
                        ),
                        "staged_installer_capability_hash": (
                            staged_candidate.installer_capability_hash
                        ),
                    }
                    operation_staged_hash = registration_hashes.derive(
                        "staged_epoch_hash", staged_fields
                    )
                    protocol.update(staged_fields)
                    protocol["staged_epoch_hash"] = operation_staged_hash
                elif transition_kind == "CANCEL_DRAIN":
                    if current["mode"] != "DRAINING":
                        raise StaleAuthority("CANCEL_DRAIN requires DRAINING")
                    if (
                        sample_boot_id != current["drain_boot_id"]
                        or sample_mono_ns > current["drain_deadline_mono_ns"]
                    ):
                        raise StaleAuthority("drain sample expired or changed boot")
                    protocol["mode"] = "DORMANT"
                    for field in (
                        "staged_generation",
                        "staged_schema_hash",
                        "staged_profile_hash",
                        "staged_runtime_capability_hash",
                        "staged_writer_binary_hash",
                        "staged_writer_capability_hash",
                        "staged_tool_inventory_hash",
                        "staged_hook_projection_hash",
                        "staged_hook_matcher_mode",
                        "staged_hook_matcher_hash",
                        "staged_projection_receipt_hash",
                        "staged_projection_file_generation",
                        "staged_installer_identity_hash",
                        "staged_installer_capability_hash",
                        "staged_epoch_hash",
                    ):
                        protocol[field] = None
                    protocol["drain_boot_id"] = None
                    protocol["drain_deadline_mono_ns"] = None
                elif transition_kind == "ADVANCE_GENERATION":
                    if (
                        current["mode"] != "DRAINING"
                        or current["staged_generation"] is None
                    ):
                        raise StaleAuthority(
                            "ADVANCE_GENERATION requires staged DRAINING"
                        )
                    if (
                        sample_boot_id != current["drain_boot_id"]
                        or sample_mono_ns > current["drain_deadline_mono_ns"]
                    ):
                        raise StaleAuthority("drain sample expired or changed boot")
                    mappings = {
                        "protocol_generation": "staged_generation",
                        "schema_hash": "staged_schema_hash",
                        "profile_hash": "staged_profile_hash",
                        "runtime_capability_hash": (
                            "staged_runtime_capability_hash"
                        ),
                        "writer_binary_hash": "staged_writer_binary_hash",
                        "writer_capability_hash": (
                            "staged_writer_capability_hash"
                        ),
                        "tool_inventory_hash": "staged_tool_inventory_hash",
                        "hook_projection_hash": (
                            "staged_hook_projection_hash"
                        ),
                        "hook_matcher_mode": "staged_hook_matcher_mode",
                        "hook_matcher_hash": "staged_hook_matcher_hash",
                        "projection_receipt_hash": (
                            "staged_projection_receipt_hash"
                        ),
                        "projection_file_generation": (
                            "staged_projection_file_generation"
                        ),
                        "installer_identity_hash": (
                            "staged_installer_identity_hash"
                        ),
                        "installer_capability_hash": (
                            "staged_installer_capability_hash"
                        ),
                    }
                    for target, staged in mappings.items():
                        protocol[target] = current[staged]
                    protocol["mode"] = "WRITABLE"
                    for field in (
                        "staged_generation",
                        "staged_schema_hash",
                        "staged_profile_hash",
                        "staged_runtime_capability_hash",
                        "staged_writer_binary_hash",
                        "staged_writer_capability_hash",
                        "staged_tool_inventory_hash",
                        "staged_hook_projection_hash",
                        "staged_hook_matcher_mode",
                        "staged_hook_matcher_hash",
                        "staged_projection_receipt_hash",
                        "staged_projection_file_generation",
                        "staged_installer_identity_hash",
                        "staged_installer_capability_hash",
                        "staged_epoch_hash",
                    ):
                        protocol[field] = None
                    protocol["drain_boot_id"] = None
                    protocol["drain_deadline_mono_ns"] = None
                elif transition_kind == "PRE_EFFECT_DORMANT":
                    if current["mode"] != "DRAINING":
                        raise StaleAuthority(
                            "PRE_EFFECT_DORMANT requires DRAINING"
                        )
                    if (
                        sample_boot_id != current["drain_boot_id"]
                        or sample_mono_ns > current["drain_deadline_mono_ns"]
                    ):
                        raise StaleAuthority("drain sample expired or changed boot")
                    protocol.update(
                        {
                            "mode": "DORMANT",
                            "drain_boot_id": None,
                            "drain_deadline_mono_ns": None,
                        }
                    )
                    for field in (
                        "staged_generation",
                        "staged_schema_hash",
                        "staged_profile_hash",
                        "staged_runtime_capability_hash",
                        "staged_writer_binary_hash",
                        "staged_writer_capability_hash",
                        "staged_tool_inventory_hash",
                        "staged_hook_projection_hash",
                        "staged_hook_matcher_mode",
                        "staged_hook_matcher_hash",
                        "staged_projection_receipt_hash",
                        "staged_projection_file_generation",
                        "staged_installer_identity_hash",
                        "staged_installer_capability_hash",
                        "staged_epoch_hash",
                    ):
                        protocol[field] = None
                elif transition_kind == "ENTER_CONTAINMENT":
                    if current["mode"] == "CONTAINMENT":
                        raise StaleAuthority("already contained")
                    if transition_reason == "DRAIN_BOOT_CHANGED":
                        if (
                            current["mode"] != "DRAINING"
                            or sample_boot_id == current["drain_boot_id"]
                        ):
                            raise StaleAuthority(
                                "boot-change containment proof mismatch"
                            )
                    elif transition_reason == "DRAIN_TIMEOUT":
                        if (
                            current["mode"] != "DRAINING"
                            or sample_boot_id != current["drain_boot_id"]
                            or sample_mono_ns
                            <= current["drain_deadline_mono_ns"]
                        ):
                            raise StaleAuthority(
                                "timeout containment proof mismatch"
                            )
                    elif transition_reason == "ADOPTION_FAILED":
                        if (
                            current["mode"] != "DRAINING"
                            or sample_boot_id != current["drain_boot_id"]
                        ):
                            raise StaleAuthority(
                                "adoption containment proof mismatch"
                            )
                    protocol.update(
                        {
                            "mode": "CONTAINMENT",
                            "drain_boot_id": None,
                            "drain_deadline_mono_ns": None,
                        }
                    )
                elif transition_kind == "BEGIN_REPAIR":
                    if current["mode"] != "CONTAINMENT":
                        raise StaleAuthority("BEGIN_REPAIR requires containment")
                    protocol.update(
                        {
                            "mode": "DRAINING",
                            "drain_boot_id": sample_boot_id,
                            "drain_deadline_mono_ns": sample_mono_ns
                            + 5_000_000_000,
                        }
                    )
                else:
                    raise ValueError("unsupported protocol transition")

                target_hash = registration_hashes.derive(
                    "protocol_hash", protocol
                )
                protocol["protocol_hash"] = target_hash
                protocol["first_effect_operation_id"] = current[
                    "first_effect_operation_id"
                ]
                protocol["operation_id"] = operation_id
                operation = self._operation_base(
                    operation_id=operation_id,
                    operation_class="CONTROL",
                    operation_kind=transition_kind,
                    measured_free_bytes=measured,
                    projected_db_growth_bytes=0,
                    candidate=candidate,
                    control=control,
                    data=None,
                    target_protocol_hash=target_hash,
                    overrides={
                        "target_staged_epoch_hash": operation_staged_hash,
                        "sample_boot_id": sample_boot_id,
                        "sample_mono_ns": sample_mono_ns,
                    },
                )
                self._insert("registration_operation_audit", operation)
                self._insert("registration_protocol_epoch", protocol)
                closure = self._connection.execute(
                    "SELECT 1 FROM registration_protocol_epoch "
                    "WHERE protocol_hash=? AND operation_id=?",
                    (target_hash, operation_id),
                ).fetchone()
                if closure is None:
                    raise StoreError(f"{transition_kind} closure failed")
                self._commit()
                self._tighten_files()
                return OperationResult(
                    "COMMITTED",
                    operation_id,
                    operation["operation_envelope_hash"],
                    target_hash,
                )
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def install_member(
        self,
        data: DataCapability,
        candidate: ProtocolCandidate,
        identity: MemberIdentity,
        intent: EffectIntent,
        *,
        sample_boot_id: str | None = None,
        sample_mono_ns: int | None = None,
        operation_id: str | None = None,
        projected_db_growth_bytes: int = 0,
        _member_lock: registration_lock.HeldLock | None = None,
    ) -> OperationResult:
        self._require_data(data, candidate)
        current = self._require_current_candidate(candidate, mode="WRITABLE")
        if identity.root_dev != int(current["storage_dev"]):
            raise StaleAuthority("member storage device mismatch")
        if identity.current_basis_hash != intent.request_basis_hash:
            raise StaleAuthority("member/effect basis mismatch")
        if (sample_boot_id is None) != (sample_mono_ns is None):
            raise ValueError("expected sample must be supplied as one pair")
        operation_id = operation_id or self._operation_ids()
        member_id = registration_hashes.deterministic_id(
            "awa-reg-member-v1",
            identity.canonical_root,
            str(identity.root_dev),
            str(identity.root_ino),
            identity.git_dir,
            str(identity.git_dir_dev),
            str(identity.git_dir_ino),
            identity.git_common_dir,
            str(identity.git_common_dev),
            str(identity.git_common_ino),
        )
        if _member_lock is None:
            with self._locks.acquire_member(member_id) as held:
                held.verify()
                return self.install_member(
                    data,
                    candidate,
                    identity,
                    intent,
                    sample_boot_id=sample_boot_id,
                    sample_mono_ns=sample_mono_ns,
                    operation_id=operation_id,
                    projected_db_growth_bytes=projected_db_growth_bytes,
                    _member_lock=held,
                )
        _member_lock.verify()
        subject_key = registration_hashes.deterministic_id(
            "awa-reg-status-subject-v4", member_id
        )
        action_blob: bytes | None = None
        action_hash = ZERO_HASH
        actions: list[dict[str, str]] = []
        if intent.request_kind == "CLEAN_ELIGIBLE":
            actions = [
                {
                    "ordinal": str(index),
                    "kind": action.kind,
                    "action_hash": action.action_hash,
                    "postcondition_hash": action.postcondition_hash,
                }
                for index, action in enumerate(intent.actions, 1)
            ]
            relation = {
                "actions": actions,
                "external_growth_reservation_bytes": str(
                    intent.external_growth_reservation_bytes
                ),
                "outcome_reservation_bytes": str(
                    intent.outcome_reservation_bytes
                ),
                "successor_reservation_bytes": str(
                    intent.successor_reservation_bytes
                ),
            }
            action_blob = registration_jcs.encode_blob("action_plan", relation)
            action_hash = _domain_hash(
                "awa-registration-action-plan/v1", action_blob
            )
        effect_id = registration_hashes.deterministic_id(
            "awa-reg-effect-v3",
            member_id,
            "1",
            intent.request_kind,
            intent.request_basis_hash,
            action_hash,
            str(current["protocol_generation"]),
            str(current["runtime_capability_hash"]),
        )
        effect: dict[str, Any] = {
            "effect_id": effect_id,
            "member_id": member_id,
            "member_epoch": 1,
            "request_kind": intent.request_kind,
            "request_basis_hash": intent.request_basis_hash,
            "predecessor_effect_id": None,
            "required_protocol_generation": current["protocol_generation"],
            "required_runtime_capability_hash": current[
                "runtime_capability_hash"
            ],
            "action_plan_hash": action_hash,
            "action_plan_blob": action_blob,
            "required_action_count": 4 if actions else 0,
            "external_growth_reservation_bytes": (
                intent.external_growth_reservation_bytes
            ),
            "outcome_reservation_bytes": intent.outcome_reservation_bytes,
            "successor_reservation_bytes": intent.successor_reservation_bytes,
        }
        for index in range(1, 5):
            action = actions[index - 1] if actions else None
            effect[f"action_{index}_kind"] = action["kind"] if action else None
            effect[f"action_{index}_hash"] = (
                action["action_hash"] if action else None
            )
            effect[f"postcondition_{index}_hash"] = (
                action["postcondition_hash"] if action else None
            )
        effect["request_tuple_hash"] = registration_hashes.derive(
            "request_tuple_hash", effect
        )
        effect.update(
            {
                "created_operation_seq": None,
                "created_operation_id": None,
                "created_operation_hash": None,
                "outcome_kind": None,
                "outcome_helper_generation": None,
                "outcome_tuple_hash": None,
                "ledger_head_hash": None,
                "first_conflict_event_seq": None,
                "completion_blob": None,
                "completion_hash": None,
                "final_basis_hash": None,
                "proof_blob": None,
                "proof_hash": None,
                "certificate_inputs_blob": None,
                "certificate_inputs_hash": None,
                "certificate_hash": None,
                "conflict_code": None,
                "conflict_blob": None,
                "conflict_hash": None,
                "superseded_by_effect_id": None,
                "successor_transition_id": None,
                "outcome_operation_seq": None,
                "outcome_operation_id": None,
                "outcome_operation_hash": None,
            }
        )
        member: dict[str, Any] = {
            "member_id": member_id,
            "canonical_root": identity.canonical_root,
            "root_dev": identity.root_dev,
            "root_ino": identity.root_ino,
            "git_toplevel": identity.git_toplevel,
            "git_dir": identity.git_dir,
            "git_dir_dev": identity.git_dir_dev,
            "git_dir_ino": identity.git_dir_ino,
            "git_common_dir": identity.git_common_dir,
            "git_common_dev": identity.git_common_dev,
            "git_common_ino": identity.git_common_ino,
            "proof_dev": identity.proof_dev,
            "projection_dev": identity.projection_dev,
            "legacy_state_dev": identity.legacy_state_dev,
            "physical_basis_hash": identity.physical_basis_hash,
            "git_basis_hash": identity.git_basis_hash,
            "policy_basis_hash": identity.policy_basis_hash,
            "operation_basis_hash": identity.operation_basis_hash,
            "lifecycle_basis_hash": identity.lifecycle_basis_hash,
            "current_basis_hash": identity.current_basis_hash,
            "member_epoch": 1,
            "phase": "REQUESTED",
            "current_effect_id": effect_id,
            "runtime_subject_key": subject_key,
            "helper_generation": current["protocol_generation"],
            "current_outcome_kind": None,
            "current_completion_hash": None,
            "current_proof_hash": None,
            "current_certificate_hash": None,
            "current_conflict_hash": None,
            "pending_effect_id": None,
            "pending_member_epoch": None,
            "pending_basis_hash": None,
            "pending_effect_tuple_hash": None,
        }
        member["member_tuple_hash"] = registration_hashes.derive(
            "member_tuple_hash", member
        )
        writes = {
            (sqlite3.SQLITE_INSERT, "registration_operation_audit"),
            (sqlite3.SQLITE_INSERT, "registration_member"),
            (sqlite3.SQLITE_INSERT, "registration_effect"),
            (sqlite3.SQLITE_INSERT, "registration_runtime_status"),
        }
        with self._write_scope(writes):
            try:
                measured = self._begin()
                fresh_boot, fresh_mono = self._fresh_sample()
                if sample_boot_id is not None and (
                    fresh_boot,
                    fresh_mono,
                ) != (sample_boot_id, sample_mono_ns):
                    raise StaleAuthority("sample is not transaction-fresh")
                sample_boot_id, sample_mono_ns = fresh_boot, fresh_mono
                clean = intent.request_kind == "CLEAN_ELIGIBLE"
                status: dict[str, Any] = {
                    "subject_key": subject_key,
                    "member_id": member_id,
                    "member_epoch": 1,
                    "current_effect_id": effect_id,
                    "status_version": 1,
                    "schedule_boot_id": sample_boot_id if clean else None,
                    "observed_now_mono_ns": sample_mono_ns if clean else None,
                    "next_due_mono_ns": sample_mono_ns if clean else None,
                    "due_since_mono_ns": sample_mono_ns if clean else None,
                    "attempt_count": 0 if clean else None,
                    "backoff_ns": 0 if clean else None,
                    "help_due": 0,
                    "executor_token_hash": None,
                    "executor_boot_id": None,
                    "executor_generation": None,
                    "unavailable_count": 0,
                    "yield_count": 0,
                    "blocked_basis_fingerprint": (
                        None if clean else intent.blocked_basis_fingerprint
                    ),
                    "reason_code": (
                        "REGISTRATION_REQUIRED"
                        if clean
                        else (
                            "DIRTY_UNSUPPORTED"
                            if intent.request_kind == "BLOCKED_DIRTY"
                            else "GIT_OPERATION_UNSUPPORTED"
                        )
                    ),
                }
                status["status_hash"] = registration_hashes.derive(
                    "status_hash", status
                )
                operation = self._operation_base(
                    operation_id=operation_id,
                    operation_class="DATA",
                    operation_kind="INSTALL_MEMBER",
                    measured_free_bytes=measured,
                    projected_db_growth_bytes=projected_db_growth_bytes,
                    candidate=candidate,
                    control=None,
                    data=data,
                    overrides={
                        "target_member_id": member_id,
                        "target_successor_effect_id": effect_id,
                        "target_subject_key": subject_key,
                        "target_member_epoch": 1,
                        "target_basis_hash": identity.current_basis_hash,
                        "target_successor_member_epoch": 1,
                        "target_successor_basis_hash": intent.request_basis_hash,
                        "target_member_tuple_hash": member["member_tuple_hash"],
                        "target_effect_tuple_hash": effect["request_tuple_hash"],
                        "target_action_plan_hash": action_hash,
                        "target_status_hash": status["status_hash"],
                        "sample_boot_id": sample_boot_id,
                        "sample_mono_ns": sample_mono_ns,
                        "new_external_reservation_bytes": (
                            intent.external_growth_reservation_bytes
                        ),
                        "new_outcome_reservation_bytes": (
                            intent.outcome_reservation_bytes
                        ),
                        "new_successor_reservation_bytes": (
                            intent.successor_reservation_bytes
                        ),
                    },
                )
                for row in (member, effect, status):
                    if row is effect:
                        row["created_operation_seq"] = operation["operation_seq"]
                        row["created_operation_id"] = operation_id
                        row["created_operation_hash"] = operation[
                            "operation_envelope_hash"
                        ]
                    else:
                        row["write_operation_seq"] = operation["operation_seq"]
                        row["write_operation_id"] = operation_id
                        row["write_operation_hash"] = operation[
                            "operation_envelope_hash"
                        ]
                self._insert("registration_operation_audit", operation)
                self._insert("registration_member", member)
                self._insert("registration_effect", effect)
                self._insert("registration_runtime_status", status)
                closure = self._connection.execute(
                    "SELECT 1 FROM registration_member m "
                    "JOIN registration_effect e ON e.effect_id=m.current_effect_id "
                    "JOIN registration_runtime_status s ON s.member_id=m.member_id "
                    "WHERE m.member_id=? AND m.member_tuple_hash=? "
                    "AND e.request_tuple_hash=? AND s.status_hash=? "
                    "AND m.write_operation_id=? AND e.created_operation_id=? "
                    "AND s.write_operation_id=?",
                    (
                        member_id,
                        member["member_tuple_hash"],
                        effect["request_tuple_hash"],
                        status["status_hash"],
                        operation_id,
                        operation_id,
                        operation_id,
                    ),
                ).fetchone()
                if closure is None:
                    raise StoreError("INSTALL_MEMBER closure failed")
                self._commit()
                self._tighten_files()
                return OperationResult(
                    "COMMITTED",
                    operation_id,
                    operation["operation_envelope_hash"],
                    member["member_tuple_hash"],
                )
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def bind_episode(
        self,
        data: DataCapability,
        candidate: ProtocolCandidate,
        *,
        member_id: str,
        source: EpisodeSource,
        operation_id: str | None = None,
        projected_db_growth_bytes: int = 0,
    ) -> OperationResult:
        self._require_data(data, candidate)
        current = self._require_current_candidate(candidate, mode="WRITABLE")
        _require_hash(member_id, "member_id")
        operation_id = operation_id or self._operation_ids()
        with self._locks.acquire_member(member_id) as held:
            held.verify()
            with self._write_scope(
                {
                    (sqlite3.SQLITE_INSERT, "registration_operation_audit"),
                    (sqlite3.SQLITE_INSERT, "registration_episode"),
                }
            ):
                try:
                    measured = self._begin()
                    member = self._connection.execute(
                        "SELECT member_tuple_hash FROM registration_member "
                        "WHERE member_id=?",
                        (member_id,),
                    ).fetchone()
                    if member is None:
                        raise StaleAuthority("episode member missing")
                    episode_id = registration_hashes.deterministic_id(
                        "awa-reg-episode-v1",
                        source.conversation_id,
                        source.generation_id,
                        source.source_contract,
                        source.source_event,
                        str(current["protocol_generation"]),
                        member_id,
                        source.workspace_roots_hash,
                        current["tool_inventory_hash"],
                        current["hook_projection_hash"],
                    )
                    episode: dict[str, Any] = {
                        "episode_id": episode_id,
                        "conversation_id": source.conversation_id,
                        "generation_id": source.generation_id,
                        "source_contract": source.source_contract,
                        "source_event": source.source_event,
                        "protocol_generation": current["protocol_generation"],
                        "member_id": member_id,
                        "workspace_root_count": 1,
                        "workspace_roots_hash": source.workspace_roots_hash,
                        "tool_inventory_hash": current["tool_inventory_hash"],
                        "hook_projection_hash": current[
                            "hook_projection_hash"
                        ],
                        "created_wall_ns": self._wall_ns(),
                    }
                    episode["envelope_hash"] = registration_hashes.derive(
                        "episode_envelope_hash", episode
                    )
                    operation = self._operation_base(
                        operation_id=operation_id,
                        operation_class="DATA",
                        operation_kind="BIND_EPISODE",
                        measured_free_bytes=measured,
                        projected_db_growth_bytes=projected_db_growth_bytes,
                        candidate=candidate,
                        control=None,
                        data=data,
                        overrides={
                            "target_member_id": member_id,
                            "target_episode_id": episode_id,
                            "target_episode_hash": episode["envelope_hash"],
                        },
                    )
                    episode["write_operation_seq"] = operation["operation_seq"]
                    episode["write_operation_id"] = operation_id
                    episode["write_operation_hash"] = operation[
                        "operation_envelope_hash"
                    ]
                    self._insert("registration_operation_audit", operation)
                    self._insert("registration_episode", episode)
                    closure = self._connection.execute(
                        "SELECT 1 FROM registration_episode "
                        "WHERE episode_id=? AND envelope_hash=? "
                        "AND write_operation_id=?",
                        (episode_id, episode["envelope_hash"], operation_id),
                    ).fetchone()
                    if closure is None:
                        raise StoreError("BIND_EPISODE closure failed")
                    self._commit()
                    self._tighten_files()
                    return OperationResult(
                        "COMMITTED",
                        operation_id,
                        operation["operation_envelope_hash"],
                        episode["envelope_hash"],
                    )
                except Exception:
                    if self._connection.in_transaction:
                        self._connection.execute("ROLLBACK")
                    raise

    def invalidate_requested(
        self,
        data: DataCapability,
        candidate: ProtocolCandidate,
        *,
        member_id: str,
        expected_member_hash: str,
        expected_effect_hash: str,
        expected_status_hash: str,
        basis: BasisUpdate,
        intent: EffectIntent,
        operation_id: str | None = None,
        projected_db_growth_bytes: int = 0,
    ) -> OperationResult:
        self._require_data(data, candidate)
        self._require_current_candidate(candidate, mode="WRITABLE")
        if basis.current_basis_hash != intent.request_basis_hash:
            raise ValueError("successor basis/effect mismatch")
        operation_id = operation_id or self._operation_ids()
        with self._locks.acquire_member(member_id) as held:
            held.verify()
            with self._write_scope(
                {
                    (sqlite3.SQLITE_INSERT, "registration_operation_audit"),
                    (sqlite3.SQLITE_INSERT, "registration_effect"),
                    (sqlite3.SQLITE_UPDATE, "registration_effect"),
                    (sqlite3.SQLITE_UPDATE, "registration_runtime_status"),
                    (sqlite3.SQLITE_UPDATE, "registration_member"),
                }
            ):
                try:
                    measured = self._begin()
                    sample_boot_id, sample_mono_ns = self._fresh_sample()
                    current = self._require_current_candidate(
                        candidate, mode="WRITABLE"
                    )
                    member = dict(
                        self._connection.execute(
                            "SELECT * FROM registration_member WHERE member_id=?",
                            (member_id,),
                        ).fetchone()
                    )
                    old_effect = dict(
                        self._connection.execute(
                            "SELECT * FROM registration_effect WHERE effect_id=?",
                            (member["current_effect_id"],),
                        ).fetchone()
                    )
                    old_status = dict(
                        self._connection.execute(
                            "SELECT * FROM registration_runtime_status "
                            "WHERE member_id=?",
                            (member_id,),
                        ).fetchone()
                    )
                    if (
                        member["phase"] != "REQUESTED"
                        or member["member_tuple_hash"] != expected_member_hash
                        or old_effect["request_tuple_hash"]
                        != expected_effect_hash
                        or old_status["status_hash"] != expected_status_hash
                        or old_status["executor_token_hash"] is not None
                    ):
                        raise StaleAuthority("INVALIDATE_REQUESTED stale tuple")
                    equivalent = self._build_effect(
                        member_id=member_id,
                        member_epoch=member["member_epoch"],
                        predecessor_effect_id=old_effect[
                            "predecessor_effect_id"
                        ],
                        intent=intent,
                        protocol_generation=current["protocol_generation"],
                        runtime_capability_hash=current[
                            "runtime_capability_hash"
                        ],
                    )
                    if (
                        equivalent["request_basis_hash"]
                        == member["current_basis_hash"]
                        and equivalent["request_tuple_hash"]
                        == old_effect["request_tuple_hash"]
                    ):
                        self._connection.execute("ROLLBACK")
                        return OperationResult(
                            "NOOP",
                            operation_id,
                            ZERO_HASH,
                            member["member_tuple_hash"],
                        )
                    new_epoch = int(member["member_epoch"]) + 1
                    successor = self._build_effect(
                        member_id=member_id,
                        member_epoch=new_epoch,
                        predecessor_effect_id=old_effect["effect_id"],
                        intent=intent,
                        protocol_generation=current["protocol_generation"],
                        runtime_capability_hash=current[
                            "runtime_capability_hash"
                        ],
                    )
                    status = self._requested_status(
                        old_status,
                        member_epoch=new_epoch,
                        effect=successor,
                        sample_boot_id=sample_boot_id,
                        sample_mono_ns=sample_mono_ns,
                        version=int(old_status["status_version"]) + 1,
                    )
                    member_target = dict(member)
                    member_target.update(
                        {
                            "policy_basis_hash": basis.policy_basis_hash,
                            "operation_basis_hash": basis.operation_basis_hash,
                            "lifecycle_basis_hash": basis.lifecycle_basis_hash,
                            "current_basis_hash": basis.current_basis_hash,
                            "member_epoch": new_epoch,
                            "phase": "REQUESTED",
                            "current_effect_id": successor["effect_id"],
                            "helper_generation": current[
                                "protocol_generation"
                            ],
                            "current_outcome_kind": None,
                            "current_completion_hash": None,
                            "current_proof_hash": None,
                            "current_certificate_hash": None,
                            "current_conflict_hash": None,
                            "pending_effect_id": None,
                            "pending_member_epoch": None,
                            "pending_basis_hash": None,
                            "pending_effect_tuple_hash": None,
                        }
                    )
                    member_target["member_tuple_hash"] = (
                        registration_hashes.derive(
                            "member_tuple_hash", member_target
                        )
                    )
                    transition_id = self._successor_transition_id(
                        operation_kind="INVALIDATE_REQUESTED",
                        cause="BASIS_CHANGED",
                        old_member_hash=member["member_tuple_hash"],
                        old_status_hash=old_status["status_hash"],
                        old_effect_hash=old_effect["request_tuple_hash"],
                        new_member_hash=member_target["member_tuple_hash"],
                        new_status_hash=status["status_hash"],
                        new_effect_hash=successor["request_tuple_hash"],
                        old_epoch=member["member_epoch"],
                        old_basis=member["current_basis_hash"],
                        new_epoch=new_epoch,
                        new_basis=basis.current_basis_hash,
                        old_effect_id=old_effect["effect_id"],
                        new_effect_id=successor["effect_id"],
                    )
                    old_effect_target = dict(old_effect)
                    old_effect_target.update(
                        {
                            "outcome_kind": "SUPERSEDED",
                            "outcome_helper_generation": None,
                            "ledger_head_hash": None,
                            "first_conflict_event_seq": None,
                            "completion_blob": None,
                            "completion_hash": None,
                            "final_basis_hash": None,
                            "proof_blob": None,
                            "proof_hash": None,
                            "certificate_inputs_blob": None,
                            "certificate_inputs_hash": None,
                            "certificate_hash": None,
                            "conflict_code": None,
                            "conflict_blob": None,
                            "conflict_hash": None,
                            "superseded_by_effect_id": successor["effect_id"],
                            "successor_transition_id": transition_id,
                        }
                    )
                    old_effect_target["outcome_tuple_hash"] = (
                        registration_hashes.derive(
                            "outcome_tuple_hash", old_effect_target
                        )
                    )
                    operation = self._operation_base(
                        operation_id=operation_id,
                        operation_class="DATA",
                        operation_kind="INVALIDATE_REQUESTED",
                        measured_free_bytes=measured,
                        projected_db_growth_bytes=projected_db_growth_bytes,
                        candidate=candidate,
                        control=None,
                        data=data,
                        overrides={
                            "target_member_id": member_id,
                            "target_effect_id": old_effect["effect_id"],
                            "target_successor_effect_id": successor["effect_id"],
                            "expected_target_status_hash": old_status[
                                "status_hash"
                            ],
                            "target_transition_id": transition_id,
                            "target_subject_key": status["subject_key"],
                            "expected_target_member_tuple_hash": member[
                                "member_tuple_hash"
                            ],
                            "expected_target_effect_tuple_hash": old_effect[
                                "request_tuple_hash"
                            ],
                            "target_member_epoch": new_epoch,
                            "target_basis_hash": basis.current_basis_hash,
                            "target_successor_member_epoch": new_epoch,
                            "target_successor_basis_hash": basis.current_basis_hash,
                            "target_member_tuple_hash": member_target[
                                "member_tuple_hash"
                            ],
                            "target_effect_tuple_hash": successor[
                                "request_tuple_hash"
                            ],
                            "target_effect_outcome_hash": old_effect_target[
                                "outcome_tuple_hash"
                            ],
                            "target_action_plan_hash": successor[
                                "action_plan_hash"
                            ],
                            "target_cause_code": "BASIS_CHANGED",
                            "target_status_hash": status["status_hash"],
                            "sample_boot_id": sample_boot_id,
                            "sample_mono_ns": sample_mono_ns,
                            "new_external_reservation_bytes": successor[
                                "external_growth_reservation_bytes"
                            ],
                            "new_outcome_reservation_bytes": successor[
                                "outcome_reservation_bytes"
                            ],
                            "new_successor_reservation_bytes": successor[
                                "successor_reservation_bytes"
                            ],
                        },
                    )
                    successor["created_operation_seq"] = operation["operation_seq"]
                    successor["created_operation_id"] = operation_id
                    successor["created_operation_hash"] = operation[
                        "operation_envelope_hash"
                    ]
                    old_effect_target["outcome_operation_seq"] = operation[
                        "operation_seq"
                    ]
                    old_effect_target["outcome_operation_id"] = operation_id
                    old_effect_target["outcome_operation_hash"] = operation[
                        "operation_envelope_hash"
                    ]
                    for row in (status, member_target):
                        row["write_operation_seq"] = operation["operation_seq"]
                        row["write_operation_id"] = operation_id
                        row["write_operation_hash"] = operation[
                            "operation_envelope_hash"
                        ]
                    self._insert("registration_operation_audit", operation)
                    self._insert("registration_effect", successor)
                    self._update_row(
                        "registration_effect",
                        old_effect_target,
                        primary_key="effect_id",
                        expected_column="outcome_kind",
                        expected_value=None,
                    )
                    self._update_row(
                        "registration_runtime_status",
                        status,
                        primary_key="subject_key",
                        expected_column="status_hash",
                        expected_value=old_status["status_hash"],
                    )
                    self._update_row(
                        "registration_member",
                        member_target,
                        primary_key="member_id",
                        expected_column="member_tuple_hash",
                        expected_value=member["member_tuple_hash"],
                    )
                    self._commit()
                    self._tighten_files()
                    return OperationResult(
                        "COMMITTED",
                        operation_id,
                        operation["operation_envelope_hash"],
                        member_target["member_tuple_hash"],
                    )
                except Exception:
                    if self._connection.in_transaction:
                        self._connection.execute("ROLLBACK")
                    raise

    def set_pending(
        self,
        data: DataCapability,
        candidate: ProtocolCandidate,
        *,
        member_id: str,
        expected_member_hash: str,
        expected_effect_hash: str,
        expected_status_hash: str,
        basis_hash: str,
        intent: EffectIntent,
        operation_id: str | None = None,
    ) -> OperationResult:
        return self._change_pending(
            data,
            candidate,
            member_id=member_id,
            expected_member_hash=expected_member_hash,
            expected_effect_hash=expected_effect_hash,
            expected_status_hash=expected_status_hash,
            basis_hash=basis_hash,
            intent=intent,
            replace=False,
            operation_id=operation_id,
        )

    def replace_pending(
        self,
        data: DataCapability,
        candidate: ProtocolCandidate,
        *,
        member_id: str,
        expected_member_hash: str,
        expected_effect_hash: str,
        expected_status_hash: str,
        basis_hash: str,
        intent: EffectIntent,
        operation_id: str | None = None,
    ) -> OperationResult:
        return self._change_pending(
            data,
            candidate,
            member_id=member_id,
            expected_member_hash=expected_member_hash,
            expected_effect_hash=expected_effect_hash,
            expected_status_hash=expected_status_hash,
            basis_hash=basis_hash,
            intent=intent,
            replace=True,
            operation_id=operation_id,
        )

    def _change_pending(
        self,
        data: DataCapability,
        candidate: ProtocolCandidate,
        *,
        member_id: str,
        expected_member_hash: str,
        expected_effect_hash: str,
        expected_status_hash: str,
        basis_hash: str,
        intent: EffectIntent,
        replace: bool,
        operation_id: str | None,
    ) -> OperationResult:
        self._require_data(data, candidate)
        self._require_current_candidate(candidate, mode="WRITABLE")
        _require_hash(basis_hash, "basis_hash")
        if basis_hash != intent.request_basis_hash:
            raise ValueError("pending basis/effect mismatch")
        operation_kind = "REPLACE_PENDING" if replace else "SET_PENDING"
        operation_id = operation_id or self._operation_ids()
        with self._locks.acquire_member(member_id) as held:
            held.verify()
            with self._write_scope(
                {
                    (sqlite3.SQLITE_INSERT, "registration_operation_audit"),
                    (sqlite3.SQLITE_INSERT, "registration_effect"),
                    (sqlite3.SQLITE_UPDATE, "registration_effect"),
                    (sqlite3.SQLITE_UPDATE, "registration_member"),
                }
            ):
                try:
                    measured = self._begin()
                    current = self._require_current_candidate(
                        candidate, mode="WRITABLE"
                    )
                    member = dict(
                        self._connection.execute(
                            "SELECT * FROM registration_member WHERE member_id=?",
                            (member_id,),
                        ).fetchone()
                    )
                    status = dict(
                        self._connection.execute(
                            "SELECT * FROM registration_runtime_status "
                            "WHERE member_id=?",
                            (member_id,),
                        ).fetchone()
                    )
                    active = dict(
                        self._connection.execute(
                            "SELECT * FROM registration_effect WHERE effect_id=?",
                            (member["current_effect_id"],),
                        ).fetchone()
                    )
                    old_pending = None
                    expected_source = active
                    if replace and member["pending_effect_id"] is not None:
                        old_pending = dict(
                            self._connection.execute(
                                "SELECT * FROM registration_effect "
                                "WHERE effect_id=?",
                                (member["pending_effect_id"],),
                            ).fetchone()
                        )
                        expected_source = old_pending
                    if (
                        member["phase"] != "EFFECT_IN_FLIGHT"
                        or member["member_tuple_hash"] != expected_member_hash
                        or expected_source["request_tuple_hash"]
                        != expected_effect_hash
                        or status["status_hash"] != expected_status_hash
                        or (replace and old_pending is None)
                        or (not replace and member["pending_effect_id"] is not None)
                    ):
                        raise StaleAuthority(f"{operation_kind} stale tuple")
                    base_epoch = (
                        int(member["pending_member_epoch"])
                        if replace
                        else int(member["member_epoch"])
                    )
                    predecessor_id = (
                        old_pending["effect_id"]
                        if old_pending is not None
                        else active["effect_id"]
                    )
                    probe = self._build_effect(
                        member_id=member_id,
                        member_epoch=base_epoch,
                        predecessor_effect_id=(
                            old_pending["predecessor_effect_id"]
                            if old_pending is not None
                            else active["effect_id"]
                        ),
                        intent=intent,
                        protocol_generation=current["protocol_generation"],
                        runtime_capability_hash=current[
                            "runtime_capability_hash"
                        ],
                    )
                    if (
                        probe["request_basis_hash"]
                        == (
                            member["pending_basis_hash"]
                            if replace
                            else member["current_basis_hash"]
                        )
                        and probe["request_tuple_hash"]
                        == expected_source["request_tuple_hash"]
                    ):
                        self._connection.execute("ROLLBACK")
                        return OperationResult(
                            "NOOP",
                            operation_id,
                            ZERO_HASH,
                            member["member_tuple_hash"],
                        )
                    new_epoch = base_epoch + 1
                    successor = self._build_effect(
                        member_id=member_id,
                        member_epoch=new_epoch,
                        predecessor_effect_id=predecessor_id,
                        intent=intent,
                        protocol_generation=current["protocol_generation"],
                        runtime_capability_hash=current[
                            "runtime_capability_hash"
                        ],
                    )
                    member_target = dict(member)
                    member_target.update(
                        {
                            "pending_effect_id": successor["effect_id"],
                            "pending_member_epoch": new_epoch,
                            "pending_basis_hash": basis_hash,
                            "pending_effect_tuple_hash": successor[
                                "request_tuple_hash"
                            ],
                        }
                    )
                    member_target["member_tuple_hash"] = (
                        registration_hashes.derive(
                            "member_tuple_hash", member_target
                        )
                    )
                    transition_id = None
                    old_pending_target = None
                    if old_pending is not None:
                        transition_id = self._successor_transition_id(
                            operation_kind=operation_kind,
                            cause="PENDING_REPLACED",
                            old_member_hash=member["member_tuple_hash"],
                            old_status_hash=status["status_hash"],
                            old_effect_hash=old_pending["request_tuple_hash"],
                            new_member_hash=member_target["member_tuple_hash"],
                            new_status_hash=status["status_hash"],
                            new_effect_hash=successor["request_tuple_hash"],
                            old_epoch=old_pending["member_epoch"],
                            old_basis=old_pending["request_basis_hash"],
                            new_epoch=new_epoch,
                            new_basis=basis_hash,
                            old_effect_id=old_pending["effect_id"],
                            new_effect_id=successor["effect_id"],
                        )
                        old_pending_target = dict(old_pending)
                        old_pending_target.update(
                            {
                                "outcome_kind": "SUPERSEDED",
                                "outcome_helper_generation": None,
                                "outcome_tuple_hash": None,
                                "ledger_head_hash": None,
                                "first_conflict_event_seq": None,
                                "completion_blob": None,
                                "completion_hash": None,
                                "final_basis_hash": None,
                                "proof_blob": None,
                                "proof_hash": None,
                                "certificate_inputs_blob": None,
                                "certificate_inputs_hash": None,
                                "certificate_hash": None,
                                "conflict_code": None,
                                "conflict_blob": None,
                                "conflict_hash": None,
                                "superseded_by_effect_id": successor[
                                    "effect_id"
                                ],
                                "successor_transition_id": transition_id,
                            }
                        )
                        old_pending_target["outcome_tuple_hash"] = (
                            registration_hashes.derive(
                                "outcome_tuple_hash", old_pending_target
                            )
                        )
                    operation = self._operation_base(
                        operation_id=operation_id,
                        operation_class="DATA",
                        operation_kind=operation_kind,
                        measured_free_bytes=measured,
                        projected_db_growth_bytes=0,
                        candidate=candidate,
                        control=None,
                        data=data,
                        overrides={
                            "target_member_id": member_id,
                            "target_effect_id": expected_source["effect_id"],
                            "target_successor_effect_id": successor["effect_id"],
                            "expected_target_status_hash": status["status_hash"],
                            "target_transition_id": transition_id,
                            "expected_target_member_tuple_hash": member[
                                "member_tuple_hash"
                            ],
                            "expected_target_effect_tuple_hash": expected_source[
                                "request_tuple_hash"
                            ],
                            "target_member_epoch": member["member_epoch"],
                            "target_basis_hash": member["current_basis_hash"],
                            "target_successor_member_epoch": new_epoch,
                            "target_successor_basis_hash": basis_hash,
                            "target_member_tuple_hash": member_target[
                                "member_tuple_hash"
                            ],
                            "target_effect_tuple_hash": successor[
                                "request_tuple_hash"
                            ],
                            "target_effect_outcome_hash": (
                                old_pending_target["outcome_tuple_hash"]
                                if old_pending_target
                                else None
                            ),
                            "target_action_plan_hash": successor[
                                "action_plan_hash"
                            ],
                            "target_cause_code": (
                                "PENDING_REPLACED" if replace else None
                            ),
                            "target_status_hash": status["status_hash"],
                            "new_external_reservation_bytes": successor[
                                "external_growth_reservation_bytes"
                            ],
                            "new_outcome_reservation_bytes": successor[
                                "outcome_reservation_bytes"
                            ],
                            "new_successor_reservation_bytes": successor[
                                "successor_reservation_bytes"
                            ],
                        },
                    )
                    successor["created_operation_seq"] = operation["operation_seq"]
                    successor["created_operation_id"] = operation_id
                    successor["created_operation_hash"] = operation[
                        "operation_envelope_hash"
                    ]
                    member_target["write_operation_seq"] = operation[
                        "operation_seq"
                    ]
                    member_target["write_operation_id"] = operation_id
                    member_target["write_operation_hash"] = operation[
                        "operation_envelope_hash"
                    ]
                    if old_pending_target is not None:
                        old_pending_target["outcome_operation_seq"] = operation[
                            "operation_seq"
                        ]
                        old_pending_target["outcome_operation_id"] = operation_id
                        old_pending_target["outcome_operation_hash"] = operation[
                            "operation_envelope_hash"
                        ]
                    self._insert("registration_operation_audit", operation)
                    self._insert("registration_effect", successor)
                    if old_pending_target is not None:
                        self._update_row(
                            "registration_effect",
                            old_pending_target,
                            primary_key="effect_id",
                            expected_column="outcome_kind",
                            expected_value=None,
                        )
                    self._update_row(
                        "registration_member",
                        member_target,
                        primary_key="member_id",
                        expected_column="member_tuple_hash",
                        expected_value=member["member_tuple_hash"],
                    )
                    self._commit()
                    self._tighten_files()
                    return OperationResult(
                        "COMMITTED",
                        operation_id,
                        operation["operation_envelope_hash"],
                        member_target["member_tuple_hash"],
                    )
                except Exception:
                    if self._connection.in_transaction:
                        self._connection.execute("ROLLBACK")
                    raise

    def handoff_resolved(
        self,
        data: DataCapability,
        candidate: ProtocolCandidate,
        *,
        member_id: str,
        expected_member_hash: str,
        expected_effect_hash: str,
        expected_status_hash: str,
        cause: str | None = None,
        basis: BasisUpdate | None = None,
        intent: EffectIntent | None = None,
        operation_id: str | None = None,
    ) -> OperationResult:
        self._require_data(data, candidate)
        self._require_current_candidate(candidate, mode="WRITABLE")
        if cause not in {
            None,
            "BASIS_CHANGED",
            "CURRENT_CLOSURE_CHANGED",
            "EXPLICIT_CONFLICT_RETRY",
        }:
            raise ValueError("invalid handoff cause")
        operation_id = operation_id or self._operation_ids()
        with self._locks.acquire_member(member_id) as held:
            held.verify()
            with self._write_scope(
                {
                    (sqlite3.SQLITE_INSERT, "registration_operation_audit"),
                    (sqlite3.SQLITE_INSERT, "registration_effect"),
                    (sqlite3.SQLITE_UPDATE, "registration_runtime_status"),
                    (sqlite3.SQLITE_UPDATE, "registration_member"),
                }
            ):
                try:
                    measured = self._begin()
                    sample_boot_id, sample_mono_ns = self._fresh_sample()
                    current = self._require_current_candidate(
                        candidate, mode="WRITABLE"
                    )
                    member = dict(
                        self._connection.execute(
                            "SELECT * FROM registration_member WHERE member_id=?",
                            (member_id,),
                        ).fetchone()
                    )
                    old_effect = dict(
                        self._connection.execute(
                            "SELECT * FROM registration_effect WHERE effect_id=?",
                            (member["current_effect_id"],),
                        ).fetchone()
                    )
                    old_status = dict(
                        self._connection.execute(
                            "SELECT * FROM registration_runtime_status "
                            "WHERE member_id=?",
                            (member_id,),
                        ).fetchone()
                    )
                    if (
                        member["phase"] != "RESOLVED"
                        or member["member_tuple_hash"] != expected_member_hash
                        or old_effect["outcome_tuple_hash"]
                        != expected_effect_hash
                        or old_status["status_hash"] != expected_status_hash
                    ):
                        raise StaleAuthority("HANDOFF_RESOLVED stale tuple")
                    successor: dict[str, Any]
                    created = False
                    applied_basis: BasisUpdate
                    if member["pending_effect_id"] is not None:
                        if cause not in {None, "BASIS_CHANGED"}:
                            raise StaleAuthority(
                                "pending handoff uses BASIS_CHANGED cause"
                            )
                        cause = "BASIS_CHANGED"
                        successor = dict(
                            self._connection.execute(
                                "SELECT * FROM registration_effect "
                                "WHERE effect_id=?",
                                (member["pending_effect_id"],),
                            ).fetchone()
                        )
                        applied_basis = BasisUpdate(
                            policy_basis_hash=(
                                basis.policy_basis_hash
                                if basis
                                else member["policy_basis_hash"]
                            ),
                            operation_basis_hash=(
                                basis.operation_basis_hash
                                if basis
                                else member["operation_basis_hash"]
                            ),
                            lifecycle_basis_hash=(
                                basis.lifecycle_basis_hash
                                if basis
                                else member["lifecycle_basis_hash"]
                            ),
                            current_basis_hash=member["pending_basis_hash"],
                        )
                        new_epoch = member["pending_member_epoch"]
                    else:
                        if cause is None or basis is None or intent is None:
                            self._connection.execute("ROLLBACK")
                            return OperationResult(
                                "NOOP",
                                operation_id,
                                ZERO_HASH,
                                member["member_tuple_hash"],
                            )
                        if basis.current_basis_hash != intent.request_basis_hash:
                            raise ValueError("handoff basis/effect mismatch")
                        if (
                            cause != "EXPLICIT_CONFLICT_RETRY"
                            and basis.current_basis_hash
                            == member["current_basis_hash"]
                        ):
                            self._connection.execute("ROLLBACK")
                            return OperationResult(
                                "NOOP",
                                operation_id,
                                ZERO_HASH,
                                member["member_tuple_hash"],
                            )
                        if (
                            cause == "EXPLICIT_CONFLICT_RETRY"
                            and member["current_outcome_kind"]
                            != "LOGICAL_CONFLICT"
                        ):
                            raise StaleAuthority(
                                "explicit retry requires logical conflict"
                            )
                        new_epoch = int(member["member_epoch"]) + 1
                        successor = self._build_effect(
                            member_id=member_id,
                            member_epoch=new_epoch,
                            predecessor_effect_id=old_effect["effect_id"],
                            intent=intent,
                            protocol_generation=current[
                                "protocol_generation"
                            ],
                            runtime_capability_hash=current[
                                "runtime_capability_hash"
                            ],
                        )
                        applied_basis = basis
                        created = True
                    status = self._requested_status(
                        old_status,
                        member_epoch=new_epoch,
                        effect=successor,
                        sample_boot_id=sample_boot_id,
                        sample_mono_ns=sample_mono_ns,
                        version=int(old_status["status_version"]) + 1,
                    )
                    member_target = dict(member)
                    member_target.update(
                        {
                            "policy_basis_hash": (
                                applied_basis.policy_basis_hash
                            ),
                            "operation_basis_hash": (
                                applied_basis.operation_basis_hash
                            ),
                            "lifecycle_basis_hash": (
                                applied_basis.lifecycle_basis_hash
                            ),
                            "current_basis_hash": (
                                applied_basis.current_basis_hash
                            ),
                            "member_epoch": new_epoch,
                            "phase": "REQUESTED",
                            "current_effect_id": successor["effect_id"],
                            "helper_generation": successor[
                                "required_protocol_generation"
                            ],
                            "current_outcome_kind": None,
                            "current_completion_hash": None,
                            "current_proof_hash": None,
                            "current_certificate_hash": None,
                            "current_conflict_hash": None,
                            "pending_effect_id": None,
                            "pending_member_epoch": None,
                            "pending_basis_hash": None,
                            "pending_effect_tuple_hash": None,
                        }
                    )
                    member_target["member_tuple_hash"] = (
                        registration_hashes.derive(
                            "member_tuple_hash", member_target
                        )
                    )
                    transition_id = self._successor_transition_id(
                        operation_kind="HANDOFF_RESOLVED",
                        cause=cause,
                        old_member_hash=member["member_tuple_hash"],
                        old_status_hash=old_status["status_hash"],
                        old_effect_hash=old_effect["outcome_tuple_hash"],
                        new_member_hash=member_target["member_tuple_hash"],
                        new_status_hash=status["status_hash"],
                        new_effect_hash=successor["request_tuple_hash"],
                        old_epoch=member["member_epoch"],
                        old_basis=member["current_basis_hash"],
                        new_epoch=new_epoch,
                        new_basis=applied_basis.current_basis_hash,
                        old_effect_id=old_effect["effect_id"],
                        new_effect_id=successor["effect_id"],
                    )
                    operation = self._operation_base(
                        operation_id=operation_id,
                        operation_class="DATA",
                        operation_kind="HANDOFF_RESOLVED",
                        measured_free_bytes=measured,
                        projected_db_growth_bytes=0,
                        candidate=candidate,
                        control=None,
                        data=data,
                        overrides={
                            "target_member_id": member_id,
                            "target_effect_id": old_effect["effect_id"],
                            "target_successor_effect_id": successor["effect_id"],
                            "expected_target_status_hash": old_status[
                                "status_hash"
                            ],
                            "target_transition_id": transition_id,
                            "target_subject_key": status["subject_key"],
                            "expected_target_member_tuple_hash": member[
                                "member_tuple_hash"
                            ],
                            "expected_target_effect_tuple_hash": old_effect[
                                "outcome_tuple_hash"
                            ],
                            "target_member_epoch": new_epoch,
                            "target_basis_hash": applied_basis.current_basis_hash,
                            "target_successor_member_epoch": new_epoch,
                            "target_successor_basis_hash": (
                                applied_basis.current_basis_hash
                            ),
                            "target_member_tuple_hash": member_target[
                                "member_tuple_hash"
                            ],
                            "target_effect_tuple_hash": successor[
                                "request_tuple_hash"
                            ],
                            "target_action_plan_hash": successor[
                                "action_plan_hash"
                            ],
                            "target_cause_code": cause,
                            "target_status_hash": status["status_hash"],
                            "sample_boot_id": sample_boot_id,
                            "sample_mono_ns": sample_mono_ns,
                            "new_external_reservation_bytes": (
                                successor["external_growth_reservation_bytes"]
                                if created
                                else 0
                            ),
                            "new_outcome_reservation_bytes": (
                                successor["outcome_reservation_bytes"]
                                if created
                                else 0
                            ),
                            "new_successor_reservation_bytes": (
                                successor["successor_reservation_bytes"]
                                if created
                                else 0
                            ),
                        },
                    )
                    if created:
                        successor["created_operation_seq"] = operation[
                            "operation_seq"
                        ]
                        successor["created_operation_id"] = operation_id
                        successor["created_operation_hash"] = operation[
                            "operation_envelope_hash"
                        ]
                    for row in (status, member_target):
                        row["write_operation_seq"] = operation["operation_seq"]
                        row["write_operation_id"] = operation_id
                        row["write_operation_hash"] = operation[
                            "operation_envelope_hash"
                        ]
                    self._insert("registration_operation_audit", operation)
                    if created:
                        self._insert("registration_effect", successor)
                    self._update_row(
                        "registration_runtime_status",
                        status,
                        primary_key="subject_key",
                        expected_column="status_hash",
                        expected_value=old_status["status_hash"],
                    )
                    self._update_row(
                        "registration_member",
                        member_target,
                        primary_key="member_id",
                        expected_column="member_tuple_hash",
                        expected_value=member["member_tuple_hash"],
                    )
                    self._commit()
                    self._tighten_files()
                    return OperationResult(
                        "COMMITTED",
                        operation_id,
                        operation["operation_envelope_hash"],
                        member_target["member_tuple_hash"],
                    )
                except Exception:
                    if self._connection.in_transaction:
                        self._connection.execute("ROLLBACK")
                    raise

    def reboot_status(
        self,
        data: DataCapability,
        candidate: ProtocolCandidate,
        *,
        member_id: str,
        expected_status_hash: str,
        operation_id: str | None = None,
    ) -> OperationResult:
        self._require_data(data, candidate)
        self._require_current_candidate(candidate, mode="WRITABLE")
        operation_id = operation_id or self._operation_ids()
        with self._locks.acquire_member(member_id) as held:
            held.verify()
            with self._write_scope(
                {
                    (sqlite3.SQLITE_INSERT, "registration_operation_audit"),
                    (sqlite3.SQLITE_UPDATE, "registration_runtime_status"),
                }
            ):
                try:
                    measured = self._begin()
                    sample_boot_id, sample_mono_ns = self._fresh_sample()
                    member = dict(
                        self._connection.execute(
                            "SELECT * FROM registration_member WHERE member_id=?",
                            (member_id,),
                        ).fetchone()
                    )
                    effect = dict(
                        self._connection.execute(
                            "SELECT * FROM registration_effect WHERE effect_id=?",
                            (member["current_effect_id"],),
                        ).fetchone()
                    )
                    old = dict(
                        self._connection.execute(
                            "SELECT * FROM registration_runtime_status "
                            "WHERE member_id=?",
                            (member_id,),
                        ).fetchone()
                    )
                    if old["status_hash"] != expected_status_hash:
                        raise StaleAuthority("REBOOT_STATUS stale status")
                    stored_boot = (
                        old["executor_boot_id"]
                        if old["executor_token_hash"] is not None
                        else old["schedule_boot_id"]
                    )
                    if stored_boot is None or stored_boot == sample_boot_id:
                        raise StaleAuthority("REBOOT_STATUS requires old boot")
                    status = dict(old)
                    status.update(
                        {
                            "status_version": int(old["status_version"]) + 1,
                            "executor_token_hash": None,
                            "executor_boot_id": None,
                            "executor_generation": None,
                        }
                    )
                    scheduled = False
                    reason: str | None
                    blocked = old["blocked_basis_fingerprint"]
                    if member["phase"] == "REQUESTED":
                        if effect["request_kind"] == "CLEAN_ELIGIBLE":
                            scheduled = True
                            reason = "REGISTRATION_REQUIRED"
                            blocked = None
                        elif effect["request_kind"] == "BLOCKED_DIRTY":
                            reason = "DIRTY_UNSUPPORTED"
                        else:
                            reason = "GIT_OPERATION_UNSUPPORTED"
                    elif member["phase"] == "EFFECT_IN_FLIGHT":
                        scheduled = True
                        reason = "EFFECT_IN_FLIGHT"
                        blocked = None
                    elif member["pending_effect_id"] is not None:
                        scheduled = True
                        reason = "REGISTRATION_REQUIRED"
                        blocked = None
                    elif member["current_outcome_kind"] == "SUCCESS":
                        reason = None
                        blocked = None
                    else:
                        reason = "EFFECT_CONFLICT"
                        blocked = None
                    status.update(
                        {
                            "schedule_boot_id": (
                                sample_boot_id if scheduled else None
                            ),
                            "observed_now_mono_ns": (
                                sample_mono_ns if scheduled else None
                            ),
                            "next_due_mono_ns": (
                                sample_mono_ns if scheduled else None
                            ),
                            "due_since_mono_ns": (
                                sample_mono_ns if scheduled else None
                            ),
                            "attempt_count": 0 if scheduled else None,
                            "backoff_ns": 0 if scheduled else None,
                            "help_due": 1 if scheduled else 0,
                            "blocked_basis_fingerprint": blocked,
                            "reason_code": reason,
                        }
                    )
                    status["status_hash"] = registration_hashes.derive(
                        "status_hash", status
                    )
                    operation = self._operation_base(
                        operation_id=operation_id,
                        operation_class="DATA",
                        operation_kind="REBOOT_STATUS",
                        measured_free_bytes=measured,
                        projected_db_growth_bytes=0,
                        candidate=candidate,
                        control=None,
                        data=data,
                        overrides={
                            "target_member_id": member_id,
                            "target_effect_id": effect["effect_id"],
                            "expected_target_status_hash": old["status_hash"],
                            "target_subject_key": status["subject_key"],
                            "target_status_hash": status["status_hash"],
                            "sample_boot_id": sample_boot_id,
                            "sample_mono_ns": sample_mono_ns,
                        },
                    )
                    status["write_operation_seq"] = operation["operation_seq"]
                    status["write_operation_id"] = operation_id
                    status["write_operation_hash"] = operation[
                        "operation_envelope_hash"
                    ]
                    self._insert("registration_operation_audit", operation)
                    self._update_row(
                        "registration_runtime_status",
                        status,
                        primary_key="subject_key",
                        expected_column="status_hash",
                        expected_value=old["status_hash"],
                    )
                    self._commit()
                    self._tighten_files()
                    return OperationResult(
                        "COMMITTED",
                        operation_id,
                        operation["operation_envelope_hash"],
                        status["status_hash"],
                    )
                except Exception:
                    if self._connection.in_transaction:
                        self._connection.execute("ROLLBACK")
                    raise

    def schedule_status(
        self,
        data: DataCapability,
        candidate: ProtocolCandidate,
        *,
        member_id: str,
        expected_status_hash: str,
        attempt_count: int,
        backoff_ns: int,
        operation_id: str | None = None,
    ) -> OperationResult:
        self._require_data(data, candidate)
        self._require_current_candidate(candidate, mode="WRITABLE")
        if not 0 <= attempt_count <= 255 or not 0 <= backoff_ns <= 15_000_000_000:
            raise ValueError("schedule bounds exceeded")
        operation_id = operation_id or self._operation_ids()
        with self._locks.acquire_member(member_id) as held:
            held.verify()
            with self._write_scope(
                {
                    (sqlite3.SQLITE_INSERT, "registration_operation_audit"),
                    (sqlite3.SQLITE_UPDATE, "registration_runtime_status"),
                }
            ):
                try:
                    measured = self._begin()
                    sample_boot_id, sample_mono_ns = self._fresh_sample()
                    old = dict(
                        self._connection.execute(
                            "SELECT * FROM registration_runtime_status "
                            "WHERE member_id=?",
                            (member_id,),
                        ).fetchone()
                    )
                    if (
                        old["status_hash"] != expected_status_hash
                        or old["schedule_boot_id"]
                        not in {None, sample_boot_id}
                    ):
                        raise StaleAuthority("SCHEDULE_STATUS stale tuple")
                    status = dict(old)
                    status.update(
                        {
                            "status_version": int(old["status_version"]) + 1,
                            "schedule_boot_id": sample_boot_id,
                            "observed_now_mono_ns": sample_mono_ns,
                            "next_due_mono_ns": sample_mono_ns + backoff_ns,
                            "due_since_mono_ns": (
                                old["due_since_mono_ns"]
                                if old["due_since_mono_ns"] is not None
                                else sample_mono_ns
                            ),
                            "attempt_count": attempt_count,
                            "backoff_ns": backoff_ns,
                        }
                    )
                    status["status_hash"] = registration_hashes.derive(
                        "status_hash", status
                    )
                    operation = self._operation_base(
                        operation_id=operation_id,
                        operation_class="DATA",
                        operation_kind="SCHEDULE_STATUS",
                        measured_free_bytes=measured,
                        projected_db_growth_bytes=0,
                        candidate=candidate,
                        control=None,
                        data=data,
                        overrides={
                            "target_member_id": member_id,
                            "target_effect_id": old["current_effect_id"],
                            "expected_target_status_hash": old["status_hash"],
                            "target_subject_key": status["subject_key"],
                            "target_status_hash": status["status_hash"],
                            "sample_boot_id": sample_boot_id,
                            "sample_mono_ns": sample_mono_ns,
                        },
                    )
                    status["write_operation_seq"] = operation["operation_seq"]
                    status["write_operation_id"] = operation_id
                    status["write_operation_hash"] = operation[
                        "operation_envelope_hash"
                    ]
                    self._insert("registration_operation_audit", operation)
                    self._update_row(
                        "registration_runtime_status",
                        status,
                        primary_key="subject_key",
                        expected_column="status_hash",
                        expected_value=old["status_hash"],
                    )
                    self._commit()
                    self._tighten_files()
                    return OperationResult(
                        "COMMITTED",
                        operation_id,
                        operation["operation_envelope_hash"],
                        status["status_hash"],
                    )
                except Exception:
                    if self._connection.in_transaction:
                        self._connection.execute("ROLLBACK")
                    raise

    def adopt_effect(
        self,
        control: ControlCapability,
        candidate: ProtocolCandidate,
        *,
        member_id: str,
        expected_member_hash: str,
        expected_status_hash: str,
        executor_secret: bytes | None = None,
        replacement_intent: EffectIntent | None = None,
        replacement_basis_hash: str | None = None,
        operation_id: str | None = None,
    ) -> ExecutionResult:
        self._require_control(control, candidate)
        current = self._require_current_candidate(candidate, mode="DRAINING")
        if current["staged_generation"] is None:
            raise StaleAuthority("ADOPT_EFFECT requires a staged epoch")
        operation_id = operation_id or self._operation_ids()
        protocol_lock = self._locks.acquire_protocol()
        member_lock: registration_lock.HeldLock | None = None
        committed = False
        try:
            protocol_lock.verify()
            member_lock = self._locks.acquire_member(member_id)
            member_lock.verify()
            with self._write_scope(
                {
                    (sqlite3.SQLITE_INSERT, "registration_operation_audit"),
                    (sqlite3.SQLITE_INSERT, "registration_effect"),
                    (sqlite3.SQLITE_UPDATE, "registration_effect"),
                    (sqlite3.SQLITE_UPDATE, "registration_runtime_status"),
                    (sqlite3.SQLITE_UPDATE, "registration_member"),
                }
            ):
                try:
                    measured = self._begin()
                    sample_boot_id, sample_mono_ns = self._fresh_sample()
                    current = self._require_current_candidate(
                        candidate, mode="DRAINING"
                    )
                    if (
                        sample_boot_id != current["drain_boot_id"]
                        or sample_mono_ns > current["drain_deadline_mono_ns"]
                    ):
                        raise StaleAuthority("ADOPT_EFFECT drain sample expired")
                    member = dict(
                        self._connection.execute(
                            "SELECT * FROM registration_member WHERE member_id=?",
                            (member_id,),
                        ).fetchone()
                    )
                    active = dict(
                        self._connection.execute(
                            "SELECT * FROM registration_effect WHERE effect_id=?",
                            (member["current_effect_id"],),
                        ).fetchone()
                    )
                    old_status = dict(
                        self._connection.execute(
                            "SELECT * FROM registration_runtime_status "
                            "WHERE member_id=?",
                            (member_id,),
                        ).fetchone()
                    )
                    if (
                        member["phase"] != "EFFECT_IN_FLIGHT"
                        or member["member_tuple_hash"] != expected_member_hash
                        or old_status["status_hash"] != expected_status_hash
                        or member["helper_generation"]
                        != current["protocol_generation"]
                        or member["helper_generation"]
                        == current["staged_generation"]
                        or active["outcome_kind"] is not None
                    ):
                        raise StaleAuthority("ADOPT_EFFECT stale tuple")
                    secret = executor_secret
                    if old_status["executor_token_hash"] is not None:
                        if (
                            secret is None
                            or _domain_hash(
                                "awa-registration-executor/v1", secret
                            )
                            != old_status["executor_token_hash"]
                        ):
                            raise AuthorizationError(
                                "preserved executor secret mismatch"
                            )
                        token_hash = old_status["executor_token_hash"]
                    else:
                        secret = secret or secrets.token_bytes(32)
                        if len(secret) < 32:
                            raise AuthorizationError(
                                "executor secret must contain at least 256 bits"
                            )
                        token_hash = _domain_hash(
                            "awa-registration-executor/v1", secret
                        )
                    status = dict(old_status)
                    status.update(
                        {
                            "status_version": int(old_status["status_version"])
                            + 1,
                            "schedule_boot_id": None,
                            "observed_now_mono_ns": None,
                            "next_due_mono_ns": None,
                            "due_since_mono_ns": None,
                            "attempt_count": None,
                            "backoff_ns": None,
                            "help_due": 0,
                            "executor_token_hash": token_hash,
                            "executor_boot_id": (
                                old_status["executor_boot_id"]
                                if old_status["executor_token_hash"] is not None
                                else sample_boot_id
                            ),
                            "executor_generation": current[
                                "staged_generation"
                            ],
                            "blocked_basis_fingerprint": None,
                            "reason_code": "EFFECT_IN_FLIGHT",
                        }
                    )
                    status["status_hash"] = registration_hashes.derive(
                        "status_hash", status
                    )
                    member_target = dict(member)
                    member_target["helper_generation"] = current[
                        "staged_generation"
                    ]
                    successor = None
                    pending_target = None
                    transition_id = None
                    target_effect_id = active["effect_id"]
                    expected_effect_hash = active["request_tuple_hash"]
                    target_effect_hash = active["request_tuple_hash"]
                    cause = None
                    if member["pending_effect_id"] is not None:
                        pending = dict(
                            self._connection.execute(
                                "SELECT * FROM registration_effect "
                                "WHERE effect_id=?",
                                (member["pending_effect_id"],),
                            ).fetchone()
                        )
                        if (
                            pending["required_protocol_generation"]
                            == current["staged_generation"]
                            and pending["required_runtime_capability_hash"]
                            == current["staged_runtime_capability_hash"]
                        ):
                            raise StaleAuthority(
                                "compatible pending effect must be retained"
                            )
                        if (
                            replacement_intent is None
                            or replacement_basis_hash is None
                            or replacement_intent.request_basis_hash
                            != replacement_basis_hash
                        ):
                            raise ValueError(
                                "incompatible pending effect needs replacement"
                            )
                        successor = self._build_effect(
                            member_id=member_id,
                            member_epoch=int(member["pending_member_epoch"]) + 1,
                            predecessor_effect_id=pending["effect_id"],
                            intent=replacement_intent,
                            protocol_generation=current["staged_generation"],
                            runtime_capability_hash=current[
                                "staged_runtime_capability_hash"
                            ],
                        )
                        member_target.update(
                            {
                                "pending_effect_id": successor["effect_id"],
                                "pending_member_epoch": successor[
                                    "member_epoch"
                                ],
                                "pending_basis_hash": replacement_basis_hash,
                                "pending_effect_tuple_hash": successor[
                                    "request_tuple_hash"
                                ],
                            }
                        )
                        target_effect_id = pending["effect_id"]
                        expected_effect_hash = pending["request_tuple_hash"]
                        target_effect_hash = successor["request_tuple_hash"]
                        cause = "STAGED_CAPABILITY_INCOMPATIBLE"
                    member_target["member_tuple_hash"] = (
                        registration_hashes.derive(
                            "member_tuple_hash", member_target
                        )
                    )
                    if successor is not None:
                        transition_id = self._successor_transition_id(
                            operation_kind="ADOPT_EFFECT",
                            cause=cause,
                            old_member_hash=member["member_tuple_hash"],
                            old_status_hash=old_status["status_hash"],
                            old_effect_hash=expected_effect_hash,
                            new_member_hash=member_target["member_tuple_hash"],
                            new_status_hash=status["status_hash"],
                            new_effect_hash=successor["request_tuple_hash"],
                            old_epoch=member["pending_member_epoch"],
                            old_basis=member["pending_basis_hash"],
                            new_epoch=successor["member_epoch"],
                            new_basis=replacement_basis_hash,
                            old_effect_id=target_effect_id,
                            new_effect_id=successor["effect_id"],
                        )
                        pending = dict(
                            self._connection.execute(
                                "SELECT * FROM registration_effect "
                                "WHERE effect_id=?",
                                (target_effect_id,),
                            ).fetchone()
                        )
                        pending_target = dict(pending)
                        pending_target.update(
                            {
                                "outcome_kind": "SUPERSEDED",
                                "outcome_helper_generation": None,
                                "outcome_tuple_hash": None,
                                "ledger_head_hash": None,
                                "first_conflict_event_seq": None,
                                "completion_blob": None,
                                "completion_hash": None,
                                "final_basis_hash": None,
                                "proof_blob": None,
                                "proof_hash": None,
                                "certificate_inputs_blob": None,
                                "certificate_inputs_hash": None,
                                "certificate_hash": None,
                                "conflict_code": None,
                                "conflict_blob": None,
                                "conflict_hash": None,
                                "superseded_by_effect_id": successor[
                                    "effect_id"
                                ],
                                "successor_transition_id": transition_id,
                            }
                        )
                        pending_target["outcome_tuple_hash"] = (
                            registration_hashes.derive(
                                "outcome_tuple_hash", pending_target
                            )
                        )
                    operation = self._operation_base(
                        operation_id=operation_id,
                        operation_class="CONTROL",
                        operation_kind="ADOPT_EFFECT",
                        measured_free_bytes=measured,
                        projected_db_growth_bytes=0,
                        candidate=candidate,
                        control=control,
                        data=None,
                        target_protocol_hash=current["protocol_hash"],
                        overrides={
                            "target_member_id": member_id,
                            "target_effect_id": target_effect_id,
                            "lineage_effect_id": active["effect_id"],
                            "target_successor_effect_id": (
                                successor["effect_id"] if successor else None
                            ),
                            "target_executor_token_hash": token_hash,
                            "expected_target_status_hash": old_status[
                                "status_hash"
                            ],
                            "target_transition_id": transition_id,
                            "target_subject_key": status["subject_key"],
                            "target_staged_epoch_hash": current[
                                "staged_epoch_hash"
                            ],
                            "expected_target_member_tuple_hash": member[
                                "member_tuple_hash"
                            ],
                            "expected_target_effect_tuple_hash": (
                                expected_effect_hash
                            ),
                            "target_member_epoch": member["member_epoch"],
                            "target_basis_hash": member["current_basis_hash"],
                            "target_successor_member_epoch": (
                                successor["member_epoch"] if successor else None
                            ),
                            "target_successor_basis_hash": (
                                replacement_basis_hash if successor else None
                            ),
                            "target_member_tuple_hash": member_target[
                                "member_tuple_hash"
                            ],
                            "target_effect_tuple_hash": target_effect_hash,
                            "target_effect_outcome_hash": (
                                pending_target["outcome_tuple_hash"]
                                if pending_target
                                else None
                            ),
                            "target_action_plan_hash": active[
                                "action_plan_hash"
                            ],
                            "target_cause_code": cause,
                            "target_status_hash": status["status_hash"],
                            "sample_boot_id": sample_boot_id,
                            "sample_mono_ns": sample_mono_ns,
                            "new_external_reservation_bytes": (
                                successor["external_growth_reservation_bytes"]
                                if successor
                                else 0
                            ),
                            "new_outcome_reservation_bytes": (
                                successor["outcome_reservation_bytes"]
                                if successor
                                else 0
                            ),
                            "new_successor_reservation_bytes": (
                                successor["successor_reservation_bytes"]
                                if successor
                                else 0
                            ),
                        },
                    )
                    if successor is not None:
                        successor["created_operation_seq"] = operation[
                            "operation_seq"
                        ]
                        successor["created_operation_id"] = operation_id
                        successor["created_operation_hash"] = operation[
                            "operation_envelope_hash"
                        ]
                    if pending_target is not None:
                        pending_target["outcome_operation_seq"] = operation[
                            "operation_seq"
                        ]
                        pending_target["outcome_operation_id"] = operation_id
                        pending_target["outcome_operation_hash"] = operation[
                            "operation_envelope_hash"
                        ]
                    for row in (status, member_target):
                        row["write_operation_seq"] = operation["operation_seq"]
                        row["write_operation_id"] = operation_id
                        row["write_operation_hash"] = operation[
                            "operation_envelope_hash"
                        ]
                    self._insert("registration_operation_audit", operation)
                    if successor is not None:
                        self._insert("registration_effect", successor)
                    if pending_target is not None:
                        self._update_row(
                            "registration_effect",
                            pending_target,
                            primary_key="effect_id",
                            expected_column="outcome_kind",
                            expected_value=None,
                        )
                    self._update_row(
                        "registration_runtime_status",
                        status,
                        primary_key="subject_key",
                        expected_column="status_hash",
                        expected_value=old_status["status_hash"],
                    )
                    self._update_row(
                        "registration_member",
                        member_target,
                        primary_key="member_id",
                        expected_column="member_tuple_hash",
                        expected_value=member["member_tuple_hash"],
                    )
                    self._commit()
                    self._tighten_files()
                    execution = MemberExecution(
                        store_identity=id(self),
                        member_lock=member_lock,
                        secret=secret,
                        member_id=member_id,
                        effect_id=active["effect_id"],
                        executor_token_hash=token_hash,
                        operation_id=operation_id,
                        target_member_hash=member_target["member_tuple_hash"],
                        target_effect_hash=active["request_tuple_hash"],
                        target_status_hash=status["status_hash"],
                        target_protocol_hash=current["protocol_hash"],
                        target_staged_epoch_hash=current["staged_epoch_hash"],
                        _seal=_EXECUTION_SEAL,
                    )
                    committed = True
                except Exception:
                    if self._connection.in_transaction:
                        self._connection.execute("ROLLBACK")
                    raise
            protocol_lock.release()
            self.verify_execution(execution)
            return ExecutionResult(
                operation=OperationResult(
                    "COMMITTED",
                    operation_id,
                    operation["operation_envelope_hash"],
                    member_target["member_tuple_hash"],
                ),
                execution=execution,
            )
        except Exception:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            if committed and member_lock is not None:
                member_lock.release()
            raise
        finally:
            if protocol_lock.held:
                protocol_lock.release()
            if not committed and member_lock is not None and member_lock.held:
                member_lock.release()

    def open_effect(
        self,
        data: DataCapability,
        candidate: ProtocolCandidate,
        *,
        member_id: str,
        expected_member_hash: str,
        expected_effect_hash: str,
        expected_status_hash: str,
        executor_secret: bytes | None = None,
        operation_id: str | None = None,
        projected_db_growth_bytes: int = 0,
    ) -> ExecutionResult:
        self._require_data(data, candidate)
        self._require_current_candidate(candidate, mode="WRITABLE")
        for value, field in (
            (member_id, "member_id"),
            (expected_member_hash, "expected_member_hash"),
            (expected_effect_hash, "expected_effect_hash"),
            (expected_status_hash, "expected_status_hash"),
        ):
            _require_hash(value, field)
        secret = executor_secret or secrets.token_bytes(32)
        if not isinstance(secret, bytes) or len(secret) < 32:
            raise AuthorizationError("executor secret must contain at least 256 bits")
        token_hash = _domain_hash("awa-registration-executor/v1", secret)
        operation_id = operation_id or self._operation_ids()
        held = self._locks.acquire_member(member_id)
        committed = False
        try:
            held.verify()
            with self._write_scope(
                {
                    (sqlite3.SQLITE_INSERT, "registration_operation_audit"),
                    (sqlite3.SQLITE_INSERT, "registration_protocol_epoch"),
                    (sqlite3.SQLITE_UPDATE, "registration_runtime_status"),
                    (sqlite3.SQLITE_UPDATE, "registration_member"),
                }
            ):
                try:
                    measured = self._begin()
                    sample_boot_id, sample_mono_ns = self._fresh_sample()
                    current = self._require_current_candidate(
                        candidate, mode="WRITABLE"
                    )
                    member_row = self._connection.execute(
                        "SELECT * FROM registration_member WHERE member_id=?",
                        (member_id,),
                    ).fetchone()
                    if member_row is None:
                        raise StaleAuthority("member missing")
                    member = dict(member_row)
                    effect_row = self._connection.execute(
                        "SELECT * FROM registration_effect WHERE effect_id=?",
                        (member["current_effect_id"],),
                    ).fetchone()
                    status_row = self._connection.execute(
                        "SELECT * FROM registration_runtime_status WHERE member_id=?",
                        (member_id,),
                    ).fetchone()
                    if effect_row is None or status_row is None:
                        raise StaleAuthority("member closure missing")
                    effect = dict(effect_row)
                    old_status = dict(status_row)
                    if (
                        member["member_tuple_hash"] != expected_member_hash
                        or effect["request_tuple_hash"] != expected_effect_hash
                        or old_status["status_hash"] != expected_status_hash
                    ):
                        raise StaleAuthority("OPEN_EFFECT stale tuple")
                    if (
                        member["phase"] != "REQUESTED"
                        or effect["request_kind"] != "CLEAN_ELIGIBLE"
                        or effect["outcome_kind"] is not None
                        or old_status["executor_token_hash"] is not None
                        or old_status["schedule_boot_id"] != sample_boot_id
                        or old_status["next_due_mono_ns"] is None
                        or int(old_status["next_due_mono_ns"]) > sample_mono_ns
                    ):
                        raise StaleAuthority("OPEN_EFFECT tuple is not due")

                    status = dict(old_status)
                    status.update(
                        {
                            "status_version": int(old_status["status_version"]) + 1,
                            "schedule_boot_id": None,
                            "observed_now_mono_ns": None,
                            "next_due_mono_ns": None,
                            "due_since_mono_ns": None,
                            "attempt_count": None,
                            "backoff_ns": None,
                            "help_due": 0,
                            "executor_token_hash": token_hash,
                            "executor_boot_id": sample_boot_id,
                            "executor_generation": current[
                                "protocol_generation"
                            ],
                            "blocked_basis_fingerprint": None,
                            "reason_code": "EFFECT_IN_FLIGHT",
                        }
                    )
                    status["status_hash"] = registration_hashes.derive(
                        "status_hash", status
                    )
                    member_target = dict(member)
                    member_target["phase"] = "EFFECT_IN_FLIGHT"
                    member_target["member_tuple_hash"] = registration_hashes.derive(
                        "member_tuple_hash", member_target
                    )

                    first_effect = current["first_effect_id"] is None
                    target_protocol_hash = current["protocol_hash"]
                    protocol: dict[str, Any] | None = None
                    if first_effect:
                        protocol = {
                            column: current[column]
                            for column in _PROTOCOL_COLUMNS
                        }
                        protocol.update(
                            {
                                "protocol_seq": int(current["protocol_seq"]) + 1,
                                "first_effect_id": effect["effect_id"],
                                "transition_kind": "FIRST_EFFECT",
                                "transition_reason_code": "FIRST_EFFECT",
                                "previous_protocol_hash": current["protocol_hash"],
                                "created_wall_ns": self._wall_ns(),
                            }
                        )
                        target_protocol_hash = registration_hashes.derive(
                            "protocol_hash", protocol
                        )
                        protocol["protocol_hash"] = target_protocol_hash
                        protocol["first_effect_operation_id"] = operation_id
                        protocol["operation_id"] = operation_id

                    operation = self._operation_base(
                        operation_id=operation_id,
                        operation_class="DATA",
                        operation_kind="OPEN_EFFECT",
                        measured_free_bytes=measured,
                        projected_db_growth_bytes=projected_db_growth_bytes,
                        candidate=candidate,
                        control=None,
                        data=data,
                        target_protocol_hash=target_protocol_hash,
                        overrides={
                            "target_member_id": member_id,
                            "target_effect_id": effect["effect_id"],
                            "target_executor_token_hash": token_hash,
                            "expected_target_status_hash": expected_status_hash,
                            "target_subject_key": status["subject_key"],
                            "expected_target_member_tuple_hash": (
                                expected_member_hash
                            ),
                            "expected_target_effect_tuple_hash": (
                                expected_effect_hash
                            ),
                            "target_member_epoch": member["member_epoch"],
                            "target_basis_hash": member["current_basis_hash"],
                            "target_member_tuple_hash": member_target[
                                "member_tuple_hash"
                            ],
                            "target_effect_tuple_hash": effect[
                                "request_tuple_hash"
                            ],
                            "target_action_plan_hash": effect["action_plan_hash"],
                            "target_status_hash": status["status_hash"],
                            "sample_boot_id": sample_boot_id,
                            "sample_mono_ns": sample_mono_ns,
                        },
                    )
                    for row in (status, member_target):
                        row["write_operation_seq"] = operation["operation_seq"]
                        row["write_operation_id"] = operation_id
                        row["write_operation_hash"] = operation[
                            "operation_envelope_hash"
                        ]
                    self._insert("registration_operation_audit", operation)
                    if protocol is not None:
                        self._insert("registration_protocol_epoch", protocol)
                    self._update_row(
                        "registration_runtime_status",
                        status,
                        primary_key="subject_key",
                        expected_column="status_hash",
                        expected_value=expected_status_hash,
                    )
                    self._update_row(
                        "registration_member",
                        member_target,
                        primary_key="member_id",
                        expected_column="member_tuple_hash",
                        expected_value=expected_member_hash,
                    )
                    closure = self._connection.execute(
                        "SELECT 1 FROM registration_member m "
                        "JOIN registration_runtime_status s USING(member_id) "
                        "JOIN registration_effect e "
                        "ON e.effect_id=m.current_effect_id "
                        "JOIN registration_protocol_epoch p "
                        "ON p.protocol_seq=(SELECT MAX(protocol_seq) "
                        "FROM registration_protocol_epoch) "
                        "WHERE m.member_id=? AND m.phase='EFFECT_IN_FLIGHT' "
                        "AND m.member_tuple_hash=? AND s.status_hash=? "
                        "AND s.executor_token_hash=? "
                        "AND e.request_tuple_hash=? AND p.protocol_hash=?",
                        (
                            member_id,
                            member_target["member_tuple_hash"],
                            status["status_hash"],
                            token_hash,
                            effect["request_tuple_hash"],
                            target_protocol_hash,
                        ),
                    ).fetchone()
                    if closure is None:
                        raise StoreError("OPEN_EFFECT closure failed")
                    self._commit()
                    self._tighten_files()
                    execution = MemberExecution(
                        store_identity=id(self),
                        member_lock=held,
                        secret=secret,
                        member_id=member_id,
                        effect_id=effect["effect_id"],
                        executor_token_hash=token_hash,
                        operation_id=operation_id,
                        target_member_hash=member_target["member_tuple_hash"],
                        target_effect_hash=effect["request_tuple_hash"],
                        target_status_hash=status["status_hash"],
                        target_protocol_hash=target_protocol_hash,
                        _seal=_EXECUTION_SEAL,
                    )
                    committed = True
                    self.verify_execution(execution)
                    return ExecutionResult(
                        operation=OperationResult(
                            "COMMITTED",
                            operation_id,
                            operation["operation_envelope_hash"],
                            member_target["member_tuple_hash"],
                        ),
                        execution=execution,
                    )
                except Exception:
                    if self._connection.in_transaction:
                        self._connection.execute("ROLLBACK")
                    raise
        finally:
            if not committed:
                held.release()

    def verify_execution(self, execution: MemberExecution) -> None:
        execution.verify_owner(self)
        if self._connection.in_transaction:
            raise AuthorizationError("helper I/O check cannot nest a transaction")
        row = self._connection.execute(
            "SELECT m.member_tuple_hash,s.status_hash,s.executor_token_hash,"
            "e.request_tuple_hash,p.protocol_hash,p.staged_epoch_hash,"
            "m.helper_generation,s.executor_generation,p.staged_generation,p.mode "
            "FROM registration_member m "
            "JOIN registration_runtime_status s USING(member_id) "
            "JOIN registration_effect e ON e.effect_id=m.current_effect_id "
            "JOIN registration_protocol_epoch p "
            "ON p.protocol_seq=(SELECT MAX(protocol_seq) "
            "FROM registration_protocol_epoch) "
            "WHERE m.member_id=? AND e.effect_id=?",
            (execution.member_id, execution.effect_id),
        ).fetchone()
        if row is None or tuple(row[:4]) != (
            execution.target_member_hash,
            execution.target_status_hash,
            execution.executor_token_hash,
            execution.target_effect_hash,
        ):
            raise AuthorizationError("post-commit executor authority changed")
        if execution.target_staged_epoch_hash is None:
            if row["protocol_hash"] != execution.target_protocol_hash:
                raise AuthorizationError("post-commit protocol authority changed")
            return
        draining = (
            row["protocol_hash"] == execution.target_protocol_hash
            and row["staged_epoch_hash"] == execution.target_staged_epoch_hash
            and row["helper_generation"] == row["staged_generation"]
            and row["executor_generation"] == row["staged_generation"]
            and row["mode"] == "DRAINING"
        )
        advanced = (
            row["mode"] == "WRITABLE"
            and row["helper_generation"] == row["executor_generation"]
            and self._connection.execute(
                "SELECT 1 FROM registration_operation_audit a "
                "JOIN registration_protocol_epoch staged "
                "ON staged.protocol_seq=a.protocol_seq "
                "JOIN registration_protocol_epoch current "
                "ON current.protocol_seq=(SELECT MAX(protocol_seq) "
                "FROM registration_protocol_epoch) "
                "WHERE a.operation_id=? AND a.operation_kind='ADOPT_EFFECT' "
                "AND a.target_staged_epoch_hash=? "
                "AND staged.staged_epoch_hash=? "
                "AND staged.staged_generation=current.protocol_generation "
                "AND staged.staged_runtime_capability_hash="
                "current.runtime_capability_hash",
                (
                    execution.operation_id,
                    execution.target_staged_epoch_hash,
                    execution.target_staged_epoch_hash,
                ),
            ).fetchone()
            is not None
        )
        if not draining and not advanced:
            raise AuthorizationError("staged executor lineage changed")

    def append_action(
        self,
        data: DataCapability,
        candidate: ProtocolCandidate,
        execution: MemberExecution,
        *,
        observation_kind: str,
        measured_postcondition_hash: str,
        external_growth_bytes: int = 0,
        operation_id: str | None = None,
        projected_db_growth_bytes: int = 0,
    ) -> OperationResult:
        self._require_data(data, candidate)
        self._require_current_candidate(candidate, mode="WRITABLE")
        execution.verify_owner(self)
        self.verify_execution(execution)
        if observation_kind not in {
            "OBSERVED_EXACT",
            "APPLIED_VERIFIED",
            "LOGICAL_CONFLICT",
        }:
            raise ValueError("unknown observation kind")
        _require_hash(measured_postcondition_hash, "measured_postcondition_hash")
        if not 0 <= external_growth_bytes <= 16 * 1024**2:
            raise ValueError("external growth out of bounds")
        operation_id = operation_id or self._operation_ids()
        with self._write_scope(
            {
                (sqlite3.SQLITE_INSERT, "registration_operation_audit"),
                (sqlite3.SQLITE_INSERT, "registration_effect_action"),
            }
        ):
            try:
                measured = self._begin()
                effect = dict(
                    self._connection.execute(
                        "SELECT * FROM registration_effect WHERE effect_id=?",
                        (execution.effect_id,),
                    ).fetchone()
                )
                status = dict(
                    self._connection.execute(
                        "SELECT * FROM registration_runtime_status "
                        "WHERE member_id=?",
                        (execution.member_id,),
                    ).fetchone()
                )
                event_seq = int(
                    self._connection.execute(
                        "SELECT COALESCE(MAX(event_seq),0)+1 "
                        "FROM registration_effect_action WHERE effect_id=?",
                        (execution.effect_id,),
                    ).fetchone()[0]
                )
                if not 1 <= event_seq <= 4:
                    raise StaleAuthority("effect action plan is already complete")
                action_kind = effect[f"action_{event_seq}_kind"]
                action_hash = effect[f"action_{event_seq}_hash"]
                postcondition_hash = effect[
                    f"postcondition_{event_seq}_hash"
                ]
                if observation_kind in {
                    "OBSERVED_EXACT",
                    "APPLIED_VERIFIED",
                } and measured_postcondition_hash != postcondition_hash:
                    raise StaleAuthority(
                        "satisfying observation must equal frozen postcondition"
                    )
                if (
                    observation_kind == "LOGICAL_CONFLICT"
                    and measured_postcondition_hash == postcondition_hash
                ):
                    raise StaleAuthority(
                        "logical conflict requires a divergent postcondition"
                    )
                prior = self._connection.execute(
                    "SELECT ledger_hash,observation_kind "
                    "FROM registration_effect_action WHERE effect_id=? "
                    "ORDER BY event_seq DESC LIMIT 1",
                    (execution.effect_id,),
                ).fetchone()
                if prior is not None and prior["observation_kind"] == "LOGICAL_CONFLICT":
                    raise StaleAuthority("logical conflict is terminal")
                prior_hash = prior["ledger_hash"] if prior else ZERO_HASH
                relation = {
                    "effect_id": execution.effect_id,
                    "event_seq": str(event_seq),
                    "ordinal": str(event_seq),
                    "kind": observation_kind,
                    "measured_postcondition_hash": measured_postcondition_hash,
                    "external_growth_bytes": str(external_growth_bytes),
                    "detail_code": observation_kind,
                }
                observation_blob = registration_jcs.encode_blob(
                    "observation", relation
                )
                observation_hash = _domain_hash(
                    "awa-registration-observation/v1", observation_blob
                )
                action: dict[str, Any] = {
                    "effect_id": execution.effect_id,
                    "event_seq": event_seq,
                    "ordinal": event_seq,
                    "action_kind": action_kind,
                    "action_hash": action_hash,
                    "postcondition_hash": postcondition_hash,
                    "observation_kind": observation_kind,
                    "observation_blob": observation_blob,
                    "observation_hash": observation_hash,
                    "prior_ledger_hash": prior_hash,
                    "external_growth_bytes": external_growth_bytes,
                    "observed_wall_ns": self._wall_ns(),
                }
                action["ledger_hash"] = registration_hashes.derive(
                    "ledger_hash", action
                )
                operation = self._operation_base(
                    operation_id=operation_id,
                    operation_class="DATA",
                    operation_kind="APPEND_ACTION",
                    measured_free_bytes=measured,
                    projected_db_growth_bytes=projected_db_growth_bytes,
                    candidate=candidate,
                    control=None,
                    data=data,
                    overrides={
                        "target_member_id": execution.member_id,
                        "target_effect_id": execution.effect_id,
                        "target_executor_token_hash": (
                            execution.executor_token_hash
                        ),
                        "expected_target_status_hash": status["status_hash"],
                        "target_action_ledger_hash": action["ledger_hash"],
                        "external_growth_bytes": external_growth_bytes,
                    },
                )
                action["write_operation_seq"] = operation["operation_seq"]
                action["write_operation_id"] = operation_id
                action["write_operation_hash"] = operation[
                    "operation_envelope_hash"
                ]
                self._insert("registration_operation_audit", operation)
                self._insert("registration_effect_action", action)
                closure = self._connection.execute(
                    "SELECT 1 FROM registration_effect_action "
                    "WHERE effect_id=? AND event_seq=? AND ledger_hash=? "
                    "AND write_operation_id=?",
                    (
                        execution.effect_id,
                        event_seq,
                        action["ledger_hash"],
                        operation_id,
                    ),
                ).fetchone()
                if closure is None:
                    raise StoreError("APPEND_ACTION closure failed")
                self._commit()
                self._tighten_files()
                return OperationResult(
                    "COMMITTED",
                    operation_id,
                    operation["operation_envelope_hash"],
                    action["ledger_hash"],
                )
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def mark_unavailable(
        self,
        data: DataCapability,
        candidate: ProtocolCandidate,
        execution: MemberExecution,
        *,
        operation_id: str | None = None,
        projected_db_growth_bytes: int = 0,
    ) -> OperationResult:
        self._require_data(data, candidate)
        self._require_current_candidate(candidate, mode="WRITABLE")
        execution.verify_owner(self)
        self.verify_execution(execution)
        operation_id = operation_id or self._operation_ids()
        committed = False
        try:
            with self._write_scope(
                {
                    (sqlite3.SQLITE_INSERT, "registration_operation_audit"),
                    (sqlite3.SQLITE_UPDATE, "registration_runtime_status"),
                }
            ):
                try:
                    measured = self._begin()
                    sample_boot_id, sample_mono_ns = self._fresh_sample()
                    old = dict(
                        self._connection.execute(
                            "SELECT * FROM registration_runtime_status "
                            "WHERE member_id=?",
                            (execution.member_id,),
                        ).fetchone()
                    )
                    if old["executor_boot_id"] != sample_boot_id:
                        raise StaleAuthority(
                            "same-boot unavailable cannot clear old-boot executor"
                        )
                    status = dict(old)
                    status.update(
                        {
                            "status_version": int(old["status_version"]) + 1,
                            "schedule_boot_id": sample_boot_id,
                            "observed_now_mono_ns": sample_mono_ns,
                            "next_due_mono_ns": sample_mono_ns,
                            "due_since_mono_ns": sample_mono_ns,
                            "attempt_count": min(
                                255, int(old["attempt_count"] or 0) + 1
                            ),
                            "backoff_ns": 0,
                            "help_due": 1,
                            "executor_token_hash": None,
                            "executor_boot_id": None,
                            "executor_generation": None,
                            "unavailable_count": min(
                                3, int(old["unavailable_count"]) + 1
                            ),
                            "yield_count": min(
                                3, int(old["yield_count"]) + 1
                            ),
                            "reason_code": "RESOLVER_UNAVAILABLE",
                        }
                    )
                    status["status_hash"] = registration_hashes.derive(
                        "status_hash", status
                    )
                    operation = self._operation_base(
                        operation_id=operation_id,
                        operation_class="DATA",
                        operation_kind="MARK_UNAVAILABLE",
                        measured_free_bytes=measured,
                        projected_db_growth_bytes=projected_db_growth_bytes,
                        candidate=candidate,
                        control=None,
                        data=data,
                        overrides={
                            "target_member_id": execution.member_id,
                            "target_effect_id": execution.effect_id,
                            "target_executor_token_hash": (
                                execution.executor_token_hash
                            ),
                            "expected_target_status_hash": old["status_hash"],
                            "target_subject_key": status["subject_key"],
                            "target_status_hash": status["status_hash"],
                            "sample_boot_id": sample_boot_id,
                            "sample_mono_ns": sample_mono_ns,
                        },
                    )
                    status["write_operation_seq"] = operation["operation_seq"]
                    status["write_operation_id"] = operation_id
                    status["write_operation_hash"] = operation[
                        "operation_envelope_hash"
                    ]
                    self._insert("registration_operation_audit", operation)
                    self._update_row(
                        "registration_runtime_status",
                        status,
                        primary_key="subject_key",
                        expected_column="status_hash",
                        expected_value=old["status_hash"],
                    )
                    self._commit()
                    self._tighten_files()
                    committed = True
                    result = OperationResult(
                        "COMMITTED",
                        operation_id,
                        operation["operation_envelope_hash"],
                        status["status_hash"],
                    )
                except Exception:
                    if self._connection.in_transaction:
                        self._connection.execute("ROLLBACK")
                    raise
            execution.close()
            return result
        except Exception:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            if committed:
                execution.close()
            raise

    def mark_dead_executor_unavailable(
        self,
        data: DataCapability,
        candidate: ProtocolCandidate,
        *,
        member_id: str,
        expected_status_hash: str,
        operation_id: str | None = None,
    ) -> OperationResult:
        """Member-lock takeover after same-boot executor process death."""
        self._require_data(data, candidate)
        self._require_current_candidate(candidate, mode="WRITABLE")
        operation_id = operation_id or self._operation_ids()
        with self._locks.acquire_member(member_id) as held:
            held.verify()
            with self._write_scope(
                {
                    (sqlite3.SQLITE_INSERT, "registration_operation_audit"),
                    (sqlite3.SQLITE_UPDATE, "registration_runtime_status"),
                }
            ):
                try:
                    measured = self._begin()
                    sample_boot_id, sample_mono_ns = self._fresh_sample()
                    old = dict(
                        self._connection.execute(
                            "SELECT * FROM registration_runtime_status "
                            "WHERE member_id=?",
                            (member_id,),
                        ).fetchone()
                    )
                    if (
                        old["status_hash"] != expected_status_hash
                        or old["executor_token_hash"] is None
                        or old["executor_boot_id"] != sample_boot_id
                    ):
                        raise StaleAuthority("dead-executor takeover stale tuple")
                    status = dict(old)
                    status.update(
                        {
                            "status_version": int(old["status_version"]) + 1,
                            "schedule_boot_id": sample_boot_id,
                            "observed_now_mono_ns": sample_mono_ns,
                            "next_due_mono_ns": sample_mono_ns,
                            "due_since_mono_ns": sample_mono_ns,
                            "attempt_count": min(
                                255, int(old["attempt_count"] or 0) + 1
                            ),
                            "backoff_ns": 0,
                            "help_due": 1,
                            "executor_token_hash": None,
                            "executor_boot_id": None,
                            "executor_generation": None,
                            "unavailable_count": min(
                                3, int(old["unavailable_count"]) + 1
                            ),
                            "yield_count": min(
                                3, int(old["yield_count"]) + 1
                            ),
                            "reason_code": "RESOLVER_UNAVAILABLE",
                        }
                    )
                    status["status_hash"] = registration_hashes.derive(
                        "status_hash", status
                    )
                    operation = self._operation_base(
                        operation_id=operation_id,
                        operation_class="DATA",
                        operation_kind="MARK_UNAVAILABLE",
                        measured_free_bytes=measured,
                        projected_db_growth_bytes=0,
                        candidate=candidate,
                        control=None,
                        data=data,
                        overrides={
                            "target_member_id": member_id,
                            "target_effect_id": old["current_effect_id"],
                            "target_executor_token_hash": old[
                                "executor_token_hash"
                            ],
                            "expected_target_status_hash": old["status_hash"],
                            "target_subject_key": status["subject_key"],
                            "target_status_hash": status["status_hash"],
                            "sample_boot_id": sample_boot_id,
                            "sample_mono_ns": sample_mono_ns,
                        },
                    )
                    status["write_operation_seq"] = operation["operation_seq"]
                    status["write_operation_id"] = operation_id
                    status["write_operation_hash"] = operation[
                        "operation_envelope_hash"
                    ]
                    self._insert("registration_operation_audit", operation)
                    self._update_row(
                        "registration_runtime_status",
                        status,
                        primary_key="subject_key",
                        expected_column="status_hash",
                        expected_value=old["status_hash"],
                    )
                    self._commit()
                    self._tighten_files()
                    return OperationResult(
                        "COMMITTED",
                        operation_id,
                        operation["operation_envelope_hash"],
                        status["status_hash"],
                    )
                except Exception:
                    if self._connection.in_transaction:
                        self._connection.execute("ROLLBACK")
                    raise

    def reacquire_effect(
        self,
        data: DataCapability,
        candidate: ProtocolCandidate,
        *,
        member_id: str,
        expected_member_hash: str,
        expected_effect_hash: str,
        expected_status_hash: str,
        executor_secret: bytes | None = None,
        operation_id: str | None = None,
        projected_db_growth_bytes: int = 0,
    ) -> ExecutionResult:
        self._require_data(data, candidate)
        self._require_current_candidate(candidate, mode="WRITABLE")
        secret = executor_secret or secrets.token_bytes(32)
        if not isinstance(secret, bytes) or len(secret) < 32:
            raise AuthorizationError("executor secret must contain at least 256 bits")
        token_hash = _domain_hash("awa-registration-executor/v1", secret)
        operation_id = operation_id or self._operation_ids()
        held = self._locks.acquire_member(member_id)
        committed = False
        try:
            held.verify()
            with self._write_scope(
                {
                    (sqlite3.SQLITE_INSERT, "registration_operation_audit"),
                    (sqlite3.SQLITE_UPDATE, "registration_runtime_status"),
                }
            ):
                try:
                    measured = self._begin()
                    sample_boot_id, sample_mono_ns = self._fresh_sample()
                    current = self._require_current_candidate(
                        candidate, mode="WRITABLE"
                    )
                    member = dict(
                        self._connection.execute(
                            "SELECT * FROM registration_member WHERE member_id=?",
                            (member_id,),
                        ).fetchone()
                    )
                    effect = dict(
                        self._connection.execute(
                            "SELECT * FROM registration_effect "
                            "WHERE effect_id=?",
                            (member["current_effect_id"],),
                        ).fetchone()
                    )
                    old = dict(
                        self._connection.execute(
                            "SELECT * FROM registration_runtime_status "
                            "WHERE member_id=?",
                            (member_id,),
                        ).fetchone()
                    )
                    if (
                        member["member_tuple_hash"] != expected_member_hash
                        or effect["request_tuple_hash"] != expected_effect_hash
                        or old["status_hash"] != expected_status_hash
                        or member["phase"] != "EFFECT_IN_FLIGHT"
                        or old["executor_token_hash"] is not None
                        or old["help_due"] != 1
                        or old["schedule_boot_id"] != sample_boot_id
                        or old["next_due_mono_ns"] is None
                        or int(old["next_due_mono_ns"]) > sample_mono_ns
                    ):
                        raise StaleAuthority("REACQUIRE_EFFECT stale tuple")
                    ledger_head = self._connection.execute(
                        "SELECT ledger_hash FROM registration_effect_action "
                        "WHERE effect_id=? ORDER BY event_seq DESC LIMIT 1",
                        (effect["effect_id"],),
                    ).fetchone()
                    ledger_hash = ledger_head[0] if ledger_head else ZERO_HASH
                    status = dict(old)
                    status.update(
                        {
                            "status_version": int(old["status_version"]) + 1,
                            "schedule_boot_id": None,
                            "observed_now_mono_ns": None,
                            "next_due_mono_ns": None,
                            "due_since_mono_ns": None,
                            "attempt_count": None,
                            "backoff_ns": None,
                            "help_due": 0,
                            "executor_token_hash": token_hash,
                            "executor_boot_id": sample_boot_id,
                            "executor_generation": current[
                                "protocol_generation"
                            ],
                            "blocked_basis_fingerprint": None,
                            "reason_code": "EFFECT_IN_FLIGHT",
                        }
                    )
                    status["status_hash"] = registration_hashes.derive(
                        "status_hash", status
                    )
                    operation = self._operation_base(
                        operation_id=operation_id,
                        operation_class="DATA",
                        operation_kind="REACQUIRE_EFFECT",
                        measured_free_bytes=measured,
                        projected_db_growth_bytes=projected_db_growth_bytes,
                        candidate=candidate,
                        control=None,
                        data=data,
                        target_protocol_hash=current["protocol_hash"],
                        overrides={
                            "target_member_id": member_id,
                            "target_effect_id": effect["effect_id"],
                            "target_executor_token_hash": token_hash,
                            "expected_target_status_hash": old["status_hash"],
                            "target_subject_key": status["subject_key"],
                            "expected_target_member_tuple_hash": (
                                member["member_tuple_hash"]
                            ),
                            "expected_target_effect_tuple_hash": (
                                effect["request_tuple_hash"]
                            ),
                            "target_member_epoch": member["member_epoch"],
                            "target_basis_hash": member["current_basis_hash"],
                            "target_member_tuple_hash": (
                                member["member_tuple_hash"]
                            ),
                            "target_effect_tuple_hash": (
                                effect["request_tuple_hash"]
                            ),
                            "target_action_plan_hash": effect["action_plan_hash"],
                            "target_action_ledger_hash": ledger_hash,
                            "target_status_hash": status["status_hash"],
                            "sample_boot_id": sample_boot_id,
                            "sample_mono_ns": sample_mono_ns,
                        },
                    )
                    status["write_operation_seq"] = operation["operation_seq"]
                    status["write_operation_id"] = operation_id
                    status["write_operation_hash"] = operation[
                        "operation_envelope_hash"
                    ]
                    self._insert("registration_operation_audit", operation)
                    self._update_row(
                        "registration_runtime_status",
                        status,
                        primary_key="subject_key",
                        expected_column="status_hash",
                        expected_value=old["status_hash"],
                    )
                    self._commit()
                    self._tighten_files()
                    execution = MemberExecution(
                        store_identity=id(self),
                        member_lock=held,
                        secret=secret,
                        member_id=member_id,
                        effect_id=effect["effect_id"],
                        executor_token_hash=token_hash,
                        operation_id=operation_id,
                        target_member_hash=member["member_tuple_hash"],
                        target_effect_hash=effect["request_tuple_hash"],
                        target_status_hash=status["status_hash"],
                        target_protocol_hash=current["protocol_hash"],
                        _seal=_EXECUTION_SEAL,
                    )
                    committed = True
                    self.verify_execution(execution)
                    return ExecutionResult(
                        operation=OperationResult(
                            "COMMITTED",
                            operation_id,
                            operation["operation_envelope_hash"],
                            status["status_hash"],
                        ),
                        execution=execution,
                    )
                except Exception:
                    if self._connection.in_transaction:
                        self._connection.execute("ROLLBACK")
                    raise
        finally:
            if not committed:
                held.release()

    def close_success(
        self,
        data: DataCapability,
        candidate: ProtocolCandidate,
        execution: MemberExecution,
        *,
        final_basis_hash: str,
        operation_id: str | None = None,
        projected_db_growth_bytes: int = 0,
    ) -> OperationResult:
        _require_hash(final_basis_hash, "final_basis_hash")
        return self._close_effect(
            data,
            candidate,
            execution,
            outcome_kind="SUCCESS",
            final_basis_hash=final_basis_hash,
            conflict_code=None,
            expected_hash=None,
            observed_hash=None,
            operation_id=operation_id,
            projected_db_growth_bytes=projected_db_growth_bytes,
        )

    def close_conflict(
        self,
        data: DataCapability,
        candidate: ProtocolCandidate,
        execution: MemberExecution,
        *,
        conflict_code: str,
        expected_hash: str,
        observed_hash: str,
        operation_id: str | None = None,
        projected_db_growth_bytes: int = 0,
    ) -> OperationResult:
        if conflict_code not in {
            "PROOF_POSTCONDITION_DIVERGENT",
            "LEGACY_LEASE_DIVERGENT",
            "LIFECYCLE_GRAPH_DIVERGENT",
            "FINAL_BASIS_DIVERGENT",
            "ACTION_POSTCONDITION_DIVERGENT",
        }:
            raise ValueError("invalid conflict code")
        _require_hash(expected_hash, "expected_hash")
        _require_hash(observed_hash, "observed_hash")
        return self._close_effect(
            data,
            candidate,
            execution,
            outcome_kind="LOGICAL_CONFLICT",
            final_basis_hash=None,
            conflict_code=conflict_code,
            expected_hash=expected_hash,
            observed_hash=observed_hash,
            operation_id=operation_id,
            projected_db_growth_bytes=projected_db_growth_bytes,
        )

    def _close_effect(
        self,
        data: DataCapability,
        candidate: ProtocolCandidate,
        execution: MemberExecution,
        *,
        outcome_kind: str,
        final_basis_hash: str | None,
        conflict_code: str | None,
        expected_hash: str | None,
        observed_hash: str | None,
        operation_id: str | None,
        projected_db_growth_bytes: int,
    ) -> OperationResult:
        self._require_data(data, candidate)
        self._require_current_candidate(candidate, mode="WRITABLE")
        execution.verify_owner(self)
        self.verify_execution(execution)
        operation_id = operation_id or self._operation_ids()
        committed = False
        try:
            with self._write_scope(
                {
                    (sqlite3.SQLITE_INSERT, "registration_operation_audit"),
                    (sqlite3.SQLITE_UPDATE, "registration_effect"),
                    (sqlite3.SQLITE_UPDATE, "registration_runtime_status"),
                    (sqlite3.SQLITE_UPDATE, "registration_member"),
                }
            ):
                try:
                    measured = self._begin()
                    sample_boot_id, sample_mono_ns = self._fresh_sample()
                    member = dict(
                        self._connection.execute(
                            "SELECT * FROM registration_member WHERE member_id=?",
                            (execution.member_id,),
                        ).fetchone()
                    )
                    effect = dict(
                        self._connection.execute(
                            "SELECT * FROM registration_effect WHERE effect_id=?",
                            (execution.effect_id,),
                        ).fetchone()
                    )
                    old_status = dict(
                        self._connection.execute(
                            "SELECT * FROM registration_runtime_status "
                            "WHERE member_id=?",
                            (execution.member_id,),
                        ).fetchone()
                    )
                    if (
                        member["phase"] != "EFFECT_IN_FLIGHT"
                        or effect["outcome_kind"] is not None
                        or old_status["status_hash"]
                        != execution.target_status_hash
                        or old_status["executor_token_hash"]
                        != execution.executor_token_hash
                    ):
                        raise StaleAuthority("effect close stale tuple")
                    actions = self._connection.execute(
                        "SELECT * FROM registration_effect_action "
                        "WHERE effect_id=? ORDER BY event_seq",
                        (execution.effect_id,),
                    ).fetchall()
                    if not actions:
                        raise StaleAuthority("effect has no action ledger")
                    ledger_head = actions[-1]["ledger_hash"]
                    effect_target = dict(effect)
                    effect_target.update(
                        {
                            "outcome_kind": outcome_kind,
                            "outcome_helper_generation": member[
                                "helper_generation"
                            ],
                            "ledger_head_hash": ledger_head,
                            "superseded_by_effect_id": None,
                            "successor_transition_id": None,
                        }
                    )
                    if outcome_kind == "SUCCESS":
                        if len(actions) != 4 or any(
                            row["observation_kind"] == "LOGICAL_CONFLICT"
                            for row in actions
                        ):
                            raise StaleAuthority(
                                "SUCCESS requires four satisfying actions"
                            )
                        if (
                            final_basis_hash != effect["request_basis_hash"]
                            or final_basis_hash
                            != effect["postcondition_4_hash"]
                        ):
                            raise StaleAuthority(
                                "SUCCESS final basis does not match intent"
                            )
                        completion_relation = {
                            "effect_id": execution.effect_id,
                            "action_count": "4",
                            "ledger_head_hash": ledger_head,
                            "final_basis_hash": final_basis_hash,
                        }
                        completion_blob = registration_jcs.encode_blob(
                            "completion", completion_relation
                        )
                        completion_hash = _domain_hash(
                            "awa-registration-completion/v1", completion_blob
                        )
                        proof_relation = {
                            "effect_id": execution.effect_id,
                            "member_id": execution.member_id,
                            "physical_basis_hash": member["physical_basis_hash"],
                            "git_basis_hash": member["git_basis_hash"],
                            "policy_basis_hash": member["policy_basis_hash"],
                            "lifecycle_basis_hash": member[
                                "lifecycle_basis_hash"
                            ],
                            "final_basis_hash": final_basis_hash,
                        }
                        proof_blob = registration_jcs.encode_blob(
                            "proof", proof_relation
                        )
                        proof_hash = _domain_hash(
                            "awa-registration-proof/v1", proof_blob
                        )
                        certificate_relation = {
                            "effect_id": execution.effect_id,
                            "ledger_head_hash": ledger_head,
                            "completion_hash": completion_hash,
                            "proof_hash": proof_hash,
                            "final_basis_hash": final_basis_hash,
                            "helper_generation": str(
                                member["helper_generation"]
                            ),
                        }
                        certificate_blob = registration_jcs.encode_blob(
                            "certificate_inputs", certificate_relation
                        )
                        certificate_inputs_hash = _domain_hash(
                            "awa-registration-certificate-inputs/v1",
                            certificate_blob,
                        )
                        certificate_hash = registration_hashes.deterministic_id(
                            "awa-reg-certificate-v1",
                            execution.effect_id,
                            ledger_head,
                            completion_hash,
                            proof_hash,
                            str(final_basis_hash),
                            str(member["helper_generation"]),
                        )
                        effect_target.update(
                            {
                                "first_conflict_event_seq": None,
                                "completion_blob": completion_blob,
                                "completion_hash": completion_hash,
                                "final_basis_hash": final_basis_hash,
                                "proof_blob": proof_blob,
                                "proof_hash": proof_hash,
                                "certificate_inputs_blob": certificate_blob,
                                "certificate_inputs_hash": (
                                    certificate_inputs_hash
                                ),
                                "certificate_hash": certificate_hash,
                                "conflict_code": None,
                                "conflict_blob": None,
                                "conflict_hash": None,
                            }
                        )
                    else:
                        conflicts = [
                            row
                            for row in actions
                            if row["observation_kind"] == "LOGICAL_CONFLICT"
                        ]
                        if (
                            len(conflicts) != 1
                            or conflicts[0]["event_seq"]
                            != actions[-1]["event_seq"]
                        ):
                            raise StaleAuthority(
                                "conflict must be the first and final conflict"
                            )
                        conflict_relation = {
                            "effect_id": execution.effect_id,
                            "ordinal": str(conflicts[0]["ordinal"]),
                            "conflict_code": conflict_code,
                            "expected_hash": expected_hash,
                            "observed_hash": observed_hash,
                        }
                        conflict_blob = registration_jcs.encode_blob(
                            "conflict", conflict_relation
                        )
                        conflict_hash = _domain_hash(
                            "awa-registration-conflict/v1", conflict_blob
                        )
                        effect_target.update(
                            {
                                "first_conflict_event_seq": conflicts[0][
                                    "event_seq"
                                ],
                                "completion_blob": None,
                                "completion_hash": None,
                                "final_basis_hash": None,
                                "proof_blob": None,
                                "proof_hash": None,
                                "certificate_inputs_blob": None,
                                "certificate_inputs_hash": None,
                                "certificate_hash": None,
                                "conflict_code": conflict_code,
                                "conflict_blob": conflict_blob,
                                "conflict_hash": conflict_hash,
                            }
                        )
                    effect_target["outcome_tuple_hash"] = (
                        registration_hashes.derive(
                            "outcome_tuple_hash", effect_target
                        )
                    )

                    pending = member["pending_effect_id"] is not None
                    status = dict(old_status)
                    status.update(
                        {
                            "status_version": int(old_status["status_version"])
                            + 1,
                            "executor_token_hash": None,
                            "executor_boot_id": None,
                            "executor_generation": None,
                            "blocked_basis_fingerprint": None,
                        }
                    )
                    if pending:
                        status.update(
                            {
                                "schedule_boot_id": sample_boot_id,
                                "observed_now_mono_ns": sample_mono_ns,
                                "next_due_mono_ns": sample_mono_ns,
                                "due_since_mono_ns": sample_mono_ns,
                                "attempt_count": 0,
                                "backoff_ns": 0,
                                "help_due": 1,
                                "reason_code": "REGISTRATION_REQUIRED",
                            }
                        )
                    else:
                        status.update(
                            {
                                "schedule_boot_id": None,
                                "observed_now_mono_ns": None,
                                "next_due_mono_ns": None,
                                "due_since_mono_ns": None,
                                "attempt_count": None,
                                "backoff_ns": None,
                                "help_due": 0,
                                "reason_code": (
                                    None
                                    if outcome_kind == "SUCCESS"
                                    else "EFFECT_CONFLICT"
                                ),
                            }
                        )
                        if outcome_kind == "SUCCESS":
                            status["unavailable_count"] = 0
                            status["yield_count"] = 0
                    status["status_hash"] = registration_hashes.derive(
                        "status_hash", status
                    )
                    member_target = dict(member)
                    member_target.update(
                        {
                            "phase": "RESOLVED",
                            "current_outcome_kind": outcome_kind,
                            "current_completion_hash": effect_target[
                                "completion_hash"
                            ],
                            "current_proof_hash": effect_target["proof_hash"],
                            "current_certificate_hash": effect_target[
                                "certificate_hash"
                            ],
                            "current_conflict_hash": effect_target[
                                "conflict_hash"
                            ],
                        }
                    )
                    member_target["member_tuple_hash"] = (
                        registration_hashes.derive(
                            "member_tuple_hash", member_target
                        )
                    )
                    operation_kind = (
                        "CLOSE_SUCCESS"
                        if outcome_kind == "SUCCESS"
                        else "CLOSE_CONFLICT"
                    )
                    operation = self._operation_base(
                        operation_id=operation_id,
                        operation_class="DATA",
                        operation_kind=operation_kind,
                        measured_free_bytes=measured,
                        projected_db_growth_bytes=projected_db_growth_bytes,
                        candidate=candidate,
                        control=None,
                        data=data,
                        overrides={
                            "target_member_id": execution.member_id,
                            "target_effect_id": execution.effect_id,
                            "target_executor_token_hash": (
                                execution.executor_token_hash
                            ),
                            "expected_target_status_hash": old_status[
                                "status_hash"
                            ],
                            "target_subject_key": status["subject_key"],
                            "expected_target_member_tuple_hash": member[
                                "member_tuple_hash"
                            ],
                            "expected_target_effect_tuple_hash": effect[
                                "request_tuple_hash"
                            ],
                            "target_member_epoch": member["member_epoch"],
                            "target_basis_hash": member["current_basis_hash"],
                            "target_member_tuple_hash": member_target[
                                "member_tuple_hash"
                            ],
                            "target_effect_tuple_hash": effect[
                                "request_tuple_hash"
                            ],
                            "target_effect_outcome_hash": effect_target[
                                "outcome_tuple_hash"
                            ],
                            "target_action_ledger_hash": ledger_head,
                            "target_status_hash": status["status_hash"],
                            "sample_boot_id": sample_boot_id,
                            "sample_mono_ns": sample_mono_ns,
                        },
                    )
                    effect_target["outcome_operation_seq"] = operation[
                        "operation_seq"
                    ]
                    effect_target["outcome_operation_id"] = operation_id
                    effect_target["outcome_operation_hash"] = operation[
                        "operation_envelope_hash"
                    ]
                    for row in (status, member_target):
                        row["write_operation_seq"] = operation["operation_seq"]
                        row["write_operation_id"] = operation_id
                        row["write_operation_hash"] = operation[
                            "operation_envelope_hash"
                        ]
                    self._insert("registration_operation_audit", operation)
                    self._update_row(
                        "registration_effect",
                        effect_target,
                        primary_key="effect_id",
                        expected_column="outcome_kind",
                        expected_value=None,
                    )
                    self._update_row(
                        "registration_runtime_status",
                        status,
                        primary_key="subject_key",
                        expected_column="status_hash",
                        expected_value=old_status["status_hash"],
                    )
                    self._update_row(
                        "registration_member",
                        member_target,
                        primary_key="member_id",
                        expected_column="member_tuple_hash",
                        expected_value=member["member_tuple_hash"],
                    )
                    closure = self._connection.execute(
                        "SELECT 1 FROM registration_member m "
                        "JOIN registration_effect e "
                        "ON e.effect_id=m.current_effect_id "
                        "JOIN registration_runtime_status s USING(member_id) "
                        "WHERE m.member_id=? AND m.phase='RESOLVED' "
                        "AND m.member_tuple_hash=? "
                        "AND e.outcome_tuple_hash=? AND s.status_hash=?",
                        (
                            execution.member_id,
                            member_target["member_tuple_hash"],
                            effect_target["outcome_tuple_hash"],
                            status["status_hash"],
                        ),
                    ).fetchone()
                    if closure is None:
                        raise StoreError("effect close closure failed")
                    self._commit()
                    self._tighten_files()
                    committed = True
                    result = OperationResult(
                        "COMMITTED",
                        operation_id,
                        operation["operation_envelope_hash"],
                        effect_target["outcome_tuple_hash"],
                    )
                except Exception:
                    if self._connection.in_transaction:
                        self._connection.execute("ROLLBACK")
                    raise
            execution.close()
            return result
        except Exception:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            if committed:
                execution.close()
            raise

    def current_protocol(self) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT * FROM registration_protocol_epoch "
            "ORDER BY protocol_seq DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def read_selected_authority(
        self, member_id: str, *, episode_id: str | None = None
    ) -> SelectedAuthority | None:
        _require_hash(member_id, "member_id")
        if episode_id is not None:
            _require_hash(episode_id, "episode_id")
        with self._read_scope():
            self._connection.execute("BEGIN")
            try:
                protocol_row = self._connection.execute(
                    "SELECT * FROM registration_protocol_epoch "
                    "ORDER BY protocol_seq DESC LIMIT 1"
                ).fetchone()
                member_row = self._connection.execute(
                    "SELECT * FROM registration_member WHERE member_id=?",
                    (member_id,),
                ).fetchone()
                status_row = self._connection.execute(
                    "SELECT * FROM registration_runtime_status "
                    "WHERE member_id=?",
                    (member_id,),
                ).fetchone()
                if (
                    protocol_row is None
                    or member_row is None
                    or status_row is None
                ):
                    self._connection.execute("COMMIT")
                    return None
                member = dict(member_row)
                effect_row = self._connection.execute(
                    "SELECT * FROM registration_effect WHERE effect_id=?",
                    (member["current_effect_id"],),
                ).fetchone()
                if effect_row is None:
                    raise StoreError("selected member effect closure missing")
                effect = dict(effect_row)
                actions = tuple(
                    dict(row)
                    for row in self._connection.execute(
                        "SELECT * FROM registration_effect_action "
                        "WHERE effect_id=? ORDER BY event_seq",
                        (effect["effect_id"],),
                    ).fetchall()
                )
                if episode_id is None:
                    episode_rows = self._connection.execute(
                        "SELECT * FROM registration_episode "
                        "WHERE member_id=? ORDER BY created_wall_ns,episode_id",
                        (member_id,),
                    ).fetchall()
                else:
                    episode_rows = self._connection.execute(
                        "SELECT * FROM registration_episode "
                        "WHERE member_id=? AND episode_id=?",
                        (member_id, episode_id),
                    ).fetchall()
                episodes = tuple(dict(row) for row in episode_rows)
                status = dict(status_row)
                protocol = dict(protocol_row)
                token = (
                    protocol["protocol_seq"],
                    protocol["protocol_hash"],
                    tuple(
                        (episode["episode_id"], episode["envelope_hash"])
                        for episode in episodes
                    ),
                    member["write_operation_seq"],
                    member["member_tuple_hash"],
                    status["status_version"],
                    status["status_hash"],
                    effect["outcome_operation_seq"],
                    effect["outcome_tuple_hash"],
                    effect["ledger_head_hash"],
                )
                self._connection.execute("COMMIT")
                return SelectedAuthority(
                    protocol=protocol,
                    member=member,
                    status=status,
                    effect=effect,
                    actions=actions,
                    episodes=episodes,
                    revision_token=token,
                )
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def read_selected_revision(
        self, member_id: str, *, episode_id: str | None = None
    ) -> tuple[Any, ...] | None:
        authority = self.read_selected_authority(
            member_id, episode_id=episode_id
        )
        return authority.revision_token if authority is not None else None

    def find_member_id(self, identity_value: MemberIdentity) -> str | None:
        with self._read_scope():
            self._connection.execute("BEGIN")
            try:
                row = self._connection.execute(
                    "SELECT member_id,canonical_root,git_toplevel,"
                    "git_dir,git_common_dir FROM registration_member "
                    "WHERE root_dev=? AND root_ino=? "
                    "AND git_dir_dev=? AND git_dir_ino=? "
                    "AND git_common_dev=? AND git_common_ino=?",
                    (
                        identity_value.root_dev,
                        identity_value.root_ino,
                        identity_value.git_dir_dev,
                        identity_value.git_dir_ino,
                        identity_value.git_common_dev,
                        identity_value.git_common_ino,
                    ),
                ).fetchall()
                self._connection.execute("COMMIT")
                if not row:
                    return None
                if len(row) != 1:
                    raise StoreError("duplicate physical member identity")
                current = row[0]
                if (
                    current["canonical_root"]
                    != identity_value.canonical_root
                    or current["git_toplevel"]
                    != identity_value.git_toplevel
                    or current["git_dir"] != identity_value.git_dir
                    or current["git_common_dir"]
                    != identity_value.git_common_dir
                ):
                    raise StaleAuthority(
                        "physical member path changed; explicit repair required"
                    )
                return str(current["member_id"])
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def episode_exists(self, member_id: str, episode_id: str) -> bool:
        _require_hash(member_id, "member_id")
        _require_hash(episode_id, "episode_id")
        return (
            self._connection.execute(
                "SELECT 1 FROM registration_episode "
                "WHERE member_id=? AND episode_id=?",
                (member_id, episode_id),
            ).fetchone()
            is not None
        )

    def list_due_candidates(
        self, *, boot_id: str, now_mono_ns: int, limit: int = 8
    ) -> tuple[DueCandidate, ...]:
        if (
            not isinstance(boot_id, str)
            or not boot_id
            or not isinstance(now_mono_ns, int)
            or isinstance(now_mono_ns, bool)
            or now_mono_ns < 0
            or not 1 <= limit <= 8
        ):
            raise ValueError("invalid due-candidate selector")
        with self._read_scope():
            self._connection.execute("BEGIN")
            try:
                rows = self._connection.execute(
                    "SELECT m.member_id,m.member_epoch,m.phase,"
                    "m.current_effect_id,m.member_tuple_hash,"
                    "m.current_basis_hash,m.pending_basis_hash,"
                    "e.request_tuple_hash,s.status_hash,"
                    "s.due_since_mono_ns,s.observed_now_mono_ns "
                    "FROM registration_runtime_status s "
                    "JOIN registration_member m USING(member_id) "
                    "JOIN registration_effect e "
                    "ON e.effect_id=m.current_effect_id "
                    "WHERE s.schedule_boot_id=? "
                    "AND s.next_due_mono_ns<=? "
                    "AND s.executor_token_hash IS NULL "
                    "ORDER BY COALESCE(s.observed_now_mono_ns,"
                    "s.due_since_mono_ns),s.due_since_mono_ns,m.member_id "
                    "LIMIT ?",
                    (boot_id, now_mono_ns, limit),
                ).fetchall()
                self._connection.execute("COMMIT")
                return tuple(
                    DueCandidate(
                        member_id=row["member_id"],
                        member_epoch=row["member_epoch"],
                        phase=row["phase"],
                        effect_id=row["current_effect_id"],
                        member_tuple_hash=row["member_tuple_hash"],
                        effect_tuple_hash=row["request_tuple_hash"],
                        status_hash=row["status_hash"],
                        current_basis_hash=row["current_basis_hash"],
                        pending_basis_hash=row["pending_basis_hash"],
                        due_since_mono_ns=row["due_since_mono_ns"],
                        observed_now_mono_ns=row["observed_now_mono_ns"],
                    )
                    for row in rows
                )
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def list_reboot_candidates(
        self, current_boot_id: str
    ) -> tuple[RebootCandidate, ...]:
        if not isinstance(current_boot_id, str) or not current_boot_id:
            raise ValueError("current boot id is required")
        with self._read_scope():
            self._connection.execute("BEGIN")
            try:
                rows = self._connection.execute(
                    "SELECT m.member_id,m.phase,m.current_effect_id,"
                    "s.status_hash,CASE WHEN s.executor_token_hash IS NOT NULL "
                    "THEN s.executor_boot_id ELSE s.schedule_boot_id END "
                    "AS stored_boot_id "
                    "FROM registration_member m "
                    "JOIN registration_runtime_status s USING(member_id) "
                    "WHERE (s.executor_token_hash IS NOT NULL "
                    "AND s.executor_boot_id<>?) "
                    "OR (s.executor_token_hash IS NULL "
                    "AND s.schedule_boot_id IS NOT NULL "
                    "AND s.schedule_boot_id<>?) "
                    "ORDER BY m.member_id",
                    (current_boot_id, current_boot_id),
                ).fetchall()
                self._connection.execute("COMMIT")
                return tuple(
                    RebootCandidate(
                        member_id=row["member_id"],
                        phase=row["phase"],
                        effect_id=row["current_effect_id"],
                        status_hash=row["status_hash"],
                        stored_boot_id=row["stored_boot_id"],
                    )
                    for row in rows
                )
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def resolve_operation(self, operation_id: str) -> str:
        """Classify ambiguous SQLite completion from durable authority only."""
        _require_hash(operation_id, "operation_id")
        try:
            operation_row = self._connection.execute(
                "SELECT * FROM registration_operation_audit WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if operation_row is None:
                return "ABSENT"
            operation = dict(operation_row)
            checks: list[bool] = []
            if operation["target_protocol_hash"] is not None:
                checks.append(
                    self._connection.execute(
                        "SELECT 1 FROM registration_protocol_epoch "
                        "WHERE protocol_hash=?",
                        (operation["target_protocol_hash"],),
                    ).fetchone()
                    is not None
                )
            if operation["target_member_tuple_hash"] is not None:
                checks.append(
                    self._connection.execute(
                        "SELECT 1 FROM registration_member "
                        "WHERE member_id=? AND member_tuple_hash=?",
                        (
                            operation["target_member_id"],
                            operation["target_member_tuple_hash"],
                        ),
                    ).fetchone()
                    is not None
                )
            if operation["target_status_hash"] is not None:
                checks.append(
                    self._connection.execute(
                        "SELECT 1 FROM registration_runtime_status "
                        "WHERE member_id=? AND status_hash=?",
                        (
                            operation["target_member_id"],
                            operation["target_status_hash"],
                        ),
                    ).fetchone()
                    is not None
                )
            if operation["target_effect_tuple_hash"] is not None:
                checks.append(
                    self._connection.execute(
                        "SELECT 1 FROM registration_effect "
                        "WHERE request_tuple_hash=?",
                        (operation["target_effect_tuple_hash"],),
                    ).fetchone()
                    is not None
                )
            if operation["target_effect_outcome_hash"] is not None:
                checks.append(
                    self._connection.execute(
                        "SELECT 1 FROM registration_effect "
                        "WHERE outcome_tuple_hash=?",
                        (operation["target_effect_outcome_hash"],),
                    ).fetchone()
                    is not None
                )
            if operation["target_action_ledger_hash"] is not None:
                checks.append(
                    operation["target_action_ledger_hash"] == ZERO_HASH
                    or self._connection.execute(
                        "SELECT 1 FROM registration_effect_action "
                        "WHERE ledger_hash=?",
                        (operation["target_action_ledger_hash"],),
                    ).fetchone()
                    is not None
                )
            if operation["target_episode_hash"] is not None:
                checks.append(
                    self._connection.execute(
                        "SELECT 1 FROM registration_episode "
                        "WHERE envelope_hash=?",
                        (operation["target_episode_hash"],),
                    ).fetchone()
                    is not None
                )
            return "COMMITTED" if all(checks) else "PARTIAL"
        except sqlite3.Error:
            return "UNAVAILABLE"

    def resolve_close(
        self, *, operation_id: str, member_id: str, effect_id: str
    ) -> str:
        try:
            effect = self._connection.execute(
                "SELECT * FROM registration_effect WHERE effect_id=?",
                (effect_id,),
            ).fetchone()
            member = self._connection.execute(
                "SELECT * FROM registration_member WHERE member_id=?",
                (member_id,),
            ).fetchone()
            operation = self._connection.execute(
                "SELECT 1 FROM registration_operation_audit "
                "WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if effect is None or member is None:
                return "UNAVAILABLE"
            if (
                operation is not None
                and member["phase"] == "RESOLVED"
                and member["current_effect_id"] == effect_id
                and effect["outcome_operation_id"] == operation_id
            ):
                if effect["outcome_kind"] == "SUCCESS":
                    return "COMMITTED_SUCCESS"
                if effect["outcome_kind"] == "LOGICAL_CONFLICT":
                    return "COMMITTED_LOGICAL_CONFLICT"
            if (
                operation is None
                and effect["outcome_kind"] is None
                and member["phase"] == "EFFECT_IN_FLIGHT"
                and member["current_effect_id"] == effect_id
            ):
                return "ABSENT"
            return "UNAVAILABLE"
        except sqlite3.Error:
            return "UNAVAILABLE"

    def resolve_reacquire(
        self,
        *,
        operation_id: str,
        member_id: str,
        effect_id: str,
        old_status_hash: str,
    ) -> str:
        try:
            operation = self._connection.execute(
                "SELECT * FROM registration_operation_audit "
                "WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            member = self._connection.execute(
                "SELECT * FROM registration_member WHERE member_id=?",
                (member_id,),
            ).fetchone()
            status = self._connection.execute(
                "SELECT * FROM registration_runtime_status WHERE member_id=?",
                (member_id,),
            ).fetchone()
            effect = self._connection.execute(
                "SELECT * FROM registration_effect WHERE effect_id=?",
                (effect_id,),
            ).fetchone()
            protocol = self.current_protocol()
            if (
                operation is not None
                and member is not None
                and status is not None
                and effect is not None
                and protocol is not None
                and operation["operation_kind"] == "REACQUIRE_EFFECT"
                and operation["target_member_tuple_hash"]
                == member["member_tuple_hash"]
                and operation["target_status_hash"] == status["status_hash"]
                and operation["target_effect_tuple_hash"]
                == effect["request_tuple_hash"]
                and operation["target_protocol_hash"]
                == protocol["protocol_hash"]
                and operation["target_executor_token_hash"]
                == status["executor_token_hash"]
            ):
                return "COMMITTED"
            if (
                operation is None
                and member is not None
                and status is not None
                and effect is not None
                and member["phase"] == "EFFECT_IN_FLIGHT"
                and member["current_effect_id"] == effect_id
                and status["status_hash"] == old_status_hash
                and status["executor_token_hash"] is None
                and status["help_due"] == 1
                and effect["outcome_kind"] is None
            ):
                return "ABSENT"
            if operation is not None:
                return "PARTIAL"
            return "UNAVAILABLE"
        except sqlite3.Error:
            return "UNAVAILABLE"

    def resolve_adoption(self, *, operation_id: str, member_id: str) -> str:
        try:
            operation = self._connection.execute(
                "SELECT * FROM registration_operation_audit "
                "WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if operation is None:
                return "ABSENT"
            if (
                operation["operation_kind"] == "ADOPT_EFFECT"
                and operation["target_member_id"] == member_id
                and self.resolve_operation(operation_id) == "COMMITTED"
            ):
                return "ALREADY_APPLIED"
            return "PARTIAL"
        except sqlite3.Error:
            return "UNAVAILABLE"

    def resolve_successor(
        self,
        *,
        operation_id: str,
        member_id: str,
        expected_member_hash: str,
        target_member_hash: str,
    ) -> str:
        try:
            operation = self._connection.execute(
                "SELECT * FROM registration_operation_audit "
                "WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            member = self._connection.execute(
                "SELECT * FROM registration_member WHERE member_id=?",
                (member_id,),
            ).fetchone()
            if member is None:
                return "UNAVAILABLE"
            if (
                operation is not None
                and operation["target_member_tuple_hash"]
                == target_member_hash
                and member["member_tuple_hash"] == target_member_hash
            ):
                return "APPLIED"
            if operation is None and member["member_tuple_hash"] == expected_member_hash:
                return "ABSENT"
            if (
                operation is None
                and member["member_tuple_hash"] not in {
                    expected_member_hash,
                    target_member_hash,
                }
            ):
                return "OBSOLETE"
            return "UNAVAILABLE"
        except sqlite3.Error:
            return "UNAVAILABLE"

    def table_count(self, table: str) -> int:
        if table not in registration_schema.TABLE_NAMES:
            raise ValueError("unknown registration table")
        return int(
            self._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        )

    def close(self) -> None:
        if self._closed:
            return
        self._connection.close()
        self._closed = True

    def __enter__(self) -> "RegistrationStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
