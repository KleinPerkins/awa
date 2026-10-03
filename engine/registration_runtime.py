"""Body B registration orchestration, replay, reboot, and fair retry."""

from __future__ import annotations

import hashlib
import multiprocessing
import os
import secrets
import sqlite3
import stat
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Protocol

from . import (
    lifecycle,
    native_entry,
    registration_admission,
    registration_hashes,
    registration_jcs,
    registration_lock,
    registration_store,
)


ACTION_KINDS = (
    "PUBLISH_EFFECT_PROOF",
    "CONVERGE_LEGACY_LEASE",
    "CONVERGE_LEGACY_LIFECYCLE",
    "COLLECT_FINAL_BASIS",
)
TICK_INTERVAL_NS = 15_000_000_000
TICK_LANES = 8
OPEN_SLICE_SECONDS = 0.125
HELPER_DEADLINE_SECONDS = 2.0
SERVICE_BUDGET_SECONDS = 5.0
SAME_BOOT_SNAPSHOT_SCHEMA = "awa-registration-same-boot-snapshot/v1"
SAME_BOOT_CURSOR_SCHEMA = "awa-registration-same-boot-cursor/v1"
SAME_BOOT_OUTCOMES = frozenset(
    {
        "BUSY_LIVE",
        "CLEARED",
        "RECOVERED",
        "NO_LONGER_CANDIDATE",
    }
)


def _hex64(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _domain_jcs_hash(domain: str, value: object) -> str:
    return hashlib.sha256(
        domain.encode("ascii")
        + b"\0"
        + registration_jcs.canonical_bytes(
            value, enforce_privacy=False
        )
    ).hexdigest()


class RecoveryContainmentUnavailable(RuntimeError):
    reason = "CONTAINMENT_UNAVAILABLE"

    def __init__(
        self, evidence: registration_store.RecoveryReserveExhausted
    ) -> None:
        if not isinstance(
            evidence, registration_store.RecoveryReserveExhausted
        ):
            raise TypeError("recovery evidence must be store-authenticated")
        super().__init__(self.reason)
        self.evidence = evidence


class R1ScopeRefused(RuntimeError):
    def __init__(
        self, selection: registration_store.R1ScopeSelection
    ) -> None:
        super().__init__("R1 tick scope contains another member")
        self.selection = selection


_R1_TICK_SCOPE_SEAL = object()


@dataclass(frozen=True)
class R1TickScope:
    """One atomic R1 observation shared across all Body B tick lanes."""

    authorized_member_id: str
    boot_id: str
    now_mono_ns: int
    selection: registration_store.R1ScopeSelection
    _store_identity: int = field(repr=False)
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._seal is not _R1_TICK_SCOPE_SEAL:
            raise TypeError("R1 tick scope must come from Body B preflight")
        if not _hex64(self.authorized_member_id):
            raise ValueError("authorized_member_id must be lowercase 64-hex")
        if not isinstance(self.boot_id, str) or not self.boot_id:
            raise ValueError("boot_id must be nonempty")
        if type(self.now_mono_ns) is not int or self.now_mono_ns < 0:
            raise ValueError("now_mono_ns must be a nonnegative integer")
        if type(self.selection) is not registration_store.R1ScopeSelection:
            raise TypeError("R1 selection has the wrong type")
        for candidate in (
            self.selection.authorized_same_boot,
            self.selection.authorized_due,
            self.selection.authorized_reboot,
        ):
            if (
                candidate is not None
                and candidate.member_id != self.authorized_member_id
            ):
                raise registration_store.StoreUnavailable(
                    "R1 selector returned another authorized member"
                )

    def __reduce__(self) -> object:
        raise TypeError("R1 tick scope is process-local")

    def __reduce_ex__(self, _protocol: int) -> object:
        raise TypeError("R1 tick scope is process-local")


def _select_r1_tick_scope(
    store: registration_store.RegistrationStore,
    *,
    authorized_member_id: str,
    boot_id: str,
    now_mono_ns: int,
) -> R1TickScope:
    selection = store.select_r1_scope(
        authorized_member_id,
        boot_id,
        now_mono_ns,
    )
    if (
        selection.outside_scope_same_boot
        or selection.outside_scope_due
        or selection.outside_scope_reboot
    ):
        raise R1ScopeRefused(selection)
    return R1TickScope(
        authorized_member_id=authorized_member_id,
        boot_id=boot_id,
        now_mono_ns=now_mono_ns,
        selection=selection,
        _store_identity=id(store),
        _seal=_R1_TICK_SCOPE_SEAL,
    )


def _require_r1_tick_scope(
    scope: R1TickScope,
    store: registration_store.RegistrationStore,
    *,
    boot_id: str,
    now_mono_ns: int | None = None,
) -> registration_store.R1ScopeSelection:
    if (
        type(scope) is not R1TickScope
        or scope._seal is not _R1_TICK_SCOPE_SEAL
        or scope._store_identity != id(store)
        or scope.boot_id != boot_id
        or (
            now_mono_ns is not None
            and scope.now_mono_ns != now_mono_ns
        )
    ):
        raise registration_store.StaleAuthority(
            "R1 tick scope does not match this tick"
        )
    return scope.selection


@dataclass(frozen=True)
class BasisObservation:
    identity: registration_store.MemberIdentity
    request_kind: str
    workspace_roots_hash: str
    blocked_basis_fingerprint: str | None
    fresh_provider: (
        Callable[
            [],
            BasisObservation | registration_store.FreshMemberBasis,
        ]
        | None
    ) = field(default=None, compare=False, repr=False)

    @classmethod
    def from_identity(
        cls,
        identity: registration_store.MemberIdentity,
        *,
        request_kind: str,
        workspace_roots_hash: str,
        blocked_basis_fingerprint: str | None = None,
        fresh_provider: (
            Callable[
                [],
                BasisObservation | registration_store.FreshMemberBasis,
            ]
            | None
        ) = None,
    ) -> "BasisObservation":
        if request_kind not in {
            "CLEAN_ELIGIBLE",
            "BLOCKED_DIRTY",
            "BLOCKED_OPERATION",
        }:
            raise ValueError("unknown request kind")
        if request_kind == "CLEAN_ELIGIBLE":
            blocked_basis_fingerprint = None
        elif blocked_basis_fingerprint is None:
            blocked_basis_fingerprint = registration_hashes.deterministic_id(
                "awa-reg-blocked-basis/v1",
                identity.current_basis_hash,
                request_kind,
            )
        return cls(
            identity=identity,
            request_kind=request_kind,
            workspace_roots_hash=workspace_roots_hash,
            blocked_basis_fingerprint=blocked_basis_fingerprint,
            fresh_provider=fresh_provider,
        )

    @property
    def basis_update(self) -> registration_store.BasisUpdate:
        return registration_store.BasisUpdate(
            self.identity.policy_basis_hash,
            self.identity.operation_basis_hash,
            self.identity.lifecycle_basis_hash,
            self.identity.current_basis_hash,
        )

    @property
    def basis_sample(self) -> registration_admission.BasisSample:
        return registration_admission.BasisSample(
            canonical_root=self.identity.canonical_root,
            canonical_root_hash=(
                registration_admission.canonical_root_hash(
                    self.identity.canonical_root
                )
            ),
            member_id=derive_member_id(self.identity),
            current_basis_hash=self.identity.current_basis_hash,
            physical_basis_hash=self.identity.physical_basis_hash,
            git_basis_hash=self.identity.git_basis_hash,
            policy_basis_hash=self.identity.policy_basis_hash,
            operation_basis_hash=self.identity.operation_basis_hash,
            lifecycle_basis_hash=self.identity.lifecycle_basis_hash,
            workspace_roots_hash=self.workspace_roots_hash,
        )

    @property
    def fresh_member_basis(self) -> registration_store.FreshMemberBasis:
        return registration_store.FreshMemberBasis(
            identity=self.identity,
            intent=_intent(self),
            workspace_roots_hash=self.workspace_roots_hash,
        )


@dataclass(frozen=True)
class RegistrationHandle:
    member_id: str
    episode_id: str


@dataclass(frozen=True)
class ActionWork:
    effect_id: str
    ordinal: int
    kind: str
    action_hash: str
    postcondition_hash: str


@dataclass(frozen=True)
class HelperObservation:
    kind: str
    measured_postcondition_hash: str
    external_growth_bytes: int
    conflict_code: str = "ACTION_POSTCONDITION_DIVERGENT"


@dataclass(frozen=True)
class DriveResult:
    member_id: str
    effect_id: str
    outcome: str


@dataclass(frozen=True)
class TickReceipt:
    snapshot_token: str
    selected_member_ids: tuple[str, ...]
    selected_status_hashes: tuple[tuple[str, str], ...]
    missed_member_ids: tuple[str, ...]
    member_reasons: tuple[tuple[str, str], ...]
    recovery_member_ids: tuple[str, ...]
    fairness_suspended: bool


@dataclass(frozen=True)
class TickRecovery:
    recovered_member_ids: tuple[str, ...]
    unavailable_member_ids: tuple[str, ...]


@dataclass(frozen=True)
class SameBootCursor:
    boot_id: str
    protocol_seq: int
    protocol_hash: str
    selection_snapshot_hash: str
    last_member_id: str | None
    last_pre_status_hash: str | None
    last_post_status_hash: str | None
    outcome: str | None
    batch_count: int
    wrapped: bool

    def __post_init__(self) -> None:
        if not isinstance(self.boot_id, str) or not self.boot_id:
            raise ValueError("cursor boot_id must be nonempty")
        if type(self.protocol_seq) is not int or self.protocol_seq < 1:
            raise ValueError("cursor protocol_seq must be positive")
        for field in ("protocol_hash", "selection_snapshot_hash"):
            if not _hex64(getattr(self, field)):
                raise ValueError(f"{field} must be lowercase 64-hex")
        if type(self.batch_count) is not int:
            raise ValueError("cursor batch_count must be an integer")
        if type(self.wrapped) is not bool:
            raise ValueError("cursor wrapped must be a boolean")
        nullable = (
            self.last_member_id,
            self.last_pre_status_hash,
            self.last_post_status_hash,
            self.outcome,
        )
        if all(value is None for value in nullable):
            if self.batch_count != 0 or self.wrapped:
                raise ValueError("empty cursor fields are inconsistent")
            return
        if any(value is None for value in nullable):
            raise ValueError("nonempty cursor fields may not be null")
        for field in (
            "last_member_id",
            "last_pre_status_hash",
            "last_post_status_hash",
        ):
            if not _hex64(getattr(self, field)):
                raise ValueError(f"{field} must be lowercase 64-hex")
        if self.outcome not in SAME_BOOT_OUTCOMES:
            raise ValueError("unknown same-boot cursor outcome")
        if not 1 <= self.batch_count <= TICK_LANES:
            raise ValueError("cursor batch_count must be between one and eight")

    def as_value(self) -> dict[str, object]:
        return {
            "schema": SAME_BOOT_CURSOR_SCHEMA,
            "boot_id": self.boot_id,
            "protocol_seq": str(self.protocol_seq),
            "protocol_hash": self.protocol_hash,
            "selection_snapshot_hash": self.selection_snapshot_hash,
            "last_member_id": self.last_member_id,
            "last_pre_status_hash": self.last_pre_status_hash,
            "last_post_status_hash": self.last_post_status_hash,
            "outcome": self.outcome,
            "batch_count": str(self.batch_count),
            "wrapped": self.wrapped,
        }


@dataclass(frozen=True)
class SameBootSelection:
    candidates: tuple[registration_store.SameBootCandidate, ...]
    wrapped: bool
    restarted: bool


@dataclass(frozen=True)
class SameBootExamined:
    member_id: str
    pre_status_hash: str
    post_status_hash: str
    outcome: str


@dataclass(frozen=True)
class SameBootRecoveryBatch:
    cursor: SameBootCursor
    examined: tuple[SameBootExamined, ...]


def same_boot_snapshot_value(
    snapshot: registration_store.SameBootSnapshot,
) -> dict[str, object]:
    if not isinstance(snapshot, registration_store.SameBootSnapshot):
        raise TypeError("same-boot snapshot has the wrong type")
    return {
        "schema": SAME_BOOT_SNAPSHOT_SCHEMA,
        "boot_id": snapshot.boot_id,
        "protocol_seq": str(snapshot.protocol_seq),
        "protocol_hash": snapshot.protocol_hash,
        "candidates": [
            {
                "member_id": candidate.member_id,
                "status_hash": candidate.status_hash,
                "executor_token_hash": candidate.executor_token_hash,
                "executor_generation": str(
                    candidate.executor_generation
                ),
            }
            for candidate in snapshot.candidates
        ],
    }


def same_boot_snapshot_hash(
    snapshot: registration_store.SameBootSnapshot,
) -> str:
    return _domain_jcs_hash(
        SAME_BOOT_SNAPSHOT_SCHEMA,
        same_boot_snapshot_value(snapshot),
    )


def same_boot_cursor_hash(cursor: SameBootCursor) -> str:
    if not isinstance(cursor, SameBootCursor):
        raise TypeError("same-boot cursor has the wrong type")
    return _domain_jcs_hash(SAME_BOOT_CURSOR_SCHEMA, cursor.as_value())


def select_same_boot_batch(
    snapshot: registration_store.SameBootSnapshot,
    cursor: SameBootCursor | None,
) -> SameBootSelection:
    if not isinstance(snapshot, registration_store.SameBootSnapshot):
        raise TypeError("same-boot snapshot has the wrong type")
    if cursor is not None and not isinstance(cursor, SameBootCursor):
        raise TypeError("same-boot cursor has the wrong type")
    candidates = snapshot.candidates
    restarted = cursor is None
    if cursor is not None:
        current = (
            cursor.boot_id == snapshot.boot_id
            and cursor.protocol_seq == snapshot.protocol_seq
            and cursor.protocol_hash == snapshot.protocol_hash
            and cursor.last_member_id is not None
        )
        by_member = {
            candidate.member_id: candidate for candidate in candidates
        }
        boundary = by_member.get(cursor.last_member_id or "")
        if boundary is not None:
            current = (
                current
                and boundary.status_hash == cursor.last_post_status_hash
            )
        else:
            current = (
                current
                and cursor.outcome == "NO_LONGER_CANDIDATE"
            )
        if current:
            remaining = tuple(
                candidate
                for candidate in candidates
                if candidate.member_id > (cursor.last_member_id or "")
            )
            if remaining:
                return SameBootSelection(
                    remaining[:TICK_LANES],
                    cursor.wrapped,
                    False,
                )
            if cursor.wrapped:
                return SameBootSelection((), True, False)
            return SameBootSelection(
                candidates[:TICK_LANES],
                True,
                False,
            )
        restarted = True
    return SameBootSelection(
        candidates[:TICK_LANES],
        False,
        restarted,
    )


@dataclass(frozen=True)
class LaneAuthorization:
    helper_payload: object
    commit_token: object


class ActionHelper(Protocol):
    def inspect(self, action: ActionWork) -> HelperObservation: ...

    def apply(
        self,
        action: ActionWork,
        execution: registration_store.MemberExecution,
    ) -> None: ...


class ObservationCollector(Protocol):
    def collect_observation(
        self, event: registration_admission.RegistrationEvent
    ) -> BasisObservation: ...


class UnavailableHelper:
    def inspect(self, action: ActionWork) -> HelperObservation:
        return HelperObservation(
            "UNAVAILABLE", action.postcondition_hash, 0
        )

    def apply(
        self,
        action: ActionWork,
        execution: registration_store.MemberExecution,
    ) -> None:
        del action, execution
        raise RuntimeError("unavailable helper cannot apply")


class ConflictHelper:
    def inspect(self, action: ActionWork) -> HelperObservation:
        measured = registration_hashes.deterministic_id(
            "awa-reg-conflict-observation/v1",
            action.effect_id,
            action.kind,
            action.postcondition_hash,
        )
        return HelperObservation(
            "CONFLICT",
            measured,
            0,
            "ACTION_POSTCONDITION_DIVERGENT",
        )

    def apply(
        self,
        action: ActionWork,
        execution: registration_store.MemberExecution,
    ) -> None:
        del action, execution
        raise RuntimeError("conflicting helper cannot apply")


class ProofFileHelper:
    def __init__(self, path: Path, proof_bytes: bytes) -> None:
        self.path = Path(path)
        self.proof_bytes = bytes(proof_bytes)
        if (
            not self.path.is_absolute()
            or os.path.normpath(str(self.path)) != str(self.path)
            or os.path.realpath(self.path.parent) != str(self.path.parent)
        ):
            raise ValueError("proof path must be canonical and absolute")
        parsed = registration_jcs.parse_canonical(self.proof_bytes)
        if not isinstance(parsed, dict):
            raise ValueError("proof bytes must be a closed JCS object")

    def inspect(self, action: ActionWork) -> HelperObservation:
        try:
            metadata = self.path.lstat()
        except FileNotFoundError:
            return HelperObservation("ABSENT", "00" * 32, 0)
        except OSError:
            return HelperObservation(
                "UNAVAILABLE", action.postcondition_hash, 0
            )
        if (
            self.path.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
        ):
            return _conflict_observation(action)
        try:
            data = self.path.read_bytes()
        except OSError:
            return HelperObservation(
                "UNAVAILABLE", action.postcondition_hash, 0
            )
        if data != self.proof_bytes:
            return _conflict_observation(action)
        return HelperObservation(
            "EXACT",
            action.postcondition_hash,
            len(self.proof_bytes),
        )

    def apply(
        self,
        action: ActionWork,
        execution: registration_store.MemberExecution,
    ) -> None:
        del action, execution
        parent = self.path.parent
        metadata = parent.lstat()
        if (
            parent.is_symlink()
            or not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            raise RuntimeError("proof parent is not private")
        temporary = parent / (
            f".{self.path.name}.tmp-{secrets.token_hex(12)}"
        )
        descriptor = os.open(
            temporary,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            view = memoryview(self.proof_bytes)
            written = 0
            while written < len(view):
                count = os.write(descriptor, view[written:])
                if count <= 0:
                    raise OSError("short proof write")
                written += count
            os.fchmod(descriptor, 0o600)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        try:
            os.link(temporary, self.path, follow_symlinks=False)
            os.unlink(temporary)
            parent_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise


class LegacyLeaseHelper:
    def __init__(self, root: str) -> None:
        self.root = root

    def inspect(self, action: ActionWork) -> HelperObservation:
        state = native_entry.inspect_lease_state(self.root)
        if state == "valid":
            return HelperObservation(
                "EXACT", action.postcondition_hash, 0
            )
        if state == "absent":
            return HelperObservation("ABSENT", "00" * 32, 0)
        if state == "conflict":
            return _conflict_observation(action)
        return HelperObservation(
            "UNAVAILABLE", action.postcondition_hash, 0
        )

    def apply(
        self,
        action: ActionWork,
        execution: registration_store.MemberExecution,
    ) -> None:
        del action, execution
        lifecycle.adopt(self.root)


class LegacyLifecycleHelper(LegacyLeaseHelper):
    def apply(
        self,
        action: ActionWork,
        execution: registration_store.MemberExecution,
    ) -> None:
        del action, execution
        ok, reason = lifecycle.attest(self.root)
        if not ok:
            raise RuntimeError(f"legacy lifecycle attest failed: {reason}")


class FinalBasisHelper:
    def __init__(
        self,
        collector: registration_admission.BasisCollector,
        event: registration_admission.RegistrationEvent,
    ) -> None:
        self.collector = collector
        self.event = event

    def inspect(self, action: ActionWork) -> HelperObservation:
        try:
            sample = self.collector.collect(self.event)
        except Exception:
            return HelperObservation(
                "UNAVAILABLE", action.postcondition_hash, 0
            )
        if sample.current_basis_hash == action.postcondition_hash:
            return HelperObservation(
                "EXACT", action.postcondition_hash, 0
            )
        return HelperObservation(
            "CONFLICT",
            sample.current_basis_hash,
            0,
            "FINAL_BASIS_DIVERGENT",
        )

    def apply(
        self,
        action: ActionWork,
        execution: registration_store.MemberExecution,
    ) -> None:
        del action, execution
        raise RuntimeError("final basis collection is read-only")


def _conflict_observation(action: ActionWork) -> HelperObservation:
    return HelperObservation(
        "CONFLICT",
        registration_hashes.deterministic_id(
            "awa-reg-observed-conflict/v1",
            action.effect_id,
            action.kind,
            action.postcondition_hash,
        ),
        0,
        "ACTION_POSTCONDITION_DIVERGENT",
    )


def derive_member_id(identity: registration_store.MemberIdentity) -> str:
    return registration_hashes.deterministic_id(
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


def _intent(
    observation: BasisObservation,
) -> registration_store.EffectIntent:
    if observation.request_kind != "CLEAN_ELIGIBLE":
        return registration_store.EffectIntent(
            request_kind=observation.request_kind,
            request_basis_hash=observation.identity.current_basis_hash,
            actions=(),
            external_growth_reservation_bytes=0,
            outcome_reservation_bytes=96 * 1024,
            successor_reservation_bytes=64 * 1024,
            blocked_basis_fingerprint=observation.blocked_basis_fingerprint,
        )
    member_id = derive_member_id(observation.identity)
    actions = []
    for ordinal, kind in enumerate(ACTION_KINDS, 1):
        postcondition = (
            observation.identity.current_basis_hash
            if ordinal == 4
            else registration_hashes.deterministic_id(
                "awa-reg-action-postcondition/v1",
                member_id,
                observation.identity.current_basis_hash,
                str(ordinal),
                kind,
            )
        )
        actions.append(
            registration_store.ActionSpec(
                kind=kind,
                action_hash=registration_hashes.deterministic_id(
                    "awa-reg-action-intent/v1",
                    member_id,
                    observation.identity.current_basis_hash,
                    str(ordinal),
                    kind,
                    postcondition,
                ),
                postcondition_hash=postcondition,
            )
        )
    return registration_store.EffectIntent(
        request_kind="CLEAN_ELIGIBLE",
        request_basis_hash=observation.identity.current_basis_hash,
        actions=tuple(actions),
        external_growth_reservation_bytes=64 * 1024,
        outcome_reservation_bytes=96 * 1024,
        successor_reservation_bytes=64 * 1024,
    )


def _fresh_basis_from_provider(provider) -> registration_store.FreshMemberBasis:
    value = provider()
    if type(value) is registration_store.FreshMemberBasis:
        return value
    if type(value) is not BasisObservation:
        raise registration_store.StaleAuthority(
            "fresh-basis provider returned the wrong type"
        )
    return value.fresh_member_basis


class RegistrationCoordinator:
    def __init__(
        self,
        *,
        store: registration_store.RegistrationStore,
        data: registration_store.DataCapability,
        candidate: registration_store.ProtocolCandidate,
    ) -> None:
        self.store = store
        self.data = data
        self.candidate = candidate

    def ensure(
        self,
        event: registration_admission.RegistrationEvent,
        observation: BasisObservation,
        *,
        fresh_provider=None,
    ) -> RegistrationHandle:
        if observation.identity.canonical_root != event.root:
            raise registration_admission.EventRefused("ROOT_UNSUPPORTED")
        member_id = derive_member_id(observation.identity)
        provider = (
            fresh_provider
            if fresh_provider is not None
            else observation.fresh_provider
        )
        if not callable(provider):
            raise registration_store.StaleAuthority(
                "fresh-basis provider is required"
            )
        with self.store.member_mutation_scope(member_id) as scope:
            basis = scope.collect_fresh_basis(
                lambda: _fresh_basis_from_provider(provider)
            )
            if basis.identity.canonical_root != event.root:
                raise registration_admission.EventRefused(
                    "ROOT_UNSUPPORTED"
                )
            authority = self.store.read_selected_authority(member_id)
            if authority is None:
                scope.install_member(
                    self.data,
                    self.candidate,
                    basis,
                )
            protocol = self.store.current_protocol()
            if protocol is None:
                raise registration_store.StoreUnavailable(
                    "protocol authority missing"
                )
            episode_id = registration_hashes.deterministic_id(
                "awa-reg-episode-v1",
                event.conversation_id,
                event.generation_id,
                event.source_contract,
                event.source_event,
                str(protocol["protocol_generation"]),
                member_id,
                basis.workspace_roots_hash,
                protocol["tool_inventory_hash"],
                protocol["hook_projection_hash"],
            )
            if not self.store.episode_exists(member_id, episode_id):
                scope.bind_episode(
                    self.data,
                    self.candidate,
                    basis,
                    source=registration_store.EpisodeSource(
                        event.conversation_id,
                        event.generation_id,
                        event.source_contract,
                        event.source_event,
                        basis.workspace_roots_hash,
                    ),
                )
            authority = self.store.read_selected_authority(
                member_id, episode_id=episode_id
            )
            if authority is None:
                raise registration_store.StoreUnavailable(
                    "member authority missing after bind"
                )
            member = authority.member
            if (
                member["phase"] == "RESOLVED"
                and member["pending_effect_id"] is not None
            ):
                scope.handoff_resolved(
                    self.data,
                    self.candidate,
                    basis,
                    expected_member_hash=member["member_tuple_hash"],
                    expected_effect_hash=authority.effect[
                        "outcome_tuple_hash"
                    ],
                    expected_status_hash=authority.status["status_hash"],
                )
                successor = self.store.read_selected_authority(member_id)
                if (
                    successor.member["current_basis_hash"]
                    != basis.intent.request_basis_hash
                ):
                    scope.invalidate_requested(
                        self.data,
                        self.candidate,
                        basis,
                        expected_member_hash=successor.member[
                            "member_tuple_hash"
                        ],
                        expected_effect_hash=successor.effect[
                            "request_tuple_hash"
                        ],
                        expected_status_hash=successor.status[
                            "status_hash"
                        ],
                    )
                return RegistrationHandle(member_id, episode_id)
            if (
                member["current_basis_hash"]
                != basis.intent.request_basis_hash
            ):
                if member["phase"] == "REQUESTED":
                    scope.invalidate_requested(
                        self.data,
                        self.candidate,
                        basis,
                        expected_member_hash=member["member_tuple_hash"],
                        expected_effect_hash=authority.effect[
                            "request_tuple_hash"
                        ],
                        expected_status_hash=authority.status[
                            "status_hash"
                        ],
                    )
                elif member["phase"] == "EFFECT_IN_FLIGHT":
                    if member["pending_effect_id"] is None:
                        scope.set_pending(
                            self.data,
                            self.candidate,
                            basis,
                            expected_member_hash=member[
                                "member_tuple_hash"
                            ],
                            expected_effect_hash=authority.effect[
                                "request_tuple_hash"
                            ],
                            expected_status_hash=authority.status[
                                "status_hash"
                            ],
                        )
                    else:
                        scope.replace_pending(
                            self.data,
                            self.candidate,
                            basis,
                            expected_member_hash=member[
                                "member_tuple_hash"
                            ],
                            expected_effect_hash=member[
                                "pending_effect_tuple_hash"
                            ],
                            expected_status_hash=authority.status[
                                "status_hash"
                            ],
                        )
                elif member["phase"] == "RESOLVED":
                    scope.handoff_resolved(
                        self.data,
                        self.candidate,
                        basis,
                        expected_member_hash=member[
                            "member_tuple_hash"
                        ],
                        expected_effect_hash=authority.effect[
                            "outcome_tuple_hash"
                        ],
                        expected_status_hash=authority.status[
                            "status_hash"
                        ],
                        cause="BASIS_CHANGED",
                    )
            return RegistrationHandle(member_id, episode_id)

    def open_due(
        self, member_id: str
    ) -> registration_store.MemberExecution:
        authority = self.store.read_selected_authority(member_id)
        if authority is None or authority.member["phase"] != "REQUESTED":
            raise registration_store.StaleAuthority(
                "member is not due REQUESTED"
            )
        return self.store.open_effect(
            self.data,
            self.candidate,
            member_id=member_id,
            expected_member_hash=authority.member["member_tuple_hash"],
            expected_effect_hash=authority.effect["request_tuple_hash"],
            expected_status_hash=authority.status["status_hash"],
        ).execution

    def authorize_due(
        self,
        due: registration_store.DueCandidate,
        *,
        current_basis_hash: str | None = None,
        fresh_provider=None,
    ) -> registration_store.MemberExecution:
        basis = None
        if fresh_provider is not None:
            with self.store.member_mutation_scope(due.member_id) as scope:
                basis = scope.collect_fresh_basis(
                    lambda: _fresh_basis_from_provider(fresh_provider)
                )
                current_basis_hash = basis.identity.current_basis_hash
                expected_basis = (
                    due.pending_basis_hash
                    if due.phase == "RESOLVED"
                    else due.current_basis_hash
                )
                if expected_basis != current_basis_hash:
                    raise registration_store.StaleAuthority(
                        "fresh due basis does not match selected authority"
                    )
                if due.phase == "RESOLVED":
                    authority = self.store.read_selected_authority(
                        due.member_id
                    )
                    if (
                        authority is None
                        or authority.member["pending_effect_id"] is None
                    ):
                        raise registration_store.StaleAuthority(
                            "RESOLVED due member has no pending handoff"
                        )
                    scope.handoff_resolved(
                        self.data,
                        self.candidate,
                        basis,
                        expected_member_hash=authority.member[
                            "member_tuple_hash"
                        ],
                        expected_effect_hash=authority.effect[
                            "outcome_tuple_hash"
                        ],
                        expected_status_hash=authority.status[
                            "status_hash"
                        ],
                    )
        if current_basis_hash is None:
            raise registration_store.StaleAuthority(
                "fresh due basis is required"
            )
        expected_basis = (
            due.pending_basis_hash
            if due.phase == "RESOLVED"
            else due.current_basis_hash
        )
        if expected_basis != current_basis_hash:
            raise registration_store.StaleAuthority(
                "fresh due basis does not match selected authority"
            )
        if due.phase == "REQUESTED":
            return self.store.open_effect(
                self.data,
                self.candidate,
                member_id=due.member_id,
                expected_member_hash=due.member_tuple_hash,
                expected_effect_hash=due.effect_tuple_hash,
                expected_status_hash=due.status_hash,
            ).execution
        if due.phase == "EFFECT_IN_FLIGHT":
            return self.store.reacquire_effect(
                self.data,
                self.candidate,
                member_id=due.member_id,
                expected_member_hash=due.member_tuple_hash,
                expected_effect_hash=due.effect_tuple_hash,
                expected_status_hash=due.status_hash,
            ).execution
        if due.phase == "RESOLVED":
            if basis is None:
                raise registration_store.StaleAuthority(
                    "RESOLVED due handoff requires a fresh-basis provider"
                )
            successor = self.store.read_selected_authority(due.member_id)
            return self.store.open_effect(
                self.data,
                self.candidate,
                member_id=due.member_id,
                expected_member_hash=successor.member[
                    "member_tuple_hash"
                ],
                expected_effect_hash=successor.effect[
                    "request_tuple_hash"
                ],
                expected_status_hash=successor.status["status_hash"],
            ).execution
        raise registration_store.StaleAuthority("unknown due member phase")

    def drive(
        self,
        member_id: str,
        helpers: Mapping[str, ActionHelper],
        *,
        fresh_provider=None,
    ) -> DriveResult:
        authority = self.store.read_selected_authority(member_id)
        if authority is None:
            raise registration_store.StoreUnavailable("member missing")
        phase = authority.member["phase"]
        if phase == "RESOLVED":
            if authority.member["pending_effect_id"] is not None:
                if fresh_provider is None:
                    raise registration_store.StaleAuthority(
                        "pending handoff requires fresh basis"
                    )
                with self.store.member_mutation_scope(member_id) as scope:
                    basis = scope.collect_fresh_basis(
                        lambda: _fresh_basis_from_provider(fresh_provider)
                    )
                    current = self.store.read_selected_authority(member_id)
                    if (
                        current is None
                        or current.member["phase"] != "RESOLVED"
                        or current.member["pending_effect_id"] is None
                    ):
                        raise registration_store.StaleAuthority(
                            "pending handoff changed"
                        )
                    scope.handoff_resolved(
                        self.data,
                        self.candidate,
                        basis,
                        expected_member_hash=current.member[
                            "member_tuple_hash"
                        ],
                        expected_effect_hash=current.effect[
                            "outcome_tuple_hash"
                        ],
                        expected_status_hash=current.status["status_hash"],
                    )
                return self.drive(
                    member_id,
                    helpers,
                    fresh_provider=fresh_provider,
                )
            return DriveResult(
                member_id,
                authority.effect["effect_id"],
                authority.effect["outcome_kind"],
            )
        if authority.effect["request_kind"] != "CLEAN_ELIGIBLE":
            return DriveResult(
                member_id,
                authority.effect["effect_id"],
                authority.status["reason_code"],
            )
        if phase == "REQUESTED":
            execution = self.open_due(member_id)
        elif (
            phase == "EFFECT_IN_FLIGHT"
            and authority.status["executor_token_hash"] is None
            and authority.status["help_due"] == 1
        ):
            execution = self.store.reacquire_effect(
                self.data,
                self.candidate,
                member_id=member_id,
                expected_member_hash=authority.member["member_tuple_hash"],
                expected_effect_hash=authority.effect[
                    "request_tuple_hash"
                ],
                expected_status_hash=authority.status["status_hash"],
            ).execution
        else:
            return DriveResult(
                member_id, authority.effect["effect_id"], "EFFECT_IN_FLIGHT"
            )
        return self.run_execution(execution, helpers)

    def run_execution(
        self,
        execution: registration_store.MemberExecution,
        helpers: Mapping[str, ActionHelper],
    ) -> DriveResult:
        try:
            return self._run_execution_inner(execution, helpers)
        except Exception:
            if execution.held:
                self._contain_helper_failure(execution)
            raise

    def _run_execution_inner(
        self,
        execution: registration_store.MemberExecution,
        helpers: Mapping[str, ActionHelper],
    ) -> DriveResult:
        while True:
            authority = self.store.read_selected_authority(
                execution.member_id
            )
            if authority is None:
                raise registration_store.StoreUnavailable("member missing")
            effect = authority.effect
            if effect["outcome_kind"] is not None:
                execution.close()
                return DriveResult(
                    execution.member_id,
                    execution.effect_id,
                    effect["outcome_kind"],
                )
            ordinal = len(authority.actions) + 1
            if ordinal > 4:
                result = self.store.close_success(
                    self.data,
                    self.candidate,
                    execution,
                    final_basis_hash=effect["request_basis_hash"],
                )
                del result
                return DriveResult(
                    execution.member_id, execution.effect_id, "SUCCESS"
                )
            kind = effect[f"action_{ordinal}_kind"]
            helper = helpers[kind]
            action = ActionWork(
                effect_id=execution.effect_id,
                ordinal=ordinal,
                kind=kind,
                action_hash=effect[f"action_{ordinal}_hash"],
                postcondition_hash=effect[
                    f"postcondition_{ordinal}_hash"
                ],
            )
            self.store.verify_execution(execution)
            try:
                observed = helper.inspect(action)
            except Exception:
                self._contain_helper_failure(execution)
                raise
            if observed.kind == "ABSENT":
                try:
                    self.store.verify_execution(execution)
                    helper.apply(action, execution)
                    self.store.verify_execution(execution)
                    observed = helper.inspect(action)
                except Exception:
                    self._contain_helper_failure(execution)
                    raise
                if observed.kind == "EXACT":
                    observation_kind = "APPLIED_VERIFIED"
                else:
                    observation_kind = ""
            elif observed.kind == "EXACT":
                observation_kind = "OBSERVED_EXACT"
            else:
                observation_kind = ""
            if observation_kind:
                self.store.append_action(
                    self.data,
                    self.candidate,
                    execution,
                    observation_kind=observation_kind,
                    measured_postcondition_hash=(
                        observed.measured_postcondition_hash
                    ),
                    external_growth_bytes=observed.external_growth_bytes,
                )
                continue
            if observed.kind == "CONFLICT":
                self.store.append_action(
                    self.data,
                    self.candidate,
                    execution,
                    observation_kind="LOGICAL_CONFLICT",
                    measured_postcondition_hash=(
                        observed.measured_postcondition_hash
                    ),
                    external_growth_bytes=observed.external_growth_bytes,
                )
                self.store.close_conflict(
                    self.data,
                    self.candidate,
                    execution,
                    conflict_code=observed.conflict_code,
                    expected_hash=action.postcondition_hash,
                    observed_hash=observed.measured_postcondition_hash,
                )
                return DriveResult(
                    execution.member_id,
                    execution.effect_id,
                    "LOGICAL_CONFLICT",
                )
            result = self.store.mark_unavailable(
                self.data, self.candidate, execution
            )
            if isinstance(
                result, registration_store.RecoveryReserveExhausted
            ):
                raise RecoveryContainmentUnavailable(result)
            return DriveResult(
                execution.member_id, execution.effect_id, "UNAVAILABLE"
            )

    def _contain_helper_failure(
        self, execution: registration_store.MemberExecution
    ) -> None:
        try:
            result = self.store.mark_unavailable(
                self.data, self.candidate, execution
            )
            if isinstance(
                result, registration_store.RecoveryReserveExhausted
            ):
                raise RecoveryContainmentUnavailable(result)
        except Exception:
            if not execution.held:
                raise
            execution.close()
            try:
                with self.store.member_mutation_scope(
                    execution.member_id
                ) as scope:
                    result = scope.mark_dead_executor_unavailable(
                        self.data,
                        self.candidate,
                        expected_status_hash=execution.target_status_hash,
                    )
                if isinstance(
                    result, registration_store.RecoveryReserveExhausted
                ):
                    raise RecoveryContainmentUnavailable(result)
            except RecoveryContainmentUnavailable:
                raise
            except Exception:
                pass

    def preflight_r1_tick(
        self,
        *,
        authorized_member_id: str,
        boot_id: str,
        now_mono_ns: int,
    ) -> R1TickScope:
        return _select_r1_tick_scope(
            self.store,
            authorized_member_id=authorized_member_id,
            boot_id=boot_id,
            now_mono_ns=now_mono_ns,
        )

    def recover_reboot(
        self,
        current_boot_id: str,
        *,
        r1_scope: R1TickScope | None = None,
    ) -> tuple[str, ...]:
        if r1_scope is None:
            candidates = self.store.list_reboot_candidates(current_boot_id)
        else:
            selection = _require_r1_tick_scope(
                r1_scope,
                self.store,
                boot_id=current_boot_id,
            )
            candidates = (
                ()
                if selection.authorized_reboot is None
                else (selection.authorized_reboot,)
            )
        recovered = []
        for candidate in candidates:
            self.store.reboot_status(
                self.data,
                self.candidate,
                member_id=candidate.member_id,
                expected_status_hash=candidate.status_hash,
            )
            recovered.append(candidate.member_id)
        return tuple(recovered)

    def recover_same_boot_executor(
        self, member_id: str
    ) -> (
        registration_store.OperationResult
        | registration_store.RecoveryReserveExhausted
    ):
        authority = self.store.read_selected_authority(member_id)
        if (
            authority is None
            or authority.member["phase"] != "EFFECT_IN_FLIGHT"
            or authority.status["executor_token_hash"] is None
        ):
            raise registration_store.StaleAuthority(
                "same-boot recovery requires stored executor"
            )
        with self.store.member_mutation_scope(
            member_id, timeout_seconds=0
        ) as scope:
            return scope.mark_dead_executor_unavailable(
                self.data,
                self.candidate,
                expected_status_hash=authority.status["status_hash"],
            )

    def recover_r1_same_boot(
        self,
        r1_scope: R1TickScope,
        *,
        recover=None,
    ) -> SameBootExamined | None:
        selection = _require_r1_tick_scope(
            r1_scope,
            self.store,
            boot_id=r1_scope.boot_id,
            now_mono_ns=r1_scope.now_mono_ns,
        )
        candidate = selection.authorized_same_boot
        if candidate is None:
            return None
        return self._recover_same_boot_candidate(
            candidate,
            boot_id=r1_scope.boot_id,
            recover=recover,
        )

    def recover_same_boot_tick(
        self,
        *,
        boot_id: str,
        cursor: SameBootCursor | None = None,
        recover=None,
        snapshot: registration_store.SameBootSnapshot | None = None,
    ) -> SameBootRecoveryBatch:
        snapshot = snapshot or self.store.select_same_boot_snapshot(
            boot_id=boot_id
        )
        if snapshot.boot_id != boot_id:
            raise registration_store.StaleAuthority(
                "same-boot snapshot belongs to another boot"
            )
        selection = select_same_boot_batch(snapshot, cursor)
        snapshot_hash = same_boot_snapshot_hash(snapshot)
        examined = []
        for candidate in selection.candidates:
            examined.append(
                self._recover_same_boot_candidate(
                    candidate,
                    boot_id=boot_id,
                    recover=recover,
                )
            )
        if examined:
            last = examined[-1]
            next_cursor = SameBootCursor(
                boot_id=snapshot.boot_id,
                protocol_seq=snapshot.protocol_seq,
                protocol_hash=snapshot.protocol_hash,
                selection_snapshot_hash=snapshot_hash,
                last_member_id=last.member_id,
                last_pre_status_hash=last.pre_status_hash,
                last_post_status_hash=last.post_status_hash,
                outcome=last.outcome,
                batch_count=len(examined),
                wrapped=selection.wrapped,
            )
        else:
            next_cursor = SameBootCursor(
                boot_id=snapshot.boot_id,
                protocol_seq=snapshot.protocol_seq,
                protocol_hash=snapshot.protocol_hash,
                selection_snapshot_hash=snapshot_hash,
                last_member_id=None,
                last_pre_status_hash=None,
                last_post_status_hash=None,
                outcome=None,
                batch_count=0,
                wrapped=False,
            )
        return SameBootRecoveryBatch(next_cursor, tuple(examined))

    def _recover_same_boot_candidate(
        self,
        candidate: registration_store.SameBootCandidate,
        *,
        boot_id: str,
        recover,
    ) -> SameBootExamined:
        outcome = "NO_LONGER_CANDIDATE"
        post_status_hash = candidate.status_hash
        try:
            with self.store.member_mutation_scope(
                candidate.member_id,
                timeout_seconds=0,
            ) as scope:
                current = self.store.read_selected_authority(
                    candidate.member_id
                )
                if (
                    current is None
                    or current.member["phase"] != "EFFECT_IN_FLIGHT"
                    or current.status["status_hash"] != candidate.status_hash
                    or current.status["executor_token_hash"]
                    != candidate.executor_token_hash
                    or current.status["executor_generation"]
                    != candidate.executor_generation
                    or current.status["executor_boot_id"] != boot_id
                ):
                    if current is not None:
                        post_status_hash = current.status["status_hash"]
                else:
                    result = scope.mark_dead_executor_unavailable(
                        self.data,
                        self.candidate,
                        expected_status_hash=candidate.status_hash,
                    )
                    if isinstance(
                        result,
                        registration_store.RecoveryReserveExhausted,
                    ):
                        raise RecoveryContainmentUnavailable(result)
                    current = self.store.read_selected_authority(
                        candidate.member_id
                    )
                    post_status_hash = current.status["status_hash"]
                    outcome = "CLEARED"
        except registration_lock.LockBusy:
            outcome = "BUSY_LIVE"
            post_status_hash = candidate.status_hash
        except registration_store.StaleAuthority:
            current = self.store.read_selected_authority(
                candidate.member_id
            )
            if current is not None:
                post_status_hash = current.status["status_hash"]
            outcome = "NO_LONGER_CANDIDATE"
        if outcome == "CLEARED" and recover is not None:
            try:
                recovery = recover(candidate.member_id)
                if isinstance(
                    recovery,
                    registration_store.RecoveryReserveExhausted,
                ):
                    raise RecoveryContainmentUnavailable(recovery)
                if bool(recovery):
                    outcome = "RECOVERED"
                    current = self.store.read_selected_authority(
                        candidate.member_id
                    )
                    if current is None:
                        raise registration_store.StoreUnavailable(
                            "recovered member authority is missing"
                        )
                    post_status_hash = current.status["status_hash"]
            except RecoveryContainmentUnavailable:
                raise
            except Exception:
                outcome = "CLEARED"
        return SameBootExamined(
            member_id=candidate.member_id,
            pre_status_hash=candidate.status_hash,
            post_status_hash=post_status_hash,
            outcome=outcome,
        )

    def retry_conflict(
        self,
        member_id: str,
        observation: BasisObservation,
        *,
        fresh_provider=None,
    ) -> registration_store.OperationResult:
        return self._handoff(
            member_id,
            observation,
            "EXPLICIT_CONFLICT_RETRY",
            fresh_provider=fresh_provider,
        )

    def repair_closure(
        self,
        member_id: str,
        observation: BasisObservation,
        *,
        fresh_provider=None,
    ) -> registration_store.OperationResult:
        return self._handoff(
            member_id,
            observation,
            "CURRENT_CLOSURE_CHANGED",
            fresh_provider=fresh_provider,
        )

    def _handoff(
        self,
        member_id: str,
        observation: BasisObservation,
        cause: str,
        *,
        fresh_provider=None,
    ) -> registration_store.OperationResult:
        provider = (
            fresh_provider
            if fresh_provider is not None
            else observation.fresh_provider
        )
        if not callable(provider):
            raise registration_store.StaleAuthority(
                "fresh-basis provider is required"
            )
        with self.store.member_mutation_scope(member_id) as scope:
            basis = scope.collect_fresh_basis(
                lambda: _fresh_basis_from_provider(provider)
            )
            authority = self.store.read_selected_authority(member_id)
            if (
                authority is None
                or authority.member["phase"] != "RESOLVED"
            ):
                raise registration_store.StaleAuthority(
                    "handoff requires RESOLVED member"
                )
            return scope.handoff_resolved(
                self.data,
                self.candidate,
                basis,
                expected_member_hash=authority.member[
                    "member_tuple_hash"
                ],
                expected_effect_hash=authority.effect[
                    "outcome_tuple_hash"
                ],
                expected_status_hash=authority.status["status_hash"],
                cause=cause,
            )


class FairnessScheduler:
    def __init__(
        self,
        *,
        store: registration_store.RegistrationStore,
        data: registration_store.DataCapability,
        candidate: registration_store.ProtocolCandidate,
    ) -> None:
        self.store = store
        self.data = data
        self.candidate = candidate

    def tick(
        self,
        *,
        boot_id: str,
        now_mono_ns: int,
        attempt,
        authorized_member_id: str | None = None,
        r1_scope: R1TickScope | None = None,
    ) -> TickReceipt:
        return self.tick_phased(
            boot_id=boot_id,
            now_mono_ns=now_mono_ns,
            open_attempt=lambda candidate: LaneAuthorization(
                candidate, candidate
            ),
            run_helper=attempt,
            commit_result=lambda _candidate, _token, result: bool(result),
            open_mutates_authority=False,
            authorized_member_id=authorized_member_id,
            r1_scope=r1_scope,
        )

    def tick_phased(
        self,
        *,
        boot_id: str,
        now_mono_ns: int,
        open_attempt,
        run_helper,
        commit_result,
        yield_result=None,
        open_mutates_authority: bool = True,
        authorized_member_id: str | None = None,
        r1_scope: R1TickScope | None = None,
    ) -> TickReceipt:
        if open_mutates_authority and yield_result is None:
            raise ValueError(
                "mutating lane opens require an exact yield resolver"
            )
        if authorized_member_id is not None and r1_scope is not None:
            raise ValueError(
                "R1 tick accepts an authorized member or a preflight, not both"
            )
        if r1_scope is not None:
            r1_selection = _require_r1_tick_scope(
                r1_scope,
                self.store,
                boot_id=boot_id,
                now_mono_ns=now_mono_ns,
            )
            selected = (
                ()
                if r1_selection.authorized_due is None
                else (r1_selection.authorized_due,)
            )
        elif authorized_member_id is None:
            selected = self.store.list_due_candidates(
                boot_id=boot_id,
                now_mono_ns=now_mono_ns,
                limit=TICK_LANES,
            )
        else:
            r1_selection = _select_r1_tick_scope(
                self.store,
                authorized_member_id=authorized_member_id,
                boot_id=boot_id,
                now_mono_ns=now_mono_ns,
            )
            selected = (
                ()
                if r1_selection.selection.authorized_due is None
                else (r1_selection.selection.authorized_due,)
            )
        opened = {}
        missed = []
        slow_open = set()
        forced_mutating = set()
        for candidate in selected:
            started = time.monotonic()
            try:
                authorization = open_attempt(candidate)
            except Exception:
                missed.append(candidate.member_id)
                continue
            if not isinstance(authorization, LaneAuthorization):
                if (
                    open_mutates_authority
                    or isinstance(
                        authorization,
                        registration_store.MemberExecution,
                    )
                ):
                    authorization = LaneAuthorization(None, authorization)
                    opened[candidate.member_id] = authorization
                    missed.append(candidate.member_id)
                    slow_open.add(candidate.member_id)
                    forced_mutating.add(candidate.member_id)
                    continue
                authorization = LaneAuthorization(
                    authorization, authorization
                )
            elif isinstance(
                authorization.helper_payload,
                registration_store.MemberExecution,
            ):
                token = (
                    authorization.commit_token
                    if isinstance(
                        authorization.commit_token,
                        registration_store.MemberExecution,
                    )
                    else authorization.helper_payload
                )
                authorization = LaneAuthorization(None, token)
                opened[candidate.member_id] = authorization
                missed.append(candidate.member_id)
                slow_open.add(candidate.member_id)
                forced_mutating.add(candidate.member_id)
                continue
            opened[candidate.member_id] = authorization
            if time.monotonic() - started > OPEN_SLICE_SECONDS:
                missed.append(candidate.member_id)
                slow_open.add(candidate.member_id)
        helper_results = _process_calls(
            [
                (
                    candidate.member_id,
                    run_helper,
                    opened[candidate.member_id].helper_payload,
                )
                for candidate in selected
                if (
                    candidate.member_id in opened
                    and candidate.member_id not in slow_open
                )
            ],
            timeout=HELPER_DEADLINE_SECONDS,
        )
        safely_resolved = set()
        unsafe_misses = set()
        for candidate in selected:
            if candidate.member_id not in opened:
                continue
            if candidate.member_id in slow_open:
                if (
                    open_mutates_authority
                    or candidate.member_id in forced_mutating
                ) and self._yield_opened(
                    candidate, opened[candidate.member_id], yield_result
                ):
                    safely_resolved.add(candidate.member_id)
                    continue
                if (
                    open_mutates_authority
                    or candidate.member_id in forced_mutating
                ):
                    unsafe_misses.add(candidate.member_id)
                continue
            result = helper_results.get(candidate.member_id)
            if result is _FAILED:
                missed.append(candidate.member_id)
                if (
                    open_mutates_authority
                    or candidate.member_id in forced_mutating
                ) and self._yield_opened(
                    candidate, opened[candidate.member_id], yield_result
                ):
                    safely_resolved.add(candidate.member_id)
                    continue
                if (
                    open_mutates_authority
                    or candidate.member_id in forced_mutating
                ):
                    unsafe_misses.add(candidate.member_id)
                continue
            started = time.monotonic()
            try:
                committed = bool(
                    commit_result(
                        candidate,
                        opened[candidate.member_id].commit_token,
                        result,
                    )
                )
            except Exception:
                committed = False
            if (
                not committed
                or time.monotonic() - started > OPEN_SLICE_SECONDS
            ):
                missed.append(candidate.member_id)
                if (
                    open_mutates_authority
                    or candidate.member_id in forced_mutating
                ) and self._yield_opened(
                    candidate, opened[candidate.member_id], yield_result
                ):
                    safely_resolved.add(candidate.member_id)
                    continue
                if (
                    open_mutates_authority
                    or candidate.member_id in forced_mutating
                ):
                    unsafe_misses.add(candidate.member_id)
        missed = list(dict.fromkeys(missed))
        suspended = bool(unsafe_misses)
        for candidate in selected:
            if (
                candidate.member_id not in missed
                or candidate.member_id in safely_resolved
                or candidate.member_id in unsafe_misses
            ):
                continue
            try:
                self.store.schedule_status(
                    self.data,
                    self.candidate,
                    member_id=candidate.member_id,
                    expected_status_hash=candidate.status_hash,
                    attempt_count=1,
                    backoff_ns=TICK_INTERVAL_NS,
                )
            except Exception:
                suspended = True
                continue
        selected_hashes = tuple(
            (row.member_id, row.status_hash) for row in selected
        )
        snapshot_token = registration_hashes.deterministic_id(
            "awa-reg-tick-snapshot/v1",
            boot_id,
            str(now_mono_ns),
            *[
                value
                for member_id, status_hash in selected_hashes
                for value in (member_id, status_hash)
            ],
        )
        return TickReceipt(
            snapshot_token=snapshot_token,
            selected_member_ids=tuple(row.member_id for row in selected),
            selected_status_hashes=selected_hashes,
            missed_member_ids=tuple(missed),
            member_reasons=tuple(
                (member_id, "HOST_STARVED") for member_id in missed
            ),
            recovery_member_ids=tuple(
                row.member_id
                for row in selected
                if row.member_id in unsafe_misses
            ),
            fairness_suspended=suspended,
        )

    def recover_suspended(
        self, receipt: TickReceipt
    ) -> TickRecovery:
        recovered = []
        unavailable = []
        for member_id in receipt.recovery_member_ids:
            try:
                authority = self.store.read_selected_authority(member_id)
                if authority is None:
                    unavailable.append(member_id)
                    continue
                if authority.status["executor_token_hash"] is not None:
                    with self.store.member_mutation_scope(
                        member_id
                    ) as scope:
                        result = scope.mark_dead_executor_unavailable(
                            self.data,
                            self.candidate,
                            expected_status_hash=authority.status[
                                "status_hash"
                            ],
                        )
                    if isinstance(
                        result,
                        registration_store.RecoveryReserveExhausted,
                    ):
                        raise RecoveryContainmentUnavailable(result)
                recovered.append(member_id)
            except RecoveryContainmentUnavailable:
                raise
            except Exception:
                unavailable.append(member_id)
        return TickRecovery(tuple(recovered), tuple(unavailable))

    def _yield_opened(
        self,
        candidate: registration_store.DueCandidate,
        authorization: LaneAuthorization,
        yield_result,
    ) -> bool:
        token = authorization.commit_token
        if yield_result is not None:
            try:
                if bool(yield_result(candidate, token)):
                    return True
            except Exception:
                pass
        authority = self.store.read_selected_authority(
            candidate.member_id
        )
        if (
            authority is not None
            and authority.status["executor_token_hash"] is None
        ):
            return True
        if not isinstance(token, registration_store.MemberExecution):
            return False
        token.close()
        try:
            with self.store.member_mutation_scope(
                candidate.member_id
            ) as scope:
                result = scope.mark_dead_executor_unavailable(
                    self.data,
                    self.candidate,
                    expected_status_hash=token.target_status_hash,
                )
            if isinstance(
                result, registration_store.RecoveryReserveExhausted
            ):
                raise RecoveryContainmentUnavailable(result)
            return True
        except RecoveryContainmentUnavailable:
            raise
        except Exception:
            authority = self.store.read_selected_authority(
                candidate.member_id
            )
            return bool(
                authority is not None
                and authority.status["executor_token_hash"] is None
            )


_FAILED = object()


def _stop_process(process) -> None:
    if process.is_alive():
        process.terminate()
        process.join(0.25)
    if process.is_alive():
        process.kill()
        process.join()


def _process_calls(jobs, *, timeout: float) -> dict[str, object]:
    context = multiprocessing.get_context("spawn")
    workers = {}
    receiving = None
    sending = None
    try:
        for member_id, function, argument in jobs:
            receiving, sending = context.Pipe(duplex=False)
            process = context.Process(
                target=_call_process,
                args=(function, argument, sending),
            )
            process.start()
            workers[member_id] = (process, receiving)
            sending.close()
    except BaseException:
        for endpoint in (sending, receiving):
            try:
                if endpoint is not None:
                    endpoint.close()
            except BaseException:
                pass
        for started, endpoint in workers.values():
            try:
                _stop_process(started)
            except BaseException:
                pass
            try:
                endpoint.close()
            except BaseException:
                pass
        raise
    # The deadline starts only after every lane process has started. Each
    # worker therefore receives the same full concurrent batch window;
    # sequential joins below only reap against that shared absolute bound.
    deadline = time.monotonic() + timeout
    results = {}
    try:
        for member_id, (process, receiving) in workers.items():
            process.join(max(0.0, deadline - time.monotonic()))
            _stop_process(process)
            if process.exitcode == 0 and receiving.poll():
                try:
                    status, value = receiving.recv()
                except Exception:
                    results[member_id] = _FAILED
                else:
                    results[member_id] = (
                        value if status == "ok" else _FAILED
                    )
            else:
                results[member_id] = _FAILED
            receiving.close()
    finally:
        for process, receiving in workers.values():
            try:
                _stop_process(process)
            except BaseException:
                pass
            try:
                receiving.close()
            except BaseException:
                pass
    return results


def _call_process(function, argument, sending) -> None:
    try:
        sending.send(("ok", function(argument)))
    except BaseException:
        sending.send(("error", None))
    finally:
        sending.close()


class StoreAuthorityAdapter:
    """Convert Body A typed selected authority into the Body B admission view."""

    def __init__(self, store: registration_store.RegistrationStore) -> None:
        self.store = store

    def read_view(
        self, member_id: str, episode_id: str
    ) -> registration_admission.SelectedAuthorityView | None:
        authority = self.store.read_selected_authority(
            member_id, episode_id=episode_id
        )
        if authority is None or len(authority.episodes) != 1:
            return None
        protocol = authority.protocol
        member = authority.member
        status = authority.status
        effect = authority.effect
        episode = authority.episodes[0]
        return registration_admission.SelectedAuthorityView(
            protocol_seq=protocol["protocol_seq"],
            protocol_hash=protocol["protocol_hash"],
            protocol_generation=protocol["protocol_generation"],
            protocol_mode=protocol["mode"],
            protocol_schema_hash=protocol["schema_hash"],
            profile_hash=protocol["profile_hash"],
            runtime_capability_hash=protocol["runtime_capability_hash"],
            tool_inventory_hash=protocol["tool_inventory_hash"],
            hook_projection_hash=protocol["hook_projection_hash"],
            episode_id=episode["episode_id"],
            episode_envelope_hash=episode["envelope_hash"],
            episode_member_id=episode["member_id"],
            member_id=member["member_id"],
            member_epoch=member["member_epoch"],
            member_phase=member["phase"],
            member_tuple_hash=member["member_tuple_hash"],
            member_write_sequence=member["write_operation_seq"],
            member_basis_hash=member["current_basis_hash"],
            pending_effect_id=member["pending_effect_id"],
            status_version=status["status_version"],
            status_hash=status["status_hash"],
            status_reason=status["reason_code"],
            status_executor_hash=status["executor_token_hash"],
            status_help_due=status["help_due"],
            effect_id=effect["effect_id"],
            effect_outcome=effect["outcome_kind"],
            effect_outcome_sequence=effect["outcome_operation_seq"],
            effect_tuple_hash=(
                effect["outcome_tuple_hash"]
                if effect["outcome_kind"] is not None
                else effect["request_tuple_hash"]
            ),
            ledger_head_hash=effect["ledger_head_hash"],
            certificate_hash=effect["certificate_hash"],
            action_count=len(authority.actions),
            revision_token=authority.revision_token,
        )

    def read_revision(
        self, member_id: str, episode_id: str
    ) -> tuple | None:
        return self.store.read_selected_revision(
            member_id, episode_id=episode_id
        )


class RegistrationService:
    """Product flow: classify launch before registration, then register/drive/admit."""

    def __init__(
        self,
        *,
        coordinator: RegistrationCoordinator,
        admission: registration_admission.AdmissionController,
        collector: ObservationCollector,
        inventory: registration_admission.ToolInventory,
        helpers: Mapping[str, ActionHelper],
    ) -> None:
        self.coordinator = coordinator
        self.admission = admission
        self.collector = collector
        self.inventory = inventory
        self.helpers = helpers

    def handle(
        self, payload: object, discriminator: str
    ) -> registration_admission.AdmissionDecision:
        try:
            event = registration_admission.parse_registration_event(payload)
        except registration_admission.EventRefused:
            return registration_admission.AdmissionDecision(
                False,
                "PARSER_REJECT",
                registration_admission.PREIDENTITY_RESPONSE,
                0,
            )
        if discriminator in self.inventory.task_launch:
            return registration_admission.AdmissionDecision(
                False,
                "TASK_SUBAGENT_DENIED",
                registration_admission.render_reason(
                    "TASK_SUBAGENT_DENIED"
                ),
                0,
            )
        if discriminator not in self.inventory.ordinary:
            return registration_admission.AdmissionDecision(
                False,
                "UNKNOWN_DISCRIMINATOR",
                registration_admission.render_reason(
                    "UNKNOWN_DISCRIMINATOR"
                ),
                0,
            )
        try:
            observation = self.collector.collect_observation(event)
            preflight_reason = self.admission.preflight(
                event, discriminator, observation.basis_sample
            )
            if preflight_reason != "READY":
                return registration_admission.AdmissionDecision(
                    False,
                    preflight_reason,
                    registration_admission.render_reason(
                        preflight_reason
                    ),
                    0,
                )
            fresh_provider = lambda: self.collector.collect_observation(event)
            handle = self.coordinator.ensure(
                event,
                observation,
                fresh_provider=fresh_provider,
            )
            self.coordinator.drive(
                handle.member_id,
                self.helpers,
                fresh_provider=fresh_provider,
            )
        except RecoveryContainmentUnavailable:
            return registration_admission.AdmissionDecision(
                False,
                "CONTAINMENT_UNAVAILABLE",
                registration_admission.render_reason(
                    "CONTAINMENT_UNAVAILABLE"
                ),
                0,
            )
        except registration_admission.BasisUnavailable as exc:
            return registration_admission.AdmissionDecision(
                False,
                exc.reason,
                registration_admission.render_reason(exc.reason),
                0,
            )
        except registration_admission.EventRefused as exc:
            reason = (
                exc.reason
                if exc.reason
                in registration_admission.RUNTIME_REASONS
                else "ROOT_UNSUPPORTED"
            )
            return registration_admission.AdmissionDecision(
                False,
                reason,
                registration_admission.render_reason(reason),
                0,
            )
        except registration_store.InsufficientSpace:
            return registration_admission.AdmissionDecision(
                False,
                "STORAGE_DEGRADED",
                registration_admission.render_reason(
                    "STORAGE_DEGRADED"
                ),
                0,
            )
        except (
            registration_store.StoreError,
            sqlite3.Error,
            OSError,
            RuntimeError,
            ValueError,
            KeyError,
        ):
            return registration_admission.AdmissionDecision(
                False,
                "STORE_UNAVAILABLE",
                registration_admission.render_reason("STORE_UNAVAILABLE"),
                0,
            )
        return self.admission.admit(
            payload,
            discriminator,
            member_id=handle.member_id,
            episode_id=handle.episode_id,
        )
