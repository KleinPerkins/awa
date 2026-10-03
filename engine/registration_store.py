"""Transactional ADR 0025 registration authority (Body A).

This module owns the dedicated seven-table store, authenticated BOOTSTRAP and
CONTROL capabilities, DATA capability boundary, fresh write preflight, and
operation-envelope framing. Product routing and hook admission live outside
Body A.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import secrets
import sqlite3
import threading
import time
from collections.abc import Mapping as MappingABC
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
BASE_OUTCOME_RESERVATION = 49_152
RECOVERY_RESERVATION = 49_152
MIN_OUTCOME_RESERVATION = BASE_OUTCOME_RESERVATION + RECOVERY_RESERVATION
MIN_SUCCESSOR_RESERVATION = 32_768
RECOVERY_OPERATION_BYTES = 8_192
MAX_RECOVERY_OPERATIONS = 6
UNVALIDATED_EFFECT_CHARGE = 18_874_368
UNVALIDATED_SUCCESSOR_CHARGE = 1_048_576
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
_CONTROL_OPERATION_KINDS = frozenset(
    {
        "ACTIVATE",
        "BEGIN_DRAIN",
        "STAGE_NEXT",
        "CANCEL_DRAIN",
        "ADOPT_EFFECT",
        "ADVANCE_GENERATION",
        "PRE_EFFECT_DORMANT",
        "ENTER_CONTAINMENT",
        "BEGIN_REPAIR",
    }
)
_EFFECT_CREATION_KINDS = frozenset(
    {
        "INSTALL_MEMBER",
        "INVALIDATE_REQUESTED",
        "SET_PENDING",
        "REPLACE_PENDING",
        "HANDOFF_RESOLVED",
        "ADOPT_EFFECT",
    }
)
_MEMBER_WRITE_KINDS = frozenset(
    {
        "INSTALL_MEMBER",
        "OPEN_EFFECT",
        "INVALIDATE_REQUESTED",
        "SET_PENDING",
        "REPLACE_PENDING",
        "HANDOFF_RESOLVED",
        "ADOPT_EFFECT",
        "CLOSE_SUCCESS",
        "CLOSE_CONFLICT",
    }
)
_STATUS_WRITE_KINDS = frozenset(
    {
        "INSTALL_MEMBER",
        "OPEN_EFFECT",
        "REACQUIRE_EFFECT",
        "ADOPT_EFFECT",
        "MARK_UNAVAILABLE",
        "REBOOT_STATUS",
        "SCHEDULE_STATUS",
        "INVALIDATE_REQUESTED",
        "SET_PENDING",
        "REPLACE_PENDING",
        "HANDOFF_RESOLVED",
        "CLOSE_SUCCESS",
        "CLOSE_CONFLICT",
    }
)

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


class SemanticClosureError(StoreUnavailable):
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
        _require_int(
            self.projection_file_generation,
            "projection_file_generation",
            minimum=1,
        )
        _require_int(self.storage_dev, "storage_dev", minimum=0)
        if self.projection_file_generation < 1 or self.storage_dev < 0:
            raise ValueError("invalid candidate generation/device")


_CONTROL_SEAL = object()
_DATA_SEAL = object()
_EXECUTION_SEAL = object()
_TEST_PROFILE_SEAL = object()
_CREATION_LOCK_SEAL = object()
_RECOVERY_EXHAUSTION_SEAL = object()
_UNSPECIFIED = object()


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


class RecoveryReserveExhausted:
    """Sealed, process-only evidence that no recovery audit byte remains."""

    __slots__ = (
        "protocol_hash",
        "staged_epoch_hash",
        "member_id",
        "effect_id",
        "member_tuple_hash",
        "status_hash",
        "executor_token_hash",
        "recovery_operation_count",
        "recovery_bytes_consumed",
        "recovery_bytes_reserved",
        "_seal",
    )

    def __init__(
        self,
        *,
        protocol_hash: str,
        staged_epoch_hash: str | None,
        member_id: str,
        effect_id: str,
        member_tuple_hash: str,
        status_hash: str,
        executor_token_hash: str | None,
        _seal: object,
    ) -> None:
        if _seal is not _RECOVERY_EXHAUSTION_SEAL:
            raise AuthorizationError("recovery exhaustion is store-authenticated")
        for field, value in (
            ("protocol_hash", protocol_hash),
            ("member_id", member_id),
            ("effect_id", effect_id),
            ("member_tuple_hash", member_tuple_hash),
            ("status_hash", status_hash),
        ):
            _require_hash(value, field)
        if staged_epoch_hash is not None:
            _require_hash(staged_epoch_hash, "staged_epoch_hash")
        if executor_token_hash is not None:
            _require_hash(executor_token_hash, "executor_token_hash")
        object.__setattr__(self, "protocol_hash", protocol_hash)
        object.__setattr__(self, "staged_epoch_hash", staged_epoch_hash)
        object.__setattr__(self, "member_id", member_id)
        object.__setattr__(self, "effect_id", effect_id)
        object.__setattr__(self, "member_tuple_hash", member_tuple_hash)
        object.__setattr__(self, "status_hash", status_hash)
        object.__setattr__(self, "executor_token_hash", executor_token_hash)
        object.__setattr__(self, "recovery_operation_count", "6")
        object.__setattr__(self, "recovery_bytes_consumed", "49152")
        object.__setattr__(self, "recovery_bytes_reserved", "49152")
        object.__setattr__(self, "_seal", _seal)

    def __setattr__(self, _name: str, _value: object) -> None:
        raise AuthorizationError("recovery exhaustion is immutable")

    def __reduce__(self) -> object:
        raise TypeError("recovery exhaustion is process-memory-only")


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
        "_transferred",
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
        object.__setattr__(self, "_transferred", False)
        object.__setattr__(self, "_sealed", True)

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_sealed", False):
            raise AuthorizationError("executor capability is immutable")
        object.__setattr__(self, name, value)

    @property
    def held(self) -> bool:
        return self._member_lock.held

    def verify_owner(self, store: "RegistrationStore") -> None:
        if self._store_identity != id(store) or not self.held or self._transferred:
            raise AuthorizationError("executor capability is not live for this store")
        self._member_lock.verify()

    def close(self) -> None:
        for index in range(len(self._secret)):
            self._secret[index] = 0
        self._member_lock.release()

    def _transfer_staged(
        self,
        transfer: registration_executor.StagedSecretTransfer,
        *,
        deadline_ns: int,
    ) -> None:
        if not self.held or self._transferred:
            raise AuthorizationError("executor capability is not live")
        if self.target_staged_epoch_hash is None:
            raise AuthorizationError("only staged executors may transfer custody")
        frame = registration_executor.StagedGrantFrame(
            member_id=self.member_id,
            effect_id=self.effect_id,
            executor_token_hash=self.executor_token_hash,
            operation_id=self.operation_id,
            member_tuple_hash=self.target_member_hash,
            status_hash=self.target_status_hash,
            protocol_hash=self.target_protocol_hash,
            staged_epoch_hash=self.target_staged_epoch_hash,
        )
        try:
            transfer.send_frame(frame, self._secret, deadline_ns=deadline_ns)
            transfer.wait_received(frame.digest, deadline_ns=deadline_ns)
            object.__setattr__(self, "_transferred", True)
            self._member_lock.release()
            transfer.wait_activated(frame.digest, deadline_ns=deadline_ns)
        finally:
            if self._transferred:
                for index in range(len(self._secret)):
                    self._secret[index] = 0
            transfer.close()

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
class _ValidatedMapping(MappingABC[str, Any]):
    _items: tuple[tuple[str, Any], ...]

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "_ValidatedMapping":
        return cls(tuple((key, row[key]) for key in row))

    def __getitem__(self, key: str) -> Any:
        for candidate, value in self._items:
            if candidate == key:
                return value
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return (key for key, _value in self._items)

    def __len__(self) -> int:
        return len(self._items)


class ValidatedProtocol(_ValidatedMapping):
    pass


class ValidatedOperation(_ValidatedMapping):
    pass


class ValidatedMember(_ValidatedMapping):
    pass


class ValidatedStatus(_ValidatedMapping):
    pass


class ValidatedEffect(_ValidatedMapping):
    pass


class ValidatedAction(_ValidatedMapping):
    pass


class ValidatedEpisode(_ValidatedMapping):
    pass


@dataclass(frozen=True)
class SelectedAuthority:
    protocol: ValidatedProtocol
    member: ValidatedMember
    status: ValidatedStatus
    effect: ValidatedEffect
    actions: tuple[ValidatedAction, ...]
    episodes: tuple[ValidatedEpisode, ...]
    revision_token: tuple[Any, ...]
    pending_effect: ValidatedEffect | None = None
    predecessor_effect: ValidatedEffect | None = None
    successor_effect: ValidatedEffect | None = None
    operations: tuple[ValidatedOperation, ...] = ()


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

    def __post_init__(self) -> None:
        for field in (
            "member_id",
            "effect_id",
            "member_tuple_hash",
            "effect_tuple_hash",
            "status_hash",
            "current_basis_hash",
        ):
            _require_hash(getattr(self, field), field)
        if self.pending_basis_hash is not None:
            _require_hash(self.pending_basis_hash, "pending_basis_hash")
        _require_int(self.member_epoch, "member_epoch", minimum=1)
        _require_int(
            self.due_since_mono_ns, "due_since_mono_ns", minimum=0
        )
        _require_int(
            self.observed_now_mono_ns,
            "observed_now_mono_ns",
            minimum=0,
        )
        if self.phase not in {
            "REQUESTED",
            "EFFECT_IN_FLIGHT",
            "RESOLVED",
        }:
            raise ValueError("invalid member phase")


@dataclass(frozen=True)
class RebootCandidate:
    member_id: str
    phase: str
    effect_id: str
    status_hash: str
    stored_boot_id: str

    def __post_init__(self) -> None:
        for field in ("member_id", "effect_id", "status_hash"):
            _require_hash(getattr(self, field), field)
        if self.phase not in {
            "REQUESTED",
            "EFFECT_IN_FLIGHT",
            "RESOLVED",
        }:
            raise ValueError("invalid member phase")
        if (
            not isinstance(self.stored_boot_id, str)
            or not self.stored_boot_id
        ):
            raise ValueError("stored_boot_id must be nonempty")


@dataclass(frozen=True)
class StagedCustodyObligation:
    operation_id: str
    operation_kind: str
    member_id: str
    effect_id: str
    status_hash: str
    executor_token_hash: str
    executor_generation: int
    staged_epoch_hash: str
    member_tuple_hash: str


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
        device_values = (
            self.root_dev,
            self.git_dir_dev,
            self.git_common_dev,
            self.proof_dev,
            self.projection_dev,
            self.legacy_state_dev,
        )
        devices = set(device_values)
        if (
            any(type(value) is not int for value in device_values)
            or len(devices) != 1
            or min(devices) < 0
        ):
            raise ValueError("member identity must be same-device")
        for field in ("root_ino", "git_dir_ino", "git_common_ino"):
            value = getattr(self, field)
            if type(value) is not int or value < 0:
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
        _require_int(
            self.external_growth_reservation_bytes,
            "external_growth_reservation_bytes",
            minimum=0,
        )
        _require_int(
            self.outcome_reservation_bytes,
            "outcome_reservation_bytes",
            minimum=MIN_OUTCOME_RESERVATION,
        )
        _require_int(
            self.successor_reservation_bytes,
            "successor_reservation_bytes",
            minimum=MIN_SUCCESSOR_RESERVATION,
        )
        if not 0 <= self.external_growth_reservation_bytes <= 16 * 1024**2:
            raise ValueError("external reservation out of bounds")
        if not MIN_OUTCOME_RESERVATION <= self.outcome_reservation_bytes <= 1024**2:
            raise ValueError("outcome reservation out of bounds")
        if (
            not MIN_SUCCESSOR_RESERVATION
            <= self.successor_reservation_bytes
            <= 1024**2
        ):
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


def _require_int(value: object, field: str, *, minimum: int | None = None) -> int:
    if type(value) is not int:
        raise ValueError(f"{field} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{field} must be at least {minimum}")
    return value


@dataclass(frozen=True)
class FreshMemberBasis:
    identity: MemberIdentity
    intent: EffectIntent
    workspace_roots_hash: str

    def __post_init__(self) -> None:
        if type(self.identity) is not MemberIdentity:
            raise ValueError("identity must be MemberIdentity")
        if type(self.intent) is not EffectIntent:
            raise ValueError("intent must be EffectIntent")
        _require_hash(self.workspace_roots_hash, "workspace_roots_hash")
        if self.identity.current_basis_hash != self.intent.request_basis_hash:
            raise ValueError("fresh member/effect basis mismatch")


@dataclass(frozen=True)
class SameBootCandidate:
    member_id: str
    status_hash: str
    executor_token_hash: str
    executor_generation: int

    def __post_init__(self) -> None:
        for field in (
            "member_id",
            "status_hash",
            "executor_token_hash",
        ):
            _require_hash(getattr(self, field), field)
        _require_int(
            self.executor_generation,
            "executor_generation",
            minimum=1,
        )


@dataclass(frozen=True)
class SameBootSnapshot:
    boot_id: str
    protocol_seq: int
    protocol_hash: str
    candidates: tuple[SameBootCandidate, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.boot_id, str) or not self.boot_id:
            raise ValueError("boot_id must be nonempty")
        _require_int(self.protocol_seq, "protocol_seq", minimum=1)
        _require_hash(self.protocol_hash, "protocol_hash")
        if type(self.candidates) is not tuple or any(
            type(candidate) is not SameBootCandidate
            for candidate in self.candidates
        ):
            raise ValueError(
                "candidates must be a tuple of SameBootCandidate"
            )
        member_ids = tuple(
            candidate.member_id for candidate in self.candidates
        )
        if member_ids != tuple(sorted(member_ids)) or len(
            member_ids
        ) != len(set(member_ids)):
            raise ValueError(
                "same-boot candidates must be unique and bytewise ordered"
            )


@dataclass(frozen=True)
class R1ScopeSelection:
    authorized_same_boot: SameBootCandidate | None
    authorized_due: DueCandidate | None
    authorized_reboot: RebootCandidate | None
    outside_scope_same_boot: bool
    outside_scope_due: bool
    outside_scope_reboot: bool

    def __post_init__(self) -> None:
        for field, expected in (
            ("authorized_same_boot", SameBootCandidate),
            ("authorized_due", DueCandidate),
            ("authorized_reboot", RebootCandidate),
        ):
            value = getattr(self, field)
            if value is not None and type(value) is not expected:
                raise ValueError(f"{field} has the wrong typed value")
        for field in (
            "outside_scope_same_boot",
            "outside_scope_due",
            "outside_scope_reboot",
        ):
            if type(getattr(self, field)) is not bool:
                raise ValueError(f"{field} must be a boolean")


_MEMBER_SCOPE_SEAL = object()


class MemberMutationScope:
    __slots__ = (
        "_store",
        "_member_id",
        "_timeout_seconds",
        "_owner_pid",
        "_owner_thread",
        "_held_lock",
        "_active",
        "_entered",
        "_basis",
    )

    def __init__(
        self,
        store: "RegistrationStore",
        member_id: str,
        timeout_seconds: float,
        *,
        _seal: object,
    ) -> None:
        if _seal is not _MEMBER_SCOPE_SEAL:
            raise AuthorizationError(
                "member mutation scope is store-authenticated"
            )
        _require_hash(member_id, "member_id")
        if isinstance(timeout_seconds, bool) or not isinstance(
            timeout_seconds, (int, float)
        ):
            raise ValueError("timeout_seconds must be nonnegative")
        try:
            normalized_timeout = float(timeout_seconds)
        except OverflowError as error:
            raise ValueError(
                "timeout_seconds must be nonnegative"
            ) from error
        if (
            not math.isfinite(normalized_timeout)
            or normalized_timeout < 0
            or normalized_timeout > threading.TIMEOUT_MAX
        ):
            raise ValueError("timeout_seconds must be nonnegative")
        self._store = store
        self._member_id = member_id
        self._timeout_seconds = normalized_timeout
        self._owner_pid = os.getpid()
        self._owner_thread = threading.get_ident()
        self._held_lock: registration_lock.HeldLock | None = None
        self._active = False
        self._entered = False
        self._basis: FreshMemberBasis | None = None

    def __reduce__(self) -> object:
        raise TypeError("member mutation scope is not serializable")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("member mutation scope is not serializable")

    def __getstate__(self) -> object:
        raise TypeError("member mutation scope is not serializable")

    def _require_owner(self) -> None:
        if (
            os.getpid() != self._owner_pid
            or threading.get_ident() != self._owner_thread
        ):
            raise AuthorizationError(
                "member mutation scope owner changed"
            )

    def _require_active(self) -> registration_lock.HeldLock:
        self._require_owner()
        if (
            not self._active
            or self._held_lock is None
            or self._store._closed
        ):
            raise AuthorizationError(
                "member mutation scope is not active"
            )
        self._store._validate_member_lock(
            self._member_id, self._held_lock
        )
        return self._held_lock

    def _require_basis(
        self, basis: FreshMemberBasis
    ) -> registration_lock.HeldLock:
        held = self._require_active()
        if type(basis) is not FreshMemberBasis or basis is not self._basis:
            raise StaleAuthority(
                "fresh basis is not current for this member scope"
            )
        return held

    @staticmethod
    def _basis_update(basis: FreshMemberBasis) -> BasisUpdate:
        identity_value = basis.identity
        return BasisUpdate(
            policy_basis_hash=identity_value.policy_basis_hash,
            operation_basis_hash=identity_value.operation_basis_hash,
            lifecycle_basis_hash=identity_value.lifecycle_basis_hash,
            current_basis_hash=identity_value.current_basis_hash,
        )

    def __enter__(self) -> "MemberMutationScope":
        self._require_owner()
        if self._entered or self._active:
            raise AuthorizationError(
                "member mutation scope is single-use"
            )
        if self._store._closed:
            raise AuthorizationError("registration store is closed")
        self._entered = True
        held = self._store._locks.acquire_member(
            self._member_id, timeout=self._timeout_seconds
        )
        try:
            self._store._validate_member_lock(self._member_id, held)
        except BaseException:
            held.release()
            raise
        self._held_lock = held
        self._active = True
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        _exception: BaseException | None,
        _traceback: object,
    ) -> bool:
        self._require_owner()
        held = self._held_lock
        self._active = False
        self._basis = None
        self._held_lock = None
        if held is not None:
            try:
                held.release()
            except BaseException:
                if exception_type is None:
                    raise
        return False

    def collect_fresh_basis(
        self, provider: Callable[[], FreshMemberBasis]
    ) -> FreshMemberBasis:
        self._require_active()
        if not callable(provider):
            raise AuthorizationError(
                "fresh-basis provider must be callable"
            )
        self._basis = None
        value = provider()
        self._require_active()
        if type(value) is not FreshMemberBasis:
            raise AuthorizationError(
                "fresh-basis provider returned the wrong type"
            )
        expected_member_id = self._store._member_id(value.identity)
        if expected_member_id != self._member_id:
            raise StaleAuthority("fresh basis belongs to another member")
        collected = FreshMemberBasis(
            identity=value.identity,
            intent=value.intent,
            workspace_roots_hash=value.workspace_roots_hash,
        )
        self._basis = collected
        return collected

    def install_member(
        self,
        data: DataCapability,
        candidate: ProtocolCandidate,
        basis: FreshMemberBasis,
        *,
        sample_boot_id: str | None = None,
        sample_mono_ns: int | None = None,
        operation_id: str | None = None,
        projected_db_growth_bytes: int = 0,
    ) -> OperationResult:
        held = self._require_basis(basis)
        return self._store.install_member(
            data,
            candidate,
            basis.identity,
            basis.intent,
            sample_boot_id=sample_boot_id,
            sample_mono_ns=sample_mono_ns,
            operation_id=operation_id,
            projected_db_growth_bytes=projected_db_growth_bytes,
            _member_lock=held,
        )

    def bind_episode(
        self,
        data: DataCapability,
        candidate: ProtocolCandidate,
        basis: FreshMemberBasis,
        *,
        source: EpisodeSource,
        operation_id: str | None = None,
        projected_db_growth_bytes: int = 0,
    ) -> OperationResult:
        held = self._require_basis(basis)
        if source.workspace_roots_hash != basis.workspace_roots_hash:
            raise StaleAuthority(
                "episode roots do not match the fresh member basis"
            )
        return self._store.bind_episode(
            data,
            candidate,
            member_id=self._member_id,
            source=source,
            operation_id=operation_id,
            projected_db_growth_bytes=projected_db_growth_bytes,
            _member_lock=held,
        )

    def invalidate_requested(
        self,
        data: DataCapability,
        candidate: ProtocolCandidate,
        basis: FreshMemberBasis,
        *,
        expected_member_hash: str,
        expected_effect_hash: str,
        expected_status_hash: str,
        operation_id: str | None = None,
        projected_db_growth_bytes: int = 0,
    ) -> OperationResult:
        held = self._require_basis(basis)
        return self._store.invalidate_requested(
            data,
            candidate,
            member_id=self._member_id,
            expected_member_hash=expected_member_hash,
            expected_effect_hash=expected_effect_hash,
            expected_status_hash=expected_status_hash,
            basis=self._basis_update(basis),
            intent=basis.intent,
            operation_id=operation_id,
            projected_db_growth_bytes=projected_db_growth_bytes,
            _member_lock=held,
        )

    def set_pending(
        self,
        data: DataCapability,
        candidate: ProtocolCandidate,
        basis: FreshMemberBasis,
        *,
        expected_member_hash: str,
        expected_effect_hash: str,
        expected_status_hash: str,
        operation_id: str | None = None,
    ) -> OperationResult:
        held = self._require_basis(basis)
        return self._store.set_pending(
            data,
            candidate,
            member_id=self._member_id,
            expected_member_hash=expected_member_hash,
            expected_effect_hash=expected_effect_hash,
            expected_status_hash=expected_status_hash,
            basis_hash=basis.identity.current_basis_hash,
            intent=basis.intent,
            operation_id=operation_id,
            _member_lock=held,
        )

    def replace_pending(
        self,
        data: DataCapability,
        candidate: ProtocolCandidate,
        basis: FreshMemberBasis,
        *,
        expected_member_hash: str,
        expected_effect_hash: str,
        expected_status_hash: str,
        operation_id: str | None = None,
    ) -> OperationResult:
        held = self._require_basis(basis)
        return self._store.replace_pending(
            data,
            candidate,
            member_id=self._member_id,
            expected_member_hash=expected_member_hash,
            expected_effect_hash=expected_effect_hash,
            expected_status_hash=expected_status_hash,
            basis_hash=basis.identity.current_basis_hash,
            intent=basis.intent,
            operation_id=operation_id,
            _member_lock=held,
        )

    def handoff_resolved(
        self,
        data: DataCapability,
        candidate: ProtocolCandidate,
        basis: FreshMemberBasis,
        *,
        expected_member_hash: str,
        expected_effect_hash: str,
        expected_status_hash: str,
        cause: str | None = None,
        operation_id: str | None = None,
    ) -> OperationResult:
        held = self._require_basis(basis)
        return self._store.handoff_resolved(
            data,
            candidate,
            member_id=self._member_id,
            expected_member_hash=expected_member_hash,
            expected_effect_hash=expected_effect_hash,
            expected_status_hash=expected_status_hash,
            cause=cause,
            basis=self._basis_update(basis),
            intent=basis.intent,
            operation_id=operation_id,
            _member_lock=held,
        )

    def mark_dead_executor_unavailable(
        self,
        data: DataCapability,
        candidate: ProtocolCandidate,
        *,
        expected_status_hash: str,
        profile_binding: (
            registration_profile.TypedProfileBinding | None
        ) = None,
        operation_id: str | None = None,
    ) -> OperationResult | RecoveryReserveExhausted:
        held = self._require_active()
        return self._store.mark_dead_executor_unavailable(
            data,
            candidate,
            member_id=self._member_id,
            expected_status_hash=expected_status_hash,
            profile_binding=profile_binding,
            operation_id=operation_id,
            _member_lock=held,
        )


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

    @staticmethod
    def _member_id(identity_value: MemberIdentity) -> str:
        return registration_hashes.deterministic_id(
            "awa-reg-member-v1",
            identity_value.canonical_root,
            str(identity_value.root_dev),
            str(identity_value.root_ino),
            identity_value.git_dir,
            str(identity_value.git_dir_dev),
            str(identity_value.git_dir_ino),
            identity_value.git_common_dir,
            str(identity_value.git_common_dev),
            str(identity_value.git_common_ino),
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
        self._activated_staged_grants: set[str] = set()
        fresh_publication = False
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
            if (
                self.db_path.exists()
                and registration_schema.has_fresh_schema_residue(
                    self.db_path
                )
            ):
                raise StoreUnavailable(
                    "unclassified fresh-schema residue blocks startup"
                )
            if not self.db_path.exists():
                registration_schema.publish_fresh_schema(
                    self.db_path, fault=self._fault
                )
                fresh_publication = True
        else:
            fresh_publication = self._prepare_supported_file(
                _creation_control
            )
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
            existing_objects = self._connection.execute(
                "SELECT COUNT(*) FROM sqlite_schema "
                "WHERE name NOT LIKE 'sqlite_%'"
            ).fetchone()[0]
            if existing_objects == 0:
                raise StoreUnavailable(
                    "existing empty database is not canonical authority"
                )
            try:
                registration_schema.verify_canonical_schema(self._connection)
            except RuntimeError as error:
                raise StoreUnavailable(
                    "registration schema is not canonical v2 authority"
                ) from error
            self._configure()
            if fresh_publication:
                self._connection.execute("BEGIN IMMEDIATE")
                self._connection.execute("ROLLBACK")
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
            self._current_typed_profile_binding: (
                registration_profile.CurrentProfileBinding | None
            ) = None
            self._staged_typed_profile_binding: (
                registration_profile.StagedProfileBinding | None
            ) = None
            if not allow_test_profile and self._profile_binding is None:
                raise StoreUnavailable(
                    "supported profile measurement is required"
                )
            self._require_live_profile_matches_protocol()
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
                    self._require_live_profile_matches_protocol()
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

    def _require_live_profile_matches_protocol(self) -> None:
        if self._profile_binding is None:
            return
        current = self._connection.execute(
            "SELECT profile_hash,storage_dev "
            "FROM registration_protocol_epoch "
            "ORDER BY protocol_seq DESC LIMIT 1"
        ).fetchone()
        if current is not None and (
            current["profile_hash"] != self._profile_binding.digest
            or type(current["storage_dev"]) is not int
            or current["storage_dev"] != self._profile_binding.storage_dev
        ):
            raise registration_profile.ProfileError(
                "live profile/device does not match protocol authority"
            )

    def _require_typed_profile_binding(
        self,
        candidate: ProtocolCandidate,
        binding: registration_profile.TypedProfileBinding | None,
        *,
        staged: bool,
    ) -> registration_profile.TypedProfileBinding | None:
        if self._allow_test_profile and binding is None:
            return None
        expected_type = (
            registration_profile.StagedProfileBinding
            if staged
            else registration_profile.CurrentProfileBinding
        )
        if type(binding) is not expected_type:
            raise registration_profile.ProfileError(
                f"{expected_type.role.lower()} typed profile is required"
            )
        assert binding is not None
        measured = binding.recheck(self._connection)
        if (
            binding.digest != candidate.profile_hash
            or binding.storage_dev != candidate.storage_dev
            or type(measured) is not int
            or measured < 0
        ):
            raise registration_profile.ProfileError(
                "typed profile does not match candidate authority"
            )
        if not staged and self._profile_binding is not None and (
            binding.profile.descriptor_digest
            != self._profile_binding.descriptor_digest
            or binding.digest != self._profile_binding.digest
            or binding.storage_dev != self._profile_binding.storage_dev
        ):
            raise registration_profile.ProfileError(
                "current typed profile changed"
            )
        return binding

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
    ) -> bool:
        fresh_publication = False
        if not self.db_path.parent.exists():
            raise StoreUnavailable(
                "installer must pre-create the private registration directory"
            )
        with registration_profile.bind_secure_path(
            self.db_path.parent,
            kind="directory",
            required_mode=0o700,
        ) as parent:
            if (
                self.db_path.exists()
                and registration_schema.has_fresh_schema_residue(
                    self.db_path
                )
            ):
                raise StoreUnavailable(
                    "unclassified fresh-schema residue blocks startup"
                )
            if not self.db_path.exists():
                if creation_control is None:
                    raise AuthorizationError(
                        "database creation requires installer CONTROL"
                    )
                registration_schema.publish_fresh_schema(
                    self.db_path, fault=self._fault
                )
                fresh_publication = True
            with registration_profile.bind_secure_path(
                self.db_path, kind="file", required_mode=0o600
            ) as bound:
                self._initial_db_identity = bound.identity
        return fresh_publication

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

    def member_mutation_scope(
        self, member_id: str, timeout_seconds: float = 5.0
    ) -> MemberMutationScope:
        if self._closed:
            raise AuthorizationError("registration store is closed")
        return MemberMutationScope(
            self,
            member_id,
            timeout_seconds,
            _seal=_MEMBER_SCOPE_SEAL,
        )

    def _validate_member_lock(
        self,
        member_id: str,
        held: registration_lock.HeldLock,
    ) -> None:
        _require_hash(member_id, "member_id")
        expected_key = f"member-{member_id}.lock"
        expected_path = self._locks.directory / expected_key
        if (
            type(held) is not registration_lock.HeldLock
            or held.kind != "member"
            or held.key != expected_key
            or held.path != expected_path
            or held.process_lock
            is not registration_lock._process_lock(str(expected_path))
            or not held.process_lock.locked()
            or registration_lock._held()["member"] != expected_key
            or not held.held
        ):
            raise AuthorizationError(
                "member lock does not belong to this store and member"
            )
        held.verify()

    @contextmanager
    def _member_lock_scope(
        self,
        member_id: str,
        held: registration_lock.HeldLock | None,
    ) -> Iterator[registration_lock.HeldLock]:
        if held is None:
            with self._locks.acquire_member(member_id) as acquired:
                self._validate_member_lock(member_id, acquired)
                yield acquired
            return
        self._validate_member_lock(member_id, held)
        yield held

    def _begin(self) -> int:
        self._fault("before_begin")
        self._connection.execute("BEGIN IMMEDIATE")
        self._fault("after_begin")
        if self._profile_binding is not None:
            value = self._profile_binding.recheck(self._connection)
            self._require_live_profile_matches_protocol()
        else:
            fd = os.open(
                self.db_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            )
            try:
                assert self._free_bytes is not None
                value = self._free_bytes(fd)
            finally:
                os.close(fd)
        if type(value) is not int or value < 0:
            raise StoreUnavailable("negative free-space measurement")
        return value

    def _commit(self) -> None:
        latest = self._connection.execute(
            "SELECT operation_id FROM registration_operation_audit "
            "ORDER BY operation_seq DESC LIMIT 1"
        ).fetchone()
        if (
            latest is None
            or self._resolve_operation_tx(latest["operation_id"]) != "COMMITTED"
        ):
            raise StoreError("mandatory operation closure SELECT failed")
        self._fault("before_commit")
        self._connection.execute("COMMIT")
        self._fault("after_commit")

    def _fresh_sample(self) -> tuple[str, int]:
        boot = self._boot_id()
        mono = self._mono_ns()
        if (
            not isinstance(boot, str)
            or not boot
            or type(mono) is not int
            or mono < 0
        ):
            raise StoreUnavailable("boot/continuous-time sample unavailable")
        return boot, mono

    def _fresh_wall_ns(self) -> int:
        value = self._wall_ns()
        if type(value) is not int or value < 0:
            raise StoreUnavailable("wall-clock sample unavailable")
        return value

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

    @staticmethod
    def _effect_outcome_is_total(effect: Mapping[str, Any]) -> bool:
        fields = frozenset(
            {
                "outcome_helper_generation",
                "outcome_tuple_hash",
                "ledger_head_hash",
                "first_conflict_event_seq",
                "completion_blob",
                "completion_hash",
                "final_basis_hash",
                "proof_blob",
                "proof_hash",
                "certificate_inputs_blob",
                "certificate_inputs_hash",
                "certificate_hash",
                "conflict_code",
                "conflict_blob",
                "conflict_hash",
                "superseded_by_effect_id",
                "successor_transition_id",
                "outcome_operation_seq",
                "outcome_operation_id",
                "outcome_operation_hash",
            }
        )
        outcome = effect["outcome_kind"]
        if outcome is None:
            required: frozenset[str] = frozenset()
        elif outcome == "SUCCESS" and effect["request_kind"] == "CLEAN_ELIGIBLE":
            required = frozenset(
                {
                    "outcome_helper_generation",
                    "outcome_tuple_hash",
                    "ledger_head_hash",
                    "completion_blob",
                    "completion_hash",
                    "final_basis_hash",
                    "proof_blob",
                    "proof_hash",
                    "certificate_inputs_blob",
                    "certificate_inputs_hash",
                    "certificate_hash",
                    "outcome_operation_seq",
                    "outcome_operation_id",
                    "outcome_operation_hash",
                }
            )
        elif (
            outcome == "LOGICAL_CONFLICT"
            and effect["request_kind"] == "CLEAN_ELIGIBLE"
        ):
            required = frozenset(
                {
                    "outcome_helper_generation",
                    "outcome_tuple_hash",
                    "ledger_head_hash",
                    "first_conflict_event_seq",
                    "conflict_code",
                    "conflict_blob",
                    "conflict_hash",
                    "outcome_operation_seq",
                    "outcome_operation_id",
                    "outcome_operation_hash",
                }
            )
        elif outcome == "SUPERSEDED":
            required = frozenset(
                {
                    "outcome_tuple_hash",
                    "superseded_by_effect_id",
                    "successor_transition_id",
                    "outcome_operation_seq",
                    "outcome_operation_id",
                    "outcome_operation_hash",
                }
            )
        else:
            return False
        return all(
            (effect[field] is not None) == (field in required)
            for field in fields
        )

    def _effect_has_terminal_witness(
        self, effect: Mapping[str, Any]
    ) -> bool:
        if (
            effect["outcome_kind"] is None
            or not self._effect_outcome_is_total(effect)
        ):
            return False
        try:
            member_row = self._connection.execute(
                "SELECT * FROM registration_member WHERE member_id=?",
                (effect["member_id"],),
            ).fetchone()
            if member_row is None:
                return False
            member = dict(member_row)
            if (
                registration_hashes.derive("member_tuple_hash", member)
                != member["member_tuple_hash"]
            ):
                return False
            operations: dict[str, ValidatedOperation] = {}
            validated, _actions = self._validate_effect_row(
                effect,
                member=member,
                operations=operations,
                include_actions=True,
            )
            self._validate_effect_predecessor(
                validated,
                member=member,
                operations=operations,
            )
            if effect["outcome_kind"] == "SUPERSEDED":
                successor_row = self._connection.execute(
                    "SELECT * FROM registration_effect WHERE effect_id=?",
                    (effect["superseded_by_effect_id"],),
                ).fetchone()
                if successor_row is None:
                    return False
                successor, _ignored = self._validate_effect_row(
                    successor_row,
                    member=member,
                    operations=operations,
                    include_actions=False,
                )
                if successor["predecessor_effect_id"] != effect["effect_id"]:
                    return False
                operation = operations.get(effect["outcome_operation_id"])
                if operation is None:
                    return False
                self._validate_successor_transition(
                    predecessor=validated,
                    successor=successor,
                    operation=operation,
                )
            return True
        except (KeyError, TypeError, ValueError, sqlite3.Error, StoreError):
            return False

    def _effect_is_resolved_current(
        self, effect: Mapping[str, Any]
    ) -> bool:
        try:
            member_rows = self._connection.execute(
                "SELECT * FROM registration_member "
                "WHERE current_effect_id=?",
                (effect["effect_id"],),
            ).fetchall()
            if len(member_rows) != 1:
                return False
            member = dict(member_rows[0])
            if (
                registration_hashes.derive("member_tuple_hash", member)
                != member["member_tuple_hash"]
                or member["member_id"] != effect["member_id"]
                or member["member_epoch"] != effect["member_epoch"]
                or member["phase"] != "RESOLVED"
                or member["current_outcome_kind"] != effect["outcome_kind"]
                or member["current_completion_hash"]
                != effect["completion_hash"]
                or member["current_proof_hash"] != effect["proof_hash"]
                or member["current_certificate_hash"]
                != effect["certificate_hash"]
                or member["current_conflict_hash"] != effect["conflict_hash"]
            ):
                return False
            operation = self._validated_operation(
                member["write_operation_id"]
            )
            return bool(
                member["write_operation_seq"] == operation["operation_seq"]
                and member["write_operation_hash"]
                == operation["operation_envelope_hash"]
                and operation["operation_kind"]
                in {"CLOSE_SUCCESS", "CLOSE_CONFLICT"}
                and operation["target_member_id"] == member["member_id"]
                and operation["target_effect_id"] == effect["effect_id"]
                and operation["target_member_tuple_hash"]
                == member["member_tuple_hash"]
                and operation["target_effect_outcome_hash"]
                == effect["outcome_tuple_hash"]
            )
        except (KeyError, TypeError, ValueError, sqlite3.Error, StoreError):
            return False

    def _outstanding_reservations(
        self,
        *,
        excluded_effect_id: str | None = None,
        exclude_adopted_pending: bool = False,
        target_member_id: str | None = None,
    ) -> int:
        rows = self._connection.execute(
            "SELECT e.*,"
            "EXISTS(SELECT 1 FROM registration_member m "
            "WHERE m.current_effect_id=e.effect_id "
            "OR m.pending_effect_id=e.effect_id) AS is_live_reference,"
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
            terminal = self._effect_has_terminal_witness(row)
            if terminal and self._effect_is_resolved_current(row):
                total += UNVALIDATED_SUCCESSOR_CHARGE
            elif row["is_live_reference"] or not terminal:
                total += UNVALIDATED_EFFECT_CHARGE
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
            if (
                int(target_row["outcome_reservation_bytes"])
                < MIN_OUTCOME_RESERVATION
                or int(target_row["successor_reservation_bytes"])
                < MIN_SUCCESSOR_RESERVATION
            ):
                raise StoreUnavailable("effect reservation floor corrupted")
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
                    - RECOVERY_RESERVATION
                )
                remaining_external = (
                    target_row["external_growth_reservation_bytes"]
                    - spent_external
                    - int(row["external_growth_bytes"])
                )
                if remaining_outcome < 0 or remaining_external < 0:
                    raise InsufficientSpace("effect reservation exhausted")
                required += UNVALIDATED_EFFECT_CHARGE
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
                    - RECOVERY_RESERVATION
                ):
                    raise InsufficientSpace("outcome reservation exhausted")
                required += UNVALIDATED_SUCCESSOR_CHARGE
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

    def _recovery_reserve_exhaustion(
        self,
        *,
        protocol: Mapping[str, Any],
        member: Mapping[str, Any],
        effect: Mapping[str, Any],
        status: Mapping[str, Any],
    ) -> RecoveryReserveExhausted | None:
        activation_rows = self._connection.execute(
            "SELECT operation_id,operation_seq "
            "FROM registration_operation_audit "
            "WHERE operation_kind IN"
            "('INSTALL_MEMBER','INVALIDATE_REQUESTED',"
            "'HANDOFF_RESOLVED') "
            "AND target_successor_effect_id=? "
            "ORDER BY operation_seq",
            (effect["effect_id"],),
        ).fetchall()
        if len(activation_rows) != 1:
            raise SemanticClosureError(
                "effect activation boundary is not unique"
            )
        activation = self._validated_operation(
            activation_rows[0]["operation_id"]
        )
        if (
            activation["operation_seq"]
            != activation_rows[0]["operation_seq"]
        ):
            raise SemanticClosureError(
                "effect activation boundary is corrupt"
            )
        rows = self._connection.execute(
            "SELECT * "
            "FROM registration_operation_audit "
            "WHERE operation_seq>? "
            "AND (target_effect_id=? OR target_member_id=?) "
            "AND (operation_kind IN"
            "('MARK_UNAVAILABLE','REACQUIRE_EFFECT') "
            "OR (projected_db_growth_bytes=? "
            "AND target_executor_token_hash IS NOT NULL "
            "AND target_status_hash IS NOT NULL)) "
            "ORDER BY operation_seq",
            (
                activation["operation_seq"],
                effect["effect_id"],
                member["member_id"],
                RECOVERY_OPERATION_BYTES,
            ),
        ).fetchall()
        validated = [self._validated_operation(row["operation_id"]) for row in rows]
        count = len(validated)
        consumed = sum(
            int(operation["projected_db_growth_bytes"])
            for operation in validated
        )
        if (
            count > MAX_RECOVERY_OPERATIONS
            or consumed != count * RECOVERY_OPERATION_BYTES
        ):
            raise SemanticClosureError("recovery reservation history is corrupt")
        for index, operation in enumerate(validated):
            previous = validated[index - 1] if index else None
            expected_kind = "MARK_UNAVAILABLE"
            if (
                previous is not None
                and previous["operation_kind"] == "MARK_UNAVAILABLE"
            ):
                intervening_adopt = self._connection.execute(
                    "SELECT operation_id "
                    "FROM registration_operation_audit "
                    "WHERE operation_seq>? AND operation_seq<? "
                    "AND operation_kind='ADOPT_EFFECT' "
                    "AND target_member_id=? AND lineage_effect_id=? "
                    "AND target_executor_token_hash IS NOT NULL "
                    "ORDER BY operation_seq DESC LIMIT 1",
                    (
                        previous["operation_seq"],
                        operation["operation_seq"],
                        member["member_id"],
                        effect["effect_id"],
                    ),
                ).fetchone()
                if intervening_adopt is None:
                    expected_kind = "REACQUIRE_EFFECT"
                else:
                    self._validated_operation(
                        intervening_adopt["operation_id"]
                    )
            protocol_row = self._connection.execute(
                "SELECT * FROM registration_protocol_epoch "
                "WHERE protocol_seq=?",
                (operation["protocol_seq"],),
            ).fetchone()
            if protocol_row is None:
                raise SemanticClosureError(
                    "recovery protocol companion is missing"
                )
            recovery_protocol = self._validate_protocol_row(protocol_row)
            draining = recovery_protocol["mode"] == "DRAINING"
            expected_runtime = recovery_protocol[
                (
                    "staged_runtime_capability_hash"
                    if draining
                    else "runtime_capability_hash"
                )
            ]
            expected_writer = recovery_protocol[
                (
                    "staged_writer_binary_hash"
                    if draining
                    else "writer_binary_hash"
                )
            ]
            expected_profile = recovery_protocol[
                "staged_profile_hash" if draining else "profile_hash"
            ]
            expected_capability = recovery_protocol[
                (
                    "staged_writer_capability_hash"
                    if draining
                    else "writer_capability_hash"
                )
            ]
            expected_staged_epoch = (
                recovery_protocol["staged_epoch_hash"]
                if draining
                else None
            )
            prior_status_row = self._connection.execute(
                "SELECT operation_id,target_status_hash "
                "FROM registration_operation_audit "
                "WHERE operation_seq<? AND target_member_id=? "
                "AND target_status_hash IS NOT NULL "
                "ORDER BY operation_seq DESC LIMIT 1",
                (operation["operation_seq"], member["member_id"]),
            ).fetchone()
            if prior_status_row is None:
                raise SemanticClosureError(
                    "recovery status predecessor is missing"
                )
            prior_status = self._validated_operation(
                prior_status_row["operation_id"]
            )
            if (
                operation["operation_kind"] != expected_kind
                or operation["target_member_id"] != member["member_id"]
                or operation["target_effect_id"] != effect["effect_id"]
                or operation["target_subject_key"]
                != member["runtime_subject_key"]
                or operation["projected_db_growth_bytes"]
                != RECOVERY_OPERATION_BYTES
                or operation["target_executor_token_hash"] is None
                or operation["target_status_hash"] is None
                or operation["target_status_hash"]
                == operation["expected_target_status_hash"]
                or operation["expected_target_status_hash"]
                != prior_status["target_status_hash"]
                or operation["expected_mode"]
                != recovery_protocol["mode"]
                or operation["expected_generation"]
                != recovery_protocol["protocol_generation"]
                or operation["expected_protocol_hash"]
                != recovery_protocol["protocol_hash"]
                or operation["runtime_capability_hash"]
                != expected_runtime
                or operation["writer_binary_hash"] != expected_writer
                or operation["profile_hash"] != expected_profile
                or operation["writer_capability_receipt_hash"]
                != expected_capability
                or operation["target_staged_epoch_hash"]
                != expected_staged_epoch
                or operation["sample_boot_id"] is None
                or operation["sample_mono_ns"] is None
                or (
                    draining
                    and (
                        operation["sample_boot_id"]
                        != recovery_protocol["drain_boot_id"]
                        or operation["sample_mono_ns"]
                        > recovery_protocol["drain_deadline_mono_ns"]
                    )
                )
            ):
                raise SemanticClosureError(
                    "recovery operation companion is corrupt"
                )
            if expected_kind == "MARK_UNAVAILABLE":
                grant_row = self._connection.execute(
                    "SELECT operation_id "
                    "FROM registration_operation_audit "
                    "WHERE operation_seq<? AND target_member_id=? "
                    "AND target_executor_token_hash IS NOT NULL "
                    "AND ((operation_kind IN"
                    "('OPEN_EFFECT','REACQUIRE_EFFECT') "
                    "AND target_effect_id=?) "
                    "OR (operation_kind='ADOPT_EFFECT' "
                    "AND lineage_effect_id=?)) "
                    "ORDER BY operation_seq DESC LIMIT 1",
                    (
                        operation["operation_seq"],
                        member["member_id"],
                        effect["effect_id"],
                        effect["effect_id"],
                    ),
                ).fetchone()
                if grant_row is None:
                    raise SemanticClosureError(
                        "recovery executor grant is missing"
                    )
                grant = self._validated_operation(
                    grant_row["operation_id"]
                )
                if (
                    operation["target_executor_token_hash"]
                    != grant["target_executor_token_hash"]
                    or operation["target_protocol_hash"] is not None
                    or operation["expected_target_member_tuple_hash"]
                    is not None
                    or operation["expected_target_effect_tuple_hash"]
                    is not None
                    or operation["target_member_tuple_hash"] is not None
                    or operation["target_effect_tuple_hash"] is not None
                    or operation["target_action_plan_hash"] is not None
                    or operation["target_action_ledger_hash"] is not None
                ):
                    raise SemanticClosureError(
                        "recovery mark companion is corrupt"
                    )
            else:
                prior_member_row = self._connection.execute(
                    "SELECT operation_id,target_member_tuple_hash "
                    "FROM registration_operation_audit "
                    "WHERE operation_seq<? AND target_member_id=? "
                    "AND target_member_tuple_hash IS NOT NULL "
                    "ORDER BY operation_seq DESC LIMIT 1",
                    (operation["operation_seq"], member["member_id"]),
                ).fetchone()
                if prior_member_row is None:
                    raise SemanticClosureError(
                        "recovery member predecessor is missing"
                    )
                prior_member = self._validated_operation(
                    prior_member_row["operation_id"]
                )
                ledger_row = self._connection.execute(
                    "SELECT ledger_hash "
                    "FROM registration_effect_action "
                    "WHERE effect_id=? AND write_operation_seq<? "
                    "ORDER BY event_seq DESC LIMIT 1",
                    (effect["effect_id"], operation["operation_seq"]),
                ).fetchone()
                expected_ledger = ledger_row[0] if ledger_row else ZERO_HASH
                if (
                    operation["expected_target_member_tuple_hash"]
                    != prior_member["target_member_tuple_hash"]
                    or operation["target_member_tuple_hash"]
                    != prior_member["target_member_tuple_hash"]
                    or operation["expected_target_effect_tuple_hash"]
                    != effect["request_tuple_hash"]
                    or operation["target_effect_tuple_hash"]
                    != effect["request_tuple_hash"]
                    or operation["target_action_plan_hash"]
                    != effect["action_plan_hash"]
                    or operation["target_action_ledger_hash"]
                    != expected_ledger
                    or operation["target_protocol_hash"]
                    != recovery_protocol["protocol_hash"]
                ):
                    raise SemanticClosureError(
                        "recovery reacquire companion is corrupt"
                    )
        if count < MAX_RECOVERY_OPERATIONS:
            return None
        return RecoveryReserveExhausted(
            protocol_hash=protocol["protocol_hash"],
            staged_epoch_hash=protocol["staged_epoch_hash"],
            member_id=member["member_id"],
            effect_id=effect["effect_id"],
            member_tuple_hash=member["member_tuple_hash"],
            status_hash=status["status_hash"],
            executor_token_hash=status["executor_token_hash"],
            _seal=_RECOVERY_EXHAUSTION_SEAL,
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
        _require_int(measured_free_bytes, "measured_free_bytes", minimum=0)
        _require_int(
            projected_db_growth_bytes,
            "projected_db_growth_bytes",
            minimum=0,
        )
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
                "created_wall_ns": self._fresh_wall_ns(),
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

    def _validate_successor_transition(
        self,
        *,
        predecessor: Mapping[str, Any],
        successor: Mapping[str, Any],
        operation: Mapping[str, Any],
    ) -> None:
        kind = operation["operation_kind"]
        cause = operation["target_cause_code"]
        fixed_causes = {
            "INVALIDATE_REQUESTED": "BASIS_CHANGED",
            "REPLACE_PENDING": "PENDING_REPLACED",
            "ADOPT_EFFECT": "STAGED_CAPABILITY_INCOMPATIBLE",
        }
        if kind in fixed_causes:
            valid_cause = cause == fixed_causes[kind]
        elif kind == "HANDOFF_RESOLVED":
            created_during_handoff = (
                successor["created_operation_id"]
                == operation["operation_id"]
            )
            if not created_during_handoff:
                valid_cause = cause == "BASIS_CHANGED"
            elif cause == "EXPLICIT_CONFLICT_RETRY":
                valid_cause = (
                    predecessor["outcome_kind"] == "LOGICAL_CONFLICT"
                )
            else:
                valid_cause = (
                    cause
                    in {"BASIS_CHANGED", "CURRENT_CLOSURE_CHANGED"}
                    and successor["request_basis_hash"]
                    != predecessor["request_basis_hash"]
                )
        else:
            self._semantic_failure("unknown successor transition kind")
        if not valid_cause:
            self._semantic_failure("successor transition cause mismatch")
        expected_old_effect_hash = (
            predecessor["outcome_tuple_hash"]
            if kind == "HANDOFF_RESOLVED"
            else predecessor["request_tuple_hash"]
        )
        expected_transition = self._successor_transition_id(
            operation_kind=kind,
            cause=cause,
            old_member_hash=operation[
                "expected_target_member_tuple_hash"
            ],
            old_status_hash=operation["expected_target_status_hash"],
            old_effect_hash=expected_old_effect_hash,
            new_member_hash=operation["target_member_tuple_hash"],
            new_status_hash=operation["target_status_hash"],
            new_effect_hash=successor["request_tuple_hash"],
            old_epoch=predecessor["member_epoch"],
            old_basis=predecessor["request_basis_hash"],
            new_epoch=successor["member_epoch"],
            new_basis=successor["request_basis_hash"],
            old_effect_id=predecessor["effect_id"],
            new_effect_id=successor["effect_id"],
        )
        if (
            operation["target_effect_id"] != predecessor["effect_id"]
            or operation["target_successor_effect_id"]
            != successor["effect_id"]
            or operation["expected_target_effect_tuple_hash"]
            != expected_old_effect_hash
            or operation["target_effect_tuple_hash"]
            != successor["request_tuple_hash"]
            or operation["target_successor_member_epoch"]
            != successor["member_epoch"]
            or operation["target_successor_basis_hash"]
            != successor["request_basis_hash"]
            or operation["target_transition_id"] != expected_transition
            or (
                predecessor["outcome_kind"] == "SUPERSEDED"
                and (
                    predecessor["successor_transition_id"]
                    != expected_transition
                    or operation["target_effect_outcome_hash"]
                    != predecessor["outcome_tuple_hash"]
                )
            )
        ):
            self._semantic_failure(
                "successor transition companion mismatch"
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
        _require_int(
            projected_db_growth_bytes,
            "projected_db_growth_bytes",
            minimum=0,
        )
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
                        "created_wall_ns": self._fresh_wall_ns(),
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
    ) -> ValidatedProtocol:
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

    def _require_recovery_candidate(
        self, data: DataCapability, candidate: ProtocolCandidate
    ) -> tuple[ValidatedProtocol, bool]:
        self._require_data(data, candidate)
        current = self.current_protocol()
        if current is None:
            raise StaleAuthority("registration authority is not bootstrapped")
        if current["mode"] == "WRITABLE":
            return self._require_current_candidate(
                candidate, mode="WRITABLE"
            ), False
        return self._require_staged_candidate(candidate, current=current), True

    def _require_recovery_profile_binding(
        self,
        candidate: ProtocolCandidate,
        staged_recovery: bool,
        binding: registration_profile.TypedProfileBinding | None,
    ) -> registration_profile.TypedProfileBinding | None:
        return self._require_typed_profile_binding(
            candidate,
            binding,
            staged=staged_recovery,
        )

    def _cached_profile_binding_for_candidate(
        self, candidate: ProtocolCandidate
    ) -> registration_profile.TypedProfileBinding | None:
        current = self.current_protocol()
        if (
            current is not None
            and current["mode"] == "DRAINING"
            and current["staged_profile_hash"] == candidate.profile_hash
            and current["storage_dev"] == candidate.storage_dev
        ):
            return self._staged_typed_profile_binding
        return self._current_typed_profile_binding

    def _require_staged_candidate(
        self,
        candidate: ProtocolCandidate,
        *,
        current: ValidatedProtocol | None = None,
    ) -> ValidatedProtocol:
        if current is None:
            current = self.current_protocol()
            if current is None:
                raise StaleAuthority(
                    "registration authority is not bootstrapped"
                )
        if current["mode"] != "DRAINING" or current["staged_generation"] is None:
            raise StaleAuthority("recovery requires WRITABLE or staged DRAINING")
        staged_pairs = {
            "staged_schema_hash": SCHEMA_SHA256,
            "staged_profile_hash": candidate.profile_hash,
            "staged_runtime_capability_hash": candidate.runtime_capability_hash,
            "staged_writer_binary_hash": candidate.writer_binary_hash,
            "staged_writer_capability_hash": candidate.writer_capability_hash,
            "staged_tool_inventory_hash": candidate.tool_inventory_hash,
            "staged_hook_projection_hash": candidate.hook_projection_hash,
            "staged_hook_matcher_mode": candidate.hook_matcher_mode,
            "staged_hook_matcher_hash": candidate.hook_matcher_hash,
            "staged_projection_receipt_hash": candidate.projection_receipt_hash,
            "staged_projection_file_generation": candidate.projection_file_generation,
            "staged_installer_identity_hash": candidate.installer_identity_hash,
            "staged_installer_capability_hash": candidate.installer_capability_hash,
            "storage_dev": candidate.storage_dev,
        }
        if any(current[key] != value for key, value in staged_pairs.items()):
            raise StaleAuthority("candidate does not match staged protocol")
        return current

    def activate(
        self,
        control: ControlCapability,
        candidate: ProtocolCandidate,
        *,
        profile_binding: (
            registration_profile.CurrentProfileBinding | None
        ) = None,
        operation_id: str | None = None,
        projected_db_growth_bytes: int = 0,
        _protocol_locked: bool = False,
    ) -> OperationResult:
        _require_int(
            projected_db_growth_bytes,
            "projected_db_growth_bytes",
            minimum=0,
        )
        self._require_control(control, candidate)
        if not _protocol_locked:
            with self._locks.acquire_protocol() as held:
                held.verify()
                return self.activate(
                    control,
                    candidate,
                    profile_binding=profile_binding,
                    operation_id=operation_id,
                    projected_db_growth_bytes=projected_db_growth_bytes,
                    _protocol_locked=True,
                )
        typed_binding = self._require_typed_profile_binding(
            candidate, profile_binding, staged=False
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
                        "created_wall_ns": self._fresh_wall_ns(),
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
                if typed_binding is not None:
                    self._current_typed_profile_binding = typed_binding
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
        profile_binding: (
            registration_profile.CurrentProfileBinding | None
        ) = None,
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
            current_profile_binding=profile_binding,
            staged_profile_binding=None,
        )

    def stage_next(
        self,
        control: ControlCapability,
        candidate: ProtocolCandidate,
        staged_candidate: ProtocolCandidate,
        *,
        quiescence_proof_hash: str,
        current_profile_binding: (
            registration_profile.CurrentProfileBinding | None
        ) = None,
        staged_profile_binding: (
            registration_profile.StagedProfileBinding | None
        ) = None,
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
            current_profile_binding=current_profile_binding,
            staged_profile_binding=staged_profile_binding,
        )

    def cancel_drain(
        self,
        control: ControlCapability,
        candidate: ProtocolCandidate,
        *,
        quiescence_proof_hash: str,
        profile_binding: (
            registration_profile.CurrentProfileBinding | None
        ) = None,
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
            current_profile_binding=profile_binding,
            staged_profile_binding=None,
        )

    def _custody_grant_closed_tx(
        self,
        grant: ValidatedOperation,
        *,
        effect_id: str,
    ) -> bool:
        if grant["operation_id"] in self._activated_staged_grants:
            return True
        later = self._connection.execute(
            "SELECT operation_id,operation_kind,target_executor_token_hash,"
            "expected_target_status_hash FROM registration_operation_audit "
            "WHERE operation_seq>? AND target_member_id=? "
            "AND target_effect_id=? ORDER BY operation_seq",
            (
                grant["operation_seq"],
                grant["target_member_id"],
                effect_id,
            ),
        ).fetchall()
        for row in later:
            exact_token_use = (
                row["operation_kind"]
                in {
                    "APPEND_ACTION",
                    "CLOSE_SUCCESS",
                    "CLOSE_CONFLICT",
                    "MARK_UNAVAILABLE",
                }
                and row["target_executor_token_hash"]
                == grant["target_executor_token_hash"]
            )
            old_boot_clear = (
                row["operation_kind"] == "REBOOT_STATUS"
                and row["expected_target_status_hash"]
                == grant["target_status_hash"]
            )
            if (
                exact_token_use or old_boot_clear
            ) and self._resolve_operation_tx(row["operation_id"]) == "COMMITTED":
                return True
        return False

    def _unresolved_custody_obligations_tx(
        self, protocol: Mapping[str, Any]
    ) -> tuple[StagedCustodyObligation, ...]:
        if (
            protocol["mode"] != "DRAINING"
            or protocol["staged_generation"] is None
            or protocol["staged_epoch_hash"] is None
        ):
            return ()
        result: list[StagedCustodyObligation] = []
        after_member = ""
        while True:
            member_rows = self._connection.execute(
                "SELECT DISTINCT target_member_id "
                "FROM registration_operation_audit "
                "WHERE operation_kind IN('ADOPT_EFFECT','REACQUIRE_EFFECT') "
                "AND target_staged_epoch_hash=? AND target_member_id>? "
                "ORDER BY target_member_id COLLATE BINARY LIMIT 8",
                (protocol["staged_epoch_hash"], after_member),
            ).fetchall()
            if not member_rows:
                break
            for member_row in member_rows:
                member_id = member_row["target_member_id"]
                authority = self._validate_semantic_closure_tx(
                    member_id, episode_id=None
                )
                if authority is None:
                    self._semantic_failure(
                        "staged custody member closure is absent"
                    )
                grant_rows = self._connection.execute(
                    "SELECT operation_id FROM registration_operation_audit "
                    "WHERE operation_kind "
                    "IN('ADOPT_EFFECT','REACQUIRE_EFFECT') "
                    "AND target_staged_epoch_hash=? "
                    "AND target_member_id=? ORDER BY operation_seq",
                    (protocol["staged_epoch_hash"], member_id),
                ).fetchall()
                for grant_row in grant_rows:
                    grant = self._validated_operation(
                        grant_row["operation_id"]
                    )
                    grant_protocol_row = self._connection.execute(
                        "SELECT * FROM registration_protocol_epoch "
                        "WHERE protocol_seq=?",
                        (grant["protocol_seq"],),
                    ).fetchone()
                    if grant_protocol_row is None:
                        self._semantic_failure(
                            "staged custody protocol is absent"
                        )
                    grant_protocol = self._validate_protocol_row(
                        grant_protocol_row
                    )
                    effect_id = (
                        grant["lineage_effect_id"]
                        if grant["operation_kind"] == "ADOPT_EFFECT"
                        else grant["target_effect_id"]
                    )
                    if (
                        self._resolve_operation_tx(grant["operation_id"])
                        != "COMMITTED"
                        or effect_id is None
                        or grant["target_status_hash"] is None
                        or grant["target_executor_token_hash"] is None
                        or grant["target_member_tuple_hash"] is None
                        or grant_protocol["mode"] != "DRAINING"
                        or grant_protocol["staged_generation"]
                        != protocol["staged_generation"]
                        or grant_protocol["staged_epoch_hash"]
                        != protocol["staged_epoch_hash"]
                    ):
                        self._semantic_failure(
                            "staged custody grant companion mismatch"
                        )
                    if self._custody_grant_closed_tx(
                        grant, effect_id=effect_id
                    ):
                        continue
                    result.append(
                        StagedCustodyObligation(
                            operation_id=grant["operation_id"],
                            operation_kind=grant["operation_kind"],
                            member_id=member_id,
                            effect_id=effect_id,
                            status_hash=grant["target_status_hash"],
                            executor_token_hash=grant[
                                "target_executor_token_hash"
                            ],
                            executor_generation=int(
                                protocol["staged_generation"]
                            ),
                            staged_epoch_hash=protocol[
                                "staged_epoch_hash"
                            ],
                            member_tuple_hash=grant[
                                "target_member_tuple_hash"
                            ],
                        )
                    )
            after_member = member_rows[-1]["target_member_id"]
        return tuple(result)

    def unresolved_custody_obligations(
        self,
    ) -> tuple[StagedCustodyObligation, ...]:
        with self._read_scope():
            self._connection.execute("BEGIN")
            try:
                protocol_row = self._connection.execute(
                    "SELECT * FROM registration_protocol_epoch "
                    "ORDER BY protocol_seq DESC LIMIT 1"
                ).fetchone()
                if protocol_row is None:
                    result: tuple[StagedCustodyObligation, ...] = ()
                else:
                    protocol = self._validate_protocol_row(protocol_row)
                    result = self._unresolved_custody_obligations_tx(
                        protocol
                    )
                self._connection.execute("COMMIT")
                return result
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def advance_generation(
        self,
        control: ControlCapability,
        candidate: ProtocolCandidate,
        *,
        quiescence_proof_hash: str,
        staged_candidate: ProtocolCandidate | None = None,
        current_profile_binding: (
            registration_profile.CurrentProfileBinding | None
        ) = None,
        staged_profile_binding: (
            registration_profile.StagedProfileBinding | None
        ) = None,
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
            current_profile_binding=current_profile_binding,
            staged_profile_binding=staged_profile_binding,
            profile_staged_candidate=staged_candidate,
        )

    def pre_effect_dormant(
        self,
        control: ControlCapability,
        candidate: ProtocolCandidate,
        *,
        absence_proof_hash: str,
        profile_binding: (
            registration_profile.CurrentProfileBinding | None
        ) = None,
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
            current_profile_binding=profile_binding,
            staged_profile_binding=None,
        )

    def enter_containment(
        self,
        control: ControlCapability,
        candidate: ProtocolCandidate,
        *,
        reason: str,
        profile_binding: (
            registration_profile.CurrentProfileBinding | None
        ) = None,
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
            current_profile_binding=profile_binding,
            staged_profile_binding=None,
        )

    def begin_repair(
        self,
        control: ControlCapability,
        candidate: ProtocolCandidate,
        *,
        current_profile_binding: (
            registration_profile.CurrentProfileBinding | None
        ) = None,
        staged_candidate: ProtocolCandidate | None = None,
        staged_profile_binding: (
            registration_profile.StagedProfileBinding | None
        ) = None,
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
            current_profile_binding=current_profile_binding,
            staged_profile_binding=staged_profile_binding,
            profile_staged_candidate=staged_candidate,
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
        current_profile_binding: (
            registration_profile.CurrentProfileBinding | None
        ),
        staged_profile_binding: (
            registration_profile.StagedProfileBinding | None
        ),
        profile_staged_candidate: ProtocolCandidate | None = None,
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
                    current_profile_binding=current_profile_binding,
                    staged_profile_binding=staged_profile_binding,
                    profile_staged_candidate=profile_staged_candidate,
                    _protocol_locked=True,
                )
        typed_current = self._require_typed_profile_binding(
            candidate, current_profile_binding, staged=False
        )
        typed_staged = None
        if transition_kind in {
            "STAGE_NEXT",
            "ADVANCE_GENERATION",
        }:
            profile_candidate = (
                staged_candidate
                if transition_kind == "STAGE_NEXT"
                else profile_staged_candidate
            )
            if profile_candidate is None and not self._allow_test_profile:
                raise registration_profile.ProfileError(
                    "staged candidate profile is required"
                )
            if profile_candidate is not None:
                typed_staged = self._require_typed_profile_binding(
                    profile_candidate,
                    staged_profile_binding,
                    staged=True,
                )
        current = self._require_current_candidate(candidate)
        if (
            transition_kind == "BEGIN_REPAIR"
            and current["staged_generation"] is not None
        ):
            if profile_staged_candidate is None and not self._allow_test_profile:
                raise registration_profile.ProfileError(
                    "staged candidate profile is required"
                )
            if profile_staged_candidate is not None:
                typed_staged = self._require_typed_profile_binding(
                    profile_staged_candidate,
                    staged_profile_binding,
                    staged=True,
                )
        if (
            transition_kind in {"ADVANCE_GENERATION", "BEGIN_REPAIR"}
            and profile_staged_candidate is not None
        ):
            self._require_staged_candidate(
                profile_staged_candidate, current=current
            )
        promoted_typed_current = (
            registration_profile.CurrentProfileBinding.promote(
                typed_staged
            )
            if transition_kind == "ADVANCE_GENERATION"
            and typed_staged is not None
            else None
        )
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
                        "created_wall_ns": self._fresh_wall_ns(),
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
                    if staged_candidate.storage_dev != current["storage_dev"]:
                        raise StaleAuthority(
                            "staged candidate storage device mismatch"
                        )
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
                    if self._unresolved_custody_obligations_tx(current):
                        raise StaleAuthority(
                            "ADVANCE_GENERATION has unresolved staged custody"
                        )
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
                if transition_kind == "ADVANCE_GENERATION":
                    if promoted_typed_current is not None:
                        self._profile_binding = (
                            promoted_typed_current.profile
                        )
                    self._current_typed_profile_binding = (
                        promoted_typed_current
                    )
                    self._staged_typed_profile_binding = None
                else:
                    if typed_current is not None:
                        self._current_typed_profile_binding = typed_current
                    if transition_kind == "STAGE_NEXT":
                        self._staged_typed_profile_binding = typed_staged
                    elif transition_kind in {
                        "CANCEL_DRAIN",
                        "PRE_EFFECT_DORMANT",
                    }:
                        self._staged_typed_profile_binding = None
                    elif typed_staged is not None:
                        self._staged_typed_profile_binding = typed_staged
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
        _require_int(
            projected_db_growth_bytes,
            "projected_db_growth_bytes",
            minimum=0,
        )
        if sample_mono_ns is not None:
            _require_int(sample_mono_ns, "sample_mono_ns", minimum=0)
        self._require_data(data, candidate)
        current = self._require_current_candidate(candidate, mode="WRITABLE")
        if identity.root_dev != int(current["storage_dev"]):
            raise StaleAuthority("member storage device mismatch")
        if identity.current_basis_hash != intent.request_basis_hash:
            raise StaleAuthority("member/effect basis mismatch")
        if (sample_boot_id is None) != (sample_mono_ns is None):
            raise ValueError("expected sample must be supplied as one pair")
        operation_id = operation_id or self._operation_ids()
        member_id = self._member_id(identity)
        if _member_lock is None:
            with self._locks.acquire_member(member_id) as held:
                self._validate_member_lock(member_id, held)
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
        self._validate_member_lock(member_id, _member_lock)
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
                live_current = self._require_current_candidate(
                    candidate, mode="WRITABLE"
                )
                if (
                    live_current["protocol_hash"]
                    != current["protocol_hash"]
                ):
                    raise StaleAuthority(
                        "member install protocol changed under lock"
                    )
                existing_member = self._connection.execute(
                    "SELECT * FROM registration_member WHERE member_id=?",
                    (member_id,),
                ).fetchone()
                if existing_member is not None:
                    authority = self._validate_semantic_closure_tx(
                        member_id, episode_id=None
                    )
                    existing_effect = self._connection.execute(
                        "SELECT * FROM registration_effect WHERE effect_id=?",
                        (effect_id,),
                    ).fetchone()
                    if authority is None or existing_effect is None:
                        raise StaleAuthority(
                            "duplicate member closure is incomplete"
                        )
                    install_operation = self._validated_operation(
                        existing_effect["created_operation_id"]
                    )
                    if (
                        install_operation["operation_kind"]
                        != "INSTALL_MEMBER"
                        or install_operation["target_member_id"] != member_id
                        or install_operation["target_successor_effect_id"]
                        != effect_id
                        or install_operation["target_member_tuple_hash"]
                        != member["member_tuple_hash"]
                        or install_operation["target_effect_tuple_hash"]
                        != effect["request_tuple_hash"]
                        or existing_effect["request_tuple_hash"]
                        != effect["request_tuple_hash"]
                    ):
                        raise StaleAuthority(
                            "duplicate member tuple conflicts"
                        )
                    self._connection.execute("ROLLBACK")
                    return OperationResult(
                        "COMMITTED",
                        install_operation["operation_id"],
                        install_operation["operation_envelope_hash"],
                        install_operation["target_member_tuple_hash"],
                    )
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
        _member_lock: registration_lock.HeldLock | None = None,
    ) -> OperationResult:
        _require_int(
            projected_db_growth_bytes,
            "projected_db_growth_bytes",
            minimum=0,
        )
        self._require_data(data, candidate)
        current = self._require_current_candidate(candidate, mode="WRITABLE")
        _require_hash(member_id, "member_id")
        operation_id = operation_id or self._operation_ids()
        with self._member_lock_scope(member_id, _member_lock) as held:
            held.verify()
            with self._write_scope(
                {
                    (sqlite3.SQLITE_INSERT, "registration_operation_audit"),
                    (sqlite3.SQLITE_INSERT, "registration_episode"),
                }
            ):
                try:
                    measured = self._begin()
                    current = self._require_current_candidate(
                        candidate, mode="WRITABLE"
                    )
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
                    existing_episode = self._connection.execute(
                        "SELECT * FROM registration_episode "
                        "WHERE episode_id=?",
                        (episode_id,),
                    ).fetchone()
                    if existing_episode is not None:
                        authority = self._validate_semantic_closure_tx(
                            member_id, episode_id=episode_id
                        )
                        if (
                            authority is None
                            or len(authority.episodes) != 1
                        ):
                            raise StaleAuthority(
                                "duplicate episode closure is incomplete"
                            )
                        episode_value = authority.episodes[0]
                        operation = self._validated_operation(
                            episode_value["write_operation_id"]
                        )
                        expected_fields = {
                            "conversation_id": source.conversation_id,
                            "generation_id": source.generation_id,
                            "source_contract": source.source_contract,
                            "source_event": source.source_event,
                            "protocol_generation": current[
                                "protocol_generation"
                            ],
                            "member_id": member_id,
                            "workspace_root_count": 1,
                            "workspace_roots_hash": (
                                source.workspace_roots_hash
                            ),
                            "tool_inventory_hash": current[
                                "tool_inventory_hash"
                            ],
                            "hook_projection_hash": current[
                                "hook_projection_hash"
                            ],
                        }
                        if (
                            any(
                                episode_value[key] != value
                                for key, value in expected_fields.items()
                            )
                            or operation["operation_kind"]
                            != "BIND_EPISODE"
                            or operation["target_episode_id"] != episode_id
                            or operation["target_episode_hash"]
                            != episode_value["envelope_hash"]
                        ):
                            raise StaleAuthority(
                                "duplicate episode tuple conflicts"
                            )
                        self._connection.execute("ROLLBACK")
                        return OperationResult(
                            "COMMITTED",
                            operation["operation_id"],
                            operation["operation_envelope_hash"],
                            episode_value["envelope_hash"],
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
                        "created_wall_ns": self._fresh_wall_ns(),
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
        _member_lock: registration_lock.HeldLock | None = None,
    ) -> OperationResult:
        _require_int(
            projected_db_growth_bytes,
            "projected_db_growth_bytes",
            minimum=0,
        )
        self._require_data(data, candidate)
        self._require_current_candidate(candidate, mode="WRITABLE")
        if basis.current_basis_hash != intent.request_basis_hash:
            raise ValueError("successor basis/effect mismatch")
        operation_id = operation_id or self._operation_ids()
        with self._member_lock_scope(member_id, _member_lock) as held:
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
                    authority = self._validate_semantic_closure_tx(
                        member_id, episode_id=None
                    )
                    if authority is None:
                        raise StaleAuthority(
                            "INVALIDATE_REQUESTED authority is absent"
                        )
                    member = dict(authority.member)
                    old_effect = dict(authority.effect)
                    old_status = dict(authority.status)
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
        _member_lock: registration_lock.HeldLock | None = None,
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
            _member_lock=_member_lock,
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
        _member_lock: registration_lock.HeldLock | None = None,
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
            _member_lock=_member_lock,
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
        _member_lock: registration_lock.HeldLock | None,
    ) -> OperationResult:
        self._require_data(data, candidate)
        self._require_current_candidate(candidate, mode="WRITABLE")
        _require_hash(basis_hash, "basis_hash")
        if basis_hash != intent.request_basis_hash:
            raise ValueError("pending basis/effect mismatch")
        operation_kind = "REPLACE_PENDING" if replace else "SET_PENDING"
        operation_id = operation_id or self._operation_ids()
        with self._member_lock_scope(member_id, _member_lock) as held:
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
                    authority = self._validate_semantic_closure_tx(
                        member_id, episode_id=None
                    )
                    if authority is None:
                        raise StaleAuthority(
                            f"{operation_kind} authority is absent"
                        )
                    member = dict(authority.member)
                    status = dict(authority.status)
                    active = dict(authority.effect)
                    old_pending = None
                    expected_source = active
                    if replace and member["pending_effect_id"] is not None:
                        if authority.pending_effect is None:
                            self._semantic_failure(
                                "pending effect closure is absent"
                            )
                        old_pending = dict(authority.pending_effect)
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
        _member_lock: registration_lock.HeldLock | None = None,
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
        with self._member_lock_scope(member_id, _member_lock) as held:
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
                    authority = self._validate_semantic_closure_tx(
                        member_id, episode_id=None
                    )
                    if authority is None:
                        raise StaleAuthority(
                            "HANDOFF_RESOLVED authority is absent"
                        )
                    member = dict(authority.member)
                    old_effect = dict(authority.effect)
                    old_status = dict(authority.status)
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
                        if authority.pending_effect is None:
                            self._semantic_failure(
                                "pending handoff closure is absent"
                            )
                        successor = dict(authority.pending_effect)
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
        _require_int(attempt_count, "attempt_count", minimum=0)
        _require_int(backoff_ns, "backoff_ns", minimum=0)
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
        current_profile_binding: (
            registration_profile.CurrentProfileBinding | None
        ) = None,
        staged_candidate: ProtocolCandidate | None = None,
        staged_profile_binding: (
            registration_profile.StagedProfileBinding | None
        ) = None,
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
        grant_durable = False
        execution: MemberExecution | None = None
        token_hash: str | None = None
        try:
            protocol_lock.verify()
            current = self._require_current_candidate(
                candidate, mode="DRAINING"
            )
            typed_current = self._require_typed_profile_binding(
                candidate, current_profile_binding, staged=False
            )
            if staged_candidate is None and not self._allow_test_profile:
                raise registration_profile.ProfileError(
                    "staged candidate profile is required"
                )
            typed_staged = (
                self._require_typed_profile_binding(
                    staged_candidate,
                    staged_profile_binding,
                    staged=True,
                )
                if staged_candidate is not None
                else None
            )
            if staged_candidate is not None:
                self._require_staged_candidate(
                    staged_candidate, current=current
                )
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
                    authority = self._validate_semantic_closure_tx(
                        member_id, episode_id=None
                    )
                    if (
                        authority is None
                        or authority.protocol["protocol_hash"]
                        != current["protocol_hash"]
                    ):
                        raise StaleAuthority("ADOPT_EFFECT closure changed")
                    member = dict(authority.member)
                    active = dict(authority.effect)
                    old_status = dict(authority.status)
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
                        if authority.pending_effect is None:
                            raise SemanticClosureError(
                                "pending effect closure is missing"
                            )
                        pending = dict(authority.pending_effect)
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
                    try:
                        self._commit()
                    except BaseException:
                        grant_durable = self._grant_is_durable(
                            operation_id=operation_id,
                            operation_kind="ADOPT_EFFECT",
                            member_id=member_id,
                            executor_token_hash=token_hash,
                        )
                        raise
                    grant_durable = True
                    if typed_current is not None:
                        self._current_typed_profile_binding = typed_current
                    if typed_staged is not None:
                        self._staged_typed_profile_binding = typed_staged
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
                except Exception:
                    if self._connection.in_transaction:
                        self._connection.execute("ROLLBACK")
                    raise
            self.verify_execution(execution)
            self._fault("before_grant_return")
            committed = True
            return ExecutionResult(
                operation=OperationResult(
                    "COMMITTED",
                    operation_id,
                    operation["operation_envelope_hash"],
                    member_target["member_tuple_hash"],
                ),
                execution=execution,
            )
        except BaseException as primary:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            if not grant_durable and token_hash is not None:
                try:
                    grant_durable = self._grant_is_durable(
                        operation_id=operation_id,
                        operation_kind="ADOPT_EFFECT",
                        member_id=member_id,
                        executor_token_hash=token_hash,
                    )
                except sqlite3.Error as check_error:
                    primary.add_note(
                        "grant durability classification failed secondarily: "
                        f"{type(check_error).__name__}"
                    )
            if grant_durable and member_lock is not None:
                if execution is None:
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
                cleanup_data, cleanup_candidate = (
                    self._staged_cleanup_credentials(current)
                )
                self._cleanup_failed_grant(
                    data=cleanup_data,
                    candidate=cleanup_candidate,
                    execution=execution,
                    primary=primary,
                )
            raise
        finally:
            if protocol_lock.held:
                protocol_lock.release()
            if not committed and member_lock is not None and member_lock.held:
                member_lock.release()

    def _grant_is_durable(
        self,
        *,
        operation_id: str,
        operation_kind: str,
        member_id: str,
        executor_token_hash: str,
    ) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM registration_operation_audit o "
            "JOIN registration_runtime_status s "
            "ON s.member_id=o.target_member_id "
            "WHERE o.operation_id=? AND o.operation_kind=? "
            "AND o.target_member_id=? "
            "AND o.target_executor_token_hash=? "
            "AND s.executor_token_hash=?",
            (
                operation_id,
                operation_kind,
                member_id,
                executor_token_hash,
                executor_token_hash,
            ),
        ).fetchone()
        return row is not None

    def _cleanup_failed_grant(
        self,
        *,
        data: DataCapability,
        candidate: ProtocolCandidate,
        execution: MemberExecution,
        primary: BaseException,
    ) -> None:
        try:
            result = self.mark_unavailable(
                data,
                candidate,
                execution,
                profile_binding=self._cached_profile_binding_for_candidate(
                    candidate
                ),
            )
            if isinstance(result, RecoveryReserveExhausted):
                primary.add_note(
                    "grant cleanup could not persist: recovery reserve exhausted"
                )
        except BaseException as cleanup:
            primary.add_note(
                f"grant cleanup failed secondarily: {type(cleanup).__name__}"
            )
        finally:
            execution.close()

    @staticmethod
    def _staged_cleanup_credentials(
        current: Mapping[str, Any],
    ) -> tuple[DataCapability, ProtocolCandidate]:
        if current["mode"] != "DRAINING" or current["staged_generation"] is None:
            raise AuthorizationError("staged cleanup authority is unavailable")
        candidate = ProtocolCandidate(
            profile_hash=current["staged_profile_hash"],
            runtime_capability_hash=current["staged_runtime_capability_hash"],
            writer_binary_hash=current["staged_writer_binary_hash"],
            writer_capability_hash=current["staged_writer_capability_hash"],
            tool_inventory_hash=current["staged_tool_inventory_hash"],
            hook_projection_hash=current["staged_hook_projection_hash"],
            hook_matcher_mode=current["staged_hook_matcher_mode"],
            hook_matcher_hash=current["staged_hook_matcher_hash"],
            projection_receipt_hash=current["staged_projection_receipt_hash"],
            projection_file_generation=current[
                "staged_projection_file_generation"
            ],
            installer_identity_hash=current["staged_installer_identity_hash"],
            installer_capability_hash=current[
                "staged_installer_capability_hash"
            ],
            storage_dev=current["storage_dev"],
        )
        return (
            DataCapability(candidate.writer_capability_hash, _seal=_DATA_SEAL),
            candidate,
        )

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
        _require_int(
            projected_db_growth_bytes,
            "projected_db_growth_bytes",
            minimum=0,
        )
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
        protocol_lock = self._locks.acquire_protocol()
        held: registration_lock.HeldLock | None = None
        committed = False
        grant_durable = False
        execution: MemberExecution | None = None
        try:
            protocol_lock.verify()
            held = self._locks.acquire_member(member_id)
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
                    authority = self._validate_semantic_closure_tx(
                        member_id, episode_id=None
                    )
                    if (
                        authority is None
                        or authority.protocol["protocol_hash"]
                        != current["protocol_hash"]
                    ):
                        raise StaleAuthority("member closure missing")
                    member = dict(authority.member)
                    effect = dict(authority.effect)
                    old_status = dict(authority.status)
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
                                "created_wall_ns": self._fresh_wall_ns(),
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
                    try:
                        self._commit()
                    except BaseException:
                        grant_durable = self._grant_is_durable(
                            operation_id=operation_id,
                            operation_kind="OPEN_EFFECT",
                            member_id=member_id,
                            executor_token_hash=token_hash,
                        )
                        raise
                    grant_durable = True
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
                    self.verify_execution(execution)
                    self._fault("before_grant_return")
                    committed = True
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
        except BaseException as primary:
            if not grant_durable and not self._connection.in_transaction:
                try:
                    grant_durable = self._grant_is_durable(
                        operation_id=operation_id,
                        operation_kind="OPEN_EFFECT",
                        member_id=member_id,
                        executor_token_hash=token_hash,
                    )
                except sqlite3.Error as check_error:
                    primary.add_note(
                        "grant durability classification failed secondarily: "
                        f"{type(check_error).__name__}"
                    )
            if grant_durable:
                if execution is None:
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
                self._cleanup_failed_grant(
                    data=data,
                    candidate=candidate,
                    execution=execution,
                    primary=primary,
                )
            raise
        finally:
            if protocol_lock.held:
                protocol_lock.release()
            if not committed and held is not None:
                held.release()

    def _require_transfer_deadline(self, deadline_ns: int) -> float:
        _require_int(deadline_ns, "deadline_ns", minimum=0)
        protocol = self.current_protocol()
        sample_boot_id, sample_mono_ns = self._fresh_sample()
        if (
            protocol is None
            or protocol["mode"] != "DRAINING"
            or protocol["staged_generation"] is None
            or sample_boot_id != protocol["drain_boot_id"]
            or sample_mono_ns >= deadline_ns
            or deadline_ns - sample_mono_ns > 5_000_000_000
            or deadline_ns > protocol["drain_deadline_mono_ns"]
        ):
            raise AuthorizationError(
                "staged transfer deadline exceeds drain authority"
            )
        return (deadline_ns - sample_mono_ns) / 1_000_000_000

    def _validate_execution_grant(
        self,
        authority: SelectedAuthority,
        execution: MemberExecution,
    ) -> ValidatedOperation:
        operations: dict[str, ValidatedOperation] = {}
        grant = self._validated_operation(
            execution.operation_id, operations
        )
        staged = execution.target_staged_epoch_hash is not None
        allowed_kinds = (
            {"ADOPT_EFFECT", "REACQUIRE_EFFECT"}
            if staged
            else {"OPEN_EFFECT", "REACQUIRE_EFFECT"}
        )
        effect_companion = (
            grant["lineage_effect_id"]
            if grant["operation_kind"] == "ADOPT_EFFECT"
            else grant["target_effect_id"]
        )
        if (
            grant["operation_kind"] not in allowed_kinds
            or grant["target_member_id"] != execution.member_id
            or effect_companion != execution.effect_id
            or grant["target_executor_token_hash"]
            != execution.executor_token_hash
            or grant["target_member_tuple_hash"]
            != execution.target_member_hash
            or grant["target_status_hash"] != execution.target_status_hash
            or grant["target_protocol_hash"]
            != execution.target_protocol_hash
            or grant["target_staged_epoch_hash"]
            != execution.target_staged_epoch_hash
            or authority.status["write_operation_id"]
            != execution.operation_id
            or authority.status["write_operation_seq"]
            != grant["operation_seq"]
            or authority.status["write_operation_hash"]
            != grant["operation_envelope_hash"]
        ):
            raise AuthorizationError(
                "executor granting operation companion changed"
            )
        if grant["operation_kind"] == "ADOPT_EFFECT":
            if (
                grant["target_action_plan_hash"]
                != authority.effect["action_plan_hash"]
                or grant["lineage_effect_id"]
                != authority.effect["effect_id"]
            ):
                raise AuthorizationError(
                    "adopted executor lineage changed"
                )
        elif (
            grant["target_effect_tuple_hash"]
            != authority.effect["request_tuple_hash"]
            or grant["expected_target_effect_tuple_hash"]
            != authority.effect["request_tuple_hash"]
        ):
            raise AuthorizationError(
                "executor effect companion changed"
            )
        return grant

    def verify_execution(self, execution: MemberExecution) -> None:
        execution.verify_owner(self)
        if self._connection.in_transaction:
            raise AuthorizationError("helper I/O check cannot nest a transaction")
        authority = (
            self._validate_semantic_closure_tx(
                execution.member_id, episode_id=None
            )
            if getattr(self._authorizer_local, "active", False)
            else self.validate_semantic_closure(execution.member_id)
        )
        if authority is None or (
            authority.effect["effect_id"] != execution.effect_id
        ):
            raise AuthorizationError("post-commit executor authority is absent")
        grant = self._validate_execution_grant(authority, execution)
        if (
            authority.member["member_tuple_hash"],
            authority.status["status_hash"],
            authority.status["executor_token_hash"],
            authority.effect["request_tuple_hash"],
        ) != (
            execution.target_member_hash,
            execution.target_status_hash,
            execution.executor_token_hash,
            execution.target_effect_hash,
        ):
            raise AuthorizationError("post-commit executor authority changed")
        if execution.target_staged_epoch_hash is None:
            if authority.protocol["protocol_hash"] != execution.target_protocol_hash:
                raise AuthorizationError("post-commit protocol authority changed")
            return
        draining = (
            authority.protocol["protocol_hash"] == execution.target_protocol_hash
            and authority.protocol["staged_epoch_hash"]
            == execution.target_staged_epoch_hash
            and authority.member["helper_generation"]
            == authority.protocol["staged_generation"]
            and authority.status["executor_generation"]
            == authority.protocol["staged_generation"]
            and authority.protocol["mode"] == "DRAINING"
        )
        advanced = (
            authority.protocol["mode"] == "WRITABLE"
            and authority.member["helper_generation"]
            == authority.status["executor_generation"]
            and grant["operation_kind"]
            in {"ADOPT_EFFECT", "REACQUIRE_EFFECT"}
            and (
                staged_protocol_row := self._connection.execute(
                    "SELECT * FROM registration_protocol_epoch "
                    "WHERE protocol_seq=?",
                    (grant["protocol_seq"],),
                ).fetchone()
            )
            is not None
            and (
                staged_protocol := self._validate_protocol_row(
                    staged_protocol_row
                )
            )["staged_epoch_hash"]
            == execution.target_staged_epoch_hash
            and staged_protocol["staged_generation"]
            == authority.protocol["protocol_generation"]
            and staged_protocol["staged_runtime_capability_hash"]
            == authority.protocol["runtime_capability_hash"]
        )
        if not draining and not advanced:
            raise AuthorizationError("staged executor lineage changed")

    def receive_staged_execution(
        self,
        transfer: registration_executor.StagedSecretTransfer,
        *,
        expected_frame_digest: str,
        deadline_ns: int,
        staged_candidate: ProtocolCandidate | None = None,
        staged_profile_binding: (
            registration_profile.StagedProfileBinding | None
        ) = None,
    ) -> MemberExecution:
        _require_hash(expected_frame_digest, "expected_frame_digest")
        self._require_transfer_deadline(deadline_ns)
        protocol = self.current_protocol()
        if protocol is None:
            raise AuthorizationError("staged protocol authority is absent")
        if staged_candidate is None and not self._allow_test_profile:
            raise registration_profile.ProfileError(
                "staged candidate profile is required"
            )
        typed_staged = None
        if staged_candidate is not None:
            self._require_staged_candidate(
                staged_candidate, current=protocol
            )
            typed_staged = self._require_typed_profile_binding(
                staged_candidate,
                staged_profile_binding,
                staged=True,
            )
        received = transfer.receive_frame(
            deadline_ns=deadline_ns,
            expected_frame_digest=expected_frame_digest,
        )
        held: registration_lock.HeldLock | None = None
        execution: MemberExecution | None = None
        try:
            frame = received.frame
            if staged_candidate is not None:
                latest = self.current_protocol()
                if latest is None:
                    raise AuthorizationError(
                        "staged protocol authority is absent"
                    )
                self._require_staged_candidate(
                    staged_candidate, current=latest
                )
                typed_staged = self._require_typed_profile_binding(
                    staged_candidate,
                    staged_profile_binding,
                    staged=True,
                )
            remaining = self._require_transfer_deadline(deadline_ns)
            held = self._locks.acquire_member(
                frame.member_id, timeout=min(remaining, 5.0)
            )
            held.verify()
            effect = self._connection.execute(
                "SELECT request_tuple_hash FROM registration_effect "
                "WHERE effect_id=?",
                (frame.effect_id,),
            ).fetchone()
            if effect is None:
                raise AuthorizationError("staged executor effect is absent")
            execution = MemberExecution(
                store_identity=id(self),
                member_lock=held,
                secret=received.take_secret(),
                member_id=frame.member_id,
                effect_id=frame.effect_id,
                executor_token_hash=frame.executor_token_hash,
                operation_id=frame.operation_id,
                target_member_hash=frame.member_tuple_hash,
                target_effect_hash=effect["request_tuple_hash"],
                target_status_hash=frame.status_hash,
                target_protocol_hash=frame.protocol_hash,
                target_staged_epoch_hash=frame.staged_epoch_hash,
                _seal=_EXECUTION_SEAL,
            )
            self.verify_execution(execution)
            self._require_transfer_deadline(deadline_ns)
            transfer.acknowledge_activated(
                frame.digest, deadline_ns=deadline_ns
            )
            if typed_staged is not None:
                self._staged_typed_profile_binding = typed_staged
            return execution
        except Exception:
            if execution is not None:
                execution.close()
            elif held is not None:
                held.release()
            raise
        finally:
            received.close()

    def transfer_staged_execution(
        self,
        execution: MemberExecution,
        transfer: registration_executor.StagedSecretTransfer,
        *,
        deadline_ns: int,
    ) -> None:
        execution.verify_owner(self)
        try:
            self._require_transfer_deadline(deadline_ns)
            execution._transfer_staged(transfer, deadline_ns=deadline_ns)
            self._activated_staged_grants.add(execution.operation_id)
        except BaseException as primary:
            if execution.held:
                try:
                    current = self.current_protocol()
                    if current is None:
                        raise AuthorizationError(
                            "staged cleanup authority is unavailable"
                        )
                    cleanup_data, cleanup_candidate = (
                        self._staged_cleanup_credentials(current)
                    )
                except BaseException as cleanup:
                    primary.add_note(
                        "grant cleanup authority failed secondarily: "
                        f"{type(cleanup).__name__}"
                    )
                    execution.close()
                else:
                    self._cleanup_failed_grant(
                        data=cleanup_data,
                        candidate=cleanup_candidate,
                        execution=execution,
                        primary=primary,
                    )
            raise

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
        _require_int(external_growth_bytes, "external_growth_bytes", minimum=0)
        _require_int(
            projected_db_growth_bytes,
            "projected_db_growth_bytes",
            minimum=0,
        )
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
                authority = self._validate_semantic_closure_tx(
                    execution.member_id, episode_id=None
                )
                if (
                    authority is None
                    or authority.effect["effect_id"] != execution.effect_id
                    or authority.member["member_tuple_hash"]
                    != execution.target_member_hash
                    or authority.status["status_hash"]
                    != execution.target_status_hash
                    or authority.status["executor_token_hash"]
                    != execution.executor_token_hash
                ):
                    raise StaleAuthority("APPEND_ACTION semantic closure changed")
                effect = dict(authority.effect)
                status = dict(authority.status)
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
                    "observed_wall_ns": self._fresh_wall_ns(),
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
        profile_binding: (
            registration_profile.TypedProfileBinding | None
        ) = None,
        operation_id: str | None = None,
        projected_db_growth_bytes: int = 0,
    ) -> OperationResult | RecoveryReserveExhausted:
        if type(projected_db_growth_bytes) is not int or projected_db_growth_bytes not in {
            0,
            RECOVERY_OPERATION_BYTES,
        }:
            raise ValueError("recovery projection must be exactly 8192 bytes")
        current, staged_recovery = self._require_recovery_candidate(
            data, candidate
        )
        typed_binding = self._require_recovery_profile_binding(
            candidate, staged_recovery, profile_binding
        )
        execution.verify_owner(self)
        self.verify_execution(execution)
        if staged_recovery and (
            execution.target_staged_epoch_hash != current["staged_epoch_hash"]
        ):
            raise StaleAuthority("staged unavailable executor lineage mismatch")
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
                    closure = self._validate_semantic_closure_tx(
                        execution.member_id, episode_id=None
                    )
                    if (
                        closure is None
                        or closure.status["status_hash"] != old["status_hash"]
                        or closure.effect["effect_id"] != execution.effect_id
                    ):
                        raise StaleAuthority("unavailable semantic closure changed")
                    exhausted = self._recovery_reserve_exhaustion(
                        protocol=closure.protocol,
                        member=closure.member,
                        effect=closure.effect,
                        status=closure.status,
                    )
                    if exhausted is not None:
                        self._connection.execute("COMMIT")
                        execution.close()
                        return exhausted
                    current = closure.protocol
                    if current["mode"] == "DRAINING" and (
                        sample_boot_id != current["drain_boot_id"]
                        or sample_mono_ns > current["drain_deadline_mono_ns"]
                        or closure.member["helper_generation"]
                        != current["staged_generation"]
                        or execution.target_staged_epoch_hash
                        != current["staged_epoch_hash"]
                    ):
                        raise StaleAuthority("staged unavailable drain lineage changed")
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
                            "target_staged_epoch_hash": (
                                current["staged_epoch_hash"]
                                if current["mode"] == "DRAINING"
                                else None
                            ),
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
                    if typed_binding is not None:
                        if staged_recovery:
                            self._staged_typed_profile_binding = typed_binding
                        else:
                            self._current_typed_profile_binding = typed_binding
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
        profile_binding: (
            registration_profile.TypedProfileBinding | None
        ) = None,
        operation_id: str | None = None,
        _member_lock: registration_lock.HeldLock | None = None,
    ) -> OperationResult | RecoveryReserveExhausted:
        """Member-lock takeover after same-boot executor process death."""
        _current, staged_recovery = self._require_recovery_candidate(
            data, candidate
        )
        typed_binding = self._require_recovery_profile_binding(
            candidate, staged_recovery, profile_binding
        )
        operation_id = operation_id or self._operation_ids()
        with self._member_lock_scope(member_id, _member_lock) as held:
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
                    closure = self._validate_semantic_closure_tx(
                        member_id, episode_id=None
                    )
                    if (
                        closure is None
                        or closure.status["status_hash"] != old["status_hash"]
                    ):
                        raise StaleAuthority("dead-executor semantic closure changed")
                    exhausted = self._recovery_reserve_exhaustion(
                        protocol=closure.protocol,
                        member=closure.member,
                        effect=closure.effect,
                        status=closure.status,
                    )
                    if exhausted is not None:
                        self._connection.execute("COMMIT")
                        return exhausted
                    current = closure.protocol
                    if current["mode"] == "DRAINING" and (
                        sample_boot_id != current["drain_boot_id"]
                        or sample_mono_ns > current["drain_deadline_mono_ns"]
                        or closure.member["helper_generation"]
                        != current["staged_generation"]
                        or old["executor_generation"] != current["staged_generation"]
                    ):
                        raise StaleAuthority("staged dead-executor lineage changed")
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
                            "target_staged_epoch_hash": (
                                current["staged_epoch_hash"]
                                if current["mode"] == "DRAINING"
                                else None
                            ),
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
                    if typed_binding is not None:
                        if staged_recovery:
                            self._staged_typed_profile_binding = typed_binding
                        else:
                            self._current_typed_profile_binding = typed_binding
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
        profile_binding: (
            registration_profile.TypedProfileBinding | None
        ) = None,
        executor_secret: bytes | None = None,
        operation_id: str | None = None,
        projected_db_growth_bytes: int = 0,
    ) -> ExecutionResult | RecoveryReserveExhausted:
        if type(projected_db_growth_bytes) is not int or projected_db_growth_bytes not in {
            0,
            RECOVERY_OPERATION_BYTES,
        }:
            raise ValueError("recovery projection must be exactly 8192 bytes")
        _current, staged_recovery = self._require_recovery_candidate(
            data, candidate
        )
        secret = executor_secret or secrets.token_bytes(32)
        if not isinstance(secret, bytes) or len(secret) < 32:
            raise AuthorizationError("executor secret must contain at least 256 bits")
        token_hash = _domain_hash("awa-registration-executor/v1", secret)
        operation_id = operation_id or self._operation_ids()
        protocol_lock = self._locks.acquire_protocol()
        held: registration_lock.HeldLock | None = None
        committed = False
        grant_durable = False
        execution: MemberExecution | None = None
        try:
            protocol_lock.verify()
            current, staged_recovery = self._require_recovery_candidate(
                data, candidate
            )
            typed_binding = self._require_recovery_profile_binding(
                candidate, staged_recovery, profile_binding
            )
            held = self._locks.acquire_member(member_id)
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
                    current, staged_recovery = self._require_recovery_candidate(
                        data, candidate
                    )
                    closure = self._validate_semantic_closure_tx(
                        member_id, episode_id=None
                    )
                    if (
                        closure is None
                        or closure.protocol["protocol_hash"]
                        != current["protocol_hash"]
                    ):
                        raise StaleAuthority(
                            "reacquire semantic closure changed"
                        )
                    member = dict(closure.member)
                    effect = dict(closure.effect)
                    old = dict(closure.status)
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
                        or (
                            staged_recovery
                            and (
                                sample_boot_id != current["drain_boot_id"]
                                or sample_mono_ns
                                > current["drain_deadline_mono_ns"]
                                or member["helper_generation"]
                                != current["staged_generation"]
                            )
                        )
                    ):
                        raise StaleAuthority("REACQUIRE_EFFECT stale tuple")
                    exhausted = self._recovery_reserve_exhaustion(
                        protocol=closure.protocol,
                        member=closure.member,
                        effect=closure.effect,
                        status=closure.status,
                    )
                    if exhausted is not None:
                        self._connection.execute("COMMIT")
                        return exhausted
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
                                (
                                    "staged_generation"
                                    if staged_recovery
                                    else "protocol_generation"
                                )
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
                            "target_staged_epoch_hash": (
                                current["staged_epoch_hash"]
                                if staged_recovery
                                else None
                            ),
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
                    try:
                        self._commit()
                    except BaseException:
                        grant_durable = self._grant_is_durable(
                            operation_id=operation_id,
                            operation_kind="REACQUIRE_EFFECT",
                            member_id=member_id,
                            executor_token_hash=token_hash,
                        )
                        raise
                    grant_durable = True
                    if typed_binding is not None:
                        if staged_recovery:
                            self._staged_typed_profile_binding = typed_binding
                        else:
                            self._current_typed_profile_binding = typed_binding
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
                        target_staged_epoch_hash=(
                            current["staged_epoch_hash"]
                            if staged_recovery
                            else None
                        ),
                        _seal=_EXECUTION_SEAL,
                    )
                    self.verify_execution(execution)
                    self._fault("before_grant_return")
                    committed = True
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
        except BaseException as primary:
            if not grant_durable and not self._connection.in_transaction:
                try:
                    grant_durable = self._grant_is_durable(
                        operation_id=operation_id,
                        operation_kind="REACQUIRE_EFFECT",
                        member_id=member_id,
                        executor_token_hash=token_hash,
                    )
                except sqlite3.Error as check_error:
                    primary.add_note(
                        "grant durability classification failed secondarily: "
                        f"{type(check_error).__name__}"
                    )
            if grant_durable:
                if execution is None:
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
                        target_staged_epoch_hash=(
                            current["staged_epoch_hash"]
                            if staged_recovery
                            else None
                        ),
                        _seal=_EXECUTION_SEAL,
                    )
                self._cleanup_failed_grant(
                    data=data,
                    candidate=candidate,
                    execution=execution,
                    primary=primary,
                )
            raise
        finally:
            if protocol_lock.held:
                protocol_lock.release()
            if not committed and held is not None:
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
        _require_int(
            projected_db_growth_bytes,
            "projected_db_growth_bytes",
            minimum=0,
        )
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
        _require_int(
            projected_db_growth_bytes,
            "projected_db_growth_bytes",
            minimum=0,
        )
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
                    current = self._require_current_candidate(
                        candidate, mode="WRITABLE"
                    )
                    authority = self._validate_semantic_closure_tx(
                        execution.member_id, episode_id=None
                    )
                    if (
                        authority is None
                        or authority.protocol["protocol_hash"]
                        != current["protocol_hash"]
                        or authority.effect["effect_id"] != execution.effect_id
                    ):
                        raise StaleAuthority("effect close closure changed")
                    member = dict(authority.member)
                    effect = dict(authority.effect)
                    old_status = dict(authority.status)
                    if (
                        member["phase"] != "EFFECT_IN_FLIGHT"
                        or effect["outcome_kind"] is not None
                        or old_status["status_hash"]
                        != execution.target_status_hash
                        or old_status["executor_token_hash"]
                        != execution.executor_token_hash
                    ):
                        raise StaleAuthority("effect close stale tuple")
                    actions = tuple(dict(item) for item in authority.actions)
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

    def _semantic_failure(self, detail: str) -> None:
        raise SemanticClosureError(f"registration semantic closure: {detail}")

    def _validated_operation(
        self,
        operation_id: str,
        operations: dict[str, ValidatedOperation] | None = None,
    ) -> ValidatedOperation:
        row = self._connection.execute(
            "SELECT * FROM registration_operation_audit WHERE operation_id=?",
            (operation_id,),
        ).fetchone()
        if row is None:
            self._semantic_failure("operation backlink is missing")
        value = dict(row)
        if (
            registration_hashes.derive("operation_envelope_hash", value)
            != value["operation_envelope_hash"]
        ):
            self._semantic_failure("operation envelope hash mismatch")
        expected_class = (
            "BOOTSTRAP"
            if value["operation_kind"] == "BOOTSTRAP"
            else (
                "CONTROL"
                if value["operation_kind"] in _CONTROL_OPERATION_KINDS
                else "DATA"
            )
        )
        if (
            value["operation_class"] != expected_class
            or value["operation_kind"] not in PROJECTED_DB_BYTES
            or type(value["operation_seq"]) is not int
            or type(value["expected_revision"]) is not int
            or value["expected_revision"] != value["operation_seq"] - 1
            or type(value["projected_db_growth_bytes"]) is not int
            or value["projected_db_growth_bytes"]
            < PROJECTED_DB_BYTES[value["operation_kind"]]
        ):
            self._semantic_failure("operation class/revision/projection mismatch")
        validated = ValidatedOperation.from_row(value)
        assert isinstance(validated, ValidatedOperation)
        if operations is not None:
            operations[operation_id] = validated
        return validated

    def _validate_write_backlink(
        self,
        row: Mapping[str, Any],
        *,
        operation_id_field: str,
        operation_seq_field: str,
        operation_hash_field: str,
        target_hash_field: str,
        target_hash: str,
        operations: dict[str, ValidatedOperation],
        target_member_id: str | None = None,
        target_effect_id: str | None = None,
        operation_kinds: frozenset[str] | None = None,
    ) -> ValidatedOperation:
        operation_id = row[operation_id_field]
        if not isinstance(operation_id, str):
            self._semantic_failure("write backlink id is missing")
        operation = self._validated_operation(operation_id, operations)
        if (
            operation["operation_seq"] != row[operation_seq_field]
            or operation["operation_envelope_hash"] != row[operation_hash_field]
            or operation[target_hash_field] != target_hash
            or (
                operation_kinds is not None
                and operation["operation_kind"] not in operation_kinds
            )
            or (
                target_member_id is not None
                and operation["target_member_id"] != target_member_id
            )
            or (
                target_effect_id is not None
                and target_effect_id
                not in {
                    operation["target_effect_id"],
                    operation["target_successor_effect_id"],
                }
            )
        ):
            self._semantic_failure(
                "write backlink companion mismatch "
                f"({operation['operation_kind']}:{target_hash_field})"
            )
        return operation

    def _validate_protocol_transition(
        self,
        *,
        value: Mapping[str, Any],
        predecessor: Mapping[str, Any],
        operation: Mapping[str, Any],
        staged_fields: tuple[str, ...],
    ) -> None:
        kind = value["transition_kind"]
        expected_modes = {
            "ACTIVATE": ("DORMANT", "WRITABLE"),
            "FIRST_EFFECT": ("WRITABLE", "WRITABLE"),
            "BEGIN_DRAIN": ("WRITABLE", "DRAINING"),
            "STAGE_NEXT": ("DRAINING", "DRAINING"),
            "CANCEL_DRAIN": ("DRAINING", "DORMANT"),
            "ADVANCE_GENERATION": ("DRAINING", "WRITABLE"),
            "PRE_EFFECT_DORMANT": ("DRAINING", "DORMANT"),
            "ENTER_CONTAINMENT": (
                predecessor["mode"],
                "CONTAINMENT",
            ),
            "BEGIN_REPAIR": ("CONTAINMENT", "DRAINING"),
        }
        if kind not in expected_modes:
            self._semantic_failure("unknown protocol transition")
        expected_old_mode, expected_new_mode = expected_modes[kind]
        if (
            predecessor["mode"] != expected_old_mode
            or value["mode"] != expected_new_mode
            or (
                kind == "ENTER_CONTAINMENT"
                and predecessor["mode"]
                not in {"DORMANT", "WRITABLE", "DRAINING"}
            )
        ):
            self._semantic_failure("protocol mode transition mismatch")

        if kind == "FIRST_EFFECT":
            if (
                predecessor["first_effect_id"] is not None
                or value["first_effect_id"] is None
                or value["first_effect_operation_id"] != value["operation_id"]
            ):
                self._semantic_failure("first-effect transition mismatch")
        elif (
            value["first_effect_id"] != predecessor["first_effect_id"]
            or value["first_effect_operation_id"]
            != predecessor["first_effect_operation_id"]
        ):
            self._semantic_failure("first-effect carry mismatch")

        current_fields = (
            "protocol_generation",
            "schema_hash",
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
        staged_sources = (
            ("protocol_generation", "staged_generation"),
            *tuple(
                (field, f"staged_{field}") for field in current_fields[1:]
            ),
        )
        if kind == "ADVANCE_GENERATION":
            if any(
                value[current] != predecessor[staged]
                for current, staged in staged_sources
            ) or value["storage_dev"] != predecessor["storage_dev"]:
                self._semantic_failure("advanced protocol tuple mismatch")
        elif any(
            value[field] != predecessor[field]
            for field in (*current_fields, "storage_dev")
        ):
            self._semantic_failure("protocol authority carry mismatch")

        clears_staged = {
            "CANCEL_DRAIN",
            "ADVANCE_GENERATION",
            "PRE_EFFECT_DORMANT",
        }
        if kind == "STAGE_NEXT":
            if (
                value["staged_generation"]
                != int(predecessor["protocol_generation"]) + 1
                or value["staged_schema_hash"] != predecessor["schema_hash"]
            ):
                self._semantic_failure("staged protocol transition mismatch")
        elif kind in clears_staged:
            if any(value[field] is not None for field in staged_fields):
                self._semantic_failure("staged protocol clear mismatch")
        elif any(
            value[field] != predecessor[field] for field in staged_fields
        ):
            self._semantic_failure("staged protocol carry mismatch")

        if kind in {
            "CANCEL_DRAIN",
            "ADVANCE_GENERATION",
            "PRE_EFFECT_DORMANT",
            "ENTER_CONTAINMENT",
        }:
            if (
                value["drain_boot_id"] is not None
                or value["drain_deadline_mono_ns"] is not None
            ):
                self._semantic_failure("protocol drain clear mismatch")
        elif kind in {"BEGIN_DRAIN", "BEGIN_REPAIR"}:
            if (
                value["drain_boot_id"] != operation["sample_boot_id"]
                or operation["sample_mono_ns"] is None
                or value["drain_deadline_mono_ns"]
                != int(operation["sample_mono_ns"]) + 5_000_000_000
            ):
                self._semantic_failure("protocol drain creation mismatch")
        elif (
            value["drain_boot_id"] != predecessor["drain_boot_id"]
            or value["drain_deadline_mono_ns"]
            != predecessor["drain_deadline_mono_ns"]
        ):
            self._semantic_failure("protocol drain carry mismatch")

        if kind == "ENTER_CONTAINMENT":
            reason = value["transition_reason_code"]
            sample_boot = operation["sample_boot_id"]
            sample_mono = operation["sample_mono_ns"]
            if (
                reason == "DRAIN_BOOT_CHANGED"
                and (
                    predecessor["mode"] != "DRAINING"
                    or sample_boot is None
                    or sample_mono is None
                    or sample_boot == predecessor["drain_boot_id"]
                )
            ) or (
                reason == "DRAIN_TIMEOUT"
                and (
                    predecessor["mode"] != "DRAINING"
                    or sample_boot != predecessor["drain_boot_id"]
                    or sample_mono is None
                    or int(sample_mono)
                    <= int(predecessor["drain_deadline_mono_ns"])
                )
            ) or (
                reason == "ADOPTION_FAILED"
                and (
                    predecessor["mode"] != "DRAINING"
                    or sample_boot != predecessor["drain_boot_id"]
                )
            ):
                self._semantic_failure("containment transition mismatch")

    def _validate_immediate_protocol_predecessor(
        self,
        row: Mapping[str, Any],
        operations: dict[str, ValidatedOperation] | None,
    ) -> None:
        value = dict(row)
        if (
            registration_hashes.derive("protocol_hash", value)
            != value["protocol_hash"]
        ):
            self._semantic_failure("protocol predecessor hash mismatch")
        staged_fields = registration_hashes.PREIMAGES[
            "staged_epoch_hash"
        ].columns
        staged_with_hash = (*staged_fields, "staged_epoch_hash")
        if value["staged_generation"] is None:
            if any(value[field] is not None for field in staged_with_hash):
                self._semantic_failure(
                    "protocol predecessor has partial staged values"
                )
        elif (
            any(value[field] is None for field in staged_with_hash)
            or registration_hashes.derive("staged_epoch_hash", value)
            != value["staged_epoch_hash"]
        ):
            self._semantic_failure(
                "protocol predecessor staged tuple mismatch"
            )
        if (
            value["mode"] == "DRAINING"
            and (
                value["drain_boot_id"] is None
                or value["drain_deadline_mono_ns"] is None
            )
        ) or (
            value["mode"] != "DRAINING"
            and (
                value["drain_boot_id"] is not None
                or value["drain_deadline_mono_ns"] is not None
            )
        ):
            self._semantic_failure(
                "protocol predecessor mode/drain totality mismatch"
            )
        if (value["first_effect_id"] is None) != (
            value["first_effect_operation_id"] is None
        ):
            self._semantic_failure(
                "protocol predecessor first-effect pair is incomplete"
            )
        if (value["absence_proof_hash"] is not None) != (
            value["transition_kind"] == "PRE_EFFECT_DORMANT"
        ) or (value["quiescence_proof_hash"] is not None) != (
            value["transition_kind"]
            in {"STAGE_NEXT", "CANCEL_DRAIN", "ADVANCE_GENERATION"}
        ):
            self._semantic_failure(
                "protocol predecessor proof totality mismatch"
            )
        if value["transition_kind"] == "ENTER_CONTAINMENT":
            if value["transition_reason_code"] not in {
                "DRAIN_BOOT_CHANGED",
                "DRAIN_TIMEOUT",
                "ADOPTION_FAILED",
                "STORE_FAILURE",
            }:
                self._semantic_failure(
                    "protocol predecessor containment reason mismatch"
                )
        elif value["transition_reason_code"] != value["transition_kind"]:
            self._semantic_failure(
                "protocol predecessor transition reason mismatch"
            )
        sequence = value["protocol_seq"]
        if type(sequence) is not int or sequence < 1:
            self._semantic_failure(
                "protocol predecessor sequence is invalid"
            )
        if sequence == 1:
            if (
                value["previous_protocol_hash"] is not None
                or value["protocol_generation"] != 1
                or value["mode"] != "DORMANT"
                or value["transition_kind"] != "BOOTSTRAP"
                or value["first_effect_id"] is not None
                or value["staged_generation"] is not None
            ):
                self._semantic_failure(
                    "protocol predecessor genesis shape mismatch"
                )
        elif value["previous_protocol_hash"] is None:
            self._semantic_failure(
                "protocol predecessor link is missing"
            )
        operation = self._validated_operation(
            value["operation_id"], operations
        )
        expected_kind = (
            "OPEN_EFFECT"
            if value["transition_kind"] == "FIRST_EFFECT"
            else value["transition_kind"]
        )
        if (
            operation["operation_kind"] != expected_kind
            or operation["target_protocol_hash"] != value["protocol_hash"]
            or operation["protocol_seq"] != sequence - 1
        ):
            self._semantic_failure(
                "protocol predecessor operation companion mismatch"
            )
        first_id = value["first_effect_id"]
        first_operation_id = value["first_effect_operation_id"]
        if first_operation_id is not None:
            first = self._validated_operation(
                first_operation_id, operations
            )
            first_protocol = self._connection.execute(
                "SELECT * FROM registration_protocol_epoch "
                "WHERE protocol_hash=?",
                (first["target_protocol_hash"],),
            ).fetchone()
            if (
                first["operation_kind"] != "OPEN_EFFECT"
                or first["target_effect_id"] != first_id
                or first_protocol is None
                or registration_hashes.derive(
                    "protocol_hash", dict(first_protocol)
                )
                != first_protocol["protocol_hash"]
                or first_protocol["transition_kind"] != "FIRST_EFFECT"
                or first_protocol["operation_id"] != first_operation_id
                or first_protocol["first_effect_id"] != first_id
                or first_protocol["first_effect_operation_id"]
                != first_operation_id
                or int(first_protocol["protocol_seq"]) > int(sequence)
            ):
                self._semantic_failure(
                    "protocol predecessor first-effect companion mismatch"
                )

    def _validate_protocol_row(
        self,
        row: Mapping[str, Any],
        operations: dict[str, ValidatedOperation] | None = None,
    ) -> ValidatedProtocol:
        value = dict(row)
        if registration_hashes.derive("protocol_hash", value) != value["protocol_hash"]:
            self._semantic_failure("protocol hash mismatch")
        staged_fields = registration_hashes.PREIMAGES["staged_epoch_hash"].columns
        staged_with_hash = (*staged_fields, "staged_epoch_hash")
        if value["staged_generation"] is None:
            if any(value[field] is not None for field in staged_with_hash):
                self._semantic_failure("unstaged protocol has staged values")
        else:
            if any(value[field] is None for field in staged_with_hash):
                self._semantic_failure("staged protocol tuple is incomplete")
            if (
                registration_hashes.derive("staged_epoch_hash", value)
                != value["staged_epoch_hash"]
            ):
                self._semantic_failure("staged epoch hash mismatch")
        if (
            value["mode"] == "DRAINING"
            and (
                value["drain_boot_id"] is None
                or value["drain_deadline_mono_ns"] is None
            )
        ) or (
            value["mode"] != "DRAINING"
            and (
                value["drain_boot_id"] is not None
                or value["drain_deadline_mono_ns"] is not None
            )
        ):
            self._semantic_failure("protocol mode/drain totality mismatch")
        if (value["first_effect_id"] is None) != (
            value["first_effect_operation_id"] is None
        ):
            self._semantic_failure("first-effect pair is incomplete")
        if (value["absence_proof_hash"] is not None) != (
            value["transition_kind"] == "PRE_EFFECT_DORMANT"
        ):
            self._semantic_failure("protocol absence proof mismatch")
        if (value["quiescence_proof_hash"] is not None) != (
            value["transition_kind"]
            in {"STAGE_NEXT", "CANCEL_DRAIN", "ADVANCE_GENERATION"}
        ):
            self._semantic_failure("protocol quiescence proof mismatch")
        expected_reason = (
            value["transition_reason_code"]
            if value["transition_kind"] == "ENTER_CONTAINMENT"
            else value["transition_kind"]
        )
        if (
            value["transition_kind"] != "ENTER_CONTAINMENT"
            and value["transition_reason_code"] != expected_reason
        ) or (
            value["transition_kind"] == "ENTER_CONTAINMENT"
            and value["transition_reason_code"]
            not in {
                "DRAIN_BOOT_CHANGED",
                "DRAIN_TIMEOUT",
                "ADOPTION_FAILED",
                "STORE_FAILURE",
            }
        ):
            self._semantic_failure("protocol transition reason mismatch")
        sequence = int(value["protocol_seq"])
        predecessor_value: Mapping[str, Any] | None = None
        if sequence == 1:
            if (
                value["previous_protocol_hash"] is not None
                or value["protocol_generation"] != 1
                or value["mode"] != "DORMANT"
                or value["transition_kind"] != "BOOTSTRAP"
                or value["first_effect_id"] is not None
                or value["staged_generation"] is not None
            ):
                self._semantic_failure("genesis protocol shape mismatch")
        else:
            predecessor = self._connection.execute(
                "SELECT * FROM registration_protocol_epoch "
                "WHERE protocol_seq=?",
                (sequence - 1,),
            ).fetchone()
            if (
                predecessor is None
                or registration_hashes.derive(
                    "protocol_hash", dict(predecessor)
                )
                != predecessor["protocol_hash"]
                or predecessor["protocol_hash"]
                != value["previous_protocol_hash"]
            ):
                self._semantic_failure("protocol predecessor mismatch")
            predecessor_value = predecessor
            self._validate_immediate_protocol_predecessor(
                predecessor_value, operations
            )
        operation = self._validated_operation(value["operation_id"], operations)
        expected_kind = (
            "OPEN_EFFECT"
            if value["transition_kind"] == "FIRST_EFFECT"
            else value["transition_kind"]
        )
        staged_operation_hash = (
            value["staged_epoch_hash"]
            if value["transition_kind"] == "STAGE_NEXT"
            else (
                predecessor_value["staged_epoch_hash"]
                if predecessor_value is not None
                else None
            )
        )
        if (
            operation["operation_kind"] != expected_kind
            or operation["target_protocol_hash"] != value["protocol_hash"]
            or operation["protocol_seq"] != sequence - 1
            or (
                sequence == 1
                and (
                    operation["expected_protocol_hash"] is not None
                    or operation["expected_mode"] != "NONE"
                    or operation["expected_generation"] != 0
                )
            )
            or (
                predecessor_value is not None
                and (
                    operation["expected_protocol_hash"]
                    != predecessor_value["protocol_hash"]
                    or operation["expected_mode"] != predecessor_value["mode"]
                    or operation["expected_generation"]
                    != predecessor_value["protocol_generation"]
                )
            )
            or operation["target_staged_epoch_hash"]
            != staged_operation_hash
        ):
            self._semantic_failure("protocol operation companion mismatch")
        if predecessor_value is not None:
            self._validate_protocol_transition(
                value=value,
                predecessor=predecessor_value,
                operation=operation,
                staged_fields=staged_with_hash,
            )
        first_id = value["first_effect_id"]
        first_operation_id = value["first_effect_operation_id"]
        if first_operation_id is not None:
            first = self._validated_operation(first_operation_id, operations)
            if (
                first["operation_kind"] != "OPEN_EFFECT"
                or first["target_effect_id"] != first_id
            ):
                self._semantic_failure("first-effect operation mismatch")
            first_protocol_row = self._connection.execute(
                "SELECT * FROM registration_protocol_epoch "
                "WHERE protocol_hash=?",
                (first["target_protocol_hash"],),
            ).fetchone()
            if first_protocol_row is None:
                self._semantic_failure("first-effect protocol is missing")
            first_protocol = dict(first_protocol_row)
            if (
                registration_hashes.derive(
                    "protocol_hash", first_protocol
                )
                != first_protocol["protocol_hash"]
                or first_protocol["transition_kind"] != "FIRST_EFFECT"
                or first_protocol["operation_id"] != first_operation_id
                or first_protocol["first_effect_id"] != first_id
                or first_protocol["first_effect_operation_id"]
                != first_operation_id
                or int(first_protocol["protocol_seq"]) > sequence
            ):
                self._semantic_failure("first-effect protocol mismatch")
        validated = ValidatedProtocol.from_row(value)
        assert isinstance(validated, ValidatedProtocol)
        return validated

    def _validate_domain_blob(
        self,
        *,
        kind: str,
        domain: str,
        raw: bytes,
        expected_hash: str,
        expected_fields: Mapping[str, str],
    ) -> dict[str, Any]:
        parsed = self._parse_semantic_blob(kind, raw)
        if not isinstance(parsed, dict) or "schema" not in parsed:
            self._semantic_failure(f"{kind} blob shape mismatch")
        relation = {key: value for key, value in parsed.items() if key != "schema"}
        self._validate_semantic_blob(kind, raw, relation)
        if _domain_hash(domain, raw) != expected_hash:
            self._semantic_failure(f"{kind} blob hash mismatch")
        if any(parsed.get(field) != expected for field, expected in expected_fields.items()):
            self._semantic_failure(f"{kind} blob relation mismatch")
        return parsed

    def _parse_semantic_blob(
        self, kind: str, raw: bytes
    ) -> dict[str, Any]:
        try:
            parsed = registration_jcs.parse_canonical(raw)
        except registration_jcs.JcsError as error:
            raise SemanticClosureError(
                f"registration semantic closure: {kind} blob is invalid"
            ) from error
        if not isinstance(parsed, dict):
            self._semantic_failure(f"{kind} blob shape mismatch")
        return parsed

    def _validate_semantic_blob(
        self,
        kind: str,
        raw: bytes,
        relation: Mapping[str, Any],
    ) -> None:
        try:
            registration_jcs.validate_blob(kind, raw, relation)
        except registration_jcs.JcsError as error:
            raise SemanticClosureError(
                f"registration semantic closure: {kind} blob is invalid"
            ) from error

    def _validate_effect_row(
        self,
        row: Mapping[str, Any],
        *,
        member: Mapping[str, Any],
        operations: dict[str, ValidatedOperation],
        include_actions: bool,
    ) -> tuple[ValidatedEffect, tuple[ValidatedAction, ...]]:
        effect = dict(row)
        if (
            registration_hashes.derive("request_tuple_hash", effect)
            != effect["request_tuple_hash"]
        ):
            self._semantic_failure("effect request hash mismatch")
        if not self._effect_outcome_is_total(effect):
            self._semantic_failure("effect outcome totality mismatch")
        if (
            type(effect["outcome_reservation_bytes"]) is not int
            or effect["outcome_reservation_bytes"] < MIN_OUTCOME_RESERVATION
            or type(effect["successor_reservation_bytes"]) is not int
            or effect["successor_reservation_bytes"] < MIN_SUCCESSOR_RESERVATION
        ):
            self._semantic_failure("effect reservation floor mismatch")
        if effect["request_kind"] == "CLEAN_ELIGIBLE":
            actions_plan = [
                {
                    "ordinal": str(index),
                    "kind": effect[f"action_{index}_kind"],
                    "action_hash": effect[f"action_{index}_hash"],
                    "postcondition_hash": effect[f"postcondition_{index}_hash"],
                }
                for index in range(1, 5)
            ]
            relation = {
                "actions": actions_plan,
                "external_growth_reservation_bytes": str(
                    effect["external_growth_reservation_bytes"]
                ),
                "outcome_reservation_bytes": str(
                    effect["outcome_reservation_bytes"]
                ),
                "successor_reservation_bytes": str(
                    effect["successor_reservation_bytes"]
                ),
            }
            self._validate_semantic_blob(
                "action_plan", effect["action_plan_blob"], relation
            )
            if (
                _domain_hash(
                    "awa-registration-action-plan/v1",
                    effect["action_plan_blob"],
                )
                != effect["action_plan_hash"]
            ):
                self._semantic_failure("action-plan hash mismatch")
        elif (
            effect["action_plan_blob"] is not None
            or effect["action_plan_hash"] != ZERO_HASH
        ):
            self._semantic_failure("blocked effect has action plan")
        created_operation = self._validate_write_backlink(
            effect,
            operation_id_field="created_operation_id",
            operation_seq_field="created_operation_seq",
            operation_hash_field="created_operation_hash",
            target_hash_field="target_effect_tuple_hash",
            target_hash=effect["request_tuple_hash"],
            operations=operations,
            target_member_id=effect["member_id"],
            target_effect_id=effect["effect_id"],
            operation_kinds=_EFFECT_CREATION_KINDS,
        )
        protocol_row = self._connection.execute(
            "SELECT * FROM registration_protocol_epoch WHERE protocol_seq=?",
            (created_operation["protocol_seq"],),
        ).fetchone()
        if protocol_row is None:
            self._semantic_failure("effect creation protocol is missing")
        creation_protocol = self._validate_protocol_row(
            protocol_row, operations
        )
        staged_creation = (
            created_operation["operation_kind"] == "ADOPT_EFFECT"
            and creation_protocol["staged_generation"]
            == effect["required_protocol_generation"]
        )
        expected_runtime = (
            creation_protocol["staged_runtime_capability_hash"]
            if staged_creation
            else created_operation["runtime_capability_hash"]
        )
        expected_generation = (
            creation_protocol["staged_generation"]
            if staged_creation
            else created_operation["expected_generation"]
        )
        creation_checks = {
            "successor_effect": (
                created_operation["target_successor_effect_id"]
                == effect["effect_id"]
            ),
            "successor_epoch": (
                created_operation["target_successor_member_epoch"]
                == effect["member_epoch"]
            ),
            "successor_basis": (
                created_operation["target_successor_basis_hash"]
                == effect["request_basis_hash"]
            ),
            "action_plan": (
                created_operation["operation_kind"] == "ADOPT_EFFECT"
                or created_operation["target_action_plan_hash"]
                == effect["action_plan_hash"]
            ),
            "external_reservation": (
                created_operation["new_external_reservation_bytes"]
                == effect["external_growth_reservation_bytes"]
            ),
            "outcome_reservation": (
                created_operation["new_outcome_reservation_bytes"]
                == effect["outcome_reservation_bytes"]
            ),
            "successor_reservation": (
                created_operation["new_successor_reservation_bytes"]
                == effect["successor_reservation_bytes"]
            ),
            "generation": (
                effect["required_protocol_generation"]
                == expected_generation
            ),
            "runtime": (
                effect["required_runtime_capability_hash"]
                == expected_runtime
            ),
            "staged_epoch": (
                not staged_creation
                or created_operation["target_staged_epoch_hash"]
                == creation_protocol["staged_epoch_hash"]
            ),
        }
        failed_creation_checks = [
            name for name, passed in creation_checks.items() if not passed
        ]
        if failed_creation_checks:
            self._semantic_failure(
                "effect creation companion mismatch: "
                + ",".join(failed_creation_checks)
            )

        action_values: list[ValidatedAction] = []
        ledger_head = ZERO_HASH
        if include_actions:
            action_rows = self._connection.execute(
                "SELECT * FROM registration_effect_action "
                "WHERE effect_id=? ORDER BY event_seq",
                (effect["effect_id"],),
            ).fetchall()
            if len(action_rows) > 4:
                self._semantic_failure("effect action count exceeds plan")
            terminal_conflict = False
            for event_seq, action_row in enumerate(action_rows, 1):
                action = dict(action_row)
                if (
                    action["event_seq"] != event_seq
                    or action["ordinal"] != event_seq
                    or action["action_kind"] != effect[f"action_{event_seq}_kind"]
                    or action["action_hash"] != effect[f"action_{event_seq}_hash"]
                    or action["postcondition_hash"]
                    != effect[f"postcondition_{event_seq}_hash"]
                    or action["prior_ledger_hash"] != ledger_head
                    or terminal_conflict
                ):
                    self._semantic_failure("action ledger relation mismatch")
                if (
                    registration_hashes.derive("ledger_hash", action)
                    != action["ledger_hash"]
                ):
                    self._semantic_failure("action ledger hash mismatch")
                relation = {
                    "effect_id": effect["effect_id"],
                    "event_seq": str(event_seq),
                    "ordinal": str(event_seq),
                    "kind": action["observation_kind"],
                    "measured_postcondition_hash": self._parse_semantic_blob(
                        "observation", action["observation_blob"]
                    ).get("measured_postcondition_hash"),
                    "external_growth_bytes": str(action["external_growth_bytes"]),
                    "detail_code": action["observation_kind"],
                }
                self._validate_semantic_blob(
                    "observation", action["observation_blob"], relation
                )
                if (
                    _domain_hash(
                        "awa-registration-observation/v1",
                        action["observation_blob"],
                    )
                    != action["observation_hash"]
                ):
                    self._semantic_failure("observation hash mismatch")
                self._validate_write_backlink(
                    action,
                    operation_id_field="write_operation_id",
                    operation_seq_field="write_operation_seq",
                    operation_hash_field="write_operation_hash",
                    target_hash_field="target_action_ledger_hash",
                    target_hash=action["ledger_hash"],
                    operations=operations,
                    target_member_id=effect["member_id"],
                    target_effect_id=effect["effect_id"],
                    operation_kinds=frozenset({"APPEND_ACTION"}),
                )
                terminal_conflict = action["observation_kind"] == "LOGICAL_CONFLICT"
                ledger_head = action["ledger_hash"]
                validated_action = ValidatedAction.from_row(action)
                assert isinstance(validated_action, ValidatedAction)
                action_values.append(validated_action)

        outcome = effect["outcome_kind"]
        if outcome is None:
            if effect["outcome_tuple_hash"] is not None:
                self._semantic_failure("open effect has outcome hash")
        else:
            if (
                registration_hashes.derive("outcome_tuple_hash", effect)
                != effect["outcome_tuple_hash"]
            ):
                self._semantic_failure("effect outcome hash mismatch")
            outcome_operation = self._validate_write_backlink(
                effect,
                operation_id_field="outcome_operation_id",
                operation_seq_field="outcome_operation_seq",
                operation_hash_field="outcome_operation_hash",
                target_hash_field="target_effect_outcome_hash",
                target_hash=effect["outcome_tuple_hash"],
                operations=operations,
                target_member_id=effect["member_id"],
                target_effect_id=effect["effect_id"],
                operation_kinds=(
                    frozenset({"CLOSE_SUCCESS"})
                    if outcome == "SUCCESS"
                    else (
                        frozenset({"CLOSE_CONFLICT"})
                        if outcome == "LOGICAL_CONFLICT"
                        else frozenset(
                            {
                                "INVALIDATE_REQUESTED",
                                "REPLACE_PENDING",
                                "ADOPT_EFFECT",
                            }
                        )
                    )
                ),
            )
            if (
                outcome_operation["target_action_ledger_hash"]
                != (
                    effect["ledger_head_hash"]
                    if outcome in {"SUCCESS", "LOGICAL_CONFLICT"}
                    else None
                )
                or (
                    outcome == "SUPERSEDED"
                    and (
                        outcome_operation["target_successor_effect_id"]
                        != effect["superseded_by_effect_id"]
                        or outcome_operation["target_transition_id"]
                        != effect["successor_transition_id"]
                    )
                )
            ):
                self._semantic_failure("effect outcome companion mismatch")
            if include_actions and outcome in {"SUCCESS", "LOGICAL_CONFLICT"}:
                if effect["ledger_head_hash"] != ledger_head:
                    self._semantic_failure("effect ledger head mismatch")
            if outcome == "SUCCESS":
                self._validate_domain_blob(
                    kind="completion",
                    domain="awa-registration-completion/v1",
                    raw=effect["completion_blob"],
                    expected_hash=effect["completion_hash"],
                    expected_fields={
                        "effect_id": effect["effect_id"],
                        "ledger_head_hash": effect["ledger_head_hash"],
                        "final_basis_hash": effect["final_basis_hash"],
                    },
                )
                proof_fields = {
                    "effect_id": effect["effect_id"],
                    "member_id": effect["member_id"],
                    "final_basis_hash": effect["final_basis_hash"],
                }
                if effect["member_epoch"] == member["member_epoch"]:
                    proof_fields.update(
                        {
                            "physical_basis_hash": member[
                                "physical_basis_hash"
                            ],
                            "git_basis_hash": member["git_basis_hash"],
                            "policy_basis_hash": member[
                                "policy_basis_hash"
                            ],
                            "lifecycle_basis_hash": member[
                                "lifecycle_basis_hash"
                            ],
                        }
                    )
                self._validate_domain_blob(
                    kind="proof",
                    domain="awa-registration-proof/v1",
                    raw=effect["proof_blob"],
                    expected_hash=effect["proof_hash"],
                    expected_fields=proof_fields,
                )
                self._validate_domain_blob(
                    kind="certificate_inputs",
                    domain="awa-registration-certificate-inputs/v1",
                    raw=effect["certificate_inputs_blob"],
                    expected_hash=effect["certificate_inputs_hash"],
                    expected_fields={
                        "effect_id": effect["effect_id"],
                        "ledger_head_hash": effect["ledger_head_hash"],
                        "completion_hash": effect["completion_hash"],
                        "proof_hash": effect["proof_hash"],
                        "final_basis_hash": effect["final_basis_hash"],
                        "helper_generation": str(effect["outcome_helper_generation"]),
                    },
                )
                certificate = registration_hashes.deterministic_id(
                    "awa-reg-certificate-v1",
                    effect["effect_id"],
                    effect["ledger_head_hash"],
                    effect["completion_hash"],
                    effect["proof_hash"],
                    effect["final_basis_hash"],
                    str(effect["outcome_helper_generation"]),
                )
                if certificate != effect["certificate_hash"]:
                    self._semantic_failure("certificate hash mismatch")
            elif outcome == "LOGICAL_CONFLICT":
                parsed = self._parse_semantic_blob(
                    "conflict", effect["conflict_blob"]
                )
                self._validate_domain_blob(
                    kind="conflict",
                    domain="awa-registration-conflict/v1",
                    raw=effect["conflict_blob"],
                    expected_hash=effect["conflict_hash"],
                    expected_fields={
                        "effect_id": effect["effect_id"],
                        "ordinal": str(effect["first_conflict_event_seq"]),
                        "conflict_code": effect["conflict_code"],
                        "expected_hash": parsed.get("expected_hash"),
                        "observed_hash": parsed.get("observed_hash"),
                    },
                )
        validated_effect = ValidatedEffect.from_row(effect)
        assert isinstance(validated_effect, ValidatedEffect)
        return validated_effect, tuple(action_values)

    def _validate_effect_predecessor(
        self,
        effect: ValidatedEffect,
        *,
        member: Mapping[str, Any],
        operations: dict[str, ValidatedOperation],
    ) -> ValidatedEffect | None:
        if effect["predecessor_effect_id"] is None:
            return None
        predecessor_row = self._connection.execute(
            "SELECT * FROM registration_effect WHERE effect_id=?",
            (effect["predecessor_effect_id"],),
        ).fetchone()
        if predecessor_row is None:
            self._semantic_failure("effect predecessor is missing")
        predecessor, _ignored = self._validate_effect_row(
            predecessor_row,
            member=member,
            operations=operations,
            include_actions=False,
        )
        created_operation = operations.get(effect["created_operation_id"])
        superseded_predecessor = (
            predecessor["superseded_by_effect_id"] == effect["effect_id"]
            and predecessor["outcome_kind"] == "SUPERSEDED"
        )
        staged_or_handoff_predecessor = (
            created_operation is not None
            and created_operation["operation_kind"]
            in {"SET_PENDING", "HANDOFF_RESOLVED"}
            and created_operation["target_effect_id"]
            == predecessor["effect_id"]
            and created_operation["target_successor_effect_id"]
            == effect["effect_id"]
            and predecessor["outcome_kind"]
            in {None, "SUCCESS", "LOGICAL_CONFLICT"}
            and predecessor["superseded_by_effect_id"] is None
        )
        if not (
            superseded_predecessor or staged_or_handoff_predecessor
        ):
            self._semantic_failure("effect predecessor relationship mismatch")
        if superseded_predecessor:
            transition_operation = operations.get(
                predecessor["outcome_operation_id"]
            )
            if transition_operation is None:
                self._semantic_failure(
                    "superseded transition operation is missing"
                )
            self._validate_successor_transition(
                predecessor=predecessor,
                successor=effect,
                operation=transition_operation,
            )
        elif (
            created_operation is not None
            and created_operation["operation_kind"] == "HANDOFF_RESOLVED"
        ):
            self._validate_successor_transition(
                predecessor=predecessor,
                successor=effect,
                operation=created_operation,
            )
        return predecessor

    def _validate_episode_row(
        self,
        row: Mapping[str, Any],
        *,
        member_id: str,
        operations: dict[str, ValidatedOperation],
    ) -> ValidatedEpisode:
        episode = dict(row)
        if (
            registration_hashes.derive("episode_envelope_hash", episode)
            != episode["envelope_hash"]
            or episode["workspace_root_count"] != 1
            or episode["member_id"] != member_id
        ):
            self._semantic_failure("episode envelope mismatch")
        episode_operation = self._validate_write_backlink(
            episode,
            operation_id_field="write_operation_id",
            operation_seq_field="write_operation_seq",
            operation_hash_field="write_operation_hash",
            target_hash_field="target_episode_hash",
            target_hash=episode["envelope_hash"],
            operations=operations,
            target_member_id=member_id,
            operation_kinds=frozenset({"BIND_EPISODE"}),
        )
        episode_protocol_row = self._connection.execute(
            "SELECT * FROM registration_protocol_epoch WHERE protocol_seq=?",
            (episode_operation["protocol_seq"],),
        ).fetchone()
        if episode_protocol_row is None:
            self._semantic_failure("episode protocol is missing")
        episode_protocol = self._validate_protocol_row(
            episode_protocol_row, operations
        )
        expected_episode_id = registration_hashes.deterministic_id(
            "awa-reg-episode-v1",
            episode["conversation_id"],
            episode["generation_id"],
            episode["source_contract"],
            episode["source_event"],
            str(episode["protocol_generation"]),
            member_id,
            episode["workspace_roots_hash"],
            episode["tool_inventory_hash"],
            episode["hook_projection_hash"],
        )
        if (
            episode["episode_id"] != expected_episode_id
            or episode_operation["target_episode_id"]
            != episode["episode_id"]
            or episode["protocol_generation"]
            != episode_protocol["protocol_generation"]
            or episode["tool_inventory_hash"]
            != episode_protocol["tool_inventory_hash"]
            or episode["hook_projection_hash"]
            != episode_protocol["hook_projection_hash"]
        ):
            self._semantic_failure("episode authority companion mismatch")
        validated = ValidatedEpisode.from_row(episode)
        assert isinstance(validated, ValidatedEpisode)
        return validated

    def _validate_phase_status_relationship(
        self,
        *,
        protocol: Mapping[str, Any],
        member: Mapping[str, Any],
        status: Mapping[str, Any],
        effect: Mapping[str, Any],
        status_write: Mapping[str, Any],
    ) -> None:
        schedule_fields = (
            "schedule_boot_id",
            "observed_now_mono_ns",
            "next_due_mono_ns",
            "due_since_mono_ns",
            "attempt_count",
            "backoff_ns",
        )
        scheduled = all(status[field] is not None for field in schedule_fields)
        unscheduled = all(status[field] is None for field in schedule_fields)
        if not scheduled and not unscheduled:
            self._semantic_failure("status schedule tuple is partial")
        executor_present = status["executor_token_hash"] is not None
        if executor_present:
            allowed_generation = (
                status["executor_generation"] == member["helper_generation"]
                and (
                    (
                        protocol["mode"] == "WRITABLE"
                        and member["helper_generation"]
                        == protocol["protocol_generation"]
                    )
                    or (
                        protocol["mode"] == "DRAINING"
                        and member["helper_generation"]
                        in {
                            protocol["protocol_generation"],
                            protocol["staged_generation"],
                        }
                    )
                )
            )
            if (
                status["executor_boot_id"] is None
                or not allowed_generation
                or status_write["operation_kind"]
                not in {"OPEN_EFFECT", "REACQUIRE_EFFECT", "ADOPT_EFFECT"}
                or status_write["target_executor_token_hash"]
                != status["executor_token_hash"]
                or status_write["sample_boot_id"]
                != status["executor_boot_id"]
            ):
                self._semantic_failure("executor status authority mismatch")
        elif (
            status["executor_boot_id"] is not None
            or status["executor_generation"] is not None
        ):
            self._semantic_failure("cleared executor status is partial")
        if effect["request_basis_hash"] != member["current_basis_hash"]:
            self._semantic_failure("member/effect basis relationship mismatch")
        if member["phase"] == "REQUESTED":
            expected_reason = {
                "CLEAN_ELIGIBLE": "REGISTRATION_REQUIRED",
                "BLOCKED_DIRTY": "DIRTY_UNSUPPORTED",
                "BLOCKED_OPERATION": "GIT_OPERATION_UNSUPPORTED",
            }[effect["request_kind"]]
            if (
                member["pending_effect_id"] is not None
                or effect["outcome_kind"] is not None
                or executor_present
                or status["reason_code"] != expected_reason
                or (
                    effect["request_kind"] == "CLEAN_ELIGIBLE"
                    and (
                        not scheduled
                        or status["help_due"] not in {0, 1}
                        or status["blocked_basis_fingerprint"] is not None
                    )
                )
                or (
                    effect["request_kind"] != "CLEAN_ELIGIBLE"
                    and (
                        not unscheduled
                        or status["help_due"] != 0
                        or status["blocked_basis_fingerprint"] is None
                    )
                )
            ):
                self._semantic_failure("requested phase/status mismatch")
            return
        if member["phase"] == "EFFECT_IN_FLIGHT":
            if (
                effect["request_kind"] != "CLEAN_ELIGIBLE"
                or effect["outcome_kind"] is not None
                or status["blocked_basis_fingerprint"] is not None
                or (
                    executor_present
                    and (
                        not unscheduled
                        or status["help_due"] != 0
                        or status["reason_code"] != "EFFECT_IN_FLIGHT"
                    )
                )
                or (
                    not executor_present
                    and (
                        not scheduled
                        or status["help_due"] != 1
                        or status["reason_code"]
                        not in {
                            "EFFECT_IN_FLIGHT",
                            "RESOLVER_UNAVAILABLE",
                        }
                    )
                )
            ):
                self._semantic_failure("in-flight phase/status mismatch")
            return
        if member["phase"] != "RESOLVED":
            self._semantic_failure("unknown member phase")
        expected_reason = (
            None
            if effect["outcome_kind"] == "SUCCESS"
            else "EFFECT_CONFLICT"
        )
        if (
            executor_present
            or status["blocked_basis_fingerprint"] is not None
            or (
                member["pending_effect_id"] is not None
                and (
                    not scheduled
                    or status["help_due"] != 1
                    or status["reason_code"] != "REGISTRATION_REQUIRED"
                )
            )
            or (
                member["pending_effect_id"] is None
                and (
                    not unscheduled
                    or status["help_due"] != 0
                    or status["reason_code"] != expected_reason
                    or (
                        effect["outcome_kind"] == "SUCCESS"
                        and (
                            status["unavailable_count"] != 0
                            or status["yield_count"] != 0
                        )
                    )
                )
            )
        ):
            self._semantic_failure("resolved phase/status mismatch")

    def _validate_semantic_closure_tx(
        self, member_id: str, *, episode_id: str | None
    ) -> SelectedAuthority | None:
        operations: dict[str, ValidatedOperation] = {}
        protocol_row = self._connection.execute(
            "SELECT * FROM registration_protocol_epoch "
            "ORDER BY protocol_seq DESC LIMIT 1"
        ).fetchone()
        if protocol_row is None:
            return None
        protocol = self._validate_protocol_row(protocol_row, operations)
        member_row = self._connection.execute(
            "SELECT * FROM registration_member WHERE member_id=?",
            (member_id,),
        ).fetchone()
        status_row = self._connection.execute(
            "SELECT * FROM registration_runtime_status WHERE member_id=?",
            (member_id,),
        ).fetchone()
        if member_row is None and status_row is None:
            return None
        if member_row is None or status_row is None:
            self._semantic_failure("member/status cardinality mismatch")
        member = dict(member_row)
        status = dict(status_row)
        if (
            registration_hashes.derive("member_tuple_hash", member)
            != member["member_tuple_hash"]
        ):
            self._semantic_failure("member tuple hash mismatch")
        if registration_hashes.derive("status_hash", status) != status["status_hash"]:
            self._semantic_failure("status hash mismatch")
        member_write = self._validate_write_backlink(
            member,
            operation_id_field="write_operation_id",
            operation_seq_field="write_operation_seq",
            operation_hash_field="write_operation_hash",
            target_hash_field="target_member_tuple_hash",
            target_hash=member["member_tuple_hash"],
            operations=operations,
            target_member_id=member_id,
            operation_kinds=_MEMBER_WRITE_KINDS,
        )
        status_write = self._validate_write_backlink(
            status,
            operation_id_field="write_operation_id",
            operation_seq_field="write_operation_seq",
            operation_hash_field="write_operation_hash",
            target_hash_field="target_status_hash",
            target_hash=status["status_hash"],
            operations=operations,
            target_member_id=member_id,
            operation_kinds=_STATUS_WRITE_KINDS,
        )
        if (
            member["runtime_subject_key"] != status["subject_key"]
            or status["member_id"] != member_id
            or status["member_epoch"] != member["member_epoch"]
            or status["current_effect_id"] != member["current_effect_id"]
        ):
            self._semantic_failure("member/status relationship mismatch")
        member_epochs = {
            value
            for value in (
                member_write["target_member_epoch"],
                member_write["target_successor_member_epoch"],
            )
            if value is not None
        }
        member_bases = {
            value
            for value in (
                member_write["target_basis_hash"],
                member_write["target_successor_basis_hash"],
            )
            if value is not None
        }
        status_effects = {
            value
            for value in (
                status_write["target_effect_id"],
                status_write["target_successor_effect_id"],
                status_write["lineage_effect_id"],
            )
            if value is not None
        }
        if (
            member["member_epoch"] not in member_epochs
            or member["current_basis_hash"] not in member_bases
            or status["current_effect_id"] not in status_effects
            or status_write["target_subject_key"] != status["subject_key"]
        ):
            self._semantic_failure("member/status operation companion mismatch")
        effect_row = self._connection.execute(
            "SELECT * FROM registration_effect WHERE effect_id=?",
            (member["current_effect_id"],),
        ).fetchone()
        if effect_row is None:
            self._semantic_failure("selected current effect is missing")
        effect, actions = self._validate_effect_row(
            effect_row,
            member=member,
            operations=operations,
            include_actions=True,
        )
        if (
            effect["member_id"] != member_id
            or effect["member_epoch"] != member["member_epoch"]
        ):
            self._semantic_failure("member/effect relationship mismatch")
        if member_write["operation_kind"] == "HANDOFF_RESOLVED":
            handoff_predecessor_row = self._connection.execute(
                "SELECT * FROM registration_effect WHERE effect_id=?",
                (member_write["target_effect_id"],),
            ).fetchone()
            if handoff_predecessor_row is None:
                self._semantic_failure(
                    "handoff predecessor effect is missing"
                )
            handoff_predecessor, _ignored = self._validate_effect_row(
                handoff_predecessor_row,
                member=member,
                operations=operations,
                include_actions=False,
            )
            self._validate_successor_transition(
                predecessor=handoff_predecessor,
                successor=effect,
                operation=member_write,
            )
        if member["phase"] == "RESOLVED":
            if (
                effect["outcome_kind"] not in {"SUCCESS", "LOGICAL_CONFLICT"}
                or member["current_outcome_kind"] != effect["outcome_kind"]
                or member["current_completion_hash"] != effect["completion_hash"]
                or member["current_proof_hash"] != effect["proof_hash"]
                or member["current_certificate_hash"] != effect["certificate_hash"]
                or member["current_conflict_hash"] != effect["conflict_hash"]
            ):
                self._semantic_failure("resolved member closure mismatch")
        elif effect["outcome_kind"] is not None:
            self._semantic_failure("non-resolved member has closed current effect")
        self._validate_phase_status_relationship(
            protocol=protocol,
            member=member,
            status=status,
            effect=effect,
            status_write=status_write,
        )

        pending: ValidatedEffect | None = None
        if member["pending_effect_id"] is not None:
            pending_row = self._connection.execute(
                "SELECT * FROM registration_effect WHERE effect_id=?",
                (member["pending_effect_id"],),
            ).fetchone()
            if pending_row is None:
                self._semantic_failure("pending effect is missing")
            pending, _ignored = self._validate_effect_row(
                pending_row,
                member=member,
                operations=operations,
                include_actions=False,
            )
            if (
                pending["member_id"] != member_id
                or pending["member_epoch"] != member["pending_member_epoch"]
                or pending["request_basis_hash"] != member["pending_basis_hash"]
                or pending["request_tuple_hash"]
                != member["pending_effect_tuple_hash"]
                or pending["outcome_kind"] is not None
            ):
                self._semantic_failure("pending effect relationship mismatch")
            self._validate_effect_predecessor(
                pending,
                member=member,
                operations=operations,
            )

        predecessor = self._validate_effect_predecessor(
            effect,
            member=member,
            operations=operations,
        )

        successor: ValidatedEffect | None = None
        if effect["superseded_by_effect_id"] is not None:
            successor_row = self._connection.execute(
                "SELECT * FROM registration_effect WHERE effect_id=?",
                (effect["superseded_by_effect_id"],),
            ).fetchone()
            if successor_row is None:
                self._semantic_failure("effect successor is missing")
            successor, _ignored = self._validate_effect_row(
                successor_row,
                member=member,
                operations=operations,
                include_actions=False,
            )
            if successor["predecessor_effect_id"] != effect["effect_id"]:
                self._semantic_failure("effect successor relationship mismatch")

        if member_write["operation_kind"] == "ADOPT_EFFECT":
            staged = self._connection.execute(
                "SELECT * FROM registration_protocol_epoch WHERE protocol_seq=?",
                (member_write["protocol_seq"],),
            ).fetchone()
            if staged is None:
                self._semantic_failure("adoption staged protocol missing")
            staged_value = self._validate_protocol_row(staged, operations)
            lineage = self._connection.execute(
                "SELECT * FROM registration_effect WHERE effect_id=?",
                (member_write["lineage_effect_id"],),
            ).fetchone()
            if (
                lineage is None
                or member_write["target_staged_epoch_hash"]
                != staged_value["staged_epoch_hash"]
                or member_write["lineage_effect_id"] != effect["effect_id"]
                or member_write["target_action_plan_hash"]
                != effect["action_plan_hash"]
                or member_write["target_member_tuple_hash"]
                != member["member_tuple_hash"]
                or (
                    status["write_operation_id"]
                    == member_write["operation_id"]
                    and member_write["target_status_hash"]
                    != status["status_hash"]
                )
                or member["helper_generation"]
                != staged_value["staged_generation"]
                or (
                    status["write_operation_id"]
                    == member_write["operation_id"]
                    and status["executor_token_hash"] is not None
                    and (
                        status["executor_generation"]
                        != staged_value["staged_generation"]
                        or member_write["target_executor_token_hash"]
                        != status["executor_token_hash"]
                    )
                )
                or effect["required_protocol_generation"]
                != staged_value["protocol_generation"]
                or effect["required_runtime_capability_hash"]
                != staged_value["runtime_capability_hash"]
            ):
                self._semantic_failure("adoption lineage mismatch")

        episodes: list[ValidatedEpisode] = []
        if episode_id is not None:
            episode_rows = self._connection.execute(
                "SELECT * FROM registration_episode "
                "WHERE member_id=? AND episode_id=?",
                (member_id, episode_id),
            ).fetchall()
            if len(episode_rows) != 1:
                self._semantic_failure("selected episode cardinality mismatch")
            episodes.append(
                self._validate_episode_row(
                    episode_rows[0],
                    member_id=member_id,
                    operations=operations,
                )
            )

        validated_member = ValidatedMember.from_row(member)
        validated_status = ValidatedStatus.from_row(status)
        assert isinstance(validated_member, ValidatedMember)
        assert isinstance(validated_status, ValidatedStatus)
        operation_values = tuple(
            operations[key] for key in sorted(operations, key=lambda value: value.encode())
        )
        token = (
            protocol["protocol_seq"],
            protocol["protocol_hash"],
            tuple((item["episode_id"], item["envelope_hash"]) for item in episodes),
            member["write_operation_seq"],
            member["member_tuple_hash"],
            status["status_version"],
            status["status_hash"],
            effect["outcome_operation_seq"],
            effect["outcome_tuple_hash"],
            effect["ledger_head_hash"],
            pending["request_tuple_hash"] if pending is not None else None,
            predecessor["outcome_tuple_hash"] if predecessor is not None else None,
            successor["request_tuple_hash"] if successor is not None else None,
            tuple(item["operation_envelope_hash"] for item in operation_values),
        )
        return SelectedAuthority(
            protocol=protocol,
            member=validated_member,
            status=validated_status,
            effect=effect,
            actions=actions,
            episodes=tuple(episodes),
            revision_token=token,
            pending_effect=pending,
            predecessor_effect=predecessor,
            successor_effect=successor,
            operations=operation_values,
        )

    def current_protocol(self) -> ValidatedProtocol | None:
        row = self._connection.execute(
            "SELECT * FROM registration_protocol_epoch "
            "ORDER BY protocol_seq DESC LIMIT 1"
        ).fetchone()
        return self._validate_protocol_row(row) if row else None

    def validate_semantic_closure(
        self, member_id: str, *, episode_id: str | None = None
    ) -> SelectedAuthority | None:
        _require_hash(member_id, "member_id")
        if episode_id is not None:
            _require_hash(episode_id, "episode_id")
        with self._read_scope():
            self._connection.execute("BEGIN")
            try:
                result = self._validate_semantic_closure_tx(
                    member_id, episode_id=episode_id
                )
                self._connection.execute("COMMIT")
                return result
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def read_selected_authority(
        self, member_id: str, *, episode_id: str | None = None
    ) -> SelectedAuthority | None:
        return self.validate_semantic_closure(member_id, episode_id=episode_id)

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

    def _selector_universes_tx(
        self,
        *,
        boot_id: str,
        now_mono_ns: int | None,
    ) -> tuple[
        ValidatedProtocol,
        tuple[str, ...],
        tuple[str, ...],
        tuple[str, ...],
        dict[str, SelectedAuthority],
    ]:
        protocol_row = self._connection.execute(
            "SELECT * FROM registration_protocol_epoch "
            "ORDER BY protocol_seq DESC LIMIT 1"
        ).fetchone()
        if protocol_row is None:
            raise StoreUnavailable(
                "candidate selector has no current protocol"
            )
        protocol = self._validate_protocol_row(protocol_row)
        same_boot_ids = tuple(
            row["member_id"]
            for row in self._connection.execute(
                "SELECT s.member_id "
                "FROM registration_runtime_status s "
                "WHERE s.executor_token_hash IS NOT NULL "
                "AND s.executor_generation IS NOT NULL "
                "AND s.executor_boot_id=? "
                "ORDER BY s.member_id",
                (boot_id,),
            ).fetchall()
        )
        due_ids: tuple[str, ...] = ()
        reboot_ids: tuple[str, ...] = ()
        if now_mono_ns is not None:
            due_ids = tuple(
                row["member_id"]
                for row in self._connection.execute(
                    "SELECT s.member_id "
                    "FROM registration_runtime_status s "
                    "WHERE s.schedule_boot_id=? "
                    "AND s.next_due_mono_ns<=? "
                    "AND s.executor_token_hash IS NULL "
                    "ORDER BY s.member_id",
                    (boot_id, now_mono_ns),
                ).fetchall()
            )
            reboot_ids = tuple(
                row["member_id"]
                for row in self._connection.execute(
                    "SELECT s.member_id "
                    "FROM registration_runtime_status s "
                    "WHERE (s.executor_token_hash IS NOT NULL "
                    "AND s.executor_boot_id<>?) "
                    "OR (s.executor_token_hash IS NULL "
                    "AND s.schedule_boot_id IS NOT NULL "
                    "AND s.schedule_boot_id<>?) "
                    "ORDER BY s.member_id",
                    (boot_id, boot_id),
                ).fetchall()
            )
        authorities: dict[str, SelectedAuthority] = {}
        for member_id in sorted(
            set(same_boot_ids) | set(due_ids) | set(reboot_ids)
        ):
            authority = self._validate_semantic_closure_tx(
                member_id, episode_id=None
            )
            if authority is None:
                self._semantic_failure(
                    "candidate semantic closure is absent"
                )
            assert authority is not None
            if (
                authority.protocol["protocol_seq"]
                != protocol["protocol_seq"]
                or authority.protocol["protocol_hash"]
                != protocol["protocol_hash"]
            ):
                self._semantic_failure(
                    "candidate protocol snapshot changed"
                )
            authorities[member_id] = authority
        return (
            protocol,
            same_boot_ids,
            due_ids,
            reboot_ids,
            authorities,
        )

    @staticmethod
    def _same_boot_value(
        authority: SelectedAuthority, *, boot_id: str
    ) -> SameBootCandidate:
        member = authority.member
        effect = authority.effect
        status = authority.status
        if (
            member["phase"] != "EFFECT_IN_FLIGHT"
            or effect["outcome_kind"] is not None
            or status["executor_token_hash"] is None
            or status["executor_generation"] is None
            or status["executor_boot_id"] != boot_id
        ):
            raise SemanticClosureError(
                "same-boot candidate changed inside the snapshot"
            )
        return SameBootCandidate(
            member_id=member["member_id"],
            status_hash=status["status_hash"],
            executor_token_hash=status["executor_token_hash"],
            executor_generation=status["executor_generation"],
        )

    @staticmethod
    def _due_value(
        authority: SelectedAuthority,
        *,
        boot_id: str,
        now_mono_ns: int,
    ) -> DueCandidate:
        member = authority.member
        effect = authority.effect
        status = authority.status
        if (
            status["schedule_boot_id"] != boot_id
            or status["next_due_mono_ns"] is None
            or status["next_due_mono_ns"] > now_mono_ns
            or status["executor_token_hash"] is not None
        ):
            raise SemanticClosureError(
                "due candidate changed inside the snapshot"
            )
        return DueCandidate(
            member_id=member["member_id"],
            member_epoch=member["member_epoch"],
            phase=member["phase"],
            effect_id=member["current_effect_id"],
            member_tuple_hash=member["member_tuple_hash"],
            effect_tuple_hash=effect["request_tuple_hash"],
            status_hash=status["status_hash"],
            current_basis_hash=member["current_basis_hash"],
            pending_basis_hash=member["pending_basis_hash"],
            due_since_mono_ns=status["due_since_mono_ns"],
            observed_now_mono_ns=status["observed_now_mono_ns"],
        )

    @staticmethod
    def _reboot_value(
        authority: SelectedAuthority, *, boot_id: str
    ) -> RebootCandidate:
        member = authority.member
        status = authority.status
        stored_boot_id = (
            status["executor_boot_id"]
            if status["executor_token_hash"] is not None
            else status["schedule_boot_id"]
        )
        if stored_boot_id is None or stored_boot_id == boot_id:
            raise SemanticClosureError(
                "reboot candidate changed inside the snapshot"
            )
        return RebootCandidate(
            member_id=member["member_id"],
            phase=member["phase"],
            effect_id=member["current_effect_id"],
            status_hash=status["status_hash"],
            stored_boot_id=stored_boot_id,
        )

    def _rollback_selector_tx(self, selector: str) -> None:
        if not self._connection.in_transaction:
            return
        try:
            self._connection.execute("ROLLBACK")
        except sqlite3.Error as error:
            raise StoreUnavailable(
                f"{selector} rollback is unavailable"
            ) from error

    def select_same_boot_snapshot(
        self, *, boot_id: str
    ) -> SameBootSnapshot:
        if not isinstance(boot_id, str) or not boot_id:
            raise ValueError("boot_id is required")
        with self._read_scope():
            try:
                self._connection.execute("BEGIN")
                (
                    protocol,
                    same_boot_ids,
                    _due_ids,
                    _reboot_ids,
                    authorities,
                ) = self._selector_universes_tx(
                    boot_id=boot_id,
                    now_mono_ns=None,
                )
                result = SameBootSnapshot(
                    boot_id=boot_id,
                    protocol_seq=protocol["protocol_seq"],
                    protocol_hash=protocol["protocol_hash"],
                    candidates=tuple(
                        self._same_boot_value(
                            authorities[member_id],
                            boot_id=boot_id,
                        )
                        for member_id in same_boot_ids
                    ),
                )
                self._connection.execute("COMMIT")
                return result
            except StoreUnavailable:
                self._rollback_selector_tx("same-boot snapshot")
                raise
            except sqlite3.Error as error:
                self._rollback_selector_tx("same-boot snapshot")
                raise StoreUnavailable(
                    "same-boot snapshot is unavailable"
                ) from error
            except Exception as error:
                self._rollback_selector_tx("same-boot snapshot")
                raise StoreUnavailable(
                    "same-boot snapshot is malformed"
                ) from error

    def select_r1_scope(
        self,
        authorized_member_id: str,
        boot_id: str,
        now_mono_ns: int,
    ) -> R1ScopeSelection:
        _require_hash(authorized_member_id, "authorized_member_id")
        if (
            not isinstance(boot_id, str)
            or not boot_id
            or type(now_mono_ns) is not int
            or now_mono_ns < 0
        ):
            raise ValueError("invalid R1 scope selector")
        with self._read_scope():
            try:
                self._connection.execute("BEGIN")
                (
                    _protocol,
                    same_boot_ids,
                    due_ids,
                    reboot_ids,
                    authorities,
                ) = self._selector_universes_tx(
                    boot_id=boot_id,
                    now_mono_ns=now_mono_ns,
                )
                authorized_same_boot = (
                    self._same_boot_value(
                        authorities[authorized_member_id],
                        boot_id=boot_id,
                    )
                    if authorized_member_id in same_boot_ids
                    else None
                )
                authorized_due = (
                    self._due_value(
                        authorities[authorized_member_id],
                        boot_id=boot_id,
                        now_mono_ns=now_mono_ns,
                    )
                    if authorized_member_id in due_ids
                    else None
                )
                authorized_reboot = (
                    self._reboot_value(
                        authorities[authorized_member_id],
                        boot_id=boot_id,
                    )
                    if authorized_member_id in reboot_ids
                    else None
                )
                result = R1ScopeSelection(
                    authorized_same_boot=authorized_same_boot,
                    authorized_due=authorized_due,
                    authorized_reboot=authorized_reboot,
                    outside_scope_same_boot=any(
                        member_id != authorized_member_id
                        for member_id in same_boot_ids
                    ),
                    outside_scope_due=any(
                        member_id != authorized_member_id
                        for member_id in due_ids
                    ),
                    outside_scope_reboot=any(
                        member_id != authorized_member_id
                        for member_id in reboot_ids
                    ),
                )
                self._connection.execute("COMMIT")
                return result
            except StoreUnavailable:
                self._rollback_selector_tx("R1 scope selection")
                raise
            except sqlite3.Error as error:
                self._rollback_selector_tx("R1 scope selection")
                raise StoreUnavailable(
                    "R1 scope selection is unavailable"
                ) from error
            except Exception as error:
                self._rollback_selector_tx("R1 scope selection")
                raise StoreUnavailable(
                    "R1 scope selection is malformed"
                ) from error

    def list_due_candidates(
        self, *, boot_id: str, now_mono_ns: int, limit: int = 8
    ) -> tuple[DueCandidate, ...]:
        if (
            not isinstance(boot_id, str)
            or not boot_id
            or type(now_mono_ns) is not int
            or now_mono_ns < 0
            or type(limit) is not int
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

    def _read_resolution(
        self,
        resolver: Callable[[], str],
        *,
        semantic_result: str = "UNAVAILABLE",
    ) -> str:
        with self._read_scope():
            self._connection.execute("BEGIN")
            try:
                result = resolver()
                self._connection.execute("COMMIT")
                return result
            except SemanticClosureError:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                return semantic_result
            except sqlite3.Error:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                return "UNAVAILABLE"
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def resolve_operation(
        self,
        operation_id: str,
        *,
        expected_revision: int | None = None,
        expected_protocol_hash: str | None | object = _UNSPECIFIED,
    ) -> str:
        """Classify an ambiguous commit from one consistent durable snapshot."""
        _require_hash(operation_id, "operation_id")
        if expected_revision is not None:
            _require_int(expected_revision, "expected_revision", minimum=0)
        if (
            expected_protocol_hash is not _UNSPECIFIED
            and expected_protocol_hash is not None
        ):
            _require_hash(expected_protocol_hash, "expected_protocol_hash")
        with self._read_scope():
            self._connection.execute("BEGIN")
            try:
                result = self._resolve_operation_tx(operation_id)
                if result == "ABSENT":
                    if (
                        expected_revision is None
                        or expected_protocol_hash is _UNSPECIFIED
                    ):
                        result = "UNAVAILABLE"
                    else:
                        revision = self.table_count(
                            "registration_operation_audit"
                        )
                        protocol = self._connection.execute(
                            "SELECT protocol_hash "
                            "FROM registration_protocol_epoch "
                            "ORDER BY protocol_seq DESC LIMIT 1"
                        ).fetchone()
                        observed_protocol = (
                            protocol["protocol_hash"]
                            if protocol is not None
                            else None
                        )
                        result = (
                            "ABSENT"
                            if revision == expected_revision
                            and observed_protocol == expected_protocol_hash
                            else "UNAVAILABLE"
                        )
                self._connection.execute("COMMIT")
                return result
            except SemanticClosureError:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                return "PARTIAL"
            except sqlite3.Error:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                return "UNAVAILABLE"
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def _resolve_operation_tx(self, operation_id: str) -> str:
        try:
            operation_row = self._connection.execute(
                "SELECT * FROM registration_operation_audit WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if operation_row is None:
                return "ABSENT"
            operations: dict[str, ValidatedOperation] = {}
            operation = self._validated_operation(operation_id, operations)
            authority: SelectedAuthority | None = None
            if operation["target_member_id"] is not None:
                authority = self._validate_semantic_closure_tx(
                    operation["target_member_id"], episode_id=None
                )
                if authority is None:
                    return "PARTIAL"
            else:
                protocol_row = self._connection.execute(
                    "SELECT * FROM registration_protocol_epoch "
                    "ORDER BY protocol_seq DESC LIMIT 1"
                ).fetchone()
                if protocol_row is not None:
                    self._validate_protocol_row(protocol_row, operations)
            checks: list[bool] = []
            if operation["target_protocol_hash"] is not None:
                protocol_row = self._connection.execute(
                    "SELECT * FROM registration_protocol_epoch "
                    "WHERE protocol_hash=?",
                    (operation["target_protocol_hash"],),
                ).fetchone()
                checks.append(protocol_row is not None)
                if protocol_row is not None:
                    self._validate_protocol_row(protocol_row, operations)
            if operation["target_member_tuple_hash"] is not None:
                checks.append(
                    authority is not None
                    and (
                        authority.member["member_tuple_hash"]
                        == operation["target_member_tuple_hash"]
                        or (
                            int(authority.member["write_operation_seq"])
                            > int(operation["operation_seq"])
                        )
                    )
                )
            if operation["target_status_hash"] is not None:
                checks.append(
                    authority is not None
                    and (
                        authority.status["status_hash"]
                        == operation["target_status_hash"]
                        or (
                            int(authority.status["write_operation_seq"])
                            > int(operation["operation_seq"])
                        )
                    )
                )

            validated_effects: dict[str, ValidatedEffect] = {}
            validated_actions: list[ValidatedAction] = []
            for effect_id in {
                operation["target_effect_id"],
                operation["target_successor_effect_id"],
                operation["lineage_effect_id"],
            } - {None}:
                effect_row = self._connection.execute(
                    "SELECT * FROM registration_effect WHERE effect_id=?",
                    (effect_id,),
                ).fetchone()
                if effect_row is None or authority is None:
                    checks.append(False)
                    continue
                effect, actions = self._validate_effect_row(
                    effect_row,
                    member=authority.member,
                    operations=operations,
                    include_actions=True,
                )
                validated_effects[effect_id] = effect
                validated_actions.extend(actions)
            if operation["target_effect_tuple_hash"] is not None:
                checks.append(
                    operation["target_effect_tuple_hash"]
                    in {
                        effect["request_tuple_hash"]
                        for effect in validated_effects.values()
                    }
                )
            if operation["target_effect_outcome_hash"] is not None:
                checks.append(
                    operation["target_effect_outcome_hash"]
                    in {
                        effect["outcome_tuple_hash"]
                        for effect in validated_effects.values()
                    }
                )
            if operation["target_action_plan_hash"] is not None:
                checks.append(
                    operation["target_action_plan_hash"]
                    in {
                        effect["action_plan_hash"]
                        for effect in validated_effects.values()
                    }
                )
            if operation["target_action_ledger_hash"] is not None:
                checks.append(
                    operation["target_action_ledger_hash"] == ZERO_HASH
                    or operation["target_action_ledger_hash"]
                    in {action["ledger_hash"] for action in validated_actions}
                )
            if operation["target_episode_hash"] is not None:
                episode_row = self._connection.execute(
                    "SELECT * FROM registration_episode WHERE episode_id=?",
                    (operation["target_episode_id"],),
                ).fetchone()
                checks.append(episode_row is not None)
                if episode_row is not None:
                    episode = self._validate_episode_row(
                        episode_row,
                        member_id=operation["target_member_id"],
                        operations=operations,
                    )
                    checks.append(
                        episode["envelope_hash"]
                        == operation["target_episode_hash"]
                    )
            return "COMMITTED" if all(checks) else "PARTIAL"
        except sqlite3.Error:
            return "UNAVAILABLE"

    def resolve_close(
        self, *, operation_id: str, member_id: str, effect_id: str
    ) -> str:
        for value, field in (
            (operation_id, "operation_id"),
            (member_id, "member_id"),
            (effect_id, "effect_id"),
        ):
            _require_hash(value, field)
        return self._read_resolution(
            lambda: self._resolve_close_tx(
                operation_id=operation_id,
                member_id=member_id,
                effect_id=effect_id,
            )
        )

    def _resolve_close_tx(
        self, *, operation_id: str, member_id: str, effect_id: str
    ) -> str:
        try:
            authority = self._validate_semantic_closure_tx(
                member_id, episode_id=None
            )
            if authority is None:
                return "UNAVAILABLE"
            effect_row = self._connection.execute(
                "SELECT * FROM registration_effect WHERE effect_id=?",
                (effect_id,),
            ).fetchone()
            if effect_row is None:
                return "UNAVAILABLE"
            operations: dict[str, ValidatedOperation] = {}
            effect, _actions = self._validate_effect_row(
                effect_row,
                member=authority.member,
                operations=operations,
                include_actions=True,
            )
            operation_row = self._connection.execute(
                "SELECT * FROM registration_operation_audit "
                "WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            operation = (
                self._validated_operation(operation_id, operations)
                if operation_row is not None
                else None
            )
            if (
                operation is not None
                and operation["target_member_id"] == member_id
                and operation["target_effect_id"] == effect_id
                and effect["outcome_operation_id"] == operation_id
            ):
                if effect["outcome_kind"] == "SUCCESS":
                    return "COMMITTED_SUCCESS"
                if effect["outcome_kind"] == "LOGICAL_CONFLICT":
                    return "COMMITTED_LOGICAL_CONFLICT"
            if (
                operation_row is None
                and (
                    member := self._connection.execute(
                        "SELECT * FROM registration_member WHERE member_id=?",
                        (member_id,),
                    ).fetchone()
                )
                is not None
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
        for value, field in (
            (operation_id, "operation_id"),
            (member_id, "member_id"),
            (effect_id, "effect_id"),
            (old_status_hash, "old_status_hash"),
        ):
            _require_hash(value, field)
        return self._read_resolution(
            lambda: self._resolve_reacquire_tx(
                operation_id=operation_id,
                member_id=member_id,
                effect_id=effect_id,
                old_status_hash=old_status_hash,
            ),
            semantic_result="PARTIAL",
        )

    def _resolve_reacquire_tx(
        self,
        *,
        operation_id: str,
        member_id: str,
        effect_id: str,
        old_status_hash: str,
    ) -> str:
        try:
            authority = self._validate_semantic_closure_tx(
                member_id, episode_id=None
            )
            if authority is None:
                return "UNAVAILABLE"
            operation_row = self._connection.execute(
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
            effect_row = self._connection.execute(
                "SELECT * FROM registration_effect WHERE effect_id=?",
                (effect_id,),
            ).fetchone()
            effect: ValidatedEffect | None = None
            operation: ValidatedOperation | None = None
            if effect_row is not None:
                operations: dict[str, ValidatedOperation] = {}
                effect, _actions = self._validate_effect_row(
                    effect_row,
                    member=authority.member,
                    operations=operations,
                    include_actions=False,
                )
                if operation_row is not None:
                    operation = self._validated_operation(
                        operation_id, operations
                    )
            protocol = self.current_protocol()
            if (
                operation is not None
                and member is not None
                and status is not None
                and effect is not None
                and protocol is not None
                and operation["operation_kind"] == "REACQUIRE_EFFECT"
                and operation["target_effect_tuple_hash"]
                == effect["request_tuple_hash"]
                and self._resolve_operation_tx(operation_id) == "COMMITTED"
            ):
                return "COMMITTED"
            if (
                operation_row is None
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
            if operation_row is not None:
                return "PARTIAL"
            return "UNAVAILABLE"
        except sqlite3.Error:
            return "UNAVAILABLE"

    def resolve_adoption(
        self,
        *,
        operation_id: str,
        member_id: str,
        expected_member_hash: str,
        expected_effect_hash: str,
        expected_status_hash: str,
        expected_protocol_hash: str,
        expected_staged_epoch_hash: str,
    ) -> str:
        for value, field in (
            (operation_id, "operation_id"),
            (member_id, "member_id"),
            (expected_member_hash, "expected_member_hash"),
            (expected_effect_hash, "expected_effect_hash"),
            (expected_status_hash, "expected_status_hash"),
            (expected_protocol_hash, "expected_protocol_hash"),
            (expected_staged_epoch_hash, "expected_staged_epoch_hash"),
        ):
            _require_hash(value, field)
        return self._read_resolution(
            lambda: self._resolve_adoption_tx(
                operation_id=operation_id,
                member_id=member_id,
                expected_member_hash=expected_member_hash,
                expected_effect_hash=expected_effect_hash,
                expected_status_hash=expected_status_hash,
                expected_protocol_hash=expected_protocol_hash,
                expected_staged_epoch_hash=expected_staged_epoch_hash,
            ),
            semantic_result="PARTIAL",
        )

    def _resolve_adoption_tx(
        self,
        *,
        operation_id: str,
        member_id: str,
        expected_member_hash: str,
        expected_effect_hash: str,
        expected_status_hash: str,
        expected_protocol_hash: str,
        expected_staged_epoch_hash: str,
    ) -> str:
        try:
            authority = self._validate_semantic_closure_tx(
                member_id, episode_id=None
            )
            if authority is None:
                return "UNAVAILABLE"
            operation = self._connection.execute(
                "SELECT * FROM registration_operation_audit "
                "WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if operation is None:
                return (
                    "ABSENT"
                    if (
                        authority.member["member_tuple_hash"]
                        == expected_member_hash
                        and authority.effect["request_tuple_hash"]
                        == expected_effect_hash
                        and authority.status["status_hash"]
                        == expected_status_hash
                        and authority.protocol["protocol_hash"]
                        == expected_protocol_hash
                        and authority.protocol["staged_epoch_hash"]
                        == expected_staged_epoch_hash
                    )
                    else "UNAVAILABLE"
                )
            if (
                operation["operation_kind"] == "ADOPT_EFFECT"
                and operation["target_member_id"] == member_id
                and self._resolve_operation_tx(operation_id) == "COMMITTED"
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
        for value, field in (
            (operation_id, "operation_id"),
            (member_id, "member_id"),
            (expected_member_hash, "expected_member_hash"),
            (target_member_hash, "target_member_hash"),
        ):
            _require_hash(value, field)
        return self._read_resolution(
            lambda: self._resolve_successor_tx(
                operation_id=operation_id,
                member_id=member_id,
                expected_member_hash=expected_member_hash,
                target_member_hash=target_member_hash,
            )
        )

    def _resolve_successor_tx(
        self,
        *,
        operation_id: str,
        member_id: str,
        expected_member_hash: str,
        target_member_hash: str,
    ) -> str:
        try:
            authority = self._validate_semantic_closure_tx(
                member_id, episode_id=None
            )
            if authority is None:
                return "UNAVAILABLE"
            operation = self._connection.execute(
                "SELECT * FROM registration_operation_audit "
                "WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            member = authority.member
            if (
                operation is not None
                and operation["target_member_tuple_hash"]
                == target_member_hash
                and self._resolve_operation_tx(operation_id) == "COMMITTED"
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
