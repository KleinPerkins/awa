"""Stateless deterministic Body B status, rendering, and redacted metrics."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from . import registration_admission


@dataclass(frozen=True)
class RegistrationStatus:
    ready: bool
    reason: str
    member_id: str
    member_epoch: int
    phase: str
    outcome: str | None
    effect_id: str
    status_version: int
    protocol_generation: int
    protocol_mode: str


def project_status(
    authority: registration_admission.SelectedAuthorityView,
    host: registration_admission.HostEnvelope,
    *,
    event: registration_admission.RegistrationEvent,
    basis: registration_admission.BasisSample,
    receipt: registration_admission.DeploymentReceipt,
    expected_candidate_digest: str,
    episode_id: str,
    discriminator: str,
    inventory: registration_admission.ToolInventory,
) -> RegistrationStatus:
    reason = registration_admission.authority_reason(
        event=event,
        discriminator=discriminator,
        basis=basis,
        authority=authority,
        host=host,
        receipt=receipt,
        expected_candidate_digest=expected_candidate_digest,
        inventory=inventory,
        episode_id=episode_id,
    )
    return RegistrationStatus(
        ready=reason == "READY",
        reason=reason,
        member_id=authority.member_id,
        member_epoch=authority.member_epoch,
        phase=authority.member_phase,
        outcome=authority.effect_outcome,
        effect_id=authority.effect_id,
        status_version=authority.status_version,
        protocol_generation=authority.protocol_generation,
        protocol_mode=authority.protocol_mode,
    )
def render_status(snapshot: RegistrationStatus) -> str:
    return registration_admission.render_reason(snapshot.reason)


def status_json(snapshot: RegistrationStatus) -> bytes:
    return (
        json.dumps(
            asdict(snapshot),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        + "\n"
    ).encode("ascii")


def product_metrics(snapshot: RegistrationStatus) -> dict[str, object]:
    return {
        "registration_ready": 1 if snapshot.ready else 0,
        "reason_code": snapshot.reason,
        "phase": snapshot.phase,
        "outcome": snapshot.outcome,
        "member_epoch": snapshot.member_epoch,
        "status_version": snapshot.status_version,
        "protocol_generation": snapshot.protocol_generation,
    }


def adr0020_component(snapshot: RegistrationStatus) -> dict[str, object]:
    if snapshot.ready:
        severity = "green"
    elif snapshot.reason in {
        "STORE_UNAVAILABLE",
        "STORAGE_RED",
        "CONTAINMENT",
        "CONTAINMENT_UNAVAILABLE",
    }:
        severity = "red"
    else:
        severity = "degraded"
    return {
        "id": "registration_authority",
        "severity": severity,
        "reason_code": snapshot.reason,
        "member_id": snapshot.member_id,
        "effect_id": snapshot.effect_id,
        "member_epoch": snapshot.member_epoch,
        "protocol_generation": snapshot.protocol_generation,
    }
