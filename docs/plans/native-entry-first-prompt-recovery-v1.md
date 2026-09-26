# Native Entry First-Prompt Recovery

- **Version:** v1
- **Status:** ACCEPTED — FROZEN
- **Date:** 2026-09-25
- **Architecture authority:** accepted
  [ADR 0024](../adr/0024-first-prompt-native-entry-recovery.md)
- **Relates to:** accepted
  [ADR 0023](../adr/0023-native-entry-registration-and-honest-worktree-metrics.md)
  and [ADR 0020](../adr/0020-awa-integrity-surveillance-and-lifecycle.md)
- **Implementation baseline:** clean AWA `main`
  `ff978ade5ff9c7604f58f4b3810b1cd75ea3287f` (`v1.8.1`)
- **Plan type:** agentic execution after explicit owner GO only
- **Review provenance:** one probe plus four focused reviewers, all validated;
  verifier gate false; no second-pass trigger; shipping clearance not evaluated

**Goal:** Correct ADR 0023's event premise without weakening its safety
properties. Keep exact `sessionStart` registration as an eager opportunity and
recover a missed native entry at the first valid `beforeSubmitPrompt`, using
only documented payload identity and a bounded fail-open adapter.

**Architecture:** One event-aware registrar accepts a closed payload envelope,
normalizes `conversation_id` as the session identity, proves an exact complete
current-session binding, and serializes lifecycle plus
`awa-native-entry/v2` evidence under a fixed lock order. A new hook-owner
successor composes a hard-deadline adapter before the unchanged finish
consumer. This body adds no `workspaceOpen` hook or behavior.

> **Governance stop:** This DRAFT authorizes documentation only. No task below
> may begin until the owner explicitly accepts ADR 0024, accepts this plan, and
> separately says **GO** to implementation. Plan acceptance, a planning PR,
> green checks, or general approval is not implementation GO.

---

## 1. Purpose and boundary

AWA v1.8.1 registers native linked worktrees from `sessionStart`. Official
Cursor semantics make that event conversation creation, not worktree entry.
An existing or moved conversation can therefore enter a worktree without
triggering the registrar.

This plan adds one recovery opportunity at prompt time. It does not promise
pre-prompt registration and does not use `workspaceOpen` as mutation
authority. It preserves:

- ADR 0023's exact root/Git/policy/content/lifecycle validation;
- one adoption, attestation, SQLite/event ordering, and post-lifecycle success
  evidence;
- ADR 0020's kernel-first, engine-off, host-ownership, and read-only discovery
  boundaries;
- the guard and cleanup kernels as the sole safety/removal authorities; and
- current finish output and exact-`Close` behavior.

No implementation, release, host wiring, install, activation, UAT acceptance,
or cleanup is part of this governance change.

## 2. Verified baseline and stop conditions

### 2.1 Live baseline recorded 2026-09-25

| Surface | Verified state |
|---|---|
| Current `bdkd` root | Clean before this documentation change at `ff978ade5ff9c7604f58f4b3810b1cd75ea3287f` |
| Local and live remote `main` | Both `ff978ade5ff9c7604f58f4b3810b1cd75ea3287f` |
| Annotated release tag | `v1.8.1` tag object `15c1634d8468bdf42da9f561d24dee635a6df9b7`; dereferences to `ff978ade5ff9c7604f58f4b3810b1cd75ea3287f` |
| No-touch roots | `3qoz` and protected primary clean at `ff978ade`; `al94` clean at `dcd11dc`; `4zjh` absent |
| Established artifact hashes | Evidence only; do not reopen files from no-touch roots |

The primary at `/Users/laurence.duggan/dev/capabilities/awa` and roots
`3qoz`, `al94`, and `4zjh` remain no-touch. All future implementation uses a
fresh governed linked worktree at the then-live main head.

### 2.2 Source facts at the bound baseline

- `engine/native_entry.py` accepts only a `sessionStart` registrar envelope,
  writes `awa-native-entry/v1`, and keys receipts by root/session.
- `kernel/hooks/awa-session-handoff.sh` independently consumes ensure handoff
  evidence and invokes the native-entry registrar, quietly and fail-open.
- `kernel/hooks/before-submit-prompt.sh` invokes
  `consumer/finish_current.py`; it has no registration pre-step.
- `consumer/finish_current.py` already binds first-prompt current-session state
  for finish, but it has legacy environment fallbacks. It is not registration
  authority and must not be changed by this work.
- `contracts/awa-hook-owner.v2.json` declares `sessionStart`, guard-composite,
  and stop-observer successor roles. It does not declare prompt-time entry
  recovery.
- Lifecycle adoption currently writes disk lease, SQLite lease, `adopt` event,
  attestation state, and `attest` event in that order before native-entry
  success evidence.

### 2.3 Stop and refresh before implementation if

- ADR 0024 or this plan is not explicitly accepted;
- the owner has not given a separate implementation GO;
- live main changes native-entry, current-session, lifecycle, finish, hook
  ownership, installer, or cleanup semantics;
- official Cursor documentation changes the relevant hook events or identity
  fields;
- implementation would require `workspaceOpen` mutation authority,
  `DEV_SESSION_ID`, synthesized identity, a guard/cleanup relaxation, or a
  change inside `consumer/finish_current.py`;
- hook-owner v3 cannot preserve v1/v2 compatibility and external zero-access;
  or
- any Dev, Skills, primary-root, release, installation, or live-state change
  becomes necessary.

An unrelated main advance may be rebound only after recording the new OID and
proving the protected-surface diff does not invalidate this plan.

## 3. Fixed implementation contract

### 3.1 Event and identity matrix

| Event | Registration role | Required identity | Allowed effect |
|---|---|---|---|
| `workspaceOpen` | Not wired or consumed by this body; existing observations remain discovery-only | Root observations only; no conversation identity exists | No bind, adopt, attest, or receipt write |
| `sessionStart` | Eager compatibility path | One canonical root; non-empty `conversation_id` and `generation_id`; explicit `session_id` required and exactly equal to `conversation_id` | Attempt exact registration |
| `beforeSubmitPrompt` | First-prompt recovery path | One canonical root; non-empty `conversation_id` and `generation_id`; absent `session_id` is allowed, but a present value must equal `conversation_id` | Attempt exact registration before finish |
| Any other/malformed event | Unsupported | None may be inferred | Quiet refusal |

The parser consumes only the closed, version-tested payload envelope. An
already-supported wrapper may be retained only when top-level and nested
copies agree exactly. At least one documented `workspace_roots` value is
required; all supplied root-bearing values must canonicalize to one physical
root and each authority-bearing path must already be canonical. Cwd,
environment, prior receipts, heartbeats, and generated identifiers are never
identity fallback.

For both supported events:

```text
normalized_session_id == conversation_id
```

If any explicit session value differs, registration refuses before receipt,
lease, SQLite, or event mutation.

### 3.2 Complete current-session gate

Before lifecycle registration, the event path must:

1. observe the exact linked root identity;
2. heartbeat only the normalized payload identity;
3. bind `awa_current_session/v1` with source equal to the real event;
4. re-read the record and active heartbeat member; and
5. require exact root, normalized session, conversation, branch, common
   directory, current boot, and live membership.

The lifecycle critical section repeats step 4 and the complete Git/policy
identity check under the common-directory lock. Missing, malformed, partial,
prior-boot, mismatched, contended, or replaced state refuses. A failed bind is
not repaired from environment or v1 receipt data.

### 3.3 `awa-native-entry/v2`

New writes use one strict schema:

```text
schema                 = "awa-native-entry/v2"
source_event           = "sessionStart" | "beforeSubmitPrompt"
session_id             = normalized conversation identity
conversation_id        = exact payload conversation_id
source_generation_id   = exact payload generation_id
root                   = canonical linked root
branch                 = attached branch
head                   = exact object id
git_dir                = canonical per-worktree Git directory
git_common_dir         = canonical common Git directory
generation             = monotonic receipt generation integer
timestamp              = UTC timestamp
result                 = pending | success | stale | mismatched | conflict | failed
action                 = adopted | attested | repaired | recovered | null
lease_id               = exact lease identity | null
reason                 = closed value-free reason code
```

`pending` is explicitly non-green. `action` and `lease_id` are non-null only
for success. `recovered` means a
prior attempt completed the exact attested lifecycle state but failed before
success publication; it emits no duplicate lifecycle event. An exact-current
success returns an in-memory no-op and does not rewrite the receipt.

The receipt key remains collision-safe per canonical root and normalized
session. A pending-to-terminal transition retains the exact source event and
source generation. Prompt/attachment/transcript/model/operator content is
never persisted or logged.

`source_generation_id` identifies the attempt that last changed v2 evidence;
it is not part of lifecycle identity. A later prompt generation for the same
exact root/session/conversation may take the exact-current success no-op and
leaves that successful receipt unchanged. If any live identity has drifted,
the new attempt publishes its own source generation through a new monotonic
pending-to-terminal transition.

Readers accept strict v1 and v2 keysets. V1 remains a legacy discovery seed
and may be reported as legacy/unknown; it cannot prove source event,
conversation, or source generation. A real v2 attempt may replace it only
after full current validation. Malformed or mixed-schema records remain
conflict, never auto-repaired.

Retain private `0700` directories, regular owned `0600` files, bounded
no-follow reads, same-directory atomic writes, fsync, strict freshness,
replay/drift rejection, and bounded inventory.

### 3.4 Locking, transitions, and exact-once effects

The only nested lock order is:

```text
common-directory lifecycle lock -> native-entry receipt lock
```

No code may wait for the common-directory lock while holding the receipt lock.
Receipt-only readers may take the receipt lock without another lock.

The mutation state machine, under the common-directory lock, is:

1. re-read exact root/Git/policy/clean/index/operation/current-session/
   heartbeat/lease/SQLite state;
2. under the receipt lock, return no-op only for an exact-current v2 success,
   otherwise CAS-publish pending evidence and release the receipt lock; an
   incoming later prompt generation alone does not defeat the no-op or rewrite
   the source provenance of the successful attempt;
3. perform at most one adoption or exact repair, preserving disk lease ->
   SQLite lease -> `adopt` -> attestation -> `attest` ordering;
4. re-read the exact complete identity, lease, SQLite row, attestation,
   heartbeat, and current session; then
5. under the receipt lock, CAS pending -> success only if generation, source,
   root, session, conversation, source generation, and Git identity still
   match.

Failure after a safe key exists may publish a monotonic terminal failure, but
must never downgrade an exact-current success. A stale worker's CAS fails
quietly. Parallel `sessionStart`/first-prompt delivery for one key yields one
adoption and one required attestation/event sequence; later exact deliveries
are no-ops.

The registrar receives one absolute monotonic deadline. Every Git read, lock
wait, SQLite operation, receipt operation, and child cleanup consumes its
remaining time; per-call timeouts cannot add up beyond it. The first-prompt
supervisor sets the hard 2.0-second deadline. The eager path is independently
bounded inside its existing `sessionStart` hook timeout and must not rely on
sibling-hook ordering.

### 3.5 Prompt adapter and unchanged finish

Use a fixed **2.0-second total wall-clock budget** for prompt recovery. It is a
sub-deadline inside the existing 20-second hook row and is not extendable by
ordinary environment configuration.

Add:

- `engine/native_entry_prompt_adapter.py`: a minimal supervisor that reads a
  bounded payload from stdin, starts the registrar worker with closed file
  descriptors and a new process group, sends payload only over stdin,
  suppresses stdout/stderr, and terminates then kills the group on deadline;
- `kernel/hooks/before-submit-prompt-with-entry.sh`: a composite that preserves
  the same complete valid JSON payload, runs the adapter quietly, and then
  invokes the existing `kernel/hooks/before-submit-prompt.sh`.

Keep byte-identical:

- `kernel/hooks/before-submit-prompt.sh`; and
- `consumer/finish_current.py`.

The composite must emit exactly the finish hook's stdout/stderr and exit code.
Missing adapter/engine/Python, malformed payload, timeout, signal, contention,
or non-zero adapter status is ignored before finish runs. The adapter can
neither block submission nor manufacture finish JSON.

### 3.6 Hook-owner successor and repository boundary

Create `contracts/awa-hook-owner.v3.json`:

- `schema: awa-hook-owner/v3`;
- `successor_of: awa-hook-owner/v2`;
- v3 composition inherits the effective v1+v2 role graph;
- `supersedes_roles: ["finish.prompt-recall"]`; and
- one new `beforeSubmitPrompt` composite role points to
  `before-submit-prompt-with-entry.sh`, retaining matcher
  `UserPromptSubmit`, timeout `20`, and `failClosed: false`.

V1 and v2 contract bytes remain unchanged. Direct install prefers and validates
v3. Explicit v1/v2 compatibility tests remain. External mode retains
`external_real_hook_file_writes:false`: AWA does not read, stat, render,
backup, chmod, or write the external hook file.

AWA owns the contract, registrar, adapter, and composite script. A later
separate Dev PR owns the external-row transition and rollback. This plan makes
no Dev edit and no live hook change.

### 3.7 Preserved safety and observability

- Guard classification, protected-primary denial, engine-off behavior, and
  shell output remain unchanged.
- Cleanup continues to require its independent active-root, current-session,
  Git registration, content/ignored-state, recovery, operation-state,
  branch-safety, and operator-authorization gates.
- Receipts, leases, heartbeats, events, metrics, and discovery observations
  never authorize removal.
- Discovery remains read-only. V1/v2 receipts may seed inspection only.
- Existing linked, managed, active, unleased, conflict, and problem population
  meanings remain unchanged. Entry evidence may distinguish v1/v2 and real
  source event only where needed to explain the invariant. Missing/unrun data
  is null/not checked, never zero.
- Primary, excluded, detached, dirty, in-progress, ambiguous, malformed, or
  contended roots are never adopted.
- No network or GitHub Actions runner enters the runtime path.

## 4. Future work items — only after owner GO

### Task 0: Rebind authority and record GO

- [ ] Re-read ADR/plan indexes, accepted ADRs 0020/0023, draft ADR 0024, and
  this plan.
- [ ] Refresh local/remote main and official Cursor hook documentation.
- [ ] Record the exact implementation worktree, base OID, clean status, and
  owner GO text.
- [ ] Stop if any §2.3 condition is true.

**Definition of done:** accepted ADR 0024, accepted frozen plan, and a separate
explicit implementation GO are all present. Otherwise no implementation file
is opened for write.

### Task 1: Freeze payload and receipt v2 behavior with failing tests

**Files:**

- Modify: `engine/tests/test_native_entry.py`
- Create: `engine/tests/test_native_entry_first_prompt.py`
- Modify later in this task: `engine/native_entry.py`

- [ ] Add RED tests for the exact §3.1 envelope matrix, equality mapping,
  absent optional prompt `session_id`, conflicting explicit identity, and zero
  environment/cwd fallback.
- [ ] Add strict v1/v2 reader fixtures, malformed/mixed-schema conflict cases,
  exact source-event retention, and prompt-content non-persistence.
- [ ] Refactor the registrar to parse `sessionStart` and
  `beforeSubmitPrompt` through one normalized payload object and write only v2.
- [ ] Preserve the ensure-handoff consumer as an independent operation; native
  registration neither forges nor closes unrelated handoff intent.
- [ ] Run the focused tests and retain RED-then-GREEN evidence.

**Definition of done:** supported payloads normalize one exact identity; every
missing, ambiguous, mismatched, or inferred identity refuses; v1 reads remain
strict and conservative.

### Task 2: Implement the current-session gate and monotonic lifecycle

**Files:**

- Modify: `engine/native_entry.py`
- Test: `engine/tests/test_native_entry.py`
- Test: `engine/tests/test_native_entry_first_prompt.py`
- Consume unchanged unless a separately reviewed defect is proved:
  `engine/lifecycle.py`, `engine/state.py`, `kernel/lib/awa_roots.py`

- [ ] Add payload-bound heartbeat, bind, and exact complete re-read before
  registration; repeat the complete gate under the lifecycle lock.
- [ ] Implement the fixed common-dir -> receipt lock order and generation CAS.
- [ ] Move exact-success dedupe inside full live validation.
- [ ] Make pending precede lifecycle mutation and success follow final
  lifecycle validation.
- [ ] Recognize crash-complete attested state as `recovered` without duplicate
  adoption, attestation, or events.
- [ ] Prove same-key sequential, repeated, and parallel delivery cannot let
  stale pending overwrite success.
- [ ] Prove different event deliveries for the same canonical identity
  converge on one lifecycle result without relabeling the source event.

**Definition of done:** one adoption exactly once; required attestation and
SQLite events in order; no same-key amplification; no receipt/common-dir
deadlock.

### Task 3: Add the hard-deadline composite and hook-owner v3

**Files:**

- Create: `engine/native_entry_prompt_adapter.py`
- Create: `kernel/hooks/before-submit-prompt-with-entry.sh`
- Create: `contracts/awa-hook-owner.v3.json`
- Create: `engine/tests/test_native_entry_prompt_hook.py`
- Create: `engine/tests/test_hook_owner_v3_matrix.py`
- Modify: `kernel/hooks/install-hooks.sh`
- Modify: `kernel/checks/awa-contract-freeze.sh`
- Modify: `install.sh`
- Preserve byte-identically: `kernel/hooks/before-submit-prompt.sh`,
  `consumer/finish_current.py`, `contracts/awa-hook-owner.v2.json`, and
  `contracts/awa-contract.v1.json`

- [ ] Implement the 2.0-second supervisor budget with process-group
  termination, bounded input, no logs, no inherited output, and no prompt in
  argv/environment/files.
- [ ] Implement the composite's complete-JSON and exact-finish-output relay.
- [ ] Freeze the v3 role composition and v1/v2 compatibility.
- [ ] Prove direct install/doctor/staging projections prefer v3.
- [ ] Prove external install/repair/doctor/uninstall remains zero-access to the
  selected hook file.
- [ ] Prove adapter absent, malformed, failed, killed, or timed out still runs
  finish and returns its exact valid JSON/exit behavior.

**Definition of done:** bounded recovery precedes finish without becoming a
blocking hook or changing finish semantics; v3 is explicit and older
contracts remain valid.

### Task 4: Preserve discovery, metrics, guard, and cleanup independence

**Files:**

- Modify as required by v2 reads: `engine/integrity.py`,
  `engine/lifecycle_reconcile.py`
- Modify tests: `engine/tests/test_integrity_invariants.py`,
  `engine/tests/test_lifecycle_reconcile.py`
- Update after behavior is proven: `README.md`, `ARCHITECTURE.md`
- Test unchanged guard/cleanup/finish/kernel-off suites

- [ ] Make discovery accept strict v1/v2 records without treating either as
  cleanup authority.
- [ ] Preserve existing population metrics and honest null/not-checked
  semantics; expose v1/v2 or source detail only where needed to explain the
  entry invariant.
- [ ] Prove replay, branch/HEAD/root/common-dir/session drift, stale
  generation, malformed receipt, and replaced current-session state cannot
  remain green.
- [ ] Prove guard and cleanup outcomes are identical with the engine missing,
  adapter missing, receipts present/absent, and registration failed/succeeded.
- [ ] Update product docs to say first-prompt recovery, never workspace-open
  registration.
- [ ] Leave version declarations unchanged; release work is out of scope.

**Definition of done:** observability understands v2 without gaining mutation
authority, and every kernel/cleanup boundary remains independent.

### Task 5: Verify, review, and hold one Draft PR

Run focused verification:

```bash
bash -n \
  kernel/hooks/awa-session-handoff.sh \
  kernel/hooks/before-submit-prompt-with-entry.sh \
  kernel/hooks/before-submit-prompt.sh
python3 -m py_compile \
  engine/native_entry.py \
  engine/native_entry_prompt_adapter.py
python3 -m unittest -v \
  engine.tests.test_native_entry \
  engine.tests.test_native_entry_first_prompt \
  engine.tests.test_native_entry_prompt_hook \
  engine.tests.test_hook_owner_v3_matrix \
  engine.tests.test_active_root \
  engine.tests.test_entry_handshake \
  engine.tests.test_integrity_invariants \
  engine.tests.test_lifecycle_reconcile \
  engine.tests.test_finish_conversation \
  engine.tests.test_finish_hardening \
  engine.tests.test_kernel_off_matrix
```

Run repository verification:

```bash
bash engine/tests/run-tests.sh
AWA_HOME="$(pwd)" bash kernel/checks/awa-contract-freeze.sh
./install.sh --check
make verify
make verify-install
git diff --check
git diff --exit-code ff978ade5ff9c7604f58f4b3810b1cd75ea3287f -- \
  consumer/finish_current.py \
  kernel/hooks/before-submit-prompt.sh \
  contracts/awa-hook-owner.v2.json \
  contracts/awa-contract.v1.json \
  kernel/hooks/worktree-guard.sh
git status --short --branch
```

- [ ] Inspect the complete branch diff and repository status.
- [ ] Open one governed **Draft PR** only after local verification passes.
- [ ] Run `/loop /review-bugbot` until no valid finding remains.
- [ ] Run one security review over the complete branch; fix valid findings and
  rerun all affected/full gates.
- [ ] Keep the PR Draft and unarmed. Do not call `gh pr merge --auto`, enable
  auto-merge, mark ready, merge, tag, release, bind, install, activate, or run
  live UAT.

**Definition of done:** the exact Draft PR head is fully reviewed and green,
with no valid unresolved finding. Shipping clearance and merge/release remain
unevaluated pending a later explicit owner decision.

## 5. Focused acceptance-test ledger

| Requirement | Required proof |
|---|---|
| Supported envelopes | Exact top-level and retained wrapper forms agree; unsupported keys/events cannot create authority |
| `workspaceOpen` boundary | No product role is added; direct/repeated open or folder-change fixtures are refused and never bind, adopt, attest, or write a receipt |
| Eager `sessionStart` | Full documented identity registers; missing/conflicting conversation, generation, or equal session refuses |
| `sessionStart` ordering | Eager registration does not depend on a sibling hook running first or on fire-and-forget completion order |
| First-prompt fallback | Existing/moved conversation with no successful eager registration adopts or attests from an exact `beforeSubmitPrompt` |
| Optional prompt session | Missing `session_id` maps only from `conversation_id`; a present unequal value refuses |
| Missing/malformed/ambiguous | Empty, oversized, non-JSON, conflicting wrapper, absent roots, multiple physical roots, and symlink aliases refuse quietly |
| Root exclusions | Primary, policy-excluded, detached, dirty, ignored-state, hidden-index, and in-progress Git roots remain unadopted and unchanged |
| Current-session gate | Exact bind plus re-read passes; absent, partial, malformed, prior/replaced, mismatch, stale membership, and contention refuse |
| Adoption exactly once | Sequential and parallel same-key/event-mixed delivery creates one lease lineage and one adoption |
| Event ordering | Disk lease, SQLite lease, `adopt`, attestation state, and `attest` precede v2 success |
| Exact-success dedupe | No-op occurs only after full live receipt/lease/SQLite/heartbeat/current-session/Git validation, accepts a later prompt generation for the same lifecycle identity without rewriting successful source provenance, and emits no new receipt/event |
| Receipt post-success only | Pending exists before mutation; success appears only after lifecycle and final identity complete; crash remains pending/recoverable |
| Same-receipt race | Generation CAS prevents stale pending/failure from overwriting success; lock-order test proves no deadlock |
| Repeat/parallel amplification | Replays and concurrent delivery do not add duplicate attestation/events |
| V1 compatibility | Strict v1 remains readable/discoverable as legacy; no source/conversation/generation is inferred; exact v2 attempt upgrades conservatively |
| Source provenance | Real source event and generation survive transition; `beforeSubmitPrompt` is never relabeled `sessionStart` |
| Replay/drift | Root, branch, HEAD, Git-dir, common-dir, conversation, session, generation, lease, SQLite, heartbeat, or current-session drift invalidates success |
| Discovery/metrics | V1/v2 seed only read-only discovery; eager/recovered/legacy/unknown/not-checked are distinct; unchecked remains null |
| Adapter deadline | Hung registrar and descendants are gone by the 2.0-second budget; finish still receives the same complete valid JSON payload |
| Finish parity | Adapter missing/success/failure/timeout yields byte-equivalent finish JSON, stdout/stderr, exit, publication, and exact-`Close` behavior |
| Hook-owner compatibility | V3 direct projection is exact; v1/v2 remain valid; external lifecycle performs zero hook-file access |
| Guard/cleanup independence | Receipts/leases/events never authorize clean; guard and cleanup decisions match with engine on/off |
| Engine off | Missing engine/adapter remains fail-open; protected-primary kernel denial and linked-worktree behavior remain intact |
| Privacy/durability | `0700`/`0600`, owner/regular/no-follow/bounds/atomic/fsync hold; prompt, attachments, transcript, model, environment, and secrets are absent |
| Shell/Python/diff/repo gates | Syntax, focused/full suites, contract freeze, installer checks, protected-file diff, `git diff --check`, and clean-status accounting pass |

No test may pass by weakening a validator, changing expected guard/cleanup
output, sleeping past races, skipping the adapter's process tree, or treating
missing evidence as success.

## 6. Acceptance criteria

Implementation is ready for owner review only when:

1. ADR 0024 and this plan were accepted before implementation, and explicit
   implementation GO is recorded.
2. The refreshed baseline and Cursor hook contract do not invalidate the
   design.
3. Payload-only identity, exact root selection, explicit-session equality,
   and complete current-session re-read are enforced.
4. `awa-native-entry/v2` records real source provenance and strict v1 readers
   remain conservative.
5. Common-dir -> receipt lock ordering, monotonic CAS, exact-success dedupe,
   adoption exactly once, event ordering, and post-lifecycle success all pass
   repeated/concurrent tests; later prompt generations alone remain no-ops for
   an otherwise exact-current success.
6. The prompt adapter has one hard 2.0-second total budget and leaves no child
   process, output, or prompt-bearing artifact.
7. Finish consumer/script bytes and behavior are unchanged.
8. Hook-owner v3 is explicit; v1/v2 compatibility and external zero-access
   pass.
9. Discovery/metrics remain honest and read-only; guard/cleanup/engine-off
   behavior remains independent.
10. Every focused and repository verification command passes at the exact
    Draft PR head.
11. Bugbot and security review have no valid unresolved finding.
12. The PR remains Draft/unarmed; no release, bump, tag, bind, install,
    activation, UAT acceptance, cleanup, or Dev/Skills edit occurred.

## 7. Owner GO / NO-GO gates

### Plan acceptance

The owner must explicitly accept draft ADR 0024 and this plan. Acceptance
freezes this plan byte-identically; a material change requires
`native-entry-first-prompt-recovery-v2.md`.

### Implementation GO

After acceptance, the owner must separately authorize implementation against
an exact refreshed baseline. A qualifying instruction must clearly name this
body of work, for example:

```text
GO to implement ADR 0024 using native-entry-first-prompt-recovery-v1
from <exact-main-oid>.
```

No generic approval, PR action, or green check substitutes for that GO.

### NO-GO

Without both accepted documents and explicit implementation GO, leave source,
contracts, tests, versions, hooks, runtime, host wiring, jobs, state, no-touch
roots, and GitHub unchanged. If implementation later completes, stop with a
Draft/unarmed PR; merge, release, and rollout require later owner decisions.

## 8. Non-goals

- Code, contract, or test changes during this governance task.
- Editing accepted ADR 0023 or any accepted plan.
- `workspaceOpen` registration or any immediate-entry claim.
- Environment/cwd/synthesized identity authority.
- Changes to finish semantics, shell guard, cleanup policy, current operator
  UX, ensure-handoff meaning, or engine-off safety.
- Release/version bump/tag/publication, Skills binding, install, activation,
  live Desktop UAT acceptance, cleanup, or state migration.
- Dev host-row edits; those require a later separate Dev PR.
- Primary/no-touch-root writes or artifact reinspection.
- Network work in the runtime path or any GitHub Actions runner.

## 9. Review provenance and residual concerns

One probe mapped the event, identity, lifecycle, receipt, hook-owner, and
finish surfaces. Four focused reviewers independently validated the governing
issues:

1. an alternate-event patch would violate accepted ADR 0023;
2. the payload/session contract lacked a durable canonical mapping;
3. hook-owner v2 cannot be silently overloaded;
4. v1 receipts cannot prove prompt source/conversation/generation;
5. same-key pending/success transitions need monotonic serialization;
6. exact-success dedupe needs complete live validation;
7. prompt recovery belongs in a separate timeout-contained adapter;
8. current-session identity must be complete and re-read before registration;
   and
9. prompt-time semantics and total latency must be stated honestly.

All reviewer outputs validated. The verifier gate was false, so shipping
clearance was not evaluated; a second pass was denied because no escalation
trigger existed.

The principal residual is product-bound: there is still no documented event
that provides both immediate worktree-entry timing and exact conversation
identity. This design does not hide that gap. It provides eager
conversation-start registration when available and exact first-prompt
recovery otherwise.
