CREATE TABLE registration_protocol_epoch(
 protocol_seq INTEGER NOT NULL PRIMARY KEY CHECK(protocol_seq>=1),
 protocol_generation INTEGER NOT NULL CHECK(protocol_generation>=1),
 mode TEXT NOT NULL CHECK(mode IN('DORMANT','WRITABLE','DRAINING','CONTAINMENT')),
 schema_hash TEXT NOT NULL CHECK(length(schema_hash)=64 AND schema_hash NOT GLOB '*[^0-9a-f]*'),
 profile_hash TEXT NOT NULL CHECK(length(profile_hash)=64 AND profile_hash NOT GLOB '*[^0-9a-f]*'),
 runtime_capability_hash TEXT NOT NULL CHECK(length(runtime_capability_hash)=64 AND runtime_capability_hash NOT GLOB '*[^0-9a-f]*'),
 writer_binary_hash TEXT NOT NULL CHECK(length(writer_binary_hash)=64 AND writer_binary_hash NOT GLOB '*[^0-9a-f]*'),
 writer_capability_hash TEXT NOT NULL CHECK(length(writer_capability_hash)=64 AND writer_capability_hash NOT GLOB '*[^0-9a-f]*'),
 tool_inventory_hash TEXT NOT NULL CHECK(length(tool_inventory_hash)=64 AND tool_inventory_hash NOT GLOB '*[^0-9a-f]*'),
 hook_projection_hash TEXT NOT NULL CHECK(length(hook_projection_hash)=64 AND hook_projection_hash NOT GLOB '*[^0-9a-f]*'),
 hook_matcher_mode TEXT NOT NULL CHECK(hook_matcher_mode IN('CATCH_ALL','ENUMERATED')),
 hook_matcher_hash TEXT NOT NULL CHECK(length(hook_matcher_hash)=64 AND hook_matcher_hash NOT GLOB '*[^0-9a-f]*'),
 projection_receipt_hash TEXT NOT NULL CHECK(length(projection_receipt_hash)=64 AND projection_receipt_hash NOT GLOB '*[^0-9a-f]*'),
 projection_file_generation INTEGER NOT NULL CHECK(projection_file_generation>=1),
 installer_identity_hash TEXT NOT NULL CHECK(length(installer_identity_hash)=64 AND installer_identity_hash NOT GLOB '*[^0-9a-f]*'),
 installer_capability_hash TEXT NOT NULL CHECK(length(installer_capability_hash)=64 AND installer_capability_hash NOT GLOB '*[^0-9a-f]*'),
 storage_dev INTEGER NOT NULL CHECK(storage_dev>=0),
 first_effect_id TEXT CHECK(first_effect_id IS NULL OR (length(first_effect_id)=64 AND first_effect_id NOT GLOB '*[^0-9a-f]*')),
 first_effect_operation_id TEXT CHECK(first_effect_operation_id IS NULL OR (length(first_effect_operation_id)=64 AND first_effect_operation_id NOT GLOB '*[^0-9a-f]*')),
 staged_generation INTEGER CHECK(staged_generation IS NULL OR staged_generation>=2),
 staged_schema_hash TEXT CHECK(staged_schema_hash IS NULL OR (length(staged_schema_hash)=64 AND staged_schema_hash NOT GLOB '*[^0-9a-f]*')),
 staged_profile_hash TEXT CHECK(staged_profile_hash IS NULL OR (length(staged_profile_hash)=64 AND staged_profile_hash NOT GLOB '*[^0-9a-f]*')),
 staged_runtime_capability_hash TEXT CHECK(staged_runtime_capability_hash IS NULL OR (length(staged_runtime_capability_hash)=64 AND staged_runtime_capability_hash NOT GLOB '*[^0-9a-f]*')),
 staged_writer_binary_hash TEXT CHECK(staged_writer_binary_hash IS NULL OR (length(staged_writer_binary_hash)=64 AND staged_writer_binary_hash NOT GLOB '*[^0-9a-f]*')),
 staged_writer_capability_hash TEXT CHECK(staged_writer_capability_hash IS NULL OR (length(staged_writer_capability_hash)=64 AND staged_writer_capability_hash NOT GLOB '*[^0-9a-f]*')),
 staged_tool_inventory_hash TEXT CHECK(staged_tool_inventory_hash IS NULL OR (length(staged_tool_inventory_hash)=64 AND staged_tool_inventory_hash NOT GLOB '*[^0-9a-f]*')),
 staged_hook_projection_hash TEXT CHECK(staged_hook_projection_hash IS NULL OR (length(staged_hook_projection_hash)=64 AND staged_hook_projection_hash NOT GLOB '*[^0-9a-f]*')),
 staged_hook_matcher_mode TEXT CHECK(staged_hook_matcher_mode IS NULL OR staged_hook_matcher_mode IN('CATCH_ALL','ENUMERATED')),
 staged_hook_matcher_hash TEXT CHECK(staged_hook_matcher_hash IS NULL OR (length(staged_hook_matcher_hash)=64 AND staged_hook_matcher_hash NOT GLOB '*[^0-9a-f]*')),
 staged_projection_receipt_hash TEXT CHECK(staged_projection_receipt_hash IS NULL OR (length(staged_projection_receipt_hash)=64 AND staged_projection_receipt_hash NOT GLOB '*[^0-9a-f]*')),
 staged_projection_file_generation INTEGER CHECK(staged_projection_file_generation IS NULL OR staged_projection_file_generation>=1),
 staged_installer_identity_hash TEXT CHECK(staged_installer_identity_hash IS NULL OR (length(staged_installer_identity_hash)=64 AND staged_installer_identity_hash NOT GLOB '*[^0-9a-f]*')),
 staged_installer_capability_hash TEXT CHECK(staged_installer_capability_hash IS NULL OR (length(staged_installer_capability_hash)=64 AND staged_installer_capability_hash NOT GLOB '*[^0-9a-f]*')),
 staged_epoch_hash TEXT CHECK(staged_epoch_hash IS NULL OR (length(staged_epoch_hash)=64 AND staged_epoch_hash NOT GLOB '*[^0-9a-f]*')),
 transition_kind TEXT NOT NULL CHECK(transition_kind IN('BOOTSTRAP','ACTIVATE','FIRST_EFFECT','BEGIN_DRAIN','STAGE_NEXT','CANCEL_DRAIN','ADVANCE_GENERATION','PRE_EFFECT_DORMANT','ENTER_CONTAINMENT','BEGIN_REPAIR')),
 transition_reason_code TEXT NOT NULL CHECK(transition_reason_code IN('BOOTSTRAP','ACTIVATE','FIRST_EFFECT','BEGIN_DRAIN','STAGE_NEXT','CANCEL_DRAIN','ADVANCE_GENERATION','PRE_EFFECT_DORMANT','DRAIN_BOOT_CHANGED','DRAIN_TIMEOUT','ADOPTION_FAILED','STORE_FAILURE','BEGIN_REPAIR')),
 previous_protocol_hash TEXT CHECK(previous_protocol_hash IS NULL OR (length(previous_protocol_hash)=64 AND previous_protocol_hash NOT GLOB '*[^0-9a-f]*')),
 protocol_hash TEXT NOT NULL UNIQUE CHECK(length(protocol_hash)=64 AND protocol_hash NOT GLOB '*[^0-9a-f]*'),
 drain_boot_id TEXT CHECK(drain_boot_id IS NULL OR (length(CAST(drain_boot_id AS BLOB)) BETWEEN 1 AND 256 AND instr(drain_boot_id,char(0))=0)),
 drain_deadline_mono_ns INTEGER CHECK(drain_deadline_mono_ns IS NULL OR drain_deadline_mono_ns>=0),
 absence_proof_hash TEXT CHECK(absence_proof_hash IS NULL OR (length(absence_proof_hash)=64 AND absence_proof_hash NOT GLOB '*[^0-9a-f]*')),
 quiescence_proof_hash TEXT CHECK(quiescence_proof_hash IS NULL OR (length(quiescence_proof_hash)=64 AND quiescence_proof_hash NOT GLOB '*[^0-9a-f]*')),
 operation_id TEXT NOT NULL UNIQUE CHECK(length(operation_id)=64 AND operation_id NOT GLOB '*[^0-9a-f]*'),
 created_wall_ns INTEGER NOT NULL CHECK(created_wall_ns>=0),
 CHECK((first_effect_id IS NULL)=(first_effect_operation_id IS NULL)),
 CHECK(
  (staged_generation IS NULL AND staged_schema_hash IS NULL AND staged_profile_hash IS NULL AND staged_runtime_capability_hash IS NULL AND staged_writer_binary_hash IS NULL AND staged_writer_capability_hash IS NULL AND staged_tool_inventory_hash IS NULL AND staged_hook_projection_hash IS NULL AND staged_hook_matcher_mode IS NULL AND staged_hook_matcher_hash IS NULL AND staged_projection_receipt_hash IS NULL AND staged_projection_file_generation IS NULL AND staged_installer_identity_hash IS NULL AND staged_installer_capability_hash IS NULL AND staged_epoch_hash IS NULL)
  OR
  (staged_generation IS NOT NULL AND staged_schema_hash IS NOT NULL AND staged_profile_hash IS NOT NULL AND staged_runtime_capability_hash IS NOT NULL AND staged_writer_binary_hash IS NOT NULL AND staged_writer_capability_hash IS NOT NULL AND staged_tool_inventory_hash IS NOT NULL AND staged_hook_projection_hash IS NOT NULL AND staged_hook_matcher_mode IS NOT NULL AND staged_hook_matcher_hash IS NOT NULL AND staged_projection_receipt_hash IS NOT NULL AND staged_projection_file_generation IS NOT NULL AND staged_installer_identity_hash IS NOT NULL AND staged_installer_capability_hash IS NOT NULL AND staged_epoch_hash IS NOT NULL)
 ),
 CHECK(
  (
   (mode='DRAINING' AND drain_boot_id IS NOT NULL AND drain_deadline_mono_ns IS NOT NULL)
   OR
   (mode<>'DRAINING' AND drain_boot_id IS NULL AND drain_deadline_mono_ns IS NULL)
  ) IS TRUE
 ),
 CHECK((transition_kind='PRE_EFFECT_DORMANT')=(absence_proof_hash IS NOT NULL)),
 CHECK((quiescence_proof_hash IS NOT NULL)=(transition_kind IN('STAGE_NEXT','CANCEL_DRAIN','ADVANCE_GENERATION'))),
 FOREIGN KEY(first_effect_id) REFERENCES registration_effect(effect_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(first_effect_operation_id) REFERENCES registration_operation_audit(operation_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(operation_id) REFERENCES registration_operation_audit(operation_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
) STRICT, WITHOUT ROWID;
CREATE TABLE registration_member(
 member_id TEXT NOT NULL PRIMARY KEY CHECK(length(member_id)=64 AND member_id NOT GLOB '*[^0-9a-f]*'),
 canonical_root TEXT NOT NULL CHECK(substr(canonical_root,1,1)='/' AND length(CAST(canonical_root AS BLOB)) BETWEEN 1 AND 4096 AND instr(canonical_root,char(0))=0),
 root_dev INTEGER NOT NULL CHECK(root_dev>=0),
 root_ino INTEGER NOT NULL CHECK(root_ino>=0),
 git_toplevel TEXT NOT NULL CHECK(substr(git_toplevel,1,1)='/' AND length(CAST(git_toplevel AS BLOB)) BETWEEN 1 AND 4096 AND instr(git_toplevel,char(0))=0),
 git_dir TEXT NOT NULL CHECK(substr(git_dir,1,1)='/' AND length(CAST(git_dir AS BLOB)) BETWEEN 1 AND 4096 AND instr(git_dir,char(0))=0),
 git_dir_dev INTEGER NOT NULL CHECK(git_dir_dev>=0),
 git_dir_ino INTEGER NOT NULL CHECK(git_dir_ino>=0),
 git_common_dir TEXT NOT NULL CHECK(substr(git_common_dir,1,1)='/' AND length(CAST(git_common_dir AS BLOB)) BETWEEN 1 AND 4096 AND instr(git_common_dir,char(0))=0),
 git_common_dev INTEGER NOT NULL CHECK(git_common_dev>=0),
 git_common_ino INTEGER NOT NULL CHECK(git_common_ino>=0),
 proof_dev INTEGER NOT NULL CHECK(proof_dev>=0),
 projection_dev INTEGER NOT NULL CHECK(projection_dev>=0),
 legacy_state_dev INTEGER NOT NULL CHECK(legacy_state_dev>=0),
 physical_basis_hash TEXT NOT NULL CHECK(length(physical_basis_hash)=64 AND physical_basis_hash NOT GLOB '*[^0-9a-f]*'),
 git_basis_hash TEXT NOT NULL CHECK(length(git_basis_hash)=64 AND git_basis_hash NOT GLOB '*[^0-9a-f]*'),
 policy_basis_hash TEXT NOT NULL CHECK(length(policy_basis_hash)=64 AND policy_basis_hash NOT GLOB '*[^0-9a-f]*'),
 operation_basis_hash TEXT NOT NULL CHECK(length(operation_basis_hash)=64 AND operation_basis_hash NOT GLOB '*[^0-9a-f]*'),
 lifecycle_basis_hash TEXT NOT NULL CHECK(length(lifecycle_basis_hash)=64 AND lifecycle_basis_hash NOT GLOB '*[^0-9a-f]*'),
 current_basis_hash TEXT NOT NULL CHECK(length(current_basis_hash)=64 AND current_basis_hash NOT GLOB '*[^0-9a-f]*'),
 member_epoch INTEGER NOT NULL CHECK(member_epoch>=1),
 phase TEXT NOT NULL CHECK(phase IN('REQUESTED','EFFECT_IN_FLIGHT','RESOLVED')),
 current_effect_id TEXT NOT NULL CHECK(length(current_effect_id)=64 AND current_effect_id NOT GLOB '*[^0-9a-f]*'),
 runtime_subject_key TEXT NOT NULL UNIQUE CHECK(length(runtime_subject_key)=64 AND runtime_subject_key NOT GLOB '*[^0-9a-f]*'),
 helper_generation INTEGER NOT NULL CHECK(helper_generation>=1),
 current_outcome_kind TEXT CHECK(current_outcome_kind IS NULL OR current_outcome_kind IN('SUCCESS','LOGICAL_CONFLICT')),
 current_completion_hash TEXT CHECK(current_completion_hash IS NULL OR (length(current_completion_hash)=64 AND current_completion_hash NOT GLOB '*[^0-9a-f]*')),
 current_proof_hash TEXT CHECK(current_proof_hash IS NULL OR (length(current_proof_hash)=64 AND current_proof_hash NOT GLOB '*[^0-9a-f]*')),
 current_certificate_hash TEXT CHECK(current_certificate_hash IS NULL OR (length(current_certificate_hash)=64 AND current_certificate_hash NOT GLOB '*[^0-9a-f]*')),
 current_conflict_hash TEXT CHECK(current_conflict_hash IS NULL OR (length(current_conflict_hash)=64 AND current_conflict_hash NOT GLOB '*[^0-9a-f]*')),
 pending_effect_id TEXT CHECK(pending_effect_id IS NULL OR (length(pending_effect_id)=64 AND pending_effect_id NOT GLOB '*[^0-9a-f]*')),
 pending_member_epoch INTEGER CHECK(pending_member_epoch IS NULL OR pending_member_epoch>=2),
 pending_basis_hash TEXT CHECK(pending_basis_hash IS NULL OR (length(pending_basis_hash)=64 AND pending_basis_hash NOT GLOB '*[^0-9a-f]*')),
 pending_effect_tuple_hash TEXT CHECK(pending_effect_tuple_hash IS NULL OR (length(pending_effect_tuple_hash)=64 AND pending_effect_tuple_hash NOT GLOB '*[^0-9a-f]*')),
 member_tuple_hash TEXT NOT NULL CHECK(length(member_tuple_hash)=64 AND member_tuple_hash NOT GLOB '*[^0-9a-f]*'),
 write_operation_seq INTEGER NOT NULL CHECK(write_operation_seq>=1),
 write_operation_id TEXT NOT NULL CHECK(length(write_operation_id)=64 AND write_operation_id NOT GLOB '*[^0-9a-f]*'),
 write_operation_hash TEXT NOT NULL CHECK(length(write_operation_hash)=64 AND write_operation_hash NOT GLOB '*[^0-9a-f]*'),
 UNIQUE(canonical_root,root_dev,root_ino,git_dir_dev,git_dir_ino,git_common_dev,git_common_ino),
 CHECK(root_dev=git_dir_dev AND root_dev=git_common_dev AND root_dev=proof_dev AND root_dev=projection_dev AND root_dev=legacy_state_dev),
 CHECK(
  (pending_effect_id IS NULL AND pending_member_epoch IS NULL AND pending_basis_hash IS NULL AND pending_effect_tuple_hash IS NULL)
  OR
  (pending_effect_id IS NOT NULL AND pending_member_epoch IS NOT NULL AND pending_basis_hash IS NOT NULL AND pending_effect_tuple_hash IS NOT NULL)
 ),
 CHECK(
  (
   (phase='REQUESTED' AND current_outcome_kind IS NULL AND current_completion_hash IS NULL AND current_proof_hash IS NULL AND current_certificate_hash IS NULL AND current_conflict_hash IS NULL AND pending_effect_id IS NULL)
   OR
   (phase='EFFECT_IN_FLIGHT' AND current_outcome_kind IS NULL AND current_completion_hash IS NULL AND current_proof_hash IS NULL AND current_certificate_hash IS NULL AND current_conflict_hash IS NULL)
   OR
   (phase='RESOLVED' AND ((current_outcome_kind='SUCCESS' AND current_completion_hash IS NOT NULL AND current_proof_hash IS NOT NULL AND current_certificate_hash IS NOT NULL AND current_conflict_hash IS NULL) OR (current_outcome_kind='LOGICAL_CONFLICT' AND current_completion_hash IS NULL AND current_proof_hash IS NULL AND current_certificate_hash IS NULL AND current_conflict_hash IS NOT NULL)))
  ) IS TRUE
 ),
 FOREIGN KEY(current_effect_id) REFERENCES registration_effect(effect_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(runtime_subject_key) REFERENCES registration_runtime_status(subject_key) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(pending_effect_id) REFERENCES registration_effect(effect_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(write_operation_id) REFERENCES registration_operation_audit(operation_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
) STRICT, WITHOUT ROWID;
CREATE TABLE registration_episode(
 episode_id TEXT NOT NULL PRIMARY KEY CHECK(length(episode_id)=64 AND episode_id NOT GLOB '*[^0-9a-f]*'),
 conversation_id TEXT NOT NULL CHECK(length(CAST(conversation_id AS BLOB)) BETWEEN 1 AND 128 AND substr(conversation_id,1,1) GLOB '[A-Za-z0-9]' AND conversation_id NOT GLOB '*[^A-Za-z0-9._:-]*'),
 generation_id TEXT NOT NULL CHECK(length(CAST(generation_id AS BLOB)) BETWEEN 1 AND 128 AND substr(generation_id,1,1) GLOB '[A-Za-z0-9]' AND generation_id NOT GLOB '*[^A-Za-z0-9._:-]*'),
 source_contract TEXT NOT NULL CHECK(length(CAST(source_contract AS BLOB)) BETWEEN 1 AND 128 AND instr(source_contract,char(0))=0),
 source_event TEXT NOT NULL CHECK(length(CAST(source_event AS BLOB)) BETWEEN 1 AND 128 AND instr(source_event,char(0))=0),
 protocol_generation INTEGER NOT NULL CHECK(protocol_generation>=1),
 member_id TEXT NOT NULL CHECK(length(member_id)=64 AND member_id NOT GLOB '*[^0-9a-f]*'),
 workspace_root_count INTEGER NOT NULL CHECK(workspace_root_count=1),
 workspace_roots_hash TEXT NOT NULL CHECK(length(workspace_roots_hash)=64 AND workspace_roots_hash NOT GLOB '*[^0-9a-f]*'),
 tool_inventory_hash TEXT NOT NULL CHECK(length(tool_inventory_hash)=64 AND tool_inventory_hash NOT GLOB '*[^0-9a-f]*'),
 hook_projection_hash TEXT NOT NULL CHECK(length(hook_projection_hash)=64 AND hook_projection_hash NOT GLOB '*[^0-9a-f]*'),
 envelope_hash TEXT NOT NULL CHECK(length(envelope_hash)=64 AND envelope_hash NOT GLOB '*[^0-9a-f]*'),
 created_wall_ns INTEGER NOT NULL CHECK(created_wall_ns>=0),
 write_operation_seq INTEGER NOT NULL CHECK(write_operation_seq>=1),
 write_operation_id TEXT NOT NULL CHECK(length(write_operation_id)=64 AND write_operation_id NOT GLOB '*[^0-9a-f]*'),
 write_operation_hash TEXT NOT NULL CHECK(length(write_operation_hash)=64 AND write_operation_hash NOT GLOB '*[^0-9a-f]*'),
 UNIQUE(conversation_id,generation_id,source_contract,source_event,protocol_generation,member_id,workspace_roots_hash),
 FOREIGN KEY(member_id) REFERENCES registration_member(member_id) ON UPDATE NO ACTION ON DELETE NO ACTION,
 FOREIGN KEY(write_operation_id) REFERENCES registration_operation_audit(operation_id) ON UPDATE NO ACTION ON DELETE NO ACTION
) STRICT, WITHOUT ROWID;
CREATE TABLE registration_effect(
 effect_id TEXT NOT NULL PRIMARY KEY CHECK(length(effect_id)=64 AND effect_id NOT GLOB '*[^0-9a-f]*'),
 member_id TEXT NOT NULL CHECK(length(member_id)=64 AND member_id NOT GLOB '*[^0-9a-f]*'),
 member_epoch INTEGER NOT NULL CHECK(member_epoch>=1),
 request_kind TEXT NOT NULL CHECK(request_kind IN('CLEAN_ELIGIBLE','BLOCKED_DIRTY','BLOCKED_OPERATION')),
 request_basis_hash TEXT NOT NULL CHECK(length(request_basis_hash)=64 AND request_basis_hash NOT GLOB '*[^0-9a-f]*'),
 predecessor_effect_id TEXT CHECK(predecessor_effect_id IS NULL OR (length(predecessor_effect_id)=64 AND predecessor_effect_id NOT GLOB '*[^0-9a-f]*')),
 required_protocol_generation INTEGER NOT NULL CHECK(required_protocol_generation>=1),
 required_runtime_capability_hash TEXT NOT NULL CHECK(length(required_runtime_capability_hash)=64 AND required_runtime_capability_hash NOT GLOB '*[^0-9a-f]*'),
 action_plan_hash TEXT NOT NULL CHECK(length(action_plan_hash)=64 AND action_plan_hash NOT GLOB '*[^0-9a-f]*'),
 action_plan_blob BLOB CHECK(action_plan_blob IS NULL OR length(action_plan_blob) BETWEEN 1 AND 65536),
 required_action_count INTEGER NOT NULL CHECK(required_action_count IN(0,4)),
 action_1_kind TEXT CHECK(action_1_kind IS NULL OR action_1_kind='PUBLISH_EFFECT_PROOF'),
 action_1_hash TEXT CHECK(action_1_hash IS NULL OR (length(action_1_hash)=64 AND action_1_hash NOT GLOB '*[^0-9a-f]*')),
 postcondition_1_hash TEXT CHECK(postcondition_1_hash IS NULL OR (length(postcondition_1_hash)=64 AND postcondition_1_hash NOT GLOB '*[^0-9a-f]*')),
 action_2_kind TEXT CHECK(action_2_kind IS NULL OR action_2_kind='CONVERGE_LEGACY_LEASE'),
 action_2_hash TEXT CHECK(action_2_hash IS NULL OR (length(action_2_hash)=64 AND action_2_hash NOT GLOB '*[^0-9a-f]*')),
 postcondition_2_hash TEXT CHECK(postcondition_2_hash IS NULL OR (length(postcondition_2_hash)=64 AND postcondition_2_hash NOT GLOB '*[^0-9a-f]*')),
 action_3_kind TEXT CHECK(action_3_kind IS NULL OR action_3_kind='CONVERGE_LEGACY_LIFECYCLE'),
 action_3_hash TEXT CHECK(action_3_hash IS NULL OR (length(action_3_hash)=64 AND action_3_hash NOT GLOB '*[^0-9a-f]*')),
 postcondition_3_hash TEXT CHECK(postcondition_3_hash IS NULL OR (length(postcondition_3_hash)=64 AND postcondition_3_hash NOT GLOB '*[^0-9a-f]*')),
 action_4_kind TEXT CHECK(action_4_kind IS NULL OR action_4_kind='COLLECT_FINAL_BASIS'),
 action_4_hash TEXT CHECK(action_4_hash IS NULL OR (length(action_4_hash)=64 AND action_4_hash NOT GLOB '*[^0-9a-f]*')),
 postcondition_4_hash TEXT CHECK(postcondition_4_hash IS NULL OR (length(postcondition_4_hash)=64 AND postcondition_4_hash NOT GLOB '*[^0-9a-f]*')),
 external_growth_reservation_bytes INTEGER NOT NULL CHECK(external_growth_reservation_bytes BETWEEN 0 AND 16777216),
 outcome_reservation_bytes INTEGER NOT NULL CHECK(outcome_reservation_bytes BETWEEN 1 AND 1048576),
 successor_reservation_bytes INTEGER NOT NULL CHECK(successor_reservation_bytes BETWEEN 1 AND 1048576),
 request_tuple_hash TEXT NOT NULL CHECK(length(request_tuple_hash)=64 AND request_tuple_hash NOT GLOB '*[^0-9a-f]*'),
 created_operation_seq INTEGER NOT NULL CHECK(created_operation_seq>=1),
 created_operation_id TEXT NOT NULL CHECK(length(created_operation_id)=64 AND created_operation_id NOT GLOB '*[^0-9a-f]*'),
 created_operation_hash TEXT NOT NULL CHECK(length(created_operation_hash)=64 AND created_operation_hash NOT GLOB '*[^0-9a-f]*'),
 outcome_kind TEXT CHECK(outcome_kind IS NULL OR outcome_kind IN('SUCCESS','LOGICAL_CONFLICT','SUPERSEDED')),
 outcome_helper_generation INTEGER CHECK(outcome_helper_generation IS NULL OR outcome_helper_generation>=1),
 outcome_tuple_hash TEXT CHECK(outcome_tuple_hash IS NULL OR (length(outcome_tuple_hash)=64 AND outcome_tuple_hash NOT GLOB '*[^0-9a-f]*')),
 ledger_head_hash TEXT CHECK(ledger_head_hash IS NULL OR (length(ledger_head_hash)=64 AND ledger_head_hash NOT GLOB '*[^0-9a-f]*')),
 first_conflict_event_seq INTEGER CHECK(first_conflict_event_seq IS NULL OR first_conflict_event_seq BETWEEN 1 AND 4),
 completion_blob BLOB CHECK(completion_blob IS NULL OR length(completion_blob) BETWEEN 1 AND 65536),
 completion_hash TEXT CHECK(completion_hash IS NULL OR (length(completion_hash)=64 AND completion_hash NOT GLOB '*[^0-9a-f]*')),
 final_basis_hash TEXT CHECK(final_basis_hash IS NULL OR (length(final_basis_hash)=64 AND final_basis_hash NOT GLOB '*[^0-9a-f]*')),
 proof_blob BLOB CHECK(proof_blob IS NULL OR length(proof_blob) BETWEEN 1 AND 65536),
 proof_hash TEXT CHECK(proof_hash IS NULL OR (length(proof_hash)=64 AND proof_hash NOT GLOB '*[^0-9a-f]*')),
 certificate_inputs_blob BLOB CHECK(certificate_inputs_blob IS NULL OR length(certificate_inputs_blob) BETWEEN 1 AND 65536),
 certificate_inputs_hash TEXT CHECK(certificate_inputs_hash IS NULL OR (length(certificate_inputs_hash)=64 AND certificate_inputs_hash NOT GLOB '*[^0-9a-f]*')),
 certificate_hash TEXT UNIQUE CHECK(certificate_hash IS NULL OR (length(certificate_hash)=64 AND certificate_hash NOT GLOB '*[^0-9a-f]*')),
 conflict_code TEXT CHECK(conflict_code IS NULL OR conflict_code IN('PROOF_POSTCONDITION_DIVERGENT','LEGACY_LEASE_DIVERGENT','LIFECYCLE_GRAPH_DIVERGENT','FINAL_BASIS_DIVERGENT','ACTION_POSTCONDITION_DIVERGENT')),
 conflict_blob BLOB CHECK(conflict_blob IS NULL OR length(conflict_blob) BETWEEN 1 AND 65536),
 conflict_hash TEXT CHECK(conflict_hash IS NULL OR (length(conflict_hash)=64 AND conflict_hash NOT GLOB '*[^0-9a-f]*')),
 superseded_by_effect_id TEXT CHECK(superseded_by_effect_id IS NULL OR (length(superseded_by_effect_id)=64 AND superseded_by_effect_id NOT GLOB '*[^0-9a-f]*')),
 successor_transition_id TEXT CHECK(successor_transition_id IS NULL OR (length(successor_transition_id)=64 AND successor_transition_id NOT GLOB '*[^0-9a-f]*')),
 outcome_operation_seq INTEGER CHECK(outcome_operation_seq IS NULL OR outcome_operation_seq>=1),
 outcome_operation_id TEXT CHECK(outcome_operation_id IS NULL OR (length(outcome_operation_id)=64 AND outcome_operation_id NOT GLOB '*[^0-9a-f]*')),
 outcome_operation_hash TEXT CHECK(outcome_operation_hash IS NULL OR (length(outcome_operation_hash)=64 AND outcome_operation_hash NOT GLOB '*[^0-9a-f]*')),
 UNIQUE(member_id,member_epoch),
 CHECK(
  (request_kind='CLEAN_ELIGIBLE' AND action_plan_blob IS NOT NULL AND required_action_count=4 AND action_1_kind IS NOT NULL AND action_1_hash IS NOT NULL AND postcondition_1_hash IS NOT NULL AND action_2_kind IS NOT NULL AND action_2_hash IS NOT NULL AND postcondition_2_hash IS NOT NULL AND action_3_kind IS NOT NULL AND action_3_hash IS NOT NULL AND postcondition_3_hash IS NOT NULL AND action_4_kind IS NOT NULL AND action_4_hash IS NOT NULL AND postcondition_4_hash IS NOT NULL)
  OR
  (request_kind<>'CLEAN_ELIGIBLE' AND action_plan_hash='0000000000000000000000000000000000000000000000000000000000000000' AND action_plan_blob IS NULL AND required_action_count=0 AND action_1_kind IS NULL AND action_1_hash IS NULL AND postcondition_1_hash IS NULL AND action_2_kind IS NULL AND action_2_hash IS NULL AND postcondition_2_hash IS NULL AND action_3_kind IS NULL AND action_3_hash IS NULL AND postcondition_3_hash IS NULL AND action_4_kind IS NULL AND action_4_hash IS NULL AND postcondition_4_hash IS NULL AND external_growth_reservation_bytes=0)
 ),
 CHECK(
  (
   (outcome_kind IS NULL AND outcome_helper_generation IS NULL AND outcome_tuple_hash IS NULL AND ledger_head_hash IS NULL AND first_conflict_event_seq IS NULL AND completion_blob IS NULL AND completion_hash IS NULL AND final_basis_hash IS NULL AND proof_blob IS NULL AND proof_hash IS NULL AND certificate_inputs_blob IS NULL AND certificate_inputs_hash IS NULL AND certificate_hash IS NULL AND conflict_code IS NULL AND conflict_blob IS NULL AND conflict_hash IS NULL AND superseded_by_effect_id IS NULL AND successor_transition_id IS NULL AND outcome_operation_seq IS NULL AND outcome_operation_id IS NULL AND outcome_operation_hash IS NULL)
   OR
   (outcome_kind='SUCCESS' AND request_kind='CLEAN_ELIGIBLE' AND outcome_helper_generation IS NOT NULL AND outcome_tuple_hash IS NOT NULL AND ledger_head_hash IS NOT NULL AND first_conflict_event_seq IS NULL AND completion_blob IS NOT NULL AND completion_hash IS NOT NULL AND final_basis_hash IS NOT NULL AND proof_blob IS NOT NULL AND proof_hash IS NOT NULL AND certificate_inputs_blob IS NOT NULL AND certificate_inputs_hash IS NOT NULL AND certificate_hash IS NOT NULL AND conflict_code IS NULL AND conflict_blob IS NULL AND conflict_hash IS NULL AND superseded_by_effect_id IS NULL AND successor_transition_id IS NULL AND outcome_operation_seq IS NOT NULL AND outcome_operation_id IS NOT NULL AND outcome_operation_hash IS NOT NULL)
   OR
   (outcome_kind='LOGICAL_CONFLICT' AND request_kind='CLEAN_ELIGIBLE' AND outcome_helper_generation IS NOT NULL AND outcome_tuple_hash IS NOT NULL AND ledger_head_hash IS NOT NULL AND first_conflict_event_seq IS NOT NULL AND completion_blob IS NULL AND completion_hash IS NULL AND final_basis_hash IS NULL AND proof_blob IS NULL AND proof_hash IS NULL AND certificate_inputs_blob IS NULL AND certificate_inputs_hash IS NULL AND certificate_hash IS NULL AND conflict_code IS NOT NULL AND conflict_blob IS NOT NULL AND conflict_hash IS NOT NULL AND superseded_by_effect_id IS NULL AND successor_transition_id IS NULL AND outcome_operation_seq IS NOT NULL AND outcome_operation_id IS NOT NULL AND outcome_operation_hash IS NOT NULL)
   OR
   (outcome_kind='SUPERSEDED' AND outcome_helper_generation IS NULL AND outcome_tuple_hash IS NOT NULL AND ledger_head_hash IS NULL AND first_conflict_event_seq IS NULL AND completion_blob IS NULL AND completion_hash IS NULL AND final_basis_hash IS NULL AND proof_blob IS NULL AND proof_hash IS NULL AND certificate_inputs_blob IS NULL AND certificate_inputs_hash IS NULL AND certificate_hash IS NULL AND conflict_code IS NULL AND conflict_blob IS NULL AND conflict_hash IS NULL AND superseded_by_effect_id IS NOT NULL AND successor_transition_id IS NOT NULL AND outcome_operation_seq IS NOT NULL AND outcome_operation_id IS NOT NULL AND outcome_operation_hash IS NOT NULL)
  ) IS TRUE
 ),
 FOREIGN KEY(member_id) REFERENCES registration_member(member_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(predecessor_effect_id) REFERENCES registration_effect(effect_id) ON UPDATE NO ACTION ON DELETE NO ACTION,
 FOREIGN KEY(superseded_by_effect_id) REFERENCES registration_effect(effect_id) ON UPDATE NO ACTION ON DELETE NO ACTION,
 FOREIGN KEY(created_operation_id) REFERENCES registration_operation_audit(operation_id) ON UPDATE NO ACTION ON DELETE NO ACTION,
 FOREIGN KEY(outcome_operation_id) REFERENCES registration_operation_audit(operation_id) ON UPDATE NO ACTION ON DELETE NO ACTION
) STRICT, WITHOUT ROWID;
CREATE TABLE registration_effect_action(
 effect_id TEXT NOT NULL CHECK(length(effect_id)=64 AND effect_id NOT GLOB '*[^0-9a-f]*'),
 event_seq INTEGER NOT NULL CHECK(event_seq BETWEEN 1 AND 4),
 ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 1 AND 4),
 action_kind TEXT NOT NULL CHECK(action_kind IN('PUBLISH_EFFECT_PROOF','CONVERGE_LEGACY_LEASE','CONVERGE_LEGACY_LIFECYCLE','COLLECT_FINAL_BASIS')),
 action_hash TEXT NOT NULL CHECK(length(action_hash)=64 AND action_hash NOT GLOB '*[^0-9a-f]*'),
 postcondition_hash TEXT NOT NULL CHECK(length(postcondition_hash)=64 AND postcondition_hash NOT GLOB '*[^0-9a-f]*'),
 observation_kind TEXT NOT NULL CHECK(observation_kind IN('OBSERVED_EXACT','APPLIED_VERIFIED','LOGICAL_CONFLICT')),
 observation_blob BLOB NOT NULL CHECK(length(observation_blob) BETWEEN 1 AND 65536),
 observation_hash TEXT NOT NULL CHECK(length(observation_hash)=64 AND observation_hash NOT GLOB '*[^0-9a-f]*'),
 prior_ledger_hash TEXT NOT NULL CHECK(length(prior_ledger_hash)=64 AND prior_ledger_hash NOT GLOB '*[^0-9a-f]*'),
 ledger_hash TEXT NOT NULL UNIQUE CHECK(length(ledger_hash)=64 AND ledger_hash NOT GLOB '*[^0-9a-f]*'),
 external_growth_bytes INTEGER NOT NULL CHECK(external_growth_bytes BETWEEN 0 AND 16777216),
 observed_wall_ns INTEGER NOT NULL CHECK(observed_wall_ns>=0),
 write_operation_seq INTEGER NOT NULL CHECK(write_operation_seq>=1),
 write_operation_id TEXT NOT NULL CHECK(length(write_operation_id)=64 AND write_operation_id NOT GLOB '*[^0-9a-f]*'),
 write_operation_hash TEXT NOT NULL CHECK(length(write_operation_hash)=64 AND write_operation_hash NOT GLOB '*[^0-9a-f]*'),
 PRIMARY KEY(effect_id,event_seq),
 UNIQUE(effect_id,ordinal),
 CHECK(event_seq=ordinal),
 FOREIGN KEY(effect_id) REFERENCES registration_effect(effect_id) ON UPDATE NO ACTION ON DELETE NO ACTION,
 FOREIGN KEY(write_operation_id) REFERENCES registration_operation_audit(operation_id) ON UPDATE NO ACTION ON DELETE NO ACTION
) STRICT, WITHOUT ROWID;
CREATE TABLE registration_runtime_status(
 subject_key TEXT NOT NULL PRIMARY KEY CHECK(length(subject_key)=64 AND subject_key NOT GLOB '*[^0-9a-f]*'),
 member_id TEXT NOT NULL UNIQUE CHECK(length(member_id)=64 AND member_id NOT GLOB '*[^0-9a-f]*'),
 member_epoch INTEGER NOT NULL CHECK(member_epoch>=1),
 current_effect_id TEXT NOT NULL CHECK(length(current_effect_id)=64 AND current_effect_id NOT GLOB '*[^0-9a-f]*'),
 status_version INTEGER NOT NULL CHECK(status_version>=1),
 status_hash TEXT NOT NULL CHECK(length(status_hash)=64 AND status_hash NOT GLOB '*[^0-9a-f]*'),
 schedule_boot_id TEXT CHECK(schedule_boot_id IS NULL OR (length(CAST(schedule_boot_id AS BLOB)) BETWEEN 1 AND 256 AND instr(schedule_boot_id,char(0))=0)),
 observed_now_mono_ns INTEGER CHECK(observed_now_mono_ns IS NULL OR observed_now_mono_ns>=0),
 next_due_mono_ns INTEGER CHECK(next_due_mono_ns IS NULL OR next_due_mono_ns>=0),
 due_since_mono_ns INTEGER CHECK(due_since_mono_ns IS NULL OR due_since_mono_ns>=0),
 attempt_count INTEGER CHECK(attempt_count IS NULL OR attempt_count BETWEEN 0 AND 255),
 backoff_ns INTEGER CHECK(backoff_ns IS NULL OR backoff_ns BETWEEN 0 AND 15000000000),
 help_due INTEGER NOT NULL CHECK(help_due IN(0,1)),
 executor_token_hash TEXT CHECK(executor_token_hash IS NULL OR (length(executor_token_hash)=64 AND executor_token_hash NOT GLOB '*[^0-9a-f]*')),
 executor_boot_id TEXT CHECK(executor_boot_id IS NULL OR (length(CAST(executor_boot_id AS BLOB)) BETWEEN 1 AND 256 AND instr(executor_boot_id,char(0))=0)),
 executor_generation INTEGER CHECK(executor_generation IS NULL OR executor_generation>=1),
 unavailable_count INTEGER NOT NULL CHECK(unavailable_count BETWEEN 0 AND 3),
 yield_count INTEGER NOT NULL CHECK(yield_count BETWEEN 0 AND 3),
 blocked_basis_fingerprint TEXT CHECK(blocked_basis_fingerprint IS NULL OR (length(blocked_basis_fingerprint)=64 AND blocked_basis_fingerprint NOT GLOB '*[^0-9a-f]*')),
 reason_code TEXT CHECK(reason_code IS NULL OR reason_code IN('REGISTRATION_REQUIRED','EFFECT_IN_FLIGHT','RESOLVER_UNAVAILABLE','BASIS_UNSTABLE','BASIS_TIMEOUT','DIRTY_UNSUPPORTED','GIT_OPERATION_UNSUPPORTED','EFFECT_CONFLICT','STORE_FAILURE','PROTOCOL_INCOMPATIBLE','HOOK_UNSUPPORTED','UNKNOWN_DISCRIMINATOR','TOOL_NOT_IN_INVENTORY','STORE_UNAVAILABLE','STORAGE_DEGRADED','STORAGE_RED','DEVICE_MISMATCH','HOST_STARVED','ROOT_COUNT_UNSUPPORTED','ROOT_UNSUPPORTED','BOOT_ID_UNAVAILABLE','TASK_SUBAGENT_DENIED','PARSER_REJECT','SERIALIZER_INVALID','CONTAINMENT','CONTAINMENT_UNAVAILABLE')),
 write_operation_seq INTEGER NOT NULL CHECK(write_operation_seq>=1),
 write_operation_id TEXT NOT NULL CHECK(length(write_operation_id)=64 AND write_operation_id NOT GLOB '*[^0-9a-f]*'),
 write_operation_hash TEXT NOT NULL CHECK(length(write_operation_hash)=64 AND write_operation_hash NOT GLOB '*[^0-9a-f]*'),
 CHECK(
  (schedule_boot_id IS NULL AND observed_now_mono_ns IS NULL AND next_due_mono_ns IS NULL AND due_since_mono_ns IS NULL AND attempt_count IS NULL AND backoff_ns IS NULL)
  OR
  (schedule_boot_id IS NOT NULL AND observed_now_mono_ns IS NOT NULL AND next_due_mono_ns IS NOT NULL AND due_since_mono_ns IS NOT NULL AND attempt_count IS NOT NULL AND backoff_ns IS NOT NULL AND next_due_mono_ns=observed_now_mono_ns+backoff_ns)
 ),
 CHECK((executor_token_hash IS NULL AND executor_boot_id IS NULL AND executor_generation IS NULL) OR (executor_token_hash IS NOT NULL AND executor_boot_id IS NOT NULL AND executor_generation IS NOT NULL)),
 FOREIGN KEY(member_id) REFERENCES registration_member(member_id) ON UPDATE NO ACTION ON DELETE NO ACTION,
 FOREIGN KEY(current_effect_id) REFERENCES registration_effect(effect_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED,
 FOREIGN KEY(write_operation_id) REFERENCES registration_operation_audit(operation_id) ON UPDATE NO ACTION ON DELETE NO ACTION
) STRICT, WITHOUT ROWID;
CREATE TABLE registration_operation_audit(
 operation_seq INTEGER NOT NULL PRIMARY KEY CHECK(operation_seq>=1),
 operation_id TEXT NOT NULL UNIQUE CHECK(length(operation_id)=64 AND operation_id NOT GLOB '*[^0-9a-f]*'),
 operation_class TEXT NOT NULL CHECK(operation_class IN('BOOTSTRAP','DATA','CONTROL')),
 operation_kind TEXT NOT NULL CHECK(operation_kind IN('BOOTSTRAP','INSTALL_MEMBER','BIND_EPISODE','REACQUIRE_EFFECT','OPEN_EFFECT','APPEND_ACTION','CLOSE_SUCCESS','CLOSE_CONFLICT','INVALIDATE_REQUESTED','SET_PENDING','REPLACE_PENDING','HANDOFF_RESOLVED','MARK_UNAVAILABLE','REBOOT_STATUS','SCHEDULE_STATUS','ACTIVATE','BEGIN_DRAIN','STAGE_NEXT','CANCEL_DRAIN','ADOPT_EFFECT','ADVANCE_GENERATION','PRE_EFFECT_DORMANT','ENTER_CONTAINMENT','BEGIN_REPAIR')),
 expected_revision INTEGER NOT NULL CHECK(expected_revision>=0),
 protocol_seq INTEGER NOT NULL CHECK(protocol_seq>=0),
 expected_mode TEXT NOT NULL CHECK(expected_mode IN('NONE','DORMANT','WRITABLE','DRAINING','CONTAINMENT')),
 expected_generation INTEGER NOT NULL CHECK(expected_generation>=0),
 expected_protocol_hash TEXT CHECK(expected_protocol_hash IS NULL OR (length(expected_protocol_hash)=64 AND expected_protocol_hash NOT GLOB '*[^0-9a-f]*')),
 runtime_capability_hash TEXT NOT NULL CHECK(length(runtime_capability_hash)=64 AND runtime_capability_hash NOT GLOB '*[^0-9a-f]*'),
 writer_binary_hash TEXT NOT NULL CHECK(length(writer_binary_hash)=64 AND writer_binary_hash NOT GLOB '*[^0-9a-f]*'),
 profile_hash TEXT NOT NULL CHECK(length(profile_hash)=64 AND profile_hash NOT GLOB '*[^0-9a-f]*'),
 writer_capability_receipt_hash TEXT CHECK(writer_capability_receipt_hash IS NULL OR (length(writer_capability_receipt_hash)=64 AND writer_capability_receipt_hash NOT GLOB '*[^0-9a-f]*')),
 installer_identity_hash TEXT CHECK(installer_identity_hash IS NULL OR (length(installer_identity_hash)=64 AND installer_identity_hash NOT GLOB '*[^0-9a-f]*')),
 installer_capability_receipt_hash TEXT CHECK(installer_capability_receipt_hash IS NULL OR (length(installer_capability_receipt_hash)=64 AND installer_capability_receipt_hash NOT GLOB '*[^0-9a-f]*')),
 protocol_lock_receipt_hash TEXT CHECK(protocol_lock_receipt_hash IS NULL OR (length(protocol_lock_receipt_hash)=64 AND protocol_lock_receipt_hash NOT GLOB '*[^0-9a-f]*')),
 control_binding_hash TEXT CHECK(control_binding_hash IS NULL OR (length(control_binding_hash)=64 AND control_binding_hash NOT GLOB '*[^0-9a-f]*')),
 target_member_id TEXT CHECK(target_member_id IS NULL OR (length(target_member_id)=64 AND target_member_id NOT GLOB '*[^0-9a-f]*')),
 target_effect_id TEXT CHECK(target_effect_id IS NULL OR (length(target_effect_id)=64 AND target_effect_id NOT GLOB '*[^0-9a-f]*')),
 lineage_effect_id TEXT CHECK(lineage_effect_id IS NULL OR (length(lineage_effect_id)=64 AND lineage_effect_id NOT GLOB '*[^0-9a-f]*')),
 target_successor_effect_id TEXT CHECK(target_successor_effect_id IS NULL OR (length(target_successor_effect_id)=64 AND target_successor_effect_id NOT GLOB '*[^0-9a-f]*')),
 target_executor_token_hash TEXT CHECK(target_executor_token_hash IS NULL OR (length(target_executor_token_hash)=64 AND target_executor_token_hash NOT GLOB '*[^0-9a-f]*')),
 expected_target_status_hash TEXT CHECK(expected_target_status_hash IS NULL OR (length(expected_target_status_hash)=64 AND expected_target_status_hash NOT GLOB '*[^0-9a-f]*')),
 target_episode_id TEXT CHECK(target_episode_id IS NULL OR (length(target_episode_id)=64 AND target_episode_id NOT GLOB '*[^0-9a-f]*')),
 target_transition_id TEXT CHECK(target_transition_id IS NULL OR (length(target_transition_id)=64 AND target_transition_id NOT GLOB '*[^0-9a-f]*')),
 target_subject_key TEXT CHECK(target_subject_key IS NULL OR (length(target_subject_key)=64 AND target_subject_key NOT GLOB '*[^0-9a-f]*')),
 target_protocol_hash TEXT CHECK(target_protocol_hash IS NULL OR (length(target_protocol_hash)=64 AND target_protocol_hash NOT GLOB '*[^0-9a-f]*')),
 target_staged_epoch_hash TEXT CHECK(target_staged_epoch_hash IS NULL OR (length(target_staged_epoch_hash)=64 AND target_staged_epoch_hash NOT GLOB '*[^0-9a-f]*')),
 expected_target_member_tuple_hash TEXT CHECK(expected_target_member_tuple_hash IS NULL OR (length(expected_target_member_tuple_hash)=64 AND expected_target_member_tuple_hash NOT GLOB '*[^0-9a-f]*')),
 expected_target_effect_tuple_hash TEXT CHECK(expected_target_effect_tuple_hash IS NULL OR (length(expected_target_effect_tuple_hash)=64 AND expected_target_effect_tuple_hash NOT GLOB '*[^0-9a-f]*')),
 target_member_epoch INTEGER CHECK(target_member_epoch IS NULL OR target_member_epoch>=1),
 target_basis_hash TEXT CHECK(target_basis_hash IS NULL OR (length(target_basis_hash)=64 AND target_basis_hash NOT GLOB '*[^0-9a-f]*')),
 target_successor_member_epoch INTEGER CHECK(target_successor_member_epoch IS NULL OR target_successor_member_epoch>=1),
 target_successor_basis_hash TEXT CHECK(target_successor_basis_hash IS NULL OR (length(target_successor_basis_hash)=64 AND target_successor_basis_hash NOT GLOB '*[^0-9a-f]*')),
 target_member_tuple_hash TEXT CHECK(target_member_tuple_hash IS NULL OR (length(target_member_tuple_hash)=64 AND target_member_tuple_hash NOT GLOB '*[^0-9a-f]*')),
 target_effect_tuple_hash TEXT CHECK(target_effect_tuple_hash IS NULL OR (length(target_effect_tuple_hash)=64 AND target_effect_tuple_hash NOT GLOB '*[^0-9a-f]*')),
 target_effect_outcome_hash TEXT CHECK(target_effect_outcome_hash IS NULL OR (length(target_effect_outcome_hash)=64 AND target_effect_outcome_hash NOT GLOB '*[^0-9a-f]*')),
 target_action_plan_hash TEXT CHECK(target_action_plan_hash IS NULL OR (length(target_action_plan_hash)=64 AND target_action_plan_hash NOT GLOB '*[^0-9a-f]*')),
 target_cause_code TEXT CHECK(target_cause_code IS NULL OR target_cause_code IN('BASIS_CHANGED','PENDING_REPLACED','STAGED_CAPABILITY_INCOMPATIBLE','CURRENT_CLOSURE_CHANGED','EXPLICIT_CONFLICT_RETRY')),
 target_episode_hash TEXT CHECK(target_episode_hash IS NULL OR (length(target_episode_hash)=64 AND target_episode_hash NOT GLOB '*[^0-9a-f]*')),
 target_action_ledger_hash TEXT CHECK(target_action_ledger_hash IS NULL OR (length(target_action_ledger_hash)=64 AND target_action_ledger_hash NOT GLOB '*[^0-9a-f]*')),
 target_status_hash TEXT CHECK(target_status_hash IS NULL OR (length(target_status_hash)=64 AND target_status_hash NOT GLOB '*[^0-9a-f]*')),
 operation_envelope_hash TEXT NOT NULL CHECK(length(operation_envelope_hash)=64 AND operation_envelope_hash NOT GLOB '*[^0-9a-f]*'),
 sample_boot_id TEXT CHECK(sample_boot_id IS NULL OR (length(CAST(sample_boot_id AS BLOB)) BETWEEN 1 AND 256 AND instr(sample_boot_id,char(0))=0)),
 sample_mono_ns INTEGER CHECK(sample_mono_ns IS NULL OR sample_mono_ns>=0),
 measured_free_bytes INTEGER NOT NULL CHECK(measured_free_bytes>=0),
 projected_db_growth_bytes INTEGER NOT NULL CHECK(projected_db_growth_bytes BETWEEN 0 AND 16777216),
 external_growth_bytes INTEGER NOT NULL CHECK(external_growth_bytes BETWEEN 0 AND 16777216),
 new_external_reservation_bytes INTEGER NOT NULL CHECK(new_external_reservation_bytes BETWEEN 0 AND 16777216),
 new_outcome_reservation_bytes INTEGER NOT NULL CHECK(new_outcome_reservation_bytes BETWEEN 0 AND 1048576),
 new_successor_reservation_bytes INTEGER NOT NULL CHECK(new_successor_reservation_bytes BETWEEN 0 AND 1048576),
 control_reserve_bytes INTEGER NOT NULL CHECK(control_reserve_bytes BETWEEN 0 AND 14680064),
 created_wall_ns INTEGER NOT NULL CHECK(created_wall_ns>=0),
 CHECK((sample_boot_id IS NULL)=(sample_mono_ns IS NULL)),
 CHECK(operation_kind NOT IN('INSTALL_MEMBER','REACQUIRE_EFFECT','OPEN_EFFECT','CLOSE_SUCCESS','CLOSE_CONFLICT','INVALIDATE_REQUESTED','HANDOFF_RESOLVED','MARK_UNAVAILABLE','REBOOT_STATUS','SCHEDULE_STATUS','BEGIN_DRAIN','STAGE_NEXT','CANCEL_DRAIN','ADOPT_EFFECT','ADVANCE_GENERATION','PRE_EFFECT_DORMANT','ENTER_CONTAINMENT','BEGIN_REPAIR') OR sample_boot_id IS NOT NULL),
 CHECK(
  (operation_class='BOOTSTRAP' AND operation_kind='BOOTSTRAP' AND writer_capability_receipt_hash IS NULL AND installer_identity_hash IS NOT NULL AND installer_capability_receipt_hash IS NOT NULL AND protocol_lock_receipt_hash IS NOT NULL AND control_binding_hash IS NOT NULL)
  OR
  (operation_class='DATA' AND operation_kind IN('INSTALL_MEMBER','BIND_EPISODE','REACQUIRE_EFFECT','OPEN_EFFECT','APPEND_ACTION','CLOSE_SUCCESS','CLOSE_CONFLICT','INVALIDATE_REQUESTED','SET_PENDING','REPLACE_PENDING','HANDOFF_RESOLVED','MARK_UNAVAILABLE','REBOOT_STATUS','SCHEDULE_STATUS') AND writer_capability_receipt_hash IS NOT NULL AND installer_identity_hash IS NULL AND installer_capability_receipt_hash IS NULL AND protocol_lock_receipt_hash IS NULL AND control_binding_hash IS NULL)
  OR
  (operation_class='CONTROL' AND operation_kind IN('ACTIVATE','BEGIN_DRAIN','STAGE_NEXT','CANCEL_DRAIN','ADOPT_EFFECT','ADVANCE_GENERATION','PRE_EFFECT_DORMANT','ENTER_CONTAINMENT','BEGIN_REPAIR') AND writer_capability_receipt_hash IS NULL AND installer_identity_hash IS NOT NULL AND installer_capability_receipt_hash IS NOT NULL AND protocol_lock_receipt_hash IS NOT NULL AND control_binding_hash IS NOT NULL)
 ),
 CHECK(
  (operation_kind IN('OPEN_EFFECT','REACQUIRE_EFFECT','APPEND_ACTION','CLOSE_SUCCESS','CLOSE_CONFLICT','MARK_UNAVAILABLE','ADOPT_EFFECT') AND target_executor_token_hash IS NOT NULL AND expected_target_status_hash IS NOT NULL)
  OR
  (operation_kind NOT IN('OPEN_EFFECT','REACQUIRE_EFFECT','APPEND_ACTION','CLOSE_SUCCESS','CLOSE_CONFLICT','MARK_UNAVAILABLE','ADOPT_EFFECT') AND target_executor_token_hash IS NULL)
 ),
 CHECK(
  operation_kind NOT IN('OPEN_EFFECT','REACQUIRE_EFFECT','ADOPT_EFFECT')
  OR (target_member_tuple_hash IS NOT NULL AND target_effect_tuple_hash IS NOT NULL AND target_status_hash IS NOT NULL AND target_protocol_hash IS NOT NULL)
 ),
 CHECK(
  (operation_kind='INVALIDATE_REQUESTED' AND target_cause_code='BASIS_CHANGED')
  OR
  (operation_kind='REPLACE_PENDING' AND target_cause_code='PENDING_REPLACED')
  OR
  (operation_kind='HANDOFF_RESOLVED' AND target_cause_code IN('BASIS_CHANGED','CURRENT_CLOSURE_CHANGED','EXPLICIT_CONFLICT_RETRY'))
  OR
  (operation_kind='ADOPT_EFFECT' AND ((target_successor_effect_id IS NULL AND target_cause_code IS NULL) OR (target_successor_effect_id IS NOT NULL AND target_cause_code='STAGED_CAPABILITY_INCOMPATIBLE')))
  OR
  (operation_kind NOT IN('INVALIDATE_REQUESTED','REPLACE_PENDING','HANDOFF_RESOLVED','ADOPT_EFFECT') AND target_cause_code IS NULL)
 ),
 CHECK((operation_kind='ADOPT_EFFECT' AND lineage_effect_id IS NOT NULL) OR (operation_kind<>'ADOPT_EFFECT' AND lineage_effect_id IS NULL)),
 CHECK(operation_kind IN('INSTALL_MEMBER','INVALIDATE_REQUESTED','SET_PENDING','REPLACE_PENDING','HANDOFF_RESOLVED','ADOPT_EFFECT') OR (new_external_reservation_bytes=0 AND new_outcome_reservation_bytes=0 AND new_successor_reservation_bytes=0)),
 FOREIGN KEY(lineage_effect_id) REFERENCES registration_effect(effect_id) ON UPDATE NO ACTION ON DELETE NO ACTION DEFERRABLE INITIALLY DEFERRED
) STRICT, WITHOUT ROWID;
CREATE TRIGGER trg_protocol_epoch_insert
BEFORE INSERT ON registration_protocol_epoch
BEGIN
 SELECT RAISE(ABORT,'protocol_epoch_insert_guard')
 WHERE (
  (
   (
    NOT EXISTS(SELECT 1 FROM registration_protocol_epoch)
    AND NEW.protocol_seq=1
    AND NEW.protocol_generation=1
    AND NEW.mode='DORMANT'
    AND NEW.transition_kind='BOOTSTRAP'
    AND NEW.transition_reason_code='BOOTSTRAP'
    AND NEW.previous_protocol_hash IS NULL
    AND NEW.first_effect_id IS NULL
    AND NEW.staged_generation IS NULL
    AND NEW.drain_boot_id IS NULL
    AND NEW.drain_deadline_mono_ns IS NULL
    AND EXISTS(
     SELECT 1 FROM registration_operation_audit o
     WHERE o.operation_seq=1 AND o.operation_id=NEW.operation_id
       AND o.operation_class='BOOTSTRAP' AND o.operation_kind='BOOTSTRAP'
       AND o.target_protocol_hash=NEW.protocol_hash
    )
   )
   OR
   (
    NEW.protocol_seq=(SELECT MAX(protocol_seq)+1 FROM registration_protocol_epoch)
    AND NEW.previous_protocol_hash=(SELECT protocol_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
    AND EXISTS(
     SELECT 1 FROM registration_operation_audit o
     WHERE o.operation_seq=(SELECT MAX(operation_seq) FROM registration_operation_audit)
       AND o.operation_id=NEW.operation_id
       AND o.target_protocol_hash=NEW.protocol_hash
    )
    AND (
     (
      NEW.transition_kind='ACTIVATE'
      AND NEW.transition_reason_code='ACTIVATE'
      AND (SELECT mode FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)='DORMANT'
      AND NEW.mode='WRITABLE'
      AND EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.operation_id AND o.operation_class='CONTROL' AND o.operation_kind='ACTIVATE')
     )
     OR
     (
      NEW.transition_kind='FIRST_EFFECT'
      AND NEW.transition_reason_code='FIRST_EFFECT'
      AND (SELECT mode FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)='WRITABLE'
      AND NEW.mode='WRITABLE'
      AND (SELECT first_effect_id FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) IS NULL
      AND NEW.first_effect_id IS NOT NULL
      AND NEW.first_effect_operation_id=NEW.operation_id
      AND EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.operation_id AND o.operation_class='DATA' AND o.operation_kind='OPEN_EFFECT' AND o.target_effect_id=NEW.first_effect_id)
     )
     OR
     (
      NEW.transition_kind='BEGIN_DRAIN'
      AND NEW.transition_reason_code='BEGIN_DRAIN'
      AND (SELECT mode FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)='WRITABLE'
      AND NEW.mode='DRAINING'
      AND NEW.staged_generation IS NULL
      AND NOT EXISTS(SELECT 1 FROM registration_member WHERE phase='RESOLVED' AND pending_effect_id IS NOT NULL)
      AND NOT EXISTS(SELECT 1 FROM registration_member m JOIN registration_effect e ON e.effect_id=m.current_effect_id WHERE m.phase='REQUESTED' AND e.request_kind='CLEAN_ELIGIBLE' AND e.outcome_kind IS NULL)
      AND NOT EXISTS(SELECT 1 FROM registration_member m JOIN registration_effect e ON e.effect_id=m.current_effect_id WHERE m.phase='EFFECT_IN_FLIGHT' AND e.required_protocol_generation<>(SELECT protocol_generation FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1))
      AND EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.operation_id AND o.operation_class='CONTROL' AND o.operation_kind='BEGIN_DRAIN' AND o.sample_boot_id=NEW.drain_boot_id AND NEW.drain_deadline_mono_ns=o.sample_mono_ns+5000000000)
     )
     OR
     (
      NEW.transition_kind='STAGE_NEXT'
      AND NEW.transition_reason_code='STAGE_NEXT'
      AND (SELECT mode FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)='DRAINING'
      AND NEW.mode='DRAINING'
      AND NEW.staged_generation=(SELECT protocol_generation+1 FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.staged_schema_hash=(SELECT schema_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.quiescence_proof_hash IS NOT NULL
      AND NOT EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_kind='ADOPT_EFFECT' AND o.target_staged_epoch_hash=(SELECT staged_epoch_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1))
      AND NOT EXISTS(SELECT 1 FROM registration_member m WHERE m.helper_generation=(SELECT staged_generation FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1))
      AND NOT EXISTS(SELECT 1 FROM registration_runtime_status s WHERE s.executor_generation=(SELECT staged_generation FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1))
      AND EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.operation_id AND o.operation_class='CONTROL' AND o.operation_kind='STAGE_NEXT' AND o.target_staged_epoch_hash=NEW.staged_epoch_hash AND o.sample_boot_id=(SELECT drain_boot_id FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) AND o.sample_mono_ns<=(SELECT drain_deadline_mono_ns FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1))
     )
     OR
     (
      NEW.transition_kind='CANCEL_DRAIN'
      AND NEW.transition_reason_code='CANCEL_DRAIN'
      AND (SELECT mode FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)='DRAINING'
      AND NEW.mode='DORMANT'
      AND NEW.staged_generation IS NULL
      AND NEW.drain_boot_id IS NULL
      AND NEW.drain_deadline_mono_ns IS NULL
      AND NEW.quiescence_proof_hash IS NOT NULL
      AND NOT EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_kind='ADOPT_EFFECT' AND o.target_staged_epoch_hash=(SELECT staged_epoch_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1))
      AND NOT EXISTS(SELECT 1 FROM registration_member m WHERE m.helper_generation=(SELECT staged_generation FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1))
      AND NOT EXISTS(SELECT 1 FROM registration_runtime_status s WHERE s.executor_generation=(SELECT staged_generation FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1))
      AND EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.operation_id AND o.operation_class='CONTROL' AND o.operation_kind='CANCEL_DRAIN' AND o.sample_boot_id=(SELECT drain_boot_id FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) AND o.sample_mono_ns<=(SELECT drain_deadline_mono_ns FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1))
     )
     OR
     (
      NEW.transition_kind='ADVANCE_GENERATION'
      AND NEW.transition_reason_code='ADVANCE_GENERATION'
      AND (SELECT mode FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)='DRAINING'
      AND (SELECT staged_generation FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) IS NOT NULL
      AND NEW.mode='WRITABLE'
      AND NEW.protocol_generation=(SELECT staged_generation FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.schema_hash=(SELECT staged_schema_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.profile_hash=(SELECT staged_profile_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.runtime_capability_hash=(SELECT staged_runtime_capability_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.writer_binary_hash=(SELECT staged_writer_binary_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.writer_capability_hash=(SELECT staged_writer_capability_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.tool_inventory_hash=(SELECT staged_tool_inventory_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.hook_projection_hash=(SELECT staged_hook_projection_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.hook_matcher_mode=(SELECT staged_hook_matcher_mode FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.hook_matcher_hash=(SELECT staged_hook_matcher_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.projection_receipt_hash=(SELECT staged_projection_receipt_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.projection_file_generation=(SELECT staged_projection_file_generation FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.installer_identity_hash=(SELECT staged_installer_identity_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.installer_capability_hash=(SELECT staged_installer_capability_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.storage_dev=(SELECT storage_dev FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.staged_generation IS NULL
      AND NEW.drain_boot_id IS NULL
      AND NEW.drain_deadline_mono_ns IS NULL
      AND NEW.quiescence_proof_hash IS NOT NULL
      AND NOT EXISTS(SELECT 1 FROM registration_member WHERE phase='EFFECT_IN_FLIGHT' AND helper_generation<>NEW.protocol_generation)
      AND NOT EXISTS(SELECT 1 FROM registration_runtime_status WHERE executor_token_hash IS NOT NULL AND executor_generation<>NEW.protocol_generation)
      AND NOT EXISTS(SELECT 1 FROM registration_member m JOIN registration_effect e ON e.effect_id=m.pending_effect_id WHERE m.pending_effect_id IS NOT NULL AND (e.required_protocol_generation<>NEW.protocol_generation OR e.required_runtime_capability_hash<>NEW.runtime_capability_hash))
      AND NOT EXISTS(SELECT 1 FROM registration_member m JOIN registration_effect e ON e.effect_id=m.current_effect_id WHERE m.phase='REQUESTED' AND e.request_kind='CLEAN_ELIGIBLE' AND e.outcome_kind IS NULL)
      AND EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.operation_id AND o.operation_class='CONTROL' AND o.operation_kind='ADVANCE_GENERATION' AND o.sample_boot_id=(SELECT drain_boot_id FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) AND o.sample_mono_ns<=(SELECT drain_deadline_mono_ns FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1))
     )
     OR
     (
      NEW.transition_kind='PRE_EFFECT_DORMANT'
      AND NEW.transition_reason_code='PRE_EFFECT_DORMANT'
      AND (SELECT mode FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)='DRAINING'
      AND NEW.mode='DORMANT'
      AND NEW.first_effect_id IS NULL
      AND NEW.staged_generation IS NULL
      AND NEW.drain_boot_id IS NULL
      AND NEW.drain_deadline_mono_ns IS NULL
      AND NEW.absence_proof_hash IS NOT NULL
      AND NOT EXISTS(SELECT 1 FROM registration_operation_audit WHERE operation_kind='OPEN_EFFECT')
      AND NOT EXISTS(SELECT 1 FROM registration_effect_action)
      AND NOT EXISTS(SELECT 1 FROM registration_member WHERE phase IN('EFFECT_IN_FLIGHT','RESOLVED'))
      AND NOT EXISTS(SELECT 1 FROM registration_runtime_status WHERE executor_token_hash IS NOT NULL)
      AND EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.operation_id AND o.operation_class='CONTROL' AND o.operation_kind='PRE_EFFECT_DORMANT' AND o.sample_boot_id=(SELECT drain_boot_id FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) AND o.sample_mono_ns<=(SELECT drain_deadline_mono_ns FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1))
     )
     OR
     (
      NEW.transition_kind='ENTER_CONTAINMENT'
      AND NEW.transition_reason_code IN('DRAIN_BOOT_CHANGED','DRAIN_TIMEOUT','ADOPTION_FAILED','STORE_FAILURE')
      AND (SELECT mode FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) IN('DORMANT','WRITABLE','DRAINING')
      AND NEW.mode='CONTAINMENT'
      AND NEW.drain_boot_id IS NULL
      AND NEW.drain_deadline_mono_ns IS NULL
      AND (
       (NEW.transition_reason_code='DRAIN_BOOT_CHANGED' AND (SELECT mode FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)='DRAINING' AND EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.operation_id AND o.sample_boot_id IS NOT NULL AND o.sample_mono_ns IS NOT NULL AND o.sample_boot_id<>(SELECT drain_boot_id FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)))
       OR
       (NEW.transition_reason_code='DRAIN_TIMEOUT' AND (SELECT mode FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)='DRAINING' AND EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.operation_id AND o.sample_boot_id=(SELECT drain_boot_id FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) AND o.sample_mono_ns>(SELECT drain_deadline_mono_ns FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)))
       OR
       (NEW.transition_reason_code='ADOPTION_FAILED' AND (SELECT mode FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)='DRAINING' AND EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.operation_id AND o.sample_boot_id=(SELECT drain_boot_id FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)))
       OR
       (NEW.transition_reason_code='STORE_FAILURE' AND EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.operation_id))
      )
      AND EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.operation_id AND o.operation_class='CONTROL' AND o.operation_kind='ENTER_CONTAINMENT')
     )
     OR
     (
      NEW.transition_kind='BEGIN_REPAIR'
      AND NEW.transition_reason_code='BEGIN_REPAIR'
      AND (SELECT mode FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)='CONTAINMENT'
      AND NEW.mode='DRAINING'
      AND EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.operation_id AND o.operation_class='CONTROL' AND o.operation_kind='BEGIN_REPAIR' AND o.sample_boot_id=NEW.drain_boot_id AND NEW.drain_deadline_mono_ns=o.sample_mono_ns+5000000000)
     )
    )
    AND (
     (
      NEW.transition_kind='FIRST_EFFECT'
      AND (SELECT first_effect_id FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) IS NULL
      AND NEW.first_effect_id IS NOT NULL
      AND NEW.first_effect_operation_id=NEW.operation_id
     )
     OR
     (
      NEW.transition_kind<>'FIRST_EFFECT'
      AND NEW.first_effect_id IS (SELECT first_effect_id FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.first_effect_operation_id IS (SELECT first_effect_operation_id FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
     )
    )
    AND (
     NEW.transition_kind='ADVANCE_GENERATION'
     OR
     (
      NEW.protocol_generation=(SELECT protocol_generation FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.schema_hash=(SELECT schema_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.profile_hash=(SELECT profile_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.runtime_capability_hash=(SELECT runtime_capability_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.writer_binary_hash=(SELECT writer_binary_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.writer_capability_hash=(SELECT writer_capability_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.tool_inventory_hash=(SELECT tool_inventory_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.hook_projection_hash=(SELECT hook_projection_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.hook_matcher_mode=(SELECT hook_matcher_mode FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.hook_matcher_hash=(SELECT hook_matcher_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.projection_receipt_hash=(SELECT projection_receipt_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.projection_file_generation=(SELECT projection_file_generation FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.installer_identity_hash=(SELECT installer_identity_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.installer_capability_hash=(SELECT installer_capability_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.storage_dev=(SELECT storage_dev FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
     )
    )
    AND (
     NEW.transition_kind IN('STAGE_NEXT','CANCEL_DRAIN','ADVANCE_GENERATION','PRE_EFFECT_DORMANT')
     OR
     (
      NEW.staged_generation IS (SELECT staged_generation FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.staged_schema_hash IS (SELECT staged_schema_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.staged_profile_hash IS (SELECT staged_profile_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.staged_runtime_capability_hash IS (SELECT staged_runtime_capability_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.staged_writer_binary_hash IS (SELECT staged_writer_binary_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.staged_writer_capability_hash IS (SELECT staged_writer_capability_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.staged_tool_inventory_hash IS (SELECT staged_tool_inventory_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.staged_hook_projection_hash IS (SELECT staged_hook_projection_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.staged_hook_matcher_mode IS (SELECT staged_hook_matcher_mode FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.staged_hook_matcher_hash IS (SELECT staged_hook_matcher_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.staged_projection_receipt_hash IS (SELECT staged_projection_receipt_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.staged_projection_file_generation IS (SELECT staged_projection_file_generation FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.staged_installer_identity_hash IS (SELECT staged_installer_identity_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.staged_installer_capability_hash IS (SELECT staged_installer_capability_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.staged_epoch_hash IS (SELECT staged_epoch_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
     )
    )
    AND (
     NEW.transition_kind IN('BEGIN_DRAIN','CANCEL_DRAIN','ADVANCE_GENERATION','PRE_EFFECT_DORMANT','ENTER_CONTAINMENT','BEGIN_REPAIR')
     OR (
      NEW.drain_boot_id IS (SELECT drain_boot_id FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.drain_deadline_mono_ns IS (SELECT drain_deadline_mono_ns FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
     )
    )
   )
  )
 ) IS NOT TRUE;
END;
CREATE TRIGGER trg_operation_audit_insert
BEFORE INSERT ON registration_operation_audit
BEGIN
 SELECT RAISE(ABORT,'operation_audit_insert_guard')
 WHERE (
  (
   (
    NOT EXISTS(SELECT 1 FROM registration_operation_audit)
    AND NOT EXISTS(SELECT 1 FROM registration_protocol_epoch)
    AND NEW.operation_seq=1
    AND NEW.operation_class='BOOTSTRAP'
    AND NEW.operation_kind='BOOTSTRAP'
    AND NEW.expected_revision=0
    AND NEW.protocol_seq=0
    AND NEW.expected_mode='NONE'
    AND NEW.expected_generation=0
    AND NEW.expected_protocol_hash IS NULL
   )
   OR
   (
    NEW.operation_seq=(SELECT MAX(operation_seq)+1 FROM registration_operation_audit)
    AND NEW.expected_revision=(SELECT MAX(operation_seq) FROM registration_operation_audit)
    AND NEW.protocol_seq=(SELECT MAX(protocol_seq) FROM registration_protocol_epoch)
    AND NEW.expected_mode=(SELECT mode FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
    AND NEW.expected_generation=(SELECT protocol_generation FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
    AND NEW.expected_protocol_hash=(SELECT protocol_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
    AND NEW.runtime_capability_hash=(SELECT runtime_capability_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
    AND NEW.writer_binary_hash=(SELECT writer_binary_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
    AND NEW.profile_hash=(SELECT profile_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
    AND (
     (
      NEW.operation_class='DATA'
      AND (SELECT mode FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)='WRITABLE'
      AND NEW.writer_capability_receipt_hash=(SELECT writer_capability_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
     )
     OR
     (
      NEW.operation_class='CONTROL'
      AND NEW.installer_identity_hash=(SELECT installer_identity_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.installer_capability_receipt_hash=(SELECT installer_capability_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.protocol_lock_receipt_hash IS NOT NULL
      AND NEW.control_binding_hash IS NOT NULL
     )
    )
    AND (
     NEW.operation_kind NOT IN('OPEN_EFFECT','REACQUIRE_EFFECT','APPEND_ACTION','CLOSE_SUCCESS','CLOSE_CONFLICT','MARK_UNAVAILABLE','ADOPT_EFFECT')
     OR EXISTS(
      SELECT 1 FROM registration_runtime_status s
      JOIN registration_member m ON m.member_id=s.member_id
      WHERE s.member_id=NEW.target_member_id
        AND s.current_effect_id=m.current_effect_id
        AND s.status_hash=NEW.expected_target_status_hash
        AND (
         (NEW.operation_kind='OPEN_EFFECT' AND m.phase='REQUESTED' AND s.executor_token_hash IS NULL AND s.schedule_boot_id=NEW.sample_boot_id AND s.next_due_mono_ns<=NEW.sample_mono_ns AND s.reason_code='REGISTRATION_REQUIRED' AND NEW.target_effect_id=m.current_effect_id AND NEW.expected_target_member_tuple_hash=m.member_tuple_hash AND NEW.expected_target_effect_tuple_hash=(SELECT request_tuple_hash FROM registration_effect WHERE effect_id=m.current_effect_id))
         OR
         (NEW.operation_kind='REACQUIRE_EFFECT' AND m.phase='EFFECT_IN_FLIGHT' AND s.executor_token_hash IS NULL AND NEW.target_effect_id=m.current_effect_id)
         OR
         (NEW.operation_kind IN('APPEND_ACTION','CLOSE_SUCCESS','CLOSE_CONFLICT','MARK_UNAVAILABLE') AND m.phase='EFFECT_IN_FLIGHT' AND s.executor_token_hash=NEW.target_executor_token_hash AND NEW.target_effect_id=m.current_effect_id)
         OR
         (NEW.operation_kind='ADOPT_EFFECT' AND m.phase='EFFECT_IN_FLIGHT' AND (s.executor_token_hash=NEW.target_executor_token_hash OR s.executor_token_hash IS NULL))
        )
     )
    )
   )
  )
  AND (
   (
    NEW.operation_kind IN('BOOTSTRAP','INSTALL_MEMBER','BIND_EPISODE','REACQUIRE_EFFECT','OPEN_EFFECT','SET_PENDING','MARK_UNAVAILABLE','REBOOT_STATUS','SCHEDULE_STATUS')
    AND NEW.control_reserve_bytes=14680064
    AND NEW.measured_free_bytes>=1088421888+NEW.projected_db_growth_bytes+
      COALESCE((SELECT SUM(CASE WHEN e.outcome_kind IS NULL THEN e.external_growth_reservation_bytes+e.outcome_reservation_bytes+e.successor_reservation_bytes ELSE e.successor_reservation_bytes END) FROM registration_effect e WHERE e.outcome_kind IS NULL OR EXISTS(SELECT 1 FROM registration_member m WHERE m.current_effect_id=e.effect_id AND m.phase='RESOLVED')),0)+
      NEW.new_external_reservation_bytes+NEW.new_outcome_reservation_bytes+NEW.new_successor_reservation_bytes
   )
   OR
   (
    NEW.operation_kind IN('APPEND_ACTION','CLOSE_SUCCESS','CLOSE_CONFLICT','INVALIDATE_REQUESTED','REPLACE_PENDING','HANDOFF_RESOLVED')
    AND NEW.control_reserve_bytes=14680064
    AND NEW.measured_free_bytes>=1088421888+NEW.projected_db_growth_bytes+
      COALESCE((SELECT SUM(CASE WHEN e.outcome_kind IS NULL THEN e.external_growth_reservation_bytes+e.outcome_reservation_bytes+e.successor_reservation_bytes ELSE e.successor_reservation_bytes END) FROM registration_effect e WHERE (e.outcome_kind IS NULL OR EXISTS(SELECT 1 FROM registration_member m WHERE m.current_effect_id=e.effect_id AND m.phase='RESOLVED')) AND e.effect_id IS NOT NEW.target_effect_id),0)+
      NEW.new_external_reservation_bytes+NEW.new_outcome_reservation_bytes+NEW.new_successor_reservation_bytes+
      CASE
       WHEN NEW.operation_kind='APPEND_ACTION' THEN COALESCE((SELECT e.successor_reservation_bytes+(e.outcome_reservation_bytes-(SELECT COALESCE(SUM(projected_db_growth_bytes),0) FROM registration_operation_audit WHERE operation_kind='APPEND_ACTION' AND target_effect_id=NEW.target_effect_id)-NEW.projected_db_growth_bytes)+(e.external_growth_reservation_bytes-(SELECT COALESCE(SUM(external_growth_bytes),0) FROM registration_effect_action WHERE effect_id=NEW.target_effect_id)-NEW.external_growth_bytes) FROM registration_effect e WHERE e.effect_id=NEW.target_effect_id),0)
       WHEN NEW.operation_kind IN('CLOSE_SUCCESS','CLOSE_CONFLICT') THEN COALESCE((SELECT successor_reservation_bytes FROM registration_effect WHERE effect_id=NEW.target_effect_id),0)
       ELSE 0
      END
    AND (
     (NEW.operation_kind='APPEND_ACTION' AND EXISTS(SELECT 1 FROM registration_effect e WHERE e.effect_id=NEW.target_effect_id AND e.outcome_kind IS NULL AND (SELECT COALESCE(SUM(projected_db_growth_bytes),0) FROM registration_operation_audit WHERE operation_kind='APPEND_ACTION' AND target_effect_id=NEW.target_effect_id)+NEW.projected_db_growth_bytes<=e.outcome_reservation_bytes AND (SELECT COALESCE(SUM(external_growth_bytes),0) FROM registration_effect_action WHERE effect_id=NEW.target_effect_id)+NEW.external_growth_bytes<=e.external_growth_reservation_bytes))
     OR
     (NEW.operation_kind IN('CLOSE_SUCCESS','CLOSE_CONFLICT') AND EXISTS(SELECT 1 FROM registration_effect e WHERE e.effect_id=NEW.target_effect_id AND e.outcome_kind IS NULL AND (SELECT COALESCE(SUM(projected_db_growth_bytes),0) FROM registration_operation_audit WHERE operation_kind='APPEND_ACTION' AND target_effect_id=NEW.target_effect_id)+NEW.projected_db_growth_bytes<=e.outcome_reservation_bytes))
     OR
     (NEW.operation_kind IN('INVALIDATE_REQUESTED','REPLACE_PENDING') AND EXISTS(SELECT 1 FROM registration_effect e WHERE e.effect_id=NEW.target_effect_id AND e.outcome_kind IS NULL AND NEW.projected_db_growth_bytes<=e.outcome_reservation_bytes+e.successor_reservation_bytes))
     OR
     (NEW.operation_kind='HANDOFF_RESOLVED' AND EXISTS(SELECT 1 FROM registration_effect e JOIN registration_member m ON m.current_effect_id=e.effect_id WHERE e.effect_id=NEW.target_effect_id AND e.outcome_kind IN('SUCCESS','LOGICAL_CONFLICT') AND m.phase='RESOLVED' AND NEW.projected_db_growth_bytes<=e.successor_reservation_bytes))
    )
   )
   OR
   (
    NEW.operation_class='CONTROL'
    AND NEW.operation_kind IN('ACTIVATE','BEGIN_DRAIN','STAGE_NEXT','CANCEL_DRAIN','ADOPT_EFFECT','ADVANCE_GENERATION','PRE_EFFECT_DORMANT','ENTER_CONTAINMENT','BEGIN_REPAIR')
    AND NEW.measured_free_bytes>=1073741824+NEW.control_reserve_bytes+NEW.projected_db_growth_bytes+
      COALESCE((SELECT SUM(CASE WHEN e.outcome_kind IS NULL THEN e.external_growth_reservation_bytes+e.outcome_reservation_bytes+e.successor_reservation_bytes ELSE e.successor_reservation_bytes END) FROM registration_effect e WHERE (e.outcome_kind IS NULL OR EXISTS(SELECT 1 FROM registration_member m WHERE m.current_effect_id=e.effect_id AND m.phase='RESOLVED')) AND NOT (NEW.operation_kind='ADOPT_EFFECT' AND NEW.target_successor_effect_id IS NOT NULL AND e.effect_id IS NEW.target_effect_id AND EXISTS(SELECT 1 FROM registration_member m WHERE m.member_id=NEW.target_member_id AND m.phase='EFFECT_IN_FLIGHT' AND m.pending_effect_id=e.effect_id))),0)+
      NEW.new_external_reservation_bytes+NEW.new_outcome_reservation_bytes+NEW.new_successor_reservation_bytes
    AND NEW.projected_db_growth_bytes<=1048576
   )
  )
 ) IS NOT TRUE;
END;
CREATE TRIGGER trg_member_update_state_machine
BEFORE UPDATE ON registration_member
BEGIN
 SELECT RAISE(ABORT,'member_update_state_machine_guard')
 WHERE (
  (NEW.member_id,NEW.canonical_root,NEW.root_dev,NEW.root_ino,NEW.git_toplevel,NEW.git_dir,NEW.git_dir_dev,NEW.git_dir_ino,NEW.git_common_dir,NEW.git_common_dev,NEW.git_common_ino,NEW.proof_dev,NEW.projection_dev,NEW.legacy_state_dev,NEW.physical_basis_hash,NEW.git_basis_hash,NEW.runtime_subject_key)
  IS
  (OLD.member_id,OLD.canonical_root,OLD.root_dev,OLD.root_ino,OLD.git_toplevel,OLD.git_dir,OLD.git_dir_dev,OLD.git_dir_ino,OLD.git_common_dir,OLD.git_common_dev,OLD.git_common_ino,OLD.proof_dev,OLD.projection_dev,OLD.legacy_state_dev,OLD.physical_basis_hash,OLD.git_basis_hash,OLD.runtime_subject_key)
  AND EXISTS(
   SELECT 1 FROM registration_operation_audit o
   WHERE o.operation_seq=(SELECT MAX(operation_seq) FROM registration_operation_audit)
     AND o.operation_seq=NEW.write_operation_seq
     AND o.operation_id=NEW.write_operation_id
     AND o.operation_envelope_hash=NEW.write_operation_hash
     AND o.target_member_id=NEW.member_id
     AND o.expected_target_member_tuple_hash=OLD.member_tuple_hash
     AND o.target_member_epoch=NEW.member_epoch
     AND o.target_basis_hash=NEW.current_basis_hash
     AND o.target_member_tuple_hash=NEW.member_tuple_hash
  )
  AND (
   (
    OLD.phase='REQUESTED' AND NEW.phase='REQUESTED'
    AND NEW.member_epoch=OLD.member_epoch+1
    AND NEW.pending_effect_id IS NULL
    AND EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.write_operation_id AND o.operation_kind='INVALIDATE_REQUESTED' AND o.target_effect_id=OLD.current_effect_id AND o.target_successor_effect_id=NEW.current_effect_id AND o.target_transition_id IS NOT NULL AND o.expected_target_effect_tuple_hash=(SELECT request_tuple_hash FROM registration_effect WHERE effect_id=OLD.current_effect_id) AND o.target_effect_tuple_hash=(SELECT request_tuple_hash FROM registration_effect WHERE effect_id=NEW.current_effect_id) AND o.expected_target_status_hash IS NOT NULL AND o.target_status_hash IS NOT NULL AND o.target_cause_code IS NOT NULL)
    AND EXISTS(SELECT 1 FROM registration_effect e WHERE e.effect_id=OLD.current_effect_id AND e.outcome_kind='SUPERSEDED' AND e.outcome_operation_id=NEW.write_operation_id)
    AND EXISTS(SELECT 1 FROM registration_effect e JOIN registration_operation_audit o ON o.operation_id=NEW.write_operation_id WHERE e.effect_id=NEW.current_effect_id AND e.outcome_kind IS NULL AND e.member_id=NEW.member_id AND e.member_epoch=NEW.member_epoch AND e.request_basis_hash=NEW.current_basis_hash AND e.request_tuple_hash=o.target_effect_tuple_hash AND NEW.helper_generation=e.required_protocol_generation)
    AND EXISTS(SELECT 1 FROM registration_runtime_status s JOIN registration_operation_audit o ON o.operation_id=NEW.write_operation_id WHERE s.member_id=NEW.member_id AND s.current_effect_id=NEW.current_effect_id AND s.status_hash=o.target_status_hash AND s.executor_token_hash IS NULL)
   )
   OR
   (
    OLD.phase='REQUESTED' AND NEW.phase='EFFECT_IN_FLIGHT'
    AND (NEW.policy_basis_hash,NEW.operation_basis_hash,NEW.lifecycle_basis_hash,NEW.current_basis_hash,NEW.member_epoch,NEW.current_effect_id,NEW.helper_generation,NEW.current_outcome_kind,NEW.current_completion_hash,NEW.current_proof_hash,NEW.current_certificate_hash,NEW.current_conflict_hash,NEW.pending_effect_id,NEW.pending_member_epoch,NEW.pending_basis_hash,NEW.pending_effect_tuple_hash)
       IS (OLD.policy_basis_hash,OLD.operation_basis_hash,OLD.lifecycle_basis_hash,OLD.current_basis_hash,OLD.member_epoch,OLD.current_effect_id,OLD.helper_generation,OLD.current_outcome_kind,OLD.current_completion_hash,OLD.current_proof_hash,OLD.current_certificate_hash,OLD.current_conflict_hash,NULL,NULL,NULL,NULL)
    AND EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.write_operation_id AND o.operation_kind='OPEN_EFFECT' AND o.target_effect_id=NEW.current_effect_id)
    AND EXISTS(SELECT 1 FROM registration_effect e WHERE e.effect_id=NEW.current_effect_id AND e.request_kind='CLEAN_ELIGIBLE' AND e.outcome_kind IS NULL)
    AND EXISTS(SELECT 1 FROM registration_runtime_status s JOIN registration_operation_audit o ON o.operation_id=NEW.write_operation_id WHERE s.member_id=NEW.member_id AND s.current_effect_id=NEW.current_effect_id AND s.executor_token_hash=o.target_executor_token_hash AND s.executor_boot_id=o.sample_boot_id AND s.executor_generation=NEW.helper_generation AND s.reason_code='EFFECT_IN_FLIGHT')
    AND EXISTS(SELECT 1 FROM registration_protocol_epoch p WHERE p.protocol_seq=(SELECT MAX(protocol_seq) FROM registration_protocol_epoch) AND p.mode='WRITABLE' AND p.first_effect_id IS NOT NULL AND p.first_effect_operation_id IS NOT NULL)
   )
   OR
   (
    OLD.phase='EFFECT_IN_FLIGHT' AND NEW.phase='EFFECT_IN_FLIGHT'
    AND (NEW.policy_basis_hash,NEW.operation_basis_hash,NEW.lifecycle_basis_hash,NEW.current_basis_hash,NEW.member_epoch,NEW.current_effect_id,NEW.helper_generation,NEW.current_outcome_kind,NEW.current_completion_hash,NEW.current_proof_hash,NEW.current_certificate_hash,NEW.current_conflict_hash)
       IS (OLD.policy_basis_hash,OLD.operation_basis_hash,OLD.lifecycle_basis_hash,OLD.current_basis_hash,OLD.member_epoch,OLD.current_effect_id,OLD.helper_generation,OLD.current_outcome_kind,OLD.current_completion_hash,OLD.current_proof_hash,OLD.current_certificate_hash,OLD.current_conflict_hash)
    AND EXISTS(SELECT 1 FROM registration_operation_audit o JOIN registration_runtime_status s ON s.member_id=NEW.member_id WHERE o.operation_id=NEW.write_operation_id AND o.operation_kind IN('SET_PENDING','REPLACE_PENDING') AND o.target_successor_effect_id=NEW.pending_effect_id AND o.expected_target_status_hash=s.status_hash AND o.target_status_hash=s.status_hash AND o.target_effect_tuple_hash=NEW.pending_effect_tuple_hash)
    AND NEW.pending_effect_id IS NOT NULL
    AND NEW.pending_member_epoch=COALESCE(OLD.pending_member_epoch,OLD.member_epoch)+1
    AND EXISTS(SELECT 1 FROM registration_effect e WHERE e.effect_id=NEW.pending_effect_id AND e.member_id=NEW.member_id AND e.member_epoch=NEW.pending_member_epoch AND e.request_basis_hash=NEW.pending_basis_hash AND e.request_tuple_hash=NEW.pending_effect_tuple_hash AND e.outcome_kind IS NULL)
    AND (
     (OLD.pending_effect_id IS NULL AND EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.write_operation_id AND o.operation_kind='SET_PENDING' AND o.target_effect_id=OLD.current_effect_id AND o.expected_target_effect_tuple_hash=(SELECT request_tuple_hash FROM registration_effect WHERE effect_id=OLD.current_effect_id)))
     OR
     (OLD.pending_effect_id IS NOT NULL AND EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.write_operation_id AND o.operation_kind='REPLACE_PENDING' AND o.target_effect_id=OLD.pending_effect_id AND o.expected_target_effect_tuple_hash=OLD.pending_effect_tuple_hash AND o.target_effect_tuple_hash=NEW.pending_effect_tuple_hash AND o.target_cause_code IS NOT NULL AND o.target_transition_id IS NOT NULL) AND EXISTS(SELECT 1 FROM registration_effect e WHERE e.effect_id=OLD.pending_effect_id AND e.outcome_kind='SUPERSEDED' AND e.outcome_operation_id=NEW.write_operation_id))
    )
   )
   OR
   (
    OLD.phase='EFFECT_IN_FLIGHT' AND NEW.phase='EFFECT_IN_FLIGHT'
    AND EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.write_operation_id AND o.operation_class='CONTROL' AND o.operation_kind='ADOPT_EFFECT' AND o.expected_mode='DRAINING' AND o.lineage_effect_id=NEW.current_effect_id AND o.target_action_plan_hash=(SELECT action_plan_hash FROM registration_effect WHERE effect_id=NEW.current_effect_id) AND o.target_staged_epoch_hash=(SELECT staged_epoch_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) AND o.sample_boot_id=(SELECT drain_boot_id FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) AND o.sample_mono_ns<=(SELECT drain_deadline_mono_ns FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1))
    AND OLD.helper_generation=(SELECT protocol_generation FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
    AND OLD.helper_generation<>(SELECT staged_generation FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
    AND NEW.helper_generation=(SELECT staged_generation FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
    AND (NEW.policy_basis_hash,NEW.operation_basis_hash,NEW.lifecycle_basis_hash,NEW.current_basis_hash,NEW.member_epoch,NEW.current_effect_id,NEW.current_outcome_kind,NEW.current_completion_hash,NEW.current_proof_hash,NEW.current_certificate_hash,NEW.current_conflict_hash)
       IS (OLD.policy_basis_hash,OLD.operation_basis_hash,OLD.lifecycle_basis_hash,OLD.current_basis_hash,OLD.member_epoch,OLD.current_effect_id,OLD.current_outcome_kind,OLD.current_completion_hash,OLD.current_proof_hash,OLD.current_certificate_hash,OLD.current_conflict_hash)
    AND EXISTS(SELECT 1 FROM registration_runtime_status s JOIN registration_operation_audit o ON o.operation_id=NEW.write_operation_id WHERE s.member_id=NEW.member_id AND s.executor_generation=NEW.helper_generation AND s.status_hash=o.target_status_hash)
    AND (
     (OLD.pending_effect_id IS NULL AND NEW.pending_effect_id IS NULL AND EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.write_operation_id AND o.target_effect_id=OLD.current_effect_id AND o.target_successor_effect_id IS NULL))
     OR
     (
      OLD.pending_effect_id IS NOT NULL
      AND EXISTS(SELECT 1 FROM registration_effect old_pending WHERE old_pending.effect_id=OLD.pending_effect_id AND (old_pending.required_protocol_generation<>(SELECT staged_generation FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) OR old_pending.required_runtime_capability_hash<>(SELECT staged_runtime_capability_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)))
      AND NEW.pending_effect_id IS NOT NULL
      AND NEW.pending_effect_id IS NOT OLD.pending_effect_id
      AND NEW.pending_member_epoch=OLD.pending_member_epoch+1
      AND EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.write_operation_id AND o.target_effect_id=OLD.pending_effect_id AND o.target_successor_effect_id=NEW.pending_effect_id)
      AND EXISTS(SELECT 1 FROM registration_effect e WHERE e.effect_id=NEW.pending_effect_id AND e.member_id=NEW.member_id AND e.member_epoch=NEW.pending_member_epoch AND e.request_basis_hash=NEW.pending_basis_hash AND e.request_tuple_hash=NEW.pending_effect_tuple_hash AND e.outcome_kind IS NULL AND e.required_protocol_generation=(SELECT staged_generation FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) AND e.required_runtime_capability_hash=(SELECT staged_runtime_capability_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1))
      AND EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.write_operation_id AND o.expected_target_effect_tuple_hash=OLD.pending_effect_tuple_hash AND o.target_effect_tuple_hash=NEW.pending_effect_tuple_hash AND o.target_cause_code IS NOT NULL AND o.target_transition_id IS NOT NULL)
      AND EXISTS(SELECT 1 FROM registration_effect e WHERE e.effect_id=OLD.pending_effect_id AND e.outcome_kind='SUPERSEDED' AND e.outcome_operation_id=NEW.write_operation_id)
     )
    )
   )
   OR
   (
    OLD.phase='EFFECT_IN_FLIGHT' AND NEW.phase='RESOLVED'
    AND (NEW.policy_basis_hash,NEW.operation_basis_hash,NEW.lifecycle_basis_hash,NEW.current_basis_hash,NEW.member_epoch,NEW.current_effect_id,NEW.helper_generation,NEW.pending_effect_id,NEW.pending_member_epoch,NEW.pending_basis_hash,NEW.pending_effect_tuple_hash)
       IS (OLD.policy_basis_hash,OLD.operation_basis_hash,OLD.lifecycle_basis_hash,OLD.current_basis_hash,OLD.member_epoch,OLD.current_effect_id,OLD.helper_generation,OLD.pending_effect_id,OLD.pending_member_epoch,OLD.pending_basis_hash,OLD.pending_effect_tuple_hash)
    AND EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.write_operation_id AND o.operation_kind IN('CLOSE_SUCCESS','CLOSE_CONFLICT') AND o.target_effect_id=NEW.current_effect_id)
    AND EXISTS(SELECT 1 FROM registration_effect e WHERE e.effect_id=NEW.current_effect_id AND e.outcome_kind=NEW.current_outcome_kind AND e.outcome_helper_generation=NEW.helper_generation AND e.completion_hash IS NEW.current_completion_hash AND e.proof_hash IS NEW.current_proof_hash AND e.certificate_hash IS NEW.current_certificate_hash AND e.conflict_hash IS NEW.current_conflict_hash)
    AND EXISTS(SELECT 1 FROM registration_runtime_status s WHERE s.member_id=NEW.member_id AND s.current_effect_id=NEW.current_effect_id AND s.executor_token_hash IS NULL AND ((NEW.pending_effect_id IS NULL AND s.schedule_boot_id IS NULL AND s.help_due=0) OR (NEW.pending_effect_id IS NOT NULL AND s.schedule_boot_id IS NOT NULL AND s.help_due=1 AND s.reason_code='REGISTRATION_REQUIRED')))
   )
   OR
   (
    OLD.phase='RESOLVED' AND NEW.phase='REQUESTED'
    AND NEW.current_outcome_kind IS NULL
    AND NEW.pending_effect_id IS NULL
    AND NEW.member_epoch=CASE WHEN OLD.pending_effect_id IS NULL THEN OLD.member_epoch+1 ELSE OLD.pending_member_epoch END
    AND EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.write_operation_id AND o.operation_kind='HANDOFF_RESOLVED' AND o.target_effect_id=OLD.current_effect_id AND o.target_successor_effect_id=NEW.current_effect_id AND o.target_transition_id IS NOT NULL AND o.expected_target_effect_tuple_hash=(SELECT outcome_tuple_hash FROM registration_effect WHERE effect_id=OLD.current_effect_id) AND o.target_effect_tuple_hash=(SELECT request_tuple_hash FROM registration_effect WHERE effect_id=NEW.current_effect_id) AND o.expected_target_status_hash IS NOT NULL AND o.target_status_hash IS NOT NULL AND o.target_cause_code IS NOT NULL)
    AND EXISTS(SELECT 1 FROM registration_effect e JOIN registration_operation_audit o ON o.operation_id=NEW.write_operation_id WHERE e.effect_id=NEW.current_effect_id AND e.outcome_kind IS NULL AND e.member_id=NEW.member_id AND e.member_epoch=NEW.member_epoch AND e.request_basis_hash=NEW.current_basis_hash AND e.request_tuple_hash=o.target_effect_tuple_hash AND NEW.helper_generation=e.required_protocol_generation)
    AND (OLD.pending_effect_id IS NULL OR NEW.current_effect_id=OLD.pending_effect_id)
    AND EXISTS(SELECT 1 FROM registration_runtime_status s JOIN registration_operation_audit o ON o.operation_id=NEW.write_operation_id WHERE s.member_id=NEW.member_id AND s.current_effect_id=NEW.current_effect_id AND s.status_hash=o.target_status_hash AND s.executor_token_hash IS NULL)
    AND (
     (OLD.pending_effect_id IS NOT NULL AND EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.write_operation_id AND o.target_cause_code='BASIS_CHANGED'))
     OR
     (NEW.current_basis_hash IS NOT OLD.current_basis_hash AND EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.write_operation_id AND o.target_cause_code IN('BASIS_CHANGED','CURRENT_CLOSURE_CHANGED')))
     OR
     (OLD.current_outcome_kind='LOGICAL_CONFLICT' AND EXISTS(SELECT 1 FROM registration_operation_audit o JOIN registration_effect e ON e.effect_id=NEW.current_effect_id WHERE o.operation_id=NEW.write_operation_id AND o.target_cause_code='EXPLICIT_CONFLICT_RETRY' AND e.request_kind='CLEAN_ELIGIBLE'))
    )
   )
  )
 ) IS NOT TRUE;
END;
CREATE TRIGGER trg_episode_insert
BEFORE INSERT ON registration_episode
BEGIN
 SELECT RAISE(ABORT,'episode_insert_guard')
 WHERE (
  EXISTS(
   SELECT 1 FROM registration_operation_audit o
   JOIN registration_protocol_epoch p ON p.protocol_seq=(SELECT MAX(protocol_seq) FROM registration_protocol_epoch)
   JOIN registration_member m ON m.member_id=NEW.member_id
   WHERE o.operation_seq=(SELECT MAX(operation_seq) FROM registration_operation_audit)
     AND o.operation_seq=NEW.write_operation_seq
     AND o.operation_id=NEW.write_operation_id
     AND o.operation_envelope_hash=NEW.write_operation_hash
     AND o.operation_class='DATA'
     AND o.operation_kind='BIND_EPISODE'
     AND o.target_episode_id=NEW.episode_id
     AND o.target_member_id=NEW.member_id
     AND o.target_episode_hash=NEW.envelope_hash
     AND NEW.protocol_generation=p.protocol_generation
     AND NEW.tool_inventory_hash=p.tool_inventory_hash
     AND NEW.hook_projection_hash=p.hook_projection_hash
     AND NEW.workspace_root_count=1
  )
 ) IS NOT TRUE;
END;
CREATE TRIGGER trg_effect_insert
BEFORE INSERT ON registration_effect
BEGIN
 SELECT RAISE(ABORT,'effect_insert_guard')
 WHERE (
  NEW.outcome_kind IS NULL
  AND EXISTS(
   SELECT 1 FROM registration_operation_audit o
   WHERE o.operation_seq=(SELECT MAX(operation_seq) FROM registration_operation_audit)
     AND o.operation_seq=NEW.created_operation_seq
     AND o.operation_id=NEW.created_operation_id
     AND o.operation_envelope_hash=NEW.created_operation_hash
     AND o.target_member_id=NEW.member_id
     AND o.target_successor_effect_id=NEW.effect_id
     AND o.target_successor_member_epoch=NEW.member_epoch
     AND o.target_successor_basis_hash=NEW.request_basis_hash
     AND o.target_effect_tuple_hash=NEW.request_tuple_hash
     AND o.new_external_reservation_bytes=NEW.external_growth_reservation_bytes
     AND o.new_outcome_reservation_bytes=NEW.outcome_reservation_bytes
     AND o.new_successor_reservation_bytes=NEW.successor_reservation_bytes
  )
  AND EXISTS(SELECT 1 FROM registration_member m JOIN registration_protocol_epoch p ON p.protocol_seq=(SELECT MAX(protocol_seq) FROM registration_protocol_epoch) WHERE m.member_id=NEW.member_id AND m.root_dev=p.storage_dev)
  AND (
   (
    EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.created_operation_id AND o.operation_class='DATA')
    AND NEW.required_protocol_generation=(SELECT protocol_generation FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
    AND NEW.required_runtime_capability_hash=(SELECT runtime_capability_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
   )
   OR
   (
    EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.created_operation_id AND o.operation_class='CONTROL' AND o.operation_kind='ADOPT_EFFECT')
    AND NEW.required_protocol_generation=(SELECT staged_generation FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
    AND NEW.required_runtime_capability_hash=(SELECT staged_runtime_capability_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
   )
  )
  AND (
   (
    EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.created_operation_id AND o.operation_kind='INSTALL_MEMBER' AND o.target_effect_id IS NULL AND o.expected_target_member_tuple_hash IS NULL)
    AND NEW.member_epoch=1 AND NEW.predecessor_effect_id IS NULL
    AND EXISTS(SELECT 1 FROM registration_member m JOIN registration_operation_audit o ON o.operation_id=NEW.created_operation_id WHERE m.member_id=NEW.member_id AND m.phase='REQUESTED' AND m.current_effect_id=NEW.effect_id AND m.member_epoch=1 AND m.current_basis_hash=NEW.request_basis_hash AND m.helper_generation=NEW.required_protocol_generation AND m.member_tuple_hash=o.target_member_tuple_hash AND m.write_operation_seq=o.operation_seq AND m.write_operation_id=o.operation_id AND m.write_operation_hash=o.operation_envelope_hash)
   )
   OR
   (
    EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.created_operation_id AND o.operation_kind='INVALIDATE_REQUESTED' AND o.target_effect_id=NEW.predecessor_effect_id)
    AND EXISTS(SELECT 1 FROM registration_member m JOIN registration_effect prior ON prior.effect_id=m.current_effect_id WHERE m.member_id=NEW.member_id AND m.phase='REQUESTED' AND NEW.predecessor_effect_id=m.current_effect_id AND NEW.member_epoch=m.member_epoch+1 AND (NEW.request_basis_hash IS NOT m.current_basis_hash OR NEW.request_tuple_hash IS NOT prior.request_tuple_hash))
   )
   OR
   (
    EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.created_operation_id AND o.operation_kind='SET_PENDING' AND o.target_effect_id=NEW.predecessor_effect_id)
    AND EXISTS(SELECT 1 FROM registration_member m JOIN registration_effect prior ON prior.effect_id=m.current_effect_id WHERE m.member_id=NEW.member_id AND m.phase='EFFECT_IN_FLIGHT' AND m.pending_effect_id IS NULL AND NEW.predecessor_effect_id=m.current_effect_id AND NEW.member_epoch=m.member_epoch+1 AND (NEW.request_basis_hash IS NOT m.current_basis_hash OR NEW.request_tuple_hash IS NOT prior.request_tuple_hash))
   )
   OR
   (
    EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.created_operation_id AND o.operation_kind='REPLACE_PENDING' AND o.target_effect_id=NEW.predecessor_effect_id)
    AND EXISTS(SELECT 1 FROM registration_member m JOIN registration_effect prior ON prior.effect_id=m.pending_effect_id WHERE m.member_id=NEW.member_id AND m.phase='EFFECT_IN_FLIGHT' AND m.pending_effect_id IS NOT NULL AND NEW.predecessor_effect_id=m.pending_effect_id AND NEW.member_epoch=m.pending_member_epoch+1 AND (NEW.request_basis_hash IS NOT m.pending_basis_hash OR NEW.request_tuple_hash IS NOT prior.request_tuple_hash))
   )
   OR
   (
    EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.created_operation_id AND o.operation_kind='HANDOFF_RESOLVED' AND o.target_effect_id=NEW.predecessor_effect_id)
    AND EXISTS(
     SELECT 1 FROM registration_member m
     JOIN registration_operation_audit o ON o.operation_id=NEW.created_operation_id
     WHERE m.member_id=NEW.member_id
       AND m.phase='RESOLVED'
       AND m.pending_effect_id IS NULL
       AND NEW.predecessor_effect_id=m.current_effect_id
       AND NEW.member_epoch=m.member_epoch+1
       AND (
        (NEW.request_basis_hash IS NOT m.current_basis_hash AND o.target_cause_code IN('BASIS_CHANGED','CURRENT_CLOSURE_CHANGED'))
        OR (m.current_outcome_kind='LOGICAL_CONFLICT' AND o.target_cause_code='EXPLICIT_CONFLICT_RETRY' AND NEW.request_kind='CLEAN_ELIGIBLE')
       )
    )
   )
   OR
   (
    EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.created_operation_id AND o.operation_class='CONTROL' AND o.operation_kind='ADOPT_EFFECT' AND o.expected_mode='DRAINING' AND o.target_effect_id=NEW.predecessor_effect_id AND o.target_staged_epoch_hash=(SELECT staged_epoch_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1))
    AND NEW.required_runtime_capability_hash=(SELECT staged_runtime_capability_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
    AND EXISTS(SELECT 1 FROM registration_member m WHERE m.member_id=NEW.member_id AND m.phase='EFFECT_IN_FLIGHT' AND m.pending_effect_id IS NOT NULL AND NEW.predecessor_effect_id=m.pending_effect_id AND NEW.member_epoch=m.pending_member_epoch+1)
   )
  )
 ) IS NOT TRUE;
END;
CREATE TRIGGER trg_effect_close
BEFORE UPDATE ON registration_effect
BEGIN
 SELECT RAISE(ABORT,'effect_close_guard')
 WHERE (
  (NEW.effect_id,NEW.member_id,NEW.member_epoch,NEW.request_kind,NEW.request_basis_hash,NEW.predecessor_effect_id,NEW.required_protocol_generation,NEW.required_runtime_capability_hash,NEW.action_plan_hash,NEW.action_plan_blob,NEW.required_action_count,NEW.action_1_kind,NEW.action_1_hash,NEW.postcondition_1_hash,NEW.action_2_kind,NEW.action_2_hash,NEW.postcondition_2_hash,NEW.action_3_kind,NEW.action_3_hash,NEW.postcondition_3_hash,NEW.action_4_kind,NEW.action_4_hash,NEW.postcondition_4_hash,NEW.external_growth_reservation_bytes,NEW.outcome_reservation_bytes,NEW.successor_reservation_bytes,NEW.request_tuple_hash,NEW.created_operation_seq,NEW.created_operation_id,NEW.created_operation_hash)
  IS
  (OLD.effect_id,OLD.member_id,OLD.member_epoch,OLD.request_kind,OLD.request_basis_hash,OLD.predecessor_effect_id,OLD.required_protocol_generation,OLD.required_runtime_capability_hash,OLD.action_plan_hash,OLD.action_plan_blob,OLD.required_action_count,OLD.action_1_kind,OLD.action_1_hash,OLD.postcondition_1_hash,OLD.action_2_kind,OLD.action_2_hash,OLD.postcondition_2_hash,OLD.action_3_kind,OLD.action_3_hash,OLD.postcondition_3_hash,OLD.action_4_kind,OLD.action_4_hash,OLD.postcondition_4_hash,OLD.external_growth_reservation_bytes,OLD.outcome_reservation_bytes,OLD.successor_reservation_bytes,OLD.request_tuple_hash,OLD.created_operation_seq,OLD.created_operation_id,OLD.created_operation_hash)
  AND OLD.outcome_kind IS NULL
  AND NEW.outcome_kind IS NOT NULL
  AND EXISTS(
   SELECT 1 FROM registration_operation_audit o
   WHERE o.operation_seq=(SELECT MAX(operation_seq) FROM registration_operation_audit)
     AND o.operation_seq=NEW.outcome_operation_seq
     AND o.operation_id=NEW.outcome_operation_id
     AND o.operation_envelope_hash=NEW.outcome_operation_hash
     AND o.target_member_id=NEW.member_id
     AND o.target_effect_id=NEW.effect_id
     AND o.target_effect_outcome_hash=NEW.outcome_tuple_hash
  )
  AND (
   (
    NEW.outcome_kind='SUCCESS'
    AND EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.outcome_operation_id AND o.operation_kind='CLOSE_SUCCESS')
    AND EXISTS(SELECT 1 FROM registration_operation_audit o JOIN registration_runtime_status s ON s.member_id=NEW.member_id WHERE o.operation_id=NEW.outcome_operation_id AND s.current_effect_id=NEW.effect_id AND s.status_hash=o.expected_target_status_hash AND s.executor_token_hash=o.target_executor_token_hash AND s.executor_token_hash IS NOT NULL)
    AND EXISTS(SELECT 1 FROM registration_member m WHERE m.member_id=NEW.member_id AND m.phase='EFFECT_IN_FLIGHT' AND m.current_effect_id=NEW.effect_id AND m.helper_generation=NEW.outcome_helper_generation)
    AND (SELECT COUNT(*) FROM registration_effect_action a WHERE a.effect_id=NEW.effect_id)=4
    AND NOT EXISTS(SELECT 1 FROM registration_effect_action a WHERE a.effect_id=NEW.effect_id AND a.observation_kind NOT IN('OBSERVED_EXACT','APPLIED_VERIFIED'))
    AND NEW.ledger_head_hash=(SELECT ledger_hash FROM registration_effect_action a WHERE a.effect_id=NEW.effect_id ORDER BY event_seq DESC LIMIT 1)
   )
   OR
   (
    NEW.outcome_kind='LOGICAL_CONFLICT'
    AND EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.outcome_operation_id AND o.operation_kind='CLOSE_CONFLICT')
    AND EXISTS(SELECT 1 FROM registration_operation_audit o JOIN registration_runtime_status s ON s.member_id=NEW.member_id WHERE o.operation_id=NEW.outcome_operation_id AND s.current_effect_id=NEW.effect_id AND s.status_hash=o.expected_target_status_hash AND s.executor_token_hash=o.target_executor_token_hash AND s.executor_token_hash IS NOT NULL)
    AND EXISTS(SELECT 1 FROM registration_member m WHERE m.member_id=NEW.member_id AND m.phase='EFFECT_IN_FLIGHT' AND m.current_effect_id=NEW.effect_id AND m.helper_generation=NEW.outcome_helper_generation)
    AND NEW.first_conflict_event_seq=(SELECT MIN(event_seq) FROM registration_effect_action a WHERE a.effect_id=NEW.effect_id AND a.observation_kind='LOGICAL_CONFLICT')
    AND NEW.first_conflict_event_seq=(SELECT MAX(event_seq) FROM registration_effect_action a WHERE a.effect_id=NEW.effect_id)
    AND NEW.ledger_head_hash=(SELECT ledger_hash FROM registration_effect_action a WHERE a.effect_id=NEW.effect_id ORDER BY event_seq DESC LIMIT 1)
   )
   OR
   (
    NEW.outcome_kind='SUPERSEDED'
    AND EXISTS(
     SELECT 1 FROM registration_operation_audit o
     JOIN registration_member m ON m.member_id=NEW.member_id
     JOIN registration_runtime_status s ON s.member_id=NEW.member_id
     JOIN registration_effect successor ON successor.effect_id=NEW.superseded_by_effect_id
     WHERE o.operation_id=NEW.outcome_operation_id
       AND o.operation_kind IN('INVALIDATE_REQUESTED','REPLACE_PENDING','ADOPT_EFFECT')
       AND o.target_successor_effect_id=NEW.superseded_by_effect_id
       AND o.target_transition_id=NEW.successor_transition_id
       AND o.expected_target_member_tuple_hash=m.member_tuple_hash
       AND o.expected_target_effect_tuple_hash=OLD.request_tuple_hash
       AND o.expected_target_status_hash=s.status_hash
       AND o.target_effect_tuple_hash=successor.request_tuple_hash
       AND o.target_member_tuple_hash IS NOT NULL
       AND o.target_status_hash IS NOT NULL
       AND o.target_cause_code IS NOT NULL
       AND successor.member_id=NEW.member_id
       AND successor.member_epoch=o.target_successor_member_epoch
       AND successor.request_basis_hash=o.target_successor_basis_hash
       AND successor.outcome_kind IS NULL
       AND (
        (o.operation_kind='INVALIDATE_REQUESTED' AND m.phase='REQUESTED' AND m.current_effect_id=NEW.effect_id AND m.pending_effect_id IS NULL)
        OR
        (o.operation_kind='REPLACE_PENDING' AND m.phase='EFFECT_IN_FLIGHT' AND m.pending_effect_id=NEW.effect_id AND o.target_status_hash=o.expected_target_status_hash)
        OR
        (o.operation_kind='ADOPT_EFFECT' AND m.phase='EFFECT_IN_FLIGHT' AND m.pending_effect_id=NEW.effect_id AND o.lineage_effect_id=m.current_effect_id)
       )
    )
   )
  )
 ) IS NOT TRUE;
END;
CREATE TRIGGER trg_effect_action_append
BEFORE INSERT ON registration_effect_action
BEGIN
 SELECT RAISE(ABORT,'effect_action_append_guard')
 WHERE (
  EXISTS(
   SELECT 1 FROM registration_operation_audit o
   JOIN registration_effect e ON e.effect_id=NEW.effect_id
   JOIN registration_member m ON m.member_id=e.member_id
   WHERE o.operation_seq=(SELECT MAX(operation_seq) FROM registration_operation_audit)
     AND o.operation_seq=NEW.write_operation_seq
     AND o.operation_id=NEW.write_operation_id
     AND o.operation_envelope_hash=NEW.write_operation_hash
     AND o.operation_class='DATA'
     AND o.operation_kind='APPEND_ACTION'
     AND o.target_member_id=e.member_id
     AND o.target_effect_id=NEW.effect_id
     AND o.target_action_ledger_hash=NEW.ledger_hash
     AND o.external_growth_bytes=NEW.external_growth_bytes
     AND e.outcome_kind IS NULL
     AND m.phase='EFFECT_IN_FLIGHT'
     AND m.current_effect_id=NEW.effect_id
     AND EXISTS(SELECT 1 FROM registration_runtime_status s WHERE s.member_id=m.member_id AND s.current_effect_id=NEW.effect_id AND s.status_hash=o.expected_target_status_hash AND s.executor_token_hash=o.target_executor_token_hash AND s.executor_token_hash IS NOT NULL)
     AND NEW.event_seq=COALESCE((SELECT MAX(event_seq)+1 FROM registration_effect_action WHERE effect_id=NEW.effect_id),1)
     AND NEW.ordinal=NEW.event_seq
     AND NEW.action_kind=CASE NEW.ordinal WHEN 1 THEN e.action_1_kind WHEN 2 THEN e.action_2_kind WHEN 3 THEN e.action_3_kind WHEN 4 THEN e.action_4_kind END
     AND NEW.action_hash=CASE NEW.ordinal WHEN 1 THEN e.action_1_hash WHEN 2 THEN e.action_2_hash WHEN 3 THEN e.action_3_hash WHEN 4 THEN e.action_4_hash END
     AND NEW.postcondition_hash=CASE NEW.ordinal WHEN 1 THEN e.postcondition_1_hash WHEN 2 THEN e.postcondition_2_hash WHEN 3 THEN e.postcondition_3_hash WHEN 4 THEN e.postcondition_4_hash END
     AND NEW.prior_ledger_hash=CASE WHEN NEW.event_seq=1 THEN '0000000000000000000000000000000000000000000000000000000000000000' ELSE (SELECT ledger_hash FROM registration_effect_action WHERE effect_id=NEW.effect_id ORDER BY event_seq DESC LIMIT 1) END
     AND NOT EXISTS(SELECT 1 FROM registration_effect_action WHERE effect_id=NEW.effect_id AND observation_kind='LOGICAL_CONFLICT')
     AND (SELECT COALESCE(SUM(external_growth_bytes),0) FROM registration_effect_action WHERE effect_id=NEW.effect_id)+NEW.external_growth_bytes<=e.external_growth_reservation_bytes
     AND (NEW.ordinal=1 OR EXISTS(SELECT 1 FROM registration_effect_action a WHERE a.effect_id=NEW.effect_id AND a.ordinal=NEW.ordinal-1 AND a.observation_kind IN('OBSERVED_EXACT','APPLIED_VERIFIED')))
  )
 ) IS NOT TRUE;
END;
CREATE TRIGGER trg_runtime_status_insert
BEFORE INSERT ON registration_runtime_status
BEGIN
 SELECT RAISE(ABORT,'runtime_status_insert_guard')
 WHERE (
  NOT EXISTS(SELECT 1 FROM registration_runtime_status s WHERE s.member_id=NEW.member_id)
  AND EXISTS(
   SELECT 1 FROM registration_operation_audit o
   JOIN registration_member m ON m.member_id=NEW.member_id
   WHERE o.operation_seq=(SELECT MAX(operation_seq) FROM registration_operation_audit)
     AND o.operation_seq=NEW.write_operation_seq
     AND o.operation_id=NEW.write_operation_id
     AND o.operation_envelope_hash=NEW.write_operation_hash
     AND o.target_member_id=NEW.member_id
     AND o.target_subject_key=NEW.subject_key
     AND o.target_status_hash=NEW.status_hash
     AND NEW.member_epoch=m.member_epoch
     AND NEW.current_effect_id=m.current_effect_id
     AND o.operation_kind='INSTALL_MEMBER'
     AND o.target_successor_effect_id=NEW.current_effect_id
     AND m.runtime_subject_key=NEW.subject_key
     AND NEW.status_version=1
  )
  AND EXISTS(SELECT 1 FROM registration_effect e WHERE e.effect_id=NEW.current_effect_id AND e.member_id=NEW.member_id AND e.outcome_kind IS NULL)
  AND NEW.executor_token_hash IS NULL
  AND NEW.executor_boot_id IS NULL
  AND NEW.help_due=0
  AND NEW.unavailable_count=0
  AND NEW.yield_count=0
  AND (
   (EXISTS(SELECT 1 FROM registration_effect e WHERE e.effect_id=NEW.current_effect_id AND e.request_kind='CLEAN_ELIGIBLE') AND NEW.schedule_boot_id=(SELECT sample_boot_id FROM registration_operation_audit WHERE operation_id=NEW.write_operation_id) AND NEW.observed_now_mono_ns=(SELECT sample_mono_ns FROM registration_operation_audit WHERE operation_id=NEW.write_operation_id) AND NEW.next_due_mono_ns=NEW.observed_now_mono_ns AND NEW.reason_code='REGISTRATION_REQUIRED' AND NEW.blocked_basis_fingerprint IS NULL)
   OR
   (EXISTS(SELECT 1 FROM registration_effect e WHERE e.effect_id=NEW.current_effect_id AND e.request_kind='BLOCKED_DIRTY') AND NEW.schedule_boot_id IS NULL AND NEW.reason_code='DIRTY_UNSUPPORTED' AND NEW.blocked_basis_fingerprint IS NOT NULL)
   OR
   (EXISTS(SELECT 1 FROM registration_effect e WHERE e.effect_id=NEW.current_effect_id AND e.request_kind='BLOCKED_OPERATION') AND NEW.schedule_boot_id IS NULL AND NEW.reason_code='GIT_OPERATION_UNSUPPORTED' AND NEW.blocked_basis_fingerprint IS NOT NULL)
  )
 ) IS NOT TRUE;
END;
CREATE TRIGGER trg_runtime_status_update
BEFORE UPDATE ON registration_runtime_status
BEGIN
 SELECT RAISE(ABORT,'runtime_status_update_guard')
 WHERE (
  (NEW.subject_key,NEW.member_id)
  IS (OLD.subject_key,OLD.member_id)
  AND NEW.status_version=OLD.status_version+1
  AND NEW.member_epoch=COALESCE((SELECT e.member_epoch FROM registration_operation_audit o JOIN registration_effect e ON e.effect_id=o.target_successor_effect_id WHERE o.operation_id=NEW.write_operation_id AND o.operation_kind IN('INVALIDATE_REQUESTED','HANDOFF_RESOLVED')),(SELECT member_epoch FROM registration_member WHERE member_id=NEW.member_id))
  AND EXISTS(
   SELECT 1 FROM registration_operation_audit o
   WHERE o.operation_seq=(SELECT MAX(operation_seq) FROM registration_operation_audit)
     AND o.operation_seq=NEW.write_operation_seq
     AND o.operation_id=NEW.write_operation_id
     AND o.operation_envelope_hash=NEW.write_operation_hash
     AND o.target_member_id=NEW.member_id
     AND o.target_subject_key=NEW.subject_key
     AND o.expected_target_status_hash=OLD.status_hash
     AND o.target_status_hash=NEW.status_hash
  )
  AND (
   (
    EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.write_operation_id AND o.operation_kind='REACQUIRE_EFFECT')
    AND (NEW.member_epoch,NEW.current_effect_id,NEW.unavailable_count,NEW.yield_count)
       IS (OLD.member_epoch,OLD.current_effect_id,OLD.unavailable_count,OLD.yield_count)
   )
   OR
   (
    EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.write_operation_id AND o.operation_kind='OPEN_EFFECT')
    AND (NEW.member_epoch,NEW.current_effect_id,NEW.unavailable_count,NEW.yield_count,NEW.blocked_basis_fingerprint)
       IS (OLD.member_epoch,OLD.current_effect_id,OLD.unavailable_count,OLD.yield_count,OLD.blocked_basis_fingerprint)
   )
   OR
   (
    EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.write_operation_id AND o.operation_kind IN('CLOSE_SUCCESS','CLOSE_CONFLICT'))
    AND (NEW.member_epoch,NEW.current_effect_id)
       IS (OLD.member_epoch,OLD.current_effect_id)
   )
   OR
   EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.write_operation_id AND o.operation_kind IN('INVALIDATE_REQUESTED','HANDOFF_RESOLVED'))
   OR
   (
    EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.write_operation_id AND o.operation_kind='ADOPT_EFFECT')
    AND (NEW.member_epoch,NEW.current_effect_id,NEW.unavailable_count,NEW.yield_count,NEW.blocked_basis_fingerprint)
       IS (OLD.member_epoch,OLD.current_effect_id,OLD.unavailable_count,OLD.yield_count,OLD.blocked_basis_fingerprint)
   )
   OR
   (
    EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.write_operation_id AND o.operation_kind='MARK_UNAVAILABLE')
    AND (NEW.member_epoch,NEW.current_effect_id,NEW.blocked_basis_fingerprint)
       IS (OLD.member_epoch,OLD.current_effect_id,OLD.blocked_basis_fingerprint)
   )
   OR
   (
    EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.write_operation_id AND o.operation_kind='REBOOT_STATUS')
    AND (NEW.member_epoch,NEW.current_effect_id,NEW.unavailable_count,NEW.yield_count,NEW.blocked_basis_fingerprint)
       IS (OLD.member_epoch,OLD.current_effect_id,OLD.unavailable_count,OLD.yield_count,OLD.blocked_basis_fingerprint)
   )
   OR
   (
    EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.write_operation_id AND o.operation_kind='SCHEDULE_STATUS')
    AND (NEW.member_epoch,NEW.current_effect_id,NEW.due_since_mono_ns,NEW.help_due,NEW.executor_token_hash,NEW.executor_boot_id,NEW.executor_generation,NEW.unavailable_count,NEW.yield_count,NEW.blocked_basis_fingerprint,NEW.reason_code)
       IS (OLD.member_epoch,OLD.current_effect_id,OLD.due_since_mono_ns,OLD.help_due,OLD.executor_token_hash,OLD.executor_boot_id,OLD.executor_generation,OLD.unavailable_count,OLD.yield_count,OLD.blocked_basis_fingerprint,OLD.reason_code)
   )
  )
  AND NEW.current_effect_id=COALESCE((SELECT target_successor_effect_id FROM registration_operation_audit o WHERE o.operation_id=NEW.write_operation_id AND o.operation_kind IN('INVALIDATE_REQUESTED','HANDOFF_RESOLVED')),(SELECT current_effect_id FROM registration_member WHERE member_id=NEW.member_id))
  AND (
     (
      EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.write_operation_id AND o.operation_kind='REACQUIRE_EFFECT' AND o.target_effect_id=NEW.current_effect_id AND o.expected_target_member_tuple_hash=(SELECT member_tuple_hash FROM registration_member WHERE member_id=NEW.member_id) AND o.expected_target_effect_tuple_hash=(SELECT request_tuple_hash FROM registration_effect WHERE effect_id=NEW.current_effect_id) AND o.expected_target_status_hash=OLD.status_hash AND o.target_action_ledger_hash=COALESCE((SELECT ledger_hash FROM registration_effect_action WHERE effect_id=NEW.current_effect_id ORDER BY event_seq DESC LIMIT 1),'0000000000000000000000000000000000000000000000000000000000000000') AND o.target_executor_token_hash=NEW.executor_token_hash)
      AND EXISTS(
       SELECT 1 FROM registration_member m
       JOIN registration_effect e ON e.effect_id=m.current_effect_id
       JOIN registration_protocol_epoch p ON p.protocol_seq=(SELECT MAX(protocol_seq) FROM registration_protocol_epoch)
       WHERE m.member_id=NEW.member_id
         AND m.phase='EFFECT_IN_FLIGHT'
         AND e.effect_id=NEW.current_effect_id
         AND e.request_kind='CLEAN_ELIGIBLE'
         AND e.outcome_kind IS NULL
         AND p.mode='WRITABLE'
         AND p.protocol_generation=m.helper_generation
         AND (
          (e.required_protocol_generation=m.helper_generation AND e.required_runtime_capability_hash=p.runtime_capability_hash)
          OR
          (
           e.required_protocol_generation<>m.helper_generation
           AND EXISTS(
            SELECT 1 FROM registration_operation_audit adopt
            JOIN registration_protocol_epoch staged ON staged.protocol_seq=adopt.protocol_seq
            WHERE adopt.operation_kind='ADOPT_EFFECT'
              AND adopt.target_member_id=m.member_id
              AND adopt.lineage_effect_id=e.effect_id
              AND adopt.expected_generation=e.required_protocol_generation
              AND adopt.target_action_plan_hash=e.action_plan_hash
              AND adopt.target_staged_epoch_hash=staged.staged_epoch_hash
              AND staged.protocol_generation=e.required_protocol_generation
              AND staged.runtime_capability_hash=e.required_runtime_capability_hash
              AND staged.staged_generation=m.helper_generation
              AND staged.staged_runtime_capability_hash=p.runtime_capability_hash
           )
          )
         )
      )
      AND OLD.executor_token_hash IS NULL
      AND OLD.schedule_boot_id=(SELECT sample_boot_id FROM registration_operation_audit WHERE operation_id=NEW.write_operation_id)
      AND OLD.next_due_mono_ns<=(SELECT sample_mono_ns FROM registration_operation_audit WHERE operation_id=NEW.write_operation_id)
      AND OLD.help_due=1
      AND NEW.executor_token_hash IS NOT NULL
      AND NEW.executor_boot_id=(SELECT sample_boot_id FROM registration_operation_audit WHERE operation_id=NEW.write_operation_id)
      AND NEW.executor_generation=(SELECT protocol_generation FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.schedule_boot_id IS NULL AND NEW.observed_now_mono_ns IS NULL AND NEW.next_due_mono_ns IS NULL AND NEW.due_since_mono_ns IS NULL AND NEW.attempt_count IS NULL AND NEW.backoff_ns IS NULL
      AND NEW.help_due=0 AND NEW.reason_code='EFFECT_IN_FLIGHT'
      AND NEW.unavailable_count=OLD.unavailable_count AND NEW.yield_count=OLD.yield_count
      AND NEW.blocked_basis_fingerprint IS NULL
     )
     OR
     (
      EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.write_operation_id AND o.operation_kind='OPEN_EFFECT' AND o.sample_boot_id=OLD.schedule_boot_id AND OLD.next_due_mono_ns<=o.sample_mono_ns AND o.expected_target_member_tuple_hash=(SELECT member_tuple_hash FROM registration_member WHERE member_id=NEW.member_id) AND o.expected_target_effect_tuple_hash=(SELECT request_tuple_hash FROM registration_effect WHERE effect_id=NEW.current_effect_id) AND o.expected_target_status_hash=OLD.status_hash AND o.target_executor_token_hash=NEW.executor_token_hash)
      AND OLD.executor_token_hash IS NULL
      AND NEW.executor_token_hash IS NOT NULL
      AND NEW.executor_boot_id=(SELECT sample_boot_id FROM registration_operation_audit WHERE operation_id=NEW.write_operation_id)
      AND NEW.executor_generation=(SELECT protocol_generation FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
      AND NEW.schedule_boot_id IS NULL AND NEW.observed_now_mono_ns IS NULL AND NEW.next_due_mono_ns IS NULL AND NEW.due_since_mono_ns IS NULL AND NEW.attempt_count IS NULL AND NEW.backoff_ns IS NULL
      AND NEW.help_due=0 AND NEW.reason_code='EFFECT_IN_FLIGHT'
      AND NEW.unavailable_count=OLD.unavailable_count AND NEW.yield_count=OLD.yield_count
      AND NEW.blocked_basis_fingerprint IS NULL
     )
     OR
     (
      EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.write_operation_id AND o.operation_kind IN('CLOSE_SUCCESS','CLOSE_CONFLICT') AND o.expected_target_status_hash=OLD.status_hash AND o.target_executor_token_hash=OLD.executor_token_hash)
      AND OLD.executor_token_hash IS NOT NULL AND NEW.executor_token_hash IS NULL AND NEW.executor_boot_id IS NULL
      AND (
       (EXISTS(SELECT 1 FROM registration_member m WHERE m.member_id=NEW.member_id AND m.pending_effect_id IS NULL) AND NEW.schedule_boot_id IS NULL AND NEW.help_due=0 AND NEW.blocked_basis_fingerprint IS NULL AND ((EXISTS(SELECT 1 FROM registration_effect e WHERE e.effect_id=NEW.current_effect_id AND e.outcome_kind='SUCCESS') AND NEW.reason_code IS NULL AND NEW.unavailable_count=0 AND NEW.yield_count=0) OR (EXISTS(SELECT 1 FROM registration_effect e WHERE e.effect_id=NEW.current_effect_id AND e.outcome_kind='LOGICAL_CONFLICT') AND NEW.reason_code='EFFECT_CONFLICT' AND NEW.unavailable_count=OLD.unavailable_count AND NEW.yield_count=OLD.yield_count)))
       OR
       (EXISTS(SELECT 1 FROM registration_member m WHERE m.member_id=NEW.member_id AND m.pending_effect_id IS NOT NULL) AND NEW.schedule_boot_id=(SELECT sample_boot_id FROM registration_operation_audit WHERE operation_id=NEW.write_operation_id) AND NEW.observed_now_mono_ns=(SELECT sample_mono_ns FROM registration_operation_audit WHERE operation_id=NEW.write_operation_id) AND NEW.next_due_mono_ns=NEW.observed_now_mono_ns AND NEW.help_due=1 AND NEW.reason_code='REGISTRATION_REQUIRED' AND NEW.unavailable_count=OLD.unavailable_count AND NEW.yield_count=OLD.yield_count)
      )
     )
     OR
     (
      EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.write_operation_id AND o.operation_kind IN('INVALIDATE_REQUESTED','HANDOFF_RESOLVED'))
      AND NEW.executor_token_hash IS NULL AND NEW.executor_boot_id IS NULL AND NEW.help_due=0
      AND EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.write_operation_id AND o.expected_target_status_hash=OLD.status_hash AND o.target_status_hash=NEW.status_hash AND o.expected_target_member_tuple_hash=(SELECT member_tuple_hash FROM registration_member WHERE member_id=NEW.member_id) AND o.target_successor_effect_id=NEW.current_effect_id AND o.target_effect_tuple_hash=(SELECT request_tuple_hash FROM registration_effect WHERE effect_id=NEW.current_effect_id))
      AND (
       (EXISTS(SELECT 1 FROM registration_effect e WHERE e.effect_id=NEW.current_effect_id AND e.request_kind='CLEAN_ELIGIBLE') AND NEW.schedule_boot_id=(SELECT sample_boot_id FROM registration_operation_audit WHERE operation_id=NEW.write_operation_id) AND NEW.observed_now_mono_ns=(SELECT sample_mono_ns FROM registration_operation_audit WHERE operation_id=NEW.write_operation_id) AND NEW.next_due_mono_ns=NEW.observed_now_mono_ns AND NEW.reason_code='REGISTRATION_REQUIRED' AND NEW.blocked_basis_fingerprint IS NULL)
       OR
       (EXISTS(SELECT 1 FROM registration_effect e WHERE e.effect_id=NEW.current_effect_id AND e.request_kind='BLOCKED_DIRTY') AND NEW.schedule_boot_id IS NULL AND NEW.reason_code='DIRTY_UNSUPPORTED' AND NEW.blocked_basis_fingerprint IS NOT NULL)
       OR
       (EXISTS(SELECT 1 FROM registration_effect e WHERE e.effect_id=NEW.current_effect_id AND e.request_kind='BLOCKED_OPERATION') AND NEW.schedule_boot_id IS NULL AND NEW.reason_code='GIT_OPERATION_UNSUPPORTED' AND NEW.blocked_basis_fingerprint IS NOT NULL)
      )
     )
     OR
     (
      EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.write_operation_id AND o.operation_kind='ADOPT_EFFECT' AND o.lineage_effect_id=NEW.current_effect_id AND o.target_staged_epoch_hash=(SELECT staged_epoch_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) AND o.expected_target_status_hash=OLD.status_hash AND o.target_executor_token_hash=NEW.executor_token_hash)
      AND EXISTS(SELECT 1 FROM registration_member m WHERE m.member_id=NEW.member_id AND m.helper_generation=(SELECT protocol_generation FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) AND m.helper_generation<>(SELECT staged_generation FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1))
      AND (OLD.executor_token_hash IS NULL OR OLD.executor_generation=(SELECT protocol_generation FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1))
      AND NEW.executor_token_hash=(SELECT target_executor_token_hash FROM registration_operation_audit WHERE operation_id=NEW.write_operation_id)
      AND NEW.executor_token_hash IS NOT NULL
      AND (OLD.executor_token_hash IS NULL OR NEW.executor_token_hash=OLD.executor_token_hash)
      AND NEW.executor_boot_id=CASE WHEN OLD.executor_token_hash IS NULL THEN (SELECT sample_boot_id FROM registration_operation_audit WHERE operation_id=NEW.write_operation_id) ELSE OLD.executor_boot_id END
      AND NEW.executor_generation=(SELECT staged_generation FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
     )
     OR
     (
      EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.write_operation_id AND o.operation_kind='MARK_UNAVAILABLE' AND o.sample_boot_id=NEW.schedule_boot_id AND o.sample_mono_ns=NEW.observed_now_mono_ns AND o.expected_target_status_hash=OLD.status_hash AND o.target_executor_token_hash=OLD.executor_token_hash AND o.sample_boot_id=OLD.executor_boot_id)
      AND OLD.executor_token_hash IS NOT NULL
      AND NEW.executor_token_hash IS NULL AND NEW.executor_boot_id IS NULL
      AND NEW.unavailable_count=CASE WHEN OLD.unavailable_count<3 THEN OLD.unavailable_count+1 ELSE 3 END
      AND NEW.yield_count=CASE WHEN OLD.yield_count<3 THEN OLD.yield_count+1 ELSE 3 END
      AND NEW.help_due=1 AND NEW.reason_code='RESOLVER_UNAVAILABLE' AND NEW.schedule_boot_id IS NOT NULL
     )
     OR
     (
      EXISTS(
       SELECT 1 FROM registration_operation_audit o
       WHERE o.operation_id=NEW.write_operation_id
         AND o.operation_kind='REBOOT_STATUS'
         AND o.expected_target_status_hash=OLD.status_hash
         AND o.sample_boot_id IS NOT NULL
         AND o.sample_mono_ns IS NOT NULL
         AND (
          (OLD.executor_token_hash IS NOT NULL AND OLD.executor_boot_id<>o.sample_boot_id)
          OR
          (OLD.executor_token_hash IS NULL AND OLD.schedule_boot_id IS NOT NULL AND OLD.schedule_boot_id<>o.sample_boot_id)
         )
      )
      AND NEW.executor_token_hash IS NULL AND NEW.executor_boot_id IS NULL
      AND (
       (EXISTS(SELECT 1 FROM registration_member m JOIN registration_effect e ON e.effect_id=m.current_effect_id WHERE m.member_id=NEW.member_id AND m.phase='REQUESTED' AND e.request_kind='CLEAN_ELIGIBLE') AND NEW.schedule_boot_id=(SELECT sample_boot_id FROM registration_operation_audit WHERE operation_id=NEW.write_operation_id) AND NEW.observed_now_mono_ns=(SELECT sample_mono_ns FROM registration_operation_audit WHERE operation_id=NEW.write_operation_id) AND NEW.due_since_mono_ns=NEW.observed_now_mono_ns AND NEW.next_due_mono_ns=NEW.observed_now_mono_ns AND NEW.attempt_count=0 AND NEW.backoff_ns=0 AND NEW.help_due=1 AND NEW.reason_code='REGISTRATION_REQUIRED' AND NEW.blocked_basis_fingerprint IS NULL)
       OR
       (EXISTS(SELECT 1 FROM registration_member m JOIN registration_effect e ON e.effect_id=m.current_effect_id WHERE m.member_id=NEW.member_id AND m.phase='REQUESTED' AND e.request_kind='BLOCKED_DIRTY') AND NEW.schedule_boot_id IS NULL AND NEW.observed_now_mono_ns IS NULL AND NEW.due_since_mono_ns IS NULL AND NEW.next_due_mono_ns IS NULL AND NEW.attempt_count IS NULL AND NEW.backoff_ns IS NULL AND NEW.help_due=0 AND NEW.reason_code='DIRTY_UNSUPPORTED' AND NEW.blocked_basis_fingerprint IS NOT NULL)
       OR
       (EXISTS(SELECT 1 FROM registration_member m JOIN registration_effect e ON e.effect_id=m.current_effect_id WHERE m.member_id=NEW.member_id AND m.phase='REQUESTED' AND e.request_kind='BLOCKED_OPERATION') AND NEW.schedule_boot_id IS NULL AND NEW.observed_now_mono_ns IS NULL AND NEW.due_since_mono_ns IS NULL AND NEW.next_due_mono_ns IS NULL AND NEW.attempt_count IS NULL AND NEW.backoff_ns IS NULL AND NEW.help_due=0 AND NEW.reason_code='GIT_OPERATION_UNSUPPORTED' AND NEW.blocked_basis_fingerprint IS NOT NULL)
       OR
       (EXISTS(SELECT 1 FROM registration_member m WHERE m.member_id=NEW.member_id AND m.phase='EFFECT_IN_FLIGHT') AND NEW.schedule_boot_id=(SELECT sample_boot_id FROM registration_operation_audit WHERE operation_id=NEW.write_operation_id) AND NEW.observed_now_mono_ns=(SELECT sample_mono_ns FROM registration_operation_audit WHERE operation_id=NEW.write_operation_id) AND NEW.due_since_mono_ns=NEW.observed_now_mono_ns AND NEW.next_due_mono_ns=NEW.observed_now_mono_ns AND NEW.attempt_count=0 AND NEW.backoff_ns=0 AND NEW.help_due=1 AND NEW.reason_code='EFFECT_IN_FLIGHT' AND NEW.blocked_basis_fingerprint IS NULL)
       OR
       (EXISTS(SELECT 1 FROM registration_member m WHERE m.member_id=NEW.member_id AND m.phase='RESOLVED' AND m.pending_effect_id IS NULL AND m.current_outcome_kind='SUCCESS') AND NEW.schedule_boot_id IS NULL AND NEW.observed_now_mono_ns IS NULL AND NEW.due_since_mono_ns IS NULL AND NEW.next_due_mono_ns IS NULL AND NEW.attempt_count IS NULL AND NEW.backoff_ns IS NULL AND NEW.help_due=0 AND NEW.reason_code IS NULL AND NEW.blocked_basis_fingerprint IS NULL)
       OR
       (EXISTS(SELECT 1 FROM registration_member m WHERE m.member_id=NEW.member_id AND m.phase='RESOLVED' AND m.pending_effect_id IS NULL AND m.current_outcome_kind='LOGICAL_CONFLICT') AND NEW.schedule_boot_id IS NULL AND NEW.observed_now_mono_ns IS NULL AND NEW.due_since_mono_ns IS NULL AND NEW.next_due_mono_ns IS NULL AND NEW.attempt_count IS NULL AND NEW.backoff_ns IS NULL AND NEW.help_due=0 AND NEW.reason_code='EFFECT_CONFLICT' AND NEW.blocked_basis_fingerprint IS NULL)
       OR
       (EXISTS(SELECT 1 FROM registration_member m WHERE m.member_id=NEW.member_id AND m.phase='RESOLVED' AND m.pending_effect_id IS NOT NULL) AND NEW.schedule_boot_id=(SELECT sample_boot_id FROM registration_operation_audit WHERE operation_id=NEW.write_operation_id) AND NEW.observed_now_mono_ns=(SELECT sample_mono_ns FROM registration_operation_audit WHERE operation_id=NEW.write_operation_id) AND NEW.due_since_mono_ns=NEW.observed_now_mono_ns AND NEW.next_due_mono_ns=NEW.observed_now_mono_ns AND NEW.attempt_count=0 AND NEW.backoff_ns=0 AND NEW.help_due=1 AND NEW.reason_code='REGISTRATION_REQUIRED' AND NEW.blocked_basis_fingerprint IS NULL)
      )
     )
     OR
     (
      EXISTS(SELECT 1 FROM registration_operation_audit o WHERE o.operation_id=NEW.write_operation_id AND o.operation_kind='SCHEDULE_STATUS' AND o.sample_boot_id=NEW.schedule_boot_id)
      AND NEW.executor_token_hash IS OLD.executor_token_hash
      AND NEW.executor_boot_id IS OLD.executor_boot_id
      AND NEW.observed_now_mono_ns=(SELECT sample_mono_ns FROM registration_operation_audit WHERE operation_id=NEW.write_operation_id)
      AND NEW.next_due_mono_ns=NEW.observed_now_mono_ns+NEW.backoff_ns
     )
  )
 ) IS NOT TRUE;
END;
