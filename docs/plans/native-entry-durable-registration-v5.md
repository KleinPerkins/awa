# Native Entry Durable Registration

- **Version:** v5
- **Status:** ACCEPTED — FROZEN — DOCUMENTATION ONLY; IMPLEMENTATION DELIVERY AND R0 NO-GO
- **Date:** 2026-09-30
- **Supersedes if accepted:** accepted, frozen
  [`native-entry-durable-registration-v4.md`](native-entry-durable-registration-v4.md).
  While v5 is draft, accepted v4 remains current implementation authority and
  remains byte-identical at SHA-256
  `fef699dfb1586c10d9dd7e768f0ca7cc945029ea330e8ec90151b66bc08ddf71`.
- **Architecture authority:** accepted, immutable
  [ADR 0026](../adr/0026-durable-registration-authority-hardening.md), SHA-256
  `1486135d62ccf9a4fdb1fbaad59a8d5d619f2bd51fa317a1eaa5f0f96db0b82a`.
- **Source baseline:** accepted `main` and implementation branch HEAD
  `bbfef976460a2c87fa24e9759286c7fd1669e34c`.
- **Documentation authorization:** exact operator GO permits only this v5 draft
  and its one DRAFT plan-index row. It permits no accepted-v4/ADR edit, code,
  test, contract, state, key, signing, Git delivery, R0, release, installation,
  activation, or rollout action.
- **Version discipline:** this is a complete standalone successor. Every v4
  requirement is inherited unless an exact `ADMIN`, `V5-S1`, or `V5-S2` delta
  below says otherwise. Historical `v4` labels retained in inherited prose do
  not weaken their force as v5 requirements.
- **Closed-world budget:** canonical SQL v2 retains exactly seven tables,
  nine triggers, ninety-seven independently generated leaf keys, three member
  phases, four protocol modes, three effect outcomes, three transaction
  classes, twenty-four operation kinds, twenty-six runtime reasons, one
  predeployment evidence stage, two rollout authorization stages, and exactly
  three implementation bodies.
- **Canonical SQL v2:** SHA-256
  `b97f02ef67d48886f917368fa420fda0c5dd5942441b23a190732e3cc45106c8`,
  unchanged from accepted v4.
- **Successor delta classes:** `ADMIN` (version/status/index/acceptance
  mechanics only), `V5-S1` (64→96 KiB compatibility seam only), and `V5-S2`
  (pre-delivery enrollment bootstrap only).

**Goal:** preserve accepted v4 and ADR 0026 while repairing exactly two
sequencing defects: SQL-v2-compatible runtime intent reservations and the
owner-enrollment bootstrap required before any implementation-delivery Gate 4.

> **Governance stop:** this draft authorizes documentation only. No status
> promotion, implementation mutation, enrollment publication, commit, push,
> PR, signing, R0, release, installation, activation, or rollout is authorized.

---

## 1. Purpose, baseline, and inherited authority

### 1.1 Exact accepted baseline

This draft derives only from accepted commit
`bbfef976460a2c87fa24e9759286c7fd1669e34c`, not from concurrent dirty
implementation bytes. Its immutable anchors are:

```text
accepted v4       fef699dfb1586c10d9dd7e768f0ca7cc945029ea330e8ec90151b66bc08ddf71
accepted ADR 0026 1486135d62ccf9a4fdb1fbaad59a8d5d619f2bd51fa317a1eaa5f0f96db0b82a
v4 index row      6c920e7e177a37a1092d0d4096a2966bea10a29844ae3f7dbfe07acb6902a3c0
ADR 0026 row      c2ffbac9b939d1217eedc55824c48353a32ab00f7a15b95e151fd785ff873123
```

Exact-base source proves two compatibility gaps:

1. canonical SQL v2 requires `outcome_reservation_bytes >= 98,304`, while both
   branches of `registration_runtime._intent` and the clean/blocked shared test
   fixtures still produce 65,536; and
2. Gate 4 requires a real current owner-key enrollment hash, while the exact
   base contains neither `contracts/awa-registration-owner-signers.v1`, the
   machine-local current receipt, nor a reviewed publisher/validator. Accepted
   Gate 2A records the public identity as `OWNER_AUTHORIZED_NOT_PUBLISHED`.

No public or private key bytes are read or requested by this draft. The
accepted Gate 2A hashes, fingerprint, enrollment digest, and
`owner_authorization_digest` are immutable inputs for a later separately
reviewed packet and separately authorized publication.

### 1.2 Preserved contract

V5 preserves every §1.2 item and closed-world stop from accepted v4 without
reinterpretation. It adds no relation, trigger, leaf key, phase, protocol
mode, effect outcome, transaction class, operation kind, runtime reason,
rollout stage, or implementation body. Exactly three bodies remain.

### 1.3 Byte-level successor provenance

Future technical clearance must compare accepted-v4 bytes to complete-v5 bytes
and classify every changed hunk as exactly `ADMIN`, `V5-S1`, or `V5-S2`.
The v5 acceptance packet binds the ordered hunk pre/post hashes, immutable
v4/ADR hashes, launcher hash, tool hash, draft and accepted v5 hashes, and
exact v5 index-row hashes. An unclassified hunk is a blocker.

Accepted v4 and ADR 0026 are immutable hash anchors, not v5 promotion
surfaces. This draft's only future promotable status surfaces are the v5
status bullet and exact v5 plan-index row. A later v4 index supersession is a
separate index-only authorization and is outside this draft GO.

## 2. Concise counterexamples

| Counterexample | Current result | Required v5 result |
|---|---|---|
| Owner says “accept” without exact checker/source/recovery/envelope bytes | Draft bytes, recovery baseline, post state, or promotion durability can change between review and receipt | Hash-checked acceptance checker plus embedded launcher/tool, exact source, immutable recovery packet, semantic owner envelope, descriptor-safe status-last promotion, two-POST proof, immutable v4/ADR anchors, and canonical detached receipt |
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
| A receipt retry supplies a mismatched owner or sees later unrelated index rows | Durability fsync can mutate state before authorization, while rebuilding from live backing bytes changes the owner envelope and makes a valid completed promotion non-idempotent | Non-mutatingly inspect and validate the exact existing canonical receipt first; reconstruct its original envelope/vector and validate supplied owner bytes/digest before any fsync; only then finalize durability and repeat held receipt, two-POST, immutable-anchor, and residue checks, while tolerating only separately authorized outside-row index additions |
| SQL v2 is installed while runtime `_intent` or shared clean/blocked fixtures still reserve 65,536 outcome bytes | Valid Body B call sites become schema-invalid even though Body A owns the new floor | Body A changes only the two runtime outcome producers and two shared fixture outcome values to 98,304, with focused B assertions and structural scope proof |
| Every body Gate 4 requires a current enrollment hash while Body C owns the absent contract/current publisher | No body can be delivered without authority that cannot yet be published | One pre-delivery Body C bootstrap substage: reviewed tool, exact packet review, separate Gate 3B publication, independent Gate 3C validation, then Gate 4 |
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

| ID | Finding and source evidence | Inherited/v5 decision | Owner | Acceptance evidence | Stop condition |
|---|---|---|---|---|---|
| P1-01 | ADR/plan acceptance lacks v3-grade exact-byte authority | Bind immutable accepted-v4/ADR anchors plus exactly two promotable v5 status surfaces to one sentinel-normalized digest; hash-check the acceptance checker, launcher, and bootstrap payload; bind exact source, recovery vector, hunk ledger, hashes/modes, narrow scope, and receipt path in one semantic owner envelope; descriptor-held status-last promotion emits a canonical receipt only after both POST contexts and immutable anchors validate; identity-bound retirement proves the classified residue inode reached zero links; and an existing receipt reconstructs its original envelope and validates owner input before any durability fsync or live rebaseline | C | Packet determinism; malformed owner/recovery/receipt matrices; source/path/symlink/race/umask/fsync/mode faults; immutable-anchor mutation; candidate/residue substitution; PRE/mixed receipt denial; two-cut reverse recovery; zero-fsync malformed/mismatched-owner retry; exact-existing-receipt finalization after separately authorized outside-row additions | Checker or artifact bytes are invented later, recovery rebaselines, v4/ADR changes, a substituted residue is retired as clean, receipt exists without both POST contexts/immutable anchors/durability, owner refusal follows a durability side effect, any authority field is absent, any non-token byte or canonical mode changes, or partial promotion becomes authority |
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

| V5-S1 | SQL-v2 floor and exact-base Body B producers/fixtures disagree | Permit Body A to change exactly two `_intent` outcome arguments, `RegistrationHarness.clean_intent`/`blocked_intent` outcome values, focused runtime-B assertions, and non-weakened independence structural proof | A | Exact clean/blocked 98,304 outcomes; unchanged external/successor/actions/hashes; AST boundary | Any broader runtime/B edit, another 64 KiB constant change, or validator weakening |
| V5-S2 | Current enrollment is a Gate-4 prerequisite owned by not-yet-deliverable Body C | Add one pre-delivery C bootstrap substage with external tool hash, exact packet review, separate Gate 3B, receipt-last publication, and independent Gate 3C | C | Tool/self-test/static vectors; three-state/fault matrix; exact packet/context/decision; independent observed enrollment hash | Publication precedes exact authority, Gate 2A changes, receipt is not commit point, validator reuses publisher builders, or any fourth body appears |

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

#### 4.1.1 V5-S1 — exact Body A compatibility seam

Body A may change only these SQL-v2 compatibility call sites:

- `engine/registration_runtime.py`, function `_intent`: the non-clean branch's
  `outcome_reservation_bytes` argument changes `64 * 1024` to `96 * 1024`;
- the same function's clean branch changes only that same argument;
- `engine/tests/registration_harness.py`, methods `clean_intent` and
  `blocked_intent`: only the outcome reservation changes 65,536→98,304;
- `engine/tests/test_registration_runtime_b.py`: focused assertions cover
  `CLEAN_ELIGIBLE`, `BLOCKED_DIRTY`, and `BLOCKED_OPERATION`; and
- `engine/tests/test_registration_independence_b.py`: add a non-weakened
  structural proof that exactly those `_intent` outcome producers form the
  production compatibility seam.

Hard negatives: clean external reservation remains 65,536; blocked external
reservation remains zero; successor reservation remains 65,536; action kinds,
request kinds, fingerprints, derived-hash algorithms, coordinator, admission,
recovery, fairness, parser/BLOB limits, `ADOPT_EFFECT`, imports, public APIs,
`registration_admission.py`, `registration_basis.py`, and
`registration_view.py` do not change under this seam. Body A does not acquire
broader Body B ownership. Any additional runtime behavior change stops.

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

#### 4.2.2 V5-S2 — pre-delivery owner-enrollment bootstrap

This is a substage of Body C, not a fourth implementation body. Gate 3 permits
local review of the embedded artifact and synthetic evidence only. No
production publication occurs until exact Gate 3A packet review and separate
Gate 3B publication authority. Gate 3C independently validates publication;
only its real observed enrollment hash can satisfy Gate 4.

Accepted Gate 2A remains immutable:

```text
principal                         KleinPerkins
namespace                         awa-registration-owner-gate-v2
algorithm                         ssh-ed25519
public_key_sha256                 3909ecbba5d835cbfdcf7f1498af2338dccd210e5fa780edf04799e869843565
openssh_fingerprint               SHA256:zMkoOQbGEq7TiPI79e8m8WoKeAkmpEfb6MfnGpS032M
allowed_signers_contract_hash     9155be780c73e65a549ae97326dc56c53045aeaddb697745a95ce191aa472b7e
key_enrollment_digest             0747f869d74ce03debdd91992050a59e2b0a587fa103c9f4ef251220efbf24c9
owner_authorization_digest        dd24db871dc0fd7806371ac7113007e3c9c267f181273a2b290b5968588ee4fe
status                            OWNER_AUTHORIZED_NOT_PUBLISHED
```

V5 never derives a replacement owner-authorization digest. Accepted-v5,
receipt, tool, packet, paths, modes, output hashes, and enrollment hash bind in
`awa-registration-owner-key-bootstrap-context/v1` and the later Gate 3B
decision instead.

##### Closed derivation order

```text
exact payload bytes
-> tool SHA-256 outside payload
-> launcher hash + v5 draft/technical review
-> separate v5 acceptance receipt
-> unchanged accepted Gate 2A
-> later descriptor-stable canonical public input
-> explicit created_wall_ns (never sampled by packet/publish/recover)
-> exact contract + current-receipt preimage + enrollment hash
-> exact packet + packet hash
-> exact Gate 3A packet review (no publication)
-> bootstrap context + exact Gate 3B decision (decision digest outside packet)
-> contract publication and durability proof
-> receipt-last publication/authority commit point
-> independent Gate 3C validation
-> per-body Gate 4
```

No decision digest appears in the packet it authorizes. The embedded payload
contains no prefilled expected tool hash, accepted-v5 digest, packet hash,
enrollment hash, accepted signer public-key bytes, or future decision bytes;
it derives and checks those later values from exact gated inputs.

##### Canonical public input

The later public input grammar is exactly
`ssh-ed25519 SP <strict canonical base64 OpenSSH wire blob> LF`: one line, no
comment, extra whitespace, CR, alternate encoding, or second LF. It must be a
bounded (≤512-byte), descriptor-stable, owner-held regular file with link
count one, mode `0600` or `0644`, opened read-only/no-follow. Validation proves
wire algorithm, framing, exactly 32 key bytes, no trailing bytes, canonical
base64 re-encoding, accepted public-key SHA-256, accepted OpenSSH fingerprint,
and the resulting fixed contract hash. No private-key derivation, signing,
agent, socket, subprocess, or network path exists.

##### Normative packet, context, and decision schemas

`awa-registration-owner-key-bootstrap-packet/v1` has exactly the fields in the
embedded `PACKET_FIELDS`. Its outer canonical document has exactly `packet`
and `packet_sha256`; the digest is domain-separated JCS of the inner packet.
The packet binds the accepted-v5 receipt/digest, launcher-verified tool hash,
public descriptor/identity, immutable Gate 2A values, explicit timestamp,
sequence `"1"`, `ACTIVE`, null predecessor, exact contract/current output
paths/modes/payloads/hashes, enrollment hash, root records, authorized recovery
actions, and denied implications. It contains neither its own digest nor any
Gate 3B decision/digest.

`awa-registration-owner-key-bootstrap-context/v1` has exactly the fields
returned by `bootstrap_context`: accepted-v5 digest/receipt, tool and packet
hashes, signer/contract/current/enrollment hashes, exact output paths/modes,
recovery actions, and denied implications.

`awa-registration-owner-key-bootstrap-publication-go/v1` has exactly
`schema,repository,authorized_by,action,bootstrap_context,authorized,
denied_implications`. Its decision digest is domain-separated JCS outside the
packet/context. Exact semantic equality is mandatory.

The ADR-defined current receipt schema remains unchanged. It stores the
accepted Gate 2A owner-authorization digest and the explicit packet timestamp.

##### Cross-root state and recovery

The primary classifier recognizes only:

1. `ABSENT_CONTRACT/ABSENT_RECEIPT`;
2. `EXACT_CONTRACT/ABSENT_RECEIPT`; and
3. `EXACT_CONTRACT/EXACT_RECEIPT`.

Receipt final-name publication is the authority commit point. Every mismatch,
orphan receipt, unknown residue, symlink/nonregular, unsafe metadata,
substituted inode, stale authority, or unexpected sequence/rotation refuses
without cleanup or authority. Residue proof is subordinate, never a fourth
state: only the deterministic packet-bound name and exact bytes/mode/owner
may establish same-operation residue. A one-link pre-final residue may be
hard-linked to the absent final name and parent-fsynced; an existing final
must be the same held inode with link count two before residue retirement.
Every such completion still requires the same exact Gate 3B packet/authority.

`publish` handles absent/absent, durability-finalizes exact-existing under
the exact write authority for exact/exact, and sends contract-only state to
explicit `recover`. `recover`
requires the same exact packet and Gate 3B decision; it never self-authorizes.
For exact-contract/absent-receipt it may forward-complete or rollback only the
exact contract when both actions are named by Gate 3B. Any receipt entry,
including malformed or unsafe, permanently prohibits rollback. Exact/exact
may only finalize durability or retire descriptor-proven same-operation temp
links; it never rolls back a primary.

Publication is descriptor-held, no-follow, no-overwrite, full-write,
`fchmod`, file-fsync, hard-link-to-absent-final, parent-fsync,
residue-unlink, second-parent-fsync, reopen/rebind/revalidate. Contract is
published and durably revalidated first; receipt is published last. No
replace-overwrite is used. Primary failure remains primary; uncertainty is a
refusal, not success.

##### Independent validator

`validate` independently parses raw public/contract/current/packet/decision
bytes and reconstructs every hash. Its `v_*` call graph cannot call publisher
builders, `p_*` mutation/state helpers, or shared receipt constructors. Static
AST and syscall guards enforce no write-capable open, mkdir, chmod, link,
unlink, rename, write, fsync, signing, socket, agent, network, or clock path.
Gate 3C runs this code in a fresh process under ordinary and optimized Python;
its observed contract/current hashes and enrollment hash must equal Gate 3B.

##### Canonical launcher and bootstrap payload

- **Acceptance checker SHA-256:** `89463fe0da9bc945aff654ca199d50fc736f25212272613d86628019210a5714`

<!-- awa-v5-acceptance-checker:v1:begin -->
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

SOURCE_COMMIT = "bbfef976460a2c87fa24e9759286c7fd1669e34c"
REPOSITORY = "KleinPerkins/awa"
ALGORITHM = "awa-registration-v5-acceptance-body/v1"
DOMAIN = ALGORITHM.encode("ascii") + b"\x00"
SENTINEL_TEXT = "__AWA_V5_ACCEPTED_STATUS_TOKEN_V1__"
SENTINEL = SENTINEL_TEXT.encode("ascii")
OWNER_SCHEMA = "awa-registration-v5-owner-acceptance/v2"
PACKET_SCHEMA = "awa-registration-v5-acceptance-packet/v2"
RECOVERY_SCHEMA = "awa-registration-v5-recovery-vector/v1"
OWNER_PREFIX = (
    "Accept native-entry-durable-registration-v5 only for "
    "this exact semantic Gate 2 envelope:\n"
).encode("ascii")
RECEIPT_SCHEMA = "awa-registration-v5-acceptance-promotion/v2"
PLAN_REL = "docs/plans/native-entry-durable-registration-v5.md"
RECEIPT_REL = (
    "awa/governance/native-entry-durable-registration-v5/"
    "acceptance-promotion.json"
)
CHECKER_BEGIN = (
    b"<!-- awa-v5-" + b"acceptance-checker:v1:begin -->\n```python\n"
)
CHECKER_END = (
    b"```\n<!-- awa-v5-" + b"acceptance-checker:v1:end -->"
)
LAUNCHER_BEGIN = b"<!-- awa-v5-" + b"canonical-launcher:v1:begin -->\n```python\n"
LAUNCHER_END = b"```\n<!-- awa-v5-" + b"canonical-launcher:v1:end -->"
BOOTSTRAP_BEGIN = b"<!-- awa-v5-" + b"enrollment-bootstrap-tool:v1:begin -->\n```python\n"
BOOTSTRAP_END = b"```\n<!-- awa-v5-" + b"enrollment-bootstrap-tool:v1:end -->"
HARNESS_BEGIN = b"<!-- awa-v5-" + b"bootstrap-fault-harness:v1:begin -->\n```python\n"
HARNESS_END = b"```\n<!-- awa-v5-" + b"bootstrap-fault-harness:v1:end -->"
ARTIFACT_HASH_LABELS = {"launcher_sha256": b"Canonical launcher SHA-256", "checker_sha256": b"Acceptance checker SHA-256", "bootstrap_sha256": b"Bootstrap tool SHA-256", "harness_sha256": b"Bootstrap fault harness SHA-256"}
IMMUTABLE_ANCHORS = (
    ("docs/plans/native-entry-durable-registration-v4.md", "FULL_FILE", "fef699dfb1586c10d9dd7e768f0ca7cc945029ea330e8ec90151b66bc08ddf71"),
    ("docs/adr/0026-durable-registration-authority-hardening.md", "FULL_FILE", "1486135d62ccf9a4fdb1fbaad59a8d5d619f2bd51fa317a1eaa5f0f96db0b82a"),
    ("docs/adr/README.md", "EXACT_ROW", "c2ffbac9b939d1217eedc55824c48353a32ab00f7a15b95e151fd785ff873123"),
    ("docs/plans/README.md", "V4_EXACT_ROW", "6c920e7e177a37a1092d0d4096a2966bea10a29844ae3f7dbfe07acb6902a3c0"),
)
ADR_ROW = "| [0026](0026-durable-registration-authority-hardening.md) | Accepted — 2026-09-29 | Conditionally supersede ADR 0025 with canonical SQL v2, typed recovery boundaries, installer-selected measured interpreter capability, external-deny/internal custody, complete authority preimages, restart-stable recovery, offline owner gates, and separately gated evidence. |\n".encode("utf-8")
V4_ROW = "| `native-entry-durable-registration-v4.md` | ACCEPTED — GOVERNANCE ONLY; IMPLEMENTATION AND R0 NO-GO — 2026-09-29 | Conditional v3 successor with exact SQL v2, typed exhaustion, measured installer-selected interpreter, staged custody and >8 recovery, closed authority vectors, generation bundles, offline signing, status-last acceptance, three bodies, and finite-scope R0. |\n".encode("utf-8")

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
    ("docs/plans/README.md", "EXACT_ROW", b64('| `native-entry-durable-registration-v5.md` | DRAFT — DOCUMENTATION ONLY; IMPLEMENTATION DELIVERY AND R0 NO-GO — 2026-09-30 | Full successor to accepted v4 under ADR 0026; limits Body A to the exact 64→96 KiB runtime compatibility seam and adds a separately reviewed, separately authorized Body C enrollment bootstrap before any Gate 4. |\n'), "DRAFT", "ACCEPTED"),
    (
        PLAN_REL, "FULL_FILE",
        b64("- **Status:** DRAFT (for review) — DOCUMENTATION ONLY; "
            "IMPLEMENTATION DELIVERY AND R0 NO-GO\n"),
        "DRAFT (for review)", "ACCEPTED — FROZEN",
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
    "PROMOTE_EXACTLY_TWO_STATUS_TOKENS",
    "PUBLISH_ONE_DETACHED_ACCEPTANCE_RECEIPT",
]
DENIED_IMPLICATIONS = [
    "ACCEPT_OR_EDIT_OTHER_DOCUMENTS_OR_ANCHORS",
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


def marked_payload(plan: bytes, begin: bytes, end: bytes, label: str) -> bytes:
    if plan.count(begin) != 1 or plan.count(end) != 1:
        fail(f"{label} markers are not unique")
    payload = plan.split(begin, 1)[1].split(end, 1)[0]
    payload.decode("utf-8", "strict")
    if b"\r" in payload or b"\x00" in payload or not payload.endswith(b"\n"):
        fail(f"{label} payload framing is invalid")
    return payload

def artifact_hashes(plan: bytes) -> dict[str, str]:
    payloads = {"launcher_sha256": marked_payload(plan, LAUNCHER_BEGIN, LAUNCHER_END, "launcher"), "checker_sha256": checker_bytes(plan), "bootstrap_sha256": marked_payload(plan, BOOTSTRAP_BEGIN, BOOTSTRAP_END, "bootstrap"), "harness_sha256": marked_payload(plan, HARNESS_BEGIN, HARNESS_END, "harness")}
    result = {key: sha256(value) for key, value in payloads.items()}
    for key, label in ARTIFACT_HASH_LABELS.items():
        recorded = b"- **" + label + b":** `" + result[key].encode("ascii") + b"`"
        if plan.count(recorded) != 1:
            fail(f"{key}: recorded artifact hash mismatch")
    return result

def immutable_anchor_vector(root_descriptor: int) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for path, kind, expected in IMMUTABLE_ANCHORS:
        backing, mode = read_relative(root_descriptor, path)
        if mode != 0o644:
            fail(f"{path}: immutable anchor mode mismatch")
        value = backing
        if kind == "EXACT_ROW":
            if backing.count(ADR_ROW) != 1: fail("ADR 0026 immutable row mismatch")
            value = ADR_ROW
        elif kind == "V4_EXACT_ROW":
            if backing.count(V4_ROW) != 1: fail("v4 immutable row mismatch")
            value = V4_ROW
        if sha256(value) != expected:
            fail(f"{path}: immutable anchor hash mismatch")
        result.append({"kind": kind, "path": path, "sha256": expected})
    return result

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
) -> BaseException | None:
    if primary is None and sys.exc_info()[1] is not None:
        primary = sys.exc_info()[1]
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
            primary.__context__ = cleanup_error
            primary.add_note(
                "secondary descriptor cleanup failure: "
                + repr(cleanup_error)
            )
        return cleanup_error
    if cleanup_error is not None:
        raise cleanup_error
    return None


def open_repo_descriptor(root: Path) -> int:
    descriptor = os.open(
        root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    )
    try:
        checked_directory(descriptor, str(root), False)
        verify_repo_anchor(root, descriptor)
    except BaseException as error:
        close_owned_descriptors(descriptor, primary=error)
        raise
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
        raise
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
                raise
            descriptor = child
        checked_directory(descriptor, str(path), owner_only)
        return descriptor
    except BaseException as error:
        close_owned_descriptors(descriptor, primary=error)
        raise


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
            try:
                close_owned_descriptors(descriptor)
            except BaseException as error:
                descriptor = None
                close_owned_descriptors(child, primary=error)
                raise
            descriptor = child
        return descriptor, parts[-1]
    except BaseException:
        close_owned_descriptors(descriptor)
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
            or stat.S_IMODE(opened.st_mode) != stat.S_IMODE(metadata.st_mode)
            or (opened.st_dev, opened.st_ino)
            != (metadata.st_dev, metadata.st_ino)
        ):
            fail(f"{label}: not one stable owner-held regular file")
    except BaseException as error:
        close_owned_descriptors(descriptor, primary=error)
        raise
    return descriptor


def read_descriptor(descriptor: int) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    while True:
        chunk = os.read(descriptor, 131072)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def regular_metadata_tuple(
    metadata: os.stat_result,
) -> tuple[int, int, int, int, int, int, int, bool]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_uid,
        stat.S_IMODE(metadata.st_mode),
        metadata.st_nlink,
        stat.S_ISREG(metadata.st_mode),
    )


def read_held_regular(
    parent: int, name: str, descriptor: int, label: str
) -> tuple[bytes, int]:
    opened = os.fstat(descriptor)
    visible = entry_metadata(parent, name)
    if (
        visible is None
        or regular_metadata_tuple(visible)
        != regular_metadata_tuple(opened)
        or not stat.S_ISREG(opened.st_mode)
        or opened.st_uid != os.geteuid()
        or opened.st_nlink != 1
    ):
        fail(f"{label}: held/visible pre-read metadata mismatch")
    value = read_descriptor(descriptor)
    after = os.fstat(descriptor)
    visible_after = entry_metadata(parent, name)
    if (
        visible_after is None
        or regular_metadata_tuple(after)
        != regular_metadata_tuple(opened)
        or regular_metadata_tuple(visible_after)
        != regular_metadata_tuple(opened)
    ):
        fail(f"{label}: held/visible post-read metadata mismatch")
    return value, stat.S_IMODE(opened.st_mode)


def read_relative(root_descriptor: int, path: str) -> tuple[bytes, int]:
    parent, name = open_parent(root_descriptor, path)
    try:
        descriptor = open_regular(parent, name, path)
        try:
            return read_held_regular(parent, name, descriptor, path)
        finally:
            close_owned_descriptors(descriptor)
    finally:
        close_owned_descriptors(parent)

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
    artifacts: dict[str, str],
    anchors: list[dict[str, str]],
) -> dict[str, object]:
    return {
        **artifacts,
        "immutable_anchors": anchors,
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
        "launcher_sha256": recovery["launcher_sha256"],
        "bootstrap_sha256": recovery["bootstrap_sha256"],
        "harness_sha256": recovery["harness_sha256"],
        "immutable_anchors": recovery["immutable_anchors"],
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
    artifacts = artifact_hashes(plan)
    if (
        globals().get("__v5_full_plan_sha256_expected__") != sha256(plan)
        or globals().get("__v5_checker_sha256_expected__") != artifacts["checker_sha256"]
        or globals().get("__v5_bootstrap_sha256_expected__") != artifacts["bootstrap_sha256"]
        or globals().get("__v5_harness_sha256_expected__") != artifacts["harness_sha256"]
    ):
        fail("independently supplied launcher expectations mismatch")
    rows, normalized_digest = surfaces(root_descriptor)
    anchors = immutable_anchor_vector(root_descriptor)
    recovery = recovery_vector(rows, normalized_digest, artifacts, anchors)
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
        close_owned_descriptors(descriptor)


def validate_held_entry(
    parent: int,
    name: str,
    descriptor: int,
    label: str,
    expected_hash: str,
    expected_mode: int,
) -> bytes:
    value, mode = read_held_regular(parent, name, descriptor, label)
    if mode != expected_mode:
        fail(f"{label}: held mode mismatch")
    if sha256(value) != expected_hash:
        fail(f"{label}: held content hash mismatch")
    return value

def residue_name(name: str) -> str:
    return f".{name}.awa-v5-acceptance-residue-v1"


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
        value, mode = read_held_regular(
            parent, name, descriptor, label
        )
        return classify_bytes_mode(value, mode, row, label)
    finally:
        close_owned_descriptors(descriptor)


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
        close_owned_descriptors(parent)


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
        close_owned_descriptors(parent)


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
            close_owned_descriptors(old_descriptor)
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
            close_owned_descriptors(descriptor)
        close_owned_descriptors(parent)


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
        raise
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
            regular_metadata_tuple(classified_metadata),
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
            regular_metadata_tuple(rebound_metadata),
            sha256(rebound),
        ) != classified_binding:
            fail(f'{row["path"]}: classified residue binding changed')
        os.unlink(residue, dir_fd=parent)
        os.fsync(parent)
        retired_metadata = os.fstat(residue_descriptor)
        expected_retired = list(classified_binding[0])
        expected_retired[6] = 0
        if regular_metadata_tuple(retired_metadata) != tuple(
            expected_retired
        ):
            fail(
                f'{row["path"]}: classified residue inode was not retired'
            )
        retired = read_descriptor(residue_descriptor)
        retired_after = os.fstat(residue_descriptor)
        if (
            regular_metadata_tuple(retired_after),
            sha256(retired),
        ) != (tuple(expected_retired), classified_binding[1]):
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
        raise
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
            close_owned_descriptors(parent)
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
            close_owned_descriptors(parent)


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
                raise
            try:
                close_owned_descriptors(descriptor)
            except BaseException as error:
                descriptor = None
                close_owned_descriptors(child, primary=error)
                raise
            descriptor = child
        return descriptor
    except BaseException as error:
        close_owned_descriptors(descriptor, primary=error)
        raise


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
        raise
    return descriptor


def receipt_entry(parent: int) -> os.stat_result | None:
    return entry_metadata(parent, PurePosixPath(RECEIPT_REL).name)


def receipt_residue_entry(parent: int) -> os.stat_result | None:
    return entry_metadata(parent, receipt_candidate_name())


def receipt_candidate_name() -> str:
    return (
        f".{PurePosixPath(RECEIPT_REL).name}."
        "awa-v5-acceptance-residue-v1"
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
            close_owned_descriptors(descriptor)


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
        "bootstrap_sha256",
        "checker_sha256",
        "harness_sha256",
        "immutable_anchors",
        "launcher_sha256",
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
        or not valid_hash(value.get("launcher_sha256"))
        or not valid_hash(value.get("bootstrap_sha256"))
        or not valid_hash(value.get("harness_sha256"))
        or not valid_hash(value.get("normalized_digest"))
    ):
        fail("recovery vector fixed field mismatch")
    plan, _ = read_relative(root_descriptor, PLAN_REL)
    observed_artifacts = artifact_hashes(plan)
    if any(value[key] != observed_artifacts[key] for key in observed_artifacts):
        fail("recovery vector artifact hash mismatch")
    if value.get("immutable_anchors") != immutable_anchor_vector(root_descriptor):
        fail("recovery vector immutable anchor mismatch")
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
    validate_recovery_vector(root_descriptor, expected["recovery_vector"])
    return {
        "owner_acceptance_digest": owner_digest(expected),
        "owner_acceptance_envelope": expected,
        "required_owner_language":
            (OWNER_PREFIX + jcs(expected)).decode("utf-8"),
        "schema": PACKET_SCHEMA,
    }


def parse_owner_language(
    root_descriptor: int, value: object
) -> dict[str, object]:
    if type(value) is not str:
        fail("required owner language is not text")
    raw = value.encode("utf-8")
    if not raw.startswith(OWNER_PREFIX):
        fail("required owner language prefix mismatch")
    parsed = strict_json(raw[len(OWNER_PREFIX):])
    if not isinstance(parsed, dict):
        fail("required owner language envelope is not an object")
    recovery = validate_recovery_vector(
        root_descriptor, parsed.get("recovery_vector")
    )
    expected = acceptance_envelope(recovery)
    if parsed != expected or jcs(parsed) != jcs(expected):
        fail("required owner language semantic mismatch")
    return parsed


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
        "owner_acceptance_digest",
        "owner_acceptance_envelope",
        "required_owner_language",
        "schema",
    }:
        fail("recovery packet key set mismatch")
    if value != jcs(parsed) + b"\n":
        fail("recovery packet is not canonical JCS plus one LF")
    if parsed.get("schema") != PACKET_SCHEMA:
        fail("recovery packet schema mismatch")
    owner = parse_owner_language(
        root_descriptor, parsed.get("required_owner_language")
    )
    supplied = parsed.get("owner_acceptance_envelope")
    if not isinstance(supplied, dict):
        fail("owner acceptance envelope is not an object")
    recovery = validate_recovery_vector(
        root_descriptor, supplied.get("recovery_vector")
    )
    expected = acceptance_envelope(recovery)
    if (
        supplied != expected
        or jcs(supplied) != jcs(expected)
        or owner != expected
        or parsed.get("owner_acceptance_digest") != owner_digest(expected)
    ):
        fail("recovery packet semantic mismatch")
    return parsed


def recover_preflight(
    root_descriptor: int, packet_bytes: bytes
) -> dict[str, object]:
    original = parse_packet(root_descriptor, packet_bytes)
    rows = original["owner_acceptance_envelope"][
        "recovery_vector"
    ]["ordered_surfaces"]
    for row in rows:
        classify_pair(root_descriptor, row)
    return original

def receipt_object(
    root_descriptor: int,
    expected: dict[str, object],
    acceptance_digest: str,
) -> dict[str, object]:
    rows = expected["recovery_vector"]["ordered_surfaces"]
    if governed_context_state(root_descriptor, rows) != ["POST"] * len(SPECS):
        fail("receipt construction requires two exact POST contexts")
    result = {
        "algorithm": ALGORITHM,
        "bootstrap_sha256": expected["bootstrap_sha256"],
        "checker_sha256": expected["checker_sha256"],
        "harness_sha256": expected["harness_sha256"],
        "immutable_anchors": expected["immutable_anchors"],
        "launcher_sha256": expected["launcher_sha256"],
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
        "bootstrap_sha256",
        "checker_sha256",
        "harness_sha256",
        "immutable_anchors",
        "launcher_sha256",
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
    ) != ["POST"] * len(SPECS):
        fail("receipt does not prove two exact POST contexts/modes")
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
        close_owned_descriptors(descriptor)
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
        close_owned_descriptors(descriptor)


def packet(root: Path) -> None:
    require_source(root)
    root_descriptor = open_repo_descriptor(root)
    try:
        result = packet_object(root_descriptor)
        rows = result["owner_acceptance_envelope"][
            "recovery_vector"
        ]["ordered_surfaces"]
        if exact_backing_state(root_descriptor, rows) != ["PRE"] * len(SPECS):
            fail("packet requires two exact preimages")
        sys.stdout.buffer.write(jcs(result) + b"\n")
    finally:
        close_owned_descriptors(root_descriptor)


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
                        try:
                            close_owned_descriptors(root_descriptor)
                        except BaseException as error:
                            root_descriptor = None
                            close_owned_descriptors(reopened, primary=error)
                            raise
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
                        close_owned_descriptors(lock)
                finally:
                    close_owned_descriptors(descriptor)
            lock = acquire_lock(state_parent)
            try:
                require_source(root)
                reopened = open_repo_descriptor(root)
                try:
                    close_owned_descriptors(root_descriptor)
                except BaseException as error:
                    root_descriptor = None
                    close_owned_descriptors(reopened, primary=error)
                    raise
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
                ) != ["POST"] * len(SPECS):
                    fail("promotion did not produce two POST contexts")
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
                close_owned_descriptors(lock)
        finally:
            close_owned_descriptors(state_parent)
    finally:
        close_owned_descriptors(root_descriptor)


def recover_pre(root: Path, packet_bytes: bytes) -> None:
    require_source(root)
    root_descriptor = open_repo_descriptor(root)
    try:
        original = recover_preflight(root_descriptor, packet_bytes)
        rows = original["owner_acceptance_envelope"][
            "recovery_vector"
        ]["ordered_surfaces"]
        state_parent = open_state_parent()
        try:
            lock = acquire_lock(state_parent)
            try:
                require_source(root)
                reopened = open_repo_descriptor(root)
                try:
                    close_owned_descriptors(root_descriptor)
                except BaseException as error:
                    root_descriptor = None
                    close_owned_descriptors(reopened, primary=error)
                    raise
                root_descriptor = reopened
                original = recover_preflight(
                    root_descriptor, packet_bytes
                )
                rows = original["owner_acceptance_envelope"][
                    "recovery_vector"
                ]["ordered_surfaces"]
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
                ) != ["PRE"] * len(SPECS):
                    fail("preimage recovery incomplete")
                if any(
                    classify_pair(root_descriptor, row)[1] is not None
                    for row in rows
                ):
                    fail("preimage recovery left deterministic residue")
                verify_repo_anchor(root, root_descriptor)
            finally:
                close_owned_descriptors(lock)
        finally:
            close_owned_descriptors(state_parent)
    finally:
        close_owned_descriptors(root_descriptor)


def read_external_input(path_text: str) -> bytes:
    path = Path(path_text)
    if not path.is_absolute() or Path(os.path.normpath(path)) != path:
        fail("authority input path is not normalized absolute")
    parent = open_absolute_directory(path.parent, False)
    try:
        descriptor = open_regular(parent, path.name, "authority input")
        try:
            value, mode = read_held_regular(
                parent, path.name, descriptor, "authority input"
            )
            if mode not in {0o600, 0o644}:
                fail("authority input mode is not canonical")
            return value
        finally:
            close_owned_descriptors(descriptor)
    finally:
        close_owned_descriptors(parent)

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
                close_owned_descriptors(state_parent)
        finally:
            close_owned_descriptors(root_descriptor)
    else:
        fail("checker mode/argument mismatch")


if not globals().get("__acceptance_harness_import__", False):
    main()
```
<!-- awa-v5-acceptance-checker:v1:end -->

- **Canonical launcher SHA-256:** `9a17cd51bb88e07fa640e42b63386ac2c336fbcfceafdeaee5a0cf0cb5774289`

<!-- awa-v5-canonical-launcher:v1:begin -->
```python
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import stat
import sys

HEX64 = re.compile(r"^[0-9a-f]{64}$")
MARKERS = {
    "acceptance": (b"<!-- awa-v5-" + b"acceptance-checker:v1:begin -->\n```python\n", b"```\n<!-- awa-v5-" + b"acceptance-checker:v1:end -->"),
    "bootstrap": (b"<!-- awa-v5-" + b"enrollment-bootstrap-tool:v1:begin -->\n```python\n", b"```\n<!-- awa-v5-" + b"enrollment-bootstrap-tool:v1:end -->"),
    "harness": (b"<!-- awa-v5-" + b"bootstrap-fault-harness:v1:begin -->\n```python\n", b"```\n<!-- awa-v5-" + b"bootstrap-fault-harness:v1:end -->"),
}


def fail(message: str) -> None:
    raise SystemExit("awa-v5-launcher: " + message)


def close_owned_descriptors(*descriptors: int | None, primary: BaseException | None = None) -> None:
    if primary is None and sys.exc_info()[1] is not None:
        primary = sys.exc_info()[1]
    cleanup: BaseException | None = None
    for descriptor in descriptors:
        if descriptor is None:
            continue
        try:
            os.close(descriptor)
        except BaseException as error:
            if cleanup is None:
                cleanup = error
    if primary is not None:
        if cleanup is not None:
            raise primary from cleanup
        raise primary
    if cleanup is not None:
        raise cleanup


def read_plan(path: pathlib.Path) -> bytes:
    if not path.is_absolute() or pathlib.Path(os.path.normpath(path)) != path:
        fail("plan path is not normalized absolute")
    parent: int | None = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    descriptor: int | None = None
    try:
        if not stat.S_ISDIR(os.fstat(parent).st_mode):
            fail("plan parent is not a directory")
        descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        before = os.fstat(descriptor)
        visible = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid() or before.st_nlink != 1 or stat.S_IMODE(before.st_mode) != 0o644 or (visible.st_dev, visible.st_ino) != (before.st_dev, before.st_ino):
            fail("plan is not one canonical owner-held regular file")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 131072)
            if not chunk:
                break
            chunks.append(chunk)
        raw = b"".join(chunks)
        after = os.fstat(descriptor)
        rebound = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_uid, before.st_nlink, stat.S_IMODE(before.st_mode)) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_uid, after.st_nlink, stat.S_IMODE(after.st_mode)) or (rebound.st_dev, rebound.st_ino) != (after.st_dev, after.st_ino):
            fail("plan changed during descriptor read")
        close_owned_descriptors(descriptor, parent)
        descriptor = None
        parent = None
        return raw
    except BaseException as error:
        close_owned_descriptors(descriptor, parent, primary=error)
    fail("unreachable plan read")


def extract(raw: bytes, target: str) -> bytes:
    begin, end = MARKERS[target]
    if raw.count(begin) != 1 or raw.count(end) != 1:
        fail(target + " markers are not exact")
    payload = raw.split(begin, 1)[1].split(end, 1)[0]
    try:
        payload.decode("utf-8", "strict")
    except UnicodeError as error:
        raise SystemExit("awa-v5-launcher: payload is not UTF-8") from error
    if b"\r" in payload or b"\x00" in payload or not payload.startswith(b"from __future__") or not payload.endswith(b"\n"):
        fail(target + " payload framing is invalid")
    return payload


def verified_payloads(raw: bytes, expected_plan: str, expected_checker: str, expected_bootstrap: str, expected_harness: str) -> dict[str, bytes]:
    if hashlib.sha256(raw).hexdigest() != expected_plan:
        fail("independently supplied full-plan hash mismatch")
    payloads = {name: extract(raw, name) for name in MARKERS}
    if hashlib.sha256(payloads["acceptance"]).hexdigest() != expected_checker:
        fail("independently supplied checker hash mismatch")
    if hashlib.sha256(payloads["bootstrap"]).hexdigest() != expected_bootstrap:
        fail("independently supplied bootstrap hash mismatch")
    if hashlib.sha256(payloads["harness"]).hexdigest() != expected_harness:
        fail("independently supplied harness hash mismatch")
    return payloads


def expect_refusal(function, label: str) -> str:
    try:
        function()
    except SystemExit:
        return label
    fail("self-test expected refusal: " + label)


def substitution_self_test(raw: bytes, expected_plan: str, expected_checker: str, expected_bootstrap: str, expected_harness: str, payloads: dict[str, bytes]) -> None:
    changed_bootstrap = payloads["bootstrap"].replace(b"from __future__", b"from  __future__", 1)
    changed_bootstrap_hash = hashlib.sha256(changed_bootstrap).hexdigest()
    begin, end = MARKERS["bootstrap"]
    co_modified = raw.split(begin, 1)[0] + begin + changed_bootstrap + end + raw.split(end, 1)[1]
    co_modified = re.sub(rb"- \*\*Bootstrap tool SHA-256:\*\* `[0-9a-f]{64}`", b"- **Bootstrap tool SHA-256:** `" + changed_bootstrap_hash.encode() + b"`", co_modified, count=1)
    changed_checker = payloads["acceptance"].replace(b"from __future__", b"from  __future__", 1)
    checker_hash = hashlib.sha256(changed_checker).hexdigest()
    cbegin, cend = MARKERS["acceptance"]
    checker_modified = raw.split(cbegin, 1)[0] + cbegin + changed_checker + cend + raw.split(cend, 1)[1]
    checker_modified = re.sub(rb"- \*\*Acceptance checker SHA-256:\*\* `[0-9a-f]{64}`", b"- **Acceptance checker SHA-256:** `" + checker_hash.encode() + b"`", checker_modified, count=1)
    vectors = [
        expect_refusal(lambda: verified_payloads(co_modified, expected_plan, expected_checker, expected_bootstrap, expected_harness), "CO_MODIFIED_BOOTSTRAP_FIXED_FULL_PLAN"),
        expect_refusal(lambda: verified_payloads(co_modified, hashlib.sha256(co_modified).hexdigest(), expected_checker, expected_bootstrap, expected_harness), "CO_MODIFIED_BOOTSTRAP_FIXED_PAYLOAD"),
        expect_refusal(lambda: verified_payloads(checker_modified, expected_plan, expected_checker, expected_bootstrap, expected_harness), "CO_MODIFIED_CHECKER_FIXED_FULL_PLAN"),
        expect_refusal(lambda: verified_payloads(checker_modified, hashlib.sha256(checker_modified).hexdigest(), expected_checker, expected_bootstrap, expected_harness), "CO_MODIFIED_CHECKER_FIXED_PAYLOAD"),
    ]
    sys.stdout.write(json.dumps({"result": "PASS", "schema": "awa-v5-launcher-self-test/v1", "vector_count": str(len(vectors)), "vectors": vectors}, sort_keys=True, separators=(",", ":")) + "\n")


def main() -> None:
    if len(sys.argv) < 8:
        fail("usage: launcher PLAN EXPECTED_PLAN EXPECTED_CHECKER EXPECTED_BOOTSTRAP EXPECTED_HARNESS acceptance|bootstrap|harness|self-test MODE [ARGS...]")
    plan = pathlib.Path(sys.argv[1])
    expected_plan, expected_checker, expected_bootstrap, expected_harness = sys.argv[2:6]
    target = sys.argv[6]
    if target not in {*MARKERS, "self-test"} or any(HEX64.fullmatch(value) is None for value in (expected_plan, expected_checker, expected_bootstrap, expected_harness)):
        fail("independent expectations or target are invalid")
    raw = read_plan(plan)
    try:
        raw.decode("utf-8", "strict")
    except UnicodeError as error:
        raise SystemExit("awa-v5-launcher: plan is not UTF-8") from error
    if b"\r" in raw or b"\x00" in raw or not raw.endswith(b"\n"):
        fail("plan framing is invalid")
    payloads = verified_payloads(raw, expected_plan, expected_checker, expected_bootstrap, expected_harness)
    if target == "self-test":
        substitution_self_test(raw, expected_plan, expected_checker, expected_bootstrap, expected_harness, payloads)
        return
    payload = payloads[target]
    source = str(plan) + "::awa-v5-" + target + "/v1"
    sys.argv = [source] + sys.argv[7:]
    scope = {
        "__name__": "__main__", "__file__": source,
        "__v5_full_plan_sha256_expected__": expected_plan,
        "__v5_checker_sha256_expected__": expected_checker,
        "__v5_bootstrap_sha256_expected__": expected_bootstrap,
        "__v5_harness_sha256_expected__": expected_harness,
        "__bootstrap_payload_bytes__": payloads["bootstrap"],
        "__bootstrap_tool_sha256__": expected_bootstrap,
        "__v5_plan_path__": str(plan),
    }
    exec(compile(payload, source, "exec", dont_inherit=True), scope, scope)


main()
```
<!-- awa-v5-canonical-launcher:v1:end -->

The sole launcher accepts independently supplied expected full-plan, checker,
bootstrap, and harness hashes before compiling any extracted payload. A hash
recorded only inside a co-modified plan is never a trust root.

- **Bootstrap tool SHA-256:** `5ab017188cc03f58663f44eda85cc7f59b4717e1e7d939ccbe9d64fcfc071399`

<!-- awa-v5-enrollment-bootstrap-tool:v1:begin -->
```python
from __future__ import annotations

import ast
import base64
import binascii
import fcntl
import hashlib
import json
import os
import pathlib
import re
import stat
import struct
import sys
import tempfile

BASE_COMMIT = "bbfef976460a2c87fa24e9759286c7fd1669e34c"
V4_SHA256 = "fef699dfb1586c10d9dd7e768f0ca7cc945029ea330e8ec90151b66bc08ddf71"
ADR_0026_SHA256 = "1486135d62ccf9a4fdb1fbaad59a8d5d619f2bd51fa317a1eaa5f0f96db0b82a"
BOOTSTRAP_LAUNCHER_SHA256 = "9a17cd51bb88e07fa640e42b63386ac2c336fbcfceafdeaee5a0cf0cb5774289"
PRINCIPAL = "KleinPerkins"
NAMESPACE = "awa-registration-owner-gate-v2"
KEY_ALGORITHM = "ssh-ed25519"
CONTRACT_RELATIVE_PATH = "contracts/awa-registration-owner-signers.v1"
CURRENT_RELATIVE_PATH = "awa/registration-owner-key/current.json"
ACCEPTANCE_RELATIVE_PATH = "awa/governance/native-entry-durable-registration-v5/acceptance-promotion.json"
ACCEPTED_PUBLIC_KEY_SHA256 = "3909ecbba5d835cbfdcf7f1498af2338dccd210e5fa780edf04799e869843565"
ACCEPTED_FINGERPRINT = "SHA256:zMkoOQbGEq7TiPI79e8m8WoKeAkmpEfb6MfnGpS032M"
ACCEPTED_CONTRACT_SHA256 = "9155be780c73e65a549ae97326dc56c53045aeaddb697745a95ce191aa472b7e"
ACCEPTED_KEY_ENROLLMENT_DIGEST = "0747f869d74ce03debdd91992050a59e2b0a587fa103c9f4ef251220efbf24c9"
ACCEPTED_OWNER_AUTHORIZATION_DIGEST = "dd24db871dc0fd7806371ac7113007e3c9c267f181273a2b290b5968588ee4fe"
CONTRACT_MODE = 0o644
CURRENT_MODE = 0o600
PRIVATE_DIR_MODE = 0o700
MAX_PUBLIC_BYTES = 512
MAX_JSON_BYTES = 131072
HEX64 = re.compile(r"^[0-9a-f]{64}$")
DECIMAL = re.compile(r"^(0|[1-9][0-9]*)$")
PUBLIC_LINE = re.compile(rb"ssh-ed25519 ([A-Za-z0-9+/]+={0,2})\n")
DENIED_IMPLICATIONS = (
    "ACCESS_PRIVATE_KEY_OR_SIGN",
    "COMMIT_PUSH_OR_OPEN_PR",
    "DELIVER_IMPLEMENTATION",
    "RUN_R0_R1_C1_OR_R2",
    "INSTALL_RELEASE_ACTIVATE_OR_ROLL_OUT",
)
RECOVERY_ACTIONS = (
    "PUBLISH_INITIAL",
    "RECOVER_FORWARD",
    "RECOVER_ROLLBACK_CONTRACT_ONLY",
)


class BootstrapError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise BootstrapError(message)


def close_owned_descriptors(
    *descriptors: int | None,
    primary: BaseException | None = None,
) -> BaseException | None:
    if primary is None and sys.exc_info()[1] is not None:
        primary = sys.exc_info()[1]
    cleanup: BaseException | None = None
    for descriptor in descriptors:
        if descriptor is None:
            continue
        try:
            os.close(descriptor)
        except BaseException as error:
            if cleanup is None:
                cleanup = error
    if primary is not None:
        if cleanup is not None:
            primary.__context__ = cleanup
            primary.add_note(
                "secondary descriptor cleanup failure: " + repr(cleanup)
            )
        return cleanup
    if cleanup is not None:
        raise cleanup
    return None


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def jcs(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def domain_hash(domain: str, value: object) -> str:
    return sha256(domain.encode("ascii") + b"\0" + jcs(value))


def strict_json(raw: bytes, *, limit: int = MAX_JSON_BYTES) -> object:
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= limit:
        fail("JSON bytes are absent or unbounded")
    if not raw.endswith(b"\n") or raw.endswith(b"\n\n") or b"\r" in raw or b"\0" in raw:
        fail("JSON framing is not canonical LF")

    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                fail("duplicate JSON key")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw[:-1].decode("utf-8", "strict"),
            object_pairs_hook=pairs,
            parse_constant=lambda token: fail("non-finite JSON token: " + token),
        )
    except (UnicodeError, json.JSONDecodeError, TypeError) as exc:
        raise BootstrapError("strict JSON parse failed") from exc
    if jcs(value) + b"\n" != raw:
        fail("JSON is not canonical JCS plus LF")
    return value


def exact_keys(value: object, keys: set[str], label: str) -> dict[str, object]:
    if type(value) is not dict or set(value) != keys:
        fail(label + " fields are not exact")
    return value


def require_hash(value: object, label: str) -> str:
    if type(value) is not str or HEX64.fullmatch(value) is None:
        fail(label + " must be lowercase 64-hex")
    return value


def require_decimal(value: object, label: str) -> str:
    if type(value) is not str or DECIMAL.fullmatch(value) is None:
        fail(label + " must be canonical unsigned decimal")
    return value


def normalized_absolute(value: str, label: str) -> pathlib.Path:
    if type(value) is not str or not value:
        fail(label + " path is absent")
    path = pathlib.Path(value)
    if not path.is_absolute() or os.path.normpath(value) != value:
        fail(label + " path is not normalized absolute")
    return path


def path_hash(domain: str, path: pathlib.Path) -> str:
    return sha256(domain.encode("ascii") + b"\0" + os.fsencode(str(path)))


def p_regular_metadata_tuple(
    metadata: os.stat_result,
) -> tuple[int, int, int, int, int, int, int, bool]:
    return (
        metadata.st_dev, metadata.st_ino, metadata.st_size,
        metadata.st_mtime_ns, metadata.st_uid,
        stat.S_IMODE(metadata.st_mode), metadata.st_nlink,
        stat.S_ISREG(metadata.st_mode),
    )


def p_visible_regular(path: pathlib.Path) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise BootstrapError("visible input binding is unavailable") from exc
    if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        fail("visible input binding is not regular")
    return metadata


def read_bounded_descriptor(path: pathlib.Path, limit: int, modes: set[int]) -> tuple[bytes, dict[str, str]]:
    before = p_visible_regular(path)
    mode = stat.S_IMODE(before.st_mode)
    if (
        before.st_uid != os.geteuid()
        or before.st_nlink != 1
        or mode not in modes
        or before.st_size < 1
        or before.st_size > limit
    ):
        fail("input metadata is unsafe")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        if p_regular_metadata_tuple(opened) != p_regular_metadata_tuple(before):
            fail("input changed while opening")
        raw = b""
        while len(raw) <= limit:
            chunk = os.read(descriptor, min(65536, limit + 1 - len(raw)))
            if not chunk:
                break
            raw += chunk
        after = os.fstat(descriptor)
        visible_after = p_visible_regular(path)
        if (
            p_regular_metadata_tuple(after)
            != p_regular_metadata_tuple(opened)
            or p_regular_metadata_tuple(visible_after)
            != p_regular_metadata_tuple(opened)
        ):
            fail("input changed while reading or rebinding")
    finally:
        close_owned_descriptors(descriptor)
    if len(raw) > limit:
        fail("input exceeds bound")
    record = {
        "path_hash": path_hash("awa-registration-owner-public-input-path/v1", path),
        "st_dev": str(before.st_dev),
        "st_ino": str(before.st_ino),
        "st_mode": str(mode),
        "st_uid": str(before.st_uid),
        "st_nlink": str(before.st_nlink),
        "st_size": str(before.st_size),
        "content_sha256": sha256(raw),
    }
    return raw, record

def parse_ssh_wire(blob: bytes) -> bytes:
    offset = 0

    def take() -> bytes:
        nonlocal offset
        if offset + 4 > len(blob):
            fail("OpenSSH wire length is truncated")
        size = struct.unpack(">I", blob[offset : offset + 4])[0]
        offset += 4
        if offset + size > len(blob):
            fail("OpenSSH wire value is truncated")
        value = blob[offset : offset + size]
        offset += size
        return value

    algorithm = take()
    key = take()
    if algorithm != b"ssh-ed25519" or len(key) != 32 or offset != len(blob):
        fail("OpenSSH wire algorithm, key length, or framing is invalid")
    return key


def p_parse_public(raw: bytes, expected: dict[str, str]) -> dict[str, object]:
    match = PUBLIC_LINE.fullmatch(raw)
    if match is None:
        fail("public input grammar is not exact")
    encoded = match.group(1)
    try:
        blob = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise BootstrapError("public input base64 is invalid") from exc
    parse_ssh_wire(blob)
    if base64.b64encode(blob) != encoded:
        fail("public input base64 is not canonical")
    fingerprint = "SHA256:" + base64.b64encode(hashlib.sha256(blob).digest()).decode("ascii").rstrip("=")
    contract = (PRINCIPAL + ' namespaces="' + NAMESPACE + '" ').encode("ascii") + raw
    observed = {
        "public_key_sha256": sha256(raw),
        "openssh_fingerprint": fingerprint,
        "allowed_signers_contract_hash": sha256(contract),
    }
    if observed != expected:
        fail("public identity does not equal authorized identity")
    return {"canonical_public": raw, "wire_blob": blob, "contract": contract, **observed}


def v_parse_public(raw: bytes, expected: dict[str, str]) -> dict[str, object]:
    if raw.count(b"\n") != 1 or not raw.endswith(b"\n") or b"\r" in raw or b"\t" in raw:
        fail("validator rejected public framing")
    pieces = raw[:-1].split(b" ")
    if len(pieces) != 2 or pieces[0] != b"ssh-ed25519" or not pieces[1]:
        fail("validator rejected public grammar")
    try:
        decoded = base64.b64decode(pieces[1], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise BootstrapError("validator rejected public base64") from exc
    if base64.b64encode(decoded) != pieces[1]:
        fail("validator rejected alternate public encoding")
    cursor = memoryview(decoded)
    if len(cursor) < 4:
        fail("validator rejected short public wire")
    first_size = struct.unpack(">I", cursor[:4])[0]
    if first_size != 11 or len(cursor) < 4 + first_size + 4:
        fail("validator rejected public algorithm framing")
    algorithm = bytes(cursor[4 : 4 + first_size])
    position = 4 + first_size
    second_size = struct.unpack(">I", cursor[position : position + 4])[0]
    position += 4
    key = bytes(cursor[position : position + second_size])
    position += second_size
    if algorithm != b"ssh-ed25519" or second_size != 32 or len(key) != 32 or position != len(cursor):
        fail("validator rejected public key framing")
    fingerprint = "SHA256:" + base64.b64encode(hashlib.sha256(decoded).digest()).decode("ascii").rstrip("=")
    contract = b'KleinPerkins namespaces="awa-registration-owner-gate-v2" ssh-ed25519 ' + pieces[1] + b"\n"
    observed = {
        "public_key_sha256": hashlib.sha256(raw).hexdigest(),
        "openssh_fingerprint": fingerprint,
        "allowed_signers_contract_hash": hashlib.sha256(contract).hexdigest(),
    }
    if observed != expected:
        fail("validator public identity mismatch")
    return {"canonical_public": raw, "wire_blob": decoded, "contract": contract, **observed}


def enrollment_object(public: dict[str, object]) -> dict[str, object]:
    relative_hash = sha256(b"awa-registration-owner-signers-path/v1\0" + CONTRACT_RELATIVE_PATH.encode("utf-8"))
    return {
        "schema": "awa-registration-owner-key-enrollment/v1",
        "principal": PRINCIPAL,
        "namespace": NAMESPACE,
        "key_algorithm": KEY_ALGORITHM,
        "public_key_sha256": public["public_key_sha256"],
        "openssh_fingerprint": public["openssh_fingerprint"],
        "allowed_signers_relative_path": CONTRACT_RELATIVE_PATH,
        "allowed_signers_path_hash": relative_hash,
        "allowed_signers_contract_hash": public["allowed_signers_contract_hash"],
        "authorized": True,
    }


def build_current_receipt(public: dict[str, object], created_wall_ns: str) -> tuple[dict[str, object], bytes, str]:
    require_decimal(created_wall_ns, "created_wall_ns")
    enrollment = enrollment_object(public)
    enrollment_digest = domain_hash("awa-registration-owner-key-enrollment/v1", enrollment)
    if enrollment_digest != ACCEPTED_KEY_ENROLLMENT_DIGEST:
        fail("key enrollment digest differs from accepted Gate 2A")
    core = {
        "schema": "awa-registration-owner-key-current/v1",
        "sequence": "1",
        "status": "ACTIVE",
        "principal": PRINCIPAL,
        "namespace": NAMESPACE,
        "key_algorithm": KEY_ALGORITHM,
        "public_key_sha256": public["public_key_sha256"],
        "openssh_fingerprint": public["openssh_fingerprint"],
        "allowed_signers_relative_path": CONTRACT_RELATIVE_PATH,
        "allowed_signers_path_hash": enrollment["allowed_signers_path_hash"],
        "allowed_signers_contract_hash": public["allowed_signers_contract_hash"],
        "key_enrollment_digest": enrollment_digest,
        "owner_authorization_digest": ACCEPTED_OWNER_AUTHORIZATION_DIGEST,
        "previous_enrollment_hash": None,
        "created_wall_ns": created_wall_ns,
    }
    enrollment_hash = domain_hash("awa-registration-owner-key-current/v1", core)
    receipt = {**core, "enrollment_hash": enrollment_hash}
    raw = jcs(receipt) + b"\n"
    return receipt, raw, enrollment_hash


def extract_plan_artifacts(plan_raw: bytes) -> dict[str, str]:
    markers = {
        "launcher_sha256": (
            b"<!-- awa-v5-" + b"canonical-launcher:v1:begin -->\n```python\n",
            b"```\n<!-- awa-v5-" + b"canonical-launcher:v1:end -->",
        ),
        "checker_sha256": (
            b"<!-- awa-v5-" + b"acceptance-checker:v1:begin -->\n```python\n",
            b"```\n<!-- awa-v5-" + b"acceptance-checker:v1:end -->",
        ),
        "bootstrap_sha256": (
            b"<!-- awa-v5-" + b"enrollment-bootstrap-tool:v1:begin -->\n```python\n",
            b"```\n<!-- awa-v5-" + b"enrollment-bootstrap-tool:v1:end -->",
        ),
        "harness_sha256": (
            b"<!-- awa-v5-" + b"bootstrap-fault-harness:v1:begin -->\n```python\n",
            b"```\n<!-- awa-v5-" + b"bootstrap-fault-harness:v1:end -->",
        ),
    }
    result: dict[str, str] = {}
    for key, (begin, end) in markers.items():
        if plan_raw.count(begin) != 1 or plan_raw.count(end) != 1:
            fail("accepted v5 artifact markers are not exact")
        payload = plan_raw.split(begin, 1)[1].split(end, 1)[0]
        payload.decode("utf-8", "strict")
        if b"\r" in payload or b"\0" in payload or not payload.endswith(b"\n"):
            fail("accepted v5 artifact framing is invalid")
        result[key] = sha256(payload)
    return result


def acceptance_receipt(path: pathlib.Path, plan_path: pathlib.Path, launch_tool_hash: str) -> tuple[dict[str, object], bytes]:
    raw, _record = read_bounded_descriptor(path, MAX_JSON_BYTES, {CURRENT_MODE})
    receipt = exact_keys(strict_json(raw), {
        "algorithm", "bootstrap_sha256", "checker_sha256",
        "completed_wall_ns", "domain", "harness_sha256",
        "immutable_anchors", "launcher_sha256", "normalized_digest",
        "owner_acceptance_digest", "receipt_hash", "recovery_vector",
        "recovery_vector_digest", "repository", "schema", "sentinel",
        "source_commit",
    }, "v5 acceptance receipt")
    recovery = exact_keys(receipt["recovery_vector"], {
        "bootstrap_sha256", "checker_sha256", "harness_sha256",
        "immutable_anchors", "launcher_sha256", "normalized_digest",
        "ordered_surfaces", "repository", "schema", "source_commit",
    }, "v5 acceptance recovery vector")
    if (
        receipt["schema"] != "awa-registration-v5-acceptance-promotion/v2"
        or receipt["repository"] != "KleinPerkins/awa"
        or receipt["source_commit"] != BASE_COMMIT
        or receipt["algorithm"] != "awa-registration-v5-acceptance-body/v1"
        or receipt["domain"] != "awa-registration-v5-acceptance-body/v1"
        or receipt["sentinel"] != "__AWA_V5_ACCEPTED_STATUS_TOKEN_V1__"
        or recovery["schema"] != "awa-registration-v5-recovery-vector/v1"
        or recovery["repository"] != "KleinPerkins/awa"
        or recovery["source_commit"] != BASE_COMMIT
    ):
        fail("v5 acceptance receipt authority mismatch")
    for field in (
        "bootstrap_sha256", "checker_sha256", "harness_sha256",
        "launcher_sha256", "normalized_digest", "owner_acceptance_digest",
        "receipt_hash", "recovery_vector_digest",
    ):
        require_hash(receipt[field], field)
    require_decimal(receipt["completed_wall_ns"], "completed_wall_ns")
    without_hash = {key: receipt[key] for key in receipt if key != "receipt_hash"}
    if domain_hash("awa-registration-v5-acceptance-promotion/v2", without_hash) != receipt["receipt_hash"]:
        fail("v5 acceptance receipt hash mismatch")
    if domain_hash("awa-registration-v5-recovery-vector/v1", recovery) != receipt["recovery_vector_digest"]:
        fail("v5 acceptance recovery digest mismatch")
    for field in ("bootstrap_sha256", "checker_sha256", "harness_sha256", "launcher_sha256", "normalized_digest", "immutable_anchors"):
        if receipt[field] != recovery[field]:
            fail("v5 acceptance receipt/recovery cross-binding mismatch")
    anchors = recovery["immutable_anchors"]
    expected_anchors = [
        {"kind": "FULL_FILE", "path": "docs/plans/native-entry-durable-registration-v4.md", "sha256": V4_SHA256},
        {"kind": "FULL_FILE", "path": "docs/adr/0026-durable-registration-authority-hardening.md", "sha256": ADR_0026_SHA256},
        {"kind": "EXACT_ROW", "path": "docs/adr/README.md", "sha256": "c2ffbac9b939d1217eedc55824c48353a32ab00f7a15b95e151fd785ff873123"},
        {"kind": "V4_EXACT_ROW", "path": "docs/plans/README.md", "sha256": "6c920e7e177a37a1092d0d4096a2966bea10a29844ae3f7dbfe07acb6902a3c0"},
    ]
    if anchors != expected_anchors:
        fail("v5 acceptance immutable anchors mismatch")
    rows = recovery["ordered_surfaces"]
    if type(rows) is not list or len(rows) != 2:
        fail("v5 acceptance surface count mismatch")
    plan_rows = [row for row in rows if type(row) is dict and row.get("path") == "docs/plans/native-entry-durable-registration-v5.md"]
    if len(plan_rows) != 1:
        fail("v5 acceptance plan surface missing")
    plan_raw, _plan_record = read_bounded_descriptor(plan_path, 1024 * 1024, {0o644})
    artifacts = extract_plan_artifacts(plan_raw)
    if artifacts != {key: recovery[key] for key in artifacts}:
        fail("accepted v5 artifact bytes are stale")
    if sha256(plan_raw) != plan_rows[0].get("post_backing_file_sha256"):
        fail("accepted v5 plan bytes are not exact POST")
    expected_plan = globals().get("__v5_full_plan_sha256_expected__")
    expected_checker = globals().get("__v5_checker_sha256_expected__")
    expected_bootstrap = globals().get("__v5_bootstrap_sha256_expected__")
    if (
        expected_plan != sha256(plan_raw)
        or expected_checker != artifacts["checker_sha256"]
        or expected_bootstrap != artifacts["bootstrap_sha256"]
        or launch_tool_hash != artifacts["bootstrap_sha256"]
        or artifacts["launcher_sha256"] != BOOTSTRAP_LAUNCHER_SHA256
    ):
        fail("launcher-independent acceptance expectations mismatch")
    return receipt, raw


def dir_record(path: pathlib.Path, domain: str) -> dict[str, str]:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.geteuid():
        fail("directory authority is unsafe")
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        opened = os.fstat(descriptor)
        if (
            (opened.st_dev, opened.st_ino)
            != (metadata.st_dev, metadata.st_ino)
            or not stat.S_ISDIR(opened.st_mode)
            or opened.st_uid != os.geteuid()
        ):
            fail("directory authority inode changed")
    finally:
        close_owned_descriptors(descriptor)
    return {
        "path_hash": path_hash(domain, path),
        "st_dev": str(metadata.st_dev),
        "st_ino": str(metadata.st_ino),
        "st_mode": str(stat.S_IMODE(metadata.st_mode)),
        "st_uid": str(metadata.st_uid),
    }


def build_packet(
    *,
    repo_root: pathlib.Path,
    state_home: pathlib.Path,
    plan_path: pathlib.Path,
    receipt_path: pathlib.Path,
    public_path: pathlib.Path,
    created_wall_ns: str,
    launch_tool_hash: str,
) -> dict[str, object]:
    if plan_path != repo_root / "docs/plans/native-entry-durable-registration-v5.md":
        fail("accepted v5 plan path is not repository-bound")
    if receipt_path != state_home / ACCEPTANCE_RELATIVE_PATH:
        fail("accepted v5 receipt path is not state-root-bound")
    receipt, receipt_raw = acceptance_receipt(receipt_path, plan_path, launch_tool_hash)
    public_raw, public_record = read_bounded_descriptor(public_path, MAX_PUBLIC_BYTES, {0o600, 0o644})
    public = p_parse_public(public_raw, {
        "public_key_sha256": ACCEPTED_PUBLIC_KEY_SHA256,
        "openssh_fingerprint": ACCEPTED_FINGERPRINT,
        "allowed_signers_contract_hash": ACCEPTED_CONTRACT_SHA256,
    })
    current, current_raw, enrollment_hash = build_current_receipt(public, created_wall_ns)
    contract_path = repo_root / CONTRACT_RELATIVE_PATH
    current_path = state_home / CURRENT_RELATIVE_PATH
    packet = {
        "schema": "awa-registration-owner-key-bootstrap-packet/v1",
        "repository": "KleinPerkins/awa",
        "source_commit": BASE_COMMIT,
        "accepted_v5_normalized_digest": receipt["normalized_digest"],
        "accepted_v5_receipt_hash": sha256(receipt_raw),
        "tool_sha256": launch_tool_hash,
        "public_input_record": public_record,
        "canonical_public_b64": base64.b64encode(public_raw).decode("ascii"),
        "principal": PRINCIPAL,
        "namespace": NAMESPACE,
        "key_algorithm": KEY_ALGORITHM,
        "public_key_sha256": public["public_key_sha256"],
        "openssh_fingerprint": public["openssh_fingerprint"],
        "allowed_signers_relative_path": CONTRACT_RELATIVE_PATH,
        "allowed_signers_path_hash": enrollment_object(public)["allowed_signers_path_hash"],
        "allowed_signers_contract_hash": public["allowed_signers_contract_hash"],
        "key_enrollment_digest": ACCEPTED_KEY_ENROLLMENT_DIGEST,
        "owner_authorization_digest": ACCEPTED_OWNER_AUTHORIZATION_DIGEST,
        "created_wall_ns": created_wall_ns,
        "sequence": "1",
        "status": "ACTIVE",
        "previous_enrollment_hash": None,
        "contract_output": {
            "absolute_path": str(contract_path),
            "path_hash": path_hash("awa-registration-owner-contract-output-path/v1", contract_path),
            "mode": str(CONTRACT_MODE),
            "payload_sha256": sha256(public["contract"]),
            "payload_b64": base64.b64encode(public["contract"]).decode("ascii"),
        },
        "current_output": {
            "absolute_path": str(current_path),
            "path_hash": path_hash("awa-registration-owner-current-output-path/v1", current_path),
            "mode": str(CURRENT_MODE),
            "parent_mode": str(PRIVATE_DIR_MODE),
            "payload_sha256": sha256(current_raw),
            "payload_b64": base64.b64encode(current_raw).decode("ascii"),
        },
        "enrollment_hash": enrollment_hash,
        "repo_root_record": dir_record(repo_root, "awa-registration-owner-repo-root/v1"),
        "state_home_path": str(state_home),
        "authorized_recovery_actions": list(RECOVERY_ACTIONS),
        "denied_implications": list(DENIED_IMPLICATIONS),
    }
    if current["owner_authorization_digest"] != ACCEPTED_OWNER_AUTHORIZATION_DIGEST:
        fail("accepted Gate 2A owner authorization changed")
    return {"packet": packet, "packet_sha256": domain_hash("awa-registration-owner-key-bootstrap-packet/v1", packet)}


PACKET_FIELDS = {
    "schema", "repository", "source_commit", "accepted_v5_normalized_digest",
    "accepted_v5_receipt_hash", "tool_sha256", "public_input_record",
    "canonical_public_b64", "principal", "namespace", "key_algorithm",
    "public_key_sha256", "openssh_fingerprint", "allowed_signers_relative_path",
    "allowed_signers_path_hash", "allowed_signers_contract_hash",
    "key_enrollment_digest", "owner_authorization_digest", "created_wall_ns",
    "sequence", "status", "previous_enrollment_hash", "contract_output",
    "current_output", "enrollment_hash", "repo_root_record", "state_home_path",
    "authorized_recovery_actions", "denied_implications",
}


def load_packet(path: pathlib.Path) -> tuple[dict[str, object], str, bytes]:
    raw, _record = read_bounded_descriptor(path, MAX_JSON_BYTES, {CURRENT_MODE, 0o644})
    document = exact_keys(strict_json(raw), {"packet", "packet_sha256"}, "packet document")
    packet = exact_keys(document["packet"], PACKET_FIELDS, "bootstrap packet")
    digest = require_hash(document["packet_sha256"], "packet_sha256")
    if domain_hash("awa-registration-owner-key-bootstrap-packet/v1", packet) != digest:
        fail("bootstrap packet hash mismatch")
    if "gate3b_decision_digest" in packet or "packet_sha256" in packet:
        fail("bootstrap packet is circular")
    return packet, digest, raw


def bootstrap_context(packet: dict[str, object], packet_hash: str) -> dict[str, object]:
    contract = exact_keys(packet["contract_output"], {"absolute_path", "path_hash", "mode", "payload_sha256", "payload_b64"}, "contract output")
    current = exact_keys(packet["current_output"], {"absolute_path", "path_hash", "mode", "parent_mode", "payload_sha256", "payload_b64"}, "current output")
    return {
        "schema": "awa-registration-owner-key-bootstrap-context/v1",
        "repository": "KleinPerkins/awa",
        "accepted_v5_normalized_digest": packet["accepted_v5_normalized_digest"],
        "accepted_v5_receipt_hash": packet["accepted_v5_receipt_hash"],
        "tool_sha256": packet["tool_sha256"],
        "packet_sha256": packet_hash,
        "public_key_sha256": packet["public_key_sha256"],
        "openssh_fingerprint": packet["openssh_fingerprint"],
        "allowed_signers_contract_hash": packet["allowed_signers_contract_hash"],
        "current_receipt_sha256": current["payload_sha256"],
        "enrollment_hash": packet["enrollment_hash"],
        "contract_absolute_path": contract["absolute_path"],
        "contract_mode": contract["mode"],
        "current_absolute_path": current["absolute_path"],
        "current_mode": current["mode"],
        "authorized_recovery_actions": packet["authorized_recovery_actions"],
        "denied_implications": packet["denied_implications"],
    }


def load_authority(path: pathlib.Path, packet: dict[str, object], packet_hash: str) -> tuple[dict[str, object], str]:
    raw, _record = read_bounded_descriptor(path, MAX_JSON_BYTES, {CURRENT_MODE, 0o644})
    value = strict_json(raw)
    authority = exact_keys(value, {
        "schema", "repository", "authorized_by", "action", "bootstrap_context",
        "authorized", "denied_implications",
    }, "Gate 3B authority")
    if (
        authority["schema"] != "awa-registration-owner-key-bootstrap-publication-go/v1"
        or authority["repository"] != "KleinPerkins/awa"
        or authority["authorized_by"] != "KleinPerkins"
        or authority["action"] != "PUBLISH_INITIAL_OWNER_ENROLLMENT"
        or authority["authorized"] is not True
        or authority["bootstrap_context"] != bootstrap_context(packet, packet_hash)
        or authority["denied_implications"] != list(DENIED_IMPLICATIONS)
    ):
        fail("Gate 3B authority does not equal packet context")
    return authority, domain_hash("awa-registration-owner-key-bootstrap-publication-go/v1", authority)


def v_domain_hash(domain: str, value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(domain.encode("ascii") + b"\0" + encoded).hexdigest()


def v_strict_json(raw: bytes, label: str) -> object:
    if (
        not isinstance(raw, bytes)
        or not 1 <= len(raw) <= MAX_JSON_BYTES
        or not raw.endswith(b"\n")
        or raw.endswith(b"\n\n")
        or b"\r" in raw
        or b"\0" in raw
    ):
        fail("validator rejected " + label + " framing")

    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                fail("validator rejected duplicate " + label + " field")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw[:-1].decode("utf-8", "strict"),
            object_pairs_hook=pairs,
            parse_constant=lambda _token: fail(
                "validator rejected non-finite " + label
            ),
        )
    except (UnicodeError, json.JSONDecodeError, TypeError) as exc:
        raise BootstrapError(
            "validator strict " + label + " parse failed"
        ) from exc
    expected = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8") + b"\n"
    if expected != raw:
        fail("validator rejected noncanonical " + label)
    return value


def v_regular_metadata_tuple(
    metadata: os.stat_result,
) -> tuple[int, int, int, int, int, int, int, bool]:
    return (
        metadata.st_dev, metadata.st_ino, metadata.st_size,
        metadata.st_mtime_ns, metadata.st_uid,
        stat.S_IMODE(metadata.st_mode), metadata.st_nlink,
        stat.S_ISREG(metadata.st_mode),
    )


def v_visible_regular(path: pathlib.Path) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise BootstrapError("validator visible input unavailable") from exc
    if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        fail("validator visible input is not regular")
    return metadata


def v_read_descriptor(
    path: pathlib.Path, limit: int, modes: set[int]
) -> tuple[bytes, dict[str, str]]:
    before = v_visible_regular(path)
    file_mode = stat.S_IMODE(before.st_mode)
    if (
        before.st_uid != os.geteuid()
        or before.st_nlink != 1
        or file_mode not in modes
        or before.st_size < 1
        or before.st_size > limit
    ):
        fail("validator input metadata is unsafe")
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        opened = os.fstat(descriptor)
        if v_regular_metadata_tuple(opened) != v_regular_metadata_tuple(before):
            fail("validator input changed while opening")
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        visible_after = v_visible_regular(path)
        if (
            v_regular_metadata_tuple(after)
            != v_regular_metadata_tuple(opened)
            or v_regular_metadata_tuple(visible_after)
            != v_regular_metadata_tuple(opened)
        ):
            fail("validator input changed while reading or rebinding")
    finally:
        close_owned_descriptors(descriptor)
    raw = b"".join(chunks)
    if len(raw) > limit:
        fail("validator input exceeds bound")
    return raw, {
        "path_hash": hashlib.sha256(
            b"awa-registration-owner-public-input-path/v1\0"
            + os.fsencode(str(path))
        ).hexdigest(),
        "st_dev": str(before.st_dev),
        "st_ino": str(before.st_ino),
        "st_mode": str(file_mode),
        "st_uid": str(before.st_uid),
        "st_nlink": str(before.st_nlink),
        "st_size": str(before.st_size),
        "content_sha256": hashlib.sha256(raw).hexdigest(),
    }

def v_load_packet(
    path: pathlib.Path,
) -> tuple[dict[str, object], str, bytes]:
    raw, _record = v_read_descriptor(
        path, MAX_JSON_BYTES, {CURRENT_MODE, 0o644}
    )
    document = v_strict_json(raw, "packet document")
    if (
        type(document) is not dict
        or set(document) != {"packet", "packet_sha256"}
        or type(document["packet"]) is not dict
        or set(document["packet"]) != PACKET_FIELDS
    ):
        fail("validator packet fields are not exact")
    packet = document["packet"]
    digest = document["packet_sha256"]
    if type(digest) is not str or HEX64.fullmatch(digest) is None:
        fail("validator packet hash is malformed")
    if v_domain_hash(
        "awa-registration-owner-key-bootstrap-packet/v1", packet
    ) != digest:
        fail("validator packet hash mismatch")
    if "packet_sha256" in packet or "gate3b_decision_digest" in packet:
        fail("validator rejected circular packet")
    return packet, digest, raw


def v_extract_plan_artifacts(plan_raw: bytes) -> dict[str, str]:
    markers = {
        "launcher_sha256": (b"<!-- awa-v5-" + b"canonical-launcher:v1:begin -->\n```python\n", b"```\n<!-- awa-v5-" + b"canonical-launcher:v1:end -->"),
        "checker_sha256": (b"<!-- awa-v5-" + b"acceptance-checker:v1:begin -->\n```python\n", b"```\n<!-- awa-v5-" + b"acceptance-checker:v1:end -->"),
        "bootstrap_sha256": (b"<!-- awa-v5-" + b"enrollment-bootstrap-tool:v1:begin -->\n```python\n", b"```\n<!-- awa-v5-" + b"enrollment-bootstrap-tool:v1:end -->"),
        "harness_sha256": (b"<!-- awa-v5-" + b"bootstrap-fault-harness:v1:begin -->\n```python\n", b"```\n<!-- awa-v5-" + b"bootstrap-fault-harness:v1:end -->"),
    }
    result: dict[str, str] = {}
    for key, (begin, end) in markers.items():
        if plan_raw.count(begin) != 1 or plan_raw.count(end) != 1:
            fail("validator artifact markers mismatch")
        payload = plan_raw.split(begin, 1)[1].split(end, 1)[0]
        payload.decode("utf-8", "strict")
        if b"\r" in payload or b"\0" in payload or not payload.endswith(b"\n"):
            fail("validator artifact framing mismatch")
        result[key] = hashlib.sha256(payload).hexdigest()
    return result


def v_load_acceptance(path: pathlib.Path, plan_path: pathlib.Path, launch_tool_hash: str) -> tuple[dict[str, object], bytes]:
    raw, _record = v_read_descriptor(path, MAX_JSON_BYTES, {CURRENT_MODE})
    receipt = v_strict_json(raw, "acceptance receipt")
    fields = {"algorithm", "bootstrap_sha256", "checker_sha256", "completed_wall_ns", "domain", "harness_sha256", "immutable_anchors", "launcher_sha256", "normalized_digest", "owner_acceptance_digest", "receipt_hash", "recovery_vector", "recovery_vector_digest", "repository", "schema", "sentinel", "source_commit"}
    if type(receipt) is not dict or set(receipt) != fields:
        fail("validator acceptance fields are not exact")
    recovery = receipt["recovery_vector"]
    recovery_fields = {"bootstrap_sha256", "checker_sha256", "harness_sha256", "immutable_anchors", "launcher_sha256", "normalized_digest", "ordered_surfaces", "repository", "schema", "source_commit"}
    if type(recovery) is not dict or set(recovery) != recovery_fields:
        fail("validator recovery fields are not exact")
    if receipt["schema"] != "awa-registration-v5-acceptance-promotion/v2" or receipt["repository"] != "KleinPerkins/awa" or receipt["source_commit"] != BASE_COMMIT or receipt["algorithm"] != "awa-registration-v5-acceptance-body/v1" or receipt["domain"] != "awa-registration-v5-acceptance-body/v1" or receipt["sentinel"] != "__AWA_V5_ACCEPTED_STATUS_TOKEN_V1__" or recovery["schema"] != "awa-registration-v5-recovery-vector/v1" or recovery["repository"] != "KleinPerkins/awa" or recovery["source_commit"] != BASE_COMMIT:
        fail("validator acceptance authority mismatch")
    for field in ("bootstrap_sha256", "checker_sha256", "harness_sha256", "launcher_sha256", "normalized_digest", "owner_acceptance_digest", "receipt_hash", "recovery_vector_digest"):
        value = receipt[field]
        if type(value) is not str or HEX64.fullmatch(value) is None:
            fail("validator acceptance hash malformed")
    completed = receipt["completed_wall_ns"]
    if type(completed) is not str or DECIMAL.fullmatch(completed) is None:
        fail("validator acceptance time malformed")
    without_hash = {key: receipt[key] for key in receipt if key != "receipt_hash"}
    if v_domain_hash("awa-registration-v5-acceptance-promotion/v2", without_hash) != receipt["receipt_hash"] or v_domain_hash("awa-registration-v5-recovery-vector/v1", recovery) != receipt["recovery_vector_digest"]:
        fail("validator acceptance digest mismatch")
    for field in ("bootstrap_sha256", "checker_sha256", "harness_sha256", "launcher_sha256", "normalized_digest", "immutable_anchors"):
        if receipt[field] != recovery[field]:
            fail("validator acceptance cross-binding mismatch")
    expected_anchors = [{"kind": "FULL_FILE", "path": "docs/plans/native-entry-durable-registration-v4.md", "sha256": V4_SHA256}, {"kind": "FULL_FILE", "path": "docs/adr/0026-durable-registration-authority-hardening.md", "sha256": ADR_0026_SHA256}, {"kind": "EXACT_ROW", "path": "docs/adr/README.md", "sha256": "c2ffbac9b939d1217eedc55824c48353a32ab00f7a15b95e151fd785ff873123"}, {"kind": "V4_EXACT_ROW", "path": "docs/plans/README.md", "sha256": "6c920e7e177a37a1092d0d4096a2966bea10a29844ae3f7dbfe07acb6902a3c0"}]
    if recovery["immutable_anchors"] != expected_anchors:
        fail("validator immutable anchors mismatch")
    rows = recovery["ordered_surfaces"]
    if type(rows) is not list or len(rows) != 2:
        fail("validator acceptance surface count mismatch")
    plan_rows = [row for row in rows if type(row) is dict and row.get("path") == "docs/plans/native-entry-durable-registration-v5.md"]
    if len(plan_rows) != 1:
        fail("validator plan surface missing")
    plan_raw, _plan_record = v_read_descriptor(plan_path, 1024 * 1024, {0o644})
    artifacts = v_extract_plan_artifacts(plan_raw)
    if artifacts != {key: recovery[key] for key in artifacts} or hashlib.sha256(plan_raw).hexdigest() != plan_rows[0].get("post_backing_file_sha256"):
        fail("validator accepted plan/artifacts stale")
    if globals().get("__v5_full_plan_sha256_expected__") != hashlib.sha256(plan_raw).hexdigest() or globals().get("__v5_checker_sha256_expected__") != artifacts["checker_sha256"] or globals().get("__v5_bootstrap_sha256_expected__") != artifacts["bootstrap_sha256"] or launch_tool_hash != artifacts["bootstrap_sha256"] or artifacts["launcher_sha256"] != BOOTSTRAP_LAUNCHER_SHA256:
        fail("validator launcher expectations mismatch")
    return receipt, raw


def v_decode_payload(field: object, label: str) -> bytes:
    if type(field) is not str:
        fail("validator " + label + " payload is not text")
    try:
        raw = base64.b64decode(field.encode("ascii"), validate=True)
    except (UnicodeError, binascii.Error, ValueError) as exc:
        raise BootstrapError("validator " + label + " payload base64 failed") from exc
    if base64.b64encode(raw).decode("ascii") != field:
        fail("validator " + label + " payload is not canonical base64")
    return raw


def v_reconstruct(packet: dict[str, object], public_raw: bytes) -> tuple[bytes, bytes, str]:
    expected = {
        "public_key_sha256": ACCEPTED_PUBLIC_KEY_SHA256,
        "openssh_fingerprint": ACCEPTED_FINGERPRINT,
        "allowed_signers_contract_hash": ACCEPTED_CONTRACT_SHA256,
    }
    public = v_parse_public(public_raw, expected)
    enrollment = {
        "schema": "awa-registration-owner-key-enrollment/v1",
        "principal": "KleinPerkins",
        "namespace": "awa-registration-owner-gate-v2",
        "key_algorithm": "ssh-ed25519",
        "public_key_sha256": public["public_key_sha256"],
        "openssh_fingerprint": public["openssh_fingerprint"],
        "allowed_signers_relative_path": "contracts/awa-registration-owner-signers.v1",
        "allowed_signers_path_hash": hashlib.sha256(b"awa-registration-owner-signers-path/v1\0contracts/awa-registration-owner-signers.v1").hexdigest(),
        "allowed_signers_contract_hash": public["allowed_signers_contract_hash"],
        "authorized": True,
    }
    enrollment_digest = v_domain_hash("awa-registration-owner-key-enrollment/v1", enrollment)
    if enrollment_digest != ACCEPTED_KEY_ENROLLMENT_DIGEST or packet["key_enrollment_digest"] != enrollment_digest:
        fail("validator enrollment digest mismatch")
    created = packet["created_wall_ns"]
    if type(created) is not str or DECIMAL.fullmatch(created) is None:
        fail("validator created_wall_ns is malformed")
    core = {
        "schema": "awa-registration-owner-key-current/v1",
        "sequence": "1",
        "status": "ACTIVE",
        "principal": "KleinPerkins",
        "namespace": "awa-registration-owner-gate-v2",
        "key_algorithm": "ssh-ed25519",
        "public_key_sha256": public["public_key_sha256"],
        "openssh_fingerprint": public["openssh_fingerprint"],
        "allowed_signers_relative_path": "contracts/awa-registration-owner-signers.v1",
        "allowed_signers_path_hash": enrollment["allowed_signers_path_hash"],
        "allowed_signers_contract_hash": public["allowed_signers_contract_hash"],
        "key_enrollment_digest": enrollment_digest,
        "owner_authorization_digest": ACCEPTED_OWNER_AUTHORIZATION_DIGEST,
        "previous_enrollment_hash": None,
        "created_wall_ns": created,
    }
    enrollment_hash = v_domain_hash("awa-registration-owner-key-current/v1", core)
    current = {**core, "enrollment_hash": enrollment_hash}
    current_raw = json.dumps(current, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8") + b"\n"
    return public["contract"], current_raw, enrollment_hash


def v_read_exact(path: pathlib.Path, expected: bytes, mode: int) -> dict[str, str]:
    raw, record = v_read_descriptor(
        path, max(MAX_JSON_BYTES, len(expected)), {mode}
    )
    if raw != expected:
        fail("validator observed unexpected bytes")
    return record


def v_validate(
    *,
    packet_path: pathlib.Path,
    authority_path: pathlib.Path,
    acceptance_path: pathlib.Path,
    plan_path: pathlib.Path,
    public_path: pathlib.Path,
    launch_tool_hash: str,
) -> dict[str, object]:
    packet, packet_hash, packet_raw = v_load_packet(packet_path)
    if packet["tool_sha256"] != launch_tool_hash:
        fail("validator tool hash mismatch")
    if (
        plan_path.name != "native-entry-durable-registration-v5.md"
        or plan_path.parent.name != "plans"
        or plan_path.parent.parent.name != "docs"
    ):
        fail("validator plan path is not repository-bound")
    repo_root = plan_path.parent.parent.parent
    if plan_path != repo_root / "docs/plans/native-entry-durable-registration-v5.md":
        fail("validator plan path is not canonical")
    if type(packet["state_home_path"]) is not str:
        fail("validator state home path type mismatch")
    state_home = pathlib.Path(packet["state_home_path"])
    if (
        not state_home.is_absolute()
        or os.path.normpath(str(state_home)) != str(state_home)
        or acceptance_path != state_home / ACCEPTANCE_RELATIVE_PATH
    ):
        fail("validator acceptance receipt is not state-root-bound")
    root_before = repo_root.lstat()
    if (
        stat.S_ISLNK(root_before.st_mode)
        or not stat.S_ISDIR(root_before.st_mode)
        or root_before.st_uid != os.geteuid()
    ):
        fail("validator repository root metadata is unsafe")
    root_fd = os.open(
        repo_root,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        root_opened = os.fstat(root_fd)
        if (
            (root_opened.st_dev, root_opened.st_ino)
            != (root_before.st_dev, root_before.st_ino)
            or not stat.S_ISDIR(root_opened.st_mode)
            or root_opened.st_uid != os.geteuid()
        ):
            fail("validator repository root inode changed")
    finally:
        close_owned_descriptors(root_fd)
    expected_root_record = {
        "path_hash": hashlib.sha256(
            b"awa-registration-owner-repo-root/v1\0"
            + os.fsencode(str(repo_root))
        ).hexdigest(),
        "st_dev": str(root_before.st_dev),
        "st_ino": str(root_before.st_ino),
        "st_mode": str(stat.S_IMODE(root_before.st_mode)),
        "st_uid": str(root_before.st_uid),
    }
    if packet["repo_root_record"] != expected_root_record:
        fail("validator repository root record mismatch")
    accepted, accepted_raw = v_load_acceptance(
        acceptance_path, plan_path, launch_tool_hash
    )
    if packet["accepted_v5_normalized_digest"] != accepted["normalized_digest"] or packet["accepted_v5_receipt_hash"] != hashlib.sha256(accepted_raw).hexdigest():
        fail("validator accepted-v5 binding mismatch")
    public_raw, public_record = v_read_descriptor(
        public_path, MAX_PUBLIC_BYTES, {0o600, 0o644}
    )
    if public_record != packet["public_input_record"]:
        fail("validator public descriptor mismatch")
    contract_raw, current_raw, enrollment_hash = v_reconstruct(packet, public_raw)
    if (
        packet["schema"]
        != "awa-registration-owner-key-bootstrap-packet/v1"
        or packet["repository"] != "KleinPerkins/awa"
        or packet["source_commit"] != BASE_COMMIT
        or packet["canonical_public_b64"]
        != base64.b64encode(public_raw).decode("ascii")
        or packet["principal"] != "KleinPerkins"
        or packet["namespace"] != "awa-registration-owner-gate-v2"
        or packet["key_algorithm"] != "ssh-ed25519"
        or packet["allowed_signers_relative_path"]
        != "contracts/awa-registration-owner-signers.v1"
        or packet["allowed_signers_path_hash"]
        != hashlib.sha256(
            b"awa-registration-owner-signers-path/v1\0"
            b"contracts/awa-registration-owner-signers.v1"
        ).hexdigest()
        or packet["sequence"] != "1"
        or packet["status"] != "ACTIVE"
        or packet["previous_enrollment_hash"] is not None
        or packet["authorized_recovery_actions"] != list(RECOVERY_ACTIONS)
        or packet["denied_implications"] != list(DENIED_IMPLICATIONS)
    ):
        fail("validator packet semantics mismatch")
    contract_output = exact_keys(packet["contract_output"], {"absolute_path", "path_hash", "mode", "payload_sha256", "payload_b64"}, "validator contract output")
    current_output = exact_keys(packet["current_output"], {"absolute_path", "path_hash", "mode", "parent_mode", "payload_sha256", "payload_b64"}, "validator current output")
    if (
        type(contract_output["absolute_path"]) is not str
        or type(current_output["absolute_path"]) is not str
        or type(packet["state_home_path"]) is not str
    ):
        fail("validator output path type mismatch")
    contract_path = pathlib.Path(contract_output["absolute_path"])
    current_path = pathlib.Path(current_output["absolute_path"])
    if (
        not contract_path.is_absolute()
        or os.path.normpath(str(contract_path)) != str(contract_path)
        or not current_path.is_absolute()
        or os.path.normpath(str(current_path)) != str(current_path)
        or not state_home.is_absolute()
        or os.path.normpath(str(state_home)) != str(state_home)
        or current_path != state_home / CURRENT_RELATIVE_PATH
        or contract_path != repo_root / CONTRACT_RELATIVE_PATH
        or contract_output["mode"] != str(CONTRACT_MODE)
        or current_output["mode"] != str(CURRENT_MODE)
        or current_output["parent_mode"] != str(PRIVATE_DIR_MODE)
        or contract_output["path_hash"]
        != hashlib.sha256(
            b"awa-registration-owner-contract-output-path/v1\0"
            + os.fsencode(str(contract_path))
        ).hexdigest()
        or current_output["path_hash"]
        != hashlib.sha256(
            b"awa-registration-owner-current-output-path/v1\0"
            + os.fsencode(str(current_path))
        ).hexdigest()
    ):
        fail("validator output path or mode binding mismatch")
    if (
        v_decode_payload(contract_output["payload_b64"], "contract") != contract_raw
        or contract_output["payload_sha256"] != hashlib.sha256(contract_raw).hexdigest()
        or v_decode_payload(current_output["payload_b64"], "current") != current_raw
        or current_output["payload_sha256"] != hashlib.sha256(current_raw).hexdigest()
        or packet["enrollment_hash"] != enrollment_hash
        or packet["public_key_sha256"] != ACCEPTED_PUBLIC_KEY_SHA256
        or packet["openssh_fingerprint"] != ACCEPTED_FINGERPRINT
        or packet["allowed_signers_contract_hash"] != ACCEPTED_CONTRACT_SHA256
        or packet["key_enrollment_digest"] != ACCEPTED_KEY_ENROLLMENT_DIGEST
        or packet["owner_authorization_digest"] != ACCEPTED_OWNER_AUTHORIZATION_DIGEST
    ):
        fail("validator packet reconstruction mismatch")
    authority_raw, _authority_record = v_read_descriptor(
        authority_path, MAX_JSON_BYTES, {CURRENT_MODE, 0o644}
    )
    authority = v_strict_json(authority_raw, "Gate 3B authority")
    if type(authority) is not dict or set(authority) != {
        "schema", "repository", "authorized_by", "action",
        "bootstrap_context", "authorized", "denied_implications",
    }:
        fail("validator Gate 3B authority fields are not exact")
    expected_context = {
        "schema": "awa-registration-owner-key-bootstrap-context/v1",
        "repository": "KleinPerkins/awa",
        "accepted_v5_normalized_digest": packet["accepted_v5_normalized_digest"],
        "accepted_v5_receipt_hash": packet["accepted_v5_receipt_hash"],
        "tool_sha256": packet["tool_sha256"],
        "packet_sha256": packet_hash,
        "public_key_sha256": packet["public_key_sha256"],
        "openssh_fingerprint": packet["openssh_fingerprint"],
        "allowed_signers_contract_hash": packet["allowed_signers_contract_hash"],
        "current_receipt_sha256": current_output["payload_sha256"],
        "enrollment_hash": packet["enrollment_hash"],
        "contract_absolute_path": contract_output["absolute_path"],
        "contract_mode": contract_output["mode"],
        "current_absolute_path": current_output["absolute_path"],
        "current_mode": current_output["mode"],
        "authorized_recovery_actions": packet["authorized_recovery_actions"],
        "denied_implications": packet["denied_implications"],
    }
    if (
        authority.get("schema") != "awa-registration-owner-key-bootstrap-publication-go/v1"
        or authority.get("repository") != "KleinPerkins/awa"
        or authority.get("authorized_by") != "KleinPerkins"
        or authority.get("action") != "PUBLISH_INITIAL_OWNER_ENROLLMENT"
        or authority.get("bootstrap_context") != expected_context
        or authority.get("authorized") is not True
        or authority.get("denied_implications") != list(DENIED_IMPLICATIONS)
    ):
        fail("validator Gate 3B decision mismatch")
    v_read_exact(contract_path, contract_raw, CONTRACT_MODE)
    v_read_exact(current_path, current_raw, CURRENT_MODE)
    return {
        "schema": "awa-registration-owner-key-bootstrap-validation/v1",
        "valid": True,
        "packet_sha256": packet_hash,
        "packet_file_sha256": hashlib.sha256(packet_raw).hexdigest(),
        "gate3b_decision_digest": v_domain_hash("awa-registration-owner-key-bootstrap-publication-go/v1", authority),
        "contract_sha256": hashlib.sha256(contract_raw).hexdigest(),
        "current_receipt_sha256": hashlib.sha256(current_raw).hexdigest(),
        "enrollment_hash": enrollment_hash,
    }


def p_read_state(path: pathlib.Path, expected: bytes, mode: int) -> tuple[str, tuple[int, int] | None]:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return "ABSENT", None
    except OSError as exc:
        raise BootstrapError("state metadata unavailable") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != mode
    ):
        fail("state entry metadata is unsafe")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        if p_regular_metadata_tuple(opened) != p_regular_metadata_tuple(metadata):
            fail("state inode or post-open metadata substituted")
        raw = b""
        while len(raw) <= max(MAX_JSON_BYTES, len(expected)):
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            raw += chunk
        after = os.fstat(descriptor)
        visible_after = p_visible_regular(path)
        if (
            p_regular_metadata_tuple(after)
            != p_regular_metadata_tuple(opened)
            or p_regular_metadata_tuple(visible_after)
            != p_regular_metadata_tuple(opened)
        ):
            fail("state entry changed while reading or rebinding")
    finally:
        close_owned_descriptors(descriptor)
    if raw != expected:
        fail("state entry bytes mismatch")
    return "EXACT", (metadata.st_dev, metadata.st_ino)

def p_primary_state(contract_path: pathlib.Path, receipt_path: pathlib.Path, contract_raw: bytes, receipt_raw: bytes) -> str:
    contract_state, _ = p_read_state(contract_path, contract_raw, CONTRACT_MODE)
    receipt_state, _ = p_read_state(receipt_path, receipt_raw, CURRENT_MODE)
    pair = (contract_state, receipt_state)
    if pair == ("ABSENT", "ABSENT"):
        return "ABSENT_CONTRACT/ABSENT_RECEIPT"
    if pair == ("EXACT", "ABSENT"):
        return "EXACT_CONTRACT/ABSENT_RECEIPT"
    if pair == ("EXACT", "EXACT"):
        return "EXACT_CONTRACT/EXACT_RECEIPT"
    fail("cross-root state is not a known state")


def p_check_parent(path: pathlib.Path, *, private: bool) -> int:
    metadata = path.lstat()
    mode = stat.S_IMODE(metadata.st_mode)
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.geteuid():
        fail("publication parent is unsafe")
    if private and mode != PRIVATE_DIR_MODE:
        fail("private publication parent mode is unsafe")
    if not private and mode & 0o022:
        fail("repository publication parent is writable by another identity")
    descriptor: int | None = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        opened = os.fstat(descriptor)
        if (
            (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino)
            or not stat.S_ISDIR(opened.st_mode)
            or opened.st_uid != os.geteuid()
            or stat.S_IMODE(opened.st_mode) != mode
        ):
            fail("publication parent inode or post-open metadata changed")
        return descriptor
    except BaseException as error:
        close_owned_descriptors(descriptor, primary=error)
        raise



def p_ensure_private_child(parent: pathlib.Path, name: str) -> pathlib.Path:
    descriptor = p_check_parent(parent, private=True)
    try:
        try:
            os.mkdir(name, PRIVATE_DIR_MODE, dir_fd=descriptor)
            os.fsync(descriptor)
        except FileExistsError:
            pass
        metadata = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) != PRIVATE_DIR_MODE:
            fail("private child directory is unsafe")
    finally:
        close_owned_descriptors(descriptor)
    return parent / name


def p_residue_name(path: pathlib.Path, packet_hash: str) -> str:
    return "." + path.name + ".bootstrap-" + packet_hash[:32]


def p_scan_residues(path: pathlib.Path, packet_hash: str, *, private_parent: bool) -> pathlib.Path | None:
    parent = path.parent
    try:
        parent.lstat()
    except FileNotFoundError:
        return None
    expected = p_residue_name(path, packet_hash)
    prefix = "." + path.name + ".bootstrap-"
    parent_fd = p_check_parent(parent, private=private_parent)
    try:
        matches = [
            entry.name
            for entry in os.scandir(parent_fd)
            if entry.name.startswith(prefix)
        ]
    finally:
        close_owned_descriptors(parent_fd)
    if any(name != expected for name in matches) or len(matches) > 1:
        fail("unknown publication residue exists")
    return parent / expected if matches else None


def p_write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    offset = 0
    while offset < len(view):
        count = os.write(descriptor, view[offset:])
        if count <= 0:
            fail("publication write made no progress")
        offset += count


def p_install_exact(path: pathlib.Path, payload: bytes, mode: int, packet_hash: str, *, private_parent: bool) -> None:
    parent_fd = p_check_parent(path.parent, private=private_parent)
    residue = p_residue_name(path, packet_hash)
    try:
        try:
            os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            fail("publication destination already exists")
        descriptor = os.open(
            residue,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            mode,
            dir_fd=parent_fd,
        )
        try:
            p_write_all(descriptor, payload)
            os.fchmod(descriptor, mode)
            os.fsync(descriptor)
            os.lseek(descriptor, 0, os.SEEK_SET)
            if os.read(descriptor, len(payload) + 1) != payload:
                fail("publication candidate reread mismatch")
            candidate = os.fstat(descriptor)
            if (
                not stat.S_ISREG(candidate.st_mode)
                or candidate.st_uid != os.geteuid()
                or candidate.st_nlink != 1
                or stat.S_IMODE(candidate.st_mode) != mode
            ):
                fail("publication candidate metadata mismatch")
            os.link(residue, path.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd, follow_symlinks=False)
            os.fsync(parent_fd)
            final = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
            rebound = os.stat(residue, dir_fd=parent_fd, follow_symlinks=False)
            if (
                (final.st_dev, final.st_ino)
                != (candidate.st_dev, candidate.st_ino)
                or final.st_nlink != 2
                or (rebound.st_dev, rebound.st_ino)
                != (candidate.st_dev, candidate.st_ino)
            ):
                fail("publication final inode mismatch")
            os.unlink(residue, dir_fd=parent_fd)
            os.fsync(parent_fd)
        finally:
            close_owned_descriptors(descriptor)
    finally:
        close_owned_descriptors(parent_fd)
    p_read_state(path, payload, mode)


def p_reconcile_known_residue(path: pathlib.Path, payload: bytes, mode: int, packet_hash: str, *, private_parent: bool) -> None:
    residue_path = p_scan_residues(
        path, packet_hash, private_parent=private_parent
    )
    if residue_path is None:
        return
    parent_fd = p_check_parent(path.parent, private=private_parent)
    try:
        residue_meta = os.stat(residue_path.name, dir_fd=parent_fd, follow_symlinks=False)
        descriptor = os.open(residue_path.name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
        try:
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != os.geteuid()
                or opened.st_nlink not in {1, 2}
                or stat.S_IMODE(opened.st_mode) != mode
                or (opened.st_dev, opened.st_ino) != (residue_meta.st_dev, residue_meta.st_ino)
                or os.read(descriptor, len(payload) + 1) != payload
            ):
                fail("publication residue bytes or mode mismatch")
            os.fsync(descriptor)
            os.lseek(descriptor, 0, os.SEEK_SET)
            reread = os.read(descriptor, len(payload) + 1)
            after_fsync = os.fstat(descriptor)
            visible_after_fsync = os.stat(
                residue_path.name, dir_fd=parent_fd, follow_symlinks=False
            )
            if (
                reread != payload
                or (after_fsync.st_dev, after_fsync.st_ino, after_fsync.st_uid,
                    after_fsync.st_nlink, stat.S_IMODE(after_fsync.st_mode))
                != (opened.st_dev, opened.st_ino, opened.st_uid,
                    opened.st_nlink, stat.S_IMODE(opened.st_mode))
                or (visible_after_fsync.st_dev, visible_after_fsync.st_ino)
                != (opened.st_dev, opened.st_ino)
            ):
                fail("publication residue changed across file fsync")
            try:
                final_meta = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                rebound = os.stat(
                    residue_path.name,
                    dir_fd=parent_fd,
                    follow_symlinks=False,
                )
                if (
                    residue_meta.st_nlink != 1
                    or (rebound.st_dev, rebound.st_ino)
                    != (opened.st_dev, opened.st_ino)
                ):
                    fail("pre-link publication residue changed")
                os.link(
                    residue_path.name,
                    path.name,
                    src_dir_fd=parent_fd,
                    dst_dir_fd=parent_fd,
                    follow_symlinks=False,
                )
                final_meta = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
            os.fsync(parent_fd)
            rebound = os.stat(
                residue_path.name,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
            if (
                (final_meta.st_dev, final_meta.st_ino)
                != (opened.st_dev, opened.st_ino)
                or final_meta.st_nlink != 2
                or (rebound.st_dev, rebound.st_ino)
                != (opened.st_dev, opened.st_ino)
            ):
                fail("publication residue is not the held final inode")
            os.unlink(residue_path.name, dir_fd=parent_fd)
            os.fsync(parent_fd)
        finally:
            close_owned_descriptors(descriptor)
    finally:
        close_owned_descriptors(parent_fd)
    p_read_state(path, payload, mode)


def p_require_receipt_absent(path: pathlib.Path, label: str) -> None:
    try:
        path.lstat()
    except FileNotFoundError:
        return
    fail(label + ": any receipt entry prohibits rollback")


def p_finalize_exact(
    path: pathlib.Path, payload: bytes, mode: int, *, private_parent: bool
) -> None:
    parent_fd: int | None = p_check_parent(path.parent, private=private_parent)
    descriptor: int | None = None
    try:
        before = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        descriptor = os.open(
            path.name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.geteuid()
            or opened.st_nlink != 1
            or stat.S_IMODE(opened.st_mode) != mode
            or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
            or os.read(descriptor, len(payload) + 1) != payload
        ):
            fail("exact-existing entry failed pre-fsync validation")
        os.fsync(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        after = os.fstat(descriptor)
        visible = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            os.read(descriptor, len(payload) + 1) != payload
            or (after.st_dev, after.st_ino, after.st_uid, after.st_nlink,
                stat.S_IMODE(after.st_mode))
            != (opened.st_dev, opened.st_ino, opened.st_uid, opened.st_nlink,
                stat.S_IMODE(opened.st_mode))
            or (visible.st_dev, visible.st_ino) != (opened.st_dev, opened.st_ino)
        ):
            fail("exact-existing entry changed across file fsync")
        os.fsync(parent_fd)
        os.lseek(descriptor, 0, os.SEEK_SET)
        final = os.fstat(descriptor)
        rebound = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            os.read(descriptor, len(payload) + 1) != payload
            or (final.st_dev, final.st_ino, final.st_uid, final.st_nlink,
                stat.S_IMODE(final.st_mode))
            != (opened.st_dev, opened.st_ino, opened.st_uid, opened.st_nlink,
                stat.S_IMODE(opened.st_mode))
            or (rebound.st_dev, rebound.st_ino) != (opened.st_dev, opened.st_ino)
        ):
            fail("exact-existing entry changed across parent fsync")
    except BaseException as error:
        close_owned_descriptors(descriptor, parent_fd, primary=error)
        raise
    close_owned_descriptors(descriptor, parent_fd)


def p_rollback_contract(
    contract_path: pathlib.Path, receipt_path: pathlib.Path, payload: bytes
) -> None:
    p_require_receipt_absent(receipt_path, "rollback preflight")
    parent_fd: int | None = p_check_parent(contract_path.parent, private=False)
    descriptor: int | None = None
    try:
        visible = os.stat(
            contract_path.name, dir_fd=parent_fd, follow_symlinks=False
        )
        descriptor = os.open(
            contract_path.name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_fd,
        )
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.geteuid()
            or opened.st_nlink != 1
            or stat.S_IMODE(opened.st_mode) != CONTRACT_MODE
            or (opened.st_dev, opened.st_ino) != (visible.st_dev, visible.st_ino)
            or os.read(descriptor, len(payload) + 1) != payload
        ):
            fail("rollback contract descriptor is not exact")
        p_require_receipt_absent(receipt_path, "rollback before rebind")
        rebound = os.stat(
            contract_path.name, dir_fd=parent_fd, follow_symlinks=False
        )
        if (rebound.st_dev, rebound.st_ino) != (opened.st_dev, opened.st_ino):
            fail("rollback contract visible inode changed")
        p_require_receipt_absent(receipt_path, "rollback immediately before unlink")
        os.unlink(contract_path.name, dir_fd=parent_fd)
        os.fsync(parent_fd)
        retired = os.fstat(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        if (
            retired.st_dev != opened.st_dev
            or retired.st_ino != opened.st_ino
            or retired.st_uid != opened.st_uid
            or retired.st_nlink != 0
            or stat.S_IMODE(retired.st_mode) != CONTRACT_MODE
            or os.read(descriptor, len(payload) + 1) != payload
        ):
            fail("rollback did not retire the held contract inode")
        try:
            os.stat(contract_path.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            fail("rollback contract name reappeared")
        p_require_receipt_absent(receipt_path, "rollback after unlink")
    except BaseException as error:
        close_owned_descriptors(descriptor, parent_fd, primary=error)
        raise
    close_owned_descriptors(descriptor, parent_fd)


def p_decode_payload(field: object, label: str) -> bytes:
    if type(field) is not str:
        fail("publisher " + label + " payload is not text")
    try:
        raw = base64.b64decode(field.encode("ascii"), validate=True)
    except (UnicodeError, binascii.Error, ValueError) as exc:
        raise BootstrapError(
            "publisher " + label + " payload base64 failed"
        ) from exc
    if base64.b64encode(raw).decode("ascii") != field:
        fail("publisher " + label + " payload is not canonical base64")
    return raw


def p_validate_packet_for_mutation(
    packet_path: pathlib.Path,
    authority_path: pathlib.Path,
    acceptance_path: pathlib.Path,
    plan_path: pathlib.Path,
    public_path: pathlib.Path,
    launch_tool_hash: str,
) -> tuple[dict[str, object], str, bytes, bytes, str]:
    packet, packet_hash, _packet_raw = load_packet(packet_path)
    if packet["tool_sha256"] != launch_tool_hash:
        fail("publisher tool hash mismatch")
    if plan_path.name != "native-entry-durable-registration-v5.md" or plan_path.parent.name != "plans" or plan_path.parent.parent.name != "docs":
        fail("publisher plan path is not repository-bound")
    repo_root = plan_path.parent.parent.parent
    if plan_path != repo_root / "docs/plans/native-entry-durable-registration-v5.md":
        fail("publisher plan path is not canonical")
    if type(packet["state_home_path"]) is not str:
        fail("publisher state home path type mismatch")
    state_home = normalized_absolute(packet["state_home_path"], "packet state-home")
    if acceptance_path != state_home / ACCEPTANCE_RELATIVE_PATH:
        fail("publisher acceptance receipt is not state-root-bound")
    if packet["repo_root_record"] != dir_record(
        repo_root, "awa-registration-owner-repo-root/v1"
    ):
        fail("publisher repository root record mismatch")
    accepted, accepted_raw = acceptance_receipt(acceptance_path, plan_path, launch_tool_hash)
    if packet["accepted_v5_normalized_digest"] != accepted["normalized_digest"] or packet["accepted_v5_receipt_hash"] != sha256(accepted_raw):
        fail("publisher accepted-v5 binding mismatch")
    public_raw, public_record = read_bounded_descriptor(public_path, MAX_PUBLIC_BYTES, {0o600, 0o644})
    if public_record != packet["public_input_record"]:
        fail("publisher public descriptor mismatch")
    public = p_parse_public(public_raw, {
        "public_key_sha256": ACCEPTED_PUBLIC_KEY_SHA256,
        "openssh_fingerprint": ACCEPTED_FINGERPRINT,
        "allowed_signers_contract_hash": ACCEPTED_CONTRACT_SHA256,
    })
    _receipt, current_raw, enrollment_hash = build_current_receipt(public, packet["created_wall_ns"])
    if (
        packet["schema"]
        != "awa-registration-owner-key-bootstrap-packet/v1"
        or packet["repository"] != "KleinPerkins/awa"
        or packet["source_commit"] != BASE_COMMIT
        or packet["canonical_public_b64"]
        != base64.b64encode(public_raw).decode("ascii")
        or packet["principal"] != PRINCIPAL
        or packet["namespace"] != NAMESPACE
        or packet["key_algorithm"] != KEY_ALGORITHM
        or packet["allowed_signers_relative_path"] != CONTRACT_RELATIVE_PATH
        or packet["allowed_signers_path_hash"]
        != sha256(
            b"awa-registration-owner-signers-path/v1\0"
            + CONTRACT_RELATIVE_PATH.encode("utf-8")
        )
        or packet["sequence"] != "1"
        or packet["status"] != "ACTIVE"
        or packet["previous_enrollment_hash"] is not None
        or packet["authorized_recovery_actions"] != list(RECOVERY_ACTIONS)
        or packet["denied_implications"] != list(DENIED_IMPLICATIONS)
    ):
        fail("publisher packet semantics mismatch")
    contract_output = exact_keys(packet["contract_output"], {"absolute_path", "path_hash", "mode", "payload_sha256", "payload_b64"}, "publisher contract output")
    current_output = exact_keys(packet["current_output"], {"absolute_path", "path_hash", "mode", "parent_mode", "payload_sha256", "payload_b64"}, "publisher current output")
    if type(contract_output["absolute_path"]) is not str or type(current_output["absolute_path"]) is not str:
        fail("publisher output path type mismatch")
    contract_path = normalized_absolute(contract_output["absolute_path"], "contract output")
    current_path = normalized_absolute(current_output["absolute_path"], "current output")
    if (
        contract_path != repo_root / CONTRACT_RELATIVE_PATH
        or current_path != state_home / CURRENT_RELATIVE_PATH
        or contract_output["path_hash"] != path_hash(
            "awa-registration-owner-contract-output-path/v1", contract_path
        )
        or current_output["path_hash"] != path_hash(
            "awa-registration-owner-current-output-path/v1", current_path
        )
        or contract_output["mode"] != str(CONTRACT_MODE)
        or current_output["mode"] != str(CURRENT_MODE)
        or current_output["parent_mode"] != str(PRIVATE_DIR_MODE)
        or p_decode_payload(
            contract_output["payload_b64"], "contract"
        ) != public["contract"]
        or contract_output["payload_sha256"] != sha256(public["contract"])
        or p_decode_payload(
            current_output["payload_b64"], "current"
        ) != current_raw
        or current_output["payload_sha256"] != sha256(current_raw)
        or packet["enrollment_hash"] != enrollment_hash
        or packet["public_key_sha256"] != ACCEPTED_PUBLIC_KEY_SHA256
        or packet["openssh_fingerprint"] != ACCEPTED_FINGERPRINT
        or packet["allowed_signers_contract_hash"] != ACCEPTED_CONTRACT_SHA256
        or packet["key_enrollment_digest"] != ACCEPTED_KEY_ENROLLMENT_DIGEST
        or packet["owner_authorization_digest"] != ACCEPTED_OWNER_AUTHORIZATION_DIGEST
    ):
        fail("publisher packet reconstruction mismatch")
    _authority, decision_digest = load_authority(authority_path, packet, packet_hash)
    return packet, packet_hash, public["contract"], current_raw, decision_digest


def p_prepare_state_parent(state_home: pathlib.Path) -> pathlib.Path:
    if not state_home.exists():
        fail("state home must preexist for bounded bootstrap")
    state_home_fd = p_check_parent(state_home, private=True)
    close_owned_descriptors(state_home_fd)
    awa = p_ensure_private_child(state_home, "awa")
    return p_ensure_private_child(awa, "registration-owner-key")


def p_existing_state_parent(state_home: pathlib.Path) -> pathlib.Path | None:
    awa = state_home / "awa"
    try:
        awa.lstat()
    except FileNotFoundError:
        return None
    awa_fd = p_check_parent(awa, private=True)
    close_owned_descriptors(awa_fd)
    owner_state = awa / "registration-owner-key"
    try:
        owner_state.lstat()
    except FileNotFoundError:
        return None
    owner_fd = p_check_parent(owner_state, private=True)
    close_owned_descriptors(owner_fd)
    return owner_state


def p_mutate(mode: str, options: dict[str, str], launch_tool_hash: str) -> dict[str, object]:
    required = {"plan", "acceptance-receipt", "packet", "authority", "public-key"}
    action: str | None = None
    if mode == "publish":
        if set(options) != required:
            fail("publish forbids recovery-action and requires exact authority inputs")
    elif mode == "recover":
        if set(options) != required | {"recovery-action"}:
            fail("recover requires exact authority inputs and one recovery-action")
        action = options["recovery-action"]
        if action not in {"forward", "rollback-contract-only"}:
            fail("recover action is unknown or unauthorized")
    else:
        fail("mutation mode is unknown or unauthorized")
    paths = {name: normalized_absolute(options[name], name) for name in required}
    packet, packet_hash, contract_raw, current_raw, decision_digest = p_validate_packet_for_mutation(
        paths["packet"], paths["authority"], paths["acceptance-receipt"],
        paths["plan"], paths["public-key"], launch_tool_hash,
    )
    contract_path = pathlib.Path(packet["contract_output"]["absolute_path"])
    current_path = pathlib.Path(packet["current_output"]["absolute_path"])
    state_home = pathlib.Path(packet["state_home_path"])
    if current_path != state_home / CURRENT_RELATIVE_PATH:
        fail("packet current path differs from state-root binding")
    state_fd: int | None = p_check_parent(state_home, private=True)
    try:
        fcntl.flock(state_fd, fcntl.LOCK_EX)
        existing_state_parent = p_existing_state_parent(state_home)
        if existing_state_parent is not None and current_path.parent != existing_state_parent:
            fail("existing state parent differs from packet binding")
        # Primary state is authoritative and MUST be classified before residue work.
        primary = p_primary_state(contract_path, current_path, contract_raw, current_raw)
        contract_residue = p_scan_residues(
            contract_path, packet_hash, private_parent=False
        )
        receipt_residue = None if existing_state_parent is None else p_scan_residues(
            current_path, packet_hash, private_parent=True
        )
        if receipt_residue is not None and primary == "ABSENT_CONTRACT/ABSENT_RECEIPT":
            fail("receipt residue exists without exact primary contract")
        if contract_residue is not None:
            p_reconcile_known_residue(
                contract_path, contract_raw, CONTRACT_MODE, packet_hash,
                private_parent=False,
            )
        if receipt_residue is not None:
            if primary not in {
                "EXACT_CONTRACT/ABSENT_RECEIPT",
                "EXACT_CONTRACT/EXACT_RECEIPT",
            }:
                fail("receipt residue is orphaned from exact contract authority")
            p_reconcile_known_residue(
                current_path, current_raw, CURRENT_MODE, packet_hash,
                private_parent=True,
            )
        primary = p_primary_state(contract_path, current_path, contract_raw, current_raw)
        if mode == "publish":
            if primary == "EXACT_CONTRACT/EXACT_RECEIPT":
                p_finalize_exact(contract_path, contract_raw, CONTRACT_MODE, private_parent=False)
                p_finalize_exact(current_path, current_raw, CURRENT_MODE, private_parent=True)
                outcome = "EXACT_EXISTING_DURABLE"
            elif primary == "ABSENT_CONTRACT/ABSENT_RECEIPT":
                p_install_exact(contract_path, contract_raw, CONTRACT_MODE, packet_hash, private_parent=False)
                state_parent = p_prepare_state_parent(state_home)
                if current_path.parent != state_parent:
                    fail("packet current parent differs from prepared state parent")
                p_install_exact(current_path, current_raw, CURRENT_MODE, packet_hash, private_parent=True)
                p_finalize_exact(contract_path, contract_raw, CONTRACT_MODE, private_parent=False)
                p_finalize_exact(current_path, current_raw, CURRENT_MODE, private_parent=True)
                outcome = "PUBLISHED_DURABLE"
            else:
                fail("contract-only state requires explicit recover")
        else:
            if primary == "EXACT_CONTRACT/EXACT_RECEIPT":
                p_finalize_exact(contract_path, contract_raw, CONTRACT_MODE, private_parent=False)
                p_finalize_exact(current_path, current_raw, CURRENT_MODE, private_parent=True)
                outcome = "EXACT_EXISTING_DURABLE"
            elif primary != "EXACT_CONTRACT/ABSENT_RECEIPT":
                fail("recover accepts only exact contract-only or exact/exact state")
            elif action == "forward":
                state_parent = p_prepare_state_parent(state_home)
                if current_path.parent != state_parent:
                    fail("packet current parent differs from prepared state parent")
                p_install_exact(current_path, current_raw, CURRENT_MODE, packet_hash, private_parent=True)
                p_finalize_exact(contract_path, contract_raw, CONTRACT_MODE, private_parent=False)
                p_finalize_exact(current_path, current_raw, CURRENT_MODE, private_parent=True)
                outcome = "FORWARD_COMPLETED_DURABLE"
            else:
                p_rollback_contract(contract_path, current_path, contract_raw)
                outcome = "CONTRACT_ONLY_ROLLED_BACK"
        final_state = p_primary_state(contract_path, current_path, contract_raw, current_raw)
    except BaseException as error:
        close_owned_descriptors(state_fd, primary=error)
        raise
    close_owned_descriptors(state_fd)
    return {
        "schema": "awa-registration-owner-key-bootstrap-mutation/v1",
        "mode": mode,
        "outcome": outcome,
        "final_state": final_state,
        "packet_sha256": packet_hash,
        "gate3b_decision_digest": decision_digest,
        "enrollment_hash": packet["enrollment_hash"],
    }


def parse_options(arguments: list[str]) -> dict[str, str]:
    if len(arguments) % 2:
        fail("options require exact --name value pairs")
    result: dict[str, str] = {}
    for index in range(0, len(arguments), 2):
        key = arguments[index]
        if not key.startswith("--") or key[2:] in result or not arguments[index + 1]:
            fail("options are malformed or duplicated")
        result[key[2:]] = arguments[index + 1]
    return result


def static_self_check() -> None:
    source = globals().get("__bootstrap_payload_bytes__")
    if type(source) is not bytes:
        fail("launcher did not bind payload bytes")
    tree = ast.parse(source.decode("utf-8"))
    if any(isinstance(node, ast.Assert) for node in ast.walk(tree)):
        fail("validation assertion statement is forbidden")
    forbidden_imports = {"socket", "subprocess", "urllib", "http", "ftplib", "ssl", "asyncio"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = {alias.name.split(".", 1)[0] for alias in node.names}
            if names & forbidden_imports:
                fail("forbidden import is present")
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".", 1)[0] in forbidden_imports:
            fail("forbidden import-from is present")
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    for name, node in functions.items():
        if not name.startswith("v_"):
            continue
        called = {
            child.func.id
            for child in ast.walk(node)
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
        }
        if any(
            value.startswith("p_")
            or value in {
                "build_packet", "build_current_receipt", "enrollment_object",
                "load_authority", "load_packet", "acceptance_receipt",
                "read_bounded_descriptor", "strict_json",
            }
            for value in called
        ):
            fail("validator calls publisher builder or mutation helper")
    for name in ("build_packet", "p_mutate"):
        node = functions[name]
        if any(isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute) and child.func.attr in {"time", "time_ns", "monotonic", "monotonic_ns"} for child in ast.walk(node)):
            fail("packet or mutation path samples a clock")


def expect_error(function, label: str) -> None:
    try:
        function()
    except BootstrapError:
        return
    fail("self-test expected refusal: " + label)


def self_test() -> dict[str, object]:
    static_self_check()
    synthetic_raw = b"ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAABAgMEBQYHCAkKCwwNDg8QERITFBUWFxgZGhscHR4f\n"
    synthetic_expected = {
        "public_key_sha256": "8b5a6781cafa6fd206a9681ddc4f09148311c8a14a571c784d30e5c53777e429",
        "openssh_fingerprint": "SHA256:ZkAslGjFiUHdGf/WUL8rQvkib4PTvQatUV0OUQSncCA",
        "allowed_signers_contract_hash": "bbd1f1bc972dc5ab20635021d8486f15de24011f61b59c1c6861379acc8b8c5f",
    }
    first = p_parse_public(synthetic_raw, synthetic_expected)
    second = v_parse_public(synthetic_raw, synthetic_expected)
    if first["contract"] != second["contract"]:
        fail("publisher and validator synthetic contract disagree")
    malformed = (
        synthetic_raw.rstrip(b"\n"),
        synthetic_raw + b"\n",
        synthetic_raw.replace(b"\n", b" comment\n"),
        b" ssh-ed25519 " + synthetic_raw.split(b" ", 1)[1],
        synthetic_raw.replace(b"ssh-ed25519 ", b"ssh-rsa "),
        synthetic_raw.replace(b"\n", b"\r\n"),
    )
    for index, raw in enumerate(malformed):
        expect_error(lambda raw=raw: p_parse_public(raw, synthetic_expected), "publisher malformed public " + str(index))
        expect_error(lambda raw=raw: v_parse_public(raw, synthetic_expected), "validator malformed public " + str(index))
    with tempfile.TemporaryDirectory(prefix="awa-v5-bootstrap-self-test-") as temporary:
        root = pathlib.Path(temporary)
        repo = root / "repo"
        contracts = repo / "contracts"
        state = root / "state"
        owner_state = state / "awa" / "registration-owner-key"
        contracts.mkdir(parents=True, mode=0o755)
        state.mkdir(mode=0o700)
        (state / "awa").mkdir(mode=0o700)
        owner_state.mkdir(mode=0o700)
        contract_path = contracts / "awa-registration-owner-signers.v1"
        receipt_path = owner_state / "current.json"
        receipt_raw = jcs({"schema": "synthetic-current/v1"}) + b"\n"
        contract_raw = first["contract"]
        if p_primary_state(contract_path, receipt_path, contract_raw, receipt_raw) != "ABSENT_CONTRACT/ABSENT_RECEIPT":
            fail("self-test absent state mismatch")
        p_install_exact(contract_path, contract_raw, CONTRACT_MODE, "11" * 32, private_parent=False)
        if p_primary_state(contract_path, receipt_path, contract_raw, receipt_raw) != "EXACT_CONTRACT/ABSENT_RECEIPT":
            fail("self-test contract-only state mismatch")
        p_install_exact(receipt_path, receipt_raw, CURRENT_MODE, "22" * 32, private_parent=True)
        if p_primary_state(contract_path, receipt_path, contract_raw, receipt_raw) != "EXACT_CONTRACT/EXACT_RECEIPT":
            fail("self-test exact state mismatch")
        receipt_path.write_bytes(b"mismatch\n")
        os.chmod(receipt_path, CURRENT_MODE)
        expect_error(lambda: p_primary_state(contract_path, receipt_path, contract_raw, receipt_raw), "mismatched receipt")
        receipt_path.unlink()
        contract_path.unlink()
        receipt_path.symlink_to(contract_path)
        expect_error(lambda: p_primary_state(contract_path, receipt_path, contract_raw, receipt_raw), "orphan symlink receipt")
        receipt_path.unlink()
        residue_packet_hash = "33" * 32
        recovered_path = contracts / "pre-link-recovered"
        recovered_raw = b"pre-link-recovery\n"
        residue_path = contracts / p_residue_name(
            recovered_path, residue_packet_hash
        )
        residue_path.write_bytes(recovered_raw)
        os.chmod(residue_path, CONTRACT_MODE)
        p_reconcile_known_residue(
            recovered_path, recovered_raw, CONTRACT_MODE,
            residue_packet_hash, private_parent=False,
        )
        if (
            residue_path.exists()
            or p_read_state(
                recovered_path, recovered_raw, CONTRACT_MODE
            )[0] != "EXACT"
        ):
            fail("self-test pre-link residue recovery mismatch")
        sample_packet = {key: None for key in PACKET_FIELDS}
        if (
            "packet_sha256" in sample_packet
            or "gate3b_decision_digest" in sample_packet
        ):
            fail("self-test found packet/decision digest cycle")
        packet_path = root / "packet.json"
        packet_digest = domain_hash(
            "awa-registration-owner-key-bootstrap-packet/v1",
            sample_packet,
        )
        packet_path.write_bytes(
            jcs({
                "packet": sample_packet,
                "packet_sha256": packet_digest,
            }) + b"\n"
        )
        os.chmod(packet_path, CURRENT_MODE)
        v_load_packet(packet_path)
        mutated_document = {
            "packet": sample_packet,
            "packet_sha256": "00" * 32,
        }
        packet_path.write_bytes(jcs(mutated_document) + b"\n")
        expect_error(
            lambda: v_load_packet(packet_path),
            "mutated exact packet hash",
        )
        circular_packet = {
            **sample_packet,
            "gate3b_decision_digest": "00" * 32,
        }
        packet_path.write_bytes(
            jcs({
                "packet": circular_packet,
                "packet_sha256": domain_hash(
                    "awa-registration-owner-key-bootstrap-packet/v1",
                    circular_packet,
                ),
            }) + b"\n"
        )
        expect_error(
            lambda: v_load_packet(packet_path),
            "circular Gate 3B decision field",
        )
    return {
        "schema": "awa-registration-owner-key-bootstrap-self-test/v1",
        "tests": [
            "STATIC_AST",
            "PUBLIC_GRAMMAR",
            "MALFORMED_PUBLIC",
            "THREE_STATE_CLASSIFIER",
            "MISMATCH_AND_ORPHAN_REFUSAL",
            "PRE_LINK_RESIDUE_RECOVERY",
            "EXACT_PACKET_HASH_MUTATION",
            "PACKET_DECISION_ACYCLICITY_AND_FIELD_REFUSAL",
        ],
        "synthetic_roots_only": True,
        "production_paths_touched": False,
        "result": "PASS",
    }


def emit(value: object) -> None:
    sys.stdout.buffer.write(jcs(value) + b"\n")


def main() -> None:
    try:
        if len(sys.argv) < 2:
            fail("mode is required")
        mode = sys.argv[1]
        options = parse_options(sys.argv[2:])
        launch_tool_hash = globals().get("__v5_bootstrap_sha256_expected__")
        if type(launch_tool_hash) is not str or HEX64.fullmatch(launch_tool_hash) is None:
            fail("launcher-independent bootstrap hash is absent")
        if mode == "self-test":
            if options:
                fail("self-test accepts no options")
            emit(self_test())
            return
        if mode == "packet":
            required = {"repo-root", "state-home", "plan", "acceptance-receipt", "public-key", "created-wall-ns"}
            if set(options) != required:
                fail("packet requires exact future public/timestamp/accepted-v5 inputs")
            packet = build_packet(
                repo_root=normalized_absolute(options["repo-root"], "repo-root"),
                state_home=normalized_absolute(options["state-home"], "state-home"),
                plan_path=normalized_absolute(options["plan"], "plan"),
                receipt_path=normalized_absolute(options["acceptance-receipt"], "acceptance-receipt"),
                public_path=normalized_absolute(options["public-key"], "public-key"),
                created_wall_ns=options["created-wall-ns"],
                launch_tool_hash=launch_tool_hash,
            )
            emit(packet)
            return
        if mode == "validate":
            required = {"packet", "authority", "acceptance-receipt", "plan", "public-key"}
            if set(options) != required:
                fail("validate requires exact future packet/authority/accepted-v5 inputs")
            emit(v_validate(
                packet_path=normalized_absolute(options["packet"], "packet"),
                authority_path=normalized_absolute(options["authority"], "authority"),
                acceptance_path=normalized_absolute(options["acceptance-receipt"], "acceptance-receipt"),
                plan_path=normalized_absolute(options["plan"], "plan"),
                public_path=normalized_absolute(options["public-key"], "public-key"),
                launch_tool_hash=launch_tool_hash,
            ))
            return
        if mode in {"publish", "recover"}:
            emit(p_mutate(mode, options, launch_tool_hash))
            return
        fail("unknown mode")
    except BootstrapError as exc:
        sys.stderr.write("awa-v5-bootstrap: " + str(exc) + "\n")
        raise SystemExit(2)


if not globals().get("__bootstrap_harness_import__", False):
    main()
```
<!-- awa-v5-enrollment-bootstrap-tool:v1:end -->

- **Bootstrap fault harness SHA-256:** `2f12d26b6d4c5f3fc12a36ade14ee2c118e054cb0a1cb42610765d1f8de64ef2`

<!-- awa-v5-bootstrap-fault-harness:v1:begin -->
```python
from __future__ import annotations

import ast
import base64
import hashlib
import json
import os
import pathlib
import stat
import struct
import sys
import tempfile
import types


def fail(message: str) -> None:
    raise RuntimeError("awa-v5-harness: " + message)


def check(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def jcs(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def extract(plan: bytes, marker: str) -> bytes:
    begin = f"<!-- {marker}:begin -->\n```python\n".encode()
    end = f"```\n<!-- {marker}:end -->".encode()
    if plan.count(begin) != 1 or plan.count(end) != 1:
        fail(marker + " markers")
    return plan.split(begin, 1)[1].split(end, 1)[0]


class ModuleProxy:
    def __init__(self, scope: dict[str, object]) -> None:
        object.__setattr__(self, "scope", scope)

    def __getattr__(self, name: str) -> object:
        return self.scope[name]

    def __setattr__(self, name: str, value: object) -> None:
        self.scope[name] = value


def expect_error(function, label: str) -> None:
    try:
        function()
    except BaseException:
        return
    fail("expected refusal: " + label)


def tree_snapshot(root: pathlib.Path) -> list[tuple[object, ...]]:
    rows: list[tuple[object, ...]] = []
    for path in sorted(root.rglob("*"), key=lambda item: str(item)):
        metadata = path.lstat()
        relative = str(path.relative_to(root))
        if stat.S_ISREG(metadata.st_mode):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            kind = "file"
        elif stat.S_ISDIR(metadata.st_mode):
            digest = "-"
            kind = "dir"
        elif stat.S_ISLNK(metadata.st_mode):
            digest = os.readlink(path)
            kind = "symlink"
        else:
            digest = "-"
            kind = "other"
        rows.append((
            relative, kind, format(stat.S_IMODE(metadata.st_mode), "04o"),
            digest, metadata.st_dev, metadata.st_ino, metadata.st_uid,
            metadata.st_nlink, metadata.st_size, metadata.st_mtime_ns,
        ))
    return rows

def write_exact(path: pathlib.Path, raw: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    os.chmod(path, mode)


def synthetic_public() -> bytes:
    algorithm = b"ssh-ed25519"
    key = bytes(range(32))
    blob = struct.pack(">I", len(algorithm)) + algorithm + struct.pack(">I", len(key)) + key
    return b"ssh-ed25519 " + base64.b64encode(blob) + b"\n"


def main() -> None:
    plan_path = pathlib.Path(globals().get("__v5_plan_path__", ""))
    plan_raw = plan_path.read_bytes()
    bootstrap = extract(plan_raw, "awa-v5-enrollment-bootstrap-tool:v1")
    expected_bootstrap = globals().get("__v5_bootstrap_sha256_expected__")
    if hashlib.sha256(bootstrap).hexdigest() != expected_bootstrap:
        fail("launcher bootstrap expectation missing")
    scope: dict[str, object] = {
        "__name__": "awa_v5_bootstrap_harness_module",
        "__file__": str(plan_path) + "::bootstrap-harness-import",
        "__bootstrap_harness_import__": True,
        "__v5_plan_path__": str(plan_path),
        "__v5_full_plan_sha256_expected__": globals().get("__v5_full_plan_sha256_expected__"),
        "__v5_checker_sha256_expected__": globals().get("__v5_checker_sha256_expected__"),
        "__v5_bootstrap_sha256_expected__": expected_bootstrap,
    }
    exec(compile(bootstrap, scope["__file__"], "exec", dont_inherit=True), scope, scope)
    module = ModuleProxy(scope)
    checker_bytes = extract(plan_raw, "awa-v5-acceptance-checker:v1")
    checker_scope: dict[str, object] = {
        "__name__": "awa_v5_acceptance_harness_module",
        "__file__": str(plan_path) + "::acceptance-harness-import",
        "__acceptance_harness_import__": True,
        "__v5_full_plan_sha256_expected__": globals().get("__v5_full_plan_sha256_expected__"),
        "__v5_checker_sha256_expected__": globals().get("__v5_checker_sha256_expected__"),
        "__v5_bootstrap_sha256_expected__": expected_bootstrap,
        "__v5_harness_sha256_expected__": globals().get("__v5_harness_sha256_expected__"),
    }
    exec(compile(checker_bytes, checker_scope["__file__"], "exec", dont_inherit=True), checker_scope, checker_scope)
    checker = ModuleProxy(checker_scope)
    called: set[str] = set()
    production = {
        "acceptance_receipt", "build_packet", "close_owned_descriptors",
        "read_bounded_descriptor", "p_regular_metadata_tuple", "p_visible_regular",
        "v_regular_metadata_tuple", "v_visible_regular",
        "p_parse_public", "v_parse_public", "dir_record",
        "v_domain_hash", "v_strict_json", "v_read_descriptor", "v_load_packet",
        "v_extract_plan_artifacts", "v_load_acceptance", "v_decode_payload",
        "v_reconstruct", "v_read_exact", "v_validate", "p_read_state",
        "p_primary_state", "p_check_parent", "p_ensure_private_child",
        "p_residue_name", "p_scan_residues", "p_write_all", "p_install_exact",
        "p_reconcile_known_residue", "p_require_receipt_absent", "p_finalize_exact",
        "p_rollback_contract", "p_decode_payload", "p_validate_packet_for_mutation",
        "p_prepare_state_parent", "p_existing_state_parent", "p_mutate",
    }
    def tracer(frame, event, arg):
        if event == "call" and frame.f_code.co_filename == scope["__file__"]:
            called.add(frame.f_code.co_name)
        return tracer

    vectors: list[str] = []
    sys.settrace(tracer)
    try:
        with tempfile.TemporaryDirectory(prefix="awa-v5-bootstrap-harness-") as temporary:
            root = pathlib.Path(temporary)
            checker_tree = ast.parse(checker_bytes.decode("utf-8"))
            checker_functions = {node.name: node for node in checker_tree.body if isinstance(node, ast.FunctionDef)}
            checker_producers = sorted(
                name for name, node in checker_functions.items()
                if any(
                    isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Attribute)
                    and isinstance(child.func.value, ast.Name)
                    and child.func.value.id == "os"
                    and child.func.attr in {"open", "dup"}
                    for child in ast.walk(node)
                )
            )
            raw_close = [
                name for name, node in checker_functions.items()
                if name != "close_owned_descriptors" and any(
                    isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Attribute)
                    and isinstance(child.func.value, ast.Name)
                    and child.func.value.id == "os"
                    and child.func.attr == "close"
                    for child in ast.walk(node)
                )
            ]
            check(not raw_close and checker_producers, "checker descriptor cleanup routing")
            check(
                not any(
                    isinstance(node, ast.Raise) and node.cause is not None
                    for node in ast.walk(
                        checker_functions["close_owned_descriptors"]
                    )
                ),
                "checker raise-from cleanup remains",
            )
            vectors.extend([
                "CHECKER_DESCRIPTOR_PRODUCER_AST",
                "CHECKER_RAW_CLOSE_ROUTING",
                "CHECKER_NO_RAISE_FROM_PRIMARY",
            ])
            checker_primary = RuntimeError("checker primary")
            checker_original_close = checker.os.close
            checker_close_calls: list[int] = []
            def checker_close_fault(fd):
                checker_close_calls.append(fd)
                raise OSError("synthetic checker close " + str(fd))
            checker.os.close = checker_close_fault
            try:
                checker_traceback = None
                try:
                    try:
                        raise checker_primary
                    except BaseException as error:
                        checker_traceback = error.__traceback__
                        cleanup = checker.close_owned_descriptors(
                            987651, 987652, 987653, primary=error
                        )
                        check(cleanup is error.__context__, "checker cleanup context")
                        check(error.__traceback__ is checker_traceback, "checker traceback changed during cleanup")
                        raise
                except BaseException as error:
                    check(error is checker_primary, "checker primary identity")
                    check(error.__traceback__ is checker_traceback, "checker bare-raise traceback identity")
                    check(isinstance(error.__context__, OSError), "checker cleanup association")
                check(checker_close_calls == [987651, 987652, 987653], "checker all-close attempts")
                try:
                    checker.close_owned_descriptors(987654)
                except OSError:
                    pass
                else:
                    fail("checker lone close fault suppressed")
            finally:
                checker.os.close = checker_original_close
            vectors.extend([
                "CHECKER_PRIMARY_OBJECT_IDENTITY",
                "CHECKER_PRIMARY_TRACEBACK_IDENTITY",
                "CHECKER_SECONDARY_CLEANUP_ASSOCIATION",
                "CHECKER_ALL_CLOSE_ATTEMPTS",
                "CHECKER_LONE_CLOSE_FAILURE",
            ])
            checker_repo = root / "checker-packet-repo"
            governed_paths = [
                "docs/plans/native-entry-durable-registration-v5.md",
                "docs/plans/native-entry-durable-registration-v4.md",
                "docs/plans/README.md",
                "docs/adr/0026-durable-registration-authority-hardening.md",
                "docs/adr/README.md",
            ]
            source_root = pathlib.Path.cwd()
            for relative in governed_paths:
                write_exact(
                    checker_repo / relative,
                    (source_root / relative).read_bytes(),
                    0o644,
                )
            checker_root_fd = os.open(
                checker_repo, os.O_RDONLY | os.O_DIRECTORY
            )
            try:
                generated_packet = checker.packet_object(checker_root_fd)
                generated_raw = checker.jcs(generated_packet) + b"\n"
                parsed_packet = checker.parse_packet(
                    checker_root_fd, generated_raw
                )
                check(parsed_packet == generated_packet, "checker packet round trip")
                parsed_owner = checker.parse_owner_language(
                    checker_root_fd,
                    generated_packet["required_owner_language"],
                )
                check(
                    parsed_owner
                    == generated_packet["owner_acceptance_envelope"],
                    "checker owner language parse",
                )
                preflight = checker.recover_preflight(
                    checker_root_fd, generated_raw
                )
                check(preflight == generated_packet, "checker recover-pre preflight")
                vectors.extend([
                    "CHECKER_PACKET_JCS_ROUND_TRIP",
                    "CHECKER_PACKET_PARSE_OWNER",
                    "CHECKER_RECOVER_PRE_COMPATIBILITY",
                ])
                packet_negatives = []
                missing = dict(generated_packet); missing.pop("schema")
                packet_negatives.append(checker.jcs(missing) + b"\n")
                extra = {**generated_packet, "extra": None}
                packet_negatives.append(checker.jcs(extra) + b"\n")
                duplicate = generated_raw[:-2] + b',"schema":"awa-registration-v5-acceptance-packet/v2"}\n'
                packet_negatives.append(duplicate)
                wrong_type = {**generated_packet, "owner_acceptance_digest": 7}
                packet_negatives.append(checker.jcs(wrong_type) + b"\n")
                reversed_raw = json.dumps(
                    dict(reversed(list(generated_packet.items()))),
                    ensure_ascii=False, sort_keys=False,
                    separators=(",", ":"), allow_nan=False,
                ).encode() + b"\n"
                packet_negatives.append(reversed_raw)
                mismatch = {**generated_packet, "owner_acceptance_digest": "00" * 32}
                packet_negatives.append(checker.jcs(mismatch) + b"\n")
                for index, bad in enumerate(packet_negatives):
                    expect_error(
                        lambda bad=bad: checker.parse_packet(
                            checker_root_fd, bad
                        ),
                        "checker packet negative " + str(index),
                    )
                vectors.extend([
                    "CHECKER_PACKET_MISSING_FIELD",
                    "CHECKER_PACKET_EXTRA_FIELD",
                    "CHECKER_PACKET_DUPLICATE_FIELD",
                    "CHECKER_PACKET_TYPE_MISMATCH",
                    "CHECKER_PACKET_JCS_ORDER",
                    "CHECKER_PACKET_SEMANTIC_MISMATCH",
                ])
            finally:
                os.close(checker_root_fd)
            transfer_root = root / "checker-transfer"
            (transfer_root / "child").mkdir(parents=True)
            root_fd = os.open(transfer_root, os.O_RDONLY | os.O_DIRECTORY)
            close_calls = 0
            def transfer_close(fd):
                nonlocal close_calls
                close_calls += 1
                if close_calls == 1:
                    raise OSError("synthetic parent close")
                return checker_original_close(fd)
            checker.os.close = transfer_close
            try:
                expect_error(lambda: checker.open_parent(root_fd, "child/file"), "checker child ownership on parent close")
            finally:
                checker.os.close = checker_original_close
                os.close(root_fd)
            check(close_calls >= 2, "checker child descriptor cleanup not attempted")
            vectors.append("CHECKER_IMMEDIATE_CHILD_OWNERSHIP")
            repo = root / "repo"
            state = root / "state"
            plan = repo / "docs/plans/native-entry-durable-registration-v5.md"
            contracts = repo / "contracts"
            contracts.mkdir(parents=True, mode=0o755)
            state.mkdir(mode=0o700)
            accepted_plan = plan_raw.replace(
                "- **Status:** DRAFT (for review) — DOCUMENTATION ONLY; IMPLEMENTATION DELIVERY AND R0 NO-GO\n".encode(),
                "- **Status:** ACCEPTED — FROZEN — DOCUMENTATION ONLY; IMPLEMENTATION DELIVERY AND R0 NO-GO\n".encode(),
                1,
            )
            write_exact(plan, accepted_plan, 0o644)
            artifacts = module.extract_plan_artifacts(accepted_plan)
            module.BOOTSTRAP_LAUNCHER_SHA256 = artifacts["launcher_sha256"]
            scope["__v5_full_plan_sha256_expected__"] = hashlib.sha256(accepted_plan).hexdigest()
            scope["__v5_checker_sha256_expected__"] = artifacts["checker_sha256"]
            scope["__v5_bootstrap_sha256_expected__"] = artifacts["bootstrap_sha256"]
            public_raw = synthetic_public()
            wire = base64.b64decode(public_raw.split(b" ", 1)[1].strip(), validate=True)
            fingerprint = "SHA256:" + base64.b64encode(hashlib.sha256(wire).digest()).decode().rstrip("=")
            contract_raw = b'KleinPerkins namespaces="awa-registration-owner-gate-v2" ' + public_raw
            module.ACCEPTED_PUBLIC_KEY_SHA256 = hashlib.sha256(public_raw).hexdigest()
            module.ACCEPTED_FINGERPRINT = fingerprint
            module.ACCEPTED_CONTRACT_SHA256 = hashlib.sha256(contract_raw).hexdigest()
            enrollment = {
                "schema": "awa-registration-owner-key-enrollment/v1",
                "principal": "KleinPerkins",
                "namespace": "awa-registration-owner-gate-v2",
                "key_algorithm": "ssh-ed25519",
                "public_key_sha256": module.ACCEPTED_PUBLIC_KEY_SHA256,
                "openssh_fingerprint": fingerprint,
                "allowed_signers_relative_path": module.CONTRACT_RELATIVE_PATH,
                "allowed_signers_path_hash": hashlib.sha256(b"awa-registration-owner-signers-path/v1\0" + module.CONTRACT_RELATIVE_PATH.encode()).hexdigest(),
                "allowed_signers_contract_hash": module.ACCEPTED_CONTRACT_SHA256,
                "authorized": True,
            }
            module.ACCEPTED_KEY_ENROLLMENT_DIGEST = module.domain_hash("awa-registration-owner-key-enrollment/v1", enrollment)
            module.ACCEPTED_OWNER_AUTHORIZATION_DIGEST = "44" * 32
            public_path = root / "synthetic-public.pub"
            write_exact(public_path, public_raw, 0o600)
            anchors = [
                {"kind": "FULL_FILE", "path": "docs/plans/native-entry-durable-registration-v4.md", "sha256": module.V4_SHA256},
                {"kind": "FULL_FILE", "path": "docs/adr/0026-durable-registration-authority-hardening.md", "sha256": module.ADR_0026_SHA256},
                {"kind": "EXACT_ROW", "path": "docs/adr/README.md", "sha256": "c2ffbac9b939d1217eedc55824c48353a32ab00f7a15b95e151fd785ff873123"},
                {"kind": "V4_EXACT_ROW", "path": "docs/plans/README.md", "sha256": "6c920e7e177a37a1092d0d4096a2966bea10a29844ae3f7dbfe07acb6902a3c0"},
            ]
            rows = [
                {"path": "docs/plans/README.md", "post_backing_file_sha256": "55" * 32},
                {"path": "docs/plans/native-entry-durable-registration-v5.md", "post_backing_file_sha256": hashlib.sha256(accepted_plan).hexdigest()},
            ]
            recovery = {
                **artifacts,
                "immutable_anchors": anchors,
                "normalized_digest": "66" * 32,
                "ordered_surfaces": rows,
                "repository": "KleinPerkins/awa",
                "schema": "awa-registration-v5-recovery-vector/v1",
                "source_commit": module.BASE_COMMIT,
            }
            receipt = {
                "algorithm": "awa-registration-v5-acceptance-body/v1",
                **artifacts,
                "completed_wall_ns": "1",
                "domain": "awa-registration-v5-acceptance-body/v1",
                "immutable_anchors": anchors,
                "normalized_digest": recovery["normalized_digest"],
                "owner_acceptance_digest": "77" * 32,
                "recovery_vector": recovery,
                "recovery_vector_digest": module.domain_hash("awa-registration-v5-recovery-vector/v1", recovery),
                "repository": "KleinPerkins/awa",
                "schema": "awa-registration-v5-acceptance-promotion/v2",
                "sentinel": "__AWA_V5_ACCEPTED_STATUS_TOKEN_V1__",
                "source_commit": module.BASE_COMMIT,
            }
            receipt["receipt_hash"] = module.domain_hash("awa-registration-v5-acceptance-promotion/v2", receipt)
            acceptance = state / module.ACCEPTANCE_RELATIVE_PATH
            private = state
            for component in pathlib.PurePosixPath(module.ACCEPTANCE_RELATIVE_PATH).parent.parts:
                private = private / component
                private.mkdir(exist_ok=True, mode=0o700)
                os.chmod(private, 0o700)
            write_exact(acceptance, module.jcs(receipt) + b"\n", 0o600)
            packet_document = module.build_packet(
                repo_root=repo, state_home=state, plan_path=plan,
                receipt_path=acceptance, public_path=public_path,
                created_wall_ns="2", launch_tool_hash=artifacts["bootstrap_sha256"],
            )
            vectors.append("BUILD_PACKET")
            packet_path = root / "packet.json"
            write_exact(packet_path, module.jcs(packet_document) + b"\n", 0o600)
            packet = packet_document["packet"]
            packet_hash = packet_document["packet_sha256"]
            authority = {
                "schema": "awa-registration-owner-key-bootstrap-publication-go/v1",
                "repository": "KleinPerkins/awa",
                "authorized_by": "KleinPerkins",
                "action": "PUBLISH_INITIAL_OWNER_ENROLLMENT",
                "bootstrap_context": module.bootstrap_context(packet, packet_hash),
                "authorized": True,
                "denied_implications": list(module.DENIED_IMPLICATIONS),
            }
            authority_path = root / "authority.json"
            write_exact(authority_path, module.jcs(authority) + b"\n", 0o600)
            options = {
                "plan": str(plan), "acceptance-receipt": str(acceptance),
                "packet": str(packet_path), "authority": str(authority_path),
                "public-key": str(public_path),
            }
            def read_race(target, function, kind, api):
                target = pathlib.Path(target)
                original_mode = stat.S_IMODE(target.lstat().st_mode)
                original_raw = target.read_bytes()
                original_read = api.read
                original_fstat = api.fstat
                target_inode = target.lstat().st_ino
                fired = False
                link_path = target.with_name(target.name + ".race-link")
                backup_path = target.with_name(target.name + ".race-backup")
                fstat_count = 0
                def racing_read(fd, size):
                    nonlocal fired
                    chunk = original_read(fd, size)
                    try:
                        matching = original_fstat(fd).st_ino == target_inode
                    except OSError:
                        matching = False
                    if chunk and matching and not fired:
                        fired = True
                        if kind == "chmod":
                            os.chmod(target, 0o600 if original_mode == 0o644 else 0o644)
                        elif kind == "hardlink":
                            os.link(target, link_path)
                        elif kind == "substitute":
                            os.replace(target, backup_path)
                            write_exact(target, original_raw, original_mode)
                    return chunk
                def racing_fstat(fd):
                    nonlocal fstat_count, fired
                    metadata = original_fstat(fd)
                    if metadata.st_ino == target_inode:
                        fstat_count += 1
                        if kind == "chown" and fstat_count >= 2:
                            fired = True
                            values = list(metadata)
                            values[4] = metadata.st_uid + 1
                            return os.stat_result(values)
                    return metadata
                api.read = racing_read
                api.fstat = racing_fstat
                try:
                    expect_error(function, "post-read " + kind + " race " + target.name)
                    check(fired, "race did not fire: " + kind + " " + target.name)
                finally:
                    api.read = original_read
                    api.fstat = original_fstat
                    if kind == "chmod" and target.exists():
                        os.chmod(target, original_mode)
                    if link_path.exists():
                        link_path.unlink()
                    if backup_path.exists():
                        if target.exists():
                            target.unlink()
                        os.replace(backup_path, target)
                        os.chmod(target, original_mode)

            read_race(
                public_path,
                lambda: module.read_bounded_descriptor(
                    public_path, module.MAX_PUBLIC_BYTES, {0o600, 0o644}
                ),
                "chmod", module.os,
            )
            read_race(
                packet_path, lambda: module.load_packet(packet_path),
                "hardlink", module.os,
            )
            read_race(
                authority_path,
                lambda: module.load_authority(
                    authority_path, packet, packet_hash
                ),
                "substitute", module.os,
            )
            read_race(
                acceptance,
                lambda: module.acceptance_receipt(
                    acceptance, plan, artifacts["bootstrap_sha256"]
                ),
                "chown", module.os,
            )
            read_race(
                plan,
                lambda: module.acceptance_receipt(
                    acceptance, plan, artifacts["bootstrap_sha256"]
                ),
                "substitute", module.os,
            )
            read_race(
                packet_path,
                lambda: module.v_read_descriptor(
                    packet_path, module.MAX_JSON_BYTES, {0o600, 0o644}
                ),
                "chmod", module.os,
            )
            synthetic_state_input = root / "synthetic-state-input"
            write_exact(synthetic_state_input, b"exact-state\n", 0o600)
            read_race(
                synthetic_state_input,
                lambda: module.p_read_state(
                    synthetic_state_input, b"exact-state\n", 0o600
                ),
                "hardlink", module.os,
            )
            read_race(
                synthetic_state_input,
                lambda: module.p_read_state(
                    synthetic_state_input, b"exact-state\n", 0o600
                ),
                "substitute", module.os,
            )
            checker_root_fd = os.open(
                checker_repo, os.O_RDONLY | os.O_DIRECTORY
            )
            try:
                checker_plan = checker_repo / "docs/plans/native-entry-durable-registration-v5.md"
                read_race(
                    checker_plan,
                    lambda: checker.read_relative(
                        checker_root_fd,
                        "docs/plans/native-entry-durable-registration-v5.md",
                    ),
                    "chmod", checker.os,
                )
            finally:
                os.close(checker_root_fd)
            checker_external = root / "checker-external.json"
            write_exact(checker_external, b"{}\n", 0o600)
            checker_external = checker_external.resolve()
            read_race(
                checker_external,
                lambda: checker.read_external_input(str(checker_external)),
                "hardlink", checker.os,
            )
            vectors.extend([
                "POST_READ_PUBLIC_CHMOD_RACE",
                "POST_READ_PACKET_HARDLINK_RACE",
                "POST_READ_AUTHORITY_VISIBLE_SUBSTITUTION",
                "POST_READ_RECEIPT_CHOWN_RACE",
                "POST_READ_PLAN_VISIBLE_SUBSTITUTION",
                "POST_READ_VALIDATOR_CHMOD_RACE",
                "POST_READ_CONTRACT_HARDLINK_RACE",
                "POST_READ_CURRENT_VISIBLE_SUBSTITUTION",
                "POST_READ_CHECKER_PLAN_CHMOD_RACE",
                "POST_READ_CHECKER_EXTERNAL_HARDLINK_RACE",
            ])
            module.acceptance_receipt(acceptance, plan, artifacts["bootstrap_sha256"])
            module.v_load_acceptance(acceptance, plan, artifacts["bootstrap_sha256"])
            vectors.extend(["ACCEPTANCE_LOAD_PUBLISHER", "ACCEPTANCE_LOAD_VALIDATOR"])
            expect_error(lambda: module.v_validate(
                packet_path=packet_path, authority_path=authority_path,
                acceptance_path=acceptance, plan_path=plan,
                public_path=public_path, launch_tool_hash=artifacts["bootstrap_sha256"],
            ), "prepublication independent validate")
            vectors.append("VALIDATE_PREPUBLICATION_DENIAL")
            module.p_validate_packet_for_mutation(
                packet_path, authority_path, acceptance, plan, public_path,
                artifacts["bootstrap_sha256"],
            )
            vectors.append("MUTATION_AUTHORITY_VALIDATE")
            contract_path = repo / module.CONTRACT_RELATIVE_PATH
            residue = contract_path.parent / module.p_residue_name(
                contract_path, packet_hash
            )
            write_exact(residue, contract_raw, 0o644)
            pristine_authority_raw = module.jcs(authority) + b"\n"
            pristine_packet_raw = module.jcs(packet_document) + b"\n"
            def action_call(mode_name, action_value=None):
                call_options = dict(options)
                if action_value is not None:
                    call_options["recovery-action"] = action_value
                return lambda: module.p_mutate(
                    mode_name, call_options, artifacts["bootstrap_sha256"]
                )
            def unchanged_refusal(function, label):
                before_action = tree_snapshot(repo) + tree_snapshot(state)
                expect_error(function, label)
                after_action = tree_snapshot(repo) + tree_snapshot(state)
                check(before_action == after_action, label + " mutated exact residue")
            unchanged_refusal(action_call("recover"), "recover missing action")
            unchanged_refusal(action_call("recover", "unknown"), "recover unknown action")
            unchanged_refusal(action_call("publish", "forward"), "publish wrong-mode action")
            for authority_label, changed in [
                ("missing", {key: value for key, value in authority.items() if key != "action"}),
                ("unknown", {**authority, "action": "UNKNOWN"}),
                ("wrong-mode", {**authority, "action": "RECOVER_FORWARD"}),
            ]:
                write_exact(authority_path, module.jcs(changed) + b"\n", 0o600)
                unchanged_refusal(action_call("publish"), "publish authority " + authority_label)
                unchanged_refusal(action_call("recover", "forward"), "recover authority " + authority_label)
            write_exact(authority_path, pristine_authority_raw, 0o600)
            reordered_packet = {
                **packet,
                "authorized_recovery_actions": list(reversed(packet["authorized_recovery_actions"])),
            }
            reordered_document = {
                "packet": reordered_packet,
                "packet_sha256": module.domain_hash(
                    "awa-registration-owner-key-bootstrap-packet/v1", reordered_packet
                ),
            }
            write_exact(packet_path, module.jcs(reordered_document) + b"\n", 0o600)
            unchanged_refusal(action_call("publish"), "publish reordered action authority")
            unchanged_refusal(action_call("recover", "forward"), "recover reordered action authority")
            write_exact(packet_path, pristine_packet_raw, 0o600)
            check(residue.exists() and not contract_path.exists(), "invalid action residue drift")
            residue.unlink()
            vectors.extend([
                "RECOVER_MISSING_ACTION_ZERO_MUTATION",
                "RECOVER_UNKNOWN_ACTION_ZERO_MUTATION",
                "PUBLISH_WRONG_MODE_ACTION_ZERO_MUTATION",
                "PUBLISH_AUTHORITY_MISSING_ACTION_ZERO_MUTATION",
                "RECOVER_AUTHORITY_MISSING_ACTION_ZERO_MUTATION",
                "PUBLISH_AUTHORITY_UNKNOWN_ACTION_ZERO_MUTATION",
                "RECOVER_AUTHORITY_UNKNOWN_ACTION_ZERO_MUTATION",
                "PUBLISH_AUTHORITY_WRONG_MODE_ZERO_MUTATION",
                "RECOVER_AUTHORITY_WRONG_MODE_ZERO_MUTATION",
                "PUBLISH_REORDERED_ACTION_ZERO_MUTATION",
                "RECOVER_REORDERED_ACTION_ZERO_MUTATION",
            ])
            prepared = module.p_prepare_state_parent(state)
            check(prepared == state / "awa/registration-owner-key", "state parent")
            vectors.append("STATE_PARENT_PREPARE")
            published = module.p_mutate("publish", dict(options), artifacts["bootstrap_sha256"])
            check(published["final_state"] == "EXACT_CONTRACT/EXACT_RECEIPT", "publish state")
            vectors.append("PUBLISH_ABSENT_ABSENT")
            # Measured syscall guard: independent validator may open/read/stat only.
            guarded = ["write", "pwrite", "mkdir", "chmod", "fchmod", "link", "unlink", "rename", "replace", "fsync", "fdatasync", "symlink"]
            originals = {name: getattr(module.os, name) for name in guarded if hasattr(module.os, name)}
            opens = 0
            original_open = module.os.open
            def guarded_open(path, flags, *args, **kwargs):
                nonlocal opens
                if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
                    fail("validator attempted write-capable open")
                opens += 1
                return original_open(path, flags, *args, **kwargs)
            def forbidden(*args, **kwargs):
                fail("validator attempted mutating syscall")
            module.os.open = guarded_open
            for name in originals:
                setattr(module.os, name, forbidden)
            try:
                validation = module.v_validate(
                    packet_path=packet_path, authority_path=authority_path,
                    acceptance_path=acceptance, plan_path=plan,
                    public_path=public_path, launch_tool_hash=artifacts["bootstrap_sha256"],
                )
            finally:
                module.os.open = original_open
                for name, value in originals.items():
                    setattr(module.os, name, value)
            check(validation["valid"] is True and opens > 0, "validator enforcement")
            vectors.append("VALIDATOR_SYSCALL_READ_ONLY_MEASURED")
            exact = module.p_mutate("publish", dict(options), artifacts["bootstrap_sha256"])
            check(exact["outcome"] == "EXACT_EXISTING_DURABLE", "exact durability")
            vectors.append("EXACT_EXISTING_DURABILITY")
            contract_path = repo / module.CONTRACT_RELATIVE_PATH
            current_path = state / module.CURRENT_RELATIVE_PATH
            current_raw = base64.b64decode(packet["current_output"]["payload_b64"], validate=True)
            # Rollback keeps the contract descriptor held and proves link-count zero.
            current_path.unlink()
            recover_options = {**options, "recovery-action": "rollback-contract-only"}
            rolled = module.p_mutate("recover", recover_options, artifacts["bootstrap_sha256"])
            check(rolled["final_state"] == "ABSENT_CONTRACT/ABSENT_RECEIPT", "rollback state")
            vectors.append("ROLLBACK_HELD_INODE")
            write_exact(contract_path, contract_raw, 0o644)
            recover_options["recovery-action"] = "forward"
            forwarded = module.p_mutate("recover", recover_options, artifacts["bootstrap_sha256"])
            check(forwarded["final_state"] == "EXACT_CONTRACT/EXACT_RECEIPT", "forward state")
            vectors.append("RECOVER_FORWARD")
            # Reset to orphan receipt plus exact contract residue: must be zero mutation.
            contract_path.unlink()
            residue = contract_path.parent / module.p_residue_name(contract_path, packet_hash)
            write_exact(residue, contract_raw, 0o644)
            before = tree_snapshot(repo) + tree_snapshot(state)
            expect_error(lambda: module.p_mutate("publish", dict(options), artifacts["bootstrap_sha256"]), "orphan receipt plus contract residue")
            after = tree_snapshot(repo) + tree_snapshot(state)
            check(before == after, "orphan receipt path mutated")
            vectors.append("ORPHAN_RECEIPT_CONTRACT_RESIDUE_ZERO_MUTATION")
            # Restore absent/absent with exact contract residue for residue fault cuts.
            current_path.unlink(); residue_inode = residue.stat().st_ino
            original_fsync = module.os.fsync
            def fail_residue_fsync(fd):
                if os.fstat(fd).st_ino == residue_inode:
                    raise OSError("synthetic residue fsync")
                return original_fsync(fd)
            module.os.fsync = fail_residue_fsync
            try:
                expect_error(lambda: module.p_mutate("publish", dict(options), artifacts["bootstrap_sha256"]), "residue file fsync")
            finally:
                module.os.fsync = original_fsync
            check(not contract_path.exists() and residue.exists(), "fsync fault published authority")
            vectors.append("RESIDUE_FILE_FSYNC_FAILURE")
            original_read = module.os.read; residue_reads = 0
            def fail_residue_reread(fd, size):
                nonlocal residue_reads
                if os.fstat(fd).st_ino == residue_inode:
                    residue_reads += 1
                    if residue_reads == 2:
                        return b"corrupt"
                return original_read(fd, size)
            module.os.read = fail_residue_reread
            try:
                expect_error(lambda: module.p_mutate("publish", dict(options), artifacts["bootstrap_sha256"]), "residue reread")
            finally:
                module.os.read = original_read
            check(not contract_path.exists() and residue.exists(), "reread fault published authority")
            vectors.append("RESIDUE_REREAD_FAILURE")
            original_stat = module.os.stat; residue_stats = 0
            def fail_residue_rebind(path, *args, **kwargs):
                nonlocal residue_stats
                if path == residue.name:
                    residue_stats += 1
                    if residue_stats == 2:
                        raise OSError("synthetic residue rebind")
                return original_stat(path, *args, **kwargs)
            module.os.stat = fail_residue_rebind
            try:
                expect_error(lambda: module.p_mutate("publish", dict(options), artifacts["bootstrap_sha256"]), "residue rebind")
            finally:
                module.os.stat = original_stat
            check(not contract_path.exists() and residue.exists(), "rebind fault published authority")
            vectors.append("RESIDUE_REBIND_FAILURE")
            # Exception preservation: bare raise keeps object and traceback; every close is attempted.
            primary = module.BootstrapError("primary")
            original_close = module.os.close
            close_calls: list[int] = []
            def close_fault(fd):
                close_calls.append(fd)
                raise OSError("synthetic close " + str(fd))
            module.os.close = close_fault
            try:
                primary_traceback = None
                try:
                    try:
                        raise primary
                    except BaseException as error:
                        primary_traceback = error.__traceback__
                        cleanup = module.close_owned_descriptors(
                            987651, 987652, 987653, primary=error
                        )
                        check(cleanup is error.__context__, "bootstrap cleanup context")
                        check(error.__traceback__ is primary_traceback, "bootstrap traceback changed during cleanup")
                        raise
                except BaseException as error:
                    check(error is primary, "bootstrap primary identity")
                    check(error.__traceback__ is primary_traceback, "bootstrap bare-raise traceback identity")
                    check(isinstance(error.__context__, OSError), "bootstrap cleanup association")
                check(close_calls == [987651, 987652, 987653], "bootstrap all-close attempts")
                try:
                    module.close_owned_descriptors(987654)
                except OSError:
                    pass
                else:
                    fail("lone close fault suppressed")
            finally:
                module.os.close = original_close
            vectors.extend([
                "PRIMARY_OBJECT_IDENTITY",
                "PRIMARY_TRACEBACK_IDENTITY",
                "SECONDARY_CLEANUP_ASSOCIATION",
                "ALL_CLOSE_ATTEMPTS",
                "LONE_CLOSE_FAILURE",
            ])
    finally:
        sys.settrace(None)
    missing = sorted(production - called)
    if missing:
        fail("uncovered production functions: " + ",".join(missing))
    vectors.extend(["CALL_GRAPH_COVERAGE", "SYSCALL_COVERAGE"])
    result = {
        "schema": "awa-v5-bootstrap-fault-harness/v1",
        "result": "PASS",
        "vector_count": str(len(vectors)),
        "vectors": vectors,
        "covered_production_functions": sorted(production),
        "covered_function_count": str(len(production)),
        "checker_descriptor_producer_count": str(len(checker_producers)),
        "validator_mutating_syscalls_observed": "0",
        "synthetic_roots_only": True,
        "production_paths_touched": False,
    }
    sys.stdout.buffer.write(jcs(result) + b"\n")


main()
```
<!-- awa-v5-bootstrap-fault-harness:v1:end -->

The tool is Python-standard-library only, contains no validation `assert`, and
exposes exactly `packet`, `validate`, `publish`, `recover`, and `self-test`.
Draft self-tests use synthetic temporary roots only. Production modes require
a future exact accepted-v5 receipt, packet, public descriptor, and Gate 3B
authority; none exists or is synthesized by this draft.

##### Closed audit invariants for acceptance and bootstrap

The acceptance packet has one canonical authority source: the exact
`owner_acceptance_envelope`. Its recovery vector exclusively carries launcher,
checker, bootstrap, harness, immutable-anchor, normalized-plan, and ordered
surface values. Top-level packet fields contain only schema, the derived owner
digest, that envelope, and owner language derived byte-for-byte from that same
envelope. Generation, strict JCS parsing, owner-language parsing, and
`recover-pre` preflight MUST round-trip; missing, extra, duplicate, mistyped,
out-of-order, or semantically mismatched input refuses.

`publish` accepts no recovery action. `recover` requires exactly one
`forward` or `rollback-contract-only` action. Unknown mode, missing/unknown
action, a publish/recover mode-action mismatch, any Gate 3B action mismatch, or
reordered authorized actions MUST refuse before lock acquisition, private-state
parent creation, residue reconciliation, fsync, or any other mutation. An exact
contract residue in ABSENT/ABSENT remains byte- and inode-identical on every
such refusal.

Every authority-bearing file read in checker, publisher, and independent
validator compares the complete pre-open/opened/post-read/visible-name tuple:
regular type, device, inode, size, `mtime_ns`, owner UID, exact mode, and link
count. The held inode and final visible name MUST remain identical. Chmod,
chown, hardlink, or visible-name substitution at any cut refuses, including
public input, packet, authority, acceptance receipt, plan/artifact extraction,
contract/current state, and checker external input.

Cleanup never re-raises a primary exception from a helper frame. The caller
catches the primary, attempts every owned close exactly once, attaches the first
cleanup failure as secondary context, and uses bare `raise`; primary object and
traceback identities remain exact. A lone cleanup failure still surfaces.

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

V5-S1 additionally permits only §4.1.1's enumerated compatibility seam; those exact Body B call sites/tests remain Body B-owned for every other purpose.

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

V5-S1 does not transfer any other runtime behavior, admission, basis, view, recovery, fairness, or parser ownership to Body A.

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

Before any body's Gate 4, Body C's enrollment-bootstrap substage follows §4.2.2 Gates 3A–3C. The embedded documentation artifact is its sole pre-delivery publisher/validator authority; it adds no fourth body and no ordinary runtime path.

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
| A22 | Candidate digest unchanged; hash-checked v5 acceptance checker/launcher/bootstrap payload, exact source/recovery packet and successor hunk ledger, immutable v4/ADR anchors, hash+mode state classification, held-candidate two-surface promotion, two-POST canonical receipt, receipt-first idempotency, semantic envelope, immediate descriptor ownership and return-only transfer; every §4.2.1 interpreter/probe/bundle/deployment preimage/vector; import JCS+LF payload equality; signing trust; immutable proof; staged C5 custody; R1/R2 scope | C | P1-01, P1-02, P1-06, P1-07, P1-08, P1-09, P1-10; P2-06; P3-02 |
| A23 | Fail-open/exhaustion evidence truth; interpreter substitution/drift/upgrade and transitive import/shadow corpus; deterministic classified target/residue pairs, stale-snapshot rejection, primary-error/residue honesty, all-descriptor cleanup and exact-primary preservation; finite R0 vectors | C | P1-05 provider; P1-07, P1-12, P2-06; P3-01, P3-02 |
| A24 | One status row/member and READY only after selected closure, fresh profile/interpreter capability, signed bundle/import manifest, and unique inventory | B | P1-03/P1-07 provider |
| A25 | Deterministic rendering; deep malformed JSON yields bounded parser denial; no presentation state | B | P2-02 |
| A26 | Dirty/in-progress bytes unchanged; exact duplicate no-op and fresh-under-lock basis add no preservation behavior | B | P2-05 |
| A27 | Five-second drain; SQL-v2 recovery; two-ack custody; exact ADOPT/DRAINING-REACQUIRE C5 closure; advance/CANCEL/containment | A | P1-05; P1-09/P1-10 provider |
| A28 | Close/successor/reacquire/adopt resolvers remain monotonic across later valid state and all fault classes | A | P2-04 |
| A29 | ADR 0020 alert authority and guard/finish/cleanup/active-root/kernel-off independence remain byte/behavior compatible | C | Retained |
| A32 | Low-free and recovery-exhaustion zero write; native FULL/IOERR resolution; typed unavailable vs adapter containment; pre/post-rename and residue honesty | A | P1-03, P1-05; P2-06 provider |

### V5 sequencing acceptance addendum

| ID | Required evidence | Owner | Stop condition |
|---|---|---|---|
| V5-S1 | Exact two `_intent` outcomes and clean/blocked fixture outcomes are 98,304; clean/blocked external, successor, actions, hashes, APIs, imports, and every non-seam Body B byte/behavior remain governed by Body B; focused functional plus structural proof | A | Any broader runtime edit, other 64 KiB change, weakened independence test, or SQL-floor bypass |
| V5-S2 | External launcher/tool hashes; normal/optimized synthetic self-test identity; strict public grammar; exact packet/context/decision; only three primary states; contract-first/receipt-last crash matrix; same-authority recovery; immutable Gate 2A digest; independent zero-write Gate 3C; real enrollment hash before Gate 4 | C | Any self-authorization, hash cycle, new owner digest, orphan cleanup, receipt rollback, shared validator builder, production self-test path, or fourth body |

No A30 or A31 exists. C1 is absent from owner/provider columns by design.

## 7. Verification, review, and evidence cadence

### 7.1 V5 exact-byte document acceptance

V5 acceptance is independent from accepted v4/ADR acceptance. Immutable hash
anchors are complete accepted-v4 bytes, complete accepted ADR 0026 bytes, and
the exact accepted ADR index row. None is promotable or writable.

The only v5 promotion surfaces are:

1. `docs/plans/native-entry-durable-registration-v5.md`: replace only
   `DRAFT (for review)` in the exact status bullet with `ACCEPTED — FROZEN`;
2. `docs/plans/README.md`: replace only `DRAFT` in the exact v5 row with
   `ACCEPTED`.

The v4 index row remains unchanged under this acceptance. Any later
`SUPERSEDED BY V5` v4 index status requires separate index-only authority.

Normalization uses domain
`awa-registration-v5-acceptance-body/v1`, sentinel
`__AWA_V5_ACCEPTED_STATUS_TOKEN_V1__`, unsigned 64-bit big-endian path/body
lengths, and exact promotable path order: exact v5 index row, then complete v5
plan. Immutable ADR 0026, accepted v4, the ADR 0026 index row, and the v4 plan
index row are separately hash-bound anchors and never enter replacement
logic. Each v5 surface replaces only its one selected status token with the
sentinel. Strict UTF-8/LF, one terminal LF, no CR/NUL, exact old/new context,
and canonical mode `0644` are mandatory.

The exact packet emitted by the embedded canonical checker binds source
commit, immutable hashes, exact
ADMIN/V5-S1/V5-S2 hunk ledger, pre/post hashes for both promotable surfaces,
normalized digest, acceptance-checker hash, launcher hash
`9a17cd51bb88e07fa640e42b63386ac2c336fbcfceafdeaee5a0cf0cb5774289`, checker hash `89463fe0da9bc945aff654ca199d50fc736f25212272613d86628019210a5714`, tool hash `5ab017188cc03f58663f44eda85cc7f59b4717e1e7d939ccbe9d64fcfc071399`, harness hash `2f12d26b6d4c5f3fc12a36ade14ee2c118e054cb0a1cb42610765d1f8de64ef2`, exact denied implications, owner
acceptance digest, and receipt path. Promotion is status-last and publishes
one detached receipt only after both POST surfaces and immutable anchors
revalidate. Crash recovery uses only packet-bound pre/post bytes; it never
rebases or edits v4/ADR.

The detached receipt schema is
`awa-registration-v5-acceptance-promotion/v2` with exactly:

```text
schema, repository, source_commit, checker_sha256, launcher_sha256,
bootstrap_sha256, harness_sha256, immutable_anchors,
recovery_vector = awa-registration-v5-recovery-vector/v1,
recovery_vector_digest, algorithm, domain, sentinel, normalized_digest,
owner_acceptance_digest, completed_wall_ns, receipt_hash
```

`receipt_hash` is the domain-separated JCS hash excluding itself. Exact JCS
plus LF, `0600`, owner UID/link-one, `0700` parents, descriptor-safe
publication, file/parent fsync, and post-fsync revalidation are mandatory.
Missing/malformed/stale/mixed authority is NO-GO. V5 acceptance authorizes
only its two status-token transitions and detached receipt; it does not
publish enrollment, implement, deliver, sign, run R0, release, install,
activate, or roll out.

### 7.2 Tests-first cadence

Before body delivery, V5-S1 and V5-S2 require their complete addendum evidence. Bootstrap tool review occurs first with synthetic inputs only; later Gate 3A reviews the exact real public descriptor, explicit timestamp, receipt preimage, packet, and hashes without publication.

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

V5 adds: payload/launcher hash substitution; normal versus `-O`; malformed public grammar/wire/base64; all three known states and every refused pair; contract/receipt write-link-fsync-rebind cuts; exact/unknown residues; forward/rollback recovery under same Gate 3B; any-receipt rollback denial; packet/context/decision acyclicity; immutable Gate 2A; zero-write packet/validate; and independent validator call-graph mutation kills.

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
  wrong mode, and unexpected entry refusal; crash before/after both
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
v5 exact-byte technical clearance, including launcher/tool review
-> explicit owner acceptance of exact v5 only
-> checked two-surface v5 promotion + detached acceptance receipt
-> unchanged accepted Gate 2A evidence
-> implementation Gate 3 continuity/reconfirmation for exact v5/base
-> later canonical public descriptor + explicit created_wall_ns
-> exact receipt preimage/enrollment hash + packet/hash
-> exact Gate 3A packet review; no publication
-> exact Gate 3B publication GO naming packet/context/output hashes
-> publish contract, then receipt-last authority commit
-> independent read-only Gate 3C yields real enrollment hash
-> per-body Gate 4 naming accepted v5 digest and that enrollment hash
-> inherited Gates 5–13 in accepted-v4 order
```

No gate implies another. Enrollment publication does not imply Git delivery,
signing, R0, release, installation, activation, or rollout.

## 8. Owner decisions

### Gate 1 — v5 exact-byte technical clearance

Requires immutable v4/ADR hashes, exact successor hunk ledger, final v5/index
hashes, launcher/tool hashes, normal/optimized self-tests, static proof, and
independent review with no blocker. It uses synthetic public data only.

### Gate 2 — exact v5 document acceptance

The owner names the exact v5 normalized digest, checker/launcher/tool hashes,
and two-surface vector. Promotion may change only the v5 status bullet and v5
index row, then publish the detached v5 acceptance receipt. V4, ADR 0026, and
the v4 index row remain unchanged. This authorizes no implementation or
enrollment publication.

### Gate 3 — implementation GO or continuity/reconfirmation

Against exact accepted v5 digest and exact implementation base, the owner must
either issue fresh local-only implementation GO or explicitly continue prior
v4 local-only authority. It authorizes no commit, push, PR, delivery,
enrollment publication, R0, release, installation, activation, or rollout.

### Gate 3A — exact enrollment packet review

After the later canonical public descriptor and explicit `created_wall_ns`
are fixed, independent review names the exact accepted-v5 receipt/digest,
tool hash, public descriptor/identity, contract/current payload hashes,
enrollment hash, packet hash, paths, modes, and expected absent/contract-only
state. Gate 3A authorizes no write.

### Gate 3B — exact enrollment publication GO

The owner supplies exact canonical
`awa-registration-owner-key-bootstrap-publication-go/v1` bytes naming the
already-reviewed packet hash and complete bootstrap context. Its authorized
actions are only initial publish, exact contract-only forward recovery, and
exact contract-only rollback. Its denied implications are private-key/signing
access, Git delivery, implementation delivery, R0/R1/C1/R2, release,
installation, activation, and rollout. The decision digest is outside the
packet/context.

### Gate 3C — independent post-publication validation

A fresh process runs the independent read-only validator under ordinary and
optimized Python. Both outputs must byte-match and bind actual contract bytes,
current-receipt bytes, immutable Gate 2A digest, packet, Gate 3B decision,
and real current `enrollment_hash`, with zero write syscalls. Gate 3C is
evidence only and authorizes nothing.

### Gate 4 — per-body implementation-delivery GO

Required separately for each existing Body A, B, and C. It retains accepted
v4's exact template but must name the accepted v5 normalized digest and the
Gate 3C-validated current enrollment hash. No Body may pass Gate 4 earlier.
Gate 4 still authorizes only commit, push, and one Draft PR for that exact
body/base/branch; no readiness, merge, signing, R0, release, installation,
activation, or rollout.

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
GO to run v5 R0 against <exact-merged-head> in the throwaway harness only,
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
head, A01–A29/A32 plus V5-S1/V5-S2 results, `partial_rollout=false`, and
passing fresh verifier shipping clearance. It grants no mutation or rollout
authority.

### Gate 13 — R2 rollout GO

Only after C1 and fresh shipping clearance:

```text
GO for R2 DIRECT rollout using <owner-gate-digest> at
<exact-implementation-head>.
```

No current gate is satisfied by this draft. No gate implies another.

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

The enrollment bootstrap adds no fourth body, product runtime path, rotation/revocation workflow, key-possession proof, signing action, network service, or broader same-UID guarantee. Public-key bytes, explicit timestamp, packet, Gate 3B decision, and enrollment hash are future exact gate inputs, not draft placeholders.

## 10. Current NO-GO

V5 is a documentation-only draft. Accepted v4 and ADR 0026 remain current and
immutable. No accepted-v5 receipt, production public input, explicit
publication timestamp, exact packet, Gate 3A evidence, Gate 3B decision,
contract, current receipt, Gate 3C validation, or qualifying Gate 4 exists.

Until each exact gate passes, leave code, tests, contracts, machine-local
state, keys, signatures, Git metadata, accepted/frozen authorities, R0/R1,
release, installation, Skills, host wiring, C1, R2, and rollout unchanged.
