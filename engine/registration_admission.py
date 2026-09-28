"""Body B revision-fenced ordinary-tool admission and launch denial."""

from __future__ import annotations

import os
import re
import json
import hashlib
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from . import registration_hashes
from .registration_schema import SCHEMA_SHA256


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_TOP_LEVEL_KEYS = frozenset(
    {
        "hook_event_name",
        "event",
        "workspace_roots",
        "cwd",
        "workspaceRoot",
        "workspace_path",
        "root",
        "projectRoot",
        "conversation_id",
        "conversationId",
        "generation_id",
        "generationId",
        "session_id",
        "sessionId",
        "tool_input",
        "tool_name",
        "server_name",
        "command",
        "model",
        "transcript_path",
        "prompt",
        "attachments",
    }
)
PREIDENTITY_RESPONSE = (
    "AWA registration could not identify exactly one supported workspace. "
    "Open one clean linked worktree and retry."
)


class EventRefused(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class BasisUnavailable(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class RegistrationEvent:
    workspace_roots: tuple[str, ...]
    conversation_id: str
    generation_id: str
    source_contract: str
    source_event: str

    @property
    def root(self) -> str:
        return self.workspace_roots[0]


@dataclass(frozen=True)
class BasisSample:
    canonical_root: str
    canonical_root_hash: str
    member_id: str
    current_basis_hash: str
    physical_basis_hash: str
    git_basis_hash: str
    policy_basis_hash: str
    operation_basis_hash: str
    lifecycle_basis_hash: str
    workspace_roots_hash: str = "0" * 64


@dataclass(frozen=True)
class ToolInventory:
    ordinary: frozenset[str]
    task_launch: frozenset[str]

    def __post_init__(self) -> None:
        if self.ordinary & self.task_launch:
            raise ValueError("ordinary/task inventory overlap")
        if not self.ordinary or not self.task_launch:
            raise ValueError("tool inventory must be closed and nonempty")
        if any(
            not isinstance(value, str)
            or not value
            or len(value.encode("utf-8")) > 128
            or "*" in value
            for value in self.ordinary | self.task_launch
        ):
            raise ValueError("invalid tool discriminator")


@dataclass(frozen=True)
class DeploymentReceipt:
    owner_mode: str
    deployment_scope: str
    candidate_digest: str
    canonical_root_hash: str | None
    member_id: str | None
    owner_gate_digest: str

    def __post_init__(self) -> None:
        if self.owner_mode != "DIRECT":
            raise ValueError("deployment receipt owner must be DIRECT")
        for field in ("candidate_digest", "owner_gate_digest"):
            if not _hex64(getattr(self, field)):
                raise ValueError(f"{field} must be lowercase 64-hex")
        if self.deployment_scope == "R1_CANARY":
            if not _hex64(self.canonical_root_hash) or not _hex64(
                self.member_id
            ):
                raise ValueError("R1 receipt requires root/member scope")
        elif self.deployment_scope in {"R2_DIRECT", "R0_THROWAWAY"}:
            if (
                self.canonical_root_hash is not None
                or self.member_id is not None
            ):
                raise ValueError("broad/predeployment receipt scope must be null")
        else:
            raise ValueError("unknown deployment scope")


@dataclass(frozen=True)
class HostEnvelope:
    host_tick_current: bool
    profile_hash: str
    projection_hash: str
    inventory_hash: str
    storage_ready: bool
    parser_ready: bool
    serializer_ready: bool
    lifecycle_ready: bool = True
    proof_ready: bool = True


@dataclass(frozen=True)
class SelectedAuthorityView:
    protocol_seq: int
    protocol_hash: str
    protocol_generation: int
    protocol_mode: str
    protocol_schema_hash: str
    profile_hash: str
    runtime_capability_hash: str
    tool_inventory_hash: str
    hook_projection_hash: str
    episode_id: str
    episode_envelope_hash: str
    episode_member_id: str
    member_id: str
    member_epoch: int
    member_phase: str
    member_tuple_hash: str
    member_write_sequence: int
    member_basis_hash: str
    pending_effect_id: str | None
    status_version: int
    status_hash: str
    status_reason: str | None
    status_executor_hash: str | None
    status_help_due: int
    effect_id: str
    effect_outcome: str | None
    effect_outcome_sequence: int | None
    effect_tuple_hash: str | None
    ledger_head_hash: str | None
    certificate_hash: str | None
    action_count: int
    revision_token: tuple[Any, ...]


@dataclass(frozen=True)
class AdmissionDecision:
    allowed: bool
    reason: str
    response: str
    attempts: int


class BasisCollector(Protocol):
    def collect(self, event: RegistrationEvent) -> BasisSample: ...


class AuthorityReader(Protocol):
    def read_view(
        self, member_id: str, episode_id: str
    ) -> SelectedAuthorityView | None: ...

    def read_revision(
        self, member_id: str, episode_id: str
    ) -> tuple[Any, ...] | None: ...


def _hex64(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def canonical_root_hash(root: str) -> str:
    if (
        not isinstance(root, str)
        or not os.path.isabs(root)
        or os.path.normpath(root) != root
        or "\x00" in root
    ):
        raise ValueError("canonical root must be normalized and absolute")
    return hashlib.sha256(
        b"awa-registration-canonical-root/v1\0"
        + root.encode("utf-8", "strict")
    ).hexdigest()


def _sources(value: object) -> list[dict]:
    if not isinstance(value, dict):
        raise EventRefused("PARSER_REJECT")
    if set(value) - _TOP_LEVEL_KEYS:
        raise EventRefused("PARSER_REJECT")
    result = [value]
    nested = value.get("tool_input")
    if nested is not None:
        if not isinstance(nested, dict):
            raise EventRefused("PARSER_REJECT")
        result.append(nested)
    return result


def _one_string(
    sources: list[dict], keys: tuple[str, ...], *, required: str
) -> str:
    if not any(required in source for source in sources):
        raise EventRefused("PARSER_REJECT")
    values = [
        source[key]
        for source in sources
        for key in keys
        if key in source
    ]
    if (
        not values
        or any(
            not isinstance(value, str)
            or value != value.strip()
            or _IDENTIFIER.fullmatch(value) is None
            for value in values
        )
        or len(set(values)) != 1
    ):
        raise EventRefused("PARSER_REJECT")
    return str(values[0])


def parse_registration_event(value: object) -> RegistrationEvent:
    sources = _sources(value)
    top = sources[0]
    if not all(
        key in top
        for key in (
            "hook_event_name",
            "workspace_roots",
            "conversation_id",
            "generation_id",
        )
    ):
        raise EventRefused("PARSER_REJECT")
    root_arrays = [
        source["workspace_roots"]
        for source in sources
        if "workspace_roots" in source
    ]
    if (
        not root_arrays
        or any(
            not isinstance(array, list)
            or len(array) != 1
            or not isinstance(array[0], str)
            or array[0] != array[0].strip()
            or "\x00" in array[0]
            or not os.path.isabs(array[0])
            or os.path.normpath(array[0]) != array[0]
            or (
                os.path.exists(array[0])
                and (
                    not os.path.isdir(array[0])
                    or os.path.realpath(array[0]) != array[0]
                )
            )
            for array in root_arrays
        )
    ):
        raise EventRefused("ROOT_COUNT_UNSUPPORTED")
    roots = {array[0] for array in root_arrays}
    for source in sources:
        for key in (
            "cwd",
            "workspaceRoot",
            "workspace_path",
            "root",
            "projectRoot",
        ):
            if key in source:
                candidate = source[key]
                if (
                    not isinstance(candidate, str)
                    or candidate != candidate.strip()
                    or candidate not in roots
                ):
                    raise EventRefused("ROOT_COUNT_UNSUPPORTED")
    if len(roots) != 1:
        raise EventRefused("ROOT_COUNT_UNSUPPORTED")
    conversation = _one_string(
        sources,
        ("conversation_id", "conversationId"),
        required="conversation_id",
    )
    generation = _one_string(
        sources,
        ("generation_id", "generationId"),
        required="generation_id",
    )
    event = _one_string(
        sources,
        ("hook_event_name", "event"),
        required="hook_event_name",
    )
    sessions = [
        source[key]
        for source in sources
        for key in ("session_id", "sessionId")
        if key in source
    ]
    if sessions and (
        any(
            not isinstance(session, str)
            or _IDENTIFIER.fullmatch(session) is None
            for session in sessions
        )
        or len(set(sessions)) != 1
        or sessions[0] != conversation
    ):
        raise EventRefused("PARSER_REJECT")
    return RegistrationEvent(
        workspace_roots=(next(iter(roots)),),
        conversation_id=conversation,
        generation_id=generation,
        source_contract="cursor-hook/v1",
        source_event=event,
    )


def parse_registration_event_bytes(raw: bytes) -> RegistrationEvent:
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= 65_536:
        raise EventRefused("PARSER_REJECT")

    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise EventRefused("PARSER_REJECT")
            value[key] = item
        return value

    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                EventRefused("PARSER_REJECT")
            ),
        )
    except EventRefused:
        raise
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise EventRefused("PARSER_REJECT") from exc
    return parse_registration_event(value)


_RESPONSES = {
    "READY": "AWA registration is ready.",
    "REGISTRATION_REQUIRED": "AWA registration is not complete.",
    "EFFECT_IN_FLIGHT": "AWA registration work is still in progress.",
    "RESOLVER_UNAVAILABLE": "AWA registration recovery is temporarily unavailable.",
    "BASIS_UNSTABLE": "AWA workspace identity changed during admission; retry.",
    "BASIS_TIMEOUT": "AWA could not finish reading workspace identity in time.",
    "DIRTY_UNSUPPORTED": "AWA requires a clean linked worktree; preserve work first.",
    "GIT_OPERATION_UNSUPPORTED": "AWA requires the Git operation to finish first.",
    "EFFECT_CONFLICT": "AWA registration found a lifecycle conflict.",
    "STORE_FAILURE": "AWA registration storage reported a durable failure.",
    "PROTOCOL_INCOMPATIBLE": "AWA registration protocol is not writable.",
    "HOOK_UNSUPPORTED": "AWA hook projection is not current.",
    "TASK_SUBAGENT_DENIED": (
        "AWA does not admit Task, subagent, or agent-launch tools in M1."
    ),
    "UNKNOWN_DISCRIMINATOR": "AWA does not recognize this tool invocation.",
    "TOOL_NOT_IN_INVENTORY": "AWA has not admitted this tool inventory entry.",
    "STORE_UNAVAILABLE": "AWA registration authority is unavailable.",
    "STORAGE_DEGRADED": "AWA registration storage needs more free space.",
    "STORAGE_RED": "AWA registration storage is not ready.",
    "DEVICE_MISMATCH": "AWA requires registration paths on one APFS device.",
    "HOST_STARVED": "AWA host reconciliation is stale.",
    "ROOT_COUNT_UNSUPPORTED": "AWA requires exactly one workspace root.",
    "ROOT_UNSUPPORTED": "AWA supports only the authorized clean linked root.",
    "BOOT_ID_UNAVAILABLE": "AWA could not establish the current boot identity.",
    "PARSER_REJECT": "AWA rejected the event envelope.",
    "SERIALIZER_INVALID": "AWA response serialization is unavailable.",
    "CONTAINMENT": "AWA registration is contained pending repair.",
    "CONTAINMENT_UNAVAILABLE": "AWA could not commit containment authority.",
}
RUNTIME_REASONS = tuple(
    reason for reason in _RESPONSES if reason != "READY"
)
if len(RUNTIME_REASONS) != 26:
    raise RuntimeError("Body B runtime reason budget drift")


def render_reason(reason: str) -> str:
    return _RESPONSES.get(
        reason, "AWA registration authority is unavailable."
    )


def authority_reason(
    *,
    event: RegistrationEvent,
    discriminator: str,
    basis: BasisSample,
    authority: SelectedAuthorityView,
    host: HostEnvelope,
    receipt: DeploymentReceipt,
    expected_candidate_digest: str,
    inventory: ToolInventory,
    episode_id: str,
) -> str:
    expected_episode_id = registration_hashes.deterministic_id(
        "awa-reg-episode-v1",
        event.conversation_id,
        event.generation_id,
        event.source_contract,
        event.source_event,
        str(authority.protocol_generation),
        basis.member_id,
        basis.workspace_roots_hash,
        authority.tool_inventory_hash,
        authority.hook_projection_hash,
    )
    if (
        authority.protocol_schema_hash != SCHEMA_SHA256
        or authority.protocol_mode != "WRITABLE"
    ):
        return "PROTOCOL_INCOMPATIBLE"
    if (
        authority.member_id != basis.member_id
        or authority.member_id != authority.episode_member_id
        or authority.episode_id != episode_id
        or episode_id != expected_episode_id
        or authority.member_basis_hash != basis.current_basis_hash
    ):
        return "REGISTRATION_REQUIRED"
    if authority.member_phase == "REQUESTED":
        return authority.status_reason or "REGISTRATION_REQUIRED"
    if authority.member_phase == "EFFECT_IN_FLIGHT":
        return authority.status_reason or "EFFECT_IN_FLIGHT"
    if authority.member_phase != "RESOLVED":
        return "STORE_UNAVAILABLE"
    if authority.effect_outcome == "LOGICAL_CONFLICT":
        return "EFFECT_CONFLICT"
    if (
        authority.effect_outcome != "SUCCESS"
        or authority.pending_effect_id is not None
        or authority.action_count != 4
        or authority.certificate_hash is None
        or authority.status_executor_hash is not None
        or authority.status_help_due != 0
        or authority.status_reason is not None
    ):
        return "REGISTRATION_REQUIRED"
    if not host.host_tick_current:
        return "HOST_STARVED"
    if not host.storage_ready:
        return "STORAGE_RED"
    if not host.parser_ready:
        return "PARSER_REJECT"
    if not host.serializer_ready:
        return "SERIALIZER_INVALID"
    if not host.lifecycle_ready or not host.proof_ready:
        return "REGISTRATION_REQUIRED"
    if (
        host.profile_hash != authority.profile_hash
        or host.projection_hash != authority.hook_projection_hash
        or host.inventory_hash != authority.tool_inventory_hash
        or discriminator not in inventory.ordinary
    ):
        return "HOOK_UNSUPPORTED"
    if (
        receipt.owner_mode != "DIRECT"
        or receipt.candidate_digest != expected_candidate_digest
    ):
        return "PROTOCOL_INCOMPATIBLE"
    if receipt.deployment_scope == "R1_CANARY":
        if (
            receipt.canonical_root_hash != basis.canonical_root_hash
            or receipt.member_id != basis.member_id
        ):
            return "ROOT_UNSUPPORTED"
    elif receipt.deployment_scope == "R2_DIRECT":
        if (
            receipt.canonical_root_hash is not None
            or receipt.member_id is not None
        ):
            return "PROTOCOL_INCOMPATIBLE"
    elif receipt.deployment_scope == "R0_THROWAWAY":
        # R0 is predeployment evidence only and is forbidden as runtime
        # deployment authority by accepted v3.
        return "PROTOCOL_INCOMPATIBLE"
    else:
        return "PROTOCOL_INCOMPATIBLE"
    return "READY"


class AdmissionController:
    def __init__(
        self,
        *,
        inventory: ToolInventory,
        collector: BasisCollector,
        store: AuthorityReader,
        host_provider: Callable[[], HostEnvelope],
        receipt_provider: Callable[[], DeploymentReceipt],
        expected_candidate_digest: str,
    ) -> None:
        self.inventory = inventory
        self.collector = collector
        self.store = store
        self.host_provider = host_provider
        self.receipt_provider = receipt_provider
        self.expected_candidate_digest = expected_candidate_digest

    def preflight(
        self,
        event: RegistrationEvent,
        discriminator: str,
        basis: BasisSample,
    ) -> str:
        host = self.host_provider()
        if not host.parser_ready:
            return "PARSER_REJECT"
        if not host.serializer_ready:
            return "SERIALIZER_INVALID"
        if not host.storage_ready:
            return "STORAGE_RED"
        if discriminator not in self.inventory.ordinary:
            return "TOOL_NOT_IN_INVENTORY"
        receipt = self.receipt_provider()
        if (
            receipt.owner_mode != "DIRECT"
            or receipt.candidate_digest != self.expected_candidate_digest
        ):
            return "PROTOCOL_INCOMPATIBLE"
        if receipt.deployment_scope == "R1_CANARY":
            if (
                receipt.canonical_root_hash != basis.canonical_root_hash
                or receipt.member_id != basis.member_id
                or basis.canonical_root != event.root
            ):
                return "ROOT_UNSUPPORTED"
        elif receipt.deployment_scope == "R2_DIRECT":
            if (
                receipt.canonical_root_hash is not None
                or receipt.member_id is not None
            ):
                return "PROTOCOL_INCOMPATIBLE"
        else:
            return "PROTOCOL_INCOMPATIBLE"
        return "READY"

    def admit(
        self,
        payload: object,
        discriminator: str,
        *,
        member_id: str,
        episode_id: str,
    ) -> AdmissionDecision:
        try:
            event = parse_registration_event(payload)
        except EventRefused:
            return AdmissionDecision(
                False, "PARSER_REJECT", PREIDENTITY_RESPONSE, 0
            )
        if discriminator in self.inventory.task_launch:
            return self._deny("TASK_SUBAGENT_DENIED", 0)
        if discriminator not in self.inventory.ordinary:
            return self._deny("UNKNOWN_DISCRIMINATOR", 0)
        last_reason = "STORE_UNAVAILABLE"
        for attempt in (1, 2):
            try:
                basis_one = self.collector.collect(event)
                authority = self.store.read_view(member_id, episode_id)
                basis_two = self.collector.collect(event)
                revision = self.store.read_revision(member_id, episode_id)
            except BasisUnavailable as exc:
                last_reason = exc.reason
                continue
            except Exception:
                last_reason = "STORE_UNAVAILABLE"
                continue
            if (
                authority is None
                or basis_one != basis_two
                or basis_two.canonical_root != event.root
                or basis_two.member_id != member_id
                or authority.episode_id != episode_id
                or authority.revision_token != revision
            ):
                last_reason = (
                    "BASIS_UNSTABLE"
                    if basis_one != basis_two
                    else "STORE_UNAVAILABLE"
                )
                continue
            reason = authority_reason(
                event=event,
                discriminator=discriminator,
                basis=basis_two,
                authority=authority,
                host=self.host_provider(),
                receipt=self.receipt_provider(),
                expected_candidate_digest=self.expected_candidate_digest,
                inventory=self.inventory,
                episode_id=episode_id,
            )
            if reason == "READY":
                return AdmissionDecision(
                    True, "READY", render_reason("READY"), attempt
                )
            return self._deny(reason, attempt)
        return self._deny(last_reason, 2)

    @staticmethod
    def _deny(reason: str, attempts: int) -> AdmissionDecision:
        return AdmissionDecision(
            False, reason, render_reason(reason), attempts
        )
