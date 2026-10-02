"""Body B registration orchestration, replay, reboot, and fair retry."""

from __future__ import annotations

import multiprocessing
import os
import secrets
import sqlite3
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol

from . import (
    lifecycle,
    native_entry,
    registration_admission,
    registration_hashes,
    registration_jcs,
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


@dataclass(frozen=True)
class BasisObservation:
    identity: registration_store.MemberIdentity
    request_kind: str
    workspace_roots_hash: str
    blocked_basis_fingerprint: str | None

    @classmethod
    def from_identity(
        cls,
        identity: registration_store.MemberIdentity,
        *,
        request_kind: str,
        workspace_roots_hash: str,
        blocked_basis_fingerprint: str | None = None,
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
    ) -> RegistrationHandle:
        if observation.identity.canonical_root != event.root:
            raise registration_admission.EventRefused("ROOT_UNSUPPORTED")
        intent = _intent(observation)
        member_id = self.store.find_member_id(observation.identity)
        if member_id is None:
            self.store.install_member(
                self.data,
                self.candidate,
                observation.identity,
                intent,
            )
            member_id = derive_member_id(observation.identity)
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
            observation.workspace_roots_hash,
            protocol["tool_inventory_hash"],
            protocol["hook_projection_hash"],
        )
        if not self.store.episode_exists(member_id, episode_id):
            self.store.bind_episode(
                self.data,
                self.candidate,
                member_id=member_id,
                source=registration_store.EpisodeSource(
                    event.conversation_id,
                    event.generation_id,
                    event.source_contract,
                    event.source_event,
                    observation.workspace_roots_hash,
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
            self.store.handoff_resolved(
                self.data,
                self.candidate,
                member_id=member_id,
                expected_member_hash=member["member_tuple_hash"],
                expected_effect_hash=authority.effect[
                    "outcome_tuple_hash"
                ],
                expected_status_hash=authority.status["status_hash"],
            )
            successor = self.store.read_selected_authority(member_id)
            if (
                successor.member["current_basis_hash"]
                != intent.request_basis_hash
            ):
                self.store.invalidate_requested(
                    self.data,
                    self.candidate,
                    member_id=member_id,
                    expected_member_hash=successor.member[
                        "member_tuple_hash"
                    ],
                    expected_effect_hash=successor.effect[
                        "request_tuple_hash"
                    ],
                    expected_status_hash=successor.status["status_hash"],
                    basis=observation.basis_update,
                    intent=intent,
                )
            return RegistrationHandle(member_id, episode_id)
        if member["current_basis_hash"] != intent.request_basis_hash:
            if member["phase"] == "REQUESTED":
                self.store.invalidate_requested(
                    self.data,
                    self.candidate,
                    member_id=member_id,
                    expected_member_hash=member["member_tuple_hash"],
                    expected_effect_hash=authority.effect[
                        "request_tuple_hash"
                    ],
                    expected_status_hash=authority.status["status_hash"],
                    basis=observation.basis_update,
                    intent=intent,
                )
            elif member["phase"] == "EFFECT_IN_FLIGHT":
                if member["pending_effect_id"] is None:
                    self.store.set_pending(
                        self.data,
                        self.candidate,
                        member_id=member_id,
                        expected_member_hash=member["member_tuple_hash"],
                        expected_effect_hash=authority.effect[
                            "request_tuple_hash"
                        ],
                        expected_status_hash=authority.status["status_hash"],
                        basis_hash=intent.request_basis_hash,
                        intent=intent,
                    )
                else:
                    self.store.replace_pending(
                        self.data,
                        self.candidate,
                        member_id=member_id,
                        expected_member_hash=member["member_tuple_hash"],
                        expected_effect_hash=member[
                            "pending_effect_tuple_hash"
                        ],
                        expected_status_hash=authority.status["status_hash"],
                        basis_hash=intent.request_basis_hash,
                        intent=intent,
                    )
            elif member["phase"] == "RESOLVED":
                self.store.handoff_resolved(
                    self.data,
                    self.candidate,
                    member_id=member_id,
                    expected_member_hash=member["member_tuple_hash"],
                    expected_effect_hash=authority.effect[
                        "outcome_tuple_hash"
                    ],
                    expected_status_hash=authority.status["status_hash"],
                    cause="BASIS_CHANGED",
                    basis=observation.basis_update,
                    intent=intent,
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
        current_basis_hash: str,
    ) -> registration_store.MemberExecution:
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
            authority = self.store.read_selected_authority(due.member_id)
            if (
                authority is None
                or authority.member["pending_effect_id"] is None
            ):
                raise registration_store.StaleAuthority(
                    "RESOLVED due member has no pending handoff"
                )
            self.store.handoff_resolved(
                self.data,
                self.candidate,
                member_id=due.member_id,
                expected_member_hash=authority.member[
                    "member_tuple_hash"
                ],
                expected_effect_hash=authority.effect[
                    "outcome_tuple_hash"
                ],
                expected_status_hash=authority.status["status_hash"],
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
    ) -> DriveResult:
        authority = self.store.read_selected_authority(member_id)
        if authority is None:
            raise registration_store.StoreUnavailable("member missing")
        phase = authority.member["phase"]
        if phase == "RESOLVED":
            if authority.member["pending_effect_id"] is not None:
                self.store.handoff_resolved(
                    self.data,
                    self.candidate,
                    member_id=member_id,
                    expected_member_hash=authority.member[
                        "member_tuple_hash"
                    ],
                    expected_effect_hash=authority.effect[
                        "outcome_tuple_hash"
                    ],
                    expected_status_hash=authority.status["status_hash"],
                )
                return self.drive(member_id, helpers)
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
            self.store.mark_unavailable(
                self.data, self.candidate, execution
            )
            return DriveResult(
                execution.member_id, execution.effect_id, "UNAVAILABLE"
            )

    def _contain_helper_failure(
        self, execution: registration_store.MemberExecution
    ) -> None:
        try:
            self.store.mark_unavailable(
                self.data, self.candidate, execution
            )
        except Exception:
            execution.close()
            try:
                self.store.mark_dead_executor_unavailable(
                    self.data,
                    self.candidate,
                    member_id=execution.member_id,
                    expected_status_hash=execution.target_status_hash,
                )
            except Exception:
                pass

    def recover_reboot(self, current_boot_id: str) -> tuple[str, ...]:
        recovered = []
        for candidate in self.store.list_reboot_candidates(current_boot_id):
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
    ) -> registration_store.OperationResult:
        authority = self.store.read_selected_authority(member_id)
        if (
            authority is None
            or authority.member["phase"] != "EFFECT_IN_FLIGHT"
            or authority.status["executor_token_hash"] is None
        ):
            raise registration_store.StaleAuthority(
                "same-boot recovery requires stored executor"
            )
        return self.store.mark_dead_executor_unavailable(
            self.data,
            self.candidate,
            member_id=member_id,
            expected_status_hash=authority.status["status_hash"],
        )

    def retry_conflict(
        self, member_id: str, observation: BasisObservation
    ) -> registration_store.OperationResult:
        return self._handoff(
            member_id, observation, "EXPLICIT_CONFLICT_RETRY"
        )

    def repair_closure(
        self, member_id: str, observation: BasisObservation
    ) -> registration_store.OperationResult:
        return self._handoff(
            member_id, observation, "CURRENT_CLOSURE_CHANGED"
        )

    def _handoff(
        self,
        member_id: str,
        observation: BasisObservation,
        cause: str,
    ) -> registration_store.OperationResult:
        authority = self.store.read_selected_authority(member_id)
        if authority is None or authority.member["phase"] != "RESOLVED":
            raise registration_store.StaleAuthority(
                "handoff requires RESOLVED member"
            )
        return self.store.handoff_resolved(
            self.data,
            self.candidate,
            member_id=member_id,
            expected_member_hash=authority.member["member_tuple_hash"],
            expected_effect_hash=authority.effect["outcome_tuple_hash"],
            expected_status_hash=authority.status["status_hash"],
            cause=cause,
            basis=observation.basis_update,
            intent=_intent(observation),
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
    ) -> TickReceipt:
        if open_mutates_authority and yield_result is None:
            raise ValueError(
                "mutating lane opens require an exact yield resolver"
            )
        selected = self.store.list_due_candidates(
            boot_id=boot_id,
            now_mono_ns=now_mono_ns,
            limit=TICK_LANES,
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
                    self.store.mark_dead_executor_unavailable(
                        self.data,
                        self.candidate,
                        member_id=member_id,
                        expected_status_hash=authority.status["status_hash"],
                    )
                recovered.append(member_id)
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
            self.store.mark_dead_executor_unavailable(
                self.data,
                self.candidate,
                member_id=candidate.member_id,
                expected_status_hash=token.target_status_hash,
            )
            return True
        except Exception:
            authority = self.store.read_selected_authority(
                candidate.member_id
            )
            return bool(
                authority is not None
                and authority.status["executor_token_hash"] is None
            )


_FAILED = object()


def _process_calls(jobs, *, timeout: float) -> dict[str, object]:
    context = multiprocessing.get_context("spawn")
    workers = {}
    for member_id, function, argument in jobs:
        receiving, sending = context.Pipe(duplex=False)
        process = context.Process(
            target=_call_process,
            args=(function, argument, sending),
        )
        process.start()
        sending.close()
        workers[member_id] = (process, receiving)
    # The deadline starts only after every lane process has started. Each
    # worker therefore receives the same full concurrent batch window;
    # sequential joins below only reap against that shared absolute bound.
    deadline = time.monotonic() + timeout
    results = {}
    for member_id, (process, receiving) in workers.items():
        process.join(max(0.0, deadline - time.monotonic()))
        if process.is_alive():
            process.terminate()
            process.join(0.25)
        if process.is_alive():
            process.kill()
            process.join()
        if process.exitcode == 0 and receiving.poll():
            status, value = receiving.recv()
            results[member_id] = value if status == "ok" else _FAILED
        else:
            results[member_id] = _FAILED
        receiving.close()
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
            handle = self.coordinator.ensure(event, observation)
            self.coordinator.drive(handle.member_id, self.helpers)
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
