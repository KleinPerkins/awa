# ADR 0025 Body A execution ledger — 2026-09-27

This ledger is append-only during execution. Earlier entries are not rewritten.
Accepted ADRs, frozen plans, and their index rows remain untouched.

## Entry 001 — operator authorization

Exact operator text:

> I grant IMPLEMENTATION GO to implement accepted ADR 0025 using accepted, frozen docs/plans/native-entry-durable-registration-v3.md from this exact live-main baseline:
>
> b21ce7893d9aa178aca7f9b29406c2da056c964e

> I also grant IMPLEMENTATION-DELIVERY GO for Bodies A, B, and C:
>
> - commit and push each completed body;
> - open one Draft PR per body;
> - resolve valid review findings;
> - mark each body PR ready only after its exact head is fully green and reviewed;
> - let the reviewer App approve, arm, and perform its governed squash merge;
> - continue automatically from each observed merge to the next body.
>
> This does not authorize direct merge, admin bypass, or agent-controlled auto-merge.

> I also grant R0 PREDEPLOYMENT GO for exact-head throwaway-only execution. R0 may install, repair, activate, crash, restart, and uninstall only inside isolated disposable HOME/XDG fixtures. It must not alter live protocol, real user hooks, jobs, state, Skills, ~/dev host wiring, or installed runtime.

Authorization used by this body: implementation and implementation-delivery GO
for Body A only. R0 is recorded but not exercised by Body A. R1, C1, R2,
release, installation, host activation, Skills, and cross-repository mutation
remain unauthorized.

## Entry 002 — immutable authority and baseline

- Root: `/Users/laurence.duggan/.cursor/worktrees/awa/4u64`
- Branch before execution: `cursor/09e287ce`
- Body branch: `feat/adr-0025-body-a`
- Base and initial `HEAD`: `b21ce7893d9aa178aca7f9b29406c2da056c964e`
- Initial status: clean
- Linked non-primary worktree: yes
- Primary root: `/Users/laurence.duggan/dev/capabilities/awa` (no-touch)
- Local identity: `KleinPerkins <49759187+KleinPerkins@users.noreply.github.com>`
- Session lock: `env:adr0025-body-a-4u64-20260927`, held by this session
- Commit hook: managed chained pre-commit with session-lock, identity-guard,
  data-guard, and registration-guard

Fresh local hashes:

```text
ADR 0025                    dabac24ccb8097888a485ef55fd9a5b83eaa1ec87976387f8ba7f834e3a8ea1f
v3 plan                     d5b03f0364a77ccd8877d88dacb0e52683e8407ba014b0e3adc89cbf22276ab8
ADR index                   d79f6a9fe818ea978cde3e33184eeac5a402859e63e1c79cf7a964a5bc774190
plan index                  d2e45c34adcb5591903c9f410620557d33668c16e304ac621b9624cfc1e03632
normalized acceptance body f0ece4cc4be42c6101e542d32fe8935c74d5f6c6c8e062ad45bf648fc13dc02c
canonical SQL               221aaf6680b50ca8f6c8c2cf024acbedbf5273b90c8c5625bcc4100c448d5ede
superseded v2               03aff346283c2809d9bab392120972de97bd14b5879e01448a8af734becf8b9b
ADR 0020                    f0911b0a85e85b6dc1d616fa6f092d33f9002e9c8d9bc5bf2edda4a927a95a98
ADR 0023                    71476602db37828c80503f05790a57aa587572cef1e800cfa42b2d32e86a0051
ADR 0024                    cecca6d380d446b91af00a4e5aea44282c4b9633b518a638967fcbeb4de38911
frozen first-prompt v1      e3bf9182e4e16411ab1424123a7200b3f6ec0dd4e09429237256a5601dcb6bd9
```

Fresh GitHub observations:

- Repository default branch: `main`
- Live `main`: `b21ce7893d9aa178aca7f9b29406c2da056c964e`
- PR #175: merged into `main`
- PR #175 source head: `7c3707ca232d97fa4e0bd4f790f13ae2a7eef742`
- PR #175 merge commit: `b21ce7893d9aa178aca7f9b29406c2da056c964e`
- Reviewer App approval binds source head `7c3707ca232d97fa4e0bd4f790f13ae2a7eef742`
- Exact-head checks `pr-automation / contract`,
  `pr-automation / job:repo.awa.engine-tests`, `pr-automation / source`,
  `pr-automation / tests`, and `pr-automation / verify`: `SUCCESS`

Canonical SQL was independently extracted, executed with Python SQLite
3.53.3, and measured as exactly seven tables, nine triggers, zero views, zero
ordinary indexes, `integrity_check=ok`, and an empty foreign-key check.

## Entry 003 — implementation seam map

- New dedicated authority belongs under `engine/`; it must not reuse mutable
  `engine.state.State`, whose initialization performs unrelated DDL and uses
  weaker durability settings.
- `engine.paths` supplies XDG anchors but its predecessor `df`/`mount`
  heuristic is not ADR 0025 profile authority.
- `engine.lock` supplies the existing process-scoped `flock` ABI; Body A must
  add a descriptor-verified one-member lock without changing independent
  recovery locks.
- `engine.native_entry` remains ADR 0024 compatibility input. Body A does not
  route its events.
- Existing hook-owner v3, hook projection, installer, finish, guard, cleanup,
  active-root, integrity/alert, live runtime, and host wiring are outside Body
  A and remain unchanged.
- Production schema bytes will be generated directly from the frozen
  canonical SQL block, then pinned and independently compared by A01.

## Entry 004 — tests-first implementation evidence

Initial focused RED run failed only because the new Body A modules did not yet
exist. The implemented Body A surface is:

- `engine/registration_schema.sql` — byte-exact canonical SQL;
- `engine/registration_schema.py` — fixed inventory, 97-leaf manifest, and
  install-or-exact-verify logic;
- `engine/registration_hashes.py` and `engine/registration_jcs.py` — exact
  row preimages, backlink exclusions, closed JCS, relational blob derivation,
  privacy rejection, and deterministic identifiers;
- `engine/registration_profile.py` and `engine/registration_clock.py` —
  descriptor-relative secure walking, APFS tuple/device measurement, profile
  vectors, object-swap checks, fresh free-space reads, and
  `mach_continuous_time`;
- `engine/registration_lock.py` and `engine/registration_executor.py` —
  protocol→single-member lock order, process-death release, and one-use
  anonymous AF_UNIX staged-secret transfer;
- `engine/registration_store.py` — dedicated WAL/FULL store, consistent
  authorizer, authenticated BOOTSTRAP/DATA/CONTROL APIs, operation envelopes,
  mandatory closure reads, three-phase member/effect/status transitions,
  drain/stage/cancel/adopt/advance/containment, action replay, executor
  unavailable/reacquire, successor handoff, reboot/schedule, exact reservation
  admission, and ambiguity resolvers; and
- `engine/tests/registration_harness.py`,
  `engine/tests/registration_leaf_scenarios.py`, and focused
  `test_registration_*` modules — Body A-owned deterministic fixtures. The
  raw predecessor seeding needed for generated T09 leaves is test-only and is
  absent from runtime modules.

Fresh focused evidence after implementation:

```text
45 focused Body A tests: PASS
canonical SQL SHA-256: 221aaf6680b50ca8f6c8c2cf024acbedbf5273b90c8c5625bcc4100c448d5ede
schema inventory: 7 tables / 9 triggers / 0 views / 0 ordinary indexes
generated leaf catalog: 97/97 independent fresh transaction witnesses PASS
A03 descriptor vector: 300bd90ff7f86774d939835c8d410f0b25e817c47881391fae95327610241e71
A03 profile vector: 3d6c52ff2aaa14f64a2793586c2703c7c6edcfc25033a448503e5d3ea8e539a7
A03 bad-DB-inode vector: bb26b2b3a2f69b3f826410f910c1b0920302abdd1d85962739c372fd433db3bf
process OPEN race: exactly one COMMITTED and one STALE
process lock death: subsequent acquirer succeeds without sleeps
FULL before commit: ABSENT
IOERR after commit: COMMITTED
low-free OPEN: zero audit/member/effect/status change
```

Covered Body A rows: A01–A10, A12, A14–A17, A27, A28, and A32. B/C provider
fixtures and final C1 adjudication remain intentionally outside this body.

No accepted/frozen document, no-touch source, live runtime, hook, job, state,
Skills binding, host wiring, release, tag, or installation was changed.

## Entry 005 — final focused head before repository gates

The complete focused command ran 51 tests at the current source bytes:

```text
python3 -m unittest -v \
  engine.tests.test_registration_schema \
  engine.tests.test_registration_jcs \
  engine.tests.test_registration_profile \
  engine.tests.test_registration_clock \
  engine.tests.test_registration_executor \
  engine.tests.test_registration_store \
  engine.tests.test_registration_concurrency \
  engine.tests.test_registration_mutations \
  engine.tests.test_registration_leaves

Ran 51 tests in 12.338s — OK
```

The final focused head additionally proves authenticated protocol-locked store
creation, no public runtime raw-connection surface, sealed immutable
CONTROL/DATA/executor capabilities, transaction-fresh install sampling,
operation-specific nonzero growth projections, measured stock-SQLite
NOFOLLOW/VFS identity, mandatory closure reads on every commit, selected-member
revision isolation, final-basis/action-plan equality, outcome-sensitive
counter carry/reset, and staged secret transfer integrated with executor
authority.
