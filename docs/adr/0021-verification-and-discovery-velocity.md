# ADR 0021: Adopt a measured, layered, safety-preserving verification architecture
Status: accepted — 2026-08-29 (owner sign-off)

*Plain-language summary: AWA's tests are slow because safety-heavy behavior is repeatedly exercised
through thousands of short-lived Python, shell, and Git processes—not because test discovery is
slow. AWA will keep every safety guarantee while making verification one measured, de-duplicated
graph: quick lanes for documentation and changed-surface feedback, one complete pre-PR lane,
process-isolated module sharding only after serial-equivalence proof, and selective install/release
rehearsals. Display-only discovery may use a fast inventory path, but no cached result may authorize a
guard, finish, cleanup, lifecycle, or deletion decision.*

## Context

AWA's regression surface grew by design as root-bound finish, state-aware primary maintenance, and
integrity surveillance added biting tests. The current runner still executes every engine module in
one Python process and emits only ordinary `unittest` progress. `make verify` then composes that
suite with contract, installer, and live-verify checks as a serial list. The result is safe but
needlessly expensive and opaque: agents cannot tell which module is active, often repeat proofs that
the enclosing target already performs, and may run the complete code gate for documentation-only
changes.

The performance problem is not permission to weaken AWA. Kernel-first, independent engine/kernel
guard mirrors, fail-safe uncertainty, root-bound finish durability, one-writer worktree isolation,
and real install/release seams remain authoritative. The architectural question is where each class
of proof runs and how often—not whether it still exists.

This decision relates to:

- ADR 0001, which deliberately retains independent engine/kernel guard implementations with
  subprocess parity;
- ADR 0002, which keeps AWA product behavior here and host-specific wiring in `~/dev`;
- ADR 0017, which allows repository-local documentation governance but forbids wiring doc-warden
  into AWA's Makefile/CI; and
- ADR 0020, whose integrity work added substantial regression coverage while remaining behind the
  kernel safety path.

This ADR **narrowly supersedes only** ADR 0020 §1's statement that guard source stays
byte-for-byte unchanged: Decision 6 permits an equivalence-gated internal probe-collection change in
both independent mirrors. It does **not** supersede ADR 0020's behavioral decision—no guard
relaxation, lease/path/`cd` carve-out, integrity dependency, or engine-on requirement is permitted.

### Backward-constraint result

The accepted ADR/plan indexes were checked before this decision:

- ADR 0001 and the complete guard target-precision plan keep full independent engine/kernel parity
  and target resolution. Decision 6 is excluded from multi-segment and redirected-target handling.
- ADR 0019 and the accepted fast-forward-primary plan keep the exact bare-Git maintenance grammar,
  configured-upstream binding, clean-state checks, and conservative denial. This ADR changes only
  how already-required facts may be collected.
- ADR 0002 keeps host wiring outside AWA. No lane invokes `~/dev`, local-jobs, or doc-warden.
- ADR 0017 keeps AWA documentation governance repository-local. The docs lane implements local
  checks only.
- The accepted external-hook-owner plan keeps direct/external/interpreter seams. Any installed
  layering retains biting canaries and the exact full serial fallback.
- ADR 0020 and its accepted integrity/lifecycle plan keep the kernel off-switch guarantee, status
  record, alerts, lifecycle evidence, recovery quarantine, entry handshake, and no autonomous
  deletion unchanged. The only conflict was its guard-byte freeze; the narrow supersession above
  resolves that conflict explicitly. The accepted execution-priority addendum is unaffected.

No other accepted decision or plan requires supersession.

## Live-state verification record

Verified on 2026-08-29 against GitHub `main` and local HEAD
`0390779930455273b6203676ae01437c43f8845f` (`pyproject.toml` version `1.7.3`):

1. **Discovery is not the long pole.** A fresh
   `unittest.defaultTestLoader.discover("engine/tests", pattern="test_*.py", top_level_dir=".")`
   found **1,045 tests across 60 tracked `test_*.py` modules in 0.63 seconds**. The earlier
   2026-08-25 audit found 902 tests; the 143-test increase means its module percentages are
   directional evidence, not a current baseline.
2. **Execution is process-heavy and load-sensitive.** The earlier isolated 902-test profile at
   `1c40a9a` took 2,510.605 seconds on a heavily loaded host, ended with one unclassified error and
   15 intentional router-off skips, and recorded 3.53 million involuntary context switches. It is
   valid for hotspot discovery, not a passing baseline or a claim that an ordinary run takes
   42 minutes. In that profile, finish modules carried 69.27% and guard/hook/Git modules 24.84%;
   the top ten modules carried 88.61%. One approximately 80-second guard corpus test launched 1,646
   Git processes (1,122 `rev-parse`, 432 `config`) while Git reported only 2.687 seconds of
   cumulative internal work.
3. **The runner is serial and low-visibility.** `engine/tests/run-tests.sh:22-33` invokes one
   unsharded `python3 -m unittest discover ...`, then the dashboard suite only after an unfiltered
   successful engine run. It records no per-test/module timing, active test, machine context, or
   reusable exact-source result.
4. **Every base test creates isolated state; Git fixtures are repeatedly rebuilt.**
   `engine/tests/helpers.py:33-105` creates fresh XDG directories per test, while `make_repo()`
   repeatedly runs `git init`, add/commit, branch rename, and optional remote setup. This isolation
   is correct; rebuilding the same immutable starting state through separate Git processes is the
   optimization opportunity.
5. **Contract proof is repeated.** On current source,
   `engine/tests/test_contract_schemas.py:85-92` executes the freeze checker,
   `Makefile:40-44` executes it again explicitly, and `install.sh:702-752` executes it inside
   `--check`. A current `./install.sh --check` pass took 37.26 seconds. The 2026-08-25 standalone
   checker took 19.769 seconds before later integrity additions; its current isolated cost was not
   re-run solely to author this record.
6. **Operational discovery is currently seconds, but scales serially.** A current
   `dashboard/emitter.py --root ~/dev` pass took 8.34 seconds.
   `dashboard/emitter.py:162-192,212-324,569-688` eagerly performs recursive `du`, worktree role,
   head, status, divergence, log, branch, and environment probes serially. Each bounded timeout is
   additive across repositories, worktrees, and orphan branches.
7. **The complete transition rehearsal is already correctly separate.**
   `live-verify/trial-runner/README.md` documents a typical two-to-three-minute isolated rehearsal,
   supports filtered transitions, and intentionally keeps it out of `make verify`.

No complete 1,045-test run was started for this documentation-only decision. Milestone 1 of the
companion plan owns a controlled current baseline before any speedup is accepted.

## Decision

### 1. Verification is one explicit directed acyclic graph with one owner per proof

AWA will replace list-like orchestration with named, composable gates whose dependencies are
visible and whose successful result is executed at most once per invocation. The graph has these
closed lanes:

- **`docs`** — allow-listed Markdown/governance-only changes; repository-local format, link, index,
  and diff checks only. Classification evaluates the status plus both old and new path of every
  add/delete/rename/copy/type-change, rejects symlinks/special files, and broadens on any
  non-allow-listed side. An operator may separately invoke host-owned doc-warden, but AWA does not
  import or call `~/dev` tooling.
- **`focused`** — explicitly selected changed-surface tests for developer feedback. It is always
  labeled non-authoritative.
- **`pre-pr`** — the complete discovered engine inventory, dashboard suite, exactly one required
  source contract-freeze execution, static installer checks, and live-verify discovery.
- **`install`** — direct/external install lifecycle and installed-copy seams, required only when
  installer, packaging, hook ownership, or runtime projection changes.
- **`release`** — affected PM/router trials and complete transition rehearsals, selected by the
  release surface rather than run on every edit.

Unknown, untracked, or mixed change classes select `pre-pr` or a stricter affected lane. Neither
`docs` nor `focused` may be described as sufficient to merge or release. `make verify` remains the
ordinary full local/pre-PR entrypoint; lane-specific targets are additive and plainly named.

The end-state `pre-pr` graph executes the source contract freeze once. Separate entrypoints may
prove that their wiring still reaches that canonical node, but must not rerun the same source-context
proof within one graph invocation.

### 2. Measurements and receipts are productively visible but never authorize a skip

The canonical runner will report the active module/test, elapsed wall time, per-test and per-module
durations, outcome counts, and bounded process/resource context. It will optionally emit a closed,
machine-validated `awa-test-receipt/v1` JSON result containing the exact clean HEAD, runner digest,
discovered-test inventory digest, lane, tool versions, timings, and outcomes.

A dirty source tree or any mismatch between before-run and after-run source identity is recorded as
unstable and non-reusable. A receipt is evidence for humans and agents only: the first implementation
does not automatically suppress a gate, and no AWA safety or lifecycle decision consumes it. Future
automatic reuse requires a superseding ADR.

### 3. Parallel execution is process-isolated, deterministic, and serial-equivalent

Engine modules may run concurrently in separate Python processes because tests mutate process-global
environment and construct Git/XDG state. In-process threaded test execution is forbidden. The
orchestrator may coordinate child processes without sharing test state, but each module receives its
own interpreter and inherited isolation contract. Duplicate test IDs, worker timeout/signal/crash,
malformed or partial output, and missing/late results fail the overall run.

The serial path remains available. A multi-process path becomes the `pre-pr` default only after:

1. serial and parallel runs discover the same test IDs;
2. exact outcomes and intentional skips match;
3. repeated parallel runs show no ordering, state, output, or cleanup flake;
4. worker crash/timeout/partial output fails the whole run; and
5. measured 1/2/4-worker results choose the smallest useful concurrency rather than assuming the
   largest worker count is fastest.

### 4. Combinatorial coverage moves below expensive boundaries; safety seams stay biting

Full decision corpora remain against the independent engine and kernel guard implementations.
Pure/combinatorial cases may execute through a batch or in-process decision interface when the same
case data and result oracle are reused. Source-hook, installed-hook, owner-mode, subprocess,
durability, crash, malformed-input, and kernel-off boundaries retain representative end-to-end
canaries chosen to bite on interpreter, installation, wrapper, and physical-I/O failures.

Installed-copy corpus reduction is allowed only after byte-identity plus representative execution is
shown to catch installer/interpreter differences. The exact full installed corpus remains a named
serial fallback and is required by the affected install lane; byte/interpreter drift refuses the
layered path. Coverage is never removed merely because a test is slow.

### 5. Fixture reuse preserves physical independence

Tests may build immutable Git seed repositories once per process and copy them into each test only
after proving independent refs, configs, hooks, worktrees, indexes, object files, and fault
boundaries. No mutable repository, object store, worktree, XDG directory, or lock is shared between
test cases. Tests whose subject is repository creation continue to build from scratch.

Production finish inventory, double-capture stability, fsync/`F_FULLFSYNC`, locking, and removal
semantics are not altered to make tests faster. Ordinary semantic matrices may inject already
established adapters, but dedicated physical durability and crash suites remain real.

### 6. Live Git context may be reused only inside one eligible maintenance decision

The guard may collect one bounded, start/end-validated Git context for the fixed Cursor session cwd
inside an exact valid ADR 0019 bare-Git maintenance decision, then reuse those values only within
that invocation. This is the live-code hotspot with repeated branch/config/ref/status/operation
probes. Equivalence tests must prove that every state-sensitive decision sees the required evidence;
detectable identity, HEAD, upstream/config, dirty-state, hidden-index, or operation drift takes the
existing uncertainty path. Unsupported or incomplete collection falls back to the existing uncached
probe path; it never converts missing evidence into an allow.

ADR 0001 target extraction is outside this optimization. Multi-segment, in-command `cd`, `git -C`,
`--git-dir`, `--work-tree`, redirected, wrapped, malformed, and otherwise ineligible maintenance
forms receive no reusable context and retain existing parsing, probing, and conservative behavior.
No classification, guard, finish, cleanup, lifecycle, or remote state is cached across commands.
Every new hook invocation reads live state again.

This is the sole guard implementation change authorized by this ADR and the narrow supersession
described in Context. If the companion plan cannot prove exact verdict, target-resolution,
engine/kernel, kernel-off, installed, owner-mode, and state-drift equivalence, guard bytes remain
unchanged.

### 7. Dashboard discovery separates safety-neutral inventory from display enrichment

Dashboard/status generation may add a fast profile that omits expensive disk-size/history
enrichment and reports those fields as not checked. Deep display enrichment may batch Git reads and
use bounded concurrency only after deterministic-output and timeout tests pass. Any cache is
display-only: it cannot feed a guard, finish, cleanup, lifecycle, reconciliation, recovery, or
deletion decision.

The existing deep/default schema remains backward compatible until a separately tested consumer
migration is complete. Honest timeout/unknown states are preserved.

### 8. Performance budgets follow controlled baselines

The initial targets are hypotheses: `docs` under 30-60 seconds, `focused` under one-to-three minutes,
and full `pre-pr` around 3.5-5.5 minutes relative to an operator-reported 12-minute execution
observation that was not a controlled baseline. `focused` has no lane-wide enforceable budget while
its selectors remain arbitrary; its timing is descriptive per invocation. Fixed-workload targets
become accepted budgets only after current-head measurements record HEAD, inventory, Python/Git
versions, machine/load context, and pass/fail state.

Timing regression starts advisory. A hard time threshold may not become merge authority until
variance is characterized and false failures under ordinary host contention are bounded. Structural
correctness and safety failures remain authoritative regardless of timing.

## Safety invariants

- Kernel-first behavior and kernel-off proof remain unchanged.
- No guard verdict is relaxed and full independent engine/kernel parity remains.
- ADR 0020's no-carve-out/no-integrity-dependency guard behavior remains; its byte freeze is
  superseded only for Decision 6's conditional, equivalence-gated internal probe collection.
- Finish warning-time/final stable-snapshot recapture, no-follow identity, locking, fsync/
  `F_FULLFSYNC`, removal journal, and recovery proof are never removed for speed.
- No mutable Git repository, refs, hooks, objects, worktree, HOME/XDG state, lock, or fault boundary
  is shared between tests.
- No cached or measured result authorizes guard, finish, cleanup, lifecycle, reconciliation,
  recovery, deletion, or a verification skip.
- No automatic lifecycle/cleanup action, paid GitHub Actions runner, new hosted CI dependency, or
  `chaos-scheduler` change is introduced.
- Python 3.9 stdlib and Bash 3.2 compatibility remain on currently supported paths.

## Non-goals

- Replacing `unittest`, adopting a third-party runner, or creating a second verification framework.
- Automatically inferring arbitrary source-to-test dependencies for the `focused` lane.
- Guaranteeing a universal focused-lane duration for caller-selected workloads.
- Changing production finish semantics, durability, or physical evidence collection to improve test
  timing.
- Persisting cross-invocation Git/safety state or letting dashboard enrichment become safety
  evidence.
- Wiring host-owned doc-warden, local-jobs, or a new CI service into AWA.

## Alternatives considered

1. **Optimize test discovery.** Rejected: current discovery takes 0.63 seconds; execution dominates.
2. **Run the unchanged suite with as many workers as possible.** Rejected: the suite is dominated by
   short process startup and scheduler contention. Unbounded workers can make loaded-host behavior
   worse and obscure shared-state defects.
3. **Delete or skip the slowest tests.** Rejected: the slowest modules cover AWA's highest-risk
   finish, guard, owner-mode, and integrity boundaries. The design moves combinatorial cases beneath
   expensive seams while preserving the seams.
4. **Require the complete code gate for every change, including prose.** Rejected: an allow-listed
   documentation change cannot alter runtime behavior. Unknown/mixed changes still fail closed to
   the broad gate.
5. **Adopt pytest-xdist or another third-party runner immediately.** Rejected for the first version:
   AWA currently supports Python 3.9 with no runtime dependencies. A small stdlib runner is enough to
   prove the architecture; a dependency needs evidence that the stdlib design cannot meet.
6. **Cache guard or lifecycle results across invocations.** Rejected: stale evidence could authorize
   an unsafe action. Only display enrichment and non-authorizing test receipts may persist.
7. **Combine every optimization in one refactor.** Rejected: measurement, orchestration, sharding,
   test-layer changes, production guard probes, and dashboard discovery have different risks and
   rollback boundaries.

## Why

The measured shape is concentrated and mechanical: repeated process boundaries, repeated fixture
construction, and repeated gate orchestration dominate; discovery and literal sleeps do not.
Separating feedback lanes from authoritative gates returns time immediately without pretending a
focused pass proves the whole product. Process-isolated sharding then attacks wall time without
sharing mutable state. Layering corpora beneath expensive boundaries addresses the deeper process
count while preserving independent kernel/engine proof.

This sequence is intentionally evidence-first. The current inventory has already grown from 902 to
1,045 tests since the original audit, so a speed claim tied only to the older profile would be false
precision. The companion plan starts by making current cost visible and de-duplicating only proofs
whose ownership is explicit.

## Consequences

- **Enables:** fast, honest docs/focused feedback; one complete pre-PR graph; visible slow-test and
  process-growth evidence; bounded process-isolated sharding; test fixture reuse with independence
  proof; and scalable display discovery.
- **Costs:** a maintained stdlib runner/receipt schema, lane classification tests, serial-equivalence
  evidence, and explicit end-to-end canary ownership.
- **Forecloses:** automatic receipt-based skips; in-process threaded tests; shared mutable fixtures;
  cross-invocation guard/lifecycle caches; removal of finish stability/durability proofs; wiring
  host doc-warden into AWA; GitHub Actions runners; and timing-only merge authority without a stable
  baseline.
- **Must stay true:** kernel-first; full engine/kernel guard parity; fail-safe uncertainty; exact
  finish authorization/inventory/durability; isolated HOME/XDG/Git test state; no real network in
  ordinary verification; no `chaos-scheduler` changes; Python 3.9/Bash 3.2 compatibility on existing
  paths; and no paid hosted or self-hosted Actions runners.
- **Creates:** the implementation and acceptance work in
  [`awa-verification-and-discovery-velocity-v1.md`](../plans/awa-verification-and-discovery-velocity-v1.md).
  This ADR authorizes no implementation until the operator accepts the plan and gives an explicit
  execution GO.
