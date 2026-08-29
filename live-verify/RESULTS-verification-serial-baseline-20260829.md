# Verification serial baseline — 2026-08-29

## Scope

This is the controlled M1-A serial observation required by
`docs/plans/awa-verification-and-discovery-velocity-v1.md`. It measures one clean,
complete `make verify` run after the measured serial runner landed on the branch.
It is a bounded observation from this machine and load window, not an SLA.

## Passing observation

| Item | Value |
|---|---|
| Git HEAD before and after | `3e7d0f82b2e5e11c9bd2ca505c695ce769b6d39d` |
| Source state | clean and stable |
| Python | `Python 3.14.6` |
| Git | `git version 2.50.1 (Apple Git-155)` |
| Platform | `darwin` |
| Logical CPUs / workers | 12 / 1 |
| Initial load note | single AWA suite after competing kernel verification exited; load averages `6.42 6.66 6.81` |
| Engine inventory | 1,060 tests; 1,045 passed; 15 skipped; 0 failures/errors |
| Dashboard inventory | 17 passed |
| Engine elapsed | 4,806.334 seconds |
| Complete `make verify` elapsed | 4,918.76 seconds |
| CPU time | 753.92 seconds user; 871.08 seconds system |
| Runner resource snapshot | 735,546 ms user; 853,173 ms system; 74,848 KiB max RSS |
| Result | `verify: OK` |
| Worktree changes after run | 0 |

Exact command, with the generated evidence directory resolved:

```bash
AWA_TEST_RECEIPT=/tmp/awa-m1a-baseline-corrected.AIp3YH/receipt.json \
AWA_TEST_LOAD_NOTE='single AWA suite after competing kernel verification exited; 12 logical CPUs; 13:13 up 15:14, 1 user, load averages: 6.42 6.66 6.81' \
PYTHONDONTWRITEBYTECODE=1 \
/usr/bin/time -lp make verify
```

Receipt facts:

- schema: `awa-test-receipt/v1`
- inventory SHA-256:
  `98adf7f89116f981f8e0fa3626a48a1ca9fffd1d345faa3647b2ddf77edc8b0e`
- runner SHA-256:
  `e3e7497480dc44fd8e38652a95562171f098426a2934978bbfca576258d0e56b`
- receipt outcome: `passed`
- source state: `stable`
- reusable as exact-head evidence: `true`
- authorizes a future skip: `false`

## Discovery-only observation

The final exact-head inventory command was:

```bash
PYTHONDONTWRITEBYTECODE=1 \
/usr/bin/time -lp python3 -B -m engine.tests.suite_runner --list-ids
```

It returned 1,060 sorted, unique IDs in 0.32 seconds (`user 0.16`, `sys
0.04`) with the same inventory SHA-256 as the passing receipt.

## Timing ranking

Slowest modules in the passing serial run:

| Module | Elapsed |
|---|---:|
| `engine.tests.test_finish_hardening` | 675.105 s |
| `engine.tests.test_guard_hook_wrappers` | 639.480 s |
| `engine.tests.test_hook_owner_modes` | 604.316 s |
| `engine.tests.test_finish_phase2_final_blockers` | 522.552 s |
| `engine.tests.test_finish_final_hardening` | 359.628 s |
| `engine.tests.test_finish_kernel` | 333.489 s |
| `engine.tests.test_finish_operations` | 286.559 s |
| `engine.tests.test_finish_publication_projection` | 228.411 s |
| `engine.tests.test_finish_conversation` | 228.309 s |
| `engine.tests.test_finish_semantic_drift` | 187.225 s |

Slowest individual tests:

| Test | Elapsed |
|---|---:|
| `TestHookOwnerParity.test_shared_git_corpus_matches_direct_and_generic_delegated_paths` | 313.111 s |
| `ShellMachineTrustTest.test_malformed_and_contradictory_rc_zero_or_three_never_prove_removal` | 181.508 s |
| `GitOperationInventoryTest.test_each_operation_group_retain_restores_and_aborts_in_isolation` | 171.260 s |
| `TestBashGuardWrapperParity.test_primary_maintenance_command_corpus_engine_source_installed_parity` | 165.106 s |
| `CurrentEnvelopeAdversarialTest.test_non_destructive_casing_matrix_through_hook_envelope_and_current` | 159.184 s |
| `TestHookOwnerInstall.test_doctor_reports_and_validates_selected_owner` | 143.604 s |
| `TestBashGuardWrapperParity.test_hook_still_denies_mutating_git_family_forms` | 133.159 s |
| `TestBashGuardWrapperParity.test_primary_maintenance_state_corpus_engine_source_installed_parity` | 106.313 s |
| `OneUseGenerationAdversarialTest.test_close_claim_is_one_use_across_validation_and_remove_faults` | 98.479 s |
| `TestLiveHookFacts.test_v2_validation_acceptance_parity_matrix` | 89.399 s |

These timings identify optimization candidates only. They do not authorize
sharding, fixture sharing, process removal, changed safety behavior, or a timing
budget.

## Preserved failed observations

Three complete failed observations preceded the passing result. All kept a clean,
stable source identity and are preserved so the accepted plan's environmental
and correction history is not erased.

| HEAD | Initial load | Inventory | Engine elapsed | Result | Identified reason |
|---|---:|---:|---:|---|---|
| `0cf1cba5a3bf99dc21b47261b40726043634c652` | `6.86 7.05 7.18` | 1,057 | 5,936.075 s | 2 failures, 1,040 passed, 15 skipped | Fixed 0.500 s wall-clock assertions observed 0.536 s and 0.626 s despite correct observer lifecycle behavior. |
| `0cf1cba5a3bf99dc21b47261b40726043634c652` | `4.32 4.90 5.39` | 1,057 | 4,460.154 s | 1 failure, 1,041 passed, 15 skipped | The same fixed observer assertion observed 0.698 s; isolated cases passed. |
| `efd2fa65ef7a0de502938c90c665e5b291943b31` | `6.05 6.09 6.15` | 1,060 | 4,672.661 s | 1 failure, 1,044 passed, 15 skipped | The new nested wrapper smoke inherited `AWA_ENGINE_TESTS_ACTIVE=1`, so its fake inner wrapper exited before the dashboard assertion. |

The first two observations led to the separately reviewed lifecycle-based timing
test correction merged in PR #137. The third led to explicit nested-test
environment isolation. Focused reproductions passed before each complete rerun.

## Acceptance result

M1-A now has a fresh passing serial baseline with exact inventory, source,
runner, environment, outcome, resource, and timing evidence. The receipt remains
non-authorizing, and this record makes no performance target or safety-equivalence
claim for M2.
