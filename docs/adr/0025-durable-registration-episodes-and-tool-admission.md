# ADR 0025: Durable native-entry registration before intercepted tools
Status: accepted — 2026-09-26 (C0-DESIGN NO-GO)

This is a proposed successor to
[ADR 0024](0024-first-prompt-native-entry-recovery.md). ADR 0024 remains
authoritative while this record is draft. This record authorizes no
implementation, PR mutation, release, installation, host wiring, or live
state change.

The candidate execution authority is
[`native-entry-durable-registration-v3.md`](../plans/native-entry-durable-registration-v3.md).
Draft v3 supersedes draft v2 as the only candidate plan. Draft v2 remains
byte-identical at SHA-256
`03aff346283c2809d9bab392120972de97bd14b5879e01448a8af734becf8b9b`.

## Context

PR #175 at `b88325768f26f8d98aecb2722d5fb253379bba47`
provides ADR 0024's eager/first-prompt substrate. It does not prove durable
registration before each later Agent tool.

The rejected v2 candidate made Rescue, physical garbage collection,
per-mutation capability graphs, production custom-VFS work, and tentative
child-agent support prerequisites. The consolidated v3 candidate instead
proves only:

> When functioning AWA receives a complete event containing exactly one
> positively identified, clean, eligible local linked non-primary worktree,
> it durably registers that physical member and conversation before allowing
> any supported ordinary intercepted Agent tool. Every unknown or non-green
> result denies that invocation when the receiving hook is functioning.
> Task/subagent launch is default-denied in M1.

“Functioning” excludes missing/not-invoked hooks, no-event surfaces, broken
wrapper startup/output, unsupported platforms, store-unavailable paths, and
total runtime/host absence. Those paths fail open and remain honest
unsupported residuals. Guard, finish, cleanup, active-root, and integrity
authorities remain independent.

The latest complete reviewer run examined:

```text
ADR  787b8902b0204cc805a33e230cc8354a586c7a702307a61975957705262530ae
plan 6e3336f8596d2186858682d3b9561f7ea97a27079516fe8e956f585b795f3017
base b88325768f26f8d98aecb2722d5fb253379bba47
```

Revision matching succeeded. Fresh reliability plus its critical probe and
the concurrency, data/schema, security, and architecture reviews were valid.

A later verifier record targeted ADR
`e8fb08caa1aad8e1f71adb33550b8933c3322c5144904948d94d17b70ef78a98`,
plan
`ffba2909a3ca7a0f753bb66fa6009467e8f6500b9b1b56fe3c8d94e4c79de84f`,
and schema
`adae0baa7afe7f8343c58b968832d7551a0125b6cd211695c6bf13d4cbab18da`.
The repository validator, with its historical six candidate ids and
accepted-risk array `[]`, exited `2` because the return omitted required keys
`no_finding_evidence` and `residual_uncertainty`. The return is invalid and
provides no clearance. Those historical ids are superseded for final
dispatch by v3 §7.2's six coherent P1 groups.
This rewrite authors design dispositions; it does not self-clear them. The
record's failed shipping clearance and incomplete-implementation
`partial_rollout` are expected before implementation and are not C0 evidence
or deployment-reach claims.

Two later valid reviewer returns examined exact predecessor hashes ADR
`f7ec08980cfd6bf4ef30cdda9abb899b62d20e41b6131b2a07bb90af8caf0954`,
plan
`5c5f387fe5060df756310f376c39ca31b2de2c26c7609fc9821fb8e4f1d085b6`,
and schema
`09c74656d9607b2ecdbc40a619bd4e89e67f5b2be6ed4b19763a524def3f43ee`;
they source-confirmed this wave's ten roots. They do not review the rewritten
bytes and provide no clearance.

Two corrected schema-valid returns then examined ADR
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
It source-confirmed sixteen roots but does not review the rewritten bytes or
clear C0.

The subsequent schema-valid narrow verifier examined ADR
`cefca40f93e80832966bbb599512df6cf09d033620d0643fb9818ef469cd4196`,
plan
`d3e25587b88e185516a1d67a69b18c102066add4abcd7100d72cee31bc134b4c`,
schema
`99896d2ec8d937d37dd9b4512ced0ae5a92f150453a7f2ba1729a584e25cdefa`,
and normalized body
`ad0795b76eee70b36b5f5229f1991aa540832f27c7b280d3ae1875f9b648ff04`.
It verified four groups and left the protocol-drain plus independent-leaf
groups open solely on the half-null drain-tuple defect corrected here. It
does not review the corrected hashes.

## Decision

### 1. M1 is single-root clean-entry registration

M1 accepts only a complete `workspace_roots` array of length one whose sole
entry resolves without alias ambiguity to an attached, local,
policy-eligible linked worktree that is not primary. Missing, empty,
multi-root, partial, mixed, primary, excluded, detached, nonlocal, aliased,
ambiguous, or unsupported input denies the whole invocation. M1 never
chooses the root nearest `cwd` or reduces a larger set.

An immutable episode records conversation/event provenance, the exact
single-root envelope hash, installed tool-inventory and hook-projection
hashes, and one member foreign key. The canonical member basis contains only
physical identity, Git topology and operation safety, policy eligibility,
and lifecycle closure. Conversation, episode, event source/generation,
protocol generation, and root-set facts never enter member identity or
current basis.

Before member and episode identity both exist, denial is one fixed bounded
stateless response. No durable notice or counter exists. Dirty or in-progress
roots are non-mutating NO-GO: AWA records only redacted reason/fingerprint,
sets no unchanged-basis timer, and directs the operator to the existing
governed preservation flow and a clean linked target.

### 2. One exact seven-table authority owns truth

The dedicated private database remains:

```text
${XDG_STATE_HOME}/awa/registration-v1/registration.db
```

The closed authority is exactly:

1. append-only `registration_protocol_epoch`, whose maximum sequence selects
   current protocol and immutable staged epoch;
2. canonical mutable `registration_member`;
3. immutable one-member `registration_episode`;
4. `registration_effect`, combining immutable request identity/intent with
   one irreversible NULL-to-closed outcome;
5. append-only semantic `registration_effect_action`;
6. bounded mutable member-only `registration_runtime_status`; and
7. append-only transaction-scoped `registration_operation_audit`.

There are exactly nine triggers, ninety-seven generated transition leaves, zero
views, and zero ordinary indexes. The complete semantic budget is three
member phases, four protocol modes, ten transition kinds, thirteen
transition reasons, three request kinds, three effect outcomes, four action
kinds, three observation kinds, five conflict codes, five successor causes,
three transaction classes, twenty-four operation kinds, twenty-six runtime
reasons, zero durable notice forms/variants, one predeployment evidence stage,
two rollout authorization stages, and three implementation bodies. Counts are
mechanically checked ceilings. There is no separate request, archive, notice,
proof, membership, alert/outbox, Rescue, GC, or
current-pointer relation, and there are zero synthetic global row ceilings,
database-byte ceilings, capacity classes, or terminal capacity stop codes.
Proof/certificate is effect outcome. ADR 0020 alone
owns integrity generations, alerts, dispatch, and receipts.

The plan's canonical normalized SQL declares every column, type, nullability,
key, foreign key, CHECK, and trigger predicate. Its SHA-256 is:

```text
221aaf6680b50ca8f6c8c2cf024acbedbf5273b90c8c5625bcc4100c448d5ede
```

Every trigger-critical value is relational. Closed JCS blobs are evidence
only, exclude raw paths, must re-encode byte-identically from their relational
tuple, and have an exact prohibited-content mutation corpus. Rejecting
triggers use complete predicates `IS NOT TRUE`; nullable equality uses `IS`
or explicit null checks. Generated NULL and one-column-invalid cases exercise
all nine triggers and every T03/T09 carry leaf.

One consistent connection-authorizer boundary makes protocol, episode,
action, and operation history append-only and exposes only named
member/status transitions plus one effect-outcome update. Protocol history
does not get a special UPDATE/DELETE trigger. Same-UID raw SQLite bypass is
an explicit unsupported residual; observed drift is RED.

The plan enumerates each persisted row-hash preimage in canonical column
order. Current operation backlink/id/hash columns are excluded and bound
separately through immutable audit plus triggers, including INSTALL; no
catch-all preimage or self-reference remains. The generated leaf manifest,
not a hand count, owns trigger coverage.

The former result archive duplicated immutable operation and participating
state hashes. Before subtraction, an equivalence model covered normal
transitions, ambiguous commit resolution, corruption mismatch,
successor/handoff, and containment. Moving indispensable predecessor effect,
member, status, cause, lineage, and successor hashes into the existing audit
preserves those classifications without a replacement relation, blob, or
parallel ledger.

### 3. Members have three durable phases

```text
REQUESTED -> EFFECT_IN_FLIGHT -> RESOLVED
    ^                 |              |
    | structural     pending         | conditioned successor
    + invalidation   successor       +------> REQUESTED
```

Schedule, executor, unavailable, and help state are bounded runtime
status, never a durable phase. `RESOLVED` is only complete SUCCESS or
LOGICAL_CONFLICT. Corrupt/partial closure attempts containment and remains
RED.

`member_epoch` is the only member revision across effect identity, current
and pending state, operation witnesses, CAS, status, and handoff. No parallel member
revision exists.

One `registration_effect` row exists before execution as the immutable
request/intent. OPEN_EFFECT validates a transaction-fresh current-boot
`mach_continuous_time()` sample and directly CASes the due
member/effect/status basis, protocol, profile, and same-device facts;
optionally appends FIRST_EFFECT; installs one executor; and moves
REQUESTED→EFFECT_IN_FLIGHT. Only that commit authorizes
lifecycle I/O.

The FIRST_EFFECT protocol row is the sole exact DATA exception to the
protocol-insert deny. The typed store OPEN_EFFECT API alone owns it; product
flow may call that API, while installer/CONTROL cannot compile or impersonate it. `first_effect_id` and
`first_effect_operation_id` become non-NULL together and every later protocol
row preserves both.

Outcome changes exactly once:

- SUCCESS requires all four frozen actions and complete
  completion/final-basis/proof/certificate data;
- LOGICAL_CONFLICT is reachable after any ordinal and requires the first
  conflict also be the final ledger entry; or
- SUPERSEDED requires the exact authorized operation, immutable
  predecessor/successor/status hashes, reachable state, and successor effect;
  it does not require the active executor.

UNAVAILABLE appends no action. It releases the member lock, clears the
executor, updates only bounded mutable status, schedules same-effect
help, and yields. The next due event/startup/tick/retry uses the
`REACQUIRE_EFFECT` DATA transaction: after `BEGIN IMMEDIATE` it samples fresh
current-boot continuous time, revalidates the exact in-flight
effect/ledger/basis/protocol/generation/capability tuple, installs one
operation-bound executor, and clears scheduling. Only that commit
reauthorizes lifecycle I/O. It never reruns OPEN_EFFECT or allocates a
replacement effect.

OPEN_EFFECT, REACQUIRE_EFFECT, ADOPT_EFFECT, every immediate pre-helper-I/O
check, APPEND_ACTION, CLOSE_SUCCESS, CLOSE_CONFLICT, and MARK_UNAVAILABLE
carry the expected executor token and old status hash under the member lock.
OPEN binds a new resulting executor to exact old member/effect/status hashes;
later result operations compare the current non-NULL executor. Stale ownership rejects
before I/O or mutation while one owner and FIRST_EFFECT provenance remain.

Post-commit I/O requires the live executor and committed
member/status/effect/protocol targets of the granting operation, not its CAS
input. Plaintext executor capability remains process-memory-only. A
process-scoped member lock is held through helper I/O and released by death;
only its next acquirer may perform exact stored token/status takeover.
Same-UID advisory-lock/memory/raw-SQL bypass remains unsupported.

An executor records its boot id. REBOOT_STATUS may clear it only from a
non-NULL transaction-fresh sample proving the stored boot differs. Same-boot
death uses exact old-executor/status MARK_UNAVAILABLE CAS and then
REACQUIRE_EFFECT.

ADOPT_EFFECT records immutable lineage to the exact active effect, old
generation/capability, staged epoch/action plan, and adopted generation.
REACQUIRE_EFFECT permits an effect/member generation mismatch only when that
lineage proves the current protocol/capability pair; hostile or lineage-free
mismatches reject.

### 4. Successor transitions are total and acknowledgement-safe

Pre-intent structural invalidation works directly from due REQUESTED state.
During in-flight work, structural change installs or full-CAS replaces one
pending effect without replacing the active effect.

After either SUCCESS or LOGICAL_CONFLICT, every root event, startup
reconciliation, 15-second tick, or explicit retry examines the member.
RESOLVED→REQUESTED is legal only for existing pending work, a freshly proven
basis/closure change, or explicit LOGICAL_CONFLICT retry. It computes a
deterministic transition id from the complete immutable predecessor,
operation cause, and successor hashes; records them in immutable audit;
installs the condition-bound successor; clears result/pending fields; and
initializes due or blocked status. Unchanged SUCCESS remains stable green and
does no write, so event volume cannot grow history.

T03/T06 bind every selected successor effect to the target member id, current
or pending epoch as applicable, basis hash, and request tuple; pending handoff
must select the exact old pending effect. INSTALL_MEMBER likewise binds the
initial member tuple and every member write backlink to its audit envelope,
with an exact pre-commit closure check.

Ambiguous effect close resolves as
`COMMITTED_SUCCESS | COMMITTED_LOGICAL_CONFLICT | ABSENT | UNAVAILABLE`.
Ambiguous successor transition resolves as
`APPLIED | ABSENT | OBSOLETE | UNAVAILABLE`. Only ABSENT retries the same
object.

After reboot, RESOLVED with no pending effect clears runtime timing. With a
pending effect it immediately attempts handoff; if unavailable it remains
RESOLVED with new-boot due/help status.

Close carries unavailable/yield counters for SUCCESS-with-pending and both
conflict leaves; only idle SUCCESS intentionally zeros them.

### 5. Admission is revision-fenced and launch-denying

The discriminator order is:

```text
preidentity/root failure -> Task/subagent launch -> unknown tool -> ordinary tool
```

Task/subagent/agent launch defaults to deny before ordinary
admission in the closed parser, direct/catch-all/enumerated dispatchers,
serializer, startup/tick, and `status|retry` control surfaces. Launch intent
cannot inherit parent green or become a diagnostic exception. Both matcher
modes must prove receipt and denial of every installed launch discriminator;
if a build exposes launch only on an unreceivable seam, installation refuses
activation with no coverage claim.

Ordinary admission is exactly `B1 / E@R1 / B2 / R2`: two independent
uncached basis samples around one complete authority read, followed by an
immediate reread of current protocol sequence/hash plus only the selected
member/status/effect tuple revision/hash. Unrelated member commits do not
change R1 or deny. Allow requires identical bases and selected tuples, exact
episode/member/effect closure, and one read-only aggregate status snapshot
that is READY only when host, profile, projection, storage, parser,
serializer, DIRECT+WRITABLE protocol, member tuple, no-pending SUCCESS, and
inventory membership are all live and green. Existing bounded reasons cover
every non-READY component. One mismatch retry is allowed; a second
unknown/change/failure denies.

The selected reason renders one deterministic response directly from that
snapshot. No notice operation, response-form split, repeat metadata, or
presentation history persists.

R1 admission additionally requires the owner receipt, exact candidate
digest, canonical root hash, and member id in the existing DIRECT receipt to
match; every other root/member denies. Only an owner-authorized R2 receipt
may broaden that scope.

Another member's conflict, retry, or overdue state never denies an unrelated
green member. Only that member's own status/fairness and genuinely shared
host health are relevant.

### 6. Fairness is a per-tick work budget, not a lifetime ceiling

Member history has no row-count limit. Eight is only the 15-second tick work
budget and lane count. Each tick snapshots due rows and selects the first
eight by
`(COALESCE(observed_now_mono_ns,due_since_mono_ns), due_since_mono_ns,
member_id)`. Every selected row commits either its attempt outcome or the
existing bounded schedule/yield update, advancing the observation field so
untouched rows sort ahead next tick. Failure to commit either is a
selected-row miss. A finite continuously due set therefore continues fairly
without a new epoch or queue relation.

The five-second service budget applies only to the selected eight. A selected
row without a durable outcome becomes own-member RED; an unselected backlog
row remains queued. Suspend, host-unhealthy, and missing-tick states remain
separate. There is no all-members-in-one-tick or fixed unbounded-backlog
liveness claim.

### 7. Hook truth remains fail-open

Hook-owner v4 binds normalized rows, exact inventory, matcher/projection
hashes, file/protocol generations, DIRECT receipt, and wrapper/runtime
hashes. Catch-all requires official contract plus live discriminator UAT;
otherwise exact enumeration is required.

Only a functioning receiving wrapper's seam-valid deny response or
intentional exit 2 proves that invocation was denied. Missing rows/events,
startup/import/exec/config failure, timeout, kill, crash, malformed output,
store unavailability, and containment-commit unavailability make no denial
claim. Global rows remain `failClosed:false`.

External projection ownership default-denies before persistence. Every
protocol row is intrinsically DIRECT with a non-NULL receipt; there is no
external dormant branch, reason, notice, recovery edge, or invented MAC/key
distribution infrastructure. External support remains deferred.

### 8. Protocol transitions use an installer-authenticated control lane

CONTROL exists only after immutable installer identity/capability and
protocol-lock receipt verification. It binds old current+DRAINING state,
immutable staged epoch, affected action plan, and exact rows. Actor strings
never authorize.

Legal protocol edges are activation, one FIRST_EFFECT, begin drain, atomic
pre-adoption stage/replace, cancel-to-read-only, generation advance, absence-proved
pre-effect dormancy, enter containment, and begin forward repair.

Staged schema must equal the current canonical seven-table/nine-trigger hash.
Changing schema requires a superseding decision and migration. STAGE_NEXT may
atomically replace a quiescent candidate, and CANCEL_DRAIN may atomically
clear one while returning to the existing DORMANT/read-only posture, only
before any adoption audit/current reference. After adoption only advance or
containment/forward repair remains. ADVANCE_GENERATION preserves `storage_dev`.

Drain disables old entrypoints, waits prior writers, and starts after every
RESOLVED pending effect has handed off. It refuses any clean REQUESTED effect;
the driver must directly OPEN or otherwise resolve/SUPERSEDE it first.
It also refuses a second drain while an in-flight effect still requires a
prior generation, making adopted reacquire single-hop. It adopts each old-generation
executor under its member lock in deterministic batches of at most eight,
continuing across control passes until none remain. Adoption validates the
frozen action plan;
it preserves a valid executor or installs one operation-bound staged
executor for a quiescent same-effect retry. Any in-flight pending effect is
recorded in immutable audit, SUPERSEDED, and replaced with a fresh
staged-generation/capability effect before advance rather than being mutated
or implicitly rebound. Its reservation is excluded only when a non-NULL
target successor proves that actual pending effect is superseded; no-pending
adoption retains the active-effect reservation.

Every positive DRAINING edge carries a fresh non-null boot/monotonic sample,
requires the stored boot, and must be at/before the drain deadline. Mismatch
or expiry permits only containment/forward repair.

Protocol shape is total: DRAINING iff both drain boot/deadline are non-null;
every other mode iff both are null. All exits clear both explicitly, while
non-DRAINING carries use NULL-safe equality. Half-null tuples are never valid.

Drain deadline is current-boot continuous time plus five seconds. Boot
mismatch requires non-NULL transaction-fresh boot and monotonic samples and
sampled boot inequality, then immediately attempts containment without
comparing an old monotonic value. A committed CONTAINMENT row is durable authority.
`CONTAINMENT_UNAVAILABLE` means the store prevented that commit, cannot claim
containment or denial, and uses the independent ADR 0020 host RED/repair
path.

### 9. Profile and storage admission are bounded

The supported profile is stock SQLite `>=3.51.3` on local macOS/APFS with
WAL, FULL sync/fullfsync/checkpoint-fullfsync, foreign keys, defensive mode,
trusted-schema off, secure absolute root/user-owned non-other-writable
ancestry, descriptor identity checks, and no checkpoint-on-close.

One domain-separated canonical profile receipt binds an ordered ancestry,
APFS, SQLite, pragma, DB/WAL/SHM, descriptor, and device measurement
sequence. Every bound descriptor is measured with `fstat` plus `fstatfs`;
the normalized filesystem type, two signed-decimal `f_fsid` components,
mount flags, and `st_dev` values enter the closed JCS preimage. DB, WAL/SHM,
proof, projection, legacy lifecycle, member root, per-worktree Git directory,
and Git common directory must share both the APFS tuple and verified
`st_dev`. `st_dev` is not claimed to prove power-loss durability, media
identity, or APFS volume-group behavior. Unsupported or unavailable
measurement denies before intent. Each write repeats identity, APFS, and
fresh descriptor-bound free-space preflight.

M1 defines no row-count or database-byte terminal. Every write requires:
one GiB filesystem safety floor, projected transaction bytes, all outstanding
and newly created effect reservations, and the exact remaining control
reserve of at most fourteen MiB. A low measurement accepts no durable
operation and writes no notice/counter; a later event automatically resumes
only after externally observable free space again satisfies the complete
reserve.

Native SQLite `FULL`/`IOERR` is not converted into another capacity state. If
creation or a later suffix write returns an error, close/reopen plus the
operation envelope resolves exact COMMITTED, ABSENT, PARTIAL, or UNAVAILABLE;
the return code never chooses persistence. COMMITTED is honored, ABSENT keeps
the prior tuple, and PARTIAL/UNAVAILABLE never become success. Post-durable
ABSENT/PARTIAL failure separately attempts existing
`ENTER_CONTAINMENT/STORE_FAILURE`. A successful containment commit is
durable; if SQLite cannot write it, only external
`CONTAINMENT_UNAVAILABLE` may be reported—never a fabricated row or
persistence claim.

Physical GC, migration, rotation, new database generations, Rescue, and
custom VFS work remain deferred. They are unnecessary for M1 safety because
free-space refusal is self-clearing and native persistent substrate failure
has no liveness promise.

### 10. Execution detail belongs to the plan

The candidate plan owns implementation-body allocation, harness ownership,
predeployment evidence, canary sequencing, C1 evidence, and rollout detail.
This ADR authorizes none of them while draft.

The one acceptance authority is existing repository owner/operator
`KleinPerkins` (Laurence Duggan). The non-circular order is fixed: exact C0
review/verifier technical clearance; checker-computed allowed promotion
hashes; owner acceptance conditional on those exact hashes; atomic checked
promotion/freeze; separate implementation GO; then the plan's separately
authorized R1, C1, and R2 gates. Only exact status-token bytes may change
during promotion, and dates/other bytes must remain identical. See v3 §3 and
§5–§6 for execution mechanics. Nothing is accepted, promoted, implemented,
or rolled out now.

## Why

- A single-root canary proves registration/admission without a membership
  protocol.
- Merging request and effect removes split authority while retaining the
  pre-I/O barrier and acknowledgement-safe history.
- Against the prior reviewed draft, object/state/operation counts stay flat;
  the derived leaf count changes 95→97 because reboot targets are now
  outcome-specific. No scheduler or authority relation is added.
- Capacity subtraction removes synthetic row/store ceilings. Fresh free-space
  admission plus SQLite rollback/containment gives equivalent safety without
  a terminal capacity lifecycle: synthetic counts could neither guarantee a
  commit nor reclaim immutable history.
- Against frozen draft v2, it removes 50 of 57 tables, 98 of 107 triggers,
  four of seven member phases, five of eight implementation tasks, and all
  Rescue/GC/separate-request/effect-graph machinery.
- Three phases keep transient execution state in bounded status and make final
  success/conflict inspectable.
- One immutable operation witness plus participating state rows supports
  requested replacement, pending replacement, staged adoption, and handoff
  without a duplicate archive ledger.
- Append-only protocol history and maximum-sequence selection remove a
  mutable current-pointer failure mode.
- One authenticated control lane is smaller than per-row capabilities while
  honestly retaining same-UID raw-SQL residual risk.
- Eight service lanes bound each tick while deterministic existing-state
  ordering continues an unbounded member-history backlog across ticks.
- Proof and alerts have no independent lifecycle: effect outcome and ADR 0020
  already own them.
- Rescue, deletion, multi-root, Task entry, external activation, and
  production custom-VFS work have no M1 counterexample.

Rejected alternatives are v2's broad prerequisite set; separate request and
effect tables; a pre-authority phase; multi-root M1; episode-owned current state; a
mutable protocol pointer; B2 as effect authorization; diagnostic tool
exceptions; child inference from parent metadata; automatic dirty-work
mutation; and invented external receipt cryptography.

## Consequences

- Functioning AWA can provide durable registration before supported ordinary
  intercepted tools for one supported clean root.
- Overlapping episodes share one canonical member/effect/result authority.
- Replay, COMMIT uncertainty, invalidation, handoff, reboot, and generation
  change have bounded same-object convergence.
- Stale statuses/executors cannot authorize I/O, append, close, or clear
  another owner's effect; same-boot and old-boot recovery use distinct fences.
- UNAVAILABLE and rebooted in-flight work have one executable same-effect
  reacquisition path, including lineage-proven adopted effects; “retryable”
  never means executorless.
- Operator responses are deterministic projections of live authority, not a
  second durable presentation lifecycle.
- Task/subagent launch and external projection activation remain unavailable
  in M1.
- Dirty/in-progress work receives denial plus manual preservation guidance,
  not automatic progress.
- Append-only history has no product-defined row/file terminal. New durable
  work stops with zero writes while free space is below the complete reserve
  and resumes after fresh recovery; native SQLite failure resolves exact
  committed/absent authority before containment or honest observable
  unavailability.

Unsupported residuals remain total hook/runtime/host absence; no-event and
broken-wrapper fail-open surfaces; local read before read-hook model denial;
manual/Tab/external/cloud-early/already-running work; dirty-root automatic
progress; same-user path replacement/raw SQLite bypass; unsupported
platform/device/VFS/power behavior; and notification visibility.

## Evidence and owner gates

Accepted source hashes remain:

```text
ADR 0020  f0911b0a85e85b6dc1d616fa6f092d33f9002e9c8d9bc5bf2edda4a927a95a98
ADR 0023  71476602db37828c80503f05790a57aa587572cef1e800cfa42b2d32e86a0051
ADR 0024  cecca6d380d446b91af00a4e5aea44282c4b9633b518a638967fcbeb4de38911
frozen v1 e3bf9182e4e16411ab1424123a7200b3f6ec0dd4e09429237256a5601dcb6bd9
draft v2  03aff346283c2809d9bab392120972de97bd14b5879e01448a8af734becf8b9b
```

The plan records the exact finding map, six verifier dispositions, reason
matrix, schema, trigger branches, harness ownership, and acceptance ledger.
Bounded local SQL syntax/inventory/hash checks are documentation evidence
only. C0 requires those checks, a source-to-design trace, final whole-file
hashes for ADR/plan/index surfaces, their normalized body digest,
fresh reliability review, and a schema-valid protected verifier return whose
expected candidates are all independently resolved,
`critical_coverage_complete=true`,
`critical_probe_blind_review_complete=true`, `revision_matches=true`, and
`blockers=[]`. Failed shipping may be ignored only when solely caused by
partial rollout for the plan's enumerated C1-only implementation/fault/UAT
gaps; every other failed field blocks. Only after that technical clearance may the checker
compute allowed post-promotion hashes for conditional `KleinPerkins`
acceptance. The verifier's
expected incomplete-evidence `partial_rollout=true` and failed shipping
clearance do not block C0; neither reports deployment reach. A fresh scoped
review still must determine whether any substantive design blocker remains.

There is no implementation, supported-profile state-transition proof,
process-fault result, concurrency result, complete live tool inventory,
Desktop UAT, or rollout proof. Their absence is expected and does not block
C0; it means `C1-SHIPPING` is UNSATISFIED. C1 later requires exact-head
implementation/model/fault/concurrency/UAT evidence,
`partial_rollout=false` for implementation/evidence completeness, and a fresh
verifier shipping pass on an explicitly authorized R1 canary. R2 still
requires its own owner GO.

`C0-DESIGN` therefore remains UNSATISFIED. Only after technical clearance,
exact owner acceptance, and atomic promotion/freeze may an exact
implementation baseline be refreshed and a separate
implementation GO name that baseline and evidence. Neither is part of C0,
and neither substitutes for R1 canary GO, C1, or R2 rollout GO.

Until C0 clears, leave code, contracts, tests, runtime, hooks, jobs, state,
PR #175, GitHub metadata, releases, installation, Skills, host wiring,
accepted ADRs, frozen v1, and superseded v2 unchanged.
