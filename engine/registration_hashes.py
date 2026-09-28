"""Exact ADR 0025 row-hash preimages and deterministic identifiers."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from . import registration_jcs


@dataclass(frozen=True)
class Preimage:
    domain: str
    columns: tuple[str, ...]


def _columns(value: str) -> tuple[str, ...]:
    return tuple(value.split(","))


PREIMAGES: dict[str, Preimage] = {
    "protocol_hash": Preimage(
        "awa-reg-protocol-v4",
        _columns(
            "protocol_seq,protocol_generation,mode,schema_hash,profile_hash,runtime_capability_hash,writer_binary_hash,writer_capability_hash,tool_inventory_hash,hook_projection_hash,hook_matcher_mode,hook_matcher_hash,projection_receipt_hash,projection_file_generation,installer_identity_hash,installer_capability_hash,storage_dev,first_effect_id,staged_generation,staged_schema_hash,staged_profile_hash,staged_runtime_capability_hash,staged_writer_binary_hash,staged_writer_capability_hash,staged_tool_inventory_hash,staged_hook_projection_hash,staged_hook_matcher_mode,staged_hook_matcher_hash,staged_projection_receipt_hash,staged_projection_file_generation,staged_installer_identity_hash,staged_installer_capability_hash,staged_epoch_hash,transition_kind,transition_reason_code,previous_protocol_hash,drain_boot_id,drain_deadline_mono_ns,absence_proof_hash,quiescence_proof_hash,created_wall_ns"
        ),
    ),
    "staged_epoch_hash": Preimage(
        "awa-reg-staged-v2",
        _columns(
            "staged_generation,staged_schema_hash,staged_profile_hash,staged_runtime_capability_hash,staged_writer_binary_hash,staged_writer_capability_hash,staged_tool_inventory_hash,staged_hook_projection_hash,staged_hook_matcher_mode,staged_hook_matcher_hash,staged_projection_receipt_hash,staged_projection_file_generation,staged_installer_identity_hash,staged_installer_capability_hash"
        ),
    ),
    "member_tuple_hash": Preimage(
        "awa-reg-member-tuple-v2",
        _columns(
            "member_id,canonical_root,root_dev,root_ino,git_toplevel,git_dir,git_dir_dev,git_dir_ino,git_common_dir,git_common_dev,git_common_ino,proof_dev,projection_dev,legacy_state_dev,physical_basis_hash,git_basis_hash,policy_basis_hash,operation_basis_hash,lifecycle_basis_hash,current_basis_hash,member_epoch,phase,current_effect_id,runtime_subject_key,helper_generation,current_outcome_kind,current_completion_hash,current_proof_hash,current_certificate_hash,current_conflict_hash,pending_effect_id,pending_member_epoch,pending_basis_hash,pending_effect_tuple_hash"
        ),
    ),
    "episode_envelope_hash": Preimage(
        "awa-reg-episode-envelope-v2",
        _columns(
            "episode_id,conversation_id,generation_id,source_contract,source_event,protocol_generation,member_id,workspace_root_count,workspace_roots_hash,tool_inventory_hash,hook_projection_hash,created_wall_ns"
        ),
    ),
    "request_tuple_hash": Preimage(
        "awa-reg-request-tuple-v3",
        _columns(
            "effect_id,member_id,member_epoch,request_kind,request_basis_hash,predecessor_effect_id,required_protocol_generation,required_runtime_capability_hash,action_plan_hash,required_action_count,action_1_kind,action_1_hash,postcondition_1_hash,action_2_kind,action_2_hash,postcondition_2_hash,action_3_kind,action_3_hash,postcondition_3_hash,action_4_kind,action_4_hash,postcondition_4_hash,external_growth_reservation_bytes,outcome_reservation_bytes,successor_reservation_bytes"
        ),
    ),
    "outcome_tuple_hash": Preimage(
        "awa-reg-outcome-tuple-v2",
        _columns(
            "effect_id,outcome_kind,outcome_helper_generation,ledger_head_hash,first_conflict_event_seq,completion_hash,final_basis_hash,proof_hash,certificate_inputs_hash,certificate_hash,conflict_code,conflict_hash,superseded_by_effect_id,successor_transition_id"
        ),
    ),
    "ledger_hash": Preimage(
        "awa-reg-ledger-v2",
        _columns(
            "effect_id,event_seq,ordinal,action_kind,action_hash,postcondition_hash,observation_kind,observation_hash,prior_ledger_hash,external_growth_bytes,observed_wall_ns"
        ),
    ),
    "status_hash": Preimage(
        "awa-reg-status-v5",
        _columns(
            "subject_key,member_id,member_epoch,current_effect_id,status_version,schedule_boot_id,observed_now_mono_ns,next_due_mono_ns,due_since_mono_ns,attempt_count,backoff_ns,help_due,executor_token_hash,executor_boot_id,executor_generation,unavailable_count,yield_count,blocked_basis_fingerprint,reason_code"
        ),
    ),
    "operation_envelope_hash": Preimage(
        "awa-reg-operation-v6",
        _columns(
            "operation_seq,operation_id,operation_class,operation_kind,expected_revision,protocol_seq,expected_mode,expected_generation,expected_protocol_hash,runtime_capability_hash,writer_binary_hash,profile_hash,writer_capability_receipt_hash,installer_identity_hash,installer_capability_receipt_hash,protocol_lock_receipt_hash,control_binding_hash,target_member_id,target_effect_id,lineage_effect_id,target_successor_effect_id,target_executor_token_hash,expected_target_status_hash,target_episode_id,target_transition_id,target_subject_key,target_protocol_hash,target_staged_epoch_hash,expected_target_member_tuple_hash,expected_target_effect_tuple_hash,target_member_epoch,target_basis_hash,target_successor_member_epoch,target_successor_basis_hash,target_member_tuple_hash,target_effect_tuple_hash,target_effect_outcome_hash,target_action_plan_hash,target_cause_code,target_episode_hash,target_action_ledger_hash,target_status_hash,sample_boot_id,sample_mono_ns,measured_free_bytes,projected_db_growth_bytes,external_growth_bytes,new_external_reservation_bytes,new_outcome_reservation_bytes,new_successor_reservation_bytes,control_reserve_bytes,created_wall_ns"
        ),
    ),
}

BACKLINK_EXCLUSIONS = {
    "protocol": frozenset({"first_effect_operation_id", "operation_id", "protocol_hash"}),
    "member": frozenset(
        {
            "write_operation_seq",
            "write_operation_id",
            "write_operation_hash",
            "member_tuple_hash",
        }
    ),
    "status": frozenset(
        {
            "write_operation_seq",
            "write_operation_id",
            "write_operation_hash",
            "status_hash",
        }
    ),
    "action": frozenset(
        {
            "write_operation_seq",
            "write_operation_id",
            "write_operation_hash",
            "ledger_hash",
        }
    ),
    "episode": frozenset(
        {
            "write_operation_seq",
            "write_operation_id",
            "write_operation_hash",
            "envelope_hash",
        }
    ),
    "effect_request": frozenset(
        {
            "created_operation_seq",
            "created_operation_id",
            "created_operation_hash",
            "request_tuple_hash",
        }
    ),
    "effect_outcome": frozenset(
        {
            "outcome_operation_seq",
            "outcome_operation_id",
            "outcome_operation_hash",
            "outcome_tuple_hash",
        }
    ),
    "operation": frozenset({"operation_envelope_hash"}),
}


def derive(name: str, row: Mapping[str, Any]) -> str:
    try:
        preimage = PREIMAGES[name]
    except KeyError as exc:
        raise registration_jcs.JcsError(f"unknown preimage: {name}") from exc
    return registration_jcs.row_hash(preimage.domain, preimage.columns, row)


def deterministic_id(domain: str, *parts: str) -> str:
    framed = bytearray(domain.encode("ascii") + b"\0")
    for part in parts:
        encoded = part.encode("utf-8", "strict")
        framed.extend(len(encoded).to_bytes(8, "big"))
        framed.extend(encoded)
    return hashlib.sha256(framed).hexdigest()
