# ADR 0026: Harden durable-registration deployment authority and cutover continuity
Status: accepted — 2026-09-29 (governance only; implementation and R0 NO-GO)

This is a proposed successor to
[ADR 0025](0025-durable-registration-episodes-and-tool-admission.md).
While this record is draft, ADR 0025 and the accepted, frozen
[`native-entry-durable-registration-v3.md`](../plans/native-entry-durable-registration-v3.md)
remain current authority. This record authorizes no code, test, PR, R0,
installation, release, or rollout action. If and only if the owner accepts
this record, it supersedes ADR 0025; ADR 0025 remains byte-identical.

## Context

The completed implementation bodies merged through
[PR #178](https://github.com/KleinPerkins/awa/pull/178). Live `main` is merge
commit `8356a60cb30ea02953149f9bea61fd1c04f2c7de`; its tree is byte-equal to
implementation head `b853a6bdb59d73d03c1410108830fb6a6c4bcf51`.

A schema-valid final full-change swarm and verifier examined that
implementation head. Shipping clearance failed with `partial_rollout=true`.
That result is not a deployment-reach statement. It records incomplete and
unsafe implementation/evidence closure. The Deep-band review consolidated
exactly twelve unique P1 blockers:

1. exact-byte acceptance and promotion authority was weaker than v3;
2. implementation, delivery, R0, release, install, Skills, host, R1, C1, and
   R2 authorities were not independently named;
3. persisted semantic closure and global reservation charging were
   insufficient;
4. canonical SQL had to change to permit narrowly fenced DRAINING recovery;
5. no finite MARK/REACQUIRE reserve or exhaustion-to-CONTROL boundary existed;
6. receiver generations and denial continuity were not bundle-complete;
7. Python import and observable inventory authority were incomplete;
8. R0 fixture ordering and owner signing were not enforceable;
9. cut C1–C3 switch/rollback could strand the deny-capable receiver;
10. C5 completion could skip staged REACQUIRE custody;
11. same-boot recovery/cursor/R1 scope and two-ack transfer were incomplete; and
12. R0 overclaimed no-live-change evidence.

Bugbot independently reproduced the receiver-cutover failure. The six unique
P2 blockers are: boolean/integer confusion; unbounded deep JSON failure;
process-held fairness collapse; non-monotonic ambiguity resolution;
duplicate-ensure/stale-observation regression; and impossible atomic
publication/cleanup plus underdefined authority-preimage claims.

A separate Security Review reported no medium-or-higher findings. That is
useful evidence about the paths it examined, not a vote and not clearance. It
is contradicted on the listed paths by the verifier's source traces and cannot
erase them.

## Decision

### 1. Replace canonical SQL v1, retain the closed semantic budget

The reviewed implementation disproved v4's prior “canonical SQL unchanged”
premise. V4 therefore defines canonical registration SQL v2 by one
byte-exact, extractor-executable transformation from v3's frozen SQL v1
bytes. SQL v2 SHA-256 is:

```text
b97f02ef67d48886f917368fa420fda0c5dd5942441b23a190732e3cc45106c8
```

Independent extraction and execution produce exactly seven tables, nine
triggers, zero views, zero ordinary indexes, `integrity_check=ok`, and an
empty foreign-key check. The generated leaf-key manifest remains exactly
ninety-seven because no trigger, operation, transition, selector/reason, or
outcome key is added; DRAINING recovery is a newly fenced mode predicate
inside the existing `mark_unavailable` and `reacquire` leaves. Independent
WRITABLE and DRAINING predicate-kill vectors are mandatory, so the unchanged
leaf count cannot hide an untested subpath.

The correction adds no relation, trigger, durable phase, implementation body,
transaction class, effect outcome, operation kind, runtime reason, or leaf
key. It retains exactly:

- three member phases, four protocol modes, three effect outcomes, and three
  transaction classes;
- twenty-four operation kinds, twenty-six runtime reasons, and three
  implementation bodies;
- v3 lock order, single-root M1, Task/subagent denial, and the same explicit
  unsupported residuals; and
- independent guard, finish, active-root, cleanup, and ADR 0020 integrity
  authority.

The accepted v3 bytes and SQL v1 source remain untouched. The linked v4 plan
contains the normative SQL-v2 transformation convention, fixed vectors, and
test evidence. SQL v2 is fresh-store-only for the verified predeployment
state; discovery of an authoritative SQL-v1 registration store stops without
mutation and requires a separate migration decision.

### 2. Persisted bytes become authority only after fresh semantic closure

Schema validity and a stored hash are necessary but not sufficient. Before a
protocol row, episode, member, effect, action chain, status row, operation
witness, DIRECT receipt, or staged tuple authorizes admission, helper I/O,
CONTROL, cutover, or ambiguity resolution, the typed owner must rederive its
hash from the exact canonical preimage and validate all participating
relationships, backlinks, JCS blobs, action ordering, phase/outcome closure,
generation/capability binding, and selected descendant lineage.

Any mismatch is non-authority. Where the existing store can commit it, the
installer attempts the existing containment path; otherwise AWA reports only
observable unavailability through the independent ADR 0020 path. It never
normalizes corrupt state or claims a denial that the receiving seam did not
emit.

Every newly created effect must also satisfy semantic reservation floors
before persistence and again before use:

```text
base outcome closure =
  4 * 8,192-byte APPEND_ACTION + 16,384-byte CLOSE = 49,152 bytes

bounded recovery =
  3 * (8,192-byte MARK_UNAVAILABLE + 8,192-byte REACQUIRE_EFFECT)
  = 49,152 bytes

outcome_reservation_bytes >= 49,152 + 49,152 = 98,304 bytes

successor_reservation_bytes >=
  max(PROJECTED_DB_BYTES["INVALIDATE_REQUESTED"],
      PROJECTED_DB_BYTES["REPLACE_PENDING"],
      PROJECTED_DB_BYTES["HANDOFF_RESOLVED"])
  = 32,768 bytes
```

SQL v2 enforces both minima. Each MARK/REACQUIRE consumes exactly 8,192 bytes
from the existing outcome reservation, and immutable audit count plus summed
projection permit at most six recovery operations in alternating,
state-machine-valid order. The seventh recovery operation refuses with zero
write and returns one closed, process-memory-only typed
`RECOVERY_RESERVE_EXHAUSTED` result binding the exact protocol/staged epoch,
member/effect/status hashes, audit count, and consumed/reserved bytes. It is
not a persisted reason, notice, row, or authority.

Ordinary runtime cannot construct CONTROL and therefore cannot enter
containment. It renders only the existing honest `CONTAINMENT_UNAVAILABLE`
response and sends a closed redacted component to ADR 0020, which reports RED;
neither output claims containment committed. Only during separately
authorized installer-owned cutover/reconciliation may Body C's already
authenticated `StoreControlAdapter` consume that exact typed result and
attempt existing `ENTER_CONTAINMENT/STORE_FAILURE` against the same hashes.
That CONTROL transaction uses the existing control reserve. Actor text,
ordinary runtime, or the typed result alone never obtains CONTROL. No column,
operation, reason, or outcome is added.

Free-space admission never trusts a raw global sum of persisted reservation
values. Until an effect's selected closure is semantically validated, each
unclosed effect is conservatively charged at the existing SQL maxima:
16 MiB external + 1 MiB outcome + 1 MiB successor = 18,874,368 bytes; each
resolved-current successor is charged at 1,048,576 bytes. Corrupt low values
can therefore only deny or contain; they cannot lower required free space.

Online semantic closure remains bounded by direct references. In addition to
the current protocol/member/status/effect/episode/action rows, it validates
the exact first-effect operation pair, direct protocol predecessor, current
write backlinks, predecessor/supersession companion, ADOPT lineage/staged
epoch companion, and directly referenced outcome/operation rows. It performs
no history scan. A persisted effect below either floor or with any companion
mismatch is non-authority and cannot authorize OPEN, action, close,
successor, adoption, admission, or free-space reduction.

### 3. Owner authorization binds the complete deployment identity

Keep `awa-registration-candidate/v1` and its logical candidate-digest
semantics unchanged. Add `awa-registration-direct-receipt/v3` and a signed
`awa-registration-owner-gate/v2`. The receipt binds one complete immutable
receiver bundle, bundle generation, transitive import manifest, complete
denial-proof vector, installed bytes, wrapper/runtime/interpreter identity,
interpreter capability probe, installer identity/capability, exact
inventory/projection, and signing
contract/key enrollment. The gate signs a domain-separated
`direct_receipt_body_hash` over every v3 receipt field except
`owner_gate_digest`, then repeats the security- and scope-critical values.

Owner signing is concrete, free, offline, and non-networked:

- algorithm: OpenSSH `ssh-ed25519`;
- stock executable: path-qualified `/usr/bin/ssh-keygen`;
- namespace: `awa-registration-owner-gate-v2`;
- principal: literal `KleinPerkins`;
- signed bytes: exact `JCS(gate) + LF`;
- future contract:
  `contracts/awa-registration-owner-signers.v1`, a regular repository file
  containing exactly one OpenSSH allowed-signers line for that principal,
  namespace, and authorized public key; and
- verification: `ssh-keygen -Y verify` against the exact descriptor-bound,
  hash-bound installed contract.

The v2 gate includes the contract path hash, contract content hash, public-key
SHA-256, OpenSSH `SHA256:` fingerprint, and an exact key-enrollment digest.
Acceptance and implementation delivery remain blocked until the owner
separately authorizes that exact future public-key fingerprint and contract
artifact. No public key, private key, signature, or contract is created now.
The private key never enters the repository, bundle, receipt, database,
runtime state, logs, or environment.

The bundle contract cannot authorize itself. A separately owner-authorized,
machine-local `awa-registration-owner-key-current/v1` receipt under the AWA
state root is the current trust anchor. The verifier requires its ACTIVE
principal/namespace/key/fingerprint/contract/enrollment fields to equal the
gate and bundle before invoking OpenSSH. Delivery, release, install, and host
activation authorities name that exact enrollment hash.

Rotation requires a successor contract hash and a fresh explicit enrollment
of the new fingerprint. Revocation removes the old key only through a
separately authorized successor contract; prior receipts remain historical
evidence but cannot authorize new work. Wrong principal, namespace, key
algorithm, fingerprint, contract path/hash, duplicate principal, altered
gate bytes/LF, or revoked contract refuses.

The receipt remains non-circular: its `owner_gate_digest` hashes the verified
gate; the gate hashes the receipt body without that one field. CONTROL is
constructed only after signature verification and fresh equality of the
bundle, manifest, installed bytes, wrapper runtime, signer contract, and
presented installer identity/capability. V1 gates and v2 receipts remain
strictly readable historical evidence but cannot authorize v4 R0, R1, or R2.
`harness_root_hash` is non-null only for `R0_THROWAWAY`; root/member are
non-null only for R1; all three are null for R2.

The v4 plan owns one closed preimage registry for every new authority hash:
external interpreter, import manifest, bundle/wrapper/projection/active
pointer, denial/readiness, enrollment/public-key identity, receipt/gate,
same-boot cursor/host tick, and R0 manifest/evidence. It fixes literal schema,
domain, canonical JCS fields, path/order/nullability, and vectors. Bundle
payload paths are relative and in-root. The external interpreter is an
installer-selected explicit normalized absolute path supplied through
separately authorized candidate/installation input—never PATH, cwd,
environment, `sys.executable`, or a fixed product path. Its descriptor-bound
record and isolated capability-probe hash enter bundle, wrapper, launcher
config, receipt, gate, projection, active pointer, readiness, and R0
authority.

### 4. Staged receiver readiness is deny-only until generation advance

Receivers install as immutable, generation-qualified bundles. One bundle
contains the receiver bytes, isolated launcher, all runtime files, canonical
transitive import manifest, DIRECT receipt, config, and bundle-local
projection. Installing N+1 never writes or replaces any N bundle or receipt.
The one atomic active projection selects an exact bundle generation, bundle
digest, bundle-local projection, receipt digest, external-interpreter record,
and capability-probe hash. Bundle N remains immutable and restorable until
C7.

The N+1 receiver gets one non-persistent deny-only readiness path. It may open
only when all of these are freshly exact:

- current protocol is DRAINING at generation N;
- the receipt and candidate equal the immutable staged N+1 tuple;
- staged schema equals canonical SQL v2;
- installed receiver, wrapper/runtime/interpreter/probe, inventory, matcher,
  transitive import manifest, signer contract, installer, and profile/device
  measurements equal signed authority; and
- a canonical sorted proof vector contains both direct-receiver and shadow
  installed-seam denial evidence for every unique installed observable tuple
  and serializer seam.

The observable inventory key is exactly
`(event, server_or_empty, discriminator, serializer_schema)`. The signed
`role` is returned as policy, not included in lookup identity. Duplicate
observable keys—including duplicates with conflicting roles—refuse
activation. Task/subagent role remains the first deny before ordinary
admission.

Every external hook/admission/startup/tick interface remains deny-only and
can never return ordinary-tool allow, launch ordinary registration work, or
advance the protocol. The sole internal exception is installer-controlled
staged recovery under the member lock: SQL v2's exact DRAINING
MARK_UNAVAILABLE/REACQUIRE paths and the frozen helper plan. RECEIVED/
ACTIVATED transfers only custody; internal helper I/O begins only after
ACTIVATED, member-lock ownership, and complete semantic closure. Ordinary
admission remains impossible until ADVANCE plus current/full revalidation.

While the old receiver is still the active projection, the installer
shadow-invokes the exact
installed wrapper/router/serializer bytes against the signed candidate bundle
for every installed observable tuple and requires the expected seam-valid
denial vector. **Cut C1** installs N+1 without touching N authority. **Cut
C2** stages and proves N+1 while N remains active. At **cut C3** the
file-authority lock atomically switches only the active pointer while N
remains enabled/restorable, runs the complete post-switch vector again, and
disables N only after it passes. On failure it atomically restores the N
pointer, revalidates N, and only then may use existing CANCEL_DRAIN where
legal. N is retained until **cut C7**. Ordinary admission becomes possible
only after `ADVANCE_GENERATION` makes N+1 current.

Cut labels C0–C7 are restart coordinates inside authorized R0/cutover work;
they grant no authority. They are distinct from **C1 shipping clearance**,
which remains evidence-only.

### 5. Profile, imports, and inventory are measured rather than inferred

Before gate bytes exist, the installer descriptor-walks the supplied
interpreter path/ancestry, measures complete identity/content, and runs a
closed read-only probe under `-I -S -B`. It requires Darwin/macOS, the exact
Python API surface used by v4, SQLite `>=3.51.3`, source-id/compile-options/
VFS/pragmas, `Connection.setconfig`, `SQLITE_DBCONFIG_DEFENSIVE`, and every
existing profile requirement. Unsupported candidates refuse before
persistence or signature.

Current and staged protocol candidates are each freshly bound under the
protocol lock to an exact `ProfileBinding`, APFS tuple, `storage_dev`,
external-interpreter record, and capability-probe hash. Every positive cut,
receiver open, and launcher exec remeasures the applicable binding. A cached
profile hash, candidate object, receipt string, or PATH lookup is not proof.

All registration Python entrypoints use an absolute, measured interpreter and
an isolated launcher. Before the first product import, the launcher verifies
a closed, path-qualified transitive import manifest generated from the exact
entry module. The generator recursively resolves static AWA imports,
automatically includes every package initializer, rejects unresolved/dynamic
product imports, and records relative path, mode, size, and content hash.
Runtime import enforcement permits no AWA-root module outside that manifest.
This is generator-owned—not a caller-enumerated file list.

The entrypoint ignores ambient `PYTHONPATH`, `PYTHONHOME`, `PYTHONSTARTUP`,
cwd, user site, and import shadowing; it inserts only the measured bundle root
after verifying the manifest. Launcher config names the signed interpreter
path and execs only it. The launcher descriptor-remeasures interpreter
ancestry/file/content and capability immediately before first product import;
upgrade or drift fails honestly unavailable without fallback. The measured
interpreter/capability, launcher, exact manifest bytes/hash, package
initializers, and all manifested runtime bytes enter `wrapper_runtime_hash`
and signed deployment authority.

Admission carries the unique observable key
`{event, server_or_empty, discriminator, serializer_schema}` from receipt
through dispatch and obtains `role` only from the signed matching inventory
entry. Matching by discriminator alone is forbidden.

### 6. Executor ownership and ambiguous completion converge monotonically

A committed OPEN, REACQUIRE, or ADOPT grant has only two legal caller-visible
ends: a live opaque execution capability is returned, or the same owner,
while retaining the member lock, clears the executor through the existing
exact `MARK_UNAVAILABLE` transition before yielding. SQL v2 narrowly permits
existing DATA-class `MARK_UNAVAILABLE` and `REACQUIRE_EFFECT` while current
mode remains DRAINING only when current staged epoch, ADOPT lineage, member
helper generation, executor/status CAS, staged runtime/writer/profile
capability, action plan, and member lock all agree. No other DATA operation
is legal in DRAINING.

If cleanup cannot commit, process death releases the lock. A bounded
same-boot recovery selector runs before due work: event/startup/retry directly
checks its named member; tick selects bytewise member-id lanes in batches of
eight with restart-stable continuation. The existing private host-tick
receipt carries a non-authoritative cursor bound to boot, protocol, selected
status/token snapshot, last examined member, outcome, and wrap bit. Busy-live
locks advance the cursor without mutation, so low IDs cannot starve later
members; end-of-set wraps deterministically. Missing/stale receipt restarts at
the lowest ID. Successful nonblocking member-lock acquisition—not cursor,
PID, or age—authorizes exact token takeover before any new I/O. The cursor
never authorizes work or cleanup.

R1 performs one read-only scope preflight before any same-boot, reboot, due,
or helper mutation. It returns `outside_scope_same_boot`,
`outside_scope_due`, and `outside_scope_reboot`; any true flag refuses the
whole tick.

Staged secret transfer is a bounded two-ack state machine. `RECEIVED` means
the receiver validated and holds the frame but cannot use it while the sender
holds the lock. The sender then irreversibly disables its local capability,
releases the lock, and starts one fixed activation deadline. The receiver
must acquire that exact member lock, revalidate executor hash and complete
semantic closure, and only then send `ACTIVATED` and perform I/O. Possession
without the lock is non-authority. The sender never reacquires or uses the
secret after release; it zeroes on `ACTIVATED` or timeout. Timeout/lost ack
routes the next lock owner through existing MARK/REACQUIRE. Duplicate/stale
acks and stale/cleared secrets are no-ops or rejects. Thus no wait cycle,
livelock retry, or dual-use window exists.

C5 restart always reruns adoption reconciliation. Completion is exactly the
existing ADVANCE predicates plus no unresolved transfer obligation:
no in-flight member has old helper generation, no executor has old
generation, no incompatible pending effect remains, no clean REQUESTED effect
remains, and every committed grant whose resulting status has staged
`executor_generation` is closed. Today those grants are ADOPT_EFFECT and
DRAINING REACQUIRE_EFFECT; DRAINING OPEN remains forbidden. Closure requires
exact audit/status/token proof of returned-and-ACTIVATED custody or a durable
MARK_UNAVAILABLE clear. Commit-before-return death for either operation is an
unresolved obligation recovered in deterministic batches beyond eight.
ADVANCE denies while any obligation remains. Stable RESOLVED rows without
pending work and blocked REQUESTED rows require no adoption and are explicitly
excluded. A staged row or ADOPT kind alone is not completion evidence.

Ambiguity resolvers treat one semantically valid immutable operation row as
the monotonic commit witness. They compare it with the current target or a
later semantically valid tuple whose write sequence is greater; no unbounded
history traversal is required. A later valid transition cannot make an
earlier committed operation look absent. Exact duplicates converge to
zero-write no-ops; only an absent operation plus the exact predecessor retries.

### 7. Bound parsers, fairness, creation, and file publication

- Integer authority inputs require `type(value) is int`; booleans are never
  accepted as integers.
- A fresh database is initialized and fully verified in one private
  same-directory candidate, then atomically installed under the creation
  lock. Before rename, failure proves canonical absence. After rename, the
  publisher reopens and classifies only `ABSENT | COMPLETE | UNAVAILABLE`;
  it never promises rollback to absence.
- Raw JSON receives a bounded non-recursive depth/node scan before decoding;
  deep input and `RecursionError` produce a seam-valid parser denial when the
  wrapper is functioning.
- Each selected fairness lane owns only its member lock in its worker. Eight
  lanes are observably concurrent; no parent-held member capability is
  serialized or transferred to a child.
- R1 uses a typed canary selector that returns at most the authorized member
  and separately reports any out-of-scope due/reboot work. It never asks the
  eight-candidate API for nine.
- Every atomic publisher preserves the primary failure, records cleanup and
  residue observations separately, fsyncs required directory changes, and
  lets startup reconciliation classify/remove only descriptor-proven
  same-operation residue. It does not claim perfect cleanup after uncertain
  rename or directory-fsync failure.
- Every mutation resamples the live basis after acquiring the member lock.
  A stale event may become an exact no-op but cannot regress a newer basis.

### 8. Evidence and owner gates remain non-circular

The linked
[`native-entry-durable-registration-v4.md`](../plans/native-entry-durable-registration-v4.md)
owns the complete finding map, three-body worklist, A01–A29/A32 ledger, exact
vectors, deterministic fault/interleaving matrix, and real throwaway
process-kill R0.

V4 restores v3-grade exact-byte acceptance. One normalized digest binds, in
explicit path order, the complete ADR 0026 file, exact ADR 0026 index row,
exact v4 index row, and complete v4 plan. A domain-separated,
length-framed algorithm replaces only the four draft/accepted status-token
spans with one sentinel. A checker binds exact pre-hashes, mechanically
computes the only permitted post-hashes, proves normalized digest equality,
and emits the vector for owner review. Acceptance is valid only when the
owner names that exact vector and digest. A checked status-last promotion
stages all four outputs, revalidates preimages, replaces only those tokens,
then publishes one detached receipt as the acceptance commit point. A crash
before that receipt is incomplete promotion—not acceptance—and must restore
or finish from exact pre/post hashes before any authority use. Accepted
ADR/plan bodies are immutable thereafter. ADR 0025 and v3 bytes never change;
only governed index status rows may later record their supersession.

R0 retains its predeployment-only place through one narrow, necessary
exception to v3's production receipt rule. The complete disposable fixture
is created first; all profile targets are descriptor-measured; only then are
exact gate bytes emitted and signed. No receipt, protocol row, or CONTROL
capability exists before signature verification and a second complete
measurement. The production installer cannot construct the sealed
`R0HarnessAuthority`, every R0 receiver state is deny-only, and every path
outside the disposable root refuses before write. R0 authority can never
open live state or substitute for R1.

R0 no-live-change evidence is finite and explicit. Before each cut it freezes
a manifest of the governed live protocol/state roots, installed runtime and
bundle bytes, Cursor hook files, AWA/local-jobs state, Skills binding, and
`~/dev` host overlay. It records descriptor-safe identity/mode/owner/size and
content hashes, then repeats them after the cut and binds both manifests plus
available external filesystem-write observations to the cut record. It does
not claim unobservable global absence. Every record names one closed
cut/barrier id from the v4 catalog; exact applicable set equality is required,
so “subcut” evidence cannot be omitted or ambiguously named. Any
governed-surface change, escaped write target, missing observation/barrier,
or surviving process fails R0.

The order remains:

```text
draft ADR 0026 + draft v4
-> fresh exact-byte technical review/verifier clearance
-> exact normalized acceptance vector
-> separate exact owner signing-key/allowed-signers enrollment
-> explicit owner acceptance and checked promotion of ADR 0026 + v4
-> separate exact-baseline implementation GO
-> separate exact-revision implementation-delivery authority
-> implemented Bodies A, B, C and complete exact-head review evidence
-> separate exact R0 GO and real throwaway R0
-> separately named release/tag/publication authority
-> Skills binding authority if applicable
-> separately named installation authority
-> separately named ~/dev host-wiring and activation authority
-> exact R1 canary GO
-> C1 evidence-only shipping clearance
-> exact R2 rollout GO
```

No step implies another. Implementation GO does not authorize commit, push,
Draft PR, readiness, merge, R0, release, install, Skills, host wiring, or
rollout. Delivery authority names exact revisions and preserves reviewer-App-
only approval, auto-merge arming, and merge; agents never call or pre-arm
auto-merge. Release, install, Skills, and host activation each require their
own exact artifact/revision authority. C1 remains evidence-only. The current
implementation and current R0 script provide source evidence but no shipping
authority.

## Why

- Binding the full deployment identity closes the proven owner-gate gap
  without changing logical candidate identity or adding networked/paid
  signing infrastructure; it uses stock offline OpenSSH.
- A deny-only staged receiver uses the existing DRAINING/staged authority and
  preserves fail-open honesty; it avoids both a fifth protocol mode and a
  premature ordinary-admission path.
- Semantic revalidation and deterministic descendant recognition make the
  existing seven tables sufficient. A new certificate, journal, or pointer
  table would duplicate authority.
- Lock-authorized executor recovery is stronger and simpler than PID or
  process-liveness inference.
- Atomic fresh install and bounded parsers correct concrete failure paths;
  they do not create migration, GC, Rescue, or broader-platform scope.

## Consequences

- The existing merged implementation is not rollout-ready and may not be used
  as R0, R1, C1, or R2 evidence without the v4 corrections.
- Hook rows remain `failClosed:false`; total hook/runtime absence still fails
  open and remains an explicit residual.
- Same-UID raw SQLite, process memory inspection, manual/external work,
  unsupported platforms/devices/VFS/power behavior, no-event surfaces, and
  notification visibility remain unsupported exactly as in v3.
- Canonical SQL v2 replaces SQL v1 for future implementation; all
  accepted/frozen governance bytes and SQL v1 source remain unchanged.
- More checks occur before authority use and cutover, but no new persistent
  lifecycle or product feature is introduced.

## Live-state verification record

Read-only verification on 2026-09-29 established:

- live remote `main` and local documentation-branch base are exactly
  `8356a60cb30ea02953149f9bea61fd1c04f2c7de`;
- PR #178 is merged with source head
  `b853a6bdb59d73d03c1410108830fb6a6c4bcf51`, and the two commits have equal
  trees;
- the linked worktree was clean, had no index lock or competing session lock,
  and used the canonical KleinPerkins noreply identity plus executable managed
  pre-commit chain before documentation mutation;
- accepted ADR 0025, frozen v3, frozen v1, superseded v2, and inherited ADRs
  0020/0023/0024 matched their recorded protected hashes;
- stock `/usr/bin/ssh-keygen` is present and exposes `-Y sign`/`-Y verify`;
  no owner key, allowed-signers contract, or signature was created;
- shell Python resolved through Homebrew to
  `/opt/homebrew/opt/python@3.14/bin/python3.14`, Python 3.14.6 / SQLite
  3.53.3 with `Connection.setconfig` and
  `SQLITE_DBCONFIG_DEFENSIVE`; this is current-machine evidence, not a product
  path. `/usr/bin/python3` resolved to CommandLineTools Python 3.9.6 / SQLite
  3.51.0 without either API and is explicit rejected evidence; and
- current source traces show the concrete gaps in
  `registration_store.py`, `registration_host.py`,
  `registration_installer.py`, `registration_projection.py`,
  `registration_runtime.py`, `registration_admission.py`,
  `registration_schema.py`, `registration_receiver.py`, the registration
  shell wrappers, and
  `live-verify/native-entry-durable-registration-r0.py`.

## Owner acceptance gate

While draft, this ADR supersedes nothing. Acceptance requires fresh exact-byte
review/verifier clearance, checker-produced allowed pre/post hashes and
normalized digest, and an explicit owner decision accepting that exact vector
for ADR 0026 and v4. It is blocked until the owner separately authorizes the
exact future ssh-ed25519 public-key fingerprint and allowed-signers contract
artifact. Checked status-last promotion and its detached receipt must then
succeed. Acceptance approves only architecture and plan bytes. A separate
implementation GO against an exact refreshed baseline remains mandatory.

Without the exact acceptance receipt and each later separately named
authority applicable to an action, the exact instruction is **NO-GO**: do not
change implementation, tests, contracts, runtime, hooks, jobs, state,
delivery, installation, release, Skills, host wiring, R0, R1, C1, R2, or
rollout.
