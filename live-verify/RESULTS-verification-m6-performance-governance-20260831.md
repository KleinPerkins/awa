# Verification M6 performance governance — 2026-08-31

## Decision

M6-A.1 is accepted for Draft-PR review as **advisory governance**.

- Timing and inventory findings are warnings; they do not replace or mask an
  authoritative result.
- Docs and pre-PR timing targets remain explicit **hypotheses**. This session
  did not provide five passing fixed-workload observations across two
  ordinary-load sessions, so no timing threshold was accepted.
- The current M3 source-boundary profile is compatible and measured **62**
  `PATH-resolved git children only`. Missing or incompatible observations are
  reported as `not measured`.
- Receipt data is descriptive only and every receipt retains
  `authorizes_skip=false`.
- The live runnerless protected recipe does **not** reach repository
  `make verify`. That integration is a controller-owned NO-GO requiring a
  separate plan; no AWA recipe, workflow, or controller setting changed.

## Source and scope

| Item | Value |
|---|---|
| M5-B merged base / live `origin/main` | `edf740f58ae35f79289836f8e55465da5b144a5a` |
| M6 implementation commit profiled | `3cb18922dc44102091cd233f166b86b28e79dc12` |
| Branch | `cursor/verification-m6-governance` |
| Python | `3.14.6` |
| Git | `git version 2.50.1 (Apple Git-155)` |
| Platform / architecture / logical CPUs | `darwin` / `arm64` / `12` |
| Controlled-run load | no competing AWA suite; second run followed the first in the same host session |

Changed product paths are limited to `Makefile`, `install.sh`, the M6
validator/policy/baseline/tests and suite-runner timing projection, the lane
runbook, one adjacent lane test, and this evidence record. There is no
`.github/workflows`, `.github/pr-automation.json`, production lifecycle,
cleanup, destructive-action, hosted-service, or `chaos-scheduler` change.

## Expected-red proofs

Before implementation:

1. `python3 -B -m unittest engine.tests.test_performance_policy` failed with
   `ImportError` because `engine.tests.performance_policy` did not exist.
2. The static single-owner test failed because
   `test_contract_schemas.py` still imported `os` and `subprocess` for its
   executable freeze integration.

These failures were recorded before adding the policy and before replacing the
executable unit integration.

## Closed baseline and inventory

The committed `awa-test-performance-baseline/v1` has exact top-level, lane,
process, and machine-context keysets. It rejects unknown/missing keys, malformed
digests, incomplete process measurements, unbounded/non-relative evidence
references, and accepted timing with fewer than five observations or two
sessions. It contains no raw paths, logs, prompts, source, or secrets and has no
rewrite command.

| Inventory | Count | SHA-256 |
|---|---:|---|
| M5-B base | 1,134 | `6eafb8101e27927d1b8d61f73861cb787fa4567ce68c63f86fa842ce5c45de02` |
| M6 candidate | 1,148 | `7f68d44a11e02bb59be5d25672d2a6457aade3593a4b950918365c76146d60a4` |

Both inventories were complete, sorted, and unique. The mapping is one planned
rename (`test_freeze_checker_passes` removed and
`test_install_check_is_single_pre_pr_freeze_owner` added) plus fourteen new
`PerformancePolicyTest` IDs. No unplanned ID disappeared.

The fixed workload identities are:

- docs: `d32fb511f0604d0d582eb18fdae4ca233454db1e812d10a375ca9572f4977836`;
- pre-PR two-worker engine:
  `d28f211aeb67b6e82a2768e54dc03ad4595f13cd4f37eab4b4b1964ca13a7c6b`.

Both lane statuses are `hypothesis`, with zero accepted observations, zero
sessions, and null p90/warning targets. The two long observations below are
retained only as loaded descriptive evidence.

## Advisory policy behavior

Focused tests prove:

- missing load/context fields warn;
- any test-ID growth is visible;
- compatible process growth above 20% warns;
- missing, unmeasured, or digest/scope-incompatible process data says
  `scoped Git process count not measured`, never zero;
- arbitrary focused elapsed time has no lane-wide budget;
- hypothesis lanes cannot emit timing-budget warnings;
- findings exit zero, while malformed baseline data exits nonzero and also
  fails the authoritative unit suite;
- receipts are not read by Make, lane, install, or live checks to suppress any
  command.

`make verify` creates a private receipt, traps cleanup, runs the existing
authoritative commands in one `set -e` block, prints `verify: OK`, then evaluates
the advisory. `make verify-performance` disables recursive warnings, runs one
authoritative `make verify`, runs the fixed M3 profile, evaluates both bounded
artifacts, preserves the first nonzero authoritative exit, and traps both
temporary files. Ordinary `make verify` contains no process-profile command.

## Current process observation

Exact target and fixed producer command:

```bash
AWA_TEST_LOAD_NOTE='ordinary post-controlled gate; no competing AWA suite' \
  make verify-performance

python3 -B -m engine.tests.guard_boundary_profile \
  --boundary source --count-git --json-out <private-temporary-profile>
```

| Field | Accepted M3 source evidence | Current M6 observation |
|---|---|---|
| Raw profile source SHA-256 | `a36317c04018c650e85b08ed47155159ac08106518139e0f261c2059a8c2af54` | exact |
| Case-manifest SHA-256 | `eb4e7662f096cecc6d0a99717d71e1868552596f22abe1db61536e61d4476435` | exact |
| Counter scope | `PATH-resolved git children only` | exact |
| Git processes | 77 | **62** |
| Combined profile + validator producer SHA-256 | n/a | `5475ffc4a3f86cf3387517fe4416590bf5e5b46c42bed53afceb652249e339de` |
| Result | passed | passed; `performance advisory: no findings` |

The baseline records the current 62-process observation. This is a controlled
count, not a claim about universal wall-clock improvement.

## Source-freeze ownership proof

The pre-change unit called:

```text
AWA_HOME=<source-root> /bin/bash <source-root>/kernel/checks/awa-contract-freeze.sh
```

`install.sh --check` was normalized to the same explicit `/bin/bash` command.
An isolated copied-source sentinel compared the two invocations and observed:

- identical command, `AWA_HOME`, working directory, Bash `3.2.57`, no arguments,
  and source-root-relative input resolution;
- one invocation on each path;
- injected checker exit `23` propagated as direct unit failure `23` and
  `install.sh --check` failure `1` with the explicit kernel-drift failure row.

Only after that proof, the executable unit was replaced by the static ownership
assertion. The required final command:

```bash
bash -x -c 'make verify'
```

passed at the implementation commit. Its captured output had exactly one
`awa install --check` header and one `PASS  kernel satisfies the frozen behavior
contract` row. `make check` independently passed and installed-runtime
doctor/lifecycle checks remain distinct.

## Verification

| Command | Outcome |
|---|---|
| Focused M6 + contract/lane/suite-runner modules | 44 passed |
| `make check` | passed; source freeze passed |
| `bash -x -c 'make verify'` | passed; 1,148 engine IDs, 30 dashboard tests, install and live checks; one source freeze |
| `make verify-performance` | passed; one authoritative `make verify`, 62 scoped Git processes, no advisory findings |

The traced `make verify` wall observation was 5,702,083 ms. The prescribed
performance target observation was 5,174,894 ms. They ran under one extended
host session and are not accepted timing baselines, budgets, or claimed gains.

## Runnerless integration check

The live GitHub `main` recipe was read after both gates. Its sole custom job
`repo.awa.engine-tests` runs literal `python3 -B -m unittest` for
`test_policy`, `test_modes`, `test_recovery`, and `test_state_lock`.
`reaches_make_verify=false`.

Per the accepted boundary, this does not weaken M6 or justify an AWA-side
workflow. A separate controller-owned plan must decide how the protected recipe
reaches repository `make verify`. `.github/pr-automation.json` and all other
`.github` files remain unchanged.

## Acceptance ledger

- **V01:** complete sorted inventory moved from 1,134 to 1,148 through one
  mapped rename and fourteen planned policy tests.
- **V05–V06:** serial fallback remains documented as
  `AWA_TEST_JOBS=1 make verify`; the authoritative suite including kernel-off
  coverage passed.
- **V09:** exact source-owner equivalence/failure propagation was proved, then
  final traced pre-PR ran one source freeze.
- **V10–V11:** non-authoritative docs/focused copy and broad mixed/unknown
  classification remain tested.
- **V12:** the baseline validator is closed; receipts retain
  `authorizes_skip=false`; source tests prove no skip consumer.
- **V13:** tests and profiles used private temporary state with cleanup traps;
  the candidate returned clean and no child/profile process survived.
- **V20–V21:** no lifecycle/destructive action, paid runner, workflow, hosted
  service, controller mutation, or `chaos-scheduler` change.
- **V22:** commands, source commit, inventory/digests, tools, worker count,
  load context, timings, and outcomes are recorded above.
- **V23:** docs/pre-PR timing stays hypothesis because the five-pass/two-session
  gate was not met.
- **V24:** focused timing remains descriptive; timing findings are warnings;
  process absence is `not measured`; explicit performance verification measured
  62; ordinary pre-PR added no second guard corpus.
- **V25:** the runbook selects filtered PM/router and complete finish/retention
  rehearsals only for affected release surfaces, plus live Desktop UAT where
  headless proof ends.

## Rollback

Revert the M6 policy, baseline, runbook, and Make wiring; restore
`test_contract_schemas.test_freeze_checker_passes` and the prior source-check
invocation form. Existing authoritative tests, install checks, and live checks
remain the fallback.
