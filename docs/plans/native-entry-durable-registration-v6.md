# Native Entry Durable Registration

- **Version:** v6
- **Status:** ACCEPTED — FROZEN — DOCUMENTATION ONLY; IMPLEMENTATION DELIVERY AND R0 NO-GO
- **Date:** 2026-10-02
- **Supersedes if accepted:** accepted, frozen
  [`native-entry-durable-registration-v5.md`](native-entry-durable-registration-v5.md),
  preserved byte-identically at SHA-256
  `4586a1302f8ce03cc064e58e610af3784fb4c77beb8e7a4d6089f1259612857b`
  and accepted normalized digest
  `f4d222435da9c7eb323d0e4c92fe0997f88beb92c56a85dad7cd96704361be94`.
- **Architecture authority:** accepted, immutable
  [ADR 0026](../adr/0026-durable-registration-authority-hardening.md), SHA-256
  `1486135d62ccf9a4fdb1fbaad59a8d5d619f2bd51fa317a1eaa5f0f96db0b82a`.
- **Source baseline:** merged Body A on `main`,
  `d96c9737d75bb2da3f603205e645a605d2f331da`; reviewed Body A head
  `f67bdb5bfef69d510ef79906f109140c43a55a95`; [PR #180](https://github.com/KleinPerkins/awa/pull/180).
- **Owner-key enrollment:** current enrollment hash
  `885f30c94383b1b69451b336fcc1fc99fe31e7d142c64588fb41f14f179028f4`;
  this plan neither reads nor uses private key material.
- **Bootstrap anchors:** accepted-v5 receipt hash
  `c27746a232275380bfca5cba110d4533813cdc4e9b4a3710629a9c34742706a6`,
  allowed-signers contract hash
  `9155be780c73e65a549ae97326dc56c53045aeaddb697745a95ce191aa472b7e`,
  and current receipt SHA-256
  `a304498e0158b05ad7f2827e9fda210dda0673133677e81a0eba735ac2e9e411`.
- **Documentation authorization:** the operator selected a narrowly scoped v6
  successor to repair the missing Body A provider boundary before Body B.
  This authorizes only this draft and its one DRAFT index row. It does not
  authorize acceptance promotion, code/test mutation, commit, push, PR,
  signing, R0/R1/C1/R2, release, installation, activation, or rollout.
- **Version discipline:** this is a bounded execution successor, not a
  restatement of accepted v5. Read accepted v5 first. Every v5 requirement is
  inherited unchanged except the exact `V6-R1`–`V6-R4` deltas below.
- **Closed-world budget:** unchanged from accepted v5: seven tables, nine
  triggers, ninety-seven generated leaf keys, three member phases, four
  protocol modes, three effect outcomes, three transaction classes,
  twenty-four operation kinds, twenty-six runtime reasons, and exactly three
  implementation bodies.

**Goal:** restore the typed Body A provider seam that accepted v5 requires
Body B to consume, then resume the original Body B without private store
access, non-atomic selection, or a fourth implementation body.

> **Governance stop:** draft bytes authorize documentation only. Accepted v5
> remains current until the exact v6 owner-acceptance envelope is supplied and
> only the two named documentation status surfaces are promoted.

---

## 1. Why a successor is required

### 1.1 Verified merged state

Body A merged through reviewer automation. Its SQL-v2, semantic closure,
profile, executor, transfer, exhaustion, and monotonic-resolution work remains
accepted evidence and is not reopened by this plan.

Before Body B mutation, exact merged-source inspection found three required
provider contracts absent:

1. no typed same-boot snapshot selector exists in
   `engine/registration_store.py`;
2. no atomic `select_r1_scope` implementation exists anywhere outside the
   accepted-plan prose; and
3. no public store-owned member-lock scope lets Body B collect a fresh basis
   and perform the associated structural mutation under that same lock.

The only global selectors are `list_due_candidates` and
`list_reboot_candidates`. `list_due_candidates` correctly caps an ordinary
fairness batch at eight; it rejects nine. The existing R1 path requests nine
in `registration_host.HostService.tick` to infer outside scope, which is
neither an atomic three-class preflight nor a valid call.

### 1.2 The boundary conflict

Accepted v5 assigns `P1-11`, `P2-02`, `P2-03`, and `P2-05` behavior to Body B
and permits Body B to change only:

- `registration_admission.py`;
- `registration_runtime.py`;
- `registration_basis.py`;
- `registration_view.py`; and
- focused tests.

The same plan requires Body B to collect fresh basis “through A's typed API”
and consume typed same-boot/R1 selectors. Those APIs must be implemented in
`registration_store.py`, a Body A surface. Using `_locks`, `_connection`, raw
SQL, or private lock arguments from Body B would violate the accepted
authority boundary. Expanding Body B to own the store would erase the
separation rather than repair it.

### 1.3 Minimal correction

V6 adds no product behavior and changes no accepted database authority. It
adds one repair pass inside existing Body A, containing only typed provider
APIs and their focused tests. Body B remains the sole owner of policy,
cursor progression, parser behavior, admission, worker scheduling, and views.
Body C remains the sole owner of durable host-tick publication and deployment
authority.

---

## 2. Exact v6 delta map

| ID | Accepted-v5 conflict | V6 decision | Owner |
|---|---|---|---|
| V6-R1 | Body B must collect fresh basis under the member lock through an A API, but no such API exists and B cannot access store locks | Add one sealed, store-bound, member-bound mutation scope. It invokes the Body B collector only after acquiring the exact member lock and reuses that lock only through closed typed store operations | A provider; B consumer |
| V6-R2 | P1-11 requires one protocol-bound, bytewise-ordered same-boot snapshot, but the store exposes no same-boot selector | Add a read-only typed `select_same_boot_snapshot` provider using one read transaction and complete semantic validation | A provider; B policy/cursor |
| V6-R3 | R1 must atomically preflight same-boot, due, and reboot scope, while the current due selector is independently capped at eight | Add read-only typed `select_r1_scope`; it returns the authorized zero-or-one candidate per class plus three outside-scope booleans from one transaction, without limit-nine inference | A provider; B enforcement |
| V6-R4 | Body A's one-PR delivery is complete, so its missing providers cannot be added under the original Gate 4 | Permit one separately authorized Body A provider-repair Draft PR, merge it before Body B, then restore accepted-v5 sequencing and per-body gates | Governance |

These four rows are exhaustive. Every other accepted-v5 byte of meaning,
finding owner, stop condition, gate, test obligation, and non-goal remains in
force.

---

## 3. Body A provider-repair contract

### 3.1 Closed typed values

`registration_store.py` adds immutable typed values with exact fields:

```text
FreshMemberBasis:
  identity: MemberIdentity
  intent: EffectIntent
  workspace_roots_hash: lowercase 64-hex

SameBootCandidate:
  member_id: lowercase 64-hex
  status_hash: lowercase 64-hex
  executor_token_hash: lowercase 64-hex
  executor_generation: positive integer

SameBootSnapshot:
  boot_id: nonempty string
  protocol_seq: positive integer
  protocol_hash: lowercase 64-hex
  candidates: tuple[SameBootCandidate, ...]

R1ScopeSelection:
  authorized_same_boot: SameBootCandidate | null
  authorized_due: DueCandidate | null
  authorized_reboot: RebootCandidate | null
  outside_scope_same_boot: bool
  outside_scope_due: bool
  outside_scope_reboot: bool
```

Python booleans are not integers for any integer field. Every hash, nullable
field, and nested typed value is validated at construction. These values
contain no connection, cursor, lock descriptor, capability, secret, callable,
or raw row.

`SameBootSnapshot` maps exactly to accepted v5's
`awa-registration-same-boot-snapshot/v1` schema. Body B owns canonical JCS
serialization—including rendering typed integer values as the accepted
unsigned decimal strings—snapshot hashing, cursor validation/progression, and
`BUSY_LIVE | CLEARED | RECOVERED | NO_LONGER_CANDIDATE` outcomes. The store
does not interpret a cursor or host-tick receipt as authority.

### 3.2 Member mutation scope

The public entry is:

```text
member_mutation_scope(member_id, timeout_seconds=5.0)
    -> MemberMutationScope
```

The scope:

- is created only by `RegistrationStore`;
- acquires exactly the existing member lock and verifies its descriptor before
  invoking any supplied collector;
- is bound to one store object and one member id;
- is context-managed, creating-PID/thread-bound, one-owner, non-serializable,
  fork-invalid, and invalid after release;
- exposes no raw `HeldLock`, lock path, SQLite connection/cursor, DATA secret,
  executor secret, CONTROL constructor, generic SQL, or arbitrary callback
  execution beyond the one typed fresh-basis provider;
- supports timeout zero so same-boot policy can classify lock contention as
  `BUSY_LIVE`; and
- never acquires a protocol lock while the member lock is held.

Its closed fresh-basis operation invokes one zero-argument provider under the
held lock and accepts only `FreshMemberBasis`. It requires:

- the identity-derived member id equals the scope member id;
- `identity.current_basis_hash == intent.request_basis_hash`; and
- the workspace-roots hash is valid.

The returned basis is scope-bound. A later collection invalidates the earlier
one for mutation. Release invalidates all collected values. Provider failure,
member mismatch, malformed typed data, or lock loss performs no store write.

The scope exposes only the existing structural operations needed by Body B:

```text
install_member
bind_episode
invalidate_requested
set_pending
replace_pending
handoff_resolved
mark_dead_executor_unavailable
```

Each wrapper re-verifies the same held lock and consumes the current
scope-bound fresh basis where the operation is basis-sensitive. It delegates
to the existing store implementation; it does not duplicate SQL, operation
construction, semantic closure, free-space accounting, or commit resolution.
Where an existing operation needs `BasisUpdate`, the wrapper derives it
directly from the four corresponding `MemberIdentity` hashes; callers cannot
supply a second basis object.
Scoped episode binding additionally requires
`EpisodeSource.workspace_roots_hash` to equal the current fresh basis's
workspace-roots hash. A pending RESOLVED handoff and any immediately required
invalidation use one continuously held scope, so no older pending basis can be
reinstalled after a newer under-lock observation.
An exact duplicate or equality with current/pending authority remains the
existing zero-write no-op.

Existing direct store methods remain available to Body A tests and
installer-owned paths, but Body B production code may not call a direct
basis-changing method. A structural test rejects Body B access to
`_locks`, `_connection`, private lock parameters, or direct calls to the six
basis-changing operations above. Same-boot recovery may call only the scoped
`mark_dead_executor_unavailable` wrapper before releasing the scope and using
the existing independent REACQUIRE path.

### 3.3 Same-boot snapshot provider

The exact public selector is:

```text
select_same_boot_snapshot(*, boot_id) -> SameBootSnapshot
```

It opens one read transaction, reads the current protocol row, and selects
every row satisfying all of:

- member phase is `EFFECT_IN_FLIGHT`;
- current effect has no outcome;
- executor token hash and executor generation are non-null;
- executor boot id equals the supplied boot id; and
- member, status, effect, operation companions, backlinks, and current
  protocol pass complete semantic validation.

Candidates are sorted by bytewise lowercase-hex `member_id`. A missing current
protocol, malformed candidate, invalid semantic closure, SQL error, or
transaction failure returns no partial snapshot and raises typed store
unavailability. The selector performs no write and acquires no member lock.

The snapshot is observational only. Body B must non-blockingly acquire the
candidate's exact member scope and full-CAS the selected status/token before a
MARK. PID, age, cursor, receipt, and snapshot membership never authorize
takeover.

### 3.4 Atomic R1 scope provider

The exact public selector is:

```text
select_r1_scope(authorized_member_id, boot_id, now_mono_ns)
    -> R1ScopeSelection
```

Input validation rejects empty boot ids, booleans as integers, negative time,
and malformed member ids. One read transaction observes one current protocol
and all three candidate universes:

1. current-boot non-null executors eligible for same-boot examination;
2. due rows eligible under the existing due predicate at `now_mono_ns`; and
3. executor/schedule rows eligible under the existing reboot predicate.

For each universe it returns the semantically validated authorized-member row
or null and independently sets `outside_scope_*` when any other member
qualifies. It does not select nine, truncate, page, or derive an outside flag
from a limited result. Any semantic or SQL failure refuses the whole result.
It performs no mutation.

Body B R1 calls this selector exactly once before any same-boot, reboot, due,
helper, status, or cursor mutation. Any true outside flag refuses the entire
tick with zero mutation. Ordinary non-R1 due fairness continues to request
exactly eight rows from `list_due_candidates`; that selector's limit remains
unchanged.

---

## 4. Revised execution sequence

There remain exactly three implementation bodies. `A-R` is a repair pass
inside Body A, not a fourth body.

### A-R — Body A typed-provider repair

Tests first, then change only:

- `engine/registration_store.py`; and
- `engine/tests/test_registration_store.py`.

No runtime, admission, basis, view, host, schema, SQL, hash-preimage,
profile, executor, installer, contract, or deployment file belongs in A-R.

A-R implements only §3. It must preserve canonical SQL v2, 7/9/97 inventory,
all operation/phase/reason budgets, direct APIs' current behavior, and merged
Body A verification.

**A-R stop:** any fix requires a schema/SQL/preimage change, new operation or
reason, raw store internals in Body B, protocol/member lock inversion,
cursor/receipt authority in the store, or a fourth implementation body.

### Body B — unchanged owner, now unblocked

After A-R merges, Body B resumes on the new `main`. Its accepted-v5 file
surface and obligations remain unchanged. It consumes §3's APIs to implement
fresh-under-lock convergence, bounded parsing, same-boot cursor policy,
independent workers, atomic R1 refusal, admission, and views. Body B neither
changes `registration_store.py` nor reconstructs its queries.

### Body C — unchanged

Body C remains responsible for durable host-tick-v2 publication, cursor/tick
preimages and receipts, deployment authority, receiver continuity, R0, and
rollout. A-R and Body B produce typed inputs and policy results only.

---

## 5. Acceptance-test ledger

| ID | Required evidence | Owner |
|---|---|---|
| AR01 | Scope acquires and verifies the exact member lock before invoking the provider; provider failure is zero-write | A-R |
| AR02 | Scope/store/member/PID/thread mismatch, post-fork/use-after-release, stale collected basis, serialization, and malformed typed values refuse; timeout-zero contention reports busy with zero write | A-R |
| AR03 | Two processes with old/new observations in both orders converge on the under-lock fresh value; exact duplicates are zero-write | A-R provider; B final consumer proof |
| AR04 | Scoped install/bind/invalidate/set/replace/handoff preserve existing operation envelopes, semantic closure, and no-op behavior | A-R |
| AR05 | Same-boot snapshot 0/1/8/9/>9 is complete, bytewise ordered, protocol-bound, semantically validated, and read-only | A-R |
| AR06 | Concurrent protocol/status changes yield one complete old or new snapshot, never a mixed or partial snapshot | A-R |
| AR07 | R1 same-boot/due/reboot authorized member at positions 1/8/9 plus an outside member sets the exact independent flag in one read transaction | A-R |
| AR08 | R1 malformed/corrupt candidate or SQL failure returns no usable partial result and causes zero mutation | A-R |
| AR09 | Ordinary due limit remains 1–8; limit nine still rejects; Body B later proves it requests eight and uses `select_r1_scope` for scope | A-R/B |
| AR10 | Existing focused Body A suite, cross-body registration suite, `make verify-pre-pr`, and diff check pass | A-R |
| AR11 | Body B structural proof finds no `_locks`, `_connection`, raw SQL, private lock argument, or direct basis-changing store call | B |
| AR12 | Body B cursor missing/stale/current/wrap/busy/no-longer-candidate, >8 progress, eight overlapping workers, killed worker, parser, admission, and R1 zero-mutation vectors pass | B |

No A-R test may weaken, skip, monkeypatch away, or replace an accepted-v5
test. Platform-specific clocks remain explicitly injected where required.

---

## 6. Non-goals

V6 does not:

- reopen merged Body A behavior unrelated to the three provider gaps;
- alter canonical SQL v2, schema objects, hash preimages, operation kinds,
  phases, outcomes, transaction classes, reasons, or reservations;
- move parser, admission, fairness, cursor policy, or view ownership into the
  store;
- move durable host-tick publication or deployment authority out of Body C;
- treat a cursor, receipt, PID, elapsed time, or snapshot as mutation
  authority;
- access a private owner key or perform signing;
- authorize implementation delivery, R0/R1/C1/R2, release, installation,
  activation, or rollout; or
- stage or deliver accepted v5, the owner-signers contract, or other dirty
  governance artifacts as part of A-R.

---

## 7. Gates and branch discipline

### Gate V6-1 — plan acceptance

Requires the exact owner envelope in §8. It authorizes only the two
documentation status promotions. It does not authorize A-R.

### Gate V6-1A — A-R local implementation GO

After acceptance, a separate owner message must name repository, accepted v6
normalized digest, exact Body A provider-repair scope, and exact base. It
authorizes tests-first local mutation of the two A-R files only. It explicitly
does not authorize commit, push, PR, readiness, merge, signing, R0/R1/C1/R2,
release, installation, activation, or rollout.

### Gate V6-2 — A-R implementation-delivery GO

After verified local implementation, a separate owner message must name:

- repository `KleinPerkins/awa`;
- accepted v6 normalized digest;
- exact base `d96c9737d75bb2da3f603205e645a605d2f331da`;
- branch `impl/native-entry-durable-registration-v6-body-a-repair`;
- current enrollment hash; and
- permission to commit, push, and open/update one Draft PR only.

Only the two A-R files may be staged. The accepted plans, index, enrollment
contract, machine-local receipts, and Body B files remain unstaged.

### Gate V6-3 — A-R body readiness

After local verification, diff audit, Bugbot, and Security Review, a separate
exact-head owner GO is required before changing the Draft PR's readiness.
Agents never approve, arm auto-merge, or call auto-merge. The reviewer App
alone may merge.

### Gate V6-4 — Body B delivery

After A-R merges and Body B is rebased onto exact live `main`, accepted v5's
separate Body B Gate 4 and Gate 5 apply unchanged, except they name accepted
v6's digest as the current execution authority. No A-R gate implies Body B
delivery.

All R0/R1/C1/R2, release, install, activation, and rollout gates remain NO-GO.

---

## 8. Exact v6 acceptance

### 8.1 Normalized digest

Compute:

```text
SHA256(
  ASCII("awa-registration-v6-normalized/v1") || 0x00 ||
  normalized_plan_bytes || 0x00 || normalized_index_bytes
)
```

`normalized_plan_bytes` are the exact UTF-8/LF v6 bytes after replacing
exactly one complete status line, whether DRAFT or ACCEPTED, with:

```text
- **Status:** __AWA_V6_STATUS__
```

including one LF.

`normalized_index_bytes` are the exact UTF-8/LF plan-index bytes after
replacing exactly one complete v6 row, whether DRAFT or ACCEPTED, with:

```text
| `native-entry-durable-registration-v6.md` | __AWA_V6_INDEX_STATUS__ | Bounded successor to accepted v5 under ADR 0026; restores Body A's typed fresh-basis, same-boot snapshot, and atomic R1-scope providers before Body B resumes. |
```

including one LF. Zero, duplicate, mixed, CRLF, or non-exact replacements
refuse.

### 8.2 Owner envelope

Acceptance requires one exact canonical-JSON object:

```json
{"action":"ACCEPT_PLAN_V6","accepted_v5_normalized_digest":"f4d222435da9c7eb323d0e4c92fe0997f88beb92c56a85dad7cd96704361be94","accepted_v5_receipt_hash":"c27746a232275380bfca5cba110d4533813cdc4e9b4a3710629a9c34742706a6","adr_0026_sha256":"1486135d62ccf9a4fdb1fbaad59a8d5d619f2bd51fa317a1eaa5f0f96db0b82a","allowed_signers_contract_hash":"9155be780c73e65a549ae97326dc56c53045aeaddb697745a95ce191aa472b7e","authorized":true,"authorized_by":"KleinPerkins","base_commit":"d96c9737d75bb2da3f603205e645a605d2f331da","current_receipt_sha256":"a304498e0158b05ad7f2827e9fda210dda0673133677e81a0eba735ac2e9e411","denied_implications":["ACCESS_PRIVATE_KEY_OR_SIGN","IMPLEMENT_OR_DELIVER_A_R","COMMIT_PUSH_OR_OPEN_PR","RUN_R0_R1_C1_OR_R2","RELEASE_INSTALL_ACTIVATE_OR_ROLL_OUT"],"draft_index_sha256":"<computed lowercase 64-hex>","draft_plan_sha256":"<computed lowercase 64-hex>","enrollment_hash":"885f30c94383b1b69451b336fcc1fc99fe31e7d142c64588fb41f14f179028f4","normalized_digest":"<computed lowercase 64-hex>","repository":"KleinPerkins/awa","schema":"awa-registration-v6-plan-acceptance-go/v1","v5_file_sha256":"4586a1302f8ce03cc064e58e610af3784fb4c77beb8e7a4d6089f1259612857b"}
```

Every placeholder is replaced with its reviewed value before submission. The
supplied full-file and normalized hashes must equal independent
recomputation. Each plan/index/ADR/contract input must be an owner-UID regular
file, mode `0644`, link count one, and not a symlink; pre-open, opened, and
post-read identity/size/mtime must remain stable. The current branch HEAD,
accepted-v5 bytes/digest/receipt, ADR bytes, owner-signers contract hash,
current receipt hash, enrollment hash, v6 draft bytes, and exact DRAFT index
row must still match the envelope.

On success, promotion changes only:

1. the v6 status line to
   `ACCEPTED — FROZEN — DOCUMENTATION ONLY; IMPLEMENTATION DELIVERY AND R0 NO-GO`;
2. the v6 index status cell to
   `ACCEPTED — DOCUMENTATION ONLY; IMPLEMENTATION DELIVERY AND R0 NO-GO — 2026-10-02`.

After both writes, reread and revalidate complete visible files and recompute
the normalized digest. It must remain identical. Any other byte or mode change,
partial promotion, replacement, or metadata drift refuses and is not
acceptance. Promotion is not a commit, delivery, or implementation GO.

---

## 9. Review provenance

The draft was derived from:

- accepted v5 exact bytes and normalized digest;
- merged Body A `main` at `d96c9737d75bb2da3f603205e645a605d2f331da`;
- direct inspection of public store/runtime/admission APIs and focused tests;
- exact symbol searches confirming no code implementation of
  `select_r1_scope`; and
- the owner-selected v6 repair path after the cross-body conflict was
  reported before Body B mutation.

Review must adjudicate the complete v6 delta against accepted v5, not only the
latest hunk. Any review finding that requires broader ownership, schema
change, or private-store access triggers the A-R stop and a new owner decision.
