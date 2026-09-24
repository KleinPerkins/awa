# ADR 0023: Register native Cursor entry and report honest worktree populations
Status: draft — 2026-09-23

## Context

AWA v1.8.0 UAT exposed a gap between the documented default entry path and the
implemented lifecycle. Cursor's Agents Window Worktree environment created and
entered a valid linked worktree. The kernel session hook then recorded an
`active_root/v1` heartbeat, so cleanup correctly preserved the root and the
shell guard correctly allowed linked-worktree use. Nothing after entry adopted
the root, however: there was no `.awa/lease.json`, active SQLite lease, adoption
event, attestation, current entry proof, or native-entry receipt.

The existing `awa-session-handoff/v1` contract did not cover this case. It is a
singleton intent/close proof produced only by `dev-worktree.sh ensure`; native
Cursor creation has no pre-create AWA call and must not forge ensure intent.

The same UAT exposed an observability defect. Deep integrity discovered
lifecycle topology only from active leases, so a heartbeating but unleased
native worktree could be omitted. `orphans.worktrees` was carried forward or
defaulted rather than computed, while the private console labeled that value
“Worktrees,” implying a total it did not contain.

ADR 0020 defines the entry invariant from explicit handoff metadata and says
the invariant set may grow only through a successor ADR. This record narrowly
supersedes that entry-evidence definition and the ambiguous worktree-count
projection. It preserves ADR 0020's evaluator, status-last store, host
ownership boundary, read-only reconciliation, and prohibition on autonomous
deletion.

## Decision

### 1. Native session entry gets a distinct fail-open registration path

The existing `sessionStart` handoff hook remains a thin, quiet dispatcher. It
continues to consume an exact pending ensure handoff and independently invokes
an engine-side native-entry registrar with the same payload. Neither operation
depends on sibling hook ordering. Missing engine code, malformed input, timeout,
lock contention, or any exception remains fail-open and cannot block ordinary
Cursor entry.

The registrar accepts only one explicit `sessionStart` event, one unambiguous
session identity, and one canonical physical root. It performs no network call.

### 2. Adoption and attestation require exact under-lock identity

Before mutation, and again under the existing per-common-directory collision
lock, registration validates:

- host-policy eligibility including higher-priority exclusions;
- a canonical real root and complete Git toplevel, per-worktree Git directory,
  common directory, attached branch, and HEAD;
- exactly one local linked-worktree registration, excluding the primary;
- a clean worktree and visible index with no unrelated ignored state; and
- private regular AWA state with no malformed, conflicting, ambiguous, or
  symlinked lease/receipt projection.

Lifecycle adoption now supports an expected complete identity recheck under
the lock immediately before writing. With no lease or conflicting row, the
registrar reuses adoption to create the lease, SQLite row, adoption event, and
attestation. A matching valid lease is attested without another adoption.
Disk-only or SQLite-only state is repaired only when one exact path, branch,
HEAD, common directory, and lease identity makes the repair unambiguous.
Malformed, mismatched, duplicate, or drifting state is preserved and reported
as conflict or mismatch; it is never seized.

### 3. `awa-native-entry/v1` is private post-entry evidence

Each root/session pair receives a deterministic collision-safe private receipt
under the AWA state root. The schema binds canonical root, session, branch,
HEAD, per-worktree Git directory, common directory, generation, timestamp,
result, action, and lease identity. Its closed results are `success`, `stale`,
`mismatched`, `conflict`, and `failed`; successful actions are `adopted`,
`attested`, or `repaired`.

Directories are `0700`, files are `0600`, reads are bounded and no-follow, and
writes are same-directory atomic publications. Receipts contain no prompt,
transcript, file content, credential, arbitrary environment, or operator text.
Success is written only after adoption/attestation and a final identity
validation.

This is proof of post-start registration, not pre-entry authorization.
`awa-session-handoff/v1` remains the unchanged singleton pending→closed proof
for `ensure`. A native session for another root cannot close or replace that
intent. Ensure-created roots may also receive native-entry receipts, but the
two evidence types remain separate.

### 4. Entry health accepts either exact evidence type and names uncertainty

The public invariant id `entry_handshake` is retained for compatibility, but
its meaning broadens to “validated entry evidence.” An exact current closed
ensure handoff or an exact current successful native-entry receipt is green.
Heartbeat or current-session observation alone is never green. Missing evidence
is unknown; stale, mismatched, failed, and conflict evidence is non-green, with
conflict distinct from absence.

Native receipt validation rechecks the current root, session, branch, HEAD,
Git directory, common directory, lease, SQLite row, heartbeat membership, and
current-session binding. Replayed evidence cannot remain green after drift.

### 5. Deep lifecycle discovery is observation-led and read-only

Candidate repositories are seeded from active leases, strict active-root
observations, strict native-entry receipts, and the configured probe. The
reconciler still performs only closed local Git reads with optional locks and
lazy fetch disabled. It never adopts, retires, cleans, removes, or contacts a
remote.

A registered linked root with active heartbeat but no lease is represented as
preserved, unleased, and problematic. Active-root evidence improves discovery
only; it adds no cleanup authority.

### 6. Worktree metrics name actual populations

Deep evaluation computes path-deduplicated populations:

- `discovered_linked`: locally registered linked worktrees observed in seeded
  repositories;
- `managed`: discovered linked worktrees with one unambiguous active SQLite
  lease and matching on-disk lease;
- `active`: discovered linked worktrees with current active-root evidence;
- `unleased`: discovered linked worktrees with no active SQLite lease;
- `conflicts`: discovered linked worktrees with ambiguous or asymmetric lease
  state; and
- `problems`: the union requiring attention, including unleased, conflict,
  unknown, dirty, husk, or topology-error rows.

The additive private/public `worktrees` object carries those values plus a
`checked` flag. Fast evaluations preserve prior private values but mark them
unchecked; a missing prior deep result projects “not checked,” never zero.
Legacy `orphans.worktrees` remains readable and is computed on deep runs as the
`unleased` population. The console labels cards “Linked worktrees,”
“AWA-managed,” “Active,” and “Problems”; it never displays an orphan count as
the total “Worktrees.”

### 7. Cleanup authority does not change

Neither a receipt, adoption event, attestation, lease, heartbeat, nor integrity
row authorizes removal. Existing active-root, session, Git registration,
content/ignored-state, recovery, operation-state, branch-safety, and explicit
operator authorization gates remain independently mandatory. Kernel-off guard
behavior, primary denial, linked-worktree allowance, and heartbeat semantics
are unchanged.

## Why

Cursor exposes post-start `sessionStart` but no AWA-controlled pre-create API.
Treating that platform boundary as permanent non-adoption would contradict the
native Worktree environment being AWA's default entry path. Post-entry exact
registration closes the gap without inventing pre-entry proof or making the
engine load-bearing for entry or shell safety.

Reusing lifecycle adoption keeps one lease/event/attestation authority.
Expected-identity validation under the collision lock closes its prior
resolve-before-lock window. Distinct receipts avoid weakening the ensure
handoff into an overloaded multi-root history store.

Observation-led discovery and named populations are the minimum honest metric
correction. A single “Worktrees” card cannot simultaneously mean total,
managed, active, and orphaned.

## Alternatives considered

1. **Treat native worktrees as an acceptable platform limitation.** Rejected:
   the documented default would remain unregistered and invisible.
2. **Forge an ensure handoff at native `sessionStart`.** Rejected: it would
   claim pre-entry intent that did not exist and could overwrite another root's
   pending handoff.
3. **Adopt from the heartbeat writer or shell guard.** Rejected: hook ordering
   is not guaranteed, the guard must stay thin/kernel-first, and shell use must
   not become conditional on engine state.
4. **Automatically repair every lease/SQLite asymmetry.** Rejected: ambiguous
   state may represent another actor or corrupted identity. Only exact
   one-to-one repair is safe.
5. **Rename only the console card.** Rejected: lease-seeded discovery would
   still omit the failed-UAT shape and the count would remain uncomputed.

## Consequences

- Native Cursor worktrees can become AWA-managed after exact local validation,
  with one adoption and per-session evidence under concurrency.
- Session entry remains quiet and available when the engine fails.
- Deep integrity can observe active unleased roots and exposes honest,
  backward-compatible worktree populations.
- Registration performs additional bounded local Git and state checks during
  `sessionStart`; uncertainty intentionally leaves the root unadopted and
  non-green.
- Existing accepted plans and ADRs remain byte-identical. No release, host
  wiring, installation, activation, UAT acceptance, or cleanup is authorized
  by this draft decision.

## Live-state verification record

Read-only revalidation on 2026-09-23 established:

- source, local main, and remote main at
  `dcd11dc1fef92f6f845a7ea5d878e89decdbc23a`, with no open AWA PR;
- installed AWA v1.8.0 at
  `60ae49b4b118211d4702d9297e3f479222f45cc0`;
- a clean, registered linked native-UAT root at the expected source HEAD, with
  an active heartbeat but no on-disk lease, matching SQLite lease/event,
  current-session record, or native-entry receipt; and
- private integrity `orphans.worktrees=0` while the separate dashboard
  inventory observed linked worktrees, proving the console card was neither a
  computed total nor an honest orphan population.

The operator explicitly accepted a recreated preservation copy after the
original root disappeared during reconnaissance. That replacement remained
unleased and unadopted; its pending ensure handoff is not treated as native
entry proof and does not authorize cleanup.
