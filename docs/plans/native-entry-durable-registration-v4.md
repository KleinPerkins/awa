# Native Entry Durable Registration

- **Version:** v4
- **Status:** ACCEPTED — FROZEN — GOVERNANCE ONLY; IMPLEMENTATION AND R0 NO-GO
- **Date:** 2026-09-29
- **Supersedes if accepted:** accepted, frozen
  [`native-entry-durable-registration-v3.md`](native-entry-durable-registration-v3.md).
  While this plan is draft, v3 remains current implementation authority and
  remains byte-identical.
- **Architecture authority:** draft
  [ADR 0026](../adr/0026-durable-registration-authority-hardening.md). While
  ADR 0026 is draft, accepted
  [ADR 0025](../adr/0025-durable-registration-episodes-and-tool-admission.md)
  remains current.
- **Implementation subject:** PR #178 merge
  `8356a60cb30ea02953149f9bea61fd1c04f2c7de`, tree-equal to implementation
  head `b853a6bdb59d73d03c1410108830fb6a6c4bcf51`.
- **Review provenance:** schema-valid final full-change Deep-band
  swarm/verifier at `b853a6bd`; shipping clearance failed with
  `partial_rollout=true`; exactly twelve unique P1 and six unique P2 blockers;
  Bugbot independently confirmed staged-receipt/current-generation cutover
  failure; separate Security Review reported no medium-or-higher findings but
  is contradicted on the listed paths by verifier source traces. Subsequent
  cleanup authorization adds exactly two P3 checker corrections and no other
  scope.
- **Closed-world budget:** canonical SQL v2 retains exactly seven tables,
  nine triggers, ninety-seven independently generated leaf keys, three member
  phases, four protocol modes, three effect outcomes, three transaction
  classes, twenty-four operation kinds, twenty-six runtime reasons, one
  predeployment evidence stage, two rollout authorization stages, and three
  implementation bodies.
- **Canonical SQL v2:** SHA-256
  `b97f02ef67d48886f917368fa420fda0c5dd5942441b23a190732e3cc45106c8`,
  derived by the byte-exact §4.1 convention from frozen SQL v1 SHA-256
  `221aaf6680b50ca8f6c8c2cf024acbedbf5273b90c8c5625bcc4100c448d5ede`.

**Goal:** correct the smallest set of proven authority, cutover, recovery,
parser, and evidence defects in the merged ADR 0025 implementation without
adding product scope or persistent machinery.

> **Governance stop:** this draft authorizes documentation only. Do not edit
> code/tests/contracts, run R0, commit, push, open or modify a PR, install,
> release, activate, or roll out. ADR 0026 and this plan must first receive
> fresh exact-byte technical clearance and explicit owner acceptance. A later
> exact-baseline implementation GO is separately mandatory.

---

## 1. Purpose, baseline, and inherited authority

### 1.1 Verified baseline

Read-only verification on 2026-09-29 established:

| Surface | Exact state |
|---|---|
| Live remote `main` | `8356a60cb30ea02953149f9bea61fd1c04f2c7de` |
| PR #178 | Merged; source head `b853a6bdb59d73d03c1410108830fb6a6c4bcf51`; merge commit above |
| Tree equality | Merge and source-head trees are equal |
| Documentation branch | `docs/adr-0026-registration-authority-hardening-v4`, created locally from the exact merge |
| Worktree | Linked, clean before documentation mutation; no index lock or competing session lock |
| Identity/hooks | `KleinPerkins <49759187+KleinPerkins@users.noreply.github.com>`; executable managed pre-commit chain |
| Offline signer prerequisite | Stock `/usr/bin/ssh-keygen` exists and exposes `-Y sign` / `-Y verify`; no key or signer contract is enrolled |
| R0/R1/C1/R2 | No qualifying v4 evidence or authorization exists |

Protected authorities matched:

```text
ADR 0020  f0911b0a85e85b6dc1d616fa6f092d33f9002e9c8d9bc5bf2edda4a927a95a98
ADR 0023  71476602db37828c80503f05790a57aa587572cef1e800cfa42b2d32e86a0051
ADR 0024  cecca6d380d446b91af00a4e5aea44282c4b9633b518a638967fcbeb4de38911
ADR 0025  dabac24ccb8097888a485ef55fd9a5b83eaa1ec87976387f8ba7f834e3a8ea1f
frozen v1 e3bf9182e4e16411ab1424123a7200b3f6ec0dd4e09429237256a5601dcb6bd9
draft v2  03aff346283c2809d9bab392120972de97bd14b5879e01448a8af734becf8b9b
frozen v3 d5b03f0364a77ccd8877d88dacb0e52683e8407ba014b0e3adc89cbf22276ab8
```

The Deep-band review subject immediately preceding this hardening was:

```text
ADR 0026   1a1fde7bb584a62c1bddb0b937230fb2001894ca0365742ebd4a1d5bc6980820
v4 plan    f877c320cf90c5e85023506fe5f800f343c935cf3f0b977fab53a21866acaf19
ADR index  dc337753314b8c8c2336618929868b664645c0a8ffe6523ecd79393cc73529d1
plan index 5102084d7331c407f1345be5ff1c57176752201d54f7169cd8c4ffa763d15c7d
```

### 1.2 Preserved contract

V4 preserves without reinterpretation:

- single-root, clean, local linked non-primary M1;
- canonical SQL v2's exact seven-table/nine-trigger schema and unchanged
  ninety-seven-key independent leaf manifest;
- `REQUESTED -> EFFECT_IN_FLIGHT -> RESOLVED`;
- `DORMANT | WRITABLE | DRAINING | CONTAINMENT`;
- `SUCCESS | LOGICAL_CONFLICT | SUPERSEDED`;
- `BOOTSTRAP | DATA | CONTROL`;
- all twenty-four operation kinds and twenty-six runtime reasons;
- `member_epoch` as the sole member revision;
- protocol lock → one member lock → short `BEGIN IMMEDIATE`;
- direct OPEN authority, immutable audit, stateless rendering, member-isolated
  admission, and default-deny Task/subagent handling;
- ADR 0020 as the only integrity/alert/outbox authority;
- independent shell guard, finish, active-root, cleanup, and ADR 0020 repair
  authority; and
- v3's explicit unsupported residuals and nine non-goals.

No new relation, trigger, leaf key, phase, protocol mode, effect outcome,
transaction class, operation kind, runtime reason, rollout stage, or
implementation body is reserved. Any implementation that needs one stops for
a superseding governance decision.

## 2. Concise counterexamples

| Counterexample | Current result | Required v4 result |
|---|---|---|
| Owner says “accept” without exact checker/source/recovery/envelope bytes | Draft bytes, recovery baseline, post state, or promotion durability can change between review and receipt | Embedded hash-checked launcher/checker, exact source, immutable recovery packet, semantic owner envelope, descriptor-safe status-last promotion, four-POST proof, and canonical detached receipt |
| Implementation GO is treated as delivery/release/install permission | One approval silently expands consequences | Every authority is separately named and exact-revision; no gate implies another |
| Recovery cycle four occurs in ordinary runtime | Runtime lacks installer CONTROL yet prose claims containment | Zero-write typed exhaustion; honest unavailable/ADR 0020 RED; only authenticated installer adapter may attempt containment |
| Adopted executor fails while protocol remains DRAINING | Blanket deny conflicts with required MARK/REACQUIRE/helper recovery | External interfaces deny; activated member-lock/closure-bound internal frozen recovery only |
| N+1 installation overwrites N receipt/config or hashes omit interpreter/preimages | Old receiver cannot restore and authority is guessed | Exact generation bundle/import/projection/interpreter schemas and vectors; one pointer; N retained through C7 |
| One sampled denial is green | Another installed event/server/serializer seam can fail open | Sorted direct+shadow proof records for every unique observable tuple/seam |
| Manifest omits an imported package initializer | Unmeasured code loads before authority check | Generator-owned transitive path manifest, package initializers, pre-import/runtime enforcement |
| Product hard-codes or PATH-resolves Python | Candidate can select an interpreter below SQLite/API requirements or drift after signature | Authorized explicit absolute path, pre-gate descriptor/capability probe, signed full record, and pre-import remeasurement |
| Same discriminator appears on two MCP servers with different roles | Discriminator-only lookup selects wrong policy | Unique observable key; signed role returned as policy; conflicting duplicate refused |
| R0 signs before creating/measuring the full fixture | Signed gate does not bind actual throwaway targets | Prepare and descriptor-measure complete fixture, emit/sign gate, then remeasure before seal/use |
| C3 switches pointer and probe fails | Old bundle exists but is no longer selected | Keep N enabled/restorable, post-switch prove, atomically restore/revalidate N before legal CANCEL |
| C5 tracks ADOPT kind only | Committed staged REACQUIRE custody can be omitted | Track every resulting staged-generation grant; exact return/activation/clear closure; DRAINING OPEN forbidden |
| Same-boot low IDs remain busy across ticks | Repeated restart can starve later IDs or R1 can mutate out of scope | Host-tick non-authoritative cursor advances busy IDs, wraps, continues >8; one R1 preflight checks same-boot/due/reboot |
| R0 observes only its throwaway path | It claims global no-live-change without evidence | Freeze finite governed live-surface manifests, compare exact before/after, bind external write observations |
| A governed file has exact bytes but mode `0600` | Hash-only classification treats a mode-divergent file as PRE/POST authority | Every packet, promotion, recovery, displaced-target, terminal, and receipt-context proof requires the packet-bound `0644` backing mode |
| A same-euid peer substitutes a candidate or classified residue name, including after pair validation but before unlink, or mutates a file during fsync finalization | A path precheck or stale snapshot can bless or unlink a different inode/content while the classified residue survives elsewhere | Hold and identify candidates across rename and classified residue across retirement; immediately rebind the held residue to its visible name before unlink, fsync the parent, require that exact held inode's link count to become zero, then revalidate target and residue absence; reread/re-fstat/recheck visible entries after file and parent fsync; retain a deterministic classified pair on uncertainty |
| A receipt retry supplies a mismatched owner or sees later unrelated index rows | Durability fsync can mutate state before authorization, while rebuilding from live backing bytes changes the owner envelope and makes a valid completed promotion non-idempotent | Non-mutatingly inspect and validate the exact existing canonical receipt first; reconstruct its original envelope/vector and validate supplied owner bytes/digest before any fsync; only then finalize durability and repeat held receipt, four-POST, and residue checks, while tolerating only outside-row index additions |
| Residue validation, unlink, fsync, or durability fails and descriptor close also fails | An unconditional `finally` close can replace the primary failure and falsify the observed cause | Attempt every owned close; re-raise the exact primary with the close error only as secondary context, while surfacing a lone close failure |
| A descriptor helper opens one or two descriptors and setup then fails | An acquired-but-untransferred descriptor can leak, or closing one descriptor can prevent cleanup of another | Ownership begins immediately after each successful open; all untransferred descriptors receive exactly one close attempt, close failures cannot mask setup failures, and return is the sole ownership transfer |

The six P2 counterexamples remain independently biting: boolean-as-integer;
deep JSON recursion; parent/process-held fairness collapse; later-state
resolver amnesia; duplicate/stale observation races; and underdefined
authority preimages plus post-rename publication uncertainty/residue.
The two authorized P3 cleanup findings remain separately binding:
exception-preserving residue cleanup and immediate descriptor ownership on
failure.

## 3. Complete finding-to-decision map

Every row has one owning body. Other bodies may supply only typed APIs,
fixtures, or call sites.

| ID | Finding and source evidence | V4 decision | Owner | Acceptance evidence | Stop condition |
|---|---|---|---|---|---|
| P1-01 | ADR/plan acceptance lacks v3-grade exact-byte authority | Bind four ordered surfaces to one sentinel-normalized digest; hash-check the embedded launcher/checker; bind exact source, original recovery vector, hashes plus canonical modes, Gate 2A evidence, narrow scope, and receipt path in one semantic owner envelope; descriptor-held status-last promotion emits a canonical receipt only after four POST contexts/modes; identity-bound retirement proves the classified residue inode reached zero links; and an existing receipt reconstructs its original envelope and validates owner input before any durability fsync or live rebaseline | C | Packet determinism; malformed owner/recovery/receipt matrices; source/path/symlink/race/umask/fsync/mode faults; candidate-substitution and post-pair-validation residue-substitution matrix; PRE/mixed receipt denial; four-cut reverse recovery; zero-fsync malformed/mismatched-owner retry; exact-existing-receipt finalize/revalidation after outside-row additions | Checker bytes are invented later, recovery rebaselines, a substituted residue can be retired as clean, receipt exists without four POST contexts/modes/durability, owner refusal follows a durability side effect, any authority field is absent, any non-token byte or canonical mode can change, or partial promotion becomes authority |
| P1-02 | Implementation, delivery, R0, release, install, Skills, host, R1, C1, and R2 authority can be conflated | Name each exact-revision gate separately; reviewer App alone approves/arms/merges | C | Gate-cross-product denies every missing/wrong revision/authority and agent auto-merge attempt | Any gate implies another or agent can arm/merge |
| P1-03 | Persisted semantic closure and raw reservation sums are insufficient | Validate exact direct companions/backlinks; charge every unvalidated outstanding effect at SQL maxima | A | One-field companion mutation plus corrupt-low reservation vectors never reduce free-space or authorize | Any corrupt row lowers required bytes or reaches admission/I/O/CONTROL/resolution |
| P1-04 | DRAINING cannot use existing MARK/REACQUIRE for an adopted staged executor | Canonical SQL v2 adds exact staged-lineage predicates inside existing DATA operations/leaves | A | Extract/execute/hash SQL v2; WRITABLE/DRAINING positive vectors; every staged predicate kill | DRAINING recovery works without exact lineage or any other DATA kind works in DRAINING |
| P1-05 | Recovery has no finite reserve/exhaustion CONTROL boundary and transfer can strand staged custody | Reserve three cycles; typed zero-write exhaustion; runtime reports existing unavailable/ADR 0020 RED; only already-authenticated installer adapter may attempt existing containment; bounded two-ack transfer | A | Floors/cycles; runtime/actor/forged-result CONTROL denial; adapter hash recheck; lost/dead/duplicate ack matrix | Runtime constructs CONTROL, exhaustion claims containment, fourth cycle commits, or transfer permits pre-ACTIVATED I/O |
| P1-06 | N+1 files/receipt can overwrite N; one denial hash and blanket deny language contradict internal staged recovery | Immutable generation bundles; complete proof vector; external interfaces deny-only while installer-internal lock/closure/ACTIVATED recovery may use exact DRAINING operations/frozen helpers | C | Multi-generation identity, full proof set, external deny matrix, internal custody/helper positives and pre-ACTIVATED negatives | N authority changes early, external allow occurs, or internal helper I/O precedes activated lock+closure |
| P1-07 | Ambient import, fixed/PATH interpreter selection, and discriminator-only inventory can select unsupported code/policy | Authorized explicit absolute interpreter path with pre-gate descriptor/capability probe and pre-import remeasurement; transitive manifest; unique observable key returns signed role | C | Supported fixture; rejected system shape; PATH/substitution/symlink/owner/mode/inode/content/probe/API/SQLite-floor/upgrade vectors; import and cross-server policy corpus | Unmeasured/unsupported interpreter or AWA byte executes, drift falls back, or observable selects another role |
| P1-08 | R0 signs before complete fixture measurement and owner signing is callback-only | Prepare/measure full fixture first; OpenSSH ssh-ed25519 detached signing with exact allowed-signers/key-enrollment contract; remeasure before seal/use | C | Real stock `ssh-keygen -Y` positive fixture plus wrong principal/namespace/key/path/hash/LF/revocation vectors | Receipt/protocol/CONTROL precedes verified signature+remeasurement or arbitrary callback authorizes |
| P1-09 | Cut C1–C3 switch can strand receiver and old bundle may be removed too soon | Install N+1 separately, prove while N active, switch pointer with N restorable, post-switch prove, restore/revalidate N before legal CANCEL, retain through cut C7 | C | Kill/fail at every pointer/proof/restore/disable boundary with one verified denial path | Old entry is disabled before post-switch proof or N cannot be restored through cut C6 |
| P1-10 | C5 completion omits staged-generation REACQUIRE grants | Define custody by resulting staged executor generation, covering ADOPT and DRAINING REACQUIRE; exact audit/status/token close; DRAINING OPEN forbidden | C | Commit-before-return kill for both operations; >8 continuation; ADVANCE denial per unresolved grant; stable-row exclusions | Any staged-generation grant is omitted or ADVANCE commits with unresolved custody |
| P1-11 | Same-boot selector lacks restart-stable cursor and R1 scope completeness | Existing host-tick v2 carries non-authoritative protocol/status-bound cursor with busy advancement/wrap; direct recovery for event/startup/retry; R1 preflight adds same-boot flag | B | Missing/stale/current cursor, wrap, low busy IDs, >8 progress, all three outside-scope flags before zero mutation | Cursor authorizes, low IDs starve, restart loses progress indefinitely, or R1 mutates with any outside flag |
| P1-12 | R0 overclaims global no-live-change and C0–C7/process continuity | Freeze finite governed live-surface manifests, bind descriptor-safe before/after/external-write evidence to real process-kill cut records | C | Every cut/subcut with actual process death, complete finite surface diff, path-escape and missing-observer failures | R0 claims unobserved absence, a governed surface changes, or write escapes throwaway root |
| P2-01 | Python booleans satisfy integer validators | Require `type(value) is int` for every integer authority/hash input | A | `True`/`False` at every integer field rejects before hash/SQL | Boolean and integer share accepted authority |
| P2-02 | Deep JSON can raise uncaught recursion/memory failure | Bounded iterative pre-scan and bounded deny serialization | B | Depth 0/16/17/1,000, wide, duplicate, truncated, recursion/memory vectors | Functioning wrapper exits without seam-valid denial |
| P2-03 | Fairness lanes can collapse around parent/process-held member authority | Parent passes serializable descriptors only; each worker opens exactly one service/member lock | B | Eight blocked workers overlap; ninth continues; no residual worker/lock | Parent transfers capability or lanes serialize behind one process lock |
| P2-04 | Later valid state makes a committed operation look absent | Immutable semantically valid operation remains commit witness; later current write yields existing COMMITTED/OBSOLETE class | A | Commit→later-state→retry for every resolver | Committed operation returns ABSENT solely because state advanced |
| P2-05 | Duplicate ensure and stale pre-lock observations can fail/regress | Unique conflict resolves exact closure no-op; resample under member lock before mutation | B | 2/8/32-process duplicate races and old/new observation barriers in both orders | Exact duplicate errors or older observation supersedes newer basis |
| P2-06 | Publication semantics and new bundle/import/pointer/signing/tick/R0 hash preimages are underdefined | Exact closed schema/domain/JCS/path/order/nullability registry and fixed vectors; descriptor-relative no-follow publication; candidate descriptor remains open and identity-bound across `fchmod`/fsync/swap or exclusive rename; classified residue descriptor remains held through unlink and proves that exact inode reached zero links; retry rereads/re-fstats after file+parent fsync; deterministic target/residue pairs preserve primary failure; receipt-first retry validates canonical receipt/current POST/residue plus supplied owner before durability finalization and never rebases completed authority | C | Mechanical recomputation of every §4.2.1 vector plus mode/substitution/stale-snapshot/deterministic-pair/write/file-fsync/dir-fsync/swap/rename/reopen/symlink/race/cleanup faults, including residue substitution immediately after pair validation and zero-fsync malformed/mismatched-owner retries | Any authority hash needs caller guess/placeholder, interpreter treatment conflicts, canonical mode or held identity is skipped, a stale snapshot is finalized, unknown/substituted residue is reused or reported clean, unauthorized retry causes a durability side effect, or post-rename failure overclaims durability |
| P3-01 | `close-masks-primary-retirement-error` (D11): `retire_known_residue` closes its held descriptor unconditionally, so close failure can replace validation/unlink/fsync/durability failure | One exception-preserving descriptor cleanup primitive attempts every owned close, re-raises the exact active primary with close failure only as secondary context, and raises close failure when it is the sole failure | C | Inject primary failure at every retirement stage plus descriptor-close failure; assert exact primary identity, secondary close context, all cleanup attempts, no receipt, and no success; inject lone close failure and assert it surfaces | Any cleanup failure replaces the primary, any owned close is skipped, or a lone close failure is suppressed |
| P3-02 | `descriptor-ownership-gap-on-failure` (D01): descriptor-producing helpers perform fallible setup before ownership guards | Immediate ownership after every successful open in `open_repo_descriptor`, `swap_known_pair`, `open_state_parent`, and `acquire_lock`; helper-local `open_regular`, anchor, and absolute-walk cleanup is repaired only where mechanically required; return is the sole transfer | C | Instrument open/close/fstat/`checked_directory`/fchmod/file fsync/parent fsync/flock/path rebind and fail each named point; prove every acquired-but-untransferred descriptor receives exactly one close attempt, transferred descriptors are not double-closed, primary errors survive cleanup failure, and no receipt/success occurs | Any acquired descriptor leaks or is double-closed, a close masks setup failure, ownership transfers before return, or any failing path reports success |

Security Review's clean result is recorded alongside this table, not used to
reduce or outvote it.

## 4. Revised architecture

### 4.1 Canonical SQL v2, semantic closure, and reservations

Canonical SQL v2 is an exact derived artifact, not prose. Its source is the
UTF-8/LF bytes of `engine/registration_schema.sql` at frozen v1 SHA-256
`221aaf6680b50ca8f6c8c2cf024acbedbf5273b90c8c5625bcc4100c448d5ede`.
The extractor applies R01–R09 below in order. For each replacement it requires
the stated exact occurrence count in the then-current bytes; zero, extra,
overlapping, CR-containing, non-UTF-8, or non-final-LF input refuses. Spans
include both named boundary lines and preserve no omitted bytes. The output
must end in exactly `;\n` and hash to
`b97f02ef67d48886f917368fa420fda0c5dd5942441b23a190732e3cc45106c8`;
it is exactly 130,952 bytes and 1,285 LF-terminated lines.

<!-- canonical-registration-sql-v2-transform:begin -->

**R01 — exact reservation CHECK tokens, once each**

```text
outcome_reservation_bytes BETWEEN 1 AND 1048576
-> outcome_reservation_bytes BETWEEN 98304 AND 1048576

successor_reservation_bytes BETWEEN 1 AND 1048576
-> successor_reservation_bytes BETWEEN 32768 AND 1048576
```

**R02 — T02 shared runtime/writer/profile span, once**

Replace original byte span `[64962,65340)` (E02, old hash from the table
below) with:

```sql
    AND NEW.runtime_capability_hash=CASE WHEN NEW.operation_kind IN('MARK_UNAVAILABLE','REACQUIRE_EFFECT') AND (SELECT mode FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)='DRAINING' THEN (SELECT staged_runtime_capability_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) ELSE (SELECT runtime_capability_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) END
    AND NEW.writer_binary_hash=CASE WHEN NEW.operation_kind IN('MARK_UNAVAILABLE','REACQUIRE_EFFECT') AND (SELECT mode FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)='DRAINING' THEN (SELECT staged_writer_binary_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) ELSE (SELECT writer_binary_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) END
    AND NEW.profile_hash=CASE WHEN NEW.operation_kind IN('MARK_UNAVAILABLE','REACQUIRE_EFFECT') AND (SELECT mode FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)='DRAINING' THEN (SELECT staged_profile_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) ELSE (SELECT profile_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) END
```

**R03 — T02 DATA authentication span, once**

Replace original byte span `[65358,65638)` (E03, old hash from the table
below) with:

```sql
      NEW.operation_class='DATA'
      AND (
       (SELECT mode FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)='WRITABLE'
       OR (
        NEW.operation_kind IN('MARK_UNAVAILABLE','REACQUIRE_EFFECT')
        AND (SELECT mode FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)='DRAINING'
        AND NEW.target_staged_epoch_hash=(SELECT staged_epoch_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
        AND EXISTS(
         SELECT 1 FROM registration_member m JOIN registration_runtime_status s ON s.member_id=m.member_id JOIN registration_effect e ON e.effect_id=m.current_effect_id JOIN registration_protocol_epoch p ON p.protocol_seq=(SELECT MAX(protocol_seq) FROM registration_protocol_epoch)
         WHERE m.member_id=NEW.target_member_id AND m.phase='EFFECT_IN_FLIGHT' AND m.current_effect_id=NEW.target_effect_id AND m.helper_generation=p.staged_generation AND e.outcome_kind IS NULL
           AND ((NEW.operation_kind='MARK_UNAVAILABLE' AND s.executor_token_hash=NEW.target_executor_token_hash AND s.executor_generation=p.staged_generation) OR (NEW.operation_kind='REACQUIRE_EFFECT' AND s.executor_token_hash IS NULL AND s.help_due=1))
           AND EXISTS(SELECT 1 FROM registration_operation_audit adopt WHERE adopt.operation_kind='ADOPT_EFFECT' AND adopt.target_member_id=m.member_id AND adopt.lineage_effect_id=e.effect_id AND adopt.target_staged_epoch_hash=p.staged_epoch_hash AND adopt.target_member_tuple_hash=m.member_tuple_hash)
        )
       )
      )
      AND NEW.writer_capability_receipt_hash=CASE WHEN (SELECT mode FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)='DRAINING' THEN (SELECT staged_writer_capability_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) ELSE (SELECT writer_capability_hash FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) END
```

**R04 — conservative outstanding-effect charge, exactly three occurrences**

```text
e.external_growth_reservation_bytes+e.outcome_reservation_bytes+e.successor_reservation_bytes ELSE e.successor_reservation_bytes
-> 18874368 ELSE 1048576
```

**R05 — bounded recovery guard, once**

At original byte offset `68431` (E05) insert:

```sql
    AND (NEW.operation_kind NOT IN('MARK_UNAVAILABLE','REACQUIRE_EFFECT') OR (NEW.projected_db_growth_bytes=8192 AND (SELECT COUNT(*) FROM registration_operation_audit WHERE operation_kind IN('MARK_UNAVAILABLE','REACQUIRE_EFFECT') AND target_effect_id=NEW.target_effect_id)<6 AND (SELECT COALESCE(SUM(projected_db_growth_bytes),0) FROM registration_operation_audit WHERE operation_kind IN('MARK_UNAVAILABLE','REACQUIRE_EFFECT') AND target_effect_id=NEW.target_effect_id)+NEW.projected_db_growth_bytes<=49152))
```

**R06 — conservative selected-effect charges and recovery carve-out, once
each**

```text
WHEN NEW.operation_kind='APPEND_ACTION' THEN COALESCE((SELECT e.successor_reservation_bytes+(e.outcome_reservation_bytes-(SELECT COALESCE(SUM(projected_db_growth_bytes),0) FROM registration_operation_audit WHERE operation_kind='APPEND_ACTION' AND target_effect_id=NEW.target_effect_id)-NEW.projected_db_growth_bytes)+(e.external_growth_reservation_bytes-(SELECT COALESCE(SUM(external_growth_bytes),0) FROM registration_effect_action WHERE effect_id=NEW.target_effect_id)-NEW.external_growth_bytes) FROM registration_effect e WHERE e.effect_id=NEW.target_effect_id),0)
-> WHEN NEW.operation_kind='APPEND_ACTION' THEN 18874368

WHEN NEW.operation_kind IN('CLOSE_SUCCESS','CLOSE_CONFLICT') THEN COALESCE((SELECT successor_reservation_bytes FROM registration_effect WHERE effect_id=NEW.target_effect_id),0)
-> WHEN NEW.operation_kind IN('CLOSE_SUCCESS','CLOSE_CONFLICT') THEN 1048576

+NEW.projected_db_growth_bytes<=e.outcome_reservation_bytes
-> +NEW.projected_db_growth_bytes<=e.outcome_reservation_bytes-49152
```

The final token replacement has exactly two occurrences: APPEND_ACTION and
CLOSE_SUCCESS/CLOSE_CONFLICT.

**R07 — T09 REACQUIRE protocol/lineage span, once**

Replace original byte span `[112722,113934)` (E07, old hash from the table
below) with:

```sql
         AND (
          (p.mode='WRITABLE' AND p.protocol_generation=m.helper_generation AND ((e.required_protocol_generation=m.helper_generation AND e.required_runtime_capability_hash=p.runtime_capability_hash) OR (e.required_protocol_generation<>m.helper_generation AND EXISTS(SELECT 1 FROM registration_operation_audit adopt JOIN registration_protocol_epoch staged ON staged.protocol_seq=adopt.protocol_seq WHERE adopt.operation_kind='ADOPT_EFFECT' AND adopt.target_member_id=m.member_id AND adopt.lineage_effect_id=e.effect_id AND adopt.expected_generation=e.required_protocol_generation AND adopt.target_action_plan_hash=e.action_plan_hash AND adopt.target_staged_epoch_hash=staged.staged_epoch_hash AND staged.protocol_generation=e.required_protocol_generation AND staged.runtime_capability_hash=e.required_runtime_capability_hash AND staged.staged_generation=m.helper_generation AND staged.staged_runtime_capability_hash=p.runtime_capability_hash))))
          OR
          (p.mode='DRAINING' AND p.staged_generation=m.helper_generation AND EXISTS(SELECT 1 FROM registration_operation_audit adopt WHERE adopt.operation_kind='ADOPT_EFFECT' AND adopt.target_member_id=m.member_id AND adopt.lineage_effect_id=e.effect_id AND adopt.target_staged_epoch_hash=p.staged_epoch_hash AND adopt.target_member_tuple_hash=m.member_tuple_hash))
         )
```

**R08 — T09 REACQUIRE executor generation, once**

Replace original byte span `[114273,114619)` (E08, old hash from the table
below):

```text
      AND NEW.executor_generation=(SELECT protocol_generation FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)
```

with:

```sql
      AND NEW.executor_token_hash IS NOT NULL
      AND NEW.executor_boot_id=(SELECT sample_boot_id FROM registration_operation_audit WHERE operation_id=NEW.write_operation_id)
      AND NEW.executor_generation=CASE WHEN (SELECT mode FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)='DRAINING' THEN (SELECT staged_generation FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) ELSE (SELECT protocol_generation FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) END
      AND NEW.schedule_boot_id IS NULL
```

**R09 — T09 MARK_UNAVAILABLE generation/lineage guard, once**

At original byte offset `121861` (E09) insert:

```sql
      AND (((SELECT mode FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)='WRITABLE' AND OLD.executor_generation=(SELECT protocol_generation FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)) OR ((SELECT mode FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1)='DRAINING' AND OLD.executor_generation=(SELECT staged_generation FROM registration_protocol_epoch ORDER BY protocol_seq DESC LIMIT 1) AND EXISTS(SELECT 1 FROM registration_member m JOIN registration_effect e ON e.effect_id=m.current_effect_id JOIN registration_protocol_epoch p ON p.protocol_seq=(SELECT MAX(protocol_seq) FROM registration_protocol_epoch) WHERE m.member_id=NEW.member_id AND m.helper_generation=p.staged_generation AND EXISTS(SELECT 1 FROM registration_operation_audit adopt WHERE adopt.operation_kind='ADOPT_EFFECT' AND adopt.target_member_id=m.member_id AND adopt.lineage_effect_id=e.effect_id AND adopt.target_staged_epoch_hash=p.staged_epoch_hash AND adopt.target_member_tuple_hash=m.member_tuple_hash))))
```

For mechanical extraction, edits are applied to the original SQL-v1 bytes in
descending zero-based `[start,end)` order. `old_sha256` covers exactly the
removed bytes; `new_sha256` covers the exact replacement bytes shown in
R01–R09. Insertions have `start=end` and the empty SHA-256. This table, base
hash, literal replacement blocks, and output hash are jointly normative:

```text
id     start   end     old_len old_sha256                                                       new_len new_sha256
E01a   19368   19415   47      96e71175309f9cb8e81d8645552958b247e516b09afb8a312a69573d472ac1c8 51      632ae0d0283c2526a26575048d8fb4ffdabb8f277824db67f64d29422c407fc2
E01b   19470   19519   49      ea22cc17e3d50362245655a8f23a3f7528dd87e800475ec73a3f43b30f67c66b 53      5c80dd03cec1802e8df22a2bf65e9a7101ba4bc0787a692fcdf18f814a63ed3d
E02    64962   65340   378     84cddbd8ec36e58438459f5dd136eefb350ed50cf472e5fedacdebd33097c27f 1232    cd79dae4ee624ff43a1daa2fbb5c6c7068bd37f5bac07378ca33b1282c208a86
E03    65358   65638   280     da39334f0388167ae907ff23c6f026e0e3fa43444e63814ed4c47142143b7e92 1916    2276598eb92ff87f78820f4b464034aac97e7a1d9045278182437a5a9beda9df
E04.1  68017   68145   128     fe890932f5ca8e9623c604effeb935d840ab49c8b6df48784d32ffffca87b2fc 21      59e2f68c9c44a9aa81d8ecd6920fad16bb7397668e5a8142f4014cf5c9eb7042
E05    68431   68431   0       e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 510     7215af995833c039a006298500002c8967fe618835faa8b1fa89ed2a8115c967
E04.2  68766   68894   128     fe890932f5ca8e9623c604effeb935d840ab49c8b6df48784d32ffffca87b2fc 21      59e2f68c9c44a9aa81d8ecd6920fad16bb7397668e5a8142f4014cf5c9eb7042
E06a   69245   69812   567     3c3f7bfb45702b70e83db0a9529bbda1f994c9bb460577c2d9e78ce161d1c47b 53      39bcd4b912d7821397b9a704e94e0a2ae1fab025ccbc5225286307c3aa56ab17
E06b   69820   69996   176     9b15d84b730b111e756f344a88653271918552f1c6d0b428ba02d6561ef774aa 73      803a1f9e78bc33ae3897ad0889240033e64d71fad3005ac3dbaa9a4fc415513d
E06.1  70353   70412   59      56d1fae8267774c0571c7dca46e463150bd72b37035dead3093c653de4b941ae 65      2a898dd125979d80033753eb1319e23ed8621b74048f3968eceb9de6264445e0
E06.2  70950   71009   59      56d1fae8267774c0571c7dca46e463150bd72b37035dead3093c653de4b941ae 65      2a898dd125979d80033753eb1319e23ed8621b74048f3968eceb9de6264445e0
E04.3  72038   72166   128     fe890932f5ca8e9623c604effeb935d840ab49c8b6df48784d32ffffca87b2fc 21      59e2f68c9c44a9aa81d8ecd6920fad16bb7397668e5a8142f4014cf5c9eb7042
E07    112722  113934  1212    bbf8700f5788f573a917c10aa7b61595e1fc6e5a9110281d92f93b94e4634119 1348    86203c31d570c634d689be5ecb5a995c12ab7d906e824a75be7b153fc65c7f5c
E08    114273  114619  346     e2d31cc77febe39db28c86a7cf8a72f097ab64c2bd80dd6173083c4078e9889e 558     20c6a2efb66c69043bfca653f4a64383548d8eef209f512ee29085c0e9b42153
E09    121861  121861  0       e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 1044    b988180a6236bb7b04b9f54182d19831ad4a6da9f3d29877242a10f0380cc731
```

<!-- canonical-registration-sql-v2-transform:end -->

The extraction check executes SQL v2 on the supported SQLite, then requires
7 tables, 9 triggers, 0 views, 0 ordinary indexes, `integrity_check=ok`, and
an empty foreign-key check. It separately compares the authored leaf manifest
with independently observed leaf keys; both remain exactly 97. R03/R07/R09
add no leaf key because operation, transition, reason/selector, and outcome
dimensions are unchanged. The inherited exact group-manifest UTF-8/LF hash is
`a4ad3ebae560cebbfa56667a9dd999be0fa9e88545ef7007f8e66d9be035aba7`;
the bytewise-sorted 97-key LF-list hash is
`497d16a334fcee798b8b720f845358977882af93dfdaff94b7fa1213a5fb7001`.

SQL v2 is a fresh-store predeployment authority, not an in-place migration or
generation advance from SQL v1. The recorded baseline has no authorized live
registration rollout. Implementation/R0 must create fresh throwaway v2
stores; a later installation must freshly prove the target registration store
absent before bootstrap. If revalidation finds any authoritative v1
registration DB/protocol, stop without mutation and require a superseding
migration decision. No code may overwrite, auto-migrate, or treat v1 as v2.

Body A exposes one read-only `validate_semantic_closure()` family. It uses the
existing connection authorizer and read transaction, never repairs. The
selected scope is exact:

1. current protocol hash/preimage, mode/drain totality, staged tuple hash,
   paired `first_effect_id|first_effect_operation_id`, their exact immutable
   OPEN operation, and the one immediate
   `previous_protocol_hash`/sequence predecessor;
2. selected member/status/current effect and, when present, pending effect;
3. selected episode and exact one-member envelope;
4. action-plan JCS equality, action ordinal/ledger chain, outcome JCS, and
   certificate inputs;
5. member/status/episode/effect/action write backlinks; target hashes;
   predecessor and SUPERSEDED successor companions; ADOPT operation,
   lineage effect, staged epoch, action-plan, and executor/generation
   companions; and transition cause; and
6. every foreign-key/phase/outcome/READY relationship used by the caller.

It returns only a typed validated snapshot whose revision token is derived
from the revalidated values. Raw dictionaries cannot cross the store
authority boundary.

The online window is constant and selected: one current protocol plus at most
one predecessor and first-effect operation; one member/status/current effect
plus at most one pending/predecessor/successor effect; one selected episode;
at most four actions; one ADOPT/staged lineage; and only operation rows
referenced by those selected backlinks. Every lookup is by exact key/hash;
online admission never scans protocol or audit history. Full-history doctor
and R0 checks are evidence-only and cannot grant a hook invocation.

At each effect creation and closure read:

```text
BASE_OUTCOME_RESERVATION = 4 * 8 KiB + 16 KiB = 49,152 bytes
RECOVERY_RESERVATION = 3 * (8 KiB + 8 KiB) = 49,152 bytes
MIN_OUTCOME_RESERVATION = 98,304 bytes
MIN_SUCCESSOR_RESERVATION = 32 KiB
```

SQL v2 enforces the minima. Exactly six 8-KiB recovery audit projections
(three valid MARK/REACQUIRE cycles) may consume the recovery reserve. Action
append/close predicates reserve the final 49,152 bytes exclusively for
recovery. Floor-minus-one vectors are 98,303 and 32,767 bytes. On attempted
cycle four the DATA transaction writes nothing and Body A returns one
process-memory-only `RecoveryReserveExhausted` value with exact
`protocol_hash, staged_epoch_hash, member_id, effect_id, member_tuple_hash,
status_hash, executor_token_hash|null, recovery_operation_count="6",
recovery_bytes_consumed="49152", recovery_bytes_reserved="49152"`. It is
never serialized, persisted, rendered as a new reason, or accepted as
CONTROL.

Ordinary Body B runtime maps it to existing `CONTAINMENT_UNAVAILABLE` and an
ADR 0020 redacted RED component; this claims neither a durable notice nor
committed containment. Only while Body C already holds an authenticated
`StoreControlAdapter` for authorized cutover/reconciliation may that adapter
consume the exact value, revalidate every hash, and attempt existing
`ENTER_CONTAINMENT/STORE_FAILURE`. Actor text, runtime code, a forged value,
or the value alone cannot create CONTROL.

Before semantic closure, every outstanding unclosed effect is charged at
18,874,368 bytes (16 MiB + 1 MiB + 1 MiB) and each resolved-current successor
at 1,048,576 bytes. Validated selected closure may enforce tighter
operation-specific consumption but a corrupt low row never lowers global
required free space. Legacy v1 rows below either new floor are corruption,
never silently raised, rewritten, or admitted.

### 4.2 Signed deployment authority successor

`awa-registration-candidate/v1` remains exact and unchanged.

Define:

```text
DIRECT_BODY_FIELDS =
  every awa-registration-direct-receipt/v3 field except owner_gate_digest

direct_receipt_body_hash =
  SHA256(ASCII("awa-registration-direct-receipt-authority/v2") || 0x00 ||
         JCS(exact DIRECT_BODY_FIELDS object))
```

The v3 receipt retains every v2 field and adds exactly:

```text
bundle_generation
bundle_digest
bundle_projection_hash
import_manifest_hash
external_interpreter_hash
interpreter_capability_hash
denial_proof_vector_hash
allowed_signers_contract_path_hash
allowed_signers_contract_hash
signer_public_key_sha256
signer_fingerprint
key_enrollment_digest
harness_root_hash
```

The signed gate has exactly:

```text
schema = "awa-registration-owner-gate/v2"
repository = "KleinPerkins/awa"
authorized_by = "KleinPerkins"
deployment_scope
direct_receipt_body_hash
candidate_digest
bundle_digest
bundle_projection_hash
import_manifest_hash
external_interpreter_hash
interpreter_capability_hash
denial_proof_vector_hash
installed_file_hash
wrapper_runtime_hash
installer_identity_hash
installer_capability_hash
allowed_signers_contract_path_hash
allowed_signers_contract_hash
signer_public_key_sha256
signer_fingerprint
key_enrollment_digest
canonical_root_hash
member_id
harness_root_hash
authorized = true
```

Its digest is:

```text
SHA256(ASCII("awa-registration-owner-gate/v2") || 0x00 || JCS(gate))
```

The receipt's `owner_gate_digest` equals that digest. `harness_root_hash` is
non-null only for `R0_THROWAWAY`; root/member are non-null only for
`R1_CANARY`; all three are null for `R2_DIRECT`.

Signing is one concrete offline mechanism:

```bash
# owner machine; private key path is external and never persisted by AWA
/usr/bin/ssh-keygen -Y sign \
  -f <owner-private-key-path> \
  -n awa-registration-owner-gate-v2 \
  <exact-gate-bytes-path>

# AWA verifier; exact gate bytes arrive on stdin
/usr/bin/ssh-keygen -Y verify \
  -f <descriptor-bound-allowed-signers-path> \
  -I KleinPerkins \
  -n awa-registration-owner-gate-v2 \
  -s <detached-signature-path> \
  < <exact-gate-bytes-path>
```

```text
gate_bytes = JCS(exact gate object) || LF
owner_gate_digest hashes JCS(gate), excluding only the framing LF
```

The future contract path is exactly
`contracts/awa-registration-owner-signers.v1`. Its content is exactly:

```text
ASCII("KleinPerkins namespaces=\"awa-registration-owner-gate-v2\" ssh-ed25519 ")
|| RFC4648_BASE64(OpenSSH_wire_blob(enrolled_ssh_ed25519_public_key))
|| LF
```

No comment, second principal/key, padding rewrite, CR, or extra LF is legal.

The implementation opens that regular, owner-safe file descriptor-relative
under the exact installed bundle, verifies its relative path hash and content
hash from the receipt/gate, and invokes stock `/usr/bin/ssh-keygen`. Before
the contract can authorize any gate, the owner must separately approve an
`awa-registration-owner-key-enrollment/v1` record with exactly:

```text
schema = "awa-registration-owner-key-enrollment/v1"
principal = "KleinPerkins"
namespace = "awa-registration-owner-gate-v2"
key_algorithm = "ssh-ed25519"
public_key_sha256
openssh_fingerprint
allowed_signers_relative_path = "contracts/awa-registration-owner-signers.v1"
allowed_signers_path_hash
allowed_signers_contract_hash
authorized = true
```

```text
key_enrollment_digest =
  SHA256(ASCII("awa-registration-owner-key-enrollment/v1") || 0x00 ||
         JCS(exact enrollment object))
```

`allowed_signers_path_hash` is
`SHA256(ASCII("awa-registration-owner-signers-path/v1") || 0x00 ||
UTF8("contracts/awa-registration-owner-signers.v1"))`. The contract content
hash covers its exact UTF-8/LF bytes.

The allowed-signers file does not bootstrap its own trust. The independent
machine-local trust anchor is:

```text
${XDG_STATE_HOME}/awa/registration-owner-key/current.json
```

It is an atomically published, owner-only regular `0600` file in `0700`
parents, created only by a separately owner-authorized key-enrollment action.
Schema `awa-registration-owner-key-current/v1` contains exactly:

```text
schema, sequence, status = ACTIVE | REVOKED,
principal, namespace, key_algorithm,
public_key_sha256, openssh_fingerprint,
allowed_signers_relative_path, allowed_signers_path_hash,
allowed_signers_contract_hash, key_enrollment_digest,
owner_authorization_digest, previous_enrollment_hash, created_wall_ns,
enrollment_hash
```

`enrollment_hash` is the domain-separated JCS hash excluding itself.
`owner_authorization_digest` binds the one-use exact operator enrollment
decision; it is not derived from the signing key. Its exact schema/domain is
`awa-registration-owner-key-authorization/v1`, with exactly:

```text
schema, repository="KleinPerkins/awa", authorized_by="KleinPerkins",
action="ENROLL", principal, namespace, key_algorithm,
public_key_sha256, openssh_fingerprint,
allowed_signers_relative_path, allowed_signers_path_hash,
allowed_signers_contract_hash, key_enrollment_digest,
acceptance_normalized_digest, authorization_nonce, authorized=true
```

`authorization_nonce` is one-use lowercase 64-hex; the digest is the standard
domain-separated exact JCS hash. Before `ssh-keygen -Y
verify`, the verifier must read this current receipt independently, require
`ACTIVE`, and require every signer/contract/enrollment field in the gate and
bundle contract to equal it. Internal gate/contract/key consistency without
that current receipt is non-authority.

The fixed authorization vector uses the synthetic
public identity/contract/enrollment values in §4.2.1,
`acceptance_normalized_digest=H(f)`, and `authorization_nonce=H(e)`;
expected digest is
`6a584b0b58637ed5336f893dd013d6d2b97ffcf239809f53ce0d220ad8c51c3a`.
The fixed current-receipt vector uses sequence `"1"`, `ACTIVE`, that
authorization digest, `previous_enrollment_hash=null`, and
`created_wall_ns="100"`. Domain is
`awa-registration-owner-key-current/v1`; expected `enrollment_hash` is
`c015932b89b150ff8f4dadd58ca9fc1ce34a1ecc5571537ec323a3285aa80a93`.

Implementation-delivery, release, installation, and host-activation
authorities each name the exact current `enrollment_hash`. Rotation appends a
higher sequence with the prior hash after a new owner enrollment decision.
Revocation publishes `REVOKED` (or an authorized ACTIVE successor); no new
gate verifies under a revoked/noncurrent receipt. Same-UID replacement remains
an explicit residual detected as authority drift, never accepted by
self-signature.

No key or contract is created by this plan. Rotation needs a successor
contract hash and fresh fingerprint enrollment. Revocation makes the
successor contract current and rejects the old contract for new gates while
preserving prior receipts as evidence. Negative vectors cover wrong principal,
namespace, key, algorithm, fingerprint, path, contract hash, enrollment
digest, duplicate principal/line, altered bytes/LF, and revoked predecessor.

The complete fixed preimages and outputs are in §4.2.1. Receipt/gate vectors
use those derived bundle/projection/import/interpreter/proof/wrapper hashes,
logical candidate fields `"aa"*32`, matcher `ENUMERATED`, generations `"2"`,
installed receiver `"bb"*32`, installer identity/capability
`"11"*32`/`"22"*32`, the concrete synthetic signer contract/public identity/
fingerprint in §4.2.1, R0 harness root
`"77"*32`, and R1 root/member `"88"*32`/`"99"*32`.

```text
candidate_digest
  44eaaa6cd88e4aee5c2e69890bad2e2db925cfae40fa2a79abdec8d29d282cfc

R0 direct_receipt_body_hash
  eacdbd28b08d7f7674059fff7e8c29f491b76dbb42c43748758ae111e0fbef48
R0 owner_gate_digest
  d0a07bd84458a9fb9cbe200b7f17e882f1ffd670df83bfcc011dce8eede20277
R0 DIRECT receipt digest
  2534fc8d372ceda50cee15761898eebda847c152d8df8ba530cb9871ff906cd5

R1 direct_receipt_body_hash
  dd0ef515d7fa7cc98cc241f2922e363460373d3799d9b938fd7887a55e021881
R1 owner_gate_digest
  f0b6cf0c2f79e224a629d0a8dc9aa3c41f6a282bc84750fbf35a4b9827c001f1
R1 DIRECT receipt digest
  19382cb1c7eba25aaabe4cfc75b55b10c4d0d87b6b17c65924fe21cc9845d518

R2 direct_receipt_body_hash (root/member null)
  500f13a4de86ef501f5e0e3e2efd7d62c19346b5e0d8435f6056649e7d36cea0
R2 owner_gate_digest
  1c86fc68c0eb6794f8e5671b7f448436ec886f1d63f329b94d9f5c28c921cc3d
R2 DIRECT receipt digest
  24f5363f6efdd6dc2620b4f3219b6db4f7a525b62c3ca1d404e6f663251fb8fa
```

The fixture mutation-kills every field, field order, nullability, literal,
domain, signature, signer-contract/enrollment binding, and repeated-field
comparison. Positive signature fixtures use an ephemeral test-only
ssh-ed25519 key under a throwaway directory; its key material and fingerprint
are never governance or production authority.

#### 4.2.1 Closed authority preimage registry

Every authority object below uses RFC 8785 JCS with exact keys, no duplicate
or unknown key, no JSON number/float, decimal integer strings, lowercase
64-hex hashes, Unicode-scalar strings, and the domain formula
`SHA256(ASCII(domain) || 0x00 || JCS(object))`. Nullable fields are explicitly
JCS `null`; omitted nullable keys are invalid.

Bundle-relative paths are UTF-8 POSIX relative paths: nonempty, NFC,
slash-separated, no leading slash, empty/`.`/`..` component, backslash, NUL,
control, or symlink traversal. Records are unique and bytewise-UTF-8 path
sorted. Absolute paths are forbidden except the separately measured external
interpreter record.

The fixed vector notation `H(x)` means the lowercase character `x` repeated
exactly 64 times; `OID(x)` means it repeated exactly 40 times. This notation
is mechanically expanded before JCS and is not a wildcard.

**Installer-selected external interpreter and capability probe**

The installer/candidate constructor requires one explicit normalized absolute
interpreter path from its separately authorized input. It never consults
`PATH`, cwd, shebang lookup, `sys.executable`, environment fallback, or a
fixed product path. Before gate bytes exist it descriptor-walks every ancestor
without symlink following, requires root/effective-user ownership and
non-group/other-writable ancestry, and measures the final regular executable.

Path grammar is exact: strict UTF-8 NFC, 1–4096 bytes, leading `/`, no NUL/
control/backslash, no empty/`.`/`..` component, `normpath(path)==path`, and
descriptor-resolved path equals the supplied path. Every ancestor and the
final executable is root- or effective-user-owned and not group/other
writable. The final object is regular, single-link, owner-executable, and
non-symlinked.

The separately authorized input is exact schema/domain
`awa-registration-interpreter-selection/v1`:

```text
schema, scope = R0 | RELEASE | INSTALL,
repository = "KleinPerkins/awa", authorized_by = "KleinPerkins",
source_revision, candidate_digest,
harness_root_hash, installation_root_hash,
interpreter_path, authorization_nonce, authorized=true
```

R0 requires harness hash non-null/install null; INSTALL requires install hash
non-null/harness null; RELEASE requires both null. The selection envelope is
the interpreter input named by Gate 6, 7, or 8 respectively; no unbound
caller argument is accepted. Fixed selection uses scope R0, source
`OID(b)`, candidate vector digest, harness `H(7)`, install null, fixture path,
nonce `H(6)`.

Ancestry schema/domain is
`awa-registration-interpreter-ancestry/v1`, exact keys `schema,records`.
Root-to-leaf parent records have exactly
`ordinal,component_hash,st_dev,st_ino,st_mode,st_uid,st_gid,st_nlink,
object_type="DIRECTORY"`; ordinal is unsigned decimal and component hash is
`SHA256("awa-registration-path-component/v1" || 0x00 || UTF8(component))`.
The fixed parents are `/`, `fixture`, `python`, `bin` with ordinals
`"0"`–`"3"`, dev `"1"`, inos `"10"`–`"13"`, root mode/uid/gid
`"16877","0","0"`, and other modes/uids/gids `"16832","501","20"`,
all nlink `"1"`.

Capability schema/domain: `awa-registration-python-capability/v1`. Exact keys:

```text
schema, platform, os_build, python_implementation, python_version,
required_python_apis, sqlite_runtime_version, sqlite_source_id,
sqlite_compile_options_hash, sqlite_vfs_name, journal_mode, synchronous,
fullfsync, checkpoint_fullfsync, foreign_keys,
connection_setconfig_available, sqlite_dbconfig_defensive_available,
defensive, trusted_schema, locking_mode, nofollow_available,
checkpoint_on_close, probe_program_hash
```

`required_python_apis` is exactly the bytewise-sorted array:

```text
fcntl.flock
os.O_NOFOLLOW
os.fstat
sqlite3.Connection.setconfig
sqlite3.SQLITE_DBCONFIG_DEFENSIVE
sqlite3.SQLITE_DBCONFIG_NO_CKPT_ON_CLOSE
```

The installer executes only the selected descriptor-revalidated path with
`-I -S -B`, a closed environment, and the exact hash-bound probe program.
The probe uses only an in-memory/private throwaway SQLite target and emits
exact JCS+LF; it performs no persistent product write. Acceptance requires:
Darwin/macOS; CPython with every listed API; SQLite runtime `>=3.51.3`; exact
source-id/compile-options/VFS and required WAL/FULL/fullfsync/
checkpoint-fullfsync/foreign-keys/defensive/trusted-schema/normal-locking/
NOFOLLOW/no-checkpoint-on-close values; `Connection.setconfig`; and
`SQLITE_DBCONFIG_DEFENSIVE`. Any unavailable/false/mismatched requirement
refuses before receipt, signature, protocol, or persistence.

Compile-options schema/domain is
`awa-registration-sqlite-compile-options/v1`, exact keys
`schema,options`; options are distinct bytewise-UTF-8 sorted strings. Fixed
options are `["ENABLE_FTS5","THREADSAFE=1"]`.

External-interpreter schema/domain:
`awa-registration-external-interpreter/v1`. Exact keys:

```text
schema, selection_hash, path, path_hash, ancestry_hash,
st_uid, st_gid, st_mode, st_dev, st_ino, st_nlink, st_size,
content_sha256, capability_probe_hash, probe_program_hash
```

`path` is the explicit canonical absolute input; all metadata are decimal
strings and selection/path/ancestry/content/probe fields are lowercase
64-hex. `path_hash` is
`SHA256("awa-registration-interpreter-path/v1" || 0x00 || UTF8(path))`.
It is never a bundle payload entry.

The machine-independent supported fixture path is
`/fixture/python/bin/python3.14`, uid/gid
`"501"/"20"`, mode `"33261"`, dev/ino/nlink/size `"1"/"2"/"1"/"3"`,
content `H(b)`, probe program `H(f)`. Supported capability values are exactly:

```text
schema="awa-registration-python-capability/v1"
platform="darwin"; os_build="fixture"; python_implementation="CPython"
python_version="3.14.6"; required_python_apis=<exact array above>
sqlite_runtime_version="3.53.3"; sqlite_source_id="fixture-source-id"
sqlite_compile_options_hash=<fixed compile-options hash>
sqlite_vfs_name="unix"; journal_mode="wal"; synchronous="full"
fullfsync=true; checkpoint_fullfsync=true; foreign_keys=true
connection_setconfig_available=true
sqlite_dbconfig_defensive_available=true; defensive=true
trusted_schema=false; locking_mode="normal"; nofollow_available=true
checkpoint_on_close=false; probe_program_hash=H(f)
```

The explicit rejected-system-shape fixture uses the same complete capability
object but Python `"3.9.6"`, SQLite `"3.51.0"`,
`connection_setconfig_available=false`,
`sqlite_dbconfig_defensive_available=false`, and `defensive=false`. It models
the observed `/usr/bin/python3` incompatibility but the normative vector
contains no durable host path.

**Import manifest**

Schema/domain: `awa-registration-import-manifest/v1`. Exact keys:
`schema, entry_modules, records`. `entry_modules` are unique bytewise-sorted
dotted names. Each path-sorted record has exactly
`path, role, mode, size, sha256`; role is `PACKAGE_INITIALIZER | MODULE`.
The generator—not a caller—owns set completeness. Fixed preimage:

```text
entry_modules = ["engine.registration_host"]
records = [
  {path:"engine/__init__.py", role:"PACKAGE_INITIALIZER",
   mode:"420", size:"1", sha256:H(a)},
  {path:"engine/registration_host.py", role:"MODULE",
   mode:"420", size:"2", sha256:H(b)}
]
```

**Bundle manifest and wrapper runtime**

Bundle schema/domain: `awa-registration-bundle-manifest/v1`; exact keys
`schema, generation, entries, import_manifest_hash,
external_interpreter_hash, interpreter_capability_hash,
allowed_signers_contract_hash`. Each entry has
exactly `path, role, mode, size, sha256`; role is
`RECEIVER | LAUNCHER | RUNTIME | PACKAGE_INITIALIZER | IMPORT_MANIFEST |
SIGNER_CONTRACT | CONFIG`. Fixed path-sorted entries:

```text
bin/awa-registration-launcher            LAUNCHER            493 2 H(c)
bin/awa-registration-receiver            RECEIVER            493 1 H(b)
contracts/awa-registration-owner-signers.v1 SIGNER_CONTRACT   420 138 bbd1f1bc972dc5ab20635021d8486f15de24011f61b59c1c6861379acc8b8c5f
engine/__init__.py                        PACKAGE_INITIALIZER  420 1 H(a)
engine/registration_host.py               RUNTIME             420 2 H(b)
import-manifest.json                      IMPORT_MANIFEST      420 420 671ff69bc00de5472889da47199821ae141e92bd37e7637ff616259cb4f3fa2c
runtime-config.json                       CONFIG               384 483 <launcher-config hash>
```

Generation is `"2"`; import/interpreter hashes are the vector outputs below;
signer-contract hash is the exact line hash above.

`import-manifest.json` payload bytes are exact `JCS(import_manifest) || LF`.
Its bundle entry always uses actual byte length and plain SHA-256; the
domain-separated `import_manifest_hash` remains separate authority. Tests
require payload parse/re-encode equality and shared-path byte/hash equality
with every runtime record.

Wrapper schema/domain: `awa-registration-wrapper-runtime/v2`; exact keys
`schema, bundle_digest, launcher_hash, import_manifest_hash,
external_interpreter_hash, interpreter_capability_hash,
launcher_config_hash, runtime_records`. `runtime_records` are exactly the
bundle's `PACKAGE_INITIALIZER|RUNTIME` entry objects in bundle order.
Launcher hash is `H(c)`.

Launcher-config schema is `awa-registration-launcher-config/v1`; exact keys:

```text
schema, bundle_generation, interpreter_path, external_interpreter_hash,
interpreter_capability_hash, import_manifest_hash, entry_module,
isolated_flags
```

The path equals the signed external record, entry module is
`engine.registration_host`, and flags are exactly `["-I","-S","-B"]`.
Config bytes are exact JCS+LF; the bundle entry stores their plain SHA-256.

**Bundle projection and active pointer**

Projection schema/domain: `awa-registration-bundle-projection/v1`; exact
keys:

```text
schema, generation, bundle_digest, receiver_relative_path,
launcher_relative_path, import_manifest_hash, external_interpreter_hash,
interpreter_capability_hash, runtime_config_hash,
allowed_signers_contract_hash
```

Fixed relative paths are `bin/awa-registration-receiver` and
`bin/awa-registration-launcher`; generation `"2"`, config
`75b27f23c46c9ef25aea30667e32bc8daab02a046ea4a24846e8cfa651cd0e63`,
contract
`bbd1f1bc972dc5ab20635021d8486f15de24011f61b59c1c6861379acc8b8c5f`.

Active-pointer schema/domain: `awa-registration-active-bundle/v1`; exact keys
`schema, generation, bundle_relative_dir, bundle_digest,
bundle_projection_hash, direct_receipt_hash, external_interpreter_hash,
interpreter_capability_hash`. Fixed
`bundle_relative_dir = "bundles/2-" || bundle_digest` and uses the R1 receipt
hash. The pointer is not included in receipt/bundle hashes, avoiding a cycle.

**Denial proof and readiness**

Proof schema/domain remains `awa-registration-staged-denial-proof/v2`.
Each sorted record has exactly `event, server_or_empty, discriminator,
serializer_schema, role, seam, bundle_digest, request_hash, output_hash,
exit_code`; `seam` is `DIRECT_RECEIVER | SHADOW_INSTALLED`. Fixed records are
the two seams for observable
`preToolUse,"",Shell,cursor-permission/v1,ordinary`, bundle vector digest,
request `H(7)`, output `H(8)`, exit `"2"`.

Readiness schema/domain: `awa-registration-staged-readiness/v2`; exact keys
`schema, mode, current_protocol_hash, staged_epoch_hash, bundle_digest,
direct_receipt_hash, import_manifest_hash, external_interpreter_hash,
interpreter_capability_hash, measured_profile_hash, storage_dev,
denial_proof_vector_hash`. Fixed values are
`DENY_ONLY,H(1),H(2),<bundle>,H(3),<import>,<interpreter>,<capability>,
H(a),"1",<proof>`.

**Signer enrollment and public-key identity**

Canonical public-key identity bytes are exactly
`ASCII("ssh-ed25519") || SP || base64_key || LF`, with no comment. Its plain
SHA-256 is `signer_public_key_sha256`; OpenSSH independently reports and must
equal `openssh_fingerprint`. Enrollment fields/domain are exactly those in
§4.2, including derived signer-path hash and contract-content hash.

The non-authorizing synthetic vector uses the 32 public bytes `00..1f` in
order. Its exact OpenSSH base64 blob is:

```text
AAAAC3NzaC1lZDI1NTE5AAAAIAABAgMEBQYHCAkKCwwNDg8QERITFBUWFxgZGhscHR4f
```

Its canonical public identity hash is
`8b5a6781cafa6fd206a9681ddc4f09148311c8a14a571c784d30e5c53777e429`;
its fingerprint is
`SHA256:ZkAslGjFiUHdGf/WUL8rQvkib4PTvQatUV0OUQSncCA`. The exact 138-byte
allowed-signers vector line is:

```text
KleinPerkins namespaces="awa-registration-owner-gate-v2" ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAABAgMEBQYHCAkKCwwNDg8QERITFBUWFxgZGhscHR4f
```

including one final LF; its plain SHA-256 is
`bbd1f1bc972dc5ab20635021d8486f15de24011f61b59c1c6861379acc8b8c5f`.
It is test data only and cannot be enrolled as owner authority.

**DIRECT receipt and owner gate**

Receipt v3's exact field set is v2's complete field set plus the thirteen fields
listed in §4.2. Gate v2's exact field set is the displayed gate block.
Receipt-body, gate, and receipt domains are respectively
`awa-registration-direct-receipt-authority/v2`,
`awa-registration-owner-gate/v2`, and
`awa-registration-direct-receipt/v3`. Scope nullability is exactly:
R0 `(root=null,member=null,harness=H(7))`; R1
`(root=H(8),member=H(9),harness=null)`; R2 all three null.

**Same-boot snapshot, cursor, and host tick**

Snapshot schema/domain: `awa-registration-same-boot-snapshot/v1`; exact keys
`schema, boot_id, protocol_seq, protocol_hash, candidates`. Candidates are
bytewise-member-id sorted and each has exactly
`member_id,status_hash,executor_token_hash,executor_generation`.

Cursor schema/domain: `awa-registration-same-boot-cursor/v1`; exact keys:

```text
schema, boot_id, protocol_seq, protocol_hash, selection_snapshot_hash,
last_member_id, last_pre_status_hash, last_post_status_hash,
outcome, batch_count, wrapped
```

Nullable only on an empty cursor:
`last_member_id|last_pre_status_hash|last_post_status_hash|outcome = null`,
`batch_count="0"`, `wrapped=false`. Otherwise all are non-null; outcome is
`BUSY_LIVE | CLEARED | RECOVERED | NO_LONGER_CANDIDATE`, batch count is
`"1"`–`"8"`, and wrapped is JCS boolean.

Host tick schema/domain: `awa-registration-host-tick/v2`; exact keys
`schema,boot_id,written_mono_ns,interval_ns,protocol_seq,protocol_hash,
same_boot_cursor,same_boot_cursor_hash,due_snapshot_hash,
fairness_suspended`. The cursor object is embedded byte-identically.

Fixed snapshot uses boot `boot-a`, protocol seq `"7"`/hash `H(7)`, candidates
`(H(1),H(2),H(3),"2")` and `(H(4),H(5),H(6),"2")`. Cursor ends at `H(4)`,
pre/post status `H(5)`/`H(5)`, outcome `BUSY_LIVE`, batch `"2"`, not wrapped.
Tick uses written `"100"`, interval `"15000000000"`, due hash `H(9)`,
fairness false.

**R0 governed manifests and cut evidence**

Manifest schema/domain: `awa-registration-r0-governed-manifest/v1`; exact
keys `schema, phase, cut_label, barrier_id, exact_head, records`; phase
`BEFORE | AFTER`, cut `C0`–`C7`. Records are path-hash sorted and have
exactly:

```text
path_hash, surface_class, presence, object_type,
st_dev, st_ino, st_mode, st_uid, st_gid, st_nlink, st_size, content_sha256,
authority_hash
```

For `ABSENT`, object type and every metadata/content field are null. For
`PRESENT REGULAR`, all metadata and content hash are non-null. For
`PRESENT DIRECTORY`, all metadata including size are non-null and content
hash is null. For `PRESENT OTHER`, all metadata are non-null, content hash is
null, and R0 necessarily fails. `authority_hash` is non-null only for
`EXTERNAL_INTERPRETER`, where it equals the complete external-interpreter
record hash (and therefore binds the capability probe); it is null otherwise.
`surface_class` is exactly
`PROTOCOL_STATE | RUNTIME | HOOKS | JOBS | SKILLS | DEV_OVERLAY |
INSTALLED_BYTES | EXTERNAL_INTERPRETER`; `presence` is `ABSENT | PRESENT`; `object_type` is
`REGULAR | DIRECTORY | OTHER | null`. Path hash is
`SHA256(ASCII("awa-registration-r0-path/v1") || 0x00 ||
UTF8(canonical_absolute_path))`.

Throwaway-target schema/domain:
`awa-registration-r0-target-manifest/v1`; exact keys
`schema,cut_label,barrier_id,harness_root_hash,records`, using the same record
schema/order.

Process-kill schema/domain: `awa-registration-r0-process-kill/v1`; exact keys
`schema,cut_label,barrier_id,pid,signal,observed_returncode,
started_mono_ns,killed_mono_ns,reaped_mono_ns,process_identity_hash`.
PID/times are unsigned decimal strings, return code is signed decimal, signal
is literal `SIGKILL`.

Process-identity schema/domain: `awa-registration-process-identity/v1`; exact
keys `schema,pid,executable_path_hash,executable_content_hash,argv_hash,
environment_contract_hash,spawn_nonce`; PID is unsigned decimal and all other
fields are lowercase 64-hex.

Write-observation schema/domain:
`awa-registration-r0-write-observation/v1`; exact keys
`schema, observer, available, records`; observer is `FSEVENTS | NONE`,
available is boolean. Each record has exactly
`event_id,path_hash,event_flags,observed_mono_ns`; event id/time are unsigned
decimal strings. `event_flags` is a bytewise-sorted `|`-joined nonempty subset
of exactly `ITEM_CREATED | ITEM_REMOVED | ITEM_INODE_META_MOD |
ITEM_RENAMED | ITEM_MODIFIED | ITEM_FINDER_INFO_MOD | ITEM_CHANGE_OWNER |
ITEM_XATTR_MOD | MUST_SCAN_SUBDIRS | ROOT_CHANGED | MOUNT | UNMOUNT`;
records sort by numeric event id then path hash. If unavailable,
observer=`NONE`, records empty.

Cut-evidence schema/domain: `awa-registration-r0-cut-evidence/v1`; exact keys:

```text
schema, cut_label, barrier_id, exact_head, before_manifest_hash, after_manifest_hash,
throwaway_target_manifest_hash, external_write_observation_hash,
process_kill_hash, receiver_proof_vector_hash, claim_scope
```

`external_write_observation_hash` is nullable only when observer unavailable.
Claim scope is literal
`FINITE_GOVERNED_SURFACES_AND_OBSERVED_TARGETS`.

`barrier_id` is one literal from this complete ordered catalog:

```text
C0.PREFLIGHT
C1.BUNDLE_PUBLISHED
C2.DRAIN_COMMITTED
C2.STAGE_COMMITTED
C2.DIRECT_PROOF
C2.SHADOW_PROOF
C3.POINTER_SWITCHED
C3.POST_SWITCH_PROOF
C3.OLD_ENTRY_DISABLED
C4.ADOPT_COMMITTED
C4.TRANSFER_RECEIVED
C4.TRANSFER_ACTIVATED
C4.MARK_COMMITTED
C4.REACQUIRE_COMMITTED
C5.RECONCILIATION_BATCH
C5.CUSTODY_EMPTY
C6.ADVANCE_COMMITTED
C7.OLD_BUNDLE_REMOVED
C7.RESIDUE_RECONCILED
```

R0 completeness is exact set coverage of every applicable catalog barrier;
extra/unknown/missing ids refuse.

Fixed manifests use cut C2, barrier `C2.STAGE_COMMITTED`, head `OID(b)`, an absent HOOKS record at path
`H(1)`, and a present RUNTIME regular record at `H(2)` with
dev/ino/mode/uid/gid/nlink/size=`"1","2","384","501","20","1","3"` and
content `H(a)`, plus an EXTERNAL_INTERPRETER regular record at the derived
fixture-path hash with
dev/ino/mode/uid/gid/nlink/size=`"1","2","33261","501","20","1","3"`,
content `H(b)`, authority hash equal to the fixed external-interpreter hash,
and R0 path hash
`d1ef657ecdb8c9aec6fdc404740b5c6e433c65e47a253582c44b1e624abab147`
. Fixed observation is available FSEVENTS with one
`event_id="1", path_hash=H(c), event_flags="ITEM_MODIFIED",
observed_mono_ns="40"` record.
The fixed throwaway manifest uses cut C2, barrier `C2.STAGE_COMMITTED`, root
`H(7)`, and one RUNTIME regular record
at `H(c)` with dev/ino/mode/uid/gid/nlink/size
`"1","3","384","501","20","1","4"`, content `H(b)`, and null authority.
Fixed process
identity uses pid `"123"` and path/content/argv/environment/spawn hashes
`H(1)`–`H(5)`. Fixed kill uses cut C2, the same barrier, pid `"123"`,
`SIGKILL`, return `"-9"`, times `"10","20","30"`, and that process identity
hash. Evidence binds these derived hashes and the proof vector.

**Mechanically recomputed fixed outputs**

```text
public_key_identity  8b5a6781cafa6fd206a9681ddc4f09148311c8a14a571c784d30e5c53777e429
signer_fingerprint   SHA256:ZkAslGjFiUHdGf/WUL8rQvkib4PTvQatUV0OUQSncCA
signer_contract      bbd1f1bc972dc5ab20635021d8486f15de24011f61b59c1c6861379acc8b8c5f
interpreter_path      a0caf9d8b6c5a2649358e0dc2d9ce4c9d75a3065496c6a50008bed580520ffdd
interpreter_ancestry  975c44feaf12545fbd1f9c0a091e0701acc2f580ba02a31e31eb205dca53e825
compile_options       b320250f51085d00daadd152978a2023a9bbd59d647976d91d3696372515f0dd
interpreter_selection bb1b13000040b1cbbe3f2c8b047ecbf6d5866ac7de73fa53b12d75e68c9b3211
capability_supported  ca675a27a71e6ff366a59c943ab17e47d02e8f560cd3c2cc00f213424747c9f6
capability_rejected   825d7068ff8d6c2f5a73052054de1cf58f5e49cff809b609223aae80d7ec25f3
external_interpreter  7b7032befe3cb79573811d97763cb8dddec67f0147a98fb99c9f912b2a3154b2
launcher_config      75b27f23c46c9ef25aea30667e32bc8daab02a046ea4a24846e8cfa651cd0e63
import_manifest       dddb3b7741e48de647da4d6950364e7330a56bb94617097a79b2b7207676e170
import_manifest_file  671ff69bc00de5472889da47199821ae141e92bd37e7637ff616259cb4f3fa2c
bundle_digest         2ceab2235e3c1c107c26fcdaa213cf191450b395e51d8e1d08f34e52e0b9ca3d
wrapper_runtime       9b2d07ca937ea451028f5b0d5a755383320f5b0f3c8224eea3c090a9fdad28e0
bundle_projection     28793a6f63a8a045df41a7590f4002897c3d860b65f96ded1bc04a1e46fa9b71
denial_proof          c72a4fc31d3037732bf55305511f58dbf0b7f5f58377e98bd80a61461d53b4cd
staged_readiness      77db8c1f786d2f10bd21574f2d56b8b867c90ec6898eea7d2f6032b0b48ecd77
signer_path           ff4fbbc153649c484ee3d8f5203efa64db0c2a4dcae0a1a692514f5347d66faa
key_enrollment        ff7b0f05ac7d34958401277fef51ecf054b8328bf9c4571e2fa794c19fe15428
owner_authorization   6a584b0b58637ed5336f893dd013d6d2b97ffcf239809f53ce0d220ad8c51c3a
current_enrollment    c015932b89b150ff8f4dadd58ca9fc1ce34a1ecc5571537ec323a3285aa80a93
candidate_digest      44eaaa6cd88e4aee5c2e69890bad2e2db925cfae40fa2a79abdec8d29d282cfc
active_pointer        a7a5af2456ae4f0e4db786965ab54720174cd02da5e9176822899dc11aa336de
same_boot_snapshot    1ea3d10abc0d2aa634d2d4318b6c96127c941bac20ba52fabe372629400f1be5
same_boot_cursor      6701c320d995330219485392c49c9fc369cbd8675442b8230eeba201853a52cc
host_tick             b1f85f7c3d3527ccb41bbb947ea3b7c621a3c8c6ec8c8128e641eb6cb23520bc
r0_before_manifest    22c58a83f0093c2a6108dc09d501f6c8a070cc12d2f48cd2b721d3eff360c1d3
r0_after_manifest     0b5f0d8a1928944332bc034c774f996521e39327db91fc3e7a4fae6949606028
r0_write_observation  cb4c5f80d50513344f28bcffa3e0d174e9c55d27762927e06518e41654033790
r0_target_manifest    00a1188ce8ba8bf043e8b2ec4debf79744e81635efed24f89f94aff2e3c88285
r0_process_identity   d9ed3d293c1599f03f6bd4c61a83db4be79e074c14a5073f1d40fb79983b8dbe
r0_process_kill       92df917c462ad025895acfb8f394ab35dc82068b2e617837b0b4ca23e67c6d7d
r0_cut_evidence       cde57711261dd06853664472b9a57c761238feb36a6bb773a1ccbc4877b04420
```

### 4.3 Deny-only staged receiver and revised C0–C7 cuts

Each receiver is one immutable generation-qualified bundle:

```text
${runtime_root}/bundles/<generation>-<bundle_digest>/
  bin/awa-registration-launcher
  bin/awa-registration-receiver
  contracts/awa-registration-owner-signers.v1
  engine/__init__.py
  engine/registration_host.py
  import-manifest.json
  runtime-config.json
  direct-receipt.json        # non-payload; bound separately
  bundle-projection.json     # non-payload; bound separately
```

`bundle_digest` is a domain-separated JCS hash of exact generation, relative
path, mode, size, and content hash for the payload set: receiver, launcher,
runtime files, import manifest, allowed-signers contract, and runtime config. The receipt and
bundle-local projection are excluded from that payload digest to avoid
self-reference. The bundle-local projection binds bundle/import/interpreter/
config/contract hashes without a receipt hash; the v3 receipt binds both
`bundle_digest` and `bundle_projection_hash`; the active pointer then binds
bundle generation/digest, bundle-local projection hash, and completed receipt
digest. The manifest includes package
initializers and is itself included. Installing N+1 creates only a new
`O_EXCL` bundle directory and never replaces N bytes, receipt, config, or
local projection.

Every bundle payload entry is relative and in-root. The selected absolute
interpreter is not copied into or represented as a payload entry; it is
descriptor-measured as the exact external-interpreter record in §4.2.1. Its hash is included in the
bundle manifest, wrapper-runtime hash, receipt, gate, projection, and
readiness authority.

The sole active file is `active-bundle.json`, containing exactly schema,
generation, bundle directory relative path, bundle digest,
bundle-projection hash, DIRECT receipt hash, external-interpreter hash, and
interpreter-capability hash. It is same-directory atomically replaced and
descriptor-revalidated. N remains immutable through C7.

The receiver supports two authority states without adding a protocol mode:

- **current/full:** receipt exactly matches current WRITABLE protocol; normal
  Body B policy may decide admission; and
- **staged/deny-only:** receipt exactly matches the staged N+1 tuple while
  current N is DRAINING; only a deterministic seam-valid denial is possible.

Every external hook/admission/startup/tick interface is deny-only: no
ordinary allow, episode/member creation, ordinary DATA, helper launch, or
protocol transition. The sole internal exception is installer-controlled
staged recovery under the member lock: SQL-v2's exact staged-lineage
MARK_UNAVAILABLE/REACQUIRE_EFFECT paths and the already-frozen four-action
helper plan. `RECEIVED`/`ACTIVATED` transfers custody only. Internal helper
I/O begins only after ACTIVATED, current member-lock ownership, and complete
semantic closure. Ordinary admission remains impossible until
ADVANCE_GENERATION plus current/full bundle/receipt/profile revalidation.

The proof vector has schema `awa-registration-staged-denial-proof/v2`. Its
`records` are canonical-JCS-byte-sorted and contain exactly two records for
every unique installed observable key:

```text
event, server_or_empty, discriminator, serializer_schema, signed role,
seam = DIRECT_RECEIVER | SHADOW_INSTALLED,
bundle_digest, request_hash, exact output_hash, exit_code
```

Set equality is mandatory. A missing/extra/duplicate observable, missing
seam, conflicting role, changed serializer, wrong output, or non-deny exit
fails the vector. The proof hash is:

```text
SHA256(ASCII("awa-registration-staged-denial-proof/v2") || 0x00 ||
       JCS({schema, records}))
```

Before owner signing, the installer deterministically builds this as an
**expected** vector from the signed inventory, exact synthetic request bytes,
serializer contract, bundle digest, and expected denial bytes/exit. It does
not claim execution. After staging, direct and shadow executions must produce
records that canonicalize byte-identically to that expected vector. Thus the
gate can bind the expected hash before protocol/CONTROL exists without
claiming the later proof occurred.

Its read-only readiness digest is:

```text
SHA256(ASCII("awa-registration-staged-readiness/v2") || 0x00 ||
  JCS({
    schema, mode="DENY_ONLY", current_protocol_hash, staged_epoch_hash,
    bundle_digest, direct_receipt_hash, import_manifest_hash,
    external_interpreter_hash, interpreter_capability_hash,
    measured_profile_hash, storage_dev, denial_proof_vector_hash
  }))
```

The fixed proof vector uses one `preToolUse` / empty-server / `Shell` /
`cursor-permission/v1` / `ordinary` observable with direct and shadow records,
the §4.2.1 bundle digest, request `H(7)`, output `H(8)`, and exit `"2"`.
Readiness uses protocol `H(1)`, staged epoch `H(2)`, the derived bundle,
receipt `H(3)`, derived import manifest, measured profile `H(a)`, and device
`"1"`:

```text
denial_proof_vector_hash
  c72a4fc31d3037732bf55305511f58dbf0b7f5f58377e98bd80a61461d53b4cd
readiness_digest
  77db8c1f786d2f10bd21574f2d56b8b867c90ec6898eea7d2f6032b0b48ecd77
```

Revised cuts:

Every `C0`–`C7` value in this table is explicitly a **cut label** and restart
coordinate, never an authorization or clearance. In particular, **cut C1**
is unrelated to **C1 shipping clearance**, which remains evidence-only.

| Cut | Last completed authority | Required deny-capable receiver | Restart action |
|---|---|---|---|
| C0 | Exact-head preflight only | Old receiver | Rerun preflight; no file/protocol claim |
| C1 | Immutable signed N+1 bundle installed; active pointer and N bundle/receipt untouched | N remains selected/enabled | Reopen and remeasure both immutable bundles and active N pointer |
| C2 | BEGIN_DRAIN + staged N+1 committed; complete direct+shadow proof vector passes while active pointer stays N | N remains selected/enabled | Revalidate DRAINING/staged/profile/import/proof vector; rerun complete vector |
| C3 | Under file lock, atomically point to N+1 while N remains enabled/restorable; complete post-switch vector passes; only then disable N entry | N+1 staged deny-only; N bundle retained | On failure atomically restore N pointer, revalidate N, then CANCEL only if existing pre-adoption predicate permits |
| C4 | One or more deterministic adoption passes attempted | New staged deny-only receiver | Resume from semantic closure and immutable audit |
| C5 | Exact ADVANCE predicates pass and every ADOPT/DRAINING-REACQUIRE staged-generation custody obligation is closed; stable RESOLVED/no-pending and blocked rows excluded | N+1 staged deny-only; N bundle retained | Continue bytewise member-id batches of eight; rerun typed completion query; deny ADVANCE until empty |
| C6 | ADVANCE_GENERATION committed; N+1 is current | New current receiver; R0 scope still deny-only | Revalidate full current authority before cleanup |
| C7 | Only after current N+1 verification, old N bundle and descriptor-proven residue cleaned/classified | New current receiver | Verify exact N+1 bundle/receipt/profile/proof; no protocol replay |

The installer never infers receiver continuity from file existence or a fake
control. R0 records the actual receiver path, receipt/gate/profile digests,
protocol/staged hashes, process exit, and exact seam output at every cut.

### 4.4 Fresh profile/device authority

Before candidate authorization and under the protocol lock:

1. require the separately authorized installer/candidate input contain one
   normalized absolute interpreter path; no PATH/cwd/environment inference;
2. descriptor-walk and measure its ancestry/file identity, then execute the
   isolated closed capability probe; unsupported candidates refuse before
   gate bytes, receipt, signature, protocol, or persistence;
3. measure current `ProfileBinding` from live descriptors and the exact
   interpreter/capability record;
4. require digest/device/APFS/interpreter/capability tuple equal current
   protocol/deployment authority;
5. measure staged `ProfileBinding` from the exact staged runtime/targets;
6. require digest/device/APFS/interpreter/capability tuple equal receipt and
   staged candidate;
7. require current/staged storage device and every required target device
   satisfy the existing same-device contract; and
8. repeat the applicable measurement before every positive C2–C7 operation,
   receiver open, and launcher exec.

For R0, all fixture targets exist before the first measurement and before
gate bytes are emitted. Signature verification precedes receipt/protocol/
CONTROL creation, then the complete target set is remeasured byte-for-byte
before `R0HarnessAuthority` is sealed.

`StoreControlAdapter` receives typed measured bindings, not naked candidate
objects. Any unavailable or changed measurement refuses before CONTROL. No
cached receipt string can substitute.

Observed machine evidence on 2026-09-29 found canonical Homebrew
`/opt/homebrew/opt/python@3.14/bin/python3.14`, Python 3.14.6, SQLite 3.53.3,
`Connection.setconfig`, and `SQLITE_DBCONFIG_DEFENSIVE`; that is supported
evidence for this machine, never a durable product path. Observed
`/usr/bin/python3` resolved to CommandLineTools Python 3.9.6/SQLite 3.51.0
without either API and is an explicit rejection case, never candidate
authority.

### 4.5 Isolated entrypoint and structured inventory

Every installed registration wrapper invokes an absolute measured Python
interpreter with `-I -S -B` and an absolute measured launcher. The exact
interpreter path comes only from signed `awa-registration-launcher-config/v1`;
the wrapper never resolves `python3`. The launcher:

- validates its own regular-file identity and exact bundle root;
- descriptor-reopens the signed interpreter path, reruns ancestry/file
  measurement, and requires exact external-interpreter and capability-probe
  hashes immediately before the first product import/exec;
- parses the closed import manifest using only the standard library;
- descriptor-opens and hashes every path before the first AWA product import;
- installs an import guard that refuses any later AWA-root path absent from
  the manifest;
- removes empty/cwd/user-site entries;
- inserts exactly the measured bundle root before importing;
- uses a closed environment allowlist required for HOME/XDG/AWA operation;
  and
- ignores ambient `PYTHONPATH`, `PYTHONHOME`, `PYTHONSTARTUP`,
  `PYTHONINSPECT`, and cwd.

The deterministic manifest generator begins from each installed entry module,
recursively resolves static imports beneath the AWA bundle, and
automatically adds every package-directory `__init__.py`. It rejects
unresolved AWA imports, computed module names, nonliteral `importlib` or
`__import__`, symlinks, duplicate normalized paths, and imports escaping the
bundle. Each record contains normalized relative path, role, mode, size, and
content hash; records are bytewise path sorted. Caller-supplied file lists
cannot add or omit records.

Interpreter, launcher, exact manifest bytes/hash, package initializers, and
every manifested file are members of `wrapper_runtime_hash` and
`bundle_digest`; interpreter record/capability hashes are separately included
in wrapper, receipt, gate, projection, active pointer, readiness, and R0
authority. The stable router uses a closed environment and execs only the
signed config path. Symlink, owner/mode/dev/inode/content/probe drift—or an
interpreter upgrade between signature and exec—fails closed at functioning
interfaces or reports honest runtime unavailability; it never falls back.

The invocation key is exactly:

```text
(event, server_or_empty, discriminator, serializer_schema)
```

Each signed inventory record adds one `role`, returned only after the unique
observable lookup. The inventory rejects any duplicate observable key,
including conflicting-role duplicates. `MatcherProof` retains exact
observable records. For MCP, server and tool identity cannot collapse into
one discriminator string. A returned `task_launch` role is denied before
ordinary admission.

### 4.6 Bounded parser and semantic admission

A non-recursive byte scanner enforces payload bytes, nesting depth, and node
count before `json.loads`. The parser catches `RecursionError` and
`MemoryError` only to produce bounded `PARSER_REJECT`; it never retries
unbounded input.

`B1 / E@R1 / B2 / R2` remains unchanged in shape. E@R1 now returns a typed
semantically validated snapshot. R2 revalidates selected semantic closure,
not only stored revision/hash equality. Profile, deployment gate, and
structured inventory are part of the same final READY decision.

### 4.7 Grant acknowledgement, secret transfer, and same-boot death

OPEN/REACQUIRE/ADOPT use one grant-finalization scope:

1. create secret and hold member lock;
2. commit exact executor hash and target closure;
3. construct and verify opaque capability;
4. return it only after caller acknowledgement boundary is ready; or
5. on any local failure, use the same lock/secret/status to commit existing
   `MARK_UNAVAILABLE`, then zero/release.

If step 5 cannot persist, the process exits without claiming recovery. The
next opportunity non-blockingly acquires the exact member lock. Success proves
no process still owns that lock; it then full-CASes the stored same-boot token
to `MARK_UNAVAILABLE` and uses existing REACQUIRE. PID, boot age, and a
missing acknowledgement alone never authorize takeover.

Staged transfer frames the exact member/effect/executor/operation/member-
tuple/status/protocol/staged-epoch hashes plus the secret. It has two
acknowledgements:

1. `RECEIVED`: receiver validated the frame but is forbidden to use the
   secret; sender still holds the member lock.
2. `ACTIVATED`: after `RECEIVED`, sender irreversibly marks its local
   capability unusable, promises never to reacquire/use it, and releases the
   lock; it retains secret bytes only for acknowledgement validation and
   zeroing. Receiver acquires that exact member lock, revalidates executor
   hash and complete semantic closure, then may acknowledge activation and
   perform I/O.

The sender zeroes after `ACTIVATED`; on timeout after releasing the lock it
zeroes and cannot use the lock-gated capability. Duplicate ack is a no-op.
Stale/cleared secret, mismatch, or loss rejects and clears/retries the same
effect through lock-authorized recovery. Possession without the member lock
is never execution authority.

Both waits use one absolute transfer deadline within the five-second drain
deadline. The receiver never waits for the member lock before sending
`RECEIVED`; the sender never holds the member lock while waiting for
`ACTIVATED`; neither side retries an ack. If `RECEIVED` is absent, sender
retains the lock and exact-clears. If activation times out after release, the
receiver may proceed only if it already holds the member lock and closure is
still exact; otherwise the deterministic same-boot selector clears the token.
This ordering has no circular wait, unbounded retry, or simultaneous
lock-authorized user.

C5 computes `unresolved_custody_obligations` from resulting authority, never
operation kind alone. Every committed operation whose target status installs
`executor_generation == staged_generation` enters the set. With SQL v2 those
granting operations are ADOPT_EFFECT and DRAINING REACQUIRE_EFFECT;
DRAINING OPEN_EFFECT is forbidden.

Each obligation binds exact granting audit id/kind, target member/effect,
target status hash, executor token hash/generation, staged epoch, and member
tuple. It closes only by: capability returned plus observed ACTIVATED in the
current driver; a later semantically valid action/close/MARK under that exact
token; or durable lock-authorized clear. Commit-before-return death for both
ADOPT and DRAINING REACQUIRE remains unresolved.

After driver restart, a busy staged member lock with no later operation is
conservatively unresolved and is waited only until the existing drain
deadline; lock release permits takeover, while deadline expiry uses existing
containment. Reconciliation processes bytewise member-id batches of eight
with continuation until the set is empty. ADVANCE explicitly refuses while
any obligation remains. A staged token is never inferred activated from its
row alone.

### 4.8 Monotonic no-op and ambiguity resolution

All structural mutation paths acquire the member lock, then freshly collect
the live basis. Caller observations are selection hints only. Equality with
current or pending authority is a zero-write no-op. A stale caller cannot
reinstall its older basis.

Duplicate member/episode installation resolves:

- exact immutable closure exists -> no-op and return it;
- insert operation is exact ABSENT -> retry same deterministic object once;
- any tuple differs -> conflict/non-authority; and
- unavailable read -> no claim.

Ambiguity resolution first validates the exact immutable operation row by
primary key, hash, class/kind, and directly referenced immutable companions.
That row is the monotonic commit witness; no history traversal is needed. If
its target is current, return the existing committed/applied class. If the
current selected tuple is semantically valid and has a later write sequence,
return existing COMMITTED or OBSOLETE as the resolver contract requires. It
never returns ABSENT merely because time advanced. Only a missing operation
plus the exact old predecessor is ABSENT and retryable. Invalid operation or
current closure returns PARTIAL/UNAVAILABLE and never retries.

### 4.9 Atomic creation/publication and fair lanes

Fresh schema installation:

1. hold the existing creation/protocol lock;
2. create one private same-directory candidate DB with `O_EXCL`;
3. execute canonical SQL v2 in one explicit transaction;
4. verify exact inventory/hash, integrity, foreign keys, and semantic empty
   genesis prerequisites;
5. before rename, re-prove canonical absence, fsync candidate, and attempt
   no-replace publication;
6. after any rename attempt, reopen descriptors and classify exactly
   `ABSENT | COMPLETE | UNAVAILABLE`; only COMPLETE continues;
7. on COMPLETE, configure supported WAL profile and freshly measure; and
8. preserve the primary failure while recording cleanup/residue outcome
   separately.

Before rename, failure guarantees canonical absence. After rename, no code
claims rollback-to-absence. Startup reconciliation uses exact operation id,
temp naming, descriptor identity, and expected hashes to classify canonical
file, journal, WAL, SHM, and temp residue; it removes only descriptor-proven
same-operation non-authority. `UNAVAILABLE` remains observable and blocks.

All private publishers use the same classification rule without creating a
new relation or framework. Receipt, bundle pointer, proof, tick, schema, and
cleanup tests independently inject write, file-fsync, rename, directory-fsync,
reopen, and unlink faults. Cleanup failure never replaces the primary error
and residue is never reported absent unless reobserved absent.

Fairness keeps eight lanes and a five-second selected-batch budget. The parent
passes only serializable due descriptors. Each spawned worker opens its own
service, acquires exactly one member lock, performs OPEN/REACQUIRE/helper/
result or exact yield, and exits. Process death releases that member lock;
the coordinator then runs the same-boot takeover path. Eight blocked workers
must overlap; a ninth remains next-tick work.

Same-boot recovery is a separate deterministic lane before due work. Event,
startup, and explicit retry inspect their exact selected member directly.
Tick opens one read transaction, snapshots current protocol and every
EFFECT_IN_FLIGHT row with current-boot non-null executor, orders by bytewise
`member_id`, and computes §4.2.1's candidate/status/token snapshot hash.

It then reads the existing private host-tick v2 receipt. A cursor is current
only when receipt framing/hash/freshness, boot, protocol sequence/hash, cursor
hash, and last observed result are exact. If the last member remains a
candidate, current status must equal `last_post_status_hash`; if it no longer
qualifies, the boundary remains valid only with
`NO_LONGER_CANDIDATE`. Changes to other candidates do not make the cursor
authority and do not reset ordering.

With a current cursor, selection begins strictly after `last_member_id`. If
none remains, it wraps once to the lowest member id and sets `wrapped=true`.
It continues strictly upward on subsequent ticks. At the end of that wrapped
pass, it publishes the empty cursor and the next cycle restarts at the lowest
id. Missing, malformed, old-boot, stale-protocol, stale-last-status, or stale
receipt restarts deterministically at the lowest id.

Each batch examines at most eight. Nonblocking lock busy is `BUSY_LIVE`,
performs no mutation, records identical pre/post status hashes, and still
advances the cursor; therefore low live executors cannot starve later IDs.
Acquired locks revalidate semantic closure and exact status/token before
MARK/REACQUIRE. The host-tick receipt is published after the batch and bound
to the protocol/result snapshot. A crash before publication may repeat only
idempotent examination; it grants no liveness claim.

Lock acquisition plus exact status/token CAS—not the cursor, PID, age, or
receipt—permits takeover. The cursor never authorizes work, admission,
cleanup, or removal. Stable RESOLVED and blocked REQUESTED rows are not
candidates.

R1 performs one dedicated read-only preflight before any same-boot, reboot,
due, helper, or status mutation:

```text
select_r1_scope(authorized_member_id, boot_id, now) -> {
  authorized_same_boot: zero_or_one,
  authorized_due: zero_or_one,
  authorized_reboot: zero_or_one,
  outside_scope_same_boot: bool,
  outside_scope_due: bool,
  outside_scope_reboot: bool
}
```

Any true outside-scope flag refuses the entire tick with zero mutation.

## 5. Three revised implementation bodies — all NO-GO

### Body A — store authority, semantic closure, and executor primitives

Tests first:

- reservation floor/floor−1 and mandatory projection vectors;
- fourth-cycle typed zero-write exhaustion, forged-result rejection, and
  proof that Body A/runtime exposes no CONTROL constructor;
- one-column semantic mutation across all seven rows, JCS blobs, backlinks,
  action chains, descendant lineage, and current/staged protocol;
- post-COMMIT/pre-return grant faults for OPEN, ADOPT, and DRAINING
  REACQUIRE;
- two-way staged-secret transfer faults;
- canonical SQL-v2 extraction/hash/inventory/97-leaf checks;
- fresh-schema statement/commit/fsync/rename/reopen classification and native
  `SQLITE_FULL`/`SQLITE_IOERR` matrices;
- boolean-as-integer rejection;
- current/staged `ProfileBinding`, supported/rejected interpreter capability,
  API/SQLite-floor, and APFS/device swaps; and
- commit-followed-by-later-state ambiguity vectors.

Then change only the existing Body A surfaces:

- `registration_store.py`, `registration_schema.py`,
  `registration_profile.py`, `registration_jcs.py`,
  `registration_executor.py`, and their Body A tests;
- generate/pin canonical SQL v2 only through §4.1's exact transformation;
- add narrowly fenced staged-lineage MARK/REACQUIRE in existing leaves;
- typed semantic snapshots and typed current/staged profile bindings;
- classified fresh install; conservative global charging; finite recovery
  reserve; monotonic resolvers; and
- grant/transfer cleanup plus process-memory-only typed exhaustion using
  existing operations and phases.

**Body A stop:** any fix needs SQL bytes other than exact v2, a tenth trigger,
new leaf key, new operation, new effect outcome, new transaction class, new
lock order, or PID authority.

### Body B — observation, admission, recovery, and fairness

Tests first:

- old/new basis interleavings in both commit orders;
- duplicate member and episode races at 2/8/32 processes;
- deep/wide/duplicate/truncated JSON through the real serializer;
- killed same-boot worker after every grant boundary;
- host-tick cursor missing/stale/current/wrap/busy vectors;
- eight concurrent mutating lanes, >8 same-boot recovery continuation, and
  R1 same-boot/due/reboot scope positions 1/8/9;
- selected-row miss, cleanup failure, and exact no-op behavior; and
- admission after semantic closure mutation and later-state resolution.

Then change only the existing Body B surfaces:

- `registration_admission.py`, `registration_runtime.py`,
  `registration_basis.py`, `registration_view.py`, and focused tests;
- collect fresh basis under the member lock through A's typed API;
- use automatic lock-proven same-boot recovery before due work and the typed
  R1 canary selector;
- map typed recovery exhaustion only to existing
  `CONTAINMENT_UNAVAILABLE` plus ADR 0020 RED, with no CONTROL access;
- keep process workers independent and serializable; and
- consume structured inventory and typed semantic snapshots supplied by C/A.

**Body B stop:** any fix introduces a queue relation, scheduler phase,
unbounded retry/sleep, parent-derived child authority, or cleanup authority.

### Body C — deployment authority, receiver continuity, and truthful R0

Tests first:

- exact receipt-v3/owner-gate-v2 R0/R1/R2 vectors, stock OpenSSH sign/verify,
  key-enrollment/contract negatives, and every-field mutation;
- every §4.2.1 schema/domain/preimage/vector, including external interpreter,
  bundle/projection/pointer, cursor/tick, and R0 evidence;
- import-manifest authority-hash versus exact JCS+LF payload-size/plain-hash
  equality and shared runtime-path byte equality;
- versioned bundle/pointer identity and old-bundle retention through C7;
- generated transitive import manifest including package initializers;
- rejected `/usr/bin/python3` shape, supported fixture, explicit-path versus
  PATH substitution, symlink/owner/mode/inode/content/probe mutation, missing
  setconfig/defensive API, SQLite below floor, signature-to-exec upgrade, and
  shadow `engine`/cwd/PYTHONPATH/PYTHONHOME/sitecustomize;
- observable event/server/discriminator/serializer lookup plus signed-role
  cross-product and conflicting-duplicate refusal;
- complete sorted direct+shadow staged-denial vector, including malformed
  output and one missing seam per observable;
- C0–C7 real process kill/restart with >8 adoption members;
- C5 restart before/after every ADOPT/DRAINING-REACQUIRE commit/return/
  activation/clear with >8 custody continuation;
- R1 canary at same-boot/due/reboot positions 1/8/9;
- acceptance packet/promotion/recovery mode drift on every backing file;
  held-candidate substitution/link/metadata and post-rename destination races;
  post-file/parent-fsync stale-snapshot barriers; deterministic PRE/POST
  target/residue matrices in both directions; classified-residue replacement
  or rename immediately after pair validation and before unlink in forward
  and reverse cleanup; and exact-receipt retry with zero fsync before malformed
  or mismatched-owner refusal, followed by authorized finalization and
  post-fsync revalidation after permitted outside-row index additions without
  deriving a live vector;
- descriptor ownership/cleanup faults at every named `open`, `fstat`,
  `checked_directory`, `fchmod`, file fsync, parent fsync, `flock`, and path
  rebind point in `open_repo_descriptor`, `swap_known_pair`,
  `open_state_parent`, `acquire_lock`, and `retire_known_residue`; exact close
  counts, return-only ownership transfer, all-close attempts, primary
  exception identity/secondary cleanup context, lone-close surfacing, and no
  receipt/success are mandatory;
- receipt/bundle-pointer/proof/tick short-write/fsync/replace/reopen/residue
  faults; exact-byte acceptance promotion crash matrix; and
- R0 evidence-schema/live-surface-manifest negatives that reject an
  unobserved claim or escaped target.

Then change only existing Body C surfaces plus one narrow isolated launcher:

- `registration_projection.py`, `registration_installer.py`,
  `registration_receiver.py`, `registration_host.py`, hook-owner v4
  projection/installer paths, registration shell wrappers, R0 harness, and
  focused tests;
- exact-byte acceptance checker/promotion receipt; owner-gate v2,
  receipt-v3, offline signer contract/enrollment, immutable bundle and
  generated import manifest;
- revised C0–C7 pointer/rollback driver and complete staged denial proof;
- external staged interfaces remain deny-only; installer-internal recovery
  invokes frozen helpers only after ACTIVATED+lock+closure;
- unique observable inventory with signed-role policy; and
- exact R0 evidence; and
- only its already-authenticated `StoreControlAdapter` may consume exact
  exhaustion and attempt existing containment after hash revalidation.

**Body C stop:** any fix adds a persistent journal, fifth mode, external-owner
path, new live host writer, new reason, or ordinary admission before advance.

### C1 evidence-only boundary

C1 still only runs, captures, and adjudicates A/B/C-owned harnesses. It
creates no production helper, fixture framework, relation, trigger, phase,
mode, reason, operation, or fourth body.

## 6. Complete A01–A29/A32 acceptance mapping

Every row remains mandatory. “Retained” means v3 evidence must be rerun at
the v4 exact implementation head; it is not grandfathered. The finding map
in §3 is the sole remediation-owner assignment. When an A-row owned by a
different body contributes evidence, this table marks it **provider** rather
than transferring finding ownership.

| ID | V4 required evidence | Owner | Finding coverage |
|---|---|---|---|
| A01 | Extract §4.1 SQL v2 from SQL v1; exact output hash; 7/9/97 inventory/independent leaf equality; fresh install classifies pre-rename absence and post-rename ABSENT/COMPLETE/UNAVAILABLE | A | P1-04; P2-06 provider |
| A02 | Closed JCS/preimages/backlinks; boolean rejected at every integer; exact receipt/bundle/signing blob derivations | A | P2-01; P1-08 provider |
| A03 | Published profile plus supported/rejected interpreter capability vectors; fresh current/staged/R0 descriptor/APFS/device/API binding and swap kills | A | P1-07/P1-08 provider |
| A04 | DB/WAL/SHM/proof/bundle/projection/legacy/root/Git retain exact device/APFS contract; external interpreter retains separately signed device/file identity | A | P1-03; P1-07 provider |
| A05 | Every write rechecks profile/free space; unvalidated effects charge SQL maxima; 98,304/32,768 floors, three cycles, and typed zero-write exhaustion are exact | A | P1-03, P1-05 |
| A06 | Total NULL/carry/predicate mutation corpus; exact first-effect/predecessor/supersession/adoption closure; independent WRITABLE/DRAINING leaf kills | A | P1-03, P1-04 |
| A07 | Append-only authorizer and named statements; only exact staged-lineage MARK/REACQUIRE DATA works in DRAINING; runtime/actor/typed-result cannot construct CONTROL | A | P1-04, P1-05; P1-08 provider |
| A08 | OPEN remains sole FIRST_EFFECT DATA exception with exact provenance; no v4 change | A | Retained |
| A09 | OPEN/pre-I/O/append/close/unavailable CAS plus post-COMMIT/pre-return OPEN/ADOPT/DRAINING-REACQUIRE fault matrix; no orphan custody | A | P1-05, P1-10 provider |
| A10 | Three phases, INSTALL closure, and exact duplicate member/episode closure API | A | P2-05 provider |
| A11 | Four-action replay; external deny/internal activated-helper separation; bounded two-ack transfer; DRAINING same-effect reacquire; lost-ack/dead-peer matrix | A | P1-05; P1-06 provider |
| A12 | SUCCESS/conflict/SUPERSEDED disjoint closure; outcome reserve preserves base close plus recovery carve-out | A | P1-03, P1-05 |
| A13 | RESOLVED conditional handoff/no-op, duplicate-ensure convergence, and fresh-under-lock basis in both event orders | B | P2-05 |
| A14 | `member_epoch` remains sole revision across current/pending/status/handoff/adoption | A | Retained |
| A15 | Fresh DRAINING boot/deadline samples and SQL-v2 staged-lineage recovery predicates | A | P1-04 |
| A16 | Stage/cancel/advance fences, SQL-v2 hash equality, storage device, and fresh profile bindings | A | P1-04; P1-10 provider |
| A17 | Pre-effect DORMANT proof; typed exhaustion can reach existing containment only through authenticated StoreControlAdapter; failed cut uses existing CANCEL predicates | A | P1-05; P1-09 provider |
| A18 | Old-boot clear plus event/startup/retry direct and host-tick-v2 cursor same-boot takeover | B | P1-11 |
| A19 | >8 recovery/due members, busy-live cursor advancement, wrap/restart continuation, concurrent workers, miss/yield suspension | B | P1-11, P2-03 |
| A20 | Member-isolated B1/E@R1/B2/R2 consumes semantically validated snapshots and one pre-mutation R1 same-boot/due/reboot scope result | B | P1-03 provider; P1-11, P2-05 |
| A21 | Task/external staged first-deny; unique observable lookup returning signed role; internal activated-lock-closure helper boundary | C | P1-06, P1-07 |
| A22 | Candidate digest unchanged; hash-checked Gate 2 launcher/checker, exact source/recovery packet, hash+mode state classification, held-candidate promotion, four-POST canonical receipt, receipt-first idempotency, semantic envelope, immediate descriptor ownership and return-only transfer; every §4.2.1 interpreter/probe/bundle/deployment preimage/vector; import JCS+LF payload equality; signing trust; immutable proof; staged C5 custody; R1/R2 scope | C | P1-01, P1-02, P1-06, P1-07, P1-08, P1-09, P1-10; P2-06; P3-02 |
| A23 | Fail-open/exhaustion evidence truth; interpreter substitution/drift/upgrade and transitive import/shadow corpus; deterministic classified target/residue pairs, stale-snapshot rejection, primary-error/residue honesty, all-descriptor cleanup and exact-primary preservation; finite R0 vectors | C | P1-05 provider; P1-07, P1-12, P2-06; P3-01, P3-02 |
| A24 | One status row/member and READY only after selected closure, fresh profile/interpreter capability, signed bundle/import manifest, and unique inventory | B | P1-03/P1-07 provider |
| A25 | Deterministic rendering; deep malformed JSON yields bounded parser denial; no presentation state | B | P2-02 |
| A26 | Dirty/in-progress bytes unchanged; exact duplicate no-op and fresh-under-lock basis add no preservation behavior | B | P2-05 |
| A27 | Five-second drain; SQL-v2 recovery; two-ack custody; exact ADOPT/DRAINING-REACQUIRE C5 closure; advance/CANCEL/containment | A | P1-05; P1-09/P1-10 provider |
| A28 | Close/successor/reacquire/adopt resolvers remain monotonic across later valid state and all fault classes | A | P2-04 |
| A29 | ADR 0020 alert authority and guard/finish/cleanup/active-root/kernel-off independence remain byte/behavior compatible | C | Retained |
| A32 | Low-free and recovery-exhaustion zero write; native FULL/IOERR resolution; typed unavailable vs adapter containment; pre/post-rename and residue honesty | A | P1-03, P1-05; P2-06 provider |

No A30 or A31 exists. C1 is absent from owner/provider columns by design.

## 7. Verification, review, and evidence cadence

### 7.1 Exact-byte document acceptance

Acceptance uses one normalized body and one checker-produced vector. Constants:

```text
DOMAIN = ASCII("awa-registration-v4-acceptance-body/v1") || 0x00
SENTINEL = ASCII("__AWA_V4_ACCEPTED_STATUS_TOKEN_V1__")
U64 = unsigned 64-bit big-endian
```

Surfaces are framed in this exact path order:

1. `docs/adr/0026-durable-registration-authority-hardening.md` — complete
   bytes;
2. `docs/adr/README.md` — exact ADR 0026 row including LF;
3. `docs/plans/README.md` — exact v4 row including LF; and
4. `docs/plans/native-entry-durable-registration-v4.md` — complete bytes.

Each backing file must be strict UTF-8/LF, contain no CR/NUL, and end in
exactly one LF. Each surface must contain exactly one of its complete
OLD_CONTEXT or NEW_CONTEXT, never both. The exact token transitions are:

```text
docs/adr/0026-durable-registration-authority-hardening.md
OLD_CONTEXT = "Status: draft — 2026-09-29 (governance only; implementation and R0 NO-GO)\n"
OLD_TOKEN = "draft"
NEW_TOKEN = "accepted"

docs/adr/README.md
OLD_CONTEXT = "| [0026](0026-durable-registration-authority-hardening.md) | Draft — 2026-09-29 | Conditionally supersede ADR 0025 with canonical SQL v2, typed recovery boundaries, installer-selected measured interpreter capability, external-deny/internal custody, complete authority preimages, restart-stable recovery, offline owner gates, and separately gated evidence. |\n"
OLD_TOKEN = "Draft"
NEW_TOKEN = "Accepted"

docs/plans/README.md
OLD_CONTEXT = "| `native-entry-durable-registration-v4.md` | DRAFT — GOVERNANCE ONLY; IMPLEMENTATION AND R0 NO-GO — 2026-09-29 | Conditional v3 successor with exact SQL v2, typed exhaustion, measured installer-selected interpreter, staged custody and >8 recovery, closed authority vectors, generation bundles, offline signing, status-last acceptance, three bodies, and finite-scope R0. |\n"
OLD_TOKEN = "DRAFT"
NEW_TOKEN = "ACCEPTED"

docs/plans/native-entry-durable-registration-v4.md
OLD_CONTEXT = "- **Status:** DRAFT (for review) — GOVERNANCE ONLY; IMPLEMENTATION AND R0 NO-GO\n"
OLD_TOKEN = "DRAFT (for review)"
NEW_TOKEN = "ACCEPTED — FROZEN"
```

For each entry `NEW_CONTEXT` is mechanically
`OLD_CONTEXT[:token_start] || NEW_TOKEN || OLD_CONTEXT[token_end:]`; dates,
descriptions, punctuation, and every non-token byte are fixed.

For each surface, replace only the selected token span with `SENTINEL`, then
frame:

```text
normalized_body = DOMAIN
for surface in exact order:
  normalized = surface_prefix || SENTINEL || surface_suffix
  normalized_body ||= U64(len(UTF8(path))) || UTF8(path)
  normalized_body ||= U64(len(normalized)) || normalized
normalized_digest = lowercase_hex(SHA256(normalized_body))
```

`source_commit` is not “the current branch” or a later merge base. It is
exactly `8356a60cb30ea02953149f9bea61fd1c04f2c7de`, the live remote `main`
revision from which this documentation branch was created. Packet generation
and promotion both require `git rev-parse HEAD` and a fresh
`git ls-remote origin refs/heads/main` to equal that value. Any later remote
advance invalidates the packet and requires a new draft revision and owner
decision; no executor substitutes a local `main` ref, abbreviation, tree OID,
or implementation-head OID.

#### Canonical acceptance checker

The canonical checker artifact is the exact UTF-8/LF payload between the
following begin/end markers: the opening/closing fence and marker lines are
excluded; the payload starts with `from __future__` and includes the LF after
`main()`. `checker_sha256` is lowercase SHA-256 of exactly those payload
bytes. The payload is normative, self-contained, Python-standard-library only,
and is the sole Gate 2 packet/parser/promotion/recovery algorithm. An executor
extracts and runs it in memory; no future repository or machine-local checker
file may substitute for it.

<!-- awa-v4-acceptance-checker:v1:begin -->
```python
from __future__ import annotations

import base64
import ctypes
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import struct
import subprocess
import sys
import time

SOURCE_COMMIT = "8356a60cb30ea02953149f9bea61fd1c04f2c7de"
REPOSITORY = "KleinPerkins/awa"
ALGORITHM = "awa-registration-v4-acceptance-body/v1"
DOMAIN = ALGORITHM.encode("ascii") + b"\x00"
SENTINEL_TEXT = "__AWA_V4_ACCEPTED_STATUS_TOKEN_V1__"
SENTINEL = SENTINEL_TEXT.encode("ascii")
OWNER_SCHEMA = "awa-registration-v4-owner-acceptance/v2"
PACKET_SCHEMA = "awa-registration-v4-acceptance-packet/v2"
RECOVERY_SCHEMA = "awa-registration-v4-recovery-vector/v1"
OWNER_PREFIX = (
    "Accept ADR 0026 and native-entry-durable-registration-v4 only for "
    "this exact semantic Gate 2 envelope:\n"
).encode("ascii")
RECEIPT_SCHEMA = "awa-registration-v4-acceptance-promotion/v2"
PLAN_REL = "docs/plans/native-entry-durable-registration-v4.md"
RECEIPT_REL = (
    "awa/governance/native-entry-durable-registration-v4/"
    "acceptance-promotion.json"
)
CHECKER_BEGIN = (
    b"<!-- awa-v4-" + b"acceptance-checker:v1:begin -->\n```python\n"
)
CHECKER_END = (
    b"```\n<!-- awa-v4-" + b"acceptance-checker:v1:end -->"
)
RENAME_SWAP = 0x00000002
RENAME_EXCL = 0x00000004
LIBC = ctypes.CDLL(None, use_errno=True)
try:
    RENAMEATX = LIBC.renameatx_np
except AttributeError:
    RENAMEATX = None
if RENAMEATX is not None:
    RENAMEATX.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    RENAMEATX.restype = ctypes.c_int


def b64(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


SPECS = (
    (
        "docs/adr/0026-durable-registration-authority-hardening.md",
        "FULL_FILE",
        b64(
            "Status: draft — 2026-09-29 "
            "(governance only; implementation and R0 NO-GO)\n"
        ),
        "draft",
        "accepted",
    ),
    (
        "docs/adr/README.md",
        "EXACT_ROW",
        b64(
            "| [0026](0026-durable-registration-authority-hardening.md) "
            "| Draft — 2026-09-29 | Conditionally supersede ADR 0025 with "
            "canonical SQL v2, typed recovery boundaries, installer-selected "
            "measured interpreter capability, external-deny/internal custody, "
            "complete authority preimages, restart-stable recovery, offline "
            "owner gates, and separately gated evidence. |\n"
        ),
        "Draft",
        "Accepted",
    ),
    (
        "docs/plans/README.md",
        "EXACT_ROW",
        b64(
            "| `native-entry-durable-registration-v4.md` | DRAFT — "
            "GOVERNANCE ONLY; IMPLEMENTATION AND R0 NO-GO — 2026-09-29 | "
            "Conditional v3 successor with exact SQL v2, typed exhaustion, "
            "measured installer-selected interpreter, staged custody and >8 "
            "recovery, closed authority vectors, generation bundles, offline "
            "signing, status-last acceptance, three bodies, and finite-scope "
            "R0. |\n"
        ),
        "DRAFT",
        "ACCEPTED",
    ),
    (
        PLAN_REL,
        "FULL_FILE",
        b64(
            "- **Status:** DRAFT (for review) — GOVERNANCE ONLY; "
            "IMPLEMENTATION AND R0 NO-GO\n"
        ),
        "DRAFT (for review)",
        "ACCEPTED — FROZEN",
    ),
)

GATE_2A_EVIDENCE = {
    "algorithm": "ssh-ed25519",
    "contract_path": "contracts/awa-registration-owner-signers.v1",
    "contract_sha256":
        "9155be780c73e65a549ae97326dc56c53045aeaddb697745a95ce191aa472b7e",
    "key_enrollment_digest":
        "0747f869d74ce03debdd91992050a59e2b0a587fa103c9f4ef251220efbf24c9",
    "namespace": "awa-registration-owner-gate-v2",
    "openssh_fingerprint":
        "SHA256:zMkoOQbGEq7TiPI79e8m8WoKeAkmpEfb6MfnGpS032M",
    "owner_authorization_digest":
        "dd24db871dc0fd7806371ac7113007e3c9c267f181273a2b290b5968588ee4fe",
    "principal": "KleinPerkins",
    "public_key_sha256":
        "3909ecbba5d835cbfdcf7f1498af2338dccd210e5fa780edf04799e869843565",
    "status": "OWNER_AUTHORIZED_NOT_PUBLISHED",
}

AUTHORIZED_ACTIONS = [
    "PROMOTE_EXACTLY_FOUR_STATUS_TOKENS",
    "PUBLISH_ONE_DETACHED_ACCEPTANCE_RECEIPT",
]
DENIED_IMPLICATIONS = [
    "ACCEPT_OR_EDIT_OTHER_DOCUMENTS",
    "COMMIT_PUSH_OR_OPEN_PR",
    "CREATE_OWNER_KEY_CURRENT_RECEIPT",
    "CREATE_SIGNER_CONTRACT",
    "IMPLEMENT_OR_DELIVER",
    "INSTALL_ACTIVATE_RELEASE_OR_ROLL_OUT",
    "RUN_R0_R1_C1_OR_R2",
]


def fail(message: str) -> None:
    raise SystemExit(message)


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def jcs(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def strict_json(value: bytes) -> object:
    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in items:
            if key in result:
                fail("duplicate JSON key")
            result[key] = item
        return result

    try:
        return json.loads(value.decode("utf-8"), object_pairs_hook=pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        fail(f"invalid acceptance JSON: {error}")


def run_git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()


def repository_root() -> Path:
    root = Path(run_git(Path.cwd(), "rev-parse", "--show-toplevel"))
    if (
        not root.is_absolute()
        or Path(os.path.normpath(root)) != root
        or root.resolve(strict=True) != root
    ):
        fail("repository root is not normalized, absolute, and symlink-free")
    return root


def require_platform() -> None:
    required = (
        sys.platform == "darwin",
        hasattr(os, "O_NOFOLLOW"),
        hasattr(os, "O_DIRECTORY"),
        os.open in os.supports_dir_fd,
        os.stat in os.supports_dir_fd,
        os.stat in os.supports_follow_symlinks,
        RENAMEATX is not None,
    )
    if not all(required):
        fail("required Darwin descriptor/no-follow/renameatx primitives absent")


def require_source(root: Path) -> None:
    if run_git(root, "rev-parse", "HEAD") != SOURCE_COMMIT:
        fail("HEAD does not equal source_commit")
    rows = run_git(root, "ls-remote", "origin", "refs/heads/main").splitlines()
    expected = f"{SOURCE_COMMIT}\trefs/heads/main"
    if rows != [expected]:
        fail("live remote main does not equal source_commit")


def receipt_path() -> Path:
    configured = os.environ.get("XDG_STATE_HOME")
    base = Path(configured) if configured else Path.home() / ".local" / "state"
    if not base.is_absolute() or base != Path(os.path.normpath(base)):
        fail("state home is not normalized absolute")
    return base / RECEIPT_REL


def checker_bytes(plan: bytes) -> bytes:
    if plan.count(CHECKER_BEGIN) != 1 or plan.count(CHECKER_END) != 1:
        fail("checker markers are not unique")
    payload = plan.split(CHECKER_BEGIN, 1)[1].split(CHECKER_END, 1)[0]
    if not payload.startswith(b"from __future__") or not payload.endswith(
        b"main()\n"
    ):
        fail("checker payload framing is invalid")
    payload.decode("utf-8", "strict")
    if b"\r" in payload or b"\x00" in payload:
        fail("checker payload is not canonical UTF-8/LF")
    return payload


def strict_backing(value: bytes, path: str) -> None:
    try:
        value.decode("utf-8", "strict")
    except UnicodeDecodeError:
        fail(f"{path}: non-UTF-8")
    if b"\r" in value or b"\x00" in value:
        fail(f"{path}: CR or NUL")
    if not value.endswith(b"\n") or value.endswith(b"\n\n"):
        fail(f"{path}: final LF is not exact")


def relative_parts(path: str) -> tuple[str, ...]:
    pure = PurePosixPath(path)
    if (
        pure.is_absolute()
        or not pure.parts
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        fail(f"{path}: invalid relative path")
    return pure.parts


def checked_directory(descriptor: int, label: str, owner_only: bool) -> None:
    metadata = os.fstat(descriptor)
    if not stat.S_ISDIR(metadata.st_mode):
        fail(f"{label}: not a directory")
    if owner_only and (
        metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        fail(f"{label}: directory is not owner-only")


def close_owned_descriptors(
    *descriptors: int | None,
    primary: BaseException | None = None,
) -> None:
    cleanup_error: BaseException | None = None
    for descriptor in descriptors:
        if descriptor is None:
            continue
        try:
            os.close(descriptor)
        except BaseException as error:
            if cleanup_error is None:
                cleanup_error = error
    if primary is not None:
        if cleanup_error is not None:
            raise primary from cleanup_error
        raise primary
    if cleanup_error is not None:
        raise cleanup_error


def open_repo_descriptor(root: Path) -> int:
    descriptor = os.open(
        root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    )
    try:
        checked_directory(descriptor, str(root), False)
        verify_repo_anchor(root, descriptor)
    except BaseException as error:
        close_owned_descriptors(descriptor, primary=error)
    return descriptor


def verify_repo_anchor(root: Path, descriptor: int) -> None:
    parent = open_absolute_directory(root.parent, False)
    try:
        visible = entry_metadata(parent, root.name)
        opened = os.fstat(descriptor)
        if (
            visible is None
            or not stat.S_ISDIR(visible.st_mode)
            or (visible.st_dev, visible.st_ino)
            != (opened.st_dev, opened.st_ino)
        ):
            fail("repository root identity changed")
    except BaseException as error:
        close_owned_descriptors(parent, primary=error)
    close_owned_descriptors(parent)


def open_absolute_directory(path: Path, owner_only: bool) -> int:
    if not path.is_absolute() or Path(os.path.normpath(path)) != path:
        fail(f"{path}: directory path is not normalized absolute")
    descriptor: int | None = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:]:
            child = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=descriptor,
            )
            try:
                close_owned_descriptors(descriptor)
            except BaseException as error:
                descriptor = None
                close_owned_descriptors(child, primary=error)
            descriptor = child
        checked_directory(descriptor, str(path), owner_only)
        return descriptor
    except BaseException as error:
        close_owned_descriptors(descriptor, primary=error)


def open_parent(root_descriptor: int, path: str) -> tuple[int, str]:
    parts = relative_parts(path)
    descriptor = os.dup(root_descriptor)
    try:
        for component in parts[:-1]:
            child = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = child
        return descriptor, parts[-1]
    except BaseException:
        os.close(descriptor)
        raise


def entry_metadata(parent: int, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        return None


def open_regular(parent: int, name: str, label: str) -> int:
    metadata = entry_metadata(parent, name)
    if metadata is None:
        fail(f"{label}: absent")
    if not stat.S_ISREG(metadata.st_mode):
        fail(f"{label}: present but not regular")
    descriptor = os.open(
        name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
    )
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.geteuid()
            or opened.st_nlink != 1
            or (opened.st_dev, opened.st_ino)
            != (metadata.st_dev, metadata.st_ino)
        ):
            fail(f"{label}: not one stable owner-held regular file")
    except BaseException as error:
        close_owned_descriptors(descriptor, primary=error)
    return descriptor


def read_descriptor(descriptor: int) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    while True:
        chunk = os.read(descriptor, 131072)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def read_relative(root_descriptor: int, path: str) -> tuple[bytes, int]:
    parent, name = open_parent(root_descriptor, path)
    try:
        descriptor = open_regular(parent, name, path)
        try:
            metadata = os.fstat(descriptor)
            value = read_descriptor(descriptor)
            after = os.fstat(descriptor)
            if (
                metadata.st_dev,
                metadata.st_ino,
                metadata.st_size,
                metadata.st_mtime_ns,
            ) != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            ):
                fail(f"{path}: changed during descriptor read")
            return value, stat.S_IMODE(metadata.st_mode)
        finally:
            os.close(descriptor)
    finally:
        os.close(parent)


def renameatx(
    source_parent: int,
    source: str,
    target_parent: int,
    target: str,
    flags: int,
) -> None:
    if RENAMEATX is None:
        fail("renameatx_np unavailable")
    result = RENAMEATX(
        source_parent,
        os.fsencode(source),
        target_parent,
        os.fsencode(target),
        flags,
    )
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), target)


def replace_context(
    value: bytes, context: bytes, old: bytes, new: bytes, path: str
) -> bytes:
    if value.count(context) != 1:
        fail(f"{path}: context is not unique")
    if context.count(old) != 1:
        fail(f"{path}: token is not unique in context")
    return value.replace(context, context.replace(old, new, 1), 1)


def surfaces(root_descriptor: int) -> tuple[list[dict[str, str]], str]:
    rows: list[dict[str, str]] = []
    normalized = bytearray(DOMAIN)
    for ordinal, (path, kind, encoded, old_text, new_text) in enumerate(
        SPECS, 1
    ):
        current, mode = read_relative(root_descriptor, path)
        if mode != 0o644:
            fail(f"{path}: backing mode is not canonical 0644")
        strict_backing(current, path)
        old_context = base64.b64decode(encoded, validate=True)
        old = old_text.encode("utf-8")
        new = new_text.encode("utf-8")
        new_context = old_context.replace(old, new, 1)
        old_count = current.count(old_context)
        new_count = current.count(new_context)
        if (old_count, new_count) == (1, 0):
            pre_backing = current
            post_backing = replace_context(
                current, old_context, old, new, path
            )
        elif (old_count, new_count) == (0, 1):
            post_backing = current
            pre_backing = replace_context(
                current, new_context, new, old, path
            )
        else:
            fail(f"{path}: neither exact pre nor exact post context")
        pre_surface = pre_backing if kind == "FULL_FILE" else old_context
        post_surface = post_backing if kind == "FULL_FILE" else new_context
        normalized_surface = replace_context(
            pre_surface, old_context, old, SENTINEL, path
        )
        path_bytes = path.encode("utf-8")
        normalized.extend(struct.pack(">Q", len(path_bytes)))
        normalized.extend(path_bytes)
        normalized.extend(struct.pack(">Q", len(normalized_surface)))
        normalized.extend(normalized_surface)
        rows.append(
            {
                "file_mode": format(mode, "04o"),
                "kind": kind,
                "new_token": new_text,
                "old_token": old_text,
                "ordinal": str(ordinal),
                "path": path,
                "post_backing_file_sha256": sha256(post_backing),
                "post_surface_sha256": sha256(post_surface),
                "pre_backing_file_sha256": sha256(pre_backing),
                "pre_surface_sha256": sha256(pre_surface),
            }
        )
    return rows, sha256(bytes(normalized))


def recovery_vector(
    rows: list[dict[str, str]],
    normalized_digest: str,
    checker_hash: str,
) -> dict[str, object]:
    return {
        "checker_sha256": checker_hash,
        "normalized_digest": normalized_digest,
        "ordered_surfaces": rows,
        "repository": REPOSITORY,
        "schema": RECOVERY_SCHEMA,
        "source_commit": SOURCE_COMMIT,
    }


def recovery_digest(value: dict[str, object]) -> str:
    return sha256(RECOVERY_SCHEMA.encode("ascii") + b"\x00" + jcs(value))


def acceptance_envelope(recovery: dict[str, object]) -> dict[str, object]:
    return {
        "action": "ACCEPT_DOCUMENTS",
        "algorithm": ALGORITHM,
        "authorized": True,
        "authorized_actions": AUTHORIZED_ACTIONS,
        "authorized_by": "KleinPerkins",
        "checker_sha256": recovery["checker_sha256"],
        "denied_implications": DENIED_IMPLICATIONS,
        "domain": ALGORITHM,
        "gate_2a_evidence": GATE_2A_EVIDENCE,
        "normalized_digest": recovery["normalized_digest"],
        "recovery_vector": recovery,
        "recovery_vector_digest": recovery_digest(recovery),
        "receipt_path": str(receipt_path()),
        "receipt_schema": RECEIPT_SCHEMA,
        "repository": REPOSITORY,
        "schema": OWNER_SCHEMA,
        "sentinel": SENTINEL_TEXT,
        "source_commit": SOURCE_COMMIT,
    }


def envelope(root_descriptor: int) -> dict[str, object]:
    plan, _ = read_relative(root_descriptor, PLAN_REL)
    checker_hash = sha256(checker_bytes(plan))
    rows, normalized_digest = surfaces(root_descriptor)
    recovery = recovery_vector(rows, normalized_digest, checker_hash)
    validate_recovery_vector(root_descriptor, recovery)
    return acceptance_envelope(recovery)


def owner_digest(value: dict[str, object]) -> str:
    return sha256(OWNER_SCHEMA.encode("ascii") + b"\x00" + jcs(value))


def parse_owner(value: bytes, expected: dict[str, object]) -> str:
    if not value.startswith(OWNER_PREFIX):
        fail("owner language prefix mismatch")
    parsed = strict_json(value[len(OWNER_PREFIX):].strip())
    if parsed != expected or jcs(parsed) != jcs(expected):
        fail("owner envelope omitted, added, reordered, or mutated authority")
    return owner_digest(expected)


def exact_backing_state(
    root_descriptor: int, rows: list[dict[str, str]]
) -> list[str]:
    result: list[str] = []
    for row in rows:
        result.append(classify_backing(root_descriptor, row))
    return result


def classify_bytes_mode(
    value: bytes,
    mode: int,
    row: dict[str, str],
    label: str,
) -> str:
    expected_mode = int(row["file_mode"], 8)
    if mode != expected_mode:
        fail(f"{label}: mode {mode:04o} is not {expected_mode:04o}")
    digest = sha256(value)
    if digest == row["pre_backing_file_sha256"]:
        return "PRE"
    if digest == row["post_backing_file_sha256"]:
        return "POST"
    fail(f"{label}: bytes are outside the exact recovery vector")


def classify_backing(
    root_descriptor: int, row: dict[str, str]
) -> str:
    value, mode = read_relative(root_descriptor, row["path"])
    return classify_bytes_mode(value, mode, row, row["path"])


def governed_context_state(
    root_descriptor: int,
    rows: list[dict[str, str]],
) -> list[str]:
    result: list[str] = []
    for spec, row in zip(SPECS, rows):
        path, kind, encoded, old_text, new_text = spec
        if (
            row.get("path") != path
            or row.get("kind") != kind
            or row.get("old_token") != old_text
            or row.get("new_token") != new_text
        ):
            fail("surface vector identity mismatch")
        current, mode = read_relative(root_descriptor, path)
        if mode != int(row["file_mode"], 8):
            fail(f"{path}: governed backing mode mismatch")
        strict_backing(current, path)
        old_context = base64.b64decode(encoded, validate=True)
        old = old_text.encode("utf-8")
        new = new_text.encode("utf-8")
        new_context = old_context.replace(old, new, 1)
        old_count = current.count(old_context)
        new_count = current.count(new_context)
        if (old_count, new_count) == (1, 0):
            surface = current if kind == "FULL_FILE" else old_context
            if sha256(surface) != row["pre_surface_sha256"]:
                fail(f"{path}: PRE surface hash mismatch")
            if kind == "FULL_FILE" and (
                sha256(current) != row["pre_backing_file_sha256"]
            ):
                fail(f"{path}: PRE full-file hash mismatch")
            result.append("PRE")
        elif (old_count, new_count) == (0, 1):
            surface = current if kind == "FULL_FILE" else new_context
            if sha256(surface) != row["post_surface_sha256"]:
                fail(f"{path}: POST surface hash mismatch")
            if kind == "FULL_FILE" and (
                sha256(current) != row["post_backing_file_sha256"]
            ):
                fail(f"{path}: POST full-file hash mismatch")
            result.append("POST")
        else:
            fail(f"{path}: context is neither exact PRE nor exact POST")
    return result


def candidate_bytes(
    root_descriptor: int, row: dict[str, str], target: str
) -> bytes:
    path = row["path"]
    encoded = next(item[2] for item in SPECS if item[0] == path)
    old_text, new_text = next(
        (item[3], item[4]) for item in SPECS if item[0] == path
    )
    old_context = base64.b64decode(encoded, validate=True)
    old = old_text.encode("utf-8")
    new = new_text.encode("utf-8")
    new_context = old_context.replace(old, new, 1)
    current, _ = read_relative(root_descriptor, path)
    if target == "POST" and current.count(old_context) == 1:
        return replace_context(current, old_context, old, new, path)
    if target == "PRE" and current.count(new_context) == 1:
        return replace_context(current, new_context, new, old, path)
    return current


def write_all(descriptor: int, value: bytes) -> None:
    remaining = memoryview(value)
    while remaining:
        written = os.write(descriptor, remaining)
        if written <= 0:
            fail("short candidate write")
        remaining = remaining[written:]


def durable_existing(
    parent: int,
    name: str,
    label: str,
    expected_hash: str,
    expected_mode: int,
) -> bytes:
    descriptor = open_regular(parent, name, label)
    try:
        value = validate_held_entry(
            parent, name, descriptor, label, expected_hash, expected_mode
        )
        os.fsync(descriptor)
        os.fsync(parent)
        final = validate_held_entry(
            parent, name, descriptor, label, expected_hash, expected_mode
        )
        if final != value:
            fail(f"{label}: bytes changed across durability finalization")
        return final
    finally:
        os.close(descriptor)


def validate_held_entry(
    parent: int,
    name: str,
    descriptor: int,
    label: str,
    expected_hash: str,
    expected_mode: int,
) -> bytes:
    opened = os.fstat(descriptor)
    visible = entry_metadata(parent, name)
    if (
        visible is None
        or not stat.S_ISREG(opened.st_mode)
        or not stat.S_ISREG(visible.st_mode)
        or opened.st_uid != os.geteuid()
        or visible.st_uid != os.geteuid()
        or opened.st_nlink != 1
        or visible.st_nlink != 1
        or stat.S_IMODE(opened.st_mode) != expected_mode
        or stat.S_IMODE(visible.st_mode) != expected_mode
        or (opened.st_dev, opened.st_ino)
        != (visible.st_dev, visible.st_ino)
    ):
        fail(f"{label}: held/visible identity or metadata mismatch")
    value = read_descriptor(descriptor)
    after = os.fstat(descriptor)
    if (
        after.st_dev,
        after.st_ino,
        after.st_uid,
        after.st_nlink,
        stat.S_IMODE(after.st_mode),
    ) != (
        opened.st_dev,
        opened.st_ino,
        opened.st_uid,
        opened.st_nlink,
        stat.S_IMODE(opened.st_mode),
    ):
        fail(f"{label}: descriptor metadata changed during validation")
    if sha256(value) != expected_hash:
        fail(f"{label}: held content hash mismatch")
    return value


def residue_name(name: str) -> str:
    return f".{name}.awa-v4-acceptance-residue-v1"


def classify_named(
    parent: int,
    name: str,
    row: dict[str, str],
    label: str,
) -> str | None:
    metadata = entry_metadata(parent, name)
    if metadata is None:
        return None
    descriptor = open_regular(parent, name, label)
    try:
        value = read_descriptor(descriptor)
        mode = stat.S_IMODE(os.fstat(descriptor).st_mode)
        return classify_bytes_mode(value, mode, row, label)
    finally:
        os.close(descriptor)


def classify_pair(
    root_descriptor: int, row: dict[str, str]
) -> tuple[str, str | None]:
    parent, name = open_parent(root_descriptor, row["path"])
    try:
        target = classify_named(parent, name, row, row["path"])
        if target is None:
            fail(f'{row["path"]}: target absent')
        residue = classify_named(
            parent, residue_name(name), row, f'{row["path"]}: residue'
        )
        if residue is not None and residue == target:
            fail(f'{row["path"]}: duplicate target/residue state {target}')
        return target, residue
    finally:
        os.close(parent)


def require_no_residue(
    root_descriptor: int, row: dict[str, str], label: str
) -> None:
    parent, name = open_parent(root_descriptor, row["path"])
    try:
        residue = residue_name(name)
        metadata = entry_metadata(parent, residue)
        if metadata is not None:
            try:
                state = classify_named(
                    parent,
                    residue,
                    row,
                    f'{row["path"]}: residue',
                )
            except BaseException as error:
                state = f"invalid:{error}"
            fail(f'{row["path"]}: {label} residue present ({state})')
    finally:
        os.close(parent)


def durable_pair(
    parent: int,
    name: str,
    row: dict[str, str],
    target_state: str,
    residue_state: str,
) -> None:
    mode = int(row["file_mode"], 8)
    durable_existing(
        parent,
        name,
        row["path"],
        row[f"{target_state.lower()}_backing_file_sha256"],
        mode,
    )
    durable_existing(
        parent,
        residue_name(name),
        f'{row["path"]}: residue',
        row[f"{residue_state.lower()}_backing_file_sha256"],
        mode,
    )


def swap_replace(
    root_descriptor: int,
    row: dict[str, str],
    value: bytes,
    expected_old_hash: str,
    mode: int,
) -> None:
    path = row["path"]
    parent, name = open_parent(root_descriptor, path)
    residue = residue_name(name)
    descriptor: int | None = None
    try:
        if entry_metadata(parent, residue) is not None:
            fail(f"{path}: deterministic residue already exists")
        descriptor = os.open(
            residue,
            os.O_RDWR
            | os.O_CREAT
            | os.O_EXCL
            | os.O_NOFOLLOW
            | os.O_NONBLOCK,
            0o600,
            dir_fd=parent,
        )
        os.fchmod(descriptor, mode)
        write_all(descriptor, value)
        candidate_hash = sha256(value)
        validate_held_entry(
            parent,
            residue,
            descriptor,
            f"{path}: candidate",
            candidate_hash,
            mode,
        )
        os.fsync(descriptor)
        validate_held_entry(
            parent,
            residue,
            descriptor,
            f"{path}: candidate pre-rename",
            candidate_hash,
            mode,
        )
        renameatx(parent, residue, parent, name, RENAME_SWAP)
        validate_held_entry(
            parent,
            name,
            descriptor,
            f"{path}: published candidate",
            candidate_hash,
            mode,
        )
        old_descriptor = open_regular(
            parent, residue, f"{path}: displaced target"
        )
        try:
            old_value = read_descriptor(old_descriptor)
            old_mode = stat.S_IMODE(os.fstat(old_descriptor).st_mode)
            classify_bytes_mode(
                old_value, old_mode, row, f"{path}: displaced target"
            )
            validate_held_entry(
                parent,
                residue,
                old_descriptor,
                f"{path}: displaced target",
                expected_old_hash,
                mode,
            )
        finally:
            os.close(old_descriptor)
        os.fsync(parent)
        validate_held_entry(
            parent,
            name,
            descriptor,
            f"{path}: published candidate durable",
            candidate_hash,
            mode,
        )
        durable_pair(parent, name, row, classify_bytes_mode(
            value, mode, row, f"{path}: candidate"
        ), classify_bytes_mode(
            old_value, mode, row, f"{path}: displaced target"
        ))
    except BaseException as error:
        try:
            target_state = classify_named(parent, name, row, path)
            residue_state = classify_named(
                parent, residue, row, f"{path}: residue"
            )
            status = f"target={target_state};residue={residue_state}"
        except BaseException as status_error:
            status = f"unclassifiable:{status_error}"
        raise RuntimeError(
            f"{path}: mutation failed; deterministic {status}; "
            f"primary={error}"
        ) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent)


def swap_known_pair(
    parent: int,
    name: str,
    row: dict[str, str],
    target_state: str,
    residue_state: str,
) -> None:
    residue = residue_name(name)
    mode = int(row["file_mode"], 8)
    target_descriptor = open_regular(parent, name, row["path"])
    residue_descriptor: int | None = None
    try:
        residue_descriptor = open_regular(
            parent, residue, f'{row["path"]}: residue'
        )
        validate_held_entry(
            parent,
            name,
            target_descriptor,
            row["path"],
            row[f"{target_state.lower()}_backing_file_sha256"],
            mode,
        )
        validate_held_entry(
            parent,
            residue,
            residue_descriptor,
            f'{row["path"]}: residue',
            row[f"{residue_state.lower()}_backing_file_sha256"],
            mode,
        )
        renameatx(parent, residue, parent, name, RENAME_SWAP)
        validate_held_entry(
            parent,
            name,
            residue_descriptor,
            row["path"],
            row[f"{residue_state.lower()}_backing_file_sha256"],
            mode,
        )
        validate_held_entry(
            parent,
            residue,
            target_descriptor,
            f'{row["path"]}: residue',
            row[f"{target_state.lower()}_backing_file_sha256"],
            mode,
        )
        os.fsync(parent)
        durable_pair(parent, name, row, residue_state, target_state)
    except BaseException as error:
        close_owned_descriptors(
            residue_descriptor, target_descriptor, primary=error
        )
    close_owned_descriptors(residue_descriptor, target_descriptor)


def retire_known_residue(
    parent: int,
    name: str,
    row: dict[str, str],
    target_state: str,
    residue_state: str,
) -> None:
    residue = residue_name(name)
    mode = int(row["file_mode"], 8)
    residue_hash = row[
        f"{residue_state.lower()}_backing_file_sha256"
    ]
    residue_descriptor = open_regular(
        parent, residue, f'{row["path"]}: residue'
    )
    try:
        classified = validate_held_entry(
            parent,
            residue,
            residue_descriptor,
            f'{row["path"]}: residue',
            residue_hash,
            mode,
        )
        classified_metadata = os.fstat(residue_descriptor)
        classified_binding = (
            classified_metadata.st_dev,
            classified_metadata.st_ino,
            classified_metadata.st_uid,
            classified_metadata.st_nlink,
            stat.S_IMODE(classified_metadata.st_mode),
            sha256(classified),
        )
        durable_pair(parent, name, row, target_state, residue_state)
        rebound = validate_held_entry(
            parent,
            residue,
            residue_descriptor,
            f'{row["path"]}: residue pre-unlink',
            residue_hash,
            mode,
        )
        rebound_metadata = os.fstat(residue_descriptor)
        if (
            rebound_metadata.st_dev,
            rebound_metadata.st_ino,
            rebound_metadata.st_uid,
            rebound_metadata.st_nlink,
            stat.S_IMODE(rebound_metadata.st_mode),
            sha256(rebound),
        ) != classified_binding:
            fail(f'{row["path"]}: classified residue binding changed')
        os.unlink(residue, dir_fd=parent)
        os.fsync(parent)
        retired_metadata = os.fstat(residue_descriptor)
        if (
            retired_metadata.st_dev,
            retired_metadata.st_ino,
            retired_metadata.st_uid,
            retired_metadata.st_nlink,
            stat.S_IMODE(retired_metadata.st_mode),
        ) != (
            classified_binding[0],
            classified_binding[1],
            classified_binding[2],
            0,
            classified_binding[4],
        ):
            fail(
                f'{row["path"]}: classified residue inode was not retired'
            )
        retired = read_descriptor(residue_descriptor)
        retired_after = os.fstat(residue_descriptor)
        if (
            retired_after.st_dev,
            retired_after.st_ino,
            retired_after.st_uid,
            retired_after.st_nlink,
            stat.S_IMODE(retired_after.st_mode),
            sha256(retired),
        ) != (
            classified_binding[0],
            classified_binding[1],
            classified_binding[2],
            0,
            classified_binding[4],
            classified_binding[5],
        ):
            fail(
                f'{row["path"]}: retired residue binding changed'
            )
        if entry_metadata(parent, residue) is not None:
            fail(f'{row["path"]}: residue unlink did not persist')
        durable_existing(
            parent,
            name,
            row["path"],
            row[f"{target_state.lower()}_backing_file_sha256"],
            mode,
        )
        if entry_metadata(parent, residue) is not None:
            fail(f'{row["path"]}: residue reappeared after retirement')
    except BaseException as error:
        close_owned_descriptors(residue_descriptor, primary=error)
    close_owned_descriptors(residue_descriptor)


def ensure_relative(
    root_descriptor: int,
    row: dict[str, str],
    desired: str,
    value: bytes,
    mode: int,
) -> None:
    path = row["path"]
    desired_hash = row[f"{desired.lower()}_backing_file_sha256"]
    previous = "pre" if desired == "POST" else "post"
    previous_hash = row[f"{previous}_backing_file_sha256"]
    previous_state = previous.upper()
    target_state, residue_state = classify_pair(root_descriptor, row)
    parent, name = open_parent(root_descriptor, path)
    try:
        if residue_state is None and target_state == desired:
            durable_existing(parent, name, path, desired_hash, mode)
            return
        if residue_state is None and target_state == previous_state:
            os.close(parent)
            parent = -1
            swap_replace(root_descriptor, row, value, previous_hash, mode)
            parent, name = open_parent(root_descriptor, path)
            target_state, residue_state = classify_pair(
                root_descriptor, row
            )
        if (
            target_state == previous_state
            and residue_state == desired
        ):
            swap_known_pair(
                parent, name, row, target_state, residue_state
            )
            target_state, residue_state = desired, previous_state
        if (
            target_state == desired
            and residue_state == previous_state
        ):
            retire_known_residue(
                parent, name, row, target_state, residue_state
            )
            return
        fail(
            f"{path}: unresolved deterministic pair "
            f"target={target_state};residue={residue_state}"
        )
    except BaseException as error:
        try:
            target_status, residue_status = classify_pair(
                root_descriptor, row
            )
            status = (
                f"target={target_status};residue={residue_status}"
            )
        except BaseException as status_error:
            status = f"unclassifiable:{status_error}"
        raise RuntimeError(
            f"{path}: reconciliation failed; deterministic {status}; "
            f"primary={error}"
        ) from error
    finally:
        if parent >= 0:
            os.close(parent)


def state_home() -> Path:
    path = receipt_path()
    for _ in Path(RECEIPT_REL).parts:
        path = path.parent
    return path


def open_state_parent() -> int:
    descriptor: int | None = open_absolute_directory(state_home(), True)
    try:
        for component in PurePosixPath(RECEIPT_REL).parent.parts:
            metadata = entry_metadata(descriptor, component)
            if metadata is None:
                os.mkdir(component, 0o700, dir_fd=descriptor)
                os.fsync(descriptor)
            child = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=descriptor,
            )
            try:
                checked_directory(child, component, True)
            except BaseException as error:
                close_owned_descriptors(child, primary=error)
            try:
                close_owned_descriptors(descriptor)
            except BaseException as error:
                descriptor = None
                close_owned_descriptors(child, primary=error)
            descriptor = child
        return descriptor
    except BaseException as error:
        close_owned_descriptors(descriptor, primary=error)


def acquire_lock(parent: int) -> int:
    name = "acceptance-promotion.lock"
    metadata = entry_metadata(parent, name)
    if metadata is not None and not stat.S_ISREG(metadata.st_mode):
        fail("promotion lock entry exists but is not regular")
    flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
    if metadata is None:
        flags |= os.O_CREAT | os.O_EXCL
    descriptor = os.open(name, flags, 0o600, dir_fd=parent)
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.geteuid()
            or opened.st_nlink != 1
            or (
                metadata is not None
                and (opened.st_dev, opened.st_ino)
                != (metadata.st_dev, metadata.st_ino)
            )
        ):
            fail("promotion lock is not one owner-held regular file")
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
        os.fsync(parent)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail("another documentation promotion holds the lock")
        current = entry_metadata(parent, name)
        if current is None or (current.st_dev, current.st_ino) != (
            opened.st_dev,
            opened.st_ino,
        ):
            fail("promotion lock path changed during acquisition")
    except BaseException as error:
        close_owned_descriptors(descriptor, primary=error)
    return descriptor


def receipt_entry(parent: int) -> os.stat_result | None:
    return entry_metadata(parent, PurePosixPath(RECEIPT_REL).name)


def receipt_residue_entry(parent: int) -> os.stat_result | None:
    return entry_metadata(parent, receipt_candidate_name())


def receipt_candidate_name() -> str:
    return (
        f".{PurePosixPath(RECEIPT_REL).name}."
        "awa-v4-acceptance-residue-v1"
    )


def publish_receipt(
    root_descriptor: int,
    parent: int,
    value: bytes,
    expected_recovery: dict[str, object],
    expected_owner_digest: str,
) -> bytes:
    name = PurePosixPath(RECEIPT_REL).name
    if receipt_entry(parent) is not None:
        fail("receipt entry already exists")
    temp = receipt_candidate_name()
    descriptor: int | None = None
    try:
        existing = entry_metadata(parent, temp)
        if existing is None:
            descriptor = os.open(
                temp,
                os.O_RDWR
                | os.O_CREAT
                | os.O_EXCL
                | os.O_NOFOLLOW
                | os.O_NONBLOCK,
                0o600,
                dir_fd=parent,
            )
            os.fchmod(descriptor, 0o600)
            write_all(descriptor, value)
        else:
            descriptor = open_regular(
                parent, temp, "receipt deterministic candidate"
            )
            value = read_descriptor(descriptor)
        validate_receipt_payload(
            root_descriptor,
            value,
            stat.S_IMODE(os.fstat(descriptor).st_mode),
            expected_recovery,
            expected_owner_digest,
        )
        validate_held_entry(
            parent,
            temp,
            descriptor,
            "receipt candidate",
            sha256(value),
            0o600,
        )
        os.fsync(descriptor)
        validate_held_entry(
            parent,
            temp,
            descriptor,
            "receipt candidate pre-rename",
            sha256(value),
            0o600,
        )
        renameatx(parent, temp, parent, name, RENAME_EXCL)
        validate_held_entry(
            parent,
            name,
            descriptor,
            "published receipt",
            sha256(value),
            0o600,
        )
        os.fsync(parent)
        final = validate_held_entry(
            parent,
            name,
            descriptor,
            "published receipt durable",
            sha256(value),
            0o600,
        )
        validate_receipt_payload(
            root_descriptor,
            final,
            stat.S_IMODE(os.fstat(descriptor).st_mode),
            expected_recovery,
            expected_owner_digest,
        )
        if entry_metadata(parent, temp) is not None:
            fail("receipt candidate entry survived exclusive rename")
        return final
    except BaseException as error:
        final_status = entry_metadata(parent, name)
        candidate_status = entry_metadata(parent, temp)
        raise RuntimeError(
            "receipt publication failed; "
            f"final_present={final_status is not None};"
            f"candidate_present={candidate_status is not None};"
            f"primary={error}"
        ) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def valid_hash(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def validate_recovery_vector(
    root_descriptor: int, value: object
) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != {
        "checker_sha256",
        "normalized_digest",
        "ordered_surfaces",
        "repository",
        "schema",
        "source_commit",
    }:
        fail("recovery vector key set mismatch")
    if (
        value.get("schema") != RECOVERY_SCHEMA
        or value.get("repository") != REPOSITORY
        or value.get("source_commit") != SOURCE_COMMIT
        or not valid_hash(value.get("checker_sha256"))
        or not valid_hash(value.get("normalized_digest"))
    ):
        fail("recovery vector fixed field mismatch")
    plan, _ = read_relative(root_descriptor, PLAN_REL)
    if value["checker_sha256"] != sha256(checker_bytes(plan)):
        fail("recovery vector checker hash mismatch")
    rows = value.get("ordered_surfaces")
    if not isinstance(rows, list) or len(rows) != len(SPECS):
        fail("recovery vector surface count mismatch")
    expected_keys = {
        "file_mode",
        "kind",
        "new_token",
        "old_token",
        "ordinal",
        "path",
        "post_backing_file_sha256",
        "post_surface_sha256",
        "pre_backing_file_sha256",
        "pre_surface_sha256",
    }
    for ordinal, (spec, row) in enumerate(zip(SPECS, rows), 1):
        if not isinstance(row, dict) or set(row) != expected_keys:
            fail("recovery surface key set mismatch")
        if (
            row.get("file_mode") != "0644"
            or
            row.get("ordinal") != str(ordinal)
            or row.get("path") != spec[0]
            or row.get("kind") != spec[1]
            or row.get("old_token") != spec[3]
            or row.get("new_token") != spec[4]
        ):
            fail("recovery surface identity/order mismatch")
        for key in (
            "pre_surface_sha256",
            "post_surface_sha256",
            "pre_backing_file_sha256",
            "post_backing_file_sha256",
        ):
            if not valid_hash(row.get(key)):
                fail(f"recovery surface {key} is not lowercase SHA-256")
    return value


def packet_object(root_descriptor: int) -> dict[str, object]:
    expected = envelope(root_descriptor)
    recovery = validate_recovery_vector(
        root_descriptor, expected["recovery_vector"]
    )
    return {
        "checker_sha256": expected["checker_sha256"],
        "normalized_digest": expected["normalized_digest"],
        "owner_acceptance_digest": owner_digest(expected),
        "owner_acceptance_envelope": expected,
        "recovery_vector": recovery,
        "recovery_vector_digest": recovery_digest(recovery),
        "required_owner_language":
            (OWNER_PREFIX + jcs(expected)).decode("utf-8"),
        "schema": PACKET_SCHEMA,
    }


def parse_packet(
    root_descriptor: int, value: bytes
) -> dict[str, object]:
    if (
        not value.endswith(b"\n")
        or value.endswith(b"\n\n")
        or b"\r" in value
    ):
        fail("recovery packet framing mismatch")
    parsed = strict_json(value[:-1])
    if not isinstance(parsed, dict) or set(parsed) != {
        "checker_sha256",
        "normalized_digest",
        "owner_acceptance_digest",
        "owner_acceptance_envelope",
        "recovery_vector",
        "recovery_vector_digest",
        "required_owner_language",
        "schema",
    }:
        fail("recovery packet key set mismatch")
    if value != jcs(parsed) + b"\n":
        fail("recovery packet is not canonical JCS plus one LF")
    if parsed.get("schema") != PACKET_SCHEMA:
        fail("recovery packet schema mismatch")
    recovery = validate_recovery_vector(
        root_descriptor, parsed.get("recovery_vector")
    )
    expected = acceptance_envelope(recovery)
    if (
        parsed.get("checker_sha256") != recovery["checker_sha256"]
        or parsed.get("normalized_digest") != recovery["normalized_digest"]
        or parsed.get("recovery_vector_digest") != recovery_digest(recovery)
        or parsed.get("owner_acceptance_envelope") != expected
        or jcs(parsed.get("owner_acceptance_envelope")) != jcs(expected)
        or parsed.get("owner_acceptance_digest") != owner_digest(expected)
        or parsed.get("required_owner_language")
        != (OWNER_PREFIX + jcs(expected)).decode("utf-8")
    ):
        fail("recovery packet semantic mismatch")
    return parsed


def receipt_object(
    root_descriptor: int,
    expected: dict[str, object],
    acceptance_digest: str,
) -> dict[str, object]:
    rows = expected["recovery_vector"]["ordered_surfaces"]
    if governed_context_state(root_descriptor, rows) != ["POST"] * 4:
        fail("receipt construction requires four exact POST contexts")
    result = {
        "algorithm": ALGORITHM,
        "checker_sha256": expected["checker_sha256"],
        "completed_wall_ns": str(time.time_ns()),
        "domain": ALGORITHM,
        "normalized_digest": expected["normalized_digest"],
        "recovery_vector": expected["recovery_vector"],
        "recovery_vector_digest": expected["recovery_vector_digest"],
        "owner_acceptance_digest": acceptance_digest,
        "repository": REPOSITORY,
        "schema": RECEIPT_SCHEMA,
        "sentinel": SENTINEL_TEXT,
        "source_commit": SOURCE_COMMIT,
    }
    result["receipt_hash"] = sha256(
        RECEIPT_SCHEMA.encode("ascii") + b"\x00" + jcs(result)
    )
    return result


def validate_receipt_payload(
    root_descriptor: int,
    raw: bytes,
    mode: int,
    expected_recovery: dict[str, object] | None = None,
    expected_owner_digest: str | None = None,
) -> dict[str, object]:
    if (
        not raw.endswith(b"\n")
        or raw.endswith(b"\n\n")
        or b"\r" in raw
    ):
        fail("receipt framing mismatch")
    parsed = strict_json(raw[:-1])
    if not isinstance(parsed, dict) or raw != jcs(parsed) + b"\n":
        fail("receipt is not canonical JCS plus one LF")
    required_keys = {
        "algorithm",
        "checker_sha256",
        "completed_wall_ns",
        "domain",
        "normalized_digest",
        "owner_acceptance_digest",
        "receipt_hash",
        "recovery_vector",
        "recovery_vector_digest",
        "repository",
        "schema",
        "sentinel",
        "source_commit",
    }
    if set(parsed) != required_keys:
        fail("receipt key set mismatch")
    receipt = dict(parsed)
    stored_hash = receipt.pop("receipt_hash", None)
    if stored_hash != sha256(
        RECEIPT_SCHEMA.encode("ascii") + b"\x00" + jcs(receipt)
    ):
        fail("receipt hash mismatch")
    completed = parsed.get("completed_wall_ns")
    if (
        not isinstance(completed, str)
        or not completed.isascii()
        or not completed.isdecimal()
        or (completed.startswith("0") and completed != "0")
    ):
        fail("receipt wall time is not canonical decimal")
    if (
        parsed.get("schema") != RECEIPT_SCHEMA
        or parsed.get("repository") != REPOSITORY
        or parsed.get("source_commit") != SOURCE_COMMIT
        or parsed.get("algorithm") != ALGORITHM
        or parsed.get("domain") != ALGORITHM
        or parsed.get("sentinel") != SENTINEL_TEXT
        or mode != 0o600
    ):
        fail("receipt fixed field or mode mismatch")
    recovery = validate_recovery_vector(
        root_descriptor, parsed.get("recovery_vector")
    )
    if (
        parsed.get("checker_sha256") != recovery["checker_sha256"]
        or parsed.get("normalized_digest") != recovery["normalized_digest"]
        or parsed.get("recovery_vector_digest")
        != recovery_digest(recovery)
    ):
        fail("receipt recovery binding mismatch")
    if expected_recovery is not None and (
        recovery != expected_recovery
        or jcs(recovery) != jcs(expected_recovery)
    ):
        fail("existing receipt recovery vector mismatch")
    if governed_context_state(
        root_descriptor, recovery["ordered_surfaces"]
    ) != ["POST"] * 4:
        fail("receipt does not prove four exact POST contexts/modes")
    _, current_digest = surfaces(root_descriptor)
    if current_digest != recovery["normalized_digest"]:
        fail("receipt normalized digest mismatch")
    accepted_envelope = acceptance_envelope(recovery)
    acceptance_digest = owner_digest(accepted_envelope)
    if parsed.get("owner_acceptance_digest") != acceptance_digest:
        fail("receipt owner acceptance mismatch")
    if (
        expected_owner_digest is not None
        and acceptance_digest != expected_owner_digest
    ):
        fail("existing receipt owner digest mismatch")
    return parsed


def validate_receipt_snapshot(
    root_descriptor: int,
    state_parent: int,
    descriptor: int,
    raw: bytes,
    expected_recovery: dict[str, object] | None = None,
    expected_owner_digest: str | None = None,
) -> dict[str, object]:
    name = PurePosixPath(RECEIPT_REL).name
    if receipt_residue_entry(state_parent) is not None:
        fail("existing receipt has unexpected residue entry")
    held = validate_held_entry(
        state_parent,
        name,
        descriptor,
        "acceptance receipt",
        sha256(raw),
        0o600,
    )
    if held != raw:
        fail("receipt bytes changed during snapshot validation")
    parsed = validate_receipt_payload(
        root_descriptor,
        held,
        stat.S_IMODE(os.fstat(descriptor).st_mode),
        expected_recovery,
        expected_owner_digest,
    )
    for row in parsed["recovery_vector"]["ordered_surfaces"]:
        require_no_residue(root_descriptor, row, "receipt")
    return parsed


def inspect_receipt(
    root_descriptor: int,
    state_parent: int,
    expected_recovery: dict[str, object] | None = None,
    expected_owner_digest: str | None = None,
) -> tuple[int, bytes, dict[str, object]]:
    name = PurePosixPath(RECEIPT_REL).name
    if receipt_entry(state_parent) is None:
        fail("receipt entry absent")
    descriptor = open_regular(state_parent, name, "acceptance receipt")
    try:
        raw = read_descriptor(descriptor)
        parsed = validate_receipt_snapshot(
            root_descriptor,
            state_parent,
            descriptor,
            raw,
            expected_recovery,
            expected_owner_digest,
        )
        return descriptor, raw, parsed
    except BaseException:
        os.close(descriptor)
        raise


def finalize_receipt(
    root_descriptor: int,
    state_parent: int,
    descriptor: int,
    raw: bytes,
    inspected: dict[str, object],
    expected_recovery: dict[str, object] | None = None,
    expected_owner_digest: str | None = None,
) -> dict[str, object]:
    before = validate_receipt_snapshot(
        root_descriptor,
        state_parent,
        descriptor,
        raw,
        expected_recovery,
        expected_owner_digest,
    )
    if before != inspected or jcs(before) != jcs(inspected):
        fail("receipt semantics changed before durability finalization")
    os.fsync(descriptor)
    os.fsync(state_parent)
    final = validate_receipt_snapshot(
        root_descriptor,
        state_parent,
        descriptor,
        raw,
        expected_recovery,
        expected_owner_digest,
    )
    if final != inspected or jcs(final) != jcs(inspected):
        fail("receipt semantics changed across durability finalization")
    return final


def verify_receipt(
    root_descriptor: int,
    state_parent: int,
    expected_recovery: dict[str, object] | None = None,
    expected_owner_digest: str | None = None,
) -> dict[str, object]:
    descriptor, raw, inspected = inspect_receipt(
        root_descriptor,
        state_parent,
        expected_recovery,
        expected_owner_digest,
    )
    try:
        return finalize_receipt(
            root_descriptor,
            state_parent,
            descriptor,
            raw,
            inspected,
            expected_recovery,
            expected_owner_digest,
        )
    finally:
        os.close(descriptor)


def packet(root: Path) -> None:
    require_source(root)
    root_descriptor = open_repo_descriptor(root)
    try:
        result = packet_object(root_descriptor)
        rows = result["recovery_vector"]["ordered_surfaces"]
        if exact_backing_state(root_descriptor, rows) != ["PRE"] * 4:
            fail("packet requires four exact preimages")
        sys.stdout.buffer.write(jcs(result) + b"\n")
    finally:
        os.close(root_descriptor)


def promote(root: Path, owner_bytes: bytes) -> None:
    require_source(root)
    root_descriptor = open_repo_descriptor(root)
    try:
        state_parent = open_state_parent()
        try:
            if receipt_entry(state_parent) is not None:
                descriptor, raw, inspected = inspect_receipt(
                    root_descriptor,
                    state_parent,
                )
                try:
                    original_envelope = acceptance_envelope(
                        inspected["recovery_vector"]
                    )
                    acceptance_digest = parse_owner(
                        owner_bytes, original_envelope
                    )
                    if (
                        inspected["owner_acceptance_digest"]
                        != acceptance_digest
                    ):
                        fail("existing receipt owner input mismatch")
                    lock = acquire_lock(state_parent)
                    try:
                        require_source(root)
                        reopened = open_repo_descriptor(root)
                        os.close(root_descriptor)
                        root_descriptor = reopened
                        verified = finalize_receipt(
                            root_descriptor,
                            state_parent,
                            descriptor,
                            raw,
                            inspected,
                            inspected["recovery_vector"],
                            acceptance_digest,
                        )
                        sys.stdout.buffer.write(jcs(verified) + b"\n")
                        return
                    finally:
                        os.close(lock)
                finally:
                    os.close(descriptor)
            lock = acquire_lock(state_parent)
            try:
                require_source(root)
                reopened = open_repo_descriptor(root)
                os.close(root_descriptor)
                root_descriptor = reopened
                if receipt_entry(state_parent) is not None:
                    fail(
                        "receipt appeared after non-mutating preflight; retry"
                    )
                expected = envelope(root_descriptor)
                acceptance_digest = parse_owner(owner_bytes, expected)
                rows = expected["recovery_vector"]["ordered_surfaces"]
                exact_backing_state(root_descriptor, rows)
                for row in rows:
                    classify_pair(root_descriptor, row)
                candidates = [
                    candidate_bytes(root_descriptor, row, "POST")
                    for row in rows
                ]
                for row, candidate in zip(rows, candidates):
                    if sha256(candidate) != row["post_backing_file_sha256"]:
                        fail(f'{row["path"]}: post candidate mismatch')
                for row, candidate in zip(rows, candidates):
                    ensure_relative(
                        root_descriptor,
                        row,
                        "POST",
                        candidate,
                        int(row["file_mode"], 8),
                    )
                if governed_context_state(
                    root_descriptor, rows
                ) != ["POST"] * 4:
                    fail("promotion did not produce four POST contexts")
                if any(
                    classify_pair(root_descriptor, row)[1] is not None
                    for row in rows
                ):
                    fail("promotion left deterministic residue")
                verify_repo_anchor(root, root_descriptor)
                final_rows, final_digest = surfaces(root_descriptor)
                if (
                    final_rows != rows
                    or jcs(final_rows) != jcs(rows)
                    or final_digest != expected["normalized_digest"]
                ):
                    fail("post vector or normalized digest changed")
                receipt = receipt_object(
                    root_descriptor, expected, acceptance_digest
                )
                receipt_bytes = jcs(receipt) + b"\n"
                receipt_bytes = publish_receipt(
                    root_descriptor,
                    state_parent,
                    receipt_bytes,
                    expected["recovery_vector"],
                    acceptance_digest,
                )
                verify_repo_anchor(root, root_descriptor)
                verified = verify_receipt(
                    root_descriptor,
                    state_parent,
                    expected["recovery_vector"],
                    acceptance_digest,
                )
                if jcs(verified) + b"\n" != receipt_bytes:
                    fail("persisted receipt byte mismatch")
                sys.stdout.buffer.write(receipt_bytes)
            finally:
                os.close(lock)
        finally:
            os.close(state_parent)
    finally:
        os.close(root_descriptor)


def recover_pre(root: Path, packet_bytes: bytes) -> None:
    require_source(root)
    root_descriptor = open_repo_descriptor(root)
    try:
        original = parse_packet(root_descriptor, packet_bytes)
        rows = original["recovery_vector"]["ordered_surfaces"]
        for row in rows:
            classify_pair(root_descriptor, row)
        state_parent = open_state_parent()
        try:
            lock = acquire_lock(state_parent)
            try:
                require_source(root)
                reopened = open_repo_descriptor(root)
                os.close(root_descriptor)
                root_descriptor = reopened
                original = parse_packet(root_descriptor, packet_bytes)
                rows = original["recovery_vector"]["ordered_surfaces"]
                for row in rows:
                    classify_pair(root_descriptor, row)
                if (
                    receipt_entry(state_parent) is not None
                    or receipt_residue_entry(state_parent) is not None
                ):
                    fail("any receipt or receipt-residue entry forbids recovery")
                for row in reversed(rows):
                    candidate = candidate_bytes(
                        root_descriptor, row, "PRE"
                    )
                    if sha256(candidate) != row["pre_backing_file_sha256"]:
                        fail(f'{row["path"]}: pre recovery mismatch')
                    ensure_relative(
                        root_descriptor,
                        row,
                        "PRE",
                        candidate,
                        int(row["file_mode"], 8),
                    )
                if exact_backing_state(
                    root_descriptor, rows
                ) != ["PRE"] * 4:
                    fail("preimage recovery incomplete")
                if any(
                    classify_pair(root_descriptor, row)[1] is not None
                    for row in rows
                ):
                    fail("preimage recovery left deterministic residue")
                verify_repo_anchor(root, root_descriptor)
            finally:
                os.close(lock)
        finally:
            os.close(state_parent)
    finally:
        os.close(root_descriptor)


def read_external_input(path_text: str) -> bytes:
    path = Path(path_text)
    if not path.is_absolute() or Path(os.path.normpath(path)) != path:
        fail("authority input path is not normalized absolute")
    descriptor = os.open(
        path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    )
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or metadata.st_nlink != 1
        ):
            fail("authority input is not one owner-held regular file")
        value = read_descriptor(descriptor)
        after = os.fstat(descriptor)
        if (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
            metadata.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            fail("authority input changed during read")
        return value
    finally:
        os.close(descriptor)


def main() -> None:
    require_platform()
    if len(sys.argv) not in {2, 3}:
        fail(
            "usage: checker packet|verify-receipt | "
            "promote|recover-pre <normalized-absolute-input-file>"
        )
    root = repository_root()
    mode = sys.argv[1]
    if mode == "packet" and len(sys.argv) == 2:
        packet(root)
    elif mode == "promote" and len(sys.argv) == 3:
        promote(root, read_external_input(sys.argv[2]))
    elif mode == "recover-pre" and len(sys.argv) == 3:
        recover_pre(root, read_external_input(sys.argv[2]))
    elif mode == "verify-receipt" and len(sys.argv) == 2:
        root_descriptor = open_repo_descriptor(root)
        try:
            state_parent = open_state_parent()
            try:
                receipt = verify_receipt(root_descriptor, state_parent)
                sys.stdout.buffer.write(jcs(receipt) + b"\n")
            finally:
                os.close(state_parent)
        finally:
            os.close(root_descriptor)
    else:
        fail("checker mode/argument mismatch")


main()
```
<!-- awa-v4-acceptance-checker:v1:end -->

The canonical launcher below is part of the protocol. It contains no `assert`
and behaves identically under `PYTHONOPTIMIZE`. Before compile or execution it
descriptor-walks the repository-relative plan path without following
symlinks; checks one stable owner-held regular file, strict UTF-8/LF, no
CR/NUL, exactly one marker pair, exact payload prefix/suffix, and exact
checker SHA-256
`9ecfcb8d8fd7ab9c9271e5e55a8b84c9acbf95219cca272a486f30e16fad6a73`.
No payload byte executes before every check passes.

```bash
python3 - packet > /absolute/path/acceptance-packet.json <<'PY'
import hashlib
import os
from pathlib import Path
import stat
import subprocess

EXPECTED = "9ecfcb8d8fd7ab9c9271e5e55a8b84c9acbf95219cca272a486f30e16fad6a73"
BEGIN = b"<!-- awa-v4-" + b"acceptance-checker:v1:begin -->\n```python\n"
END = b"```\n<!-- awa-v4-" + b"acceptance-checker:v1:end -->"
root = Path(subprocess.run(
    ["git", "rev-parse", "--show-toplevel"],
    check=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
).stdout.strip())
if (
    not root.is_absolute()
    or Path(os.path.normpath(root)) != root
    or root.resolve(strict=True) != root
):
    raise SystemExit("invalid repository root")
directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
try:
    for component in ("docs", "plans"):
        child = os.open(
            component,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=directory,
        )
        os.close(directory)
        directory = child
    descriptor = os.open(
        "native-entry-durable-registration-v4.md",
        os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
        dir_fd=directory,
    )
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_nlink != 1
        ):
            raise SystemExit("plan is not one owner-held regular file")
        chunks = []
        while True:
            chunk = os.read(descriptor, 131072)
            if not chunk:
                break
            chunks.append(chunk)
        plan = b"".join(chunks)
        after = os.fstat(descriptor)
        if (
            before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns
        ) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ):
            raise SystemExit("plan changed during read")
    finally:
        os.close(descriptor)
finally:
    os.close(directory)
try:
    plan.decode("utf-8", "strict")
except UnicodeDecodeError as error:
    raise SystemExit(f"plan is not strict UTF-8: {error}")
if (
    b"\r" in plan
    or b"\x00" in plan
    or not plan.endswith(b"\n")
    or plan.endswith(b"\n\n")
):
    raise SystemExit("plan framing is not canonical UTF-8/LF")
if plan.count(BEGIN) != 1 or plan.count(END) != 1:
    raise SystemExit("checker markers are not unique")
payload = plan.split(BEGIN, 1)[1].split(END, 1)[0]
try:
    payload.decode("utf-8", "strict")
except UnicodeDecodeError as error:
    raise SystemExit(f"checker is not strict UTF-8: {error}")
if (
    b"\r" in payload
    or b"\x00" in payload
    or not payload.startswith(b"from __future__")
    or not payload.endswith(b"main()\n")
    or hashlib.sha256(payload).hexdigest() != EXPECTED
):
    raise SystemExit("checker framing or SHA-256 mismatch")
program = compile(payload, "<awa-v4-acceptance-checker-v1>", "exec")
exec(program)
PY
```

The launcher arguments are exactly:

```text
packet
verify-receipt
promote /normalized/absolute/path/to/owner-language.txt
recover-pre /normalized/absolute/path/to/original-acceptance-packet.json
```

For the latter three modes replace only the command-line arguments on the
first launcher line; remove packet-mode output redirection unless evidence is
being captured. `packet` is read-only and its canonical JCS+LF output must be
preserved byte-for-byte for possible recovery. `promote` and `recover-pre`
read their named owner-held regular input once by no-follow descriptor.
`recover-pre` consumes the original packet, never owner acceptance. Mutating
modes remain forbidden without their separately named authority; this draft
hardening does not run them against the governed files.

The v2 semantic owner envelope has exactly the keys and values produced by
`envelope()`. Object-key order and JSON whitespace are non-semantic because
the parser rejects duplicate keys and then compares the parsed object for
exact equality before RFC 8785-compatible JCS reserialization. Arrays,
strings, booleans, nullability, and every nested key/value remain exact and
ordered. The only accepted operator form is the exact `OWNER_PREFIX` followed
by one JSON object and optional surrounding JSON whitespace; omitted, extra,
duplicate, type-changed, reordered-array, or mutated values refuse.
Chat/UI visual wrapping therefore cannot change authority, while a newline
inserted inside a JSON string remains invalid.

```text
owner_acceptance_digest =
  lowercase_hex(SHA256(
    ASCII("awa-registration-v4-owner-acceptance/v2") || 0x00 ||
    JCS(exact owner acceptance envelope)
  ))
```

The envelope includes the exact source commit, canonical checker hash,
`awa-registration-v4-recovery-vector/v1`, its domain-separated digest, all
four ordered pre/post surface/backing hashes and `0644` modes, normalized
algorithm/domain/sentinel/digest, resolved receipt path/schema, authorized
actions, denied implications, and separately supplied Gate 2A evidence. It
excludes its own digest, runtime completion time, and receipt hash, so no
field is self-referential. The canonical packet schema is
`awa-registration-v4-acceptance-packet/v2`; its JCS+LF bytes contain that
envelope and recovery vector. Every earlier acceptance packet or prose
acceptance—including packets produced before identity-bound residue
retirement, owner-before-fsync receipt retry, and exception-preserving
immediate descriptor ownership—lacks this exact checker/recovery/receipt
binding and is invalid; none may be reused. Every owner-language artifact
whose envelope names the prior checker SHA-256
`fea753e102b26882fc2e04528abd644068a36e47b849dd81797e1cee62dba571`
is explicitly invalid and must be discarded and regenerated from this
revision's canonical packet.

Promotion is one checked status-last operation under
`<receipt-directory>/acceptance-promotion.lock`, a descriptor-validated
owner-only `0600` regular file. Darwin `renameatx_np(RENAME_SWAP)` atomically
swaps each fsynced, `fchmod`-verified candidate with the current target. The
candidate descriptor remains open across rename; immediately before rename
the directory entry must still name that exact dev/inode/uid/link/mode/hash,
and immediately after rename the destination must name that held descriptor
with unchanged content and metadata. The displaced target must match the
packet's expected prior hash **and** `0644` mode before deletion.
`RENAME_EXCL` publishes the receipt with the same held-descriptor pre/post
identity rule and without replacement. Every trusted path component is
traversed from an anchored no-follow directory descriptor; every file is
opened no-follow and identity-checked. Missing Darwin
descriptor/`renameatx_np` support refuses.

Darwin does not expose an atomic “rename this open descriptor” primitive.
The checker therefore uses a bounded same-euid exclusion model: one promotion
lock, descriptor-held pre/post identity checks, and deterministic residue
classification make interference detectable and recoverable, but cannot
prevent an independently malicious same-euid process from racing the
path-based syscall itself. Identity-bound retirement detects a classified
residue moved or replaced before/during path unlink by requiring the held
inode itself to reach zero links, but cannot prevent or undo a malicious
peer's independent filesystem action. Such a process is outside Gate 2's
cooperative local-operator model; any detected substitution refuses,
publishes no receipt, and cannot return a clean terminal result.

The canonical replacement order remains ADR body, ADR row backing file, plan
row backing file, then v4 body; reverse recovery order is v4 body, plan row,
ADR row, then ADR body. The v4 frozen-status token is therefore the last
repository replacement. All four governed contexts must be exact POST and
the full recovery vector/digest must match before receipt construction.
Every exact-state decision is one hash+mode decision: packet creation requires
four exact PRE backings at `0644`; promotion/recovery classification,
displaced-target validation, terminal PRE/POST proof, and exact-row context
proof all require the packet-bound mode. EXACT_ROW tolerance applies only to
unrelated bytes outside its governed row after acceptance, never to backing
mode. Retries seeing exact desired bytes fsync the held target and parent,
then reread/re-fstat and recheck current bytes, mode, owner, link count, and
visible-entry identity rather than treating either visibility or a stale
snapshot as durability.

Each governed target has exactly one deterministic same-directory residue
name, `.<basename>.awa-v4-acceptance-residue-v1`. On entry, promotion and
recovery classify target plus residue before creating anything. Only no
residue with exact target, target PRE/residue POST, or target POST/residue PRE
is recoverable. Promotion with exact owner authority may finish only the
known post-swap pair; `recover-pre` with the original packet may restore only
the known pre-swap pair. Cleanup opens and classifies the residue once and
holds that descriptor through retirement. After durable-pair validation it
immediately requires the visible residue name to rebind to the exact held
dev/inode/uid/link/mode/hash, unlinks, fsyncs the parent, and requires that
same held inode—not merely the path occupant—to retain its bound
uid/mode/hash with link count exactly zero. It then revalidates the target and
residue-name absence before success. Duplicate state, unknown bytes, wrong
mode/owner/link, symlink/nonregular entry, substitution, or unlink/swap
failure refuses with the primary failure and classified pair status; residue
is never silent authority and must be absent before receipt publication.

Descriptor ownership begins immediately after every successful open on the
Gate 2 repository, regular-file, state-parent, known-pair, residue, and lock
paths. A return is the only ownership transfer. On failure,
`close_owned_descriptors` attempts every still-owned descriptor exactly once;
if a primary exception exists it re-raises that exact object and attaches the
first close failure only as secondary cause, while a lone close failure is
raised. No validation, unlink, fsync, lock, or path-rebind failure can become
success or be replaced by descriptor cleanup.

Promotion inspects any existing receipt **before** lock durability or deriving
a live backing vector. The non-mutating phase holds the receipt descriptor,
validates canonical bytes/schema/hash and its embedded original recovery
vector, reconstructs that exact original owner envelope, proves four POST
contexts with `0644` backing modes and all residue names absent, then parses
the supplied owner input and requires its digest. Only after that
authorization may lock and receipt/file-plus-parent durability finalization
run. Immediately before and after receipt and parent fsync, the checker
repeats held/visible receipt identity, exact payload, current four POST
contexts/modes, normalized digest, receipt-candidate absence, and every
governed residue check. This remains idempotent after permitted unrelated
additions outside the two exact index rows. A malformed/mismatched owner
causes zero fsync; a malformed, mismatched, noncanonical, PRE/mixed,
mode-divergent, dangling-symlink, nonregular, changed, or unexpected
receipt/residue entry refuses; only receipt absence through non-mutating
preflight permits a fresh PRE/POST vector.

Before any state-directory/lock effect, `recover-pre` revalidates exact source
and parses the original canonical packet. Under lock it revalidates source
again, then accepts only exact PRE/POST whole backing hashes and modes from
that packet; changed non-token bytes cannot become a new baseline. Recovery
remains non-owner/non-acceptance authority and restores known postimages in
reverse order only. Promotion similarly revalidates source/root identity
under lock immediately before mutation. Crash residue is non-authority and
reported; no cleanup claim substitutes for exact classification.

The detached receipt path is the normalized absolute expansion of:

```text
${XDG_STATE_HOME:-$HOME/.local/state}/awa/governance/
  native-entry-durable-registration-v4/acceptance-promotion.json
```

It is exact JCS plus one LF, regular owner-only `0600` in `0700` parents, and
has exactly:

```text
schema = "awa-registration-v4-acceptance-promotion/v2"
repository = "KleinPerkins/awa"
source_commit
checker_sha256
recovery_vector = awa-registration-v4-recovery-vector/v1
recovery_vector_digest
algorithm = "awa-registration-v4-acceptance-body/v1"
domain = "awa-registration-v4-acceptance-body/v1"
sentinel = "__AWA_V4_ACCEPTED_STATUS_TOKEN_V1__"
normalized_digest
owner_acceptance_digest
completed_wall_ns
receipt_hash
```

Recovery-vector ordinals and `completed_wall_ns` are nonempty canonical
decimal strings with no sign or leading zero except literal `"0"`; packet
ordinals are `"1"` through `"4"`. Every surface row also binds
`file_mode="0644"`. `receipt_hash` is
`SHA256(ASCII("awa-registration-v4-acceptance-promotion/v2") || 0x00 ||
JCS(receipt_without_receipt_hash))`. Publication uses a same-directory
`O_EXCL|O_NOFOLLOW` temporary, descriptor `fchmod`, mode verification, file
fsync, held-descriptor `RENAME_EXCL`, and parent fsync after all four
postimages verify. After file and parent fsync it rereads/re-fstats the held
descriptor and rechecks canonical bytes, mode, owner, link count, and visible
directory identity before success.

Verification first requires persisted bytes to equal canonical JCS plus
exactly one LF, then validates exact key set, hash, schema, recovery vector,
owner digest reconstruction, receipt mode, all four exact POST contexts, both
accepted full files, both exact index rows, and normalized digest. PRE or
mixed contexts can never validate a receipt. Backing index files may later
change only outside those exact rows
(for example to mark ADR 0025/v3 superseded); their original backing hashes
remain promotion evidence, not perpetual currentness requirements. Missing,
malformed, stale, or mixed authority is NO-GO and cannot be inferred from
status text alone. This acceptance authorizes only the four token transitions
and one detached receipt; it does not create the signer contract or
owner-key-current receipt and implies no implementation, delivery, R0/R1,
release, Skills, installation, host activation, C1, or R2 authority.

### 7.2 Tests-first cadence

For each future body, after an explicit implementation GO:

1. add failing focused tests for that body's mapped rows;
2. capture deterministic RED evidence;
3. implement only the minimum correction;
4. run focused and all affected cross-body tests;
5. run full repository, install, contract, kernel-off, guard, finish, cleanup,
   schema-hash, and protected-file gates;
6. inspect complete diff/status and protected hashes;
7. open one governed Draft PR only if separately authorized;
8. run Bugbot until no valid finding remains;
9. run one security review over the complete body where authority/import/
   parser/cutover behavior changed; and
10. keep rollout and merge authority separate under repository governance.

Implementation GO permits local source/test work only. Before commit, push,
or Draft PR, the owner must separately grant
`IMPLEMENTATION-DELIVERY GO` naming repository, accepted normalized digest,
exact body, exact base revision, branch, and allowed commit/push/Draft-PR
actions. After review, marking ready requires a second exact-head
`BODY-READINESS GO` naming the reviewed commit and passing checks. The
reviewer App alone may approve, arm native auto-merge, and merge that exact
head. Agents never call `gh pr merge --auto`, enable/disable/pre-arm
auto-merge, directly merge, or treat a later head as authorized.

After Body C, run a fresh final full-change review and protected verifier on
the complete v4 implementation head. Earlier body reviews and the prior clean
Security Review do not substitute.

### 7.3 Deterministic interleaving/fault floor

The exact-head suite must include:

- canonical launcher/checker marker extraction and exact hash twice under
  normal and `PYTHONOPTIMIZE`, with duplicate marker, prefix/suffix, UTF-8,
  CR/NUL, and hash negatives before compile/exec; deterministic packet/JCS/
  owner digest equality; exact source `HEAD`/fresh-remote binding; semantic
  acceptance with JSON whitespace and object-key reorder positives; wrong
  prefix, duplicate/unknown/omitted/mutated/type-changed field, reordered
  array, changed source/checker/backing hash/mode/receipt path/Gate 2A evidence/
  scope, raw prior acceptance, and trailing-object negatives;
- original-packet recovery with canonical wire plus wrong/mutated/reordered/
  extra/omitted recovery fields, changed non-token bytes, wrong HEAD, remote
  advance before lock and under lock, and exact reverse-order PRE recovery;
  recovery never consumes owner acceptance and never derives a vector from
  recovery-time bytes;
- PRE/mixed/POST receipt-state vectors; exact JCS+LF, alternate whitespace/
  key order/escaping and CRLF negatives; later additive index-only changes;
  packet/promote refusal for each non-`0644` PRE backing; PRE/POST/mixed mode
  drift recovery refusal; displaced-target wrong-mode retention; terminal
  hash+mode proof; dangling final/ancestor symlinks; restrictive umask;
  candidate-entry substitution, link/metadata mutation, and immediate
  post-rename destination replacement while the candidate descriptor stays
  open; target/receipt mutation before/after file fsync and parent fsync with
  post-fsync reread/re-fstat/visible-entry rejection;
- deterministic target/residue matrices for every surface and direction:
  no residue, PRE/POST and POST/PRE pairs, unknown/duplicate hash, wrong
  mode/owner/link, symlink/nonregular, reverse-swap and unlink failure, and
  crash/retry; promotion finishes only the known authorized pair, recovery
  restores only the packet-bound pair, and replacement/rename immediately
  after durable-pair validation but before unlink requires the held classified
  inode to reach zero links or refuses with no receipt and no clean terminal
  result; unresolved residue forbids receipt; retry durability when desired
  bytes are visible; exact-existing-receipt receipt-first non-mutating
  validation and owner reconstruction, zero fsync for malformed/mismatched
  owner, then authorized idempotent finalize plus post-fsync held-entry,
  payload, current-POST, and residue revalidation after permitted outside-row
  additions; altered embedded vector, malformed receipt, PRE/mixed contexts,
  wrong mode, and unexpected entry refusal; crash before/after all four
  replacements and receipt `RENAME_EXCL`; and receipt schema/hash/mode/path/
  recovery-vector/owner-digest reconstruction;
- grant COMMIT→capability-return faults for OPEN, ADOPT, and DRAINING
  REACQUIRE plus same-boot process death;
- SQL-v2 extraction/output hash/inventory/97-leaf equality plus independent
  WRITABLE/DRAINING predicate kills;
- staged send/RECEIVED/release/lock-acquire/ACTIVATED/zero faults and absolute
  timeout ordering, including explicit sender reuse/reacquire rejection;
- 98,304/98,303 outcome and 32,768/32,767 successor vectors; three recovery
  cycles; fourth-cycle typed zero-write result; runtime/actor/forged-result
  CONTROL denial; authenticated adapter containment attempt;
- corrupt-low reservation rows charged at SQL maxima before closure;
- old/new basis barriers and exact duplicate races;
- first-effect/predecessor/supersession/adoption semantic closure mutation
  before admission, helper I/O, CONTROL, cut selection, and every resolver;
- schema statement/commit/rename/fsync/reopen/startup-reconcile faults;
- native SQLite `FULL`/`IOERR` before commit, ambiguous return, reopen,
  containment commit, and containment unavailability;
- eight-lane overlap, ninth continuation, worker kill, and cleanup failure;
- host-tick cursor missing/stale/current/busy/wrap/no-longer-candidate,
  >8 progress, cursor non-authority, and R1 same-boot/due/reboot scope refusal;
- deep JSON and hostile path-qualified transitive import environments,
  including package initializers and dynamic-import refusal;
- explicit supported interpreter acceptance; rejected system-interpreter
  shape; PATH/cwd/environment substitution; symlink/ancestry/owner/mode/
  inode/content/probe drift; missing setconfig/defensive APIs; SQLite below
  3.51.3; and upgrade between signature and launcher exec;
- same discriminator across two MCP servers/events/serializers, conflicting
  roles, and Task-first denial;
- immutable N/N+1 bundle, pointer restore, complete direct+shadow proof-set,
  and old-bundle-through-C7 vectors;
- external staged admission/startup/tick denial plus internal
  ACTIVATED+lock+closure helper positives and pre-ACTIVATED I/O negatives;
- C5 ADOPT and DRAINING-REACQUIRE commit-before-return custody, exact
  audit/status/token closure, >8 continuation, and ADVANCE refusal;
- mechanical recomputation and one-field mutation of every §4.2.1
  interpreter/import/bundle/wrapper/projection/pointer/proof/readiness/
  signing/receipt/gate/tick/R0 hash;
- import-manifest JCS+LF length/plain-hash versus domain-hash separation and
  shared `engine/registration_host.py` byte equality;
- stock OpenSSH signature/enrollment/rotation/revocation negatives; and
- temp-file short write, fsync, replace, directory fsync, reopen, cleanup,
  residue, and primary-error preservation.

No test may pass by weakening a validator, using sleeps as race proof,
constructing fake current authority, skipping the installed wrapper, or
treating fail-open as denial.

### 7.4 Real throwaway R0

R0 remains Body C predeployment evidence and needs a separate exact-head R0
GO after implementation. It runs only under a newly created throwaway
HOME/XDG tree and proves every touched path is below that root before the
first write.

This is one narrow exception to v3's production rule that
`R0_THROWAWAY` never persists. The exception is confined as follows:

1. after R0 GO, the harness creates and prepares the complete private fixture:
   HOME/XDG roots, state/database parent, locks, bundles, proof/projection/
   legacy parents, Git/common/root fixtures, temp, config, and every profile
   target—without writing a receipt, protocol row, or CONTROL capability;
2. it descriptor-binds and measures every target, materializes candidate
   bundle/import/proof-vector hashes, captures the finite live-surface
   pre-manifest, and only then emits exact receipt-body and owner-gate v2
   bytes;
3. it pauses until `/usr/bin/ssh-keygen -Y verify` accepts the detached owner
   signature against the exact enrolled allowed-signers contract;
4. it reopens and remeasures every fixture target and candidate byte; any
   difference from the signed gate refuses before persistence;
5. a sealed process-local `R0HarnessAuthority` is constructed only when the
   signed scope is `R0_THROWAWAY`, its non-null `harness_root_hash` matches the
   live descriptor, root/member scope is null, and every configured state,
   profile, bundle, projection, receipt, proof, legacy, temp, and install path is a
   descendant of that descriptor-proven root;
6. only that sealed authority lets the real production cutover APIs persist
   the R0 receipt digest in the throwaway protocol; production installer
   entrypoints cannot construct the seal; and
7. every receiver state under R0 remains deny-only, including after
   generation advance.

R0 GO does not itself sign the gate. R0 persistence cannot touch or open the
live protocol and can never satisfy R1.

For every applicable §4.2.1 barrier id (grouped under cut C0–C7):

1. start the real installer/cutover in an external process;
2. stop it at a deterministic post-durable barrier;
3. send `SIGKILL`, verify death, and discard process memory;
4. start a fresh process with no in-memory journal;
5. read actual file/protocol/audit authority;
6. invoke the real stable installed wrapper and capture exact denial bytes;
7. continue or contain according to the revised cut table; and
8. record immutable evidence fields and hashes.

The matrix includes >8 in-flight members, incomplete staged secret transfer,
ADOPT/DRAINING-REACQUIRE commit-before-return custody, ordinary-runtime and
installer-adapter recovery exhaustion, R1 same-boot/due/reboot scope probes,
schema install faults, native FULL/IOERR, selected-interpreter path/API/
content upgrade drift, old/new receiver byte drift, and failed temp cleanup.
At C0–C5 exactly one old or staged
receiver must emit a seam-valid denial. At C6–C7 an R0-scoped receipt remains
deny-only and can never become ordinary deployment authority.

Before each cut the harness freezes a finite governed-live manifest:

```text
live registration protocol/state DB, WAL, SHM, locks, and receipts
live registration runtime/bundles/config/projection and installed bytes
selected external interpreter ancestry/file identity and capability probe
selected Cursor hook file and normalized AWA-owned rows
AWA/local-jobs definitions, receipts, and launchd job state
current Skills AWA descriptor/pin when present
~/dev AWA overlay files and activation state
AWA source/install identity files named by current host configuration
```

Each record carries canonical path hash, descriptor device/inode/type/mode/
owner/link-count/size, and content hash for regular files; absent is explicit.
The post-cut manifest is captured by a separate read-only process and compared
byte-for-byte. Every cut record hashes both manifests, the throwaway target
manifest, process-kill evidence, and receiver-proof vector.

When an external macOS write observer is available, it is started before the
cut for the exact governed roots plus throwaway parent and its event-log hash
is bound to the record. If unavailable, the record says unavailable and makes
no claim about unobserved global writes; it still proves the finite governed
before/after set and product-declared target confinement. Any observed target
outside the throwaway root, any governed-live byte/metadata change, incomplete
manifest, or missing required descriptor fails R0.

Required R0 report facts:

```text
predeployment_evidence = R0
rollout_stage = NONE
exact_head = <authorized merged implementation head>
live_state_changed = false
cuts = exact observed per-cut records, not a generated name list
barrier_catalog_complete = true only on exact applicable set equality
process_kill_complete = true only from observed process deaths
receiver_continuity_complete = true only from captured installed-seam denials
governed_live_manifest_before_hash
governed_live_manifest_after_hash
throwaway_target_manifest_hash
external_write_observer = available | unavailable
external_write_observation_hash = hash | null
cut_evidence_hash
claim_scope = "FINITE_GOVERNED_SURFACES_AND_OBSERVED_TARGETS"
```

Any absent cut, fake authority, unobserved claim, path outside the throwaway
root, surviving process, governed-live change, incomplete manifest, or claim
beyond `claim_scope` fails R0.

### 7.5 Exact rollout order

```text
fresh exact-byte technical clearance + exact acceptance vector
-> separate exact owner signing-key/allowed-signers enrollment
-> owner acceptance + checked promotion receipt
-> separate exact-baseline implementation GO
-> per-body exact implementation-delivery GO
-> per-body exact-head readiness GO; reviewer App alone approves/arms/merges
-> Bodies A, B, C merged and final exact-head technical clearance
-> separate exact-head R0 GO
-> real throwaway R0 passes
-> separate release/tag/publication GO for exact merged head/version
-> release completes
-> separate Skills binding GO if the ecosystem requires a pin
-> separate installation GO for exact release/bundle
-> separate ~/dev host-wiring/activation GO for exact revisions
-> owner signs exact R1 deployment authority and gives R1 canary GO
-> one named clean single-root canary
-> C1 executes/captures/adjudicates all A01–A29/A32 evidence
-> fresh verifier: partial_rollout=false, shipping clearance passed,
   no blocker, exact revision/critical coverage/blind probe
-> owner signs exact R2 deployment authority and gives R2 rollout GO
```

C1 cannot grant R1 or R2. R0 cannot grant release, installation, host
activation, or R1. Release does not authorize installation; installation
does not authorize Skills or host wiring; host activation does not authorize
R1. A signed owner gate cannot replace plain-language GO. No gate implies
another.

## 8. Owner decisions

### Gate 1 — exact-byte technical clearance

No owner decision is valid until the final whole-file hashes, index-row
hashes, normalized digest, SQL-v2 hash/inventory/leaf result, and fresh
review/verifier return all bind the same revision with no blocker.

### Gate 2 — exact document acceptance and promotion

Run the canonical §7.1 checker in read-only `packet` mode. The packet's
`required_owner_language` is the only valid owner form:

```text
Accept ADR 0026 and native-entry-durable-registration-v4 only for this exact semantic Gate 2 envelope:
<exact JSON serialization of awa-registration-v4-owner-acceptance/v2>
```

The parser accepts JSON whitespace and object-key ordering differences only
after reconstructing exact semantic equality; the owner digest always hashes
canonical JCS. The envelope must contain the source commit, checker hash, all
canonical recovery vector/digest with all four ordered pre/post surface and
backing hashes/modes, normalized constants/digest, resolved receipt path/
schema, narrow authorized actions, explicit denied implications, and exact
Gate 2A evidence. Any omitted, extra, duplicate, type-changed, array-reordered,
or mutated value refuses. The canonical packet must be preserved for recovery.
Every earlier packet/acceptance sentence is invalid and cannot be upgraded by
inference.

The checked `promote` mode and detached receipt must then succeed. Without
both, ADR 0025/frozen v3 remain current. ADR 0025/v3 bodies never change;
index status rows may later record supersession. Gate 2A must first have
separately authorized the exact fingerprint and future contract artifact;
Gate 2 records that evidence but does not create the contract or machine-local
owner-key receipt. Gate 2 authorizes no implementation, delivery, commit,
push, PR, R0/R1, release, Skills, installation, host activation, C1, or R2.

### Gate 2A — owner signing-key enrollment

Before implementation delivery or any deployment-gate signature, the owner
must separately authorize the future contract artifact:

```text
ENROLL AWA owner signing key for principal KleinPerkins and namespace
awa-registration-owner-gate-v2 only:
algorithm ssh-ed25519,
public-key SHA-256 <hex>,
OpenSSH fingerprint <SHA256:...>,
contract path contracts/awa-registration-owner-signers.v1,
contract SHA-256 <hex>,
key-enrollment digest <hex>.
```

No key material or contract is created now. A changed value, rotation, or
revocation requires a new enrollment decision.

### Gate 3 — implementation GO

Only after Gates 1–2 and fresh technical clearance:

```text
GO to implement ADR 0026 using native-entry-durable-registration-v4
from <exact-live-main-oid>.
```

This gate authorizes local code/test implementation only. It does not
authorize commit, push, PR, readiness, merge, R0, release, install, Skills,
host wiring, or rollout.

### Gate 4 — implementation-delivery GO

Required separately for each body:

```text
IMPLEMENTATION-DELIVERY GO for Body <A|B|C> in KleinPerkins/awa,
accepted normalized digest <digest>, exact base <base>, branch <branch>:
commit, push, and open/update one Draft PR only; current owner-key enrollment
hash <enrollment-hash>.
```

### Gate 5 — exact-head readiness and reviewer-App merge

After complete review/checks:

```text
BODY-READINESS GO for Body <A|B|C> at exact head <oid> with checks <vector>.
```

This permits marking that exact head ready. Only the reviewer App may approve,
arm native auto-merge, and merge. A changed head needs a new GO. Agents never
direct-merge or call/enable/disable/pre-arm auto-merge.

### Gate 6 — R0 GO

After exact-head implementation verification:

```text
GO to run v4 R0 against <exact-merged-head> in the throwaway harness only,
using explicit normalized interpreter path <absolute-path> and interpreter
selection/probe hashes <selection-hash>/<probe-hash>.
```

The harness then returns exact `harness_root_hash`, R0 receipt-body hash, and
owner-gate bytes. Before execution continues, the owner supplies the detached
signature over those exact gate bytes. A changed root, head, receipt body, or
gate requires a new signature.

### Gate 7 — release/tag/publication GO

```text
RELEASE GO for exact merged head <oid> as version <version>, tag <tag>,
publication artifact/bundle digest <digest>, and owner-key enrollment hash
<enrollment-hash>, using explicit normalized interpreter path <absolute-path>
and measured selection/interpreter/capability hashes
<selection-hash>/<interpreter-hash>/<probe-hash>.
```

This authorizes only the named release/tag/publication.

### Gate 8 — installation GO

```text
INSTALLATION GO for exact release <version>/<digest> into target
<installation-root>, owner-key enrollment hash <enrollment-hash>, without
host activation, using explicit normalized interpreter path <absolute-path>
whose freshly measured selection/record/probe hashes are
<selection-hash>/<interpreter-hash>/<probe-hash>.
```

### Gate 9 — Skills authority, if applicable

Only when the live ecosystem still requires the Flavor-2 pointer:

```text
SKILLS BINDING GO for exact AWA release <digest> from exact Skills base
<oid>, Draft PR delivery only under Skills governance.
```

Absence of this gate means no Skills change; it does not block when a fresh
source check proves no pin change is applicable.

### Gate 10 — `~/dev` host wiring and activation GO

```text
DEV HOST-WIRING/ACTIVATION GO for installed AWA <digest> from exact
KleinPerkins/dev base <oid>, owner-key enrollment hash <enrollment-hash>,
external-interpreter/probe hashes <interpreter-hash>/<probe-hash>, limited to
named hook/local-job rows and UAT; live selection hash <selection-hash>.
```

Cross-repository delivery follows `~/dev` governance and is not authorized by
AWA implementation/release/install gates.

### Gate 11 — R1 canary GO

After R0 passes, the owner signs the exact R1 gate/receipt vector and names
one root/member; release, installation, and required host wiring must already
be separately authorized and verified:

```text
GO for R1 canary using <owner-gate-digest> for
<canonical-root-hash>/<member-id> with live external-interpreter/probe hashes
<interpreter-hash>/<probe-hash> and selection hash <selection-hash>.
```

Each R1 tick must first produce the one read-only
`outside_scope_same_boot|due|reboot` result from §4.9; any true flag makes the
GO inapplicable to that tick and permits zero mutation.

### Gate 12 — C1 shipping clearance

C1 is evidence-only. It must bind the exact R1 receipt/gate, implementation
head, A01–A29/A32 results, `partial_rollout=false`, and passing fresh verifier
shipping clearance. It grants no mutation or rollout authority.

### Gate 13 — R2 rollout GO

Only after C1 and fresh shipping clearance:

```text
GO for R2 DIRECT rollout using <owner-gate-digest> at
<exact-implementation-head>.
```

No current gate is satisfied by this draft.

## 9. Non-goals and residuals

The exact v3 non-goals remain: dirty-work preservation; multi-root
membership; Task/subagent entry; physical retirement/GC/migration/rotation;
Rescue; production custom VFS; broader platforms; external activation; and
stronger same-user defense.

Retained residuals remain total hook/runtime/host absence; no-event and
broken-wrapper fail-open surfaces; local disk read before model-admission
hook; manual/Tab/external/cloud-early/already-running work; same-UID raw
SQLite/path/memory bypass; unsupported platform/device/VFS/power behavior;
notification visibility; and no automatic dirty-work progress.

V4 adds no performance SLA beyond the existing bounded hook/tick/drain
budgets, no paid runner, no new daemon, no cross-repository writer, and no
live-host change.

## 10. Current NO-GO

The full-change verifier failed shipping clearance and recorded open P1/P2
findings; this draft now also carries exactly the two authorized P3 checker
cleanup corrections in §3. ADR 0026 and v4 are draft. The merged implementation is a
source-evidence subject, not v4 implementation or rollout authority. The
current R0 script is packaging evidence only and must not be run or cited as
v4 R0. No owner signing fingerprint/contract is enrolled, so exact document
acceptance and implementation delivery are also blocked.

Until the owner passes the relevant gates, leave code, tests, contracts,
runtime, hooks, jobs, state, accepted/frozen authorities, GitHub metadata,
releases, installation, Skills, host wiring, R0, R1, C1, R2, and live rollout
unchanged.
