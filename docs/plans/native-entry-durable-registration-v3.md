# Native Entry Durable Registration

- **Version:** v3
- **Status:** ACCEPTED — C0-DESIGN NO-GO
- **Date:** 2026-09-26
- **Supersedes:** draft
  [`native-entry-durable-registration-v2.md`](native-entry-durable-registration-v2.md),
  preserved byte-identically at SHA-256
  `03aff346283c2809d9bab392120972de97bd14b5879e01448a8af734becf8b9b`
- **Relates to:** accepted frozen
  [`native-entry-first-prompt-recovery-v1.md`](native-entry-first-prompt-recovery-v1.md);
  v1 remains implementation authority unless ADR 0025 and this plan are
  separately accepted
- **Architecture authority:** draft
  [ADR 0025](../adr/0025-durable-registration-episodes-and-tool-admission.md);
  accepted [ADR 0024](../adr/0024-first-prompt-native-entry-recovery.md)
  remains authoritative
- **Documentation baseline:** local PR #175 substrate
  `b88325768f26f8d98aecb2722d5fb253379bba47`; no PR mutation is authorized
- **Closed-world budget:** exactly seven tables, nine triggers, ninety-seven
  generated transition leaves, three durable member phases, four protocol
  modes, three effect outcomes, three transaction classes, twenty-four
  operation kinds, twenty-six runtime reason codes, zero durable notice
  forms/variants, one predeployment evidence stage, two rollout authorization
  stages, and three implementation bodies. These are mechanically checked
  ceilings; there is no reserved object or hidden branch.
- **Plan type:** Bodies A–C implement. C1 only executes, captures, and
  adjudicates harnesses owned by A, B, or C.

**Goal:** for one complete, positively identified, clean local linked
non-primary worktree, functioning AWA durably registers the physical member
and conversation before allowing any supported intercepted ordinary Agent
tool. Every unknown or non-green result denies that invocation when the
receiving hook is functioning. Task/subagent launch is default-denied in M1.

> **Governance stop:** this draft authorizes documentation only.
> `C0-DESIGN` is **UNSATISFIED**. Do not implement, mutate PR #175, touch
> remote/live state, install, release, wire a host job, or alter any accepted
> or frozen artifact.

---

## 1. Boundary and inherited authority

ADR 0024 and PR #175 provide payload identity, eager `sessionStart`,
first-prompt recovery, native-entry v2 evidence, and hook-owner v3. They do
not prove durable registration before each later intercepted tool. This
successor preserves:

- normalized `conversation_id`, real event `generation_id`, and strict
  private/redacted evidence boundaries;
- exactly one complete `workspace_roots` entry;
- clean, idle initial registration and conservative exact repair;
- the protected-primary guard, engine-off behavior, finish authorization,
  active-root protection, and cleanup kernel as independent authorities; and
- AWA product ownership with `~/dev` as the only live hook/local-jobs owner.

M1 does not preserve, stash, reset, abort, relocate, or delete dirty work. It
does not support multi-root episodes, Task/subagent entry, physical garbage
collection/migration/rotation, Rescue, production custom VFS work, or broader
platforms. It
reserves no dormant object, phase, trigger, action, or test branch for them.

Legacy `awa-native-entry/v1|v2` and hook-owner v1–v3 remain readable
compatibility evidence. They never select successor success. Registration
state never grants guard, finish, active-root, or cleanup authority.

## 2. Protected baseline and evidence discipline

| Surface | SHA-256 / state |
|---|---|
| Current documentation baseline | `b88325768f26f8d98aecb2722d5fb253379bba47` |
| ADR 0020 | `f0911b0a85e85b6dc1d616fa6f092d33f9002e9c8d9bc5bf2edda4a927a95a98` |
| ADR 0023 | `71476602db37828c80503f05790a57aa587572cef1e800cfa42b2d32e86a0051` |
| ADR 0024 | `cecca6d380d446b91af00a4e5aea44282c4b9633b518a638967fcbeb4de38911` |
| Frozen v1 plan | `e3bf9182e4e16411ab1424123a7200b3f6ec0dd4e09429237256a5601dcb6bd9` |
| Superseded draft v2 | `03aff346283c2809d9bab392120972de97bd14b5879e01448a8af734becf8b9b` |

Accepted/frozen files are no-touch authorities. Evidence remains separated
as accepted authority, official/source facts, point-in-time observations,
design inference, and future exact-head C1 evidence. Stop and supersede this
draft before implementation if any claimed interception seam, single-root
identity, same-device fact, profile receipt, object, phase, trigger, body, or
branch differs from this closed manifest.

Read-only source reconnaissance at the bound baseline also established:

- `engine/native_entry.py` and its focused tests implement ADR 0024's
  fail-open eager/first-prompt v2 evidence, not this dedicated durable store
  or later-tool admission;
- `contracts/awa-hook-owner.v3.json`,
  `kernel/hooks/install-hooks.sh`, and their matrix tests project the current
  seven direct rows but declare no Task/subagent launch interception;
- `engine/paths.py` uses a best-effort `df`/`mount` local-disk heuristic, not
  the descriptor-bound APFS profile required here; and
- no source or test at this baseline implements the schema, protocol,
  executor reacquisition, free-space admission, admission fence, model,
  fault-injection, or Desktop UAT in this plan.

Those are source facts, not C0 failures. They establish that this remains a
preimplementation design and identify what C1 must later prove.

## 3. Gates and review provenance

### 3.1 C0-DESIGN

`C0-DESIGN` technical clearance requires, in order:

1. final whole-file hashes for ADR 0025, this plan, and both index files plus
   the §3.3 normalized acceptance-body digest;
2. extraction, execution, hash, inventory, nullable-predicate, enum-count,
   link, preserved-artifact, and §3.3 read-only acceptance-vector checks
   (current pre-hashes, normalized digest, exact allowed post-hashes, negative
   corpus) against the bound baseline;
3. a source-to-design trace for every claimed ingress, profile measurement,
   and inherited authority;
4. disposition of every finding as resolved, false positive, or an explicit
   unsupported-platform residual;
5. a fresh reliability review against those exact hashes;
6. a schema-valid protected verifier return against the same hashes with
   every expected candidate independently resolved,
   `critical_coverage_complete=true`,
   `critical_probe_blind_review_complete=true`, `revision_matches=true`, and
   `blockers=[]`.

`shipping_clearance=failed` may be disregarded for C0 only when its sole cause
is `partial_rollout=true` and the complete missing-evidence set is drawn from
these C1-only ids:
`implementation_absent`,
`supported_profile_state_transition_unproven`,
`process_fault_evidence_absent`,
`concurrency_evidence_absent`, and `desktop_uat_absent`.
Any other failed field, blocker, unresolved/unexpected candidate, missing
blind probe, revision mismatch, or additional shipping-failure cause blocks
C0.

C0 consumes design and documentation evidence only. Missing implementation,
model, process-fault, concurrency, and Desktop UAT results do not block C0;
they keep C1 unsatisfied. Technical clearance does not itself accept or
promote bytes; §3.3 owns that later owner-authorized step.

The latest complete reviewer run examined the pre-consolidation pair:

```text
ADR  787b8902b0204cc805a33e230cc8354a586c7a702307a61975957705262530ae
plan 6e3336f8596d2186858682d3b9561f7ea97a27079516fe8e956f585b795f3017
base b88325768f26f8d98aecb2722d5fb253379bba47
```

Revision matching succeeded. The fresh reliability review plus critical
probe were valid; the concurrency, data/schema, security, and architecture
reviews were valid.

A later verifier record targeted the pre-wave compact candidate:

```text
ADR    e8fb08caa1aad8e1f71adb33550b8933c3322c5144904948d94d17b70ef78a98
plan   ffba2909a3ca7a0f753bb66fa6009467e8f6500b9b1b56fe3c8d94e4c79de84f
schema adae0baa7afe7f8343c58b968832d7551a0125b6cd211695c6bf13d4cbab18da
```

The repository swarm validator was invoked with the frozen six candidate ids
and `authorized_accepted_risk_ids=[]`. It exited `2`:

```text
swarm: reviewer_return: missing keys ['no_finding_evidence', 'residual_uncertainty']
```

The return is therefore invalid and supplies no C0 or shipping clearance. Its
six candidate ids remain mandatory review inputs in §7.2. Its
`shipping_clearance=failed` and `partial_rollout=true` are expected for a
draft with incomplete M1 implementation/evidence; neither is itself a C0
blocker only under the exact §3.1 matrix. `partial_rollout` means
implementation-and-evidence completeness for verifier clearance, never
deployment reach. This rewrite
authors design dispositions but cannot self-clear them.

Two later exact-hash reviewer returns validly examined ADR
`f7ec08980cfd6bf4ef30cdda9abb899b62d20e41b6131b2a07bb90af8caf0954`,
plan
`5c5f387fe5060df756310f376c39ca31b2de2c26c7609fc9821fb8e4f1d085b6`,
and schema
`09c74656d9607b2ecdbc40a619bd4e89e67f5b2be6ed4b19763a524def3f43ee`.
They source-confirmed the ten roots closed by this subtraction wave. Those
returns review the predecessor bytes, not this rewritten exact subject, and
provide no C0 clearance.

Two corrected schema-valid returns then examined exact hashes ADR
`1f6e292a718ae1c4443634a1c688d963b341fc345088bc502137512edff5da39`,
plan
`0d5b5312dfd52e44ca433ad6bb2075f5ac5ed84cf7f370520dd4f37fee96d283`,
schema
`c2839c02dc3217e6034abae4d638e6eb39e2ca47f9db44c8cacbd3a4ef87d965`,
normalized body
`e673927ca31a310c911dc268d837ca7ba91c28e0bcf6e2d1000e0e87a9b2902b`,
ADR index
`f058a4db25ddb2b070856d8e3f7851f175a7b0969ba38053eca22589ce1662a2`,
and plan index
`d670f1521f4b16c954282dcc96111d850e83b5ee51e048be52b9c31bf235ed19`.
They source-confirmed this wave's eleven roots but do not review the rewritten
bytes or clear C0.

The deterministic five-reviewer final critical cohort then schema-validly
examined ADR
`040921c9722a2d62fd3fbaf426ae487c8eeda33277e6964960f07a4a3848d514`,
plan
`6cebc7d4d97a880f6ebfe1e9ad0f92e92da803be5406035744183719e548084f`,
schema
`6a15f47ee920f7605a707d0c20bfa220e650f55dd3683f646e7ab1468d7538d6`,
normalized body
`7b6743ce201cb4010e179709ac475b4456bec54f654f92455caee2eb5d8c1bb3`,
ADR index
`518ec4995ff8167b6a35dca89810562e82800a0e265c5e9251fa4497d922465e`,
and plan index
`88358b5f834da67d64d2a833473fc1ca7f8f56ac9eae1a47932f4c23652733bd`.
It source-confirmed this wave's sixteen roots; those returns bind predecessor
bytes only and provide no clearance for this rewrite.

The subsequent schema-valid narrow verifier examined ADR
`cefca40f93e80832966bbb599512df6cf09d033620d0643fb9818ef469cd4196`,
plan
`d3e25587b88e185516a1d67a69b18c102066add4abcd7100d72cee31bc134b4c`,
schema
`99896d2ec8d937d37dd9b4512ced0ae5a92f150453a7f2ba1729a584e25cdefa`,
and normalized body
`ad0795b76eee70b36b5f5229f1991aa540832f27c7b280d3ae1875f9b648ff04`.
It verified four final groups and left
`protocol-transition-drain-fence-integrity` plus
`independent-leaf-mutation-coverage` open solely on the half-null drain tuple
fixed by this wave. It does not review the corrected hashes.

### 3.2 C1-SHIPPING

C1 is post-implementation evidence, not an implementation body. Bodies A,
B, and C own every harness and every instrumentation point. C1 only runs
those harnesses, captures immutable evidence, and adjudicates it against the
accepted hashes and exact implementation head.

C1 requires complete fault/concurrency/UAT evidence, direct-mode Desktop
UAT, security and Bugbot review, no open protected finding,
`partial_rollout=false`, and fresh verifier shipping clearance.
`partial_rollout=false` attests that the M1 implementation and its evidence
are complete; it says nothing about deployment reach. Shipping clearance is
irrelevant before implementation. PR readiness, merge, release,
installation, host activation, and live rollout remain separate owner gates.
C1 may run against a WRITABLE environment only after explicit R1 canary GO
names that bounded canary; C1 clearance does not authorize R2.

After C0 passes, implementation remains separately NO-GO until the owner
names a refreshed exact baseline and gives an explicit implementation GO.
That authorization is not part of C0 and cannot substitute for C1.

R0 is Body C predeployment evidence, not rollout: candidate bytes, DIRECT
projection, and installer receipts run only in a throwaway environment while
the live protocol remains unchanged. After C0 acceptance and a separate
implementation GO, the owner must give an explicit **R1 canary GO** before
one named supported single-root canary may become WRITABLE. C1 runs against
that bounded canary. Only after C1 shipping clearance may the owner give a
separate **R2 rollout GO** for DIRECT M1.

Reports carry `predeployment_evidence=R0|absent` and
`rollout_stage=NONE|R1|R2` separately from verifier `partial_rollout`.
C0 design acceptance, implementation GO, R1 canary GO, C1 shipping
clearance, and R2 rollout GO are five distinct facts; none advances another.
External ownership, multi-root, Task/subagent, and broader-platform support
remain deferred.

### 3.3 One owner, exact-byte acceptance, and promotion

The single acceptance authority is the existing repository owner/operator
**`KleinPerkins` (Laurence Duggan)**, grounded in `.github/CODEOWNERS`
(`* @KleinPerkins`) and the repository's existing owner record. No committee,
reviewer, checker, or implementation body can substitute for that principal.

`awa-registration-acceptance-body/v2` has one exact byte algorithm.

Constants:

```text
DOMAIN = ASCII("awa-registration-acceptance-body/v2") || 0x00
SENTINEL = ASCII("__AWA_ACCEPTED_STATUS_TOKEN_V2__")
U64 = unsigned 64-bit big-endian
```

The four logical surfaces, in this explicit ascending bytewise UTF-8 path
order, are:

1. `docs/adr/0025-durable-registration-episodes-and-tool-admission.md` —
   complete file bytes;
2. `docs/adr/README.md` — exactly the ADR 0025 index-row bytes, including its
   terminating LF;
3. `docs/plans/README.md` — exactly the v3 index-row bytes, including its
   terminating LF; and
4. `docs/plans/native-entry-durable-registration-v3.md` — complete file
   bytes.

Every backing file must decode as strict UTF-8, contain no CR byte, use LF
line endings, and end in exactly one final LF. A row surface is the one exact
matching line including that LF; no preceding/following bytes enter that
surface.

The exact old full contexts and token substitutions are:

```text
docs/adr/0025-durable-registration-episodes-and-tool-admission.md
OLD_CONTEXT = "Status: draft — 2026-09-26 (C0-DESIGN NO-GO)\n"
OLD_TOKEN = "draft"
NEW_TOKEN = "accepted"

docs/adr/README.md
OLD_CONTEXT = "| [0025](0025-durable-registration-episodes-and-tool-admission.md) | Draft — C0-DESIGN NO-GO — 2026-09-26 | Propose single-root durable registration with one merged request/effect authority and member epoch, exact 7-table/9-trigger/97-generated-leaf manifest, direct OPEN authority, audit-only transition witness, stateless rendering, member-isolated admission, and distinct implementation/R1/C1/R2 gates; fresh exact-hash review/verifier adjudication remain C0 gates. |\n"
OLD_TOKEN = "Draft"
NEW_TOKEN = "Accepted"

docs/plans/README.md
OLD_CONTEXT = "| `native-entry-durable-registration-v3.md` | DRAFT — C0-DESIGN NO-GO — 2026-09-26 | Single-root candidate with one merged request/effect authority and member epoch, exact 7-table/9-trigger/97-generated-leaf manifest, direct OPEN authority, audit-only transition witness, stateless rendering, member-isolated admission, and distinct implementation/R1/C1/R2 gates; fresh exact-hash review/verifier adjudication remain C0 gates. |\n"
OLD_TOKEN = "DRAFT"
NEW_TOKEN = "ACCEPTED"

docs/plans/native-entry-durable-registration-v3.md
OLD_CONTEXT = "- **Status:** DRAFT (for review) — C0-DESIGN NO-GO\n"
OLD_TOKEN = "DRAFT (for review)"
NEW_TOKEN = "ACCEPTED"
```

For each entry, `NEW_CONTEXT` is mechanically
`OLD_CONTEXT[0:token_start] || NEW_TOKEN ||
OLD_CONTEXT[token_end:]`; there is no separately authored new context.
Source bytes must contain exactly one complete OLD_CONTEXT or exactly one
complete NEW_CONTEXT. Within that matched context, the selected token occurs
exactly once and the opposite token is absent; occurrences outside the
matched context are irrelevant. Zero/multiple matching contexts, both
contexts, or any ambiguous token span rejects.

Normative pseudocode:

```text
framed = DOMAIN
for spec in SURFACES_IN_THE_NUMBERED_ORDER:
    backing = read_bytes(spec.path)
    require strict_utf8(backing)
    require b"\r" not in backing
    require backing.endswith(b"\n") and not backing.endswith(b"\n\n")
    surface = backing if spec.kind == FULL_FILE
              else unique_exact_line_including_lf(backing, OLD_CONTEXT|NEW_CONTEXT)
    context_start, context = unique_occurrence(surface, OLD_CONTEXT|NEW_CONTEXT)
    token_start, token_end = unique_token_span_within(context, OLD_TOKEN|NEW_TOKEN)
    token_start += context_start; token_end += context_start
    normalized = surface[:token_start] || SENTINEL || surface[token_end:]
    path = UTF8(spec.path)
    framed ||= U64(len(path)) || path
    framed ||= U64(len(normalized)) || normalized
digest = lowercase_hex(SHA256(framed))
require no_unconsumed_or_appended_bytes(framed)
```

Promotion computes post files in memory by replacing only those four token
spans. For each complete backing file:
`post_prefix == pre_prefix` and `post_suffix == pre_suffix` around the token
span. The checker rejects reordered surfaces, omitted/wrong row LF,
non-UTF-8, CRLF, missing/double final LF, non-64-bit or little-endian length,
alternate sentinel/domain, date/path/title/description/non-token mutation,
duplicate context, old+new token coexistence, and extra framed bytes.

The only legal order is:

1. exact-hash C0 review and verifier technical clearance;
2. the checker applies the four substitutions in memory, verifies that every
   other byte is identical, and computes the allowed post-promotion whole-file
   hashes plus unchanged normalized digest;
3. `KleinPerkins` conditionally accepts that exact post-hash vector and digest;
4. the checker revalidates current pre-hashes and the bound acceptance,
   atomically applies the four substitutions, verifies computed post-hashes
   and normalized equality, emits a detached `acceptance-promotion/v2`
   receipt with ordered paths, each exact old/new token substitution,
   all four pre/post whole-file hashes, algorithm id, domain, sentinel, and
   normalized digest, and freezes ADR/plan bytes;
5. only then may the same owner separately grant implementation GO, followed
   later by R1 canary GO, C1, and R2 rollout GO.

The detached receipt prevents self-hash circularity. Owner acceptance and
promotion are not performed by this draft.

## 4. Exact M1 contract

### 4.1 Identity, privacy, and persisted JCS

Semantic objects use RFC 8785 JCS. Parsers reject duplicate keys, unknown
fields, floats, invalid Unicode, and out-of-bound depth/count/bytes. Hashes
are domain-separated, length-framed SHA-256. JSON 64-bit values are decimal
strings.

```text
member_id = H("awa-reg-member-v1", physical root identity,
              per-worktree Git-dir identity, common-dir identity)
episode_id = H("awa-reg-episode-v1", conversation_id, generation_id,
               source_contract, source_event, protocol_generation,
               member_id, workspace_roots_hash, tool_inventory_hash,
               hook_projection_hash)
effect_id = H("awa-reg-effect-v3", member_id, member_epoch,
              request_kind, request_basis_hash,
              action_plan_hash, required_protocol_generation,
              required_runtime_capability_hash)
action_hash = H("awa-reg-action-v1", effect_id, ordinal, action_kind,
                postcondition_hash)
certificate_hash =
    H("awa-reg-certificate-v1", effect_id, ledger_head_hash,
      completion_hash, proof_hash, final_basis_hash, helper_generation)
subject_key =
    H("awa-reg-status-subject-v4", member_id)
successor_transition_id =
    H("awa-reg-successor-v4", operation_kind, target_cause_code,
      expected_target_member_tuple_hash, expected_target_status_hash,
      expected_target_effect_tuple_hash, target_member_tuple_hash,
      target_status_hash, target_effect_tuple_hash, target_member_epoch,
      target_basis_hash, target_successor_member_epoch,
      target_successor_basis_hash, target_effect_id, target_successor_effect_id)
```

There is no separate request object. One `registration_effect` row is born
with immutable request identity and immutable intended action tuple. Before
execution it is the pending request; after the OPEN_EFFECT barrier the same
row is the effect. Its outcome changes exactly once from NULL to
`SUCCESS`, `LOGICAL_CONFLICT`, or `SUPERSEDED`.

The member basis is exactly physical identity, Git topology and operation
safety, policy eligibility, and lifecycle closure. Conversation, episode,
event source/generation, protocol generation, and root-set facts are
excluded. An episode has exactly one member foreign key.

Every row hash uses one domain-separated JCS object built from the exact
ordered column list below. Nullable fields encode as JCS `null`. The manifest
order is canonical SQL column order; the fixture asserts both this source
order and the RFC 8785 key-sorted byte preimage. Current operation backlinks
and their hashes are excluded, then bound separately by audit rows and
triggers. There is no “all other fields” rule.

<!-- registration-hash-preimages:begin -->
```text
protocol_hash|awa-reg-protocol-v4|protocol_seq,protocol_generation,mode,schema_hash,profile_hash,runtime_capability_hash,writer_binary_hash,writer_capability_hash,tool_inventory_hash,hook_projection_hash,hook_matcher_mode,hook_matcher_hash,projection_receipt_hash,projection_file_generation,installer_identity_hash,installer_capability_hash,storage_dev,first_effect_id,staged_generation,staged_schema_hash,staged_profile_hash,staged_runtime_capability_hash,staged_writer_binary_hash,staged_writer_capability_hash,staged_tool_inventory_hash,staged_hook_projection_hash,staged_hook_matcher_mode,staged_hook_matcher_hash,staged_projection_receipt_hash,staged_projection_file_generation,staged_installer_identity_hash,staged_installer_capability_hash,staged_epoch_hash,transition_kind,transition_reason_code,previous_protocol_hash,drain_boot_id,drain_deadline_mono_ns,absence_proof_hash,quiescence_proof_hash,created_wall_ns
staged_epoch_hash|awa-reg-staged-v2|staged_generation,staged_schema_hash,staged_profile_hash,staged_runtime_capability_hash,staged_writer_binary_hash,staged_writer_capability_hash,staged_tool_inventory_hash,staged_hook_projection_hash,staged_hook_matcher_mode,staged_hook_matcher_hash,staged_projection_receipt_hash,staged_projection_file_generation,staged_installer_identity_hash,staged_installer_capability_hash
member_tuple_hash|awa-reg-member-tuple-v2|member_id,canonical_root,root_dev,root_ino,git_toplevel,git_dir,git_dir_dev,git_dir_ino,git_common_dir,git_common_dev,git_common_ino,proof_dev,projection_dev,legacy_state_dev,physical_basis_hash,git_basis_hash,policy_basis_hash,operation_basis_hash,lifecycle_basis_hash,current_basis_hash,member_epoch,phase,current_effect_id,runtime_subject_key,helper_generation,current_outcome_kind,current_completion_hash,current_proof_hash,current_certificate_hash,current_conflict_hash,pending_effect_id,pending_member_epoch,pending_basis_hash,pending_effect_tuple_hash
episode_envelope_hash|awa-reg-episode-envelope-v2|episode_id,conversation_id,generation_id,source_contract,source_event,protocol_generation,member_id,workspace_root_count,workspace_roots_hash,tool_inventory_hash,hook_projection_hash,created_wall_ns
request_tuple_hash|awa-reg-request-tuple-v3|effect_id,member_id,member_epoch,request_kind,request_basis_hash,predecessor_effect_id,required_protocol_generation,required_runtime_capability_hash,action_plan_hash,required_action_count,action_1_kind,action_1_hash,postcondition_1_hash,action_2_kind,action_2_hash,postcondition_2_hash,action_3_kind,action_3_hash,postcondition_3_hash,action_4_kind,action_4_hash,postcondition_4_hash,external_growth_reservation_bytes,outcome_reservation_bytes,successor_reservation_bytes
outcome_tuple_hash|awa-reg-outcome-tuple-v2|effect_id,outcome_kind,outcome_helper_generation,ledger_head_hash,first_conflict_event_seq,completion_hash,final_basis_hash,proof_hash,certificate_inputs_hash,certificate_hash,conflict_code,conflict_hash,superseded_by_effect_id,successor_transition_id
ledger_hash|awa-reg-ledger-v2|effect_id,event_seq,ordinal,action_kind,action_hash,postcondition_hash,observation_kind,observation_hash,prior_ledger_hash,external_growth_bytes,observed_wall_ns
status_hash|awa-reg-status-v5|subject_key,member_id,member_epoch,current_effect_id,status_version,schedule_boot_id,observed_now_mono_ns,next_due_mono_ns,due_since_mono_ns,attempt_count,backoff_ns,help_due,executor_token_hash,executor_boot_id,executor_generation,unavailable_count,yield_count,blocked_basis_fingerprint,reason_code
operation_envelope_hash|awa-reg-operation-v6|operation_seq,operation_id,operation_class,operation_kind,expected_revision,protocol_seq,expected_mode,expected_generation,expected_protocol_hash,runtime_capability_hash,writer_binary_hash,profile_hash,writer_capability_receipt_hash,installer_identity_hash,installer_capability_receipt_hash,protocol_lock_receipt_hash,control_binding_hash,target_member_id,target_effect_id,lineage_effect_id,target_successor_effect_id,target_executor_token_hash,expected_target_status_hash,target_episode_id,target_transition_id,target_subject_key,target_protocol_hash,target_staged_epoch_hash,expected_target_member_tuple_hash,expected_target_effect_tuple_hash,target_member_epoch,target_basis_hash,target_successor_member_epoch,target_successor_basis_hash,target_member_tuple_hash,target_effect_tuple_hash,target_effect_outcome_hash,target_action_plan_hash,target_cause_code,target_episode_hash,target_action_ledger_hash,target_status_hash,sample_boot_id,sample_mono_ns,measured_free_bytes,projected_db_growth_bytes,external_growth_bytes,new_external_reservation_bytes,new_outcome_reservation_bytes,new_successor_reservation_bytes,control_reserve_bytes,created_wall_ns
```
<!-- registration-hash-preimages:end -->

The excluded backlink columns are exact: protocol
`first_effect_operation_id,operation_id`; member/status/action
`write_operation_seq,write_operation_id,write_operation_hash`; episode the
same write triple; effect request
`created_operation_seq,created_operation_id,created_operation_hash`; effect
outcome `outcome_operation_seq,outcome_operation_id,outcome_operation_hash`;
and each hash column itself. The operation envelope excludes only its own
`operation_envelope_hash`. INSTALL therefore computes request/member/status
hashes first, computes the audit envelope over those targets second, and
writes backlinks last; no preimage references its current operation.
Blob bytes are excluded from row JCS and are bound through their adjacent
named content hash after byte-identical schema validation.

`member_epoch` is the sole monotonic member revision. It appears once in
effect identity, current and pending member state, operation witnesses,
successor handoff, CAS predicates, and runtime status. There is no parallel member
version or admission epoch.

The complete `workspace_roots` array must have length one. Missing, empty,
multi-root, partial, mixed, primary, excluded, detached, nonlocal, aliased,
ambiguous, or unresolvable input denies the whole invocation. Before both
member and episode identity exist, the only response is the fixed stateless
copy below; no row or counter is written:

```text
AWA registration could not identify exactly one supported workspace. Open one clean linked worktree and retry.
```

`conversation_id` and `generation_id` are 1–128 byte ASCII values matching
`[A-Za-z0-9][A-Za-z0-9._:-]{0,127}`. They come only from the current
intercepted event's top-level fields under the recorded `source_contract` and
`source_event`; no path, parent-agent inference, cache, timestamp, or locally
generated fallback may supply either. Missing, duplicate, transformed, or
out-of-grammar provenance denies before episode persistence.

Persisted blobs use only these closed schemas:

| Blob column | Exact schema and fields |
|---|---|
| `action_plan_blob` | `awa-registration-action-plan/v1`: `schema`; `actions` (exactly four ordered objects with `ordinal`, `kind`, `action_hash`, `postcondition_hash`); `external_growth_reservation_bytes`; `outcome_reservation_bytes`; `successor_reservation_bytes` |
| `observation_blob` | `awa-registration-observation/v1`: `schema`, `effect_id`, `event_seq`, `ordinal`, `kind`, `measured_postcondition_hash`, `external_growth_bytes`, `detail_code` |
| `completion_blob` | `awa-registration-completion/v1`: `schema`, `effect_id`, `action_count`, `ledger_head_hash`, `final_basis_hash` |
| `proof_blob` | `awa-registration-proof/v1`: `schema`, `effect_id`, `member_id`, `physical_basis_hash`, `git_basis_hash`, `policy_basis_hash`, `lifecycle_basis_hash`, `final_basis_hash` |
| `certificate_inputs_blob` | `awa-registration-certificate-inputs/v1`: `schema`, `effect_id`, `ledger_head_hash`, `completion_hash`, `proof_hash`, `final_basis_hash`, `helper_generation` |
| `conflict_blob` | `awa-registration-conflict/v1`: `schema`, `effect_id`, `ordinal`, `conflict_code`, `expected_hash`, `observed_hash` |

All identifiers/hashes are lowercase 64-hex strings; ordinals and byte
counts are decimal strings; `kind`, `detail_code`, and `conflict_code` use
their SQL enums; no other key or free text is allowed. The typed writer
rebuilds each blob from relational scalars, JCS-encodes it, verifies byte-for-
byte re-encoding equality and its hash before `BEGIN IMMEDIATE`, and rejects
any blob whose parsed tree cannot be derived from the named relational tuple.

The negative corpus rejects a prohibited key or sentinel value at every
depth: `prompt`, `attachment`, `transcript`, `model`, `task_text`,
`tool_input`, `file_content`, `environment`, `credential`, `authorization`,
`cookie`, `secret`, `raw_path`, and `user_message`, plus `BEGIN PRIVATE KEY`,
`Bearer `, `ghp_`, `xox`, and embedded NUL. The fixture injects every
prohibited key and sentinel at every object/array/string leaf, adds every
unknown key position, and mutates every canonical byte class. Corpus
rejection is required even when the containing blob otherwise matches a
schema. Canonical local paths exist only in private typed columns; rendered
responses, logs, alerts, and projections expose only named
hashes/reason/action codes.

### 4.2 Supported path, profile, receipt, and device boundary

The dedicated store is:

```text
${XDG_STATE_HOME}/awa/registration-v1/registration.db
```

The only M1 profile is local macOS/APFS with stock SQLite `>=3.51.3`,
`journal_mode=WAL`, `synchronous=FULL`, `fullfsync=ON`,
`checkpoint_fullfsync=ON`, foreign keys, defensive mode,
`trusted_schema=OFF`, normal locking, and no checkpoint-on-close. Unsupported
WAL shared memory denies; there is no alternate VFS or journal fallback.

Bootstrap walks an absolute normalized path descriptor-relative without
following links. Every existing ancestor must be a root- or effective-user-
owned directory and not group/other writable. Protocol directories are
user-owned `0700`; DB/WAL/SHM and immutable proof files are user-owned,
single-link regular `0600` objects. The runtime uses stock
`SQLITE_OPEN_NOFOLLOW` when exposed, binds parent/object device+inode before
the path-based open, and rechecks them after open and each transaction.

The profile receipt is the domain-separated SHA-256 of one closed JCS
preimage:

```text
schema, measurement_order, platform, os_build, apfs_fstype,
apfs_fsid_0, apfs_fsid_1, apfs_mount_flags,
sqlite_runtime_version, sqlite_source_id, sqlite_compile_options_hash,
sqlite_vfs_name, journal_mode, synchronous, fullfsync,
checkpoint_fullfsync, foreign_keys, defensive, trusted_schema,
locking_mode, nofollow_available, checkpoint_on_close,
state_parent_dev, db_dev, wal_dev, shm_dev, proof_parent_dev,
projection_parent_dev, legacy_parent_dev, root_dev, git_dir_dev,
git_common_dev, ancestry_hash, descriptor_binding_hash
```

The hash input is
`b"awa-registration-profile/v2\\0" || JCS(profile_object)`.
`profile_object.schema` is literal `awa-registration-profile/v2`;
`platform` is literal `darwin`; `apfs_fstype` is literal `apfs`; SQLite/VFS
and pragma fields are lowercase ASCII strings except
`nofollow_available,fullfsync,checkpoint_fullfsync,foreign_keys,defensive`,
`trusted_schema`, and `checkpoint_on_close`, which are JCS booleans. Every `*_dev`, fsid component,
mount flag, and kernel integer is a base-10 string (`-?[0-9]+` for signed
fsid values; `[0-9]+` otherwise). Every `*_hash` is lowercase 64-hex. Unknown
keys, numbers, floats, alternate literals, and locale encodings reject.

`measurement_order` is exactly:

```text
["ANCESTRY","DESCRIPTOR_FS","SQLITE_RUNTIME","DB_OPEN",
 "PRAGMA_READBACK","WAL_DURABILITY","DEPENDENCY_DEVICES",
 "FINAL_DESCRIPTOR_RECHECK"]
```

Its steps are:

1. descriptor-walk and ownership/mode ancestry;
2. `fstat` each bound descriptor for device/inode and `fstatfs` that same
   descriptor for exact lowercase `apfs`, the two signed-decimal
   `f_fsid.val[]` components, and unsigned-decimal mount flags;
3. SQLite runtime/source-id/compile options/VFS;
4. descriptor-bound DB open and object identities;
5. set then read back pragmas in the order shown above;
6. WAL/SHM identity and durability probe;
7. proof/projection/legacy/root/Git device measurements; and
8. final descriptor recheck and JCS hash.

`sqlite_compile_options_hash` hashes the distinct `PRAGMA compile_options`
rows in bytewise ascending UTF-8 order with one LF after each value.
`ancestry_hash` hashes root-to-leaf descriptor records containing only
component ordinal, owner, mode, device, inode, link count, and type. The
profile preimage uses the exact displayed key set and RFC 8785 property order
(equivalent to bytewise ASCII for these keys); numeric kernel values are
canonical decimal strings and no locale-rendered or raw structure bytes are
hashed.

`descriptor_binding_hash` is
`SHA256(b"awa-registration-descriptor-binding/v1\\0" ||
JCS(binding_object))`. `binding_object` is exactly
`{"schema":"awa-registration-descriptor-binding/v1","records":[...]}`.
Records are ordered
`state_parent,db,wal,shm,proof_parent,projection_parent,legacy_parent,root,git_dir,git_common`;
each has exactly `ordinal,role,component_hash,st_dev,st_ino,st_mode,st_uid,
st_gid,st_nlink,fd_flags,nofollow,fstype,fsid_0,fsid_1,mount_flags`.
`ordinal` and all kernel values use the decimal-string rules above,
`component_hash` is lowercase 64-hex, `nofollow` is JCS boolean, `fstype` is
literal `apfs`, and no path or opaque bytes appear.

A03 owns fixed vectors. `A03-PROFILE-VALID` uses `os_build/source_id=fixture`,
SQLite `3.51.3`, VFS `unix`, `wal/full/normal`, required booleans, decimal
`"1"`, signed fsid `"-1","1"`, hash=`"aa"*32`, and the exact role order.
Expected descriptor hash is
`300bd90ff7f86774d939835c8d410f0b25e817c47881391fae95327610241e71`;
expected profile hash is
`3d6c52ff2aaa14f64a2793586c2703c7c6edcfc25033a448503e5d3ea8e539a7`.
`A03-PROFILE-BAD-DB-INO` changes only DB `st_ino` to `"2"`; its descriptor
digest is
`bb26b2b3a2f69b3f826410f910c1b0920302abdd1d85962739c372fd433db3bf`
and it must fail descriptor recheck. Every field/order/encoding mutation is a
targeted kill.

M1 requires every listed `*_dev` to equal `state_parent_dev` and every
descriptor's `f_fsid` pair and filesystem type to equal the state parent's
measured APFS tuple. `st_dev` is only a same-device rename/allocation
precondition; it is not claimed to prove power-loss durability, physical
media identity, or APFS volume-group behavior. Any mismatch or unavailable
measurement is root-level unsupported before intent. Every write repeats
descriptor identity, APFS tuple, and free-space/reservation preflight.

Stock SQLite remains path-bound. Same-UID raw SQLite access, same-user path
replacement between checks, and a same-UID process bypassing the connection
authorizer are explicit unsupported residuals, not claimed impossible.
Observed schema/history/hash drift is RED and invokes repair; it is never
silently normalized.

### 4.3 Closed-world object and branch manifest

The exact authority is seven tables, nine triggers, zero views, and zero
ordinary indexes. SQLite autoindexes are only those implied by declared
primary/unique constraints.

| # | Table | Retained invariant | Counterexample requiring it |
|---:|---|---|---|
| 1 | `registration_protocol_epoch` | Append-only protocol snapshots; `MAX(protocol_seq)` alone selects current mode/generation and staged epoch | A mutable current pointer can diverge from transition history |
| 2 | `registration_member` | One canonical current tuple per physical member in exactly three phases | Concurrent episodes can otherwise fork admission truth |
| 3 | `registration_episode` | Immutable one-root conversation snapshot bound to one member and exact hook/tool hashes | Episode facts otherwise contaminate member identity or become unverifiable |
| 4 | `registration_effect` | One durable operation: immutable request/intent identity plus one irreversible NULL-to-closed outcome | Separate request/effect authorities create split closure and ambiguous acknowledgements |
| 5 | `registration_effect_action` | Append-only, ordinal semantic observations; UNAVAILABLE never appends | Blind replay can duplicate external lifecycle work |
| 6 | `registration_runtime_status` | One deterministic member subject with bounded mutable executor/retry/help state | Executors in phases or append-only unavailability create forks or unbounded growth |
| 7 | `registration_operation_audit` | One immutable operation envelope carrying predecessor/successor scalar hashes, cause, provenance, and control inputs | A stale writer or actor string can otherwise impersonate a transition |

No request, archive, notice, proof, membership, alert/outbox, Rescue, GC, or current-pointer
table exists. Proof/certificate is effect outcome. ADR 0020 alone owns
integrity generations, alert outbox, dispatch, and receipts.

The hand-counted coarse “variant” budget is deleted. The closed
`awa-registration-leaves/v1` manifest below is generated into concrete unique
keys `trigger|branch|operation|transition|selector-or-reason-or-cause|outcome`. Semicolons
separate leaves; `-` is an absent dimension. A01 expands these exact groups,
compares them byte-for-byte to the trigger coverage inventory, and derives the
published leaf count. No test may claim trigger coverage from a coarser branch
count.

<!-- registration-leaf-manifest:begin -->
```text
trg_protocol_epoch_insert=bootstrap@BOOTSTRAP@BOOTSTRAP@BOOTSTRAP@-;activate@ACTIVATE@ACTIVATE@ACTIVATE@-;first_effect@OPEN_EFFECT@FIRST_EFFECT@FIRST_EFFECT@-;begin_drain@BEGIN_DRAIN@BEGIN_DRAIN@BEGIN_DRAIN@-;stage_next@STAGE_NEXT@STAGE_NEXT@STAGE_NEXT@-;cancel_drain@CANCEL_DRAIN@CANCEL_DRAIN@CANCEL_DRAIN@-;advance_generation@ADVANCE_GENERATION@ADVANCE_GENERATION@ADVANCE_GENERATION@-;pre_effect_dormant@PRE_EFFECT_DORMANT@PRE_EFFECT_DORMANT@PRE_EFFECT_DORMANT@-;contain_boot@ENTER_CONTAINMENT@ENTER_CONTAINMENT@DRAIN_BOOT_CHANGED@-;contain_timeout@ENTER_CONTAINMENT@ENTER_CONTAINMENT@DRAIN_TIMEOUT@-;contain_adoption@ENTER_CONTAINMENT@ENTER_CONTAINMENT@ADOPTION_FAILED@-;contain_store@ENTER_CONTAINMENT@ENTER_CONTAINMENT@STORE_FAILURE@-;begin_repair@BEGIN_REPAIR@BEGIN_REPAIR@BEGIN_REPAIR@-
trg_operation_audit_insert=bootstrap@BOOTSTRAP@-@-@-;install_member@INSTALL_MEMBER@-@-@-;bind_episode@BIND_EPISODE@-@-@-;reacquire@REACQUIRE_EFFECT@-@-@-;open@OPEN_EFFECT@-@-@-;append@APPEND_ACTION@-@-@-;close_success@CLOSE_SUCCESS@-@-@SUCCESS;close_conflict@CLOSE_CONFLICT@-@-@LOGICAL_CONFLICT;invalidate@INVALIDATE_REQUESTED@-@BASIS_CHANGED@SUPERSEDED;set_pending@SET_PENDING@-@-@-;replace_pending@REPLACE_PENDING@-@PENDING_REPLACED@SUPERSEDED;handoff@HANDOFF_RESOLVED@-@-@-;mark_unavailable@MARK_UNAVAILABLE@-@-@-;reboot@REBOOT_STATUS@-@-@-;schedule@SCHEDULE_STATUS@-@-@-;activate@ACTIVATE@-@-@-;begin_drain@BEGIN_DRAIN@-@-@-;stage_next@STAGE_NEXT@-@-@-;cancel_drain@CANCEL_DRAIN@-@-@-;adopt@ADOPT_EFFECT@-@-@-;advance@ADVANCE_GENERATION@-@-@-;pre_effect_dormant@PRE_EFFECT_DORMANT@-@-@-;contain@ENTER_CONTAINMENT@-@-@-;begin_repair@BEGIN_REPAIR@-@-@-
trg_member_update_state_machine=invalidate@INVALIDATE_REQUESTED@REQUESTED_TO_REQUESTED@BASIS_CHANGED@SUPERSEDED;open@OPEN_EFFECT@REQUESTED_TO_IN_FLIGHT@-@-;set_pending@SET_PENDING@IN_FLIGHT_TO_IN_FLIGHT@-@-;replace_pending@REPLACE_PENDING@IN_FLIGHT_TO_IN_FLIGHT@PENDING_REPLACED@SUPERSEDED;adopt_preserve@ADOPT_EFFECT@IN_FLIGHT_TO_IN_FLIGHT@-@-;adopt_replace@ADOPT_EFFECT@IN_FLIGHT_TO_IN_FLIGHT@STAGED_CAPABILITY_INCOMPATIBLE@SUPERSEDED;close_success@CLOSE_SUCCESS@IN_FLIGHT_TO_RESOLVED@-@SUCCESS;close_conflict@CLOSE_CONFLICT@IN_FLIGHT_TO_RESOLVED@-@LOGICAL_CONFLICT;handoff_pending@HANDOFF_RESOLVED@RESOLVED_TO_REQUESTED@BASIS_CHANGED@-;handoff_basis@HANDOFF_RESOLVED@RESOLVED_TO_REQUESTED@BASIS_CHANGED@-;handoff_closure@HANDOFF_RESOLVED@RESOLVED_TO_REQUESTED@CURRENT_CLOSURE_CHANGED@-;handoff_conflict_retry@HANDOFF_RESOLVED@RESOLVED_TO_REQUESTED@EXPLICIT_CONFLICT_RETRY@-
trg_episode_insert=bind@BIND_EPISODE@-@-@-
trg_effect_insert=install@INSTALL_MEMBER@-@-@-;invalidate@INVALIDATE_REQUESTED@-@BASIS_CHANGED@-;set_pending@SET_PENDING@-@-@-;replace_pending@REPLACE_PENDING@-@PENDING_REPLACED@-;handoff_basis@HANDOFF_RESOLVED@-@BASIS_CHANGED@-;handoff_closure@HANDOFF_RESOLVED@-@CURRENT_CLOSURE_CHANGED@-;handoff_conflict_retry@HANDOFF_RESOLVED@-@EXPLICIT_CONFLICT_RETRY@-;adopt_replace@ADOPT_EFFECT@-@STAGED_CAPABILITY_INCOMPATIBLE@-
trg_effect_close=success@CLOSE_SUCCESS@-@-@SUCCESS;conflict@CLOSE_CONFLICT@-@-@LOGICAL_CONFLICT;supersede_requested@INVALIDATE_REQUESTED@-@BASIS_CHANGED@SUPERSEDED;supersede_pending@REPLACE_PENDING@-@PENDING_REPLACED@SUPERSEDED;supersede_adopted@ADOPT_EFFECT@-@STAGED_CAPABILITY_INCOMPATIBLE@SUPERSEDED
trg_effect_action_append=observed_exact@APPEND_ACTION@-@-@OBSERVED_EXACT;applied_verified@APPEND_ACTION@-@-@APPLIED_VERIFIED;logical_conflict@APPEND_ACTION@-@-@LOGICAL_CONFLICT
trg_runtime_status_insert=clean@INSTALL_MEMBER@-@CLEAN_ELIGIBLE@-;dirty@INSTALL_MEMBER@-@BLOCKED_DIRTY@-;operation_blocked@INSTALL_MEMBER@-@BLOCKED_OPERATION@-
trg_runtime_status_update=reacquire_native@REACQUIRE_EFFECT@-@NATIVE_GENERATION@-;reacquire_adopted@REACQUIRE_EFFECT@-@ADOPTED_LINEAGE@-;open@OPEN_EFFECT@-@-@-;close_success_idle@CLOSE_SUCCESS@-@NO_PENDING@SUCCESS;close_success_pending@CLOSE_SUCCESS@-@PENDING@SUCCESS;close_conflict_idle@CLOSE_CONFLICT@-@NO_PENDING@LOGICAL_CONFLICT;close_conflict_pending@CLOSE_CONFLICT@-@PENDING@LOGICAL_CONFLICT;invalidate_clean@INVALIDATE_REQUESTED@-@CLEAN_ELIGIBLE@-;invalidate_dirty@INVALIDATE_REQUESTED@-@BLOCKED_DIRTY@-;invalidate_operation@INVALIDATE_REQUESTED@-@BLOCKED_OPERATION@-;handoff_basis_clean@HANDOFF_RESOLVED@-@BASIS_CHANGED_CLEAN@-;handoff_basis_dirty@HANDOFF_RESOLVED@-@BASIS_CHANGED_DIRTY@-;handoff_basis_operation@HANDOFF_RESOLVED@-@BASIS_CHANGED_OPERATION@-;handoff_closure_clean@HANDOFF_RESOLVED@-@CURRENT_CLOSURE_CHANGED_CLEAN@-;handoff_closure_dirty@HANDOFF_RESOLVED@-@CURRENT_CLOSURE_CHANGED_DIRTY@-;handoff_closure_operation@HANDOFF_RESOLVED@-@CURRENT_CLOSURE_CHANGED_OPERATION@-;handoff_conflict_retry@HANDOFF_RESOLVED@-@EXPLICIT_CONFLICT_RETRY@-;adopt_preserve@ADOPT_EFFECT@-@PRESERVE_EXECUTOR@-;adopt_install@ADOPT_EFFECT@-@INSTALL_EXECUTOR@-;mark_unavailable@MARK_UNAVAILABLE@-@-@-;reboot_requested_clean@REBOOT_STATUS@-@REQUESTED_CLEAN@-;reboot_requested_dirty@REBOOT_STATUS@-@REQUESTED_DIRTY@-;reboot_requested_operation@REBOOT_STATUS@-@REQUESTED_OPERATION@-;reboot_in_flight@REBOOT_STATUS@-@IN_FLIGHT@-;reboot_resolved_success@REBOOT_STATUS@-@RESOLVED_SUCCESS@-;reboot_resolved_conflict@REBOOT_STATUS@-@RESOLVED_CONFLICT@-;reboot_resolved_pending@REBOOT_STATUS@-@RESOLVED_PENDING@-;schedule@SCHEDULE_STATUS@-@-@-
```
<!-- registration-leaf-manifest:end -->

Manifest text is not its own oracle. A01's independent fixture catalog is
authored separately from this block and executes one valid transaction for
every leaf. It derives the observed leaf id only from committed trigger table,
operation kind, transition/reason or selector, and outcome readback, then
requires exact set equality with the authored manifest. A06 additionally
changes each predicate introduced by this wave and requires one targeted
rejection/mutation kill. T01 coverage exhausts nullable current/staged,
first-effect, and drain-field carry—including legal ACTIVATE and first
OPEN_EFFECT/FIRST_EFFECT with null drain fields—so mere manifest equality
cannot claim branch coverage.

The complete semantic budget is literal and machine-counted:

| Dimension | Exact count |
|---|---:|
| Tables / triggers / generated transition leaves | 7 / 9 / 97 |
| Durable member phases | 3 |
| Protocol modes / transition kinds / transition reasons | 4 / 10 / 13 |
| Request kinds / effect outcomes | 3 / 3 |
| Action kinds / observation kinds / conflict codes | 4 / 3 / 5 |
| Successor cause codes | 5 |
| Transaction classes / operation kinds | 3 / 24 |
| Synthetic global row ceilings / database-byte ceilings | 0 / 0 |
| Capacity classes / terminal capacity stop codes | 0 / 0 |
| Runtime reason codes | 26 |
| Durable notice forms / durable notice variants | 0 / 0 |
| Predeployment evidence stages / rollout authorization stages / implementation bodies | 1 / 2 / 3 |

The read-only aggregate snapshot renders one deterministic response for its
selected reason code. Rendering has no relation, operation, trigger branch,
repeat counter, FULL/COMPACT split, or presentation history. The fixed
preidentity copy remains stateless. R0 is Body C predeployment evidence;
only R1 and R2 are rollout authorization stages.

Compared with the immediately prior reviewed draft, this pass keeps 7 tables,
9 triggers, 24 operations, 10 transitions, 13 transition reasons, and 26
runtime reasons. The mechanically derived leaf count changes 95→97 because
reboot's blocked and resolved-idle branches are now outcome-specific. New
authority is carried only in existing audit/projection/profile fields; no
table, trigger, operation, phase, transaction class, scheduler state, or
implementation body is introduced.
For scale, frozen v2 contains 57
`CREATE TABLE` statements, 107 `CREATE TRIGGER` statements, seven member
phases, and eight implementation tasks; its Rescue, physical-GC, separate
request/effect, effect-graph, and broader writer surfaces are absent here.

Adding a table, trigger, branch, durable phase, or implementation body
requires a concrete source counterexample, a superseding draft, a new exact
SQL hash, and fresh C0 review.

### 4.4 Canonical normalized SQL

The canonical artifact is the exact UTF-8/LF byte sequence between the begin
and end markers, excluding marker lines and Markdown fence. It has one
statement per object, a final `;\n`, no comments, macros, or runtime
expansion. Its SHA-256 is
`221aaf6680b50ca8f6c8c2cf024acbedbf5273b90c8c5625bcc4100c448d5ede`.
A01 extracts, executes, and hashes these bytes and compares the complete
object inventory. Bootstrap
must supply that same digest as `schema_hash`; staged schema hash must equal
the current digest. Any schema change requires a superseding design and
migration rather than generation advance.

Every trigger-critical fact is a relational scalar. Blobs are evidence only;
SQL does not parse JCS or recompute SHA-256. Every rejecting trigger is
written as `(complete valid predicate) IS NOT TRUE`, so NULL cannot bypass a
guard.

<!-- canonical-registration-sql:begin -->
```sql
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
```
<!-- canonical-registration-sql:end -->

A bounded documentation fixture extracts and hashes the exact bytes above,
executes them on local SQLite, and checks 7 tables, 9 triggers, 0 views, 0
ordinary indexes, `integrity_check=ok`, and an empty foreign-key check. It
seeds rows before trigger installation and mechanically invokes every named
trigger guard; all nine must return their exact abort. Focused in-memory
fixtures additionally cover direct OPEN races and stale member/effect/status
CAS; unchanged SUCCESS
no-op; more than eight historical members with deterministic eight-per-tick
continuation; old-boot versus same-boot executor recovery; no-pending
adoption reservation; unrelated-member admission churn; pre-adoption
stage replacement/cancel and post-adoption rejection; NULL drain samples; one member epoch; NULL
discriminator/latent tuples; ADVANCE_GENERATION `storage_dev`; and unchanged
low-free/FULL/containment behavior. The same harness model-checks archive
equivalence before/after subtraction, ambiguous transition resolution,
corruption mismatch, SUPERSEDED reachability, adopted-lineage reacquire and
hostile mismatch, exact hash preimage/order including INSTALL, and every
T03/T09 one-column carry mutation. These are preimplementation documentation
checks, not implementation, model, fault, concurrency, UAT, or C1 evidence.

This wave additionally fixtures legal ACTIVATE/FIRST_EFFECT null carry;
fresh/equal/stale structural events; helper/adoption bindings; committed
post-I/O authority; A03/A22 vectors; every positive drain leaf; selected-miss
fairness; all reboot targets; adoption lost-ack; the C0 verifier matrix; 97
independent successful leaf transactions plus predicate kills; R1/R2 scope;
C0–C7 crash/restart cuts; real process-lock death takeover; and ambiguous
reacquire's four outcomes.

The independent drain-tuple matrix executes every initializer, carrier, and
clearing leaf, then separately rejects boot-only non-null, deadline-only
non-null, failed boot clear, failed deadline clear, and SQL NULL/UNKNOWN
mutations. Legal ACTIVATE and first OPEN_EFFECT/FIRST_EFFECT are positive
null/null carry fixtures.

The connection authorizer is part of the exact authority boundary. It
permits INSERT only through named prepared statements; denies UPDATE/DELETE
for protocol, episode, action, and operation history; permits only
the named member/status transitions and one effect outcome update; and
denies DDL, ATTACH, VACUUM, writable pragmas, raw SQL, and extension loading.
There are no protocol-history UPDATE/DELETE triggers because that same
append-only authorizer rule applies consistently to every immutable table.

### 4.5 Exact trigger responsibilities

| ID | Trigger | Exact responsibility | Rejected counterexample |
|---|---|---|---|
| T01 | `trg_protocol_epoch_insert` | Genesis or one of ten legal transition kinds; current/staged tuple carry; paired first-effect provenance; total drain-boot sample; pre-adoption replace/cancel fence; requested/single-hop drain fences; repair eligibility | Skipped generation, post-adoption replace/cancel, requested-effect drain, multi-hop adoption, split first marker, or fabricated containment becomes current |
| T02 | `trg_operation_audit_insert` | Contiguous revision, current protocol, DATA/control authentication, executor-token/status CAS for every I/O-authorizing or result operation, fresh descriptor-bound free bytes, and exact reservation accounting | Stale owner, actor-string CONTROL, stale free-space sample, no-pending adoption reserve loss, or a write consumes another operation's reserve |
| T03 | `trg_member_update_state_machine` | The six and only six member edges, including due REQUESTED invalidation, staged adoption compatibility, outcome selection, and condition-bound successor handoff | Generic same-phase mutation, unchanged SUCCESS reopen, incompatible pending carry, or final member with an unproven successor edge |
| T04 | `trg_episode_insert` | Exact one-root member/protocol/tool/hook binding | Episode binds a different member, root set, inventory, or projection |
| T05 | `trg_effect_insert` | Deterministic merged request/intent install for initial, invalidation, pending set/replace, proven fresh handoff, or staged replacement | Separate request identity, unchanged SUCCESS reopen, wrong source/successor, or missing action reservation |
| T06 | `trg_effect_close` | Immutable identity/intent; executor/status CAS only for SUCCESS/conflict; audit/state witness for SUPERSEDED | Stale executor, unreachable supersession, reopen, second outcome, or partial success |
| T07 | `trg_effect_action_append` | Current executor/status CAS, next frozen ordinal, current in-flight effect, prior ledger, satisfying predecessor, and materialized external growth | Stale executor, duplicate/out-of-order action, post-conflict progress, UNAVAILABLE row, or unreserved external growth |
| T08 | `trg_runtime_status_insert` | Deterministic non-null subject, member-current-effect equality, and one status row per member | NULL/competing subject or stale effect |
| T09 | `trg_runtime_status_update` | Subject immutability; complete branch carry; exact open/close/handoff/adopt/unavailable/native-or-adopted-reacquire/reboot/schedule leaves | Stale owner, hostile generation mismatch, one-column smuggling, unbounded retry, or false green |

The generated carry fixture uses the exact branch-owned manifest below.
Framework-owned hash/version/write-backlink columns are checked separately.
For every other table column and every branch, the trigger must contain an
explicit `NEW ... IS OLD` carry predicate; the fixture mutates that one
column and requires the named guard abort.

```text
T03.invalidate=policy_basis_hash,operation_basis_hash,lifecycle_basis_hash,current_basis_hash,member_epoch,phase,current_effect_id,helper_generation,current_outcome_kind,current_completion_hash,current_proof_hash,current_certificate_hash,current_conflict_hash,pending_effect_id,pending_member_epoch,pending_basis_hash,pending_effect_tuple_hash
T03.open=phase
T03.set_pending=pending_effect_id,pending_member_epoch,pending_basis_hash,pending_effect_tuple_hash
T03.replace_pending=pending_effect_id,pending_member_epoch,pending_basis_hash,pending_effect_tuple_hash
T03.adopt_preserve=helper_generation
T03.adopt_replace=helper_generation,pending_effect_id,pending_member_epoch,pending_basis_hash,pending_effect_tuple_hash
T03.close_success=phase,current_outcome_kind,current_completion_hash,current_proof_hash,current_certificate_hash,current_conflict_hash
T03.close_conflict=phase,current_outcome_kind,current_completion_hash,current_proof_hash,current_certificate_hash,current_conflict_hash
T03.handoff_pending=policy_basis_hash,operation_basis_hash,lifecycle_basis_hash,current_basis_hash,member_epoch,phase,current_effect_id,helper_generation,current_outcome_kind,current_completion_hash,current_proof_hash,current_certificate_hash,current_conflict_hash,pending_effect_id,pending_member_epoch,pending_basis_hash,pending_effect_tuple_hash
T03.handoff_basis=policy_basis_hash,operation_basis_hash,lifecycle_basis_hash,current_basis_hash,member_epoch,phase,current_effect_id,helper_generation,current_outcome_kind,current_completion_hash,current_proof_hash,current_certificate_hash,current_conflict_hash,pending_effect_id,pending_member_epoch,pending_basis_hash,pending_effect_tuple_hash
T03.handoff_closure=policy_basis_hash,operation_basis_hash,lifecycle_basis_hash,current_basis_hash,member_epoch,phase,current_effect_id,helper_generation,current_outcome_kind,current_completion_hash,current_proof_hash,current_certificate_hash,current_conflict_hash,pending_effect_id,pending_member_epoch,pending_basis_hash,pending_effect_tuple_hash
T03.handoff_conflict_retry=policy_basis_hash,operation_basis_hash,lifecycle_basis_hash,current_basis_hash,member_epoch,phase,current_effect_id,helper_generation,current_outcome_kind,current_completion_hash,current_proof_hash,current_certificate_hash,current_conflict_hash,pending_effect_id,pending_member_epoch,pending_basis_hash,pending_effect_tuple_hash
T09.reacquire_native=schedule_boot_id,observed_now_mono_ns,next_due_mono_ns,due_since_mono_ns,attempt_count,backoff_ns,help_due,executor_token_hash,executor_boot_id,executor_generation,blocked_basis_fingerprint,reason_code
T09.reacquire_adopted=schedule_boot_id,observed_now_mono_ns,next_due_mono_ns,due_since_mono_ns,attempt_count,backoff_ns,help_due,executor_token_hash,executor_boot_id,executor_generation,blocked_basis_fingerprint,reason_code
T09.open=schedule_boot_id,observed_now_mono_ns,next_due_mono_ns,due_since_mono_ns,attempt_count,backoff_ns,help_due,executor_token_hash,executor_boot_id,executor_generation,blocked_basis_fingerprint,reason_code
T09.close_success_idle=schedule_boot_id,observed_now_mono_ns,next_due_mono_ns,due_since_mono_ns,attempt_count,backoff_ns,help_due,executor_token_hash,executor_boot_id,executor_generation,unavailable_count,yield_count,blocked_basis_fingerprint,reason_code
T09.close_success_pending=schedule_boot_id,observed_now_mono_ns,next_due_mono_ns,due_since_mono_ns,attempt_count,backoff_ns,help_due,executor_token_hash,executor_boot_id,executor_generation,blocked_basis_fingerprint,reason_code
T09.close_conflict_idle=schedule_boot_id,observed_now_mono_ns,next_due_mono_ns,due_since_mono_ns,attempt_count,backoff_ns,help_due,executor_token_hash,executor_boot_id,executor_generation,blocked_basis_fingerprint,reason_code
T09.close_conflict_pending=schedule_boot_id,observed_now_mono_ns,next_due_mono_ns,due_since_mono_ns,attempt_count,backoff_ns,help_due,executor_token_hash,executor_boot_id,executor_generation,blocked_basis_fingerprint,reason_code
T09.invalidate=member_epoch,current_effect_id,schedule_boot_id,observed_now_mono_ns,next_due_mono_ns,due_since_mono_ns,attempt_count,backoff_ns,help_due,executor_token_hash,executor_boot_id,executor_generation,unavailable_count,yield_count,blocked_basis_fingerprint,reason_code
T09.handoff=member_epoch,current_effect_id,schedule_boot_id,observed_now_mono_ns,next_due_mono_ns,due_since_mono_ns,attempt_count,backoff_ns,help_due,executor_token_hash,executor_boot_id,executor_generation,unavailable_count,yield_count,blocked_basis_fingerprint,reason_code
T09.adopt_preserve=schedule_boot_id,observed_now_mono_ns,next_due_mono_ns,due_since_mono_ns,attempt_count,backoff_ns,help_due,executor_generation,blocked_basis_fingerprint,reason_code
T09.adopt_install=schedule_boot_id,observed_now_mono_ns,next_due_mono_ns,due_since_mono_ns,attempt_count,backoff_ns,help_due,executor_token_hash,executor_boot_id,executor_generation,blocked_basis_fingerprint,reason_code
T09.mark_unavailable=schedule_boot_id,observed_now_mono_ns,next_due_mono_ns,due_since_mono_ns,attempt_count,backoff_ns,help_due,executor_token_hash,executor_boot_id,executor_generation,unavailable_count,yield_count,reason_code
T09.reboot=schedule_boot_id,observed_now_mono_ns,next_due_mono_ns,due_since_mono_ns,attempt_count,backoff_ns,help_due,executor_token_hash,executor_boot_id,executor_generation,reason_code
T09.schedule=schedule_boot_id,observed_now_mono_ns,next_due_mono_ns,attempt_count,backoff_ns
```

Close semantics intentionally zero `unavailable_count`/`yield_count` only for
SUCCESS with no pending work. SUCCESS-with-pending and both conflict leaves
carry both counters exactly from OLD to NEW.

The authorizer and writer validate JCS/hash derivations and transaction
closure; triggers validate only relational inputs. A01 owns exact extraction,
inventory, hash, execution, and direct negative fixtures.

### 4.6 Three durable member phases

| Current | Event | Next | Same-transaction requirement |
|---|---|---|---|
| absent | exact observed basis | `REQUESTED` | member, merged durable operation, member status, and audit envelope |
| `REQUESTED` | due/unavailable | `REQUESTED` | bounded status only; no pre-authority lifecycle |
| `REQUESTED` | structural invalidation | `REQUESTED` | immutable operation witness, old effect→SUPERSEDED, successor effect, member-epoch increment, due/blocked status |
| `REQUESTED` | OPEN_EFFECT barrier | `EFFECT_IN_FLIGHT` | transaction-fresh member/effect/status CAS, optional FIRST_EFFECT append, sole executor install, member edge |
| `EFFECT_IN_FLIGHT` | structural invalidation | `EFFECT_IN_FLIGHT` | preserve active effect; set or full-CAS replace one pending effect |
| `EFFECT_IN_FLIGHT` | due same-effect help after UNAVAILABLE/reboot | `EFFECT_IN_FLIGHT` | `REACQUIRE_EFFECT` validates current boot/due time, protocol/generation/capability, effect/ledger and NULL outcome; installs one operation-bound executor and clears the schedule |
| `EFFECT_IN_FLIGHT` | staged adoption | `EFFECT_IN_FLIGHT` | bind old DRAINING+staged epoch, frozen action plan, and executor; replace any pending effect with a fresh staged-bound successor |
| `EFFECT_IN_FLIGHT` | exact success/conflict | `RESOLVED` | one effect outcome mutation, executor clear, exact member selection |
| `RESOLVED` | pending work, proven basis/closure change, or explicit conflict retry | `REQUESTED` | full predecessor audit/state CAS, existing-pending or condition-bound fresh successor, cleared result/pending, initialized status |
| `RESOLVED/SUCCESS` | unchanged event/startup/tick/retry | `RESOLVED/SUCCESS` | read-only no-op; no audit, effect, status, or member write |

There is no pre-authority, REGISTERED, or TERMINAL phase. `RESOLVED` has exactly:

- SUCCESS with all four actions, completion, final basis, proof, and
  certificate; or
- LOGICAL_CONFLICT with the first conflict also the last ledger entry and no
  success-only fields.

Partial, duplicate, wrong-effect, or hash-invalid closure is corruption. It
attempts installer-only containment and remains RED; it never becomes
RESOLVED.

### 4.7 Transaction, authorizer, and authenticated control boundary

Every mutation uses one typed store facade and one `BEGIN IMMEDIATE`
transaction. Its first statement inserts one operation envelope at the exact
expected revision. Every changed row copies that envelope. A mandatory
closure SELECT checks expected rows/counts before COMMIT; no-op calls do not
commit.

INSTALL_MEMBER's mandatory closure SELECT requires the initial member,
effect, and status rows; `member_tuple_hash`; and every member
`write_operation_seq|id|hash` backlink to equal that exact audit envelope.
T05 repeats the relational predicate, so a malformed initial backlink aborts
before commit without a new trigger.

The member lock has exactly one execution owner. OPEN_EFFECT,
REACQUIRE_EFFECT, ADOPT_EFFECT, every immediate pre-helper-I/O check,
APPEND_ACTION, CLOSE_SUCCESS, CLOSE_CONFLICT, and MARK_UNAVAILABLE carry the
operation's expected `target_executor_token_hash`. For OPEN_EFFECT it is the
new resulting executor; for reacquire or quiescent adoption
it equals the resulting executor; otherwise it equals the current non-NULL
executor. The operation's `expected_target_status_hash` is the expected
current status hash on these paths. T02 plus T06/T07/T09 compare both under the member lock
in the same transaction; a stale status or executor performs no I/O and
cannot append, close, clear, or take ownership. FIRST_EFFECT remains paired
to the one successful OPEN_EFFECT operation id.

`expected_target_status_hash` is CAS input only and never post-commit
authority. A successful OPEN_EFFECT, REACQUIRE_EFFECT, or quiescent
ADOPT_EFFECT returns one operation-bound in-memory capability. Immediately
before every helper I/O, while holding the same member lock, the typed API
rereads and requires: live executor hash equals the granting operation's
`target_executor_token_hash`; member/status/request tuple hashes equal its
`target_member_tuple_hash`, `target_status_hash`, and
`target_effect_tuple_hash`; ids equal its target member/effect; and the live
protocol hash equals `target_protocol_hash`. For staged adoption, the staged
epoch hash and current generation/capability must additionally equal the
immutable lineage witness. Any mismatch invalidates the capability and
performs no I/O.

The executor secret is generated in process memory before the granting
transaction; only its hash persists. Normal code receives an opaque
non-serializable capability object after COMMIT. Staged code receives the
same one-use secret over a pre-created anonymous `AF_UNIX` socketpair bound to
the authenticated staged process; it never enters argv, environment, files,
database, logs, receipts, or JSON, and both endpoints zeroize/close after
transfer. Same-UID memory/process compromise remains outside the guarantee.

The member lock is a process-scoped kernel advisory lock on the
descriptor-verified per-common-directory member lock object. The executor
process holds its descriptor continuously from the granting CAS through
helper I/O and APPEND/CLOSE/MARK resolution; process death closes the
descriptor and releases the lock. Only the subsequent successful acquirer may
insert MARK_UNAVAILABLE with `target_executor_token_hash` equal to the exact
stored hash and `expected_target_status_hash` equal to the exact old status;
it does not need or recreate the dead process's plaintext secret.

Lock order is installer protocol lock (CONTROL only) → one member lock
(bytewise `member_id`) → short `BEGIN IMMEDIATE` transaction. No second member
lock is nested. ADOPT commits, releases the protocol lock, and retains only
the member lock across helper I/O; helper callbacks cannot start CONTROL or a
nested store transaction. Same-UID code can ignore advisory locks, replace
paths, inspect memory, or bypass the authorizer/raw SQLite and remains an
explicit unsupported residual.

The §4.1 preimage manifest is exhaustive. T01 carries every branch-unowned
column with `=` for non-null values and `IS` for nullable values; current
operation backlinks are separately equal to the audit witness. The typed
closure SELECT re-derives both hashes. No transition may silently drop or
rebind one member of a coupled tuple.

Data and control use separate prepared-statement allowlists:

- DATA works only in WRITABLE and cannot compile CONTROL or immutable-table
  mutations.
- The sole exception is the exact OPEN_EFFECT prepared statement: while
  holding the current DATA capability it may insert one FIRST_EFFECT protocol
  row only when the marker pair is NULL. Every other DATA protocol INSERT is
  denied.
- Body A's typed OPEN_EFFECT API is the only owner of that exception. B may
  invoke the API but cannot compile the statement; C and CONTROL cannot
  impersonate it. The inserted protocol row and operation envelope share the
  same `operation_id`, preserving first-effect provenance.
- `REACQUIRE_EFFECT` is ordinary DATA, not a protocol exception. Its one
  named statement can only install an executor for the already-current
  in-flight effect after T09 proves current-boot due status and the exact
  member/effect/ledger/token/status/current-protocol tuple. A generation
  mismatch is legal only when immutable ADOPT_EFFECT lineage binds that exact
  active effect, old generation/capability, staged epoch/action plan, and
  current generation/capability. Its executor token, boot id, and status CAS
  are one atomic result; every hostile or lineage-free mismatch rejects.
- CONTROL is created only by the installer after immutable code identity,
  installer capability, and protocol-lock receipt are verified. It exposes
  one named transition/adoption statement and is then destroyed.
- T01/T02/T03 bind old current protocol, DRAINING state, immutable staged
  epoch, installer receipts, action plan, and affected rows. An actor string
  is never authorization.

This is authenticated against supported entrypoints, not non-forgeable
against the same UID. Raw same-UID SQLite access is unsupported and produces
RED drift when observed.

### 4.8 Installer protocol, drain, staging, and containment

```text
DORMANT     -> WRITABLE      ACTIVATE, DIRECT receipt only
WRITABLE    -> WRITABLE      FIRST_EFFECT, OPEN_EFFECT DATA exception once
WRITABLE    -> DRAINING      BEGIN_DRAIN
DRAINING    -> DRAINING      STAGE_NEXT, initial or pre-adoption replacement
DRAINING    -> DORMANT       CANCEL_DRAIN, clear pre-adoption candidate and return READ_ONLY
DRAINING    -> WRITABLE      ADVANCE_GENERATION
DRAINING    -> DORMANT       PRE_EFFECT_DORMANT, exact absence proof
DORMANT | WRITABLE | DRAINING
            -> CONTAINMENT   ENTER_CONTAINMENT
CONTAINMENT -> DRAINING      BEGIN_REPAIR
```

`first_effect_id` and `first_effect_operation_id` are both NULL before
FIRST_EFFECT, both become non-NULL in its OPEN_EFFECT transaction, and are
copied together by every later protocol row.

The staged epoch binds exact schema/profile/runtime/writer/tool/hook/direct-
projection/installer fields and `staged_epoch_hash`. Its schema hash must
equal the current canonical seven-table/nine-trigger digest. A changed schema
requires a superseding design and migration.

A staged candidate may be atomically replaced by STAGE_NEXT after quiescence
only while no committed ADOPT_EFFECT audit or current member/status tuple
references its staged epoch/generation. CANCEL_DRAIN uses the same fence,
clears any pre-adoption candidate, and returns to persisted DORMANT—the
existing READ_ONLY posture, not a fifth mode. After adoption, only
ADVANCE_GENERATION or containment/forward repair is legal.

Drain fences admission and later DATA writers, waits the prior writer,
disables old entrypoints, and refuses while any current CLEAN_ELIGIBLE
REQUESTED effect exists or any in-flight effect already requires a different
generation. Before drain, the driver must directly OPEN_EFFECT for due clean
work or otherwise resolve/SUPERSEDE it through an existing transition. It
also starts only after every RESOLVED pending effect has handed off.
ADVANCE_GENERATION repeats the requested-effect absence check. It then
enumerates every old-generation in-flight executor.
Control processes deterministic `member_id` batches of at most eight and
continues across passes until none remain; eight is not a generation
membership limit. Under each member lock, staged code recomputes the frozen effect
plan/ledger/postconditions. ADOPT_EFFECT binds the old current DRAINING row
and staged epoch. It preserves a valid old executor token or, for a
quiescent in-flight effect whose unavailable path cleared the executor,
installs one operation-bound staged executor token for same-effect help. If
an in-flight member has a pending effect, the same adoption transaction
records the predecessor/successor hashes in immutable audit, SUPERSEDEs it,
and installs a fresh effect bound to the staged
generation and runtime capability before advance; M1 does not mutate or
implicitly rebind the old intent.

Adoption requires OLD member helper generation—and any OLD executor
generation—to equal the current old generation and differ from staged. A
pending replacement is legal only when its required generation or capability
is staged-incompatible. After acknowledgement loss, the resolver compares
immutable ADOPT_EFFECT audit targets with the current member/status/pending
tuple; an exact target returns `ALREADY_APPLIED` with zero writes and never
reapplies completed lineage.

An adopted active effect may use its single immutable lineage hop to
REACQUIRE_EFFECT and close under the new generation. BEGIN_DRAIN refuses a
second drain while that effect's required generation still differs from the
current generation; multi-hop adoption is therefore impossible without new
state.

Every positive operation while DRAINING—STAGE_NEXT (initial or replacement),
CANCEL_DRAIN, ADOPT_EFFECT, ADVANCE_GENERATION, and PRE_EFFECT_DORMANT—takes a
non-null boot/continuous-time sample after `BEGIN IMMEDIATE`, requires boot
equality with `drain_boot_id`, and requires sample time at or before the
stored deadline. One-column NULL/boot/deadline mutations reject for every
leaf. Mismatch or expiry authorizes no positive edge; only existing
containment or forward repair may proceed.

The deadline is current-boot `mach_continuous_time()+5s`. If current boot
differs from `drain_boot_id`, drain fails immediately and attempts
ENTER_CONTAINMENT with reason `DRAIN_BOOT_CHANGED`; that operation requires a
non-NULL transaction-fresh `sample_boot_id` and `sample_mono_ns`, and the
sampled boot must differ. SQL NULL never selects this edge and no old
monotonic value is compared. ADVANCE_GENERATION preserves the prior current
protocol `storage_dev` exactly. Lock, plan, postcondition, or deadline failure
also attempts containment.

Committed CONTAINMENT is durable protocol authority and denies while the
hook works. `CONTAINMENT_UNAVAILABLE` means storage prevented that commit:
AWA cannot claim containment or denial, old entries remain disabled where
possible, the independent ADR 0020 host observer reports RED, and only the
installer-authenticated repair entrypoint may recover.

Pre-effect DRAINING→DORMANT requires paired first-effect NULL, no OPEN_EFFECT
audit, no action, no in-flight/resolved member, no executor, and exact
prior-byte restoration. Otherwise rollback is forbidden and the only finite
failure destination is containment/forward repair.

External projection ownership is rejected before any protocol or status
write. Every persisted protocol row is intrinsically DIRECT and carries a
non-NULL DIRECT receipt; there is no external-owner column value, dormant
external branch, reason, message, or recovery edge. External support remains
deferred, and this design adds no MAC, key distribution, or pretend host
attestation.

### 4.9 Effect, action, and outcome

OPEN_EFFECT is the first durable execution authority. Under the member lock,
it starts `BEGIN IMMEDIATE`, obtains a new current-boot
`mach_continuous_time()` sample after transaction start, and directly CASes
the exact due REQUESTED member/effect/status tuple to one operation-bound
executor. A stale status, member, effect, boot, due time, or competing
executor rejects. No durable pre-authority token/window/expiry step exists.

The merged effect row already contains immutable request identity, basis,
runtime capability, four-action intent, and reservations. OPEN_EFFECT
validates it plus the expected member/effect/status hashes and new executor token,
optionally inserts FIRST_EFFECT, installs the sole executor, records
its boot id, and moves REQUESTED→EFFECT_IN_FLIGHT. Only that commit authorizes
lifecycle I/O. Immediately before each helper call, the same operation
context and member lock recompare the current non-NULL executor token and
status hash; stale ownership denies before external I/O.

| Ordinal | Action | Exact replay postcondition |
|---:|---|---|
| 1 | `PUBLISH_EFFECT_PROOF` | Exact final `0600` immutable proof bytes/hash under the verified same-device parent |
| 2 | `CONVERGE_LEGACY_LEASE` | Compatibility projection binds exact root/member/effect/lease identity and bytes |
| 3 | `CONVERGE_LEGACY_LIFECYCLE` | Lease, adoption, attestation, and event form the frozen one-to-one graph |
| 4 | `COLLECT_FINAL_BASIS` | Fresh physical/Git/policy/operation/lifecycle/proof basis equals intent and final hash |

Each helper inspects before applying. Exact appends `OBSERVED_EXACT`; absence
applies, verifies, then appends `APPLIED_VERIFIED`; domain divergence appends
the first `LOGICAL_CONFLICT` then closes it. Unavailable/read-ambiguous
appends no action, releases the member lock, clears the executor, saturates
bounded status counters, schedules same-effect help, and yields. The
MARK_UNAVAILABLE transaction full-CASes the exact old status hash and current
non-NULL executor token; it cannot clear a stale or competing executor.

The next root event, startup pass, tick, or explicit retry does not call
OPEN_EFFECT again and does not create another effect. Under the member lock,
`REACQUIRE_EFFECT` begins a new transaction, samples the current boot and
`mach_continuous_time()` after `BEGIN IMMEDIATE`, requires that the scheduled
same-effect help is due, revalidates WRITABLE mode, effect/ledger, NULL
outcome, helper generation, runtime capability, and basis, then installs one
operation-bound executor token and clears the schedule. Only that commit
reauthorizes lifecycle I/O. A failed or ambiguous reacquisition performs no
I/O and leaves the same effect due.

Ambiguous REACQUIRE_EFFECT uses the native four-way resolver:

| Result | Exact predicate | Action |
|---|---|---|
| `COMMITTED` | operation id exists and live member/status/effect/protocol equal every target hash; caller retains the matching operation-bound secret | return that capability and resume |
| `ABSENT` | operation id absent and exact old due tuple remains | keep due; retry the same operation object |
| `PARTIAL` | any operation/current target subset or hash mismatch | perform no helper I/O; attempt existing containment |
| `UNAVAILABLE` | bounded reopen/read cannot establish another result | perform no I/O and make no state/authority claim |

COMMITTED without the matching in-memory secret cannot resume helper I/O; it
uses the member-lock takeover/MARK_UNAVAILABLE path before any later
reauthorization.

Effect outcome changes once:

- SUCCESS requires all four satisfying actions and complete
  completion/final-basis/proof/certificate data.
- LOGICAL_CONFLICT is reachable after any ordinal; the first conflict must
  also be the ledger head and last row, with no success-only data.
- SUPERSEDED requires the exact authorized operation kind, immutable
  predecessor/successor/status audit witness, reachable member state, and
  successor effect. It never requires an executor because REQUESTED and
  pending effects are not the active executor-owned effect.

Ambiguous SUCCESS/conflict close resolves after verified close/reopen in at
most three reads/250 ms:

| Result | Predicate | Next step |
|---|---|---|
| `COMMITTED_SUCCESS` | exact effect and member SUCCESS closure | fresh admission only |
| `COMMITTED_LOGICAL_CONFLICT` | exact effect and member conflict closure | preserve/report conflict |
| `ABSENT` | effect outcome NULL, member in flight, ledger closure exact | retry same close/effect |
| `UNAVAILABLE` | bounded fresh reads establish no normal result | mark same-effect help when writable; yield |

Only ABSENT retries. Return codes or files never select success.

### 4.10 Structural invalidation and successor handoff

Before intent, structural change uses the exact due status. One
transaction inserts the deterministic successor effect; records exact
predecessor/successor member/status/effect hashes and cause in immutable
audit; changes old outcome
NULL→SUPERSEDED; increments the sole member epoch; clears any executor;
installs the successor; and initializes clean-due or
blocked-unscheduled status.

The writer acquires the process-scoped member lock, rereads the current tuple,
then samples the successor basis; pre-lock B1 data never authorizes a
transition. INVALIDATE_REQUESTED and SET_PENDING require the sampled
basis/request tuple to differ from the current pair. REPLACE_PENDING requires
it to differ from the prior pending pair. Equality returns a zero-write no-op,
and a stale event cannot regress a committed later tuple.

During EFFECT_IN_FLIGHT the active effect is preserved. Structural change
sets one pending effect. A later replacement records the exact current and
pending hashes, SUPERSEDEs only the old pending effect, and installs the
deterministic successor. The active effect still reaches SUCCESS or conflict.

Every root event, startup reconciliation, 15-second tick, or exact retry
examines RESOLVED members. It attempts handoff only when a pending effect
exists, a fresh basis proves a basis/closure change, or an explicit retry
targets LOGICAL_CONFLICT. An unchanged SUCCESS is stable green and returns a
read-only no-op on event, startup, tick, and retry; it writes no operation,
effect, member, or status. Success and conflict otherwise
use the identical transaction:

1. compute `successor_transition_id` from the complete immutable predecessor,
   operation cause, and successor hashes;
2. insert the immutable operation witness and, when fresh, successor effect;
3. full-CAS the predecessor member/status/audit tuple;
4. install REQUESTED and clear result/pending fields; and
5. initialize current-boot due status or blocked-unscheduled status.

Ambiguous invalidation/handoff returns exactly:

| Result | Predicate | Next step |
|---|---|---|
| `APPLIED` | exact operation witness exists and member/status/effect equal its targets | continue successor |
| `ABSENT` | exact predecessor hashes remain and operation id is absent | retry same transition id |
| `OBSOLETE` | one fully valid later operation/current tuple exists | reread; never replay stale id |
| `UNAVAILABLE` | bounded reads establish no normal result | mark help when possible; yield |

Partial audit/member/effect/status combinations are corruption. Only ABSENT
retries. Event volume alone therefore cannot grow append-only history; growth
requires a proven change or explicit conflict retry.

### 4.11 Revision-fenced admission and launch denial

The branch order is normative:

```text
1. malformed/preidentity/root-cardinality failure -> fixed stateless deny
2. Task/subagent/agent-launch discriminator       -> default deny
3. unsupported/unknown discriminator              -> valid deny if received
4. ordinary supported tool                        -> B1 / E@R1 / B2 / R2
```

Task launch never reaches ordinary admission and cannot inherit parent
green. The closed parser, direct dispatcher, catch-all dispatcher, enumerated
dispatcher, serializer, startup reconciliation, tick, `status`, and `retry`
entrypoints all default-deny any Task, subagent, child-agent, or agent-launch
intent; none may translate it into an ordinary tool, diagnostic exception, or
parent-derived registration. Registration-only events never launch work.
Both matcher modes must receive and deny every installed launch discriminator
on the exact Cursor build or installation refuses activation with the existing
`HOOK_UNSUPPORTED` result. If Task is exposed only on an unreceivable seam,
M1 makes no coverage claim. No Task path falls through to persistence or
ordinary-tool admission.

For ordinary tools:

- B1 is an uncached complete live/event basis.
- E@R1 is one read transaction over complete
  protocol/episode/member/effect/action/status authority and returns the
  selected tuple token R1: protocol sequence/hash; episode envelope hash;
  member write sequence/tuple hash; status version/hash; and current effect
  outcome sequence/tuple hash plus ledger head.
- B2 independently recollects the same basis.
- R2 rereads exactly that selected member/status/effect tuple and the current
  protocol sequence/hash. It does not read global `MAX(operation_seq)`.

Allow requires B1=B2, R1=R2, exact episode/member
binding, DIRECT+WRITABLE, RESOLVED/SUCCESS, no pending effect, complete
closure, and a READY aggregate status snapshot. Any unknown, busy,
unavailable, mismatch, or selected-tuple change retries once from B1; a
second failure denies.

During R1, the current DIRECT receipt must have
`deployment_scope=R1_CANARY` and its exact candidate digest,
`canonical_root_hash`, and `member_id` must match this invocation; every other
root/member default-denies with existing `ROOT_UNSUPPORTED`. Only an
owner-authorized R2 receipt with `deployment_scope=R2_DIRECT` and null
root/member scope broadens admission.

Another member's conflict, retry, or overdue state never denies this member.
Only the selected member tuple and genuinely shared host facts are admission
inputs. An unrelated member may commit between E@R1 and R2 without changing
R1 or causing retry/denial. The successful B2 followed immediately by R2 is
invocation-start linearization only; it does not reserve or revoke a running
tool.

### 4.12 Hook inventory, projection, and fail-open truth

Hook-owner v4 binds normalized rows, exact enumerated inventory or proven
catch-all contract, matcher hash, inventory hash, projection hash, file
generation, protocol generation, DIRECT receipt, and wrapper/runtime hashes.

`tool_inventory_hash` is the JCS hash of bytewise-sorted closed tuples
`{event,server_or_empty,discriminator,role,serializer_schema}`.
`hook_projection_hash` is the JCS hash of bytewise-sorted normalized rows
`{event,matcher,command_argv,timeout_ms,fail_closed}` plus matcher mode/hash,
inventory hash, file generation, protocol generation, and wrapper/runtime
hashes. Duplicate tuples/rows, unknown keys, wildcard-looking syntax, or a
different sort order refuse activation.
The DIRECT receipt hash is
`SHA256(b"awa-registration-direct-receipt/v2\\0" || JCS(receipt))`.
`receipt` has exactly:

```text
schema, owner_mode, deployment_scope, candidate_digest,
schema_hash, profile_hash, runtime_capability_hash,
writer_binary_hash, writer_capability_hash, tool_inventory_hash,
hook_projection_hash, hook_matcher_mode, hook_matcher_hash,
installed_file_hash, projection_file_generation, protocol_generation,
wrapper_runtime_hash, installer_identity_hash, installer_capability_hash,
owner_gate_digest, canonical_root_hash, member_id
```

`schema` is literal `awa-registration-direct-receipt/v2`; `owner_mode` is the
concrete literal `DIRECT`; `deployment_scope` is
`R0_THROWAWAY|R1_CANARY|R2_DIRECT`; generations are unsigned decimal strings;
matcher mode uses the SQL enum; every digest/id is lowercase 64-hex.
`R1_CANARY` requires non-null root/member; `R2_DIRECT` requires both null;
`R0_THROWAWAY` is forbidden in persisted protocol. Unknown/opaque/secret
fields reject. `candidate_digest` is the domain-separated hash of the
exact JCS object
`schema_hash,profile_hash,runtime_capability_hash,writer_binary_hash,
writer_capability_hash,tool_inventory_hash,hook_projection_hash,
hook_matcher_mode,hook_matcher_hash,projection_file_generation,
protocol_generation` under tag `awa-registration-candidate/v1`.
`owner_gate_digest` binds the exact checker-generated R1 or R2 authorization
receipt; its detached owner signature is verified before hashing but is not a
JCS field or runtime secret.

A22 owns exact vectors `A22-R1-VALID` (all candidate hashes=`"aa"*32`,
installed/wrapper hashes=`"bb"*32`, owner gate=`"cc"*32`, root=`"dd"*32`,
member=`"ee"*32`, generations=`"1"`, matcher=`ENUMERATED`) and
`A22-R1-OTHER-ROOT` (root=`"ff"*32`, must deny), plus `A22-R2-VALID` with
null root/member. Expected candidate digest is
`a1c2c85d94124228ee839295c92b27efd1811c583e9e2e0f2b7ff06c7791e9ae`;
receipt digests are respectively
`4bc1ec7a34c527402da5ea85a55e868a5409bc1cb4a7634c6032f6ed65793d75`,
`abc336e3e104857960bda2540744b81ba1a343bf900cd4b27c1ddb0c42d7d6fb`,
and
`b6f93242d5f21629898d41aa101639753b26cc133be4d8932d48e3cc5a4e7431`.
The harness mutation-kills every field, order, literal, nullability, and encoding.
External ownership is rejected before a protocol row is constructed.

- CATCH_ALL activates only with an official contract and direct live UAT for
  ordinary, MCP, renamed, unknown, and Task launch discriminators.
- ENUMERATED lists every observed supported discriminator and every Task/
  subagent launch discriminator. Missing/extra names or hash drift refuses.
- External projection support is deferred and has no M1 row or recovery path.

| Seam/failure | Exact behavior | Honest statement |
|---|---|---|
| `sessionStart` | registration opportunity; never a later-tool gate | no denial claim |
| `beforeSubmitPrompt` | bounded registration/retry opportunity | no later-tool denial claim |
| `beforeShellExecution` | valid deny/exit 2 blocks only when wrapper completes | otherwise shell may fail open |
| `beforeReadFile` | valid deny/exit 2 gates model admission after local read | never claims disk-read prevention |
| `beforeMCPExecution` / `beforeMCP` | receiving proven seam may deny | absent seam is unsupported |
| proven catch-all `preToolUse` | receives ordinary/unknown/renamed/Task discriminators | no catch-all claim without contract+UAT |
| startup/import/exec/config failure, timeout, kill, crash | fail open | unsupported/RED; no denial claim |
| missing row/event/matcher/wrapper | fail open | unsupported/RED; no denial claim |
| malformed, duplicate, contaminated, wrong-shape output | fail open | unsupported/RED; no denial claim |
| store unavailable or containment commit unavailable | fail-open honesty; independent host RED/repair path | cannot claim denial or containment |
| functioning wrapper returns seam-valid deny/intentional exit 2 | that invocation blocks | may claim only that invocation was denied |
| DIRECT projection/install before receipt | activation is absent; protocol stays DORMANT | no installed/protected claim |
| installer broker, identity, capability, or protocol lock failure | no CONTROL statement is compiled; last committed mode remains authority | no transition claim |
| startup/tick absent, late, or crashed | no attempt is inferred; shared host receipt becomes RED when stale | no service/denial claim |
| `status` / `retry` parse or execution failure | no wake or mutation is inferred | current durable authority is unchanged |
| effect helper/proof/legacy I/O unavailable | no action row; bounded same-effect help only when writable | no success/conflict claim |
| ADR 0020 observer/alert failure | registration authority is unchanged | no notification claim |

Global rows stay `failClosed:false`. Manual terminal/editor work, Tab,
external processes, already-running tools, cloud-early turns, and total
hook/runtime/host absence remain unsupported.

### 4.13 Runtime status, reboot, retry, and fairness

`subject_key` is deterministic and non-null. There is exactly one runtime
status row per member; no episode-scoped presentation row exists. The row
carries the sole `member_epoch` and current merged operation
(`current_effect_id`, which is also the pending request identity before
OPEN_EFFECT).

The typed writer recomputes `subject_key` from `member_id` before the
transaction. T08 repeats relational member uniqueness under the same
`BEGIN IMMEDIATE` serialization boundary. A01/A06 race inserts and directly
try NULL, hash-mismatch, duplicate-member, and stale-current-effect rows.

The exact quiescent green MEMBER shape is:

```text
member_epoch=<member current epoch>
current_effect_id=<member current effect>
reason_code=NULL
schedule/executor/blocked fields=NULL
help_due=0
unavailable_count=0
yield_count=0
```

One read-only aggregate status snapshot is the sole operator and admission
summary. In one read transaction it returns the selected
protocol/episode/member/effect/action/status token, current host-tick receipt,
supported profile hash, DIRECT projection/inventory receipt, storage
measurement, parser result, and serializer result. `READY`/green requires all
of them to be current and mutually equal: host, profile, projection, storage,
parser, serializer, DIRECT+WRITABLE protocol, exact member/episode binding,
RESOLVED/SUCCESS closure, no pending effect, own selected-attempt health, and
inventory membership. Any missing, unknown, stale, or mismatched component
returns the applicable existing bounded reason (`HOST_STARVED`,
`PROTOCOL_INCOMPATIBLE`, `HOOK_UNSUPPORTED`, storage reason,
`PARSER_REJECT`, `SERIALIZER_INVALID`, or member reason); there is no new
reason family and status performs no write.

Times use boot identity plus suspend-inclusive `mach_continuous_time()`.
Persisted schedule fields are all-null or one current-boot group with
`next_due=observed_now+backoff`. Old-boot values are never compared.

Registration opportunities are root-bearing `sessionStart`,
`beforeSubmitPrompt`, every supported ordinary intercepted event, startup
reconciliation, the host tick, and exact `awa registration status|retry`
controls. `status` is read-only; `retry` only wakes the ordinary protocol and
never bypasses executor or admission. Tokens/arguments are case-sensitive and
attachment-free; extra input is not control authorization. The tick is a
short one-shot executable. AWA owns its contract; only the `~/dev` host
overlay may later schedule it.

Reboot behavior is exact:

- REQUESTED clean rebases due scheduling on the new boot; blocked REQUESTED
  is unscheduled.
- EFFECT_IN_FLIGHT keeps effect/ledger. REBOOT_STATUS may clear a non-NULL
  executor only when its stored `executor_boot_id` differs from a non-NULL
  transaction-fresh current boot sample; it then becomes immediately due for
  exact `REACQUIRE_EFFECT`.
- RESOLVED with no pending effect clears all runtime scheduling state.
- RESOLVED with pending effect immediately attempts handoff; if it cannot
  complete, it remains RESOLVED with new-boot due/help status.

Same-boot executor death never uses REBOOT_STATUS. Under the member lock,
MARK_UNAVAILABLE must full-CAS the exact old status hash and non-NULL executor
token, clear it, and schedule help; only then may REACQUIRE_EFFECT install a
new executor.

Member history has no row ceiling: a ninth and every later distinct member
may be installed when ordinary free-space admission passes. Eight is only the
per-tick work budget. At each 15-second tick, one read snapshot orders due
MEMBER rows by
`(COALESCE(observed_now_mono_ns,due_since_mono_ns), due_since_mono_ns,
member_id)` and selects the first eight. A fixed eight-lane pool gives only
that selected batch a two-second attempt deadline and five-second service
budget: at most eight serial 125 ms OPEN slices, concurrent helpers at at
most two seconds, at most eight serial 125 ms result slices, and one second
launch/collection tolerance.

Every selected row either commits its attempt outcome or the existing
bounded SCHEDULE_STATUS/yield update; both advance that row's
`observed_now_mono_ns`, so untouched due rows sort ahead on the next healthy
tick. Failure to commit either is a selected-row miss, not a silent queue
success. For any finite continuously due set, this deterministic continuation
eventually selects every row without a new epoch or queue table. The host
receipt records the snapshot token and selected member/status hashes. A
selected row with no durable outcome by its tick deadline is own-member
`HOST_STARVED`; an unselected backlog row remains queued, not RED. A
stale/missing shared receipt remains a separate host RED gate. There is no
claim that one tick services all members and no fixed wall-clock liveness
bound for an unbounded backlog.

After a selected worker timeout/crash, the coordinator acquires the member
lock and must commit existing SCHEDULE_STATUS with saturated yield and the
fresh selected-attempt sample, advancing the ordering key. If that write
fails, the aggregate snapshot reports shared `STORE_UNAVAILABLE` or
`HOST_STARVED` as observed, and the finite-set fairness claim is suspended
until persistence recovers. No attempt, advancement, or fairness progress is
inferred and no scheduler row/state is added.

UNAVAILABLE appends no action. It releases the common-directory lock, clears
the executor, saturates counters at three, schedules same-effect help, and
yields. Only `REACQUIRE_EFFECT` can make that same effect executable again.
No new effect, sleep, or unbounded retry is permitted.

The renderer maps the read-only aggregate snapshot's selected reason to one
deterministic reason-specific response. Repeated reads return identical bytes
for identical snapshots; no response form, repeat count, cause fingerprint,
wall time, operation, or presentation history is persisted. Preidentity uses
the fixed stateless copy.

### 4.14 Normative reason-to-action matrix

The future exact entrypoints are read-only `awa registration status`, wake
request `awa registration retry`, and installer-authenticated
`awa registration doctor|repair|install --direct`. This draft installs none.

| Reason | Entrypoint / authority | Safe action | Exact recovery |
|---|---|---|---|
| preidentity/root parse before identity | none; stateless wrapper | show fixed §4.1 copy | fresh complete single-root event |
| `REGISTRATION_REQUIRED` | status/retry; B | inspect, then retry once | exact successor reaches SUCCESS |
| `EFFECT_IN_FLIGHT` | status/retry; B | inspect; retry only when due | same effect closes exactly |
| `RESOLVER_UNAVAILABLE` | status/retry; A+B | retry once when due | four-way resolver returns a normal result |
| `BASIS_UNSTABLE` | status; B | stop changing the root and retry | two complete basis samples agree |
| `BASIS_TIMEOUT` | status/retry; B | retry after root becomes responsive | basis completes within deadline |
| `DIRTY_UNSUPPORTED` | existing governed `Retain` flow; independent finish/retention authority | retain selected work, then open a clean linked worktree | fresh clean/idle basis |
| `GIT_OPERATION_UNSUPPORTED` | existing governed preservation flow; independent Git/retention authority | finish/preserve operation, then open clean target | recognized idle Git state |
| `EFFECT_CONFLICT` | repair; installer+A | do not edit state/proof manually | exact closure or committed containment |
| `STORE_FAILURE` | repair; installer+A | keep workspace idle | exact native/integrity state restored or containment committed |
| `PROTOCOL_INCOMPATIBLE` | install/doctor; installer+C via A | install exact DIRECT candidate | compatible WRITABLE epoch |
| `HOOK_UNSUPPORTED` | install/doctor; installer+C | repair exact inventory/projection | required seam proof current |
| `UNKNOWN_DISCRIMINATOR` | doctor; C | update only through superseding reviewed inventory | discriminator becomes enumerated/proven |
| `TOOL_NOT_IN_INVENTORY` | doctor; C | use no diagnostic bypass | exact inventory contains tool |
| `STORE_UNAVAILABLE` | doctor; installer+A | restore store access; do not move files manually | verified profile opens |
| `STORAGE_DEGRADED` | status/retry; A+B from fresh filesystem measurement | free space outside AWA; do not edit registration files | next ordinary opportunity automatically resumes only when measured free bytes meet the full reserve |
| `STORAGE_RED` | repair; installer+A | keep workspace idle | integrity/native store access restored or containment commits |
| `DEVICE_MISMATCH` | doctor; A | open a supported same-device root; do not relocate state manually | all required `st_dev` values equal |
| `HOST_STARVED` | retry then host-job doctor; B+C | request one retry, then repair scheduler | own attempt within healthy threshold and shared receipt current |
| `ROOT_COUNT_UNSUPPORTED` | none; stateless/B | open exactly one root | exact one-root envelope |
| `ROOT_UNSUPPORTED` | status; B | open eligible clean linked non-primary root | supported canonical root |
| `BOOT_ID_UNAVAILABLE` | doctor; A+C | retry after boot identity works | current boot/clock receipt available |
| `TASK_SUBAGENT_DENIED` | none in M1; B+C | continue in current agent | only a separately accepted future design |
| `PARSER_REJECT` | install/doctor; C | repair exact closed parser | envelope passes closed schema |
| `SERIALIZER_INVALID` | install/doctor; C | repair wrapper serializer | seam-valid output fixture passes |
| `CONTAINMENT` | repair; installer+A invoked by C | keep workspace idle | forward repair reaches supported WRITABLE |
| `CONTAINMENT_UNAVAILABLE` | host repair; independent ADR 0020 observer plus installer+A | keep workspace idle; no denial claim | store reopens and containment/repair commits |

Unknown internal values map to fixed `STORE_UNAVAILABLE` copy without a
durable state assertion. Dirty handling writes only redacted fingerprint/reason, sets
no unchanged-basis timer, and never touches source, index, refs, operation
state, or worktree.

### 4.15 Free-space admission and native SQLite failure

Lean M1 has no product-defined row ceiling, database-byte ceiling, retirement
threshold, or terminal capacity state. SQLite's native integer/page limits
and errors remain substrate facts, not a second lifecycle. The only product
admission bound is:

```text
required_free_bytes =
  1 GiB filesystem safety floor
  + projected bytes for this transaction
  + exact remaining control reserve (at most 14 MiB)
  + every outstanding effect external/outcome/successor reservation
  + reservations created by this transaction
```

Every write begins `BEGIN IMMEDIATE`, samples free bytes from the already
profile-bound filesystem descriptor, and places that fresh measurement and
all reservation terms in the first SQL statement's operation envelope. T02
accepts only when `measured_free_bytes >= required_free_bytes`; operation-
specific predicates charge APPEND_ACTION, outcome close, successor, and
control writes against the reservation they consume.

Each open effect reserves its exact external maximum, up to one MiB shared by
its four possible action appends and SUCCESS/conflict/SUPERSEDED closure, and
up to one MiB for its deterministic successor. The successor reserve remains
while that effect is current RESOLVED authority. The at-most-14-MiB control
reserve covers containment, begin repair, staged clear/stage, one batch of at
most eight member adoptions, generation advance, and fallback containment.
ADOPT_EFFECT excludes
an old effect reservation only when `target_successor_effect_id` is non-NULL
and that target is the member's actual pending effect being superseded in the
same transaction. A no-pending adoption retains the active effect's complete
reservation. UNAVAILABLE consumes no action or reserved transaction.

The two failure moments are intentionally different:

1. **Before accepting a new durable operation.** If the fresh free-space
   inequality fails, the transaction writes nothing: no audit row, effect,
   notice, counter, or containment claim. A functioning receiving hook
   returns the existing `STORAGE_DEGRADED` denial from the fresh measurement.
   Every later event/startup/tick/retry remeasures; the same path resumes
   automatically only after externally observable free space again satisfies
   the complete reserve. No unchanged-basis timer or durable capacity state
   exists.
2. **After an operation is already durable.** A later suffix transaction that
   returns native `SQLITE_FULL`, `SQLITE_IOERR`, or an extended form never
   treats the return code as commit truth. Close/reopen plus the existing
   operation-envelope revision/target hashes resolves
   `COMMITTED | ABSENT | PARTIAL | UNAVAILABLE`: exact COMMITTED is honored;
   exact ABSENT leaves the prior tuple authoritative; PARTIAL is corruption;
   unavailable reads make no state claim. A separate installer-authenticated
   `ENTER_CONTAINMENT/STORE_FAILURE` transaction is then attempted for
   ABSENT/PARTIAL post-durable failure. If it commits, CONTAINMENT is durable
   authority. If SQLite cannot commit it, AWA reports only externally observed
   `CONTAINMENT_UNAVAILABLE`; it does not claim a durable row, persisted
   denial, or successful containment. The functioning wrapper may still deny
   that one invocation.

The same resolver governs a native error during creation: complete COMMITTED
means the new operation exists and enters the post-durable path; exact ABSENT
means no operation was accepted; PARTIAL/UNAVAILABLE never become success.
A persistent native page-limit/FULL or I/O fault has no M1 liveness promise:
admission remains denied/observable until the substrate works. Physical GC,
migration, rotation, new database generations, Rescue, and custom VFS work
remain deferred because none is required for the M1 safety invariant.

## 5. Three implementation bodies — all NO-GO

### Body A — transactional store and control primitives

Owns all seven relations, nine triggers, authorizers, protocol operations,
three-phase transitions, merged effect/outcome/action/status
primitives, resolvers, profile/device/free-space checks, and transaction
closure. A owns the SQL extractor/hash/inventory harness, direct relational
negative fixtures, authorizer fixtures, fault injection, concurrency
scheduler, profile/ancestry probe, and free-space instrumentation.

A exposes typed DATA and authenticated CONTROL APIs. It does not route
events, decide admission, project hooks, install files, or run host jobs.
A alone owns drain locks, protocol transitions, adoption validation, and
containment semantics.

### Body B — registration, retry, admission, and status

Consumes only A APIs. Owns single-root parsing/canonicalization, episode
binding, merged durable-operation creation, executor/reboot/fairness behavior,
four-action replay, successor drive, B1/E@R1/B2/R2 admission, default-deny
Task handling, deterministic snapshot response rendering, and ADR 0020's redacted
component. B owns event corpus, action/replay model, eight-lane tick harness,
revision-race harness, reason matrix oracle, and product metrics.

B performs no lifecycle I/O before OPEN_EFFECT and cannot alter schema,
protocol edges, hook ownership, or live jobs.

### Body C — hook and installer sequencing

Owns hook-owner v4 projection, exact inventory/matcher proof, fail-open
serializers, launch ingress, DIRECT receipt, installer capability/lock,
old-entry disablement, drain/adoption sequencing through A's CONTROL API,
startup/tick packaging, compatibility, and throwaway install/repair/uninstall
fixtures. C owns hook seam simulators, inventory/projection differ, receipt
fixture, installer crash matrix, R0 predeployment evidence, and the Desktop
UAT script. C may prepare but cannot grant R1 canary GO or R2 rollout GO.

C never writes a relation directly and never defines state semantics.
It orchestrates drain calls but cannot implement a drain transition, member
adoption, or containment decision outside A. B owns no drain behavior.
External ownership is rejected before persistence and remains deferred. C
cannot change admission policy, ADR 0020 outbox, or delivery state.

Body C's installer order and crash cuts are normative:

| Cut | Last completed durable/file action | Deny-capable receiver | Idempotent restart action |
|---|---|---|---|
| C0 | R0 exact-head preflight only | old receiver | rerun R0; no file/protocol write |
| C1 | new receiver bytes + DIRECT receipt installed, hook unchanged | old receiver | verify new bytes/receipt, then continue |
| C2 | hook/projection atomically points to new DORMANT receiver | new receiver | verify projection receipt; old bytes remain fallback-disabled, not deleted |
| C3 | old entrypoints disabled after C2 receipt | new receiver | issue BEGIN_DRAIN or restore C2 projection; never re-enable unverified old entry |
| C4 | BEGIN_DRAIN committed | new draining receiver | resume exact drain tuple; pre-adoption failure may CANCEL_DRAIN to read-only |
| C5 | staged candidate/adoption prefix committed | new draining receiver | resume from audit/current tuple; after first adoption only advance or containment/repair |
| C6 | ADVANCE_GENERATION committed | new receiver | verify current protocol/projection, then clean old bytes |
| C7 | old bytes cleaned | new receiver | verify exact current bytes/receipt; no protocol replay |

Hook/projection writes use same-directory atomic replacement. No cut disables
the last deny-capable receiver. Each restart derives its action from current
file receipt plus protocol/audit authority, not a new journal. The exact-head
R0 crash matrix must kill/restart at C0–C7, including CANCEL and containment
branches, before the owner may issue R1 canary GO.

### C1 evidence-only boundary

C1 runs, captures, and adjudicates A/B/C-owned harnesses. It authors no
production helper, fixture framework, instrumentation, relation, trigger,
phase, or body. A harness without an A/B/C owner fails C0.

## 6. Acceptance ledger

| ID | Required exact evidence | Owner | API / fixture providers |
|---|---|---|---|
| A01 | Extract/execute exact SQL; assert 7 tables, 9 triggers, 0 views/indexes, enums/hash, and exact authored-vs-independent-observed leaf equality with one valid transaction per leaf | A | — |
| A02 | Closed JCS plus exact §4.1 preimage/order manifests, backlink exclusions, INSTALL ordering, byte-identical re-encoding, relational derivation, and prohibited-content corpus | A | B supplies product tuples |
| A03 | Exact domain/schema/encoding plus published profile/descriptor vectors; ordered `fstat`/`fstatfs`, ancestry/mode/link/NOFOLLOW/object-swap matrix, and bounded residuals | A | — |
| A04 | DB/WAL/SHM/proof/projection/legacy/root/Git targets share `st_dev` and APFS tuple; unavailable/mismatch denies before intent | A | B supplies root fixtures |
| A05 | Every write rechecks descriptor/APFS identity, revision, projected bytes, free space, effect reservations, and control suffix | A | — |
| A06 | Every invariant; total NULL corpus; independent predicate mutation-kill per changed guard; exhaustive T01 nullable/current/staged/first/drain carry; T03/T09 one-column carry matrix | A | B supplies expected transition rows |
| A07 | Append-only authorizer denies immutable mutation; named mutable statements only; actor string cannot obtain CONTROL | A | — |
| A08 | Only OPEN_EFFECT DATA appends FIRST_EFFECT; all other DATA protocol inserts fail; provenance pair persists separately from protocol hash | A | — |
| A09 | Direct OPEN races plus stale member/effect/status/executor rejection on OPEN/pre-I/O/APPEND/CLOSE/UNAVAILABLE; no pre-authority lifecycle | A | B supplies interleavings |
| A10 | Exactly three phases; REQUESTED invalidation and INSTALL backlink closure are exact audit/effect/status/member transactions | A | B supplies basis/install fixtures |
| A11 | Four-action replay/ack loss; same-effect help; native/adopted REACQUIRE; lost-ack ALREADY_APPLIED; hostile generation/multi-hop mismatch rejection; four-way reacquire resolver | B | A supplies typed APIs/fault fixtures |
| A12 | SUCCESS/conflict/SUPERSEDED closures are disjoint/reachable; SUPERSEDED needs no executor/archive; close counter carry/reset semantics are exact | A | B supplies transition scenarios |
| A13 | RESOLVED conditional handoff/no-op plus APPLIED/ABSENT/OBSOLETE/UNAVAILABLE resolution from audit/current state | B | A supplies resolver API |
| A14 | One `member_epoch` owns identity, pending/current state, CAS, status, and handoff | A | B supplies lifecycle fixtures |
| A15 | DRAINING boot mismatch requires fresh non-NULL unequal sample and no old monotonic comparison | A | C supplies installer sequence |
| A16 | Pre-adoption atomic STAGE_NEXT replacement/CANCEL clearing, post-adoption rejection, schema equality, `storage_dev`, requested-effect drain/advance rejection, and reserve path | A | C supplies control sequencing |
| A17 | Pre-effect DORMANT proof passes only before OPEN_EFFECT; every other rollback contains | A | C supplies installer sequence |
| A18 | Old-boot executor clear, same-boot takeover proof, and one-column-exact REQUESTED/IN_FLIGHT/RESOLVED reboot targets with immediate zero-backoff fields | B | A supplies status API |
| A19 | >8 members, deterministic continuation, coordinator miss/yield commit, failed-schedule-write suspension, selected-only RED, and no all-members-one-tick claim | B | — |
| A20 | Member-isolated B1/E@R1/B2/R2 race matrix and invocation-start semantics | B | A supplies snapshot reader |
| A21 | Task/subagent default-deny across every installed ingress; unreceivable launch refuses activation | C | B supplies policy oracle |
| A22 | Exact DIRECT receipt domain/schema/vectors; R1 owner/candidate/root/member scope and other-root denial; R2 broadening; inventory/projection/catch-all or enumeration | C | — |
| A23 | Every seam/failure proves fail-open truth; unavailable containment never claims denial | C | A supplies store failures |
| A24 | One status row/member and one read-only aggregate READY snapshot over full live envelope | B | A supplies authoritative tuples |
| A25 | Deterministic reason-specific rendering from snapshot; no notice operation/state/FULL/COMPACT/repeat history | B | C supplies serializer fixtures |
| A26 | Dirty/in-progress source/index/refs/operation bytes remain unchanged and no unchanged-basis timer exists | B | — |
| A27 | Five-second drain, old-entry disablement, requested-effect resolution, single-hop adoption, no-pending reserve retention, advance-or-containment | A | C supplies sequencing |
| A28 | Four-way close/successor/reacquire resolvers under crash, busy, I/O, ENOSPC, lock, reboot, and concurrency | A | B/C supply scenario fixtures |
| A29 | ADR 0020 alone owns alerts; guard/finish/cleanup/kernel-off remain independent and compatible | C | B supplies product-state fixtures |
| A32 | Low-free zero-write recovery; native FULL/IOERR exact resolution; commit-only containment and honest unavailable result | A | B/C supply call-site fixtures |

C1 executes and adjudicates every ledger row; it is intentionally absent
from owner/provider columns.

Governance-only checks sit outside the implementation harness ledger:

- **G01:** verify every A-row has exactly one owner, providers expose only
  APIs/fixtures, and C1 owns no instrumentation.
- **G02:** bind final whole-file hashes plus the normalized acceptance-body
  digest; obtain fresh review/verifier results and separate owner acceptance.
- **G03:** test all four exact old→new status-token substitutions, allowed
  post-hash computation before owner acceptance, exact path order/u64be/LF/
  sentinel/domain framing, the complete negative corpus, atomic promotion,
  unchanged normalized digest, detached pre/post receipt, and
  post-promotion freeze.

## 7. Exact-hash finding dispositions

These are authored design closures, not independent review clearance.

### 7.1 Final review findings

| ID | Disposition in this draft |
|---|---|
| F01 | RESOLVED handoff requires pending work, proven basis/closure change, or explicit conflict retry; unchanged SUCCESS is a zero-write event/startup/tick/retry no-op (§4.10; A13) |
| F02 | Member history is unbounded by row count; batch/lanes remain eight with deterministic existing-state continuation, selected-only RED, and no all-members-one-tick claim (§4.13; A19) |
| F03 | OPEN/pre-I/O/APPEND/CLOSE/UNAVAILABLE carries and atomically checks the expected executor token plus old status hash; UNAVAILABLE appends no action and only exact REACQUIRE reauthorizes the same effect (§4.7, §4.9; A09/A11/A18) |
| F04 | Durable CONTAINMENT and uncommitted containment-unavailable are distinct; the latter makes no denial claim and uses independent host RED (§4.8, §4.12) |
| F05 | Every persisted/preidentity reason has exact entrypoint, authority, action, recovery (§4.14; A25) |
| F06 | Preidentity is fixed/stateless; identified responses render deterministically from the read-only snapshot with no presentation state (§4.1, §4.13; A24/A25) |
| F07 | OPEN_EFFECT uses transaction-fresh current-boot continuous time (§4.9; T09; A09) |
| F08 | FIRST_EFFECT id and operation id are paired and copied forever (§4.8; T01; A08) |
| F09 | Drain boot mismatch requires non-NULL transaction-fresh samples and boot inequality before containment, with no old monotonic compare (§4.8; T01; A15) |
| F10 | Adoption binds old DRAINING+staged epoch and exact active-effect lineage, replaces pending intent when present, enables only lineage-proven later reacquire, and forbids later stage replacement/cancel (§4.8; T01/T03/T05/T09; A11/A14/A16) |
| F11 | REBOOT_STATUS clears an executor only on transaction-fresh old-boot proof; same-boot death uses exact MARK_UNAVAILABLE CAS then REACQUIRE; RESOLVED pending/no-pending behavior remains exact (§4.13; T09; A18) |
| F12 | Durable notice state is absent; one member status row and the aggregate snapshot select deterministic reason-specific output (§4.3–§4.4, §4.13; A24/A25) |
| F13 | Member basis is physical/Git/policy/operation/lifecycle only (§4.1; A04) |
| F14 | Exact B1/E@R1/B2/R2 fence uses protocol plus selected member/status/effect tuple hashes, so unrelated-member commits do not deny; invalidation stays REQUESTED without pre-authority state (§4.6, §4.11; A10/A20) |
| F15 | Successor operation id and four-way acknowledgement are deterministic from immutable audit plus current state (§4.10; A13) |
| F16 | Conflict closure is reachable after any ordinal and outcome-sensitive (§4.9; T06; A12) |
| F17 | Trigger-critical facts are relational; hash preimages are explicitly enumerated and operation backlinks are excluded/bound separately (§4.1, §4.4; A02/A06) |
| F18 | Status subject is deterministic/non-null, competing status rows are rejected under the serialized insert, and green shape is exact (§4.13; A24) |
| F19 | Adoption envelope authenticates old current+DRAINING and immutable staged epoch (§4.7–§4.8; A16) |
| F20 | Pre-effect DRAINING→DORMANT has exact absence proof; otherwise containment (§4.8; A17) |
| F21 | Single-device DB/proof/projection/legacy/root/Git profile and per-write preflight are normative; ADVANCE_GENERATION preserves prior `storage_dev` (§4.2, §4.8; A04/A05/A16) |
| F22 | Merged effect identity/intent is immutable; outcome mutates once irreversibly (§4.1, T06; A12) |
| F23 | FIRST_EFFECT is the sole exact OPEN_EFFECT DATA protocol exception (§4.7; A08) |
| F24 | Every rejecting trigger uses complete predicate `IS NOT TRUE`; T03/T09 explicitly carry every branch-unowned column; generated one-column mutations and total nullable composites reject (§4.4–§4.5; A06) |
| F25 | STAGE_NEXT replacement and CANCEL_DRAIN clearing are atomic and pre-adoption only; any committed adoption/current staged-generation reference forbids both (§4.8; A16) |
| F26 | Fresh free-space admission materializes every effect/control reservation; no-pending adoption retains the active-effect reservation; suffix writes charge their own reserve and native failure cannot manufacture a receipt (§4.15; A05/A16/A27/A32) |
| F27 | Staged schema equals current canonical digest; schema change requires superseding migration (§4.4, §4.8; A01/A16) |
| F28 | Drain fields are exactly both null/non-null by mode and operation provenance is retained (§4.4 T01; A15–A17) |
| F29 | Canonical DDL enumerates every column/type/null/key/FK/CHECK/trigger predicate; 7-table/9-trigger inventory and generated 97-leaf manifest are executable/hash-checked (§4.3–§4.4; A01) |
| F30 | Every claimed seam and failure has explicit fail-open behavior (§4.12; A23) |
| F31 | Inventory/projection hashes and catch-all/enumerated activation are exact (§4.12; A22) |
| F32 | CONTROL is installer-authenticated; actor text has no authority (§4.7; A07) |
| F33 | External ownership default-denies before persistence; protocol rows are DIRECT-only and no external dormant branch/reason/message or receipt infrastructure exists (§4.8, §4.12; A22) |
| F34 | APFS/profile receipt has a closed domain-separated preimage, descriptor-bound `fstat`/`fstatfs` order, normalized fsid/flags, and bounded non-claims (§4.2; A03) |
| F35 | Persisted blobs have closed JCS schemas, relational derivation, byte-equal re-encoding, no raw paths, and exhaustive prohibited-content mutation corpus (§4.1; A02) |
| F36 | Secure absolute ancestry and stock SQLite path residual are explicit (§4.2; A03) |
| F37 | Task/subagent handling defaults to deny and precedes ordinary admission (§4.11; A21) |
| F38 | Same-UID raw SQLite is unsupported, not non-forgeable; observed drift is RED (§4.2, §4.7; A03/A07) |
| F39 | Closed world exposes object, generated trigger-leaf, phase, mode, transition/reason, request/outcome, action/observation/conflict, successor-cause, transaction/operation, runtime-reason, predeployment, rollout-gate, and body counts (§3.2, §4.3; A01/A06/A25/G01) |
| F40 | Proof is outcome; membership, alert, and current-pointer relations are absent (§4.3; A01/A29) |
| F41 | One authorizer immutability boundary covers all immutable relations; no special protocol update/delete triggers (§4.4–§4.7; A07) |
| F42 | Every harness has exactly one A/B/C owner; other bodies are API/fixture providers; governance checks are outside the ledger and C1 only executes/captures/adjudicates (§5–§6; G01) |
| F43 | One read-only aggregate snapshot is READY only for the full live host/profile/projection/storage/parser/serializer/protocol/member envelope (§4.13; A24) |
| F44 | Stale counts/section references are removed; this map uses current IDs only (§3.1; G02 whole-document governance check) |
| F45 | Synthetic row/store ceilings and terminal capacity machinery are absent; fresh FREE_BYTES refusal is zero-write and self-clearing, while native FULL/IOERR resolves exact commit/absence/partial/unavailable before containment-or-observable-unavailability (§4.15; A32) |
| F46 | `member_epoch` is the sole member revision across identity, pending/current state, CAS, status, and handoff; no parallel revision counter remains (§4.1, §4.4; A14) |
| F47 | R0 is predeployment evidence; C0, implementation GO, explicit R1 canary GO, C1, and explicit R2 rollout GO remain distinct (§3.2; G02) |
| F48 | The duplicate archive relation/trigger/blob are removed after equivalence checking; immutable audit plus participating state rows preserve transition, ambiguity, corruption, and containment truth (§4.3–§4.10; A10/A12/A13/A28) |
| F49 | Promotion normalizes only four exact old/new status-token byte spans; any date/non-token mutation rejects, and detached pre/post hashes avoid self-reference (§3.3; G02/G03) |
| F50 | `KleinPerkins` (Laurence Duggan) is the sole owner authority; C0 technical clearance precedes checker post-hash computation, conditional owner acceptance, atomic promotion/freeze, implementation GO, R1, C1, and R2 (§3.1–§3.3; G02/G03) |
| F51 | OPEN_EFFECT directly CASes the due REQUESTED member/effect/status tuple into one executor; no durable pre-authority operation or field remains (§4.6–§4.9; A09) |
| F52 | BEGIN_DRAIN/ADVANCE reject clean REQUESTED effects, and BEGIN_DRAIN rejects an in-flight required-generation mismatch, forcing closure before another generation (§4.8; A16/A27) |
| F53 | Successor effect member/epoch/basis/tuple and exact pending selection are relationally bound in T03/T05/T06 (§4.4–§4.10; A10/A12/A13) |
| F54 | INSTALL_MEMBER binds initial member tuple and write backlinks to one audit envelope and closure SELECT (§4.4, §4.7; A01/A10) |
| F55 | Close carries unavailable/yield counters for pending SUCCESS and both conflicts; only idle SUCCESS zeros them (§4.5; A06/A12) |

### 7.2 Protected-verifier candidates

| Exact candidate | Disposition |
|---|---|
| `protocol-transition-drain-fence-integrity` | **Open on reviewed predecessor; corrected here.** T01/table predicates now enforce total mode/drain shape, explicit null/null on every DRAINING exit, total `IS` carry for ACTIVATE/FIRST_EFFECT, and fresh boot/deadline proof for every positive DRAINING leaf (§4.4–§4.8; A06/A15–A17). |
| `post-commit-executor-takeover-authority` | **Verified on reviewed predecessor; source predicates unchanged.** Committed target-tuple authority, in-memory executor transfer, process-scoped takeover, and same-UID residual remain (§4.7–§4.9; A09/A11/A18). |
| `c0-verifier-evidence-matrix-integrity` | **Verified on reviewed predecessor; source predicates unchanged.** Exact candidate/coverage/blind-probe/revision/blocker matrix and narrow partial-rollout exception remain (§3.1; G02). |
| `independent-leaf-mutation-coverage` | **Open on reviewed predecessor; corrected here.** Independent T01 cases now include one valid transaction for every initialize/carry/clear leaf plus boot-only, deadline-only, failed-boot-clear, failed-deadline-clear, NULL/UNKNOWN, and changed-predicate kills (§4.3–§4.5; A01/A06). |
| `r1-canary-scope-admission-authority` | **Verified on reviewed predecessor; source predicates unchanged.** Owner receipt/candidate/root/member scope, other-root denial, and R2 broadening remain (§3.2, §4.11–§4.12; A20/A22). |
| `installer-cutover-crash-continuity` | **Verified on reviewed predecessor; source predicates unchanged.** C0–C7 order, deny-capable receivers, idempotent restart, and R0 crash matrix remain (§5 Body C; A22/A23/A27). |

All six authored design dispositions remain formally open until a fresh
schema-valid verifier independently resolves them against the final ADR/plan
hashes. This draft asserts closures only; the fresh scoped re-review and
verifier determine whether any substantive design blocker remains.

P2 closure evidence remains separately blocking if any fixture is unresolved:
P2-02 structural fresh-sample/no-op (A10/A13), P2-03 helper generation
(A10/A14), P2-04 adoption pending basis (A11/A16), P2-06 canonical receipts
(A03/A22), P2-08 selected-miss fairness (A19), P2-09 reboot targets (A18),
P2-10 adoption lost-ack/single-hop (A11/A27), and P2-16 ambiguous reacquire
(A11/A28). All must be green before verifier dispatch.

## 8. Non-goals and unsupported residuals

The exact nine non-goals are: (1) dirty-work preservation; (2) multi-root
membership; (3) Task/subagent entry; (4) physical data retirement/GC,
migration, or database rotation/new generations;
(5) Rescue; (6) production custom VFS; (7) broader platforms;
(8) external activation; and (9) stronger same-user defense. None is an M1
hidden branch or reserved object.

Retained residuals are total hook/runtime/host absence; no-event and broken-
wrapper fail-open surfaces; local read before read-hook model admission;
manual/Tab/external/cloud-early/already-running work; same-user replacement
or raw SQLite bypass; unsupported platform/device/VFS/power behavior;
notification visibility; and no automatic dirty-work progress.

## 9. Current owner gate

ADR 0025 and v3 remain DRAFT. C0-DESIGN is UNSATISFIED and implementation is
NO-GO. Fresh exact-hash review and resolved verifier adjudication remain C0
evidence blockers. Missing
implementation/model/fault/UAT evidence is not a C0 blocker; it keeps C1
unsatisfied. After C0 technical clearance and exact owner-authorized
promotion/freeze, a later qualifying implementation
instruction must name the exact accepted plan, refreshed implementation
baseline, and C0 evidence. Generic approval, document acceptance, a PR
comment, or green checks is not implementation GO. Implementation GO is not
R1 canary GO; R1 canary GO is not C1 clearance; C1 clearance is not R2
rollout GO. No such authorization is recorded here.

Until then leave source, contracts, tests, runtime, hooks, jobs, state,
PR #175, GitHub metadata, releases, installation, Skills, host wiring,
accepted ADRs, frozen v1, and superseded v2 unchanged.
