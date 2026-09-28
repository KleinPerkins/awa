# ADR 0025 Body B execution ledger — 2026-09-27

This ledger is append-only during execution. Accepted ADRs, frozen plans,
Body A schema/protocol bytes, and no-touch surfaces remain unchanged.

## Entry 001 — authority and exact baseline

- Original ADR 0025 implementation and implementation-delivery GO remains the
  sole implementation authority.
- Body A reviewed head:
  `81a881b83a2fbe83c9dc0cac0f698202cb43cf1c`.
- Body A governed squash merge and Body B baseline:
  `d336dfe1170df3fa5aefb8ec85b2d1e7539359f6`.
- PR #176 required checks passed, reviewer App approved the exact head, and
  reviewer App performed the merge.
- Remote `feat/adr-0025-body-a` was deleted; the linked execution worktree was
  retained clean.
- Body B root:
  `/Users/laurence.duggan/.cursor/worktrees/awa/4u64`.
- Body B branch: `feat/adr-0025-body-b`.
- Local identity:
  `KleinPerkins <49759187+KleinPerkins@users.noreply.github.com>`.
- Session lock: `env:adr0025-body-b-4u64-20260927`, held by this session.

Fresh authority hashes:

```text
ADR 0025                    dabac24ccb8097888a485ef55fd9a5b83eaa1ec87976387f8ba7f834e3a8ea1f
v3 plan                     d5b03f0364a77ccd8877d88dacb0e52683e8407ba014b0e3adc89cbf22276ab8
ADR index                   d79f6a9fe818ea978cde3e33184eeac5a402859e63e1c79cf7a964a5bc774190
plan index                  d2e45c34adcb5591903c9f410620557d33668c16e304ac621b9624cfc1e03632
canonical SQL               221aaf6680b50ca8f6c8c2cf024acbedbf5273b90c8c5625bcc4100c448d5ede
superseded v2               03aff346283c2809d9bab392120972de97bd14b5879e01448a8af734becf8b9b
ADR 0020                    f0911b0a85e85b6dc1d616fa6f092d33f9002e9c8d9bc5bf2edda4a927a95a98
ADR 0023                    71476602db37828c80503f05790a57aa587572cef1e800cfa42b2d32e86a0051
ADR 0024                    cecca6d380d446b91af00a4e5aea44282c4b9633b518a638967fcbeb4de38911
frozen first-prompt v1      e3bf9182e4e16411ab1424123a7200b3f6ec0dd4e09429237256a5601dcb6bd9
```

No accepted/frozen file, no-touch implementation file, live runtime, hook,
job, state, release, Skills binding, or host wiring changed during entry.

## Entry 002 — Body B seam map

- Body B consumes `RegistrationStore` typed mutation, selected-authority,
  revision, executor, resolver, and status APIs. It does not execute raw SQL
  or change the canonical schema/protocol transitions.
- Existing ADR 0024 `native_entry` parsing/Git observers remain compatibility
  inputs; Body B adds a closed later-tool event envelope and does not change
  ADR 0024 receipts or finish composition.
- Existing `lifecycle` helpers are reachable only after committed
  `OPEN_EFFECT`/`REACQUIRE_EFFECT` executor authority.
- Hook matching/projection and installed ingress remain Body C; Body B owns
  only the discriminator policy oracle and admission decision.
- ADR 0020 integrity remains alert/outbox authority. Body B emits only a
  closed redacted component for that independent evaluator.

## Entry 003 — tests-first Body B implementation

The initial focused tests were RED because the Body B modules and typed read
APIs did not exist. The implemented surfaces are:

- `engine/registration_admission.py` — bounded duplicate-rejecting event
  parser, exact one-root identity, closed tool inventory, Task/subagent launch
  denial, DIRECT R1/R2 receipt scope, and B1/E@R1/B2/R2 admission;
- `engine/registration_basis.py` — read-only canonical linked-worktree,
  Git/policy/operation/lifecycle basis collection with dirty/in-progress
  redaction and no source/index/ref mutation;
- `engine/registration_runtime.py` — member/episode orchestration, merged
  intent creation, OPEN barrier, four-action replay, unavailable/reacquire,
  reboot and same-boot takeover, structural invalidation/pending replacement,
  successor handoff, eight-lane phased tick processing, and process cleanup;
- `engine/registration_view.py` — full-envelope read-only status,
  deterministic rendering, product metrics, and a redacted ADR 0020
  component;
- read-only typed additions in `engine/registration_store.py` for exact member
  lookup, due/reboot candidate snapshots, and member-isolated authority reads;
  and
- Body B-focused tests for parser/admission, basis safety, helpers, runtime,
  fairness, status/rendering, typed store reads, privacy, and authority
  independence.

Current focused/affected evidence:

```text
78 tests PASS in 20.299s
```

Owned acceptance rows covered: A11, A13, A18, A19, A20, A24, A25, and A26.
Body B supplies product tuples/interleavings/scenarios for A02, A04, A09,
A10, A12, A14, A28, A29, and A32. The focused fixtures also cover P2-02,
P2-03, P2-04, P2-08, P2-09, P2-10, and P2-16 paths assigned to or consumed by
Body B.

No schema object, trigger, protocol edge, hook, installer behavior, host job,
live state, release/version, Skills binding, accepted/frozen document, or
no-touch authority changed.

## Entry 004 — pre-review focused head

The repository focused runner executed the complete Body B suite plus affected
Body A authority/concurrency/leaf suites:

```text
Ran 79 tests in 18.930s — OK
```

This head additionally proves:

- stock-SQLite-gated typed member/due/reboot reads without raw production SQL;
- closed byte/event parsing and exact 26-reason SQL/rendering parity;
- Task/subagent denial before basis collection or persistence;
- same-effect native and adopted reacquisition, staged pending replacement,
  explicit conflict retry, and unchanged-SUCCESS zero writes;
- process-isolated eight-lane helpers with serial selected-order open/result
  slices, two-second timeout, deterministic continuation, selected-only
  `HOST_STARVED`, failed-write suspension, and no residual workers;
- payload prompt/attachment sentinel absence from DB/WAL/SHM;
- low-space and IOERR call-site honesty;
- private immutable proof publication and final-basis replay semantics; and
- dirty/in-progress source, index, refs, and Git operation markers remaining
  byte-identical with no schedule/executor timer.

## Entry 005 — review closure and final focused head

Bugbot review iterated until clean. Valid findings fixed and regression-tested:

- stale-status scheduling after committed OPEN/REACQUIRE;
- helper/root exceptions escaping bounded service denial;
- specific blocked reason loss;
- phase-aware tick OPEN versus REACQUIRE and RESOLVED pending handoff;
- stale pending basis promotion;
- helper/append/close exception executor leaks;
- per-selected schedule continuation after one write failure;
- canonical-root alias and Git timeout reason mismatches;
- admission/status READY gate divergence;
- physical path-rename duplicate-member risk;
- slow-open and failed-yield executor cleanup;
- unsafe `fork` helper workers and non-serializable executor payloads;
- stale-basis scheduler opens;
- explicit recovery after durable cleanup failure; and
- event-derived episode-id binding.

False positives were adjudicated from accepted authority: R0 is intentionally
not runtime deployment authority; the helper deadline is one shared window
started after all lanes; lifecycle/proof readiness remains a final READY gate
so replay can repair those components first.

Final Bugbot: no bugs. Final targeted security/concurrency review: no valid
authority, privacy, serialization, or concurrency finding remains.

Final repository-focused/affected evidence:

```text
Ran 102 tests in 21.411s — OK
```

## Entry 006 — recovery and exact-head gates

Recovery established that prior session PID `59053` was absent, no test or
verification process remained, and no competing writer was active. The stale
session lock was taken over as
`env:adr0025-body-b-4u64-recovery-20260928` before further work. Body B
production and test bytes had not changed after Entry 005's clean reviews;
only this ledger was subsequently extended.

Frozen production-byte vector:

```text
registration_admission.py 763d9ae2294c8ef31f3c04eb054a0b2f18c6c85c50598e213a9d5a11d99aa35d
registration_basis.py     ac444b17ad46e3cd43f0e989d6addd6ac16688c4635642960a115fd03ee869f1
registration_runtime.py   6ed22882dd35cac692b3081930790d2291279110dec45450afc29179b2d4784b
registration_store.py     c781d879cb2c9f0df920f8be5b25315f93bd9247a06a6ce2c1864d2f528e7085
registration_view.py      4d55d3e05b0c7bb1275e01267eb9031e5779a31dd2b58a826be7324e8b4ed0ff
```

Exact-head gate results:

- `py_compile` for every Body B production/test module: PASS;
- `git diff --check`: PASS;
- protected/no-touch diff from
  `d336dfe1170df3fa5aefb8ec85b2d1e7539359f6`: empty;
- schema file and extracted canonical SQL:
  `221aaf6680b50ca8f6c8c2cf024acbedbf5273b90c8c5625bcc4100c448d5ede`;
- accepted/frozen authority hashes remained the Entry 001 vector;
- `kernel/checks/awa-contract-freeze.sh`: `awa-contract-freeze: OK`
  in 52.098s;
- `install.sh --check`: `awa --check: OK` in 52.697s;
- `make verify`: `verify: OK` in 2,285.062s; and
- `make verify-install`: `verify-install: OK`, including 5/5 installed
  guard tests in 228.921s and full lifecycle completion in 307.113s.

The first recovery invocation of `make verify` incorrectly injected the
recovery-only `DEV_SESSION_ID` into the product test environment. That filter
made the unrelated finish-recovery fixture ignore its own test session and
fail deterministically. The exact test failed with the injected filter and
passed in 3.742s without it. The one permitted normal-environment
authoritative retry then passed as recorded above. No source byte changed.

A11, A13, A18–A20, A24–A26 and Body B's P2-02/03/04/08/09/10/16 fixture
coverage remain green. No accepted/frozen file, canonical schema/protocol
surface, no-touch implementation file, live runtime, hook, job, state,
release, Skills binding, installation, or host wiring changed.
