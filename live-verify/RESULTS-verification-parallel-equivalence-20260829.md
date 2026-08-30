# Verification parallel equivalence — 2026-08-29

## Decision

**No promotion. `selected_jobs=1`.**

`jobs=2` was the only passing non-1 candidate and produced four exactly
equivalent engine receipts, but its 3,527.072-second p50 was only **22.376%**
faster than the 4,543.763-second serial observation. The accepted threshold is
at least 25%. `jobs=4` hit the plan's 1,800-second worker deadline and failed
closed. The authoritative default therefore remains serial.

Receipts in this record are evidence only. Every receipt has
`authorizes_skip=false`; none authorizes a future verification skip.

## Controlled source and environment

| Item | Value |
|---|---|
| Campaign HEAD before/after every counted run | `7024ceb71d14891becfe65ca98b2a25b15aef9f1` |
| Source state during every counted run | clean and stable |
| Branch | `cursor/verification-m2a` |
| Python | `3.14.6` |
| Git | `git version 2.50.1 (Apple Git-155)` |
| Platform / architecture | `darwin` / `arm64` |
| Logical CPUs | 12 |
| Campaign concurrency | one complete inventory at a time |
| Prior timing receipt for every parallel run | counted `jobs1` receipt from the same HEAD |

The source changed once before the counted campaign: commit `7024ceb` isolated
nested `suite_runner.main` tests from an outer campaign's
`AWA_TEST_RECEIPT` and `AWA_TEST_PRIOR_RECEIPT`. The branch was clean before
the campaign restarted and did not change during the six observations.

## Six-run campaign

`Engine` is the receipt's measured engine inventory time. `Elapsed`, `user`,
`system`, and max RSS are from `/usr/bin/time -lp` around
`engine/tests/run-tests.sh`, including the dashboard gate when reached.

| Observation | Jobs | Engine | Elapsed | User | System | Max RSS | Dashboard | Result |
|---|---:|---:|---:|---:|---:|---:|---|---|
| `jobs1` | 1 | 4,543.763 s | 4,569.21 s | 706.97 s | 806.59 s | 123,371,520 B | 17 passed in 24.607 s | PASS |
| `jobs2` | 2 | 3,399.570 s | 3,439.16 s | 713.94 s | 809.13 s | 62,750,720 B | 17 passed in 38.557 s | PASS |
| `jobs4` | 4 | incomplete | 1,800.80 s | 359.70 s | 392.16 s | 56,492,032 B | not run | FAIL CLOSED |
| `jobs2-repeat1` | 2 | 3,561.372 s | 3,583.28 s | 718.60 s | 810.03 s | 62,652,416 B | 17 passed in 20.869 s | PASS |
| `jobs2-repeat2` | 2 | 3,492.772 s | 3,528.98 s | 714.28 s | 814.05 s | 62,619,648 B | 17 passed in 35.157 s | PASS |
| `jobs2-repeat3` | 2 | 3,967.113 s | 3,993.09 s | 719.43 s | 813.94 s | 62,816,256 B | 17 passed in 24.792 s | PASS |

Initial load averages recorded immediately before each run:

| Observation | Load averages |
|---|---|
| `jobs1` | `6.50 6.27 6.64` |
| `jobs2` | `2.38 3.70 4.48` |
| `jobs4` | `7.79 6.50 6.13` |
| `jobs2-repeat1` | `5.71 5.40 5.46` |
| `jobs2-repeat2` | `2.59 4.66 5.26` |
| `jobs2-repeat3` | `6.90 6.31 6.05` |

Each run's load record also confirmed no competing AWA suite. Unrelated host
activity remained ordinary machine context and was not stopped.

## Exact receipt equivalence

All five complete passing receipts reported:

| Receipt fact | Exact value |
|---|---|
| Inventory | 1,092 sorted unique test IDs |
| Outcomes | 1,077 passed; 15 intentionally skipped; 0 failures/errors |
| Inventory SHA-256 | `9199d59491b3542ea2369f3832988c7480bc31fea37d5cc2f66bdd3a6f9376d0` |
| Outcome-manifest SHA-256 | `3845552496a061b5edde23c35d90b9a6a8c046beda3ffc1bd67c2a740504b186` |
| Skip-manifest SHA-256 | `3c126568ad7288e18e8def73da823cd3b630ce2bcd6e07230903ad8a9d82fe18` |
| Runner SHA-256 | `b2d0b7cc50d380a2dea666521649633011c32693198b613015e745572b9535d0` |
| Source identity | clean, stable, exact HEAD `7024ceb71d14891becfe65ca98b2a25b15aef9f1` |
| Receipt policy | `reusable=true`; `authorizes_skip=false` |

Machine comparison of serial against each of the four `jobs=2` receipts passed
every check: exact ordered IDs, per-ID outcomes, intentional skip reasons,
inventory/count/runner digests, source identity, dashboard result/count, strict
real-state preservation, and worker cleanup.

The exact intentional skips were:

| Test ID | Reason |
|---|---|
| `engine.tests.test_consumer_golden.TestGoldenAgainstRealRouter.test_router_reproduces_every_pinned_proposal` | router not installed (off-switch): golden propose skipped — AWA verify passes router-uninstalled |
| `engine.tests.test_consumer_loop.TestOperatorLoop.test_real_router_benign_status_reads` | router not installed (off-switch): real-router loop skipped |
| `engine.tests.test_consumer_loop.TestOperatorLoop.test_real_router_destructive_utterance_confirms` | router not installed (off-switch): real-router loop skipped |
| `engine.tests.test_consumer_seam.TestRouterSeam.test_awa_egress_snapshot_is_superset_of_router_tiers` | router not installed (off-switch): seam test skipped — AWA verify passes router-uninstalled |
| `engine.tests.test_consumer_seam.TestRouterSeam.test_catalog_contract_schema_string_matches_pin` | router not installed (off-switch): seam test skipped — AWA verify passes router-uninstalled |
| `engine.tests.test_consumer_seam.TestRouterSeam.test_catalog_schema_string_matches_pin` | router not installed (off-switch): seam test skipped — AWA verify passes router-uninstalled |
| `engine.tests.test_consumer_seam.TestRouterSeam.test_constitution_egress_check_active_if_declared` | router not installed (off-switch): seam test skipped — AWA verify passes router-uninstalled |
| `engine.tests.test_consumer_seam.TestRouterSeam.test_constitution_schema_string_matches_pin` | router not installed (off-switch): seam test skipped — AWA verify passes router-uninstalled |
| `engine.tests.test_consumer_seam.TestRouterSeam.test_matcher_logic_agrees_with_router` | router not installed (off-switch): seam test skipped — AWA verify passes router-uninstalled |
| `engine.tests.test_consumer_seam.TestRouterSeam.test_proposal_contract_is_frozen_at_pinned_version` | router not installed (off-switch): seam test skipped — AWA verify passes router-uninstalled |
| `engine.tests.test_consumer_seam.TestRouterSeam.test_router_authoritative_catalog_verify_accepts_awa_catalog` | router not installed (off-switch): seam test skipped — AWA verify passes router-uninstalled |
| `engine.tests.test_consumer_trial_runner.TestRouterLifecycleSeam.test_isolated_install_on_uninstall_off_restore` | isolated real router lifecycle runs only in the credentialed router-seam job |
| `engine.tests.test_consumer_trial_runner.TestRouterLifecycleSeam.test_production_run_trial_all_seven_has_pm_safe_complete_stream` | isolated real router lifecycle runs only in the credentialed router-seam job |
| `engine.tests.test_consumer_trial_runner.TestRouterLifecycleSeam.test_production_run_trial_restores_after_injected_post_uninstall_failure` | isolated real router lifecycle runs only in the credentialed router-seam job |
| `engine.tests.test_consumer_trial_runner.TestRouterLifecycleSeam.test_real_post_uninstall_failure_and_interrupt_restore` | isolated real router lifecycle runs only in the credentialed router-seam job |

## `jobs=4` failure

`jobs=4` failed safely with:

```text
WORKER ERROR: worker timed out: engine.tests.test_finish_hardening
```

The serial prior measured that module at 577.662 seconds. The accepted deadline
function computes four times the prior duration and caps it at 1,800 seconds, so
this worker received the maximum 1,800-second monotonic deadline. It did not
complete under the observed load before that deadline. The parent terminated
and reaped the workers, removed the private worker root, emitted no reusable
receipt, skipped the dashboard, and returned 2. No process survived and the
strict real-state fingerprint was unchanged.

This is the required fail-closed timeout behavior, not an equivalence pass and
not a reason to weaken the accepted deadline or safety tests. `jobs=4` was
therefore ineligible for selection.

## Performance calculation

The selected non-1 candidate was `jobs=2` because it passed the initial run
while `jobs=4` did not. Its four engine times were:

```text
3,399.570 s
3,561.372 s
3,492.772 s
3,967.113 s
```

Sorted: `3,399.570`, `3,492.772`, `3,561.372`, `3,967.113`.

```text
p50 = (3,492.772 + 3,561.372) / 2
    = 3,527.072 seconds

improvement = (4,543.763 - 3,527.072) / 4,543.763
            = 22.376%
```

Selected-candidate engine flake rate was 0/4; serial was 0/1. Exact equivalence
and cleanup held, but the p50 missed the 25% threshold. Promotion is refused
and `selected_jobs=1`.

## Real-state and cleanup evidence

Every counted run captured before/after fingerprints for:

- `~/.cursor/hooks.json`
- real AWA config, cache, durable state, and data
- AWA worktree metadata
- repository HEAD, status, worktree list, refs, packed refs, and worktree
  administrative identity

All six observations finished with identical strict before/after fingerprints.
Expected volatile AWA heartbeat/receipt state was recorded separately and was
allowed to vary.

Two narrow harness corrections were made after inspecting exact changed paths:

1. Read-only `git status` refreshed only
   `worktrees/izkk/index` bytes. Linked-worktree `index`/`index.lock` files are
   now treated as Git stat caches; refs, packed refs, HEAD, worktree
   registration, source status, and all other administration remain strict.
2. An unrelated read-only AWA status probe created only `state.db-shm` and
   `state.db-wal` during `jobs2-repeat1`. Those exact SQLite sidecars are
   volatile; the durable `state.db` remains strict. The original failed harness
   classification was preserved before machine revalidation.

Serial execution also exercised two legacy trial-runner cases that create
unique `0600` facilitator logs under real XDG state. The harness recorded
name, size, mode, and SHA-256, then removed only the two files absent from the
pre-run baseline before taking the final fingerprint:

- `trial-facilitator-mxw5k2lx.log` — 542 bytes,
  `da8a7d2883f1cbe93e3f860c20fab53bda580f7c3ad6574def00f7769ce0090c`
- `trial-facilitator-ns_udmsl.log` — 589 bytes,
  `172042da69b67cdca159d4754e708851409ac98f8dcd7b3ec10c01f5ff6ce9fb`

No parallel run created a real-state trial log because every worker had private
TMP/XDG roots. The bounded cleanup refused symlinks, wrong ownership, wrong
mode, oversized files, or unexpected names.

Survivor detection was also corrected after its first version matched an
unrelated `~/dev make verify-ci`. It now matches only AWA
`engine.tests.suite_runner` and `engine/tests/run-tests.sh` processes; every
before/after process list was empty. Every `awa-test-workers.*` root was gone.
The fault-injection suite separately proved crash, timeout, signal, partial,
malformed, extra, duplicate-ID, and interrupt paths fail overall and reap all
children.

## Preserved pre-campaign observations

These do not count toward the six-run clean-HEAD campaign:

| Observation | HEAD | Duration | Result | Disposition |
|---|---|---:|---|---|
| Original controlled launcher | `f90e2d5` | 2,415.719 s | aborted during `test_finish_final_hardening`; no receipt/final result | Aborted, non-counting. Its macOS-incompatible `mktemp` template produced the literal `/tmp/awa-m2a-jobs1.XXXXXX.json`. |
| First harness serial | `f90e2d5` | 4,487.129 s observed before interruption | aborted during `test_hook_owner_modes`; no receipt/final result | Aborted, non-counting; no PID remained. |
| Resumed `jobs1` | `f90e2d5` | 5,431.281 s engine; 5,432.11 s timed | 1 failure, 3 errors, 1,073 passed, 15 skipped | Failed, non-counting; stable-source receipt was non-reusable. |

The complete failed `jobs1` exposed a real nested-test isolation defect:
four `test_parallel_equivalence` tests invoked `suite_runner.main` while the
outer campaign exported receipt variables. Partial mocked results then entered
production receipt construction, producing three `KeyError: 'inventory'`
errors and one explicit/ambient receipt-target disagreement.

Red reproduction on `f90e2d5`:

```bash
AWA_TEST_RECEIPT=/tmp/awa-m2a-resumed-20260829.g9oIkX/red-outer-receipt.json \
AWA_TEST_PRIOR_RECEIPT=/tmp/awa-m2a-resumed-20260829.g9oIkX/red-outer-prior.json \
PYTHONDONTWRITEBYTECODE=1 \
python3 -B -m unittest \
  engine.tests.test_parallel_equivalence.ParallelEquivalenceTest.test_default_main_path_remains_serial \
  engine.tests.test_parallel_equivalence.ParallelEquivalenceTest.test_parallel_cli_writes_valid_jobs_two_receipt -v
```

Result: 2 tests, 1 failure and 1 error.

The smallest fix isolated both campaign receipt variables around nested CLI
probes while retaining explicit `--json-out` and validated prior-receipt
coverage. The same two-test command then passed. The fix is commit
`7024ceb71d14891becfe65ca98b2a25b15aef9f1`.

The failed run also created two exact legacy trial logs; their bounded recovery
record removed only those two files and restored the 422-file baseline:

- `trial-facilitator-jy8bsqwc.log` — 542 bytes,
  `3ef14b4b278cd0618264762f91c21463fffbc87f189bbd69969f60d6510c0594`
- `trial-facilitator-p19256kg.log` — 589 bytes,
  `c01a1af1e166a02a46167a636fc86575bb688d6e4d4b511ccf17adadc4ae2265`

No stale descendant from any aborted/failed launcher remained.

## Exact campaign commands

The evidence root was created with `mktemp -d` after verifying `/tmp` existed.
Each wrapper invocation used one fixed run directory beneath it:

```bash
AWA_CAMPAIGN_ROOT=/tmp/awa-m2a-clean-7024ceb.c3UGPJ \
  /tmp/awa-m2a-20260829.6gj1ht/run-one.sh jobs1 1 -

AWA_CAMPAIGN_ROOT=/tmp/awa-m2a-clean-7024ceb.c3UGPJ \
  /tmp/awa-m2a-20260829.6gj1ht/run-one.sh jobs2 2 \
  /tmp/awa-m2a-clean-7024ceb.c3UGPJ/jobs1/receipt.json

AWA_CAMPAIGN_ROOT=/tmp/awa-m2a-clean-7024ceb.c3UGPJ \
  /tmp/awa-m2a-20260829.6gj1ht/run-one.sh jobs4 4 \
  /tmp/awa-m2a-clean-7024ceb.c3UGPJ/jobs1/receipt.json

AWA_CAMPAIGN_ROOT=/tmp/awa-m2a-clean-7024ceb.c3UGPJ \
  /tmp/awa-m2a-20260829.6gj1ht/run-one.sh jobs2-repeat1 2 \
  /tmp/awa-m2a-clean-7024ceb.c3UGPJ/jobs1/receipt.json

AWA_CAMPAIGN_ROOT=/tmp/awa-m2a-clean-7024ceb.c3UGPJ \
  /tmp/awa-m2a-20260829.6gj1ht/run-one.sh jobs2-repeat2 2 \
  /tmp/awa-m2a-clean-7024ceb.c3UGPJ/jobs1/receipt.json

AWA_CAMPAIGN_ROOT=/tmp/awa-m2a-clean-7024ceb.c3UGPJ \
  /tmp/awa-m2a-20260829.6gj1ht/run-one.sh jobs2-repeat3 2 \
  /tmp/awa-m2a-clean-7024ceb.c3UGPJ/jobs1/receipt.json
```

The wrapper's measured command was:

```bash
PYTHONDONTWRITEBYTECODE=1 \
AWA_TEST_RECEIPT="$run_dir/receipt.json" \
AWA_TEST_LOAD_NOTE="$recorded_load_note" \
AWA_TEST_PRIOR_RECEIPT="$jobs1_receipt" \
/usr/bin/time -lp bash engine/tests/run-tests.sh --jobs "$jobs"
```

For `jobs1`, `AWA_TEST_PRIOR_RECEIPT` was unset. Every long-run wrapper used an
EXIT trap that emitted `CAMPAIGN_RUN_DONE` even on nonzero/early exits; a
deliberate run-directory collision proved the nonzero sentinel path.

Raw receipts and large logs were machine-validated locally but are not
committed. This record preserves their bounded facts.

## Focused verification before campaign

After commit `7024ceb` and before restarting the counted campaign:

| Command | Result |
|---|---|
| `python3 -B -m unittest engine.tests.test_suite_runner engine.tests.test_verify_lane engine.tests.test_parallel_equivalence engine.tests.test_contract_schemas engine.tests.test_kernel_off_matrix` under poisoned outer receipt variables | 62 passed on Python 3.14 |
| `/usr/bin/python3 -B -m unittest engine.tests.test_suite_runner engine.tests.test_verify_lane engine.tests.test_parallel_equivalence engine.tests.test_contract_schemas` under poisoned outer receipt variables | 54 passed on Python 3.9 |

A broader Python 3.9 probe that also included
`test_kernel_off_matrix.test_kernel_libs_are_stdlib_only` found its pre-existing
fallback list does not recognize stdlib `hmac` on Python 3.9. The same kernel
matrix passed on Python 3.14. This unrelated compatibility observation did not
change M2-A code or the passing Python 3.9 M1+M2 result.

## Final verification and review

After the six-run campaign:

| Check | Result |
|---|---|
| Python 3.14 focused M1+M2 plus kernel-off matrix under poisoned outer receipt variables | 62 passed |
| Python 3.9 focused M1+M2 under poisoned outer receipt variables | 54 passed |
| `make check` | PASS |
| `git diff --check` | PASS |
| Bugbot full branch review against `main` | no bugs |

## Acceptance ledger result

- V01–V06: focused serial runner, receipt, lane, dashboard, and kernel-off
  checks passed; dashboard ran once after each complete engine pass.
- V12–V13: exact serial/parallel manifests matched; strict real state and
  source were restored unchanged; private worker roots were removed.
- V20–V22: isolated process workers, deterministic prior-based scheduling,
  bounded deadlines, fail-closed worker validation, resource aggregation, and
  cleanup were exercised.
- Performance promotion criterion: **not met** (`22.376% < 25%`).

Final campaign result: five complete equivalent passes and one safe `jobs=4`
timeout across the required six observations. Keep serial authoritative:
`selected_jobs=1`; no promotion.
