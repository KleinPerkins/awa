# M4-B pure finish matrix verification — 2026-08-31

## Decision

Promote the test-only pure/physical partition. A current clean profile found an existing production
pure-decision seam, `consumer.finish_current.canonicalize_choice`, behind a repeated stateful casing
matrix. Moving only the supplied-value normalization cases to that seam reduced test-generated Git
processes by 37.5% in the closed profile while all test IDs and outcomes stayed exact.

The implementation is commit
`328e3ddbfde07bd70d51b15477234714ca6bae16`, based directly on live `origin/main`
`2b6a5939d3fd6f6bfb3570bdc7c1fa9829642f01` after M4-A merged. The implementation
commit was clean before and after every reusable acceptance run.

## Exact scope

The implementation diff contains only:

- added `engine/tests/finish_case_manifest.py`;
- added `engine/tests/test_finish_case_manifest.py`;
- modified the eligible matrix in `engine/tests/test_finish_hardening.py`;
- modified the existing direct choice-oracle test in
  `engine/tests/test_finish_conversation.py`.

The implementation diff is 415 additions and 68 deletions with SHA-256
`ad608b7579beef53c7f95b5764cfe886e3289dd57e62d8a5f3c970a7a94a2622`.
`git diff --exit-code origin/main...328e3dd -- kernel/lib/awa_finish.py
kernel/lib/awa_durability.py consumer/finish_current.py` returned zero: no production finish file
changed.

The manifest file SHA-256 is
`a4dd90854fc909dc8b5293c798456427b0a737f5c81687574b5e72cad66a0538`.
The manifest-test SHA-256 is
`487cade9830795487f848f1a249112e516cde75cad446b32d230b7a3910e54a1`.

## Baseline failure and qualification profile

The clean baseline did not contain the partition. In an isolated `origin/main` archive, copying in
only the new manifest test and running
`/usr/bin/python3 -B -m unittest engine.tests.test_finish_case_manifest -v`
failed as expected with
`ModuleNotFoundError: No module named 'engine.tests.finish_case_manifest'`.
The captured log SHA-256 is
`595b413dd34143c00203530cdfb99c915ef1536c988347cf401977721d0697bb`.
No baseline test file or temporary archive remained afterward.

Before promotion, five existing pure-decision tests ran on clean live main in 7 ms. Git Trace2
observed only the suite runner's fixed five source/version probes (`version`, two `rev-parse`, and
two `status`) and zero test-generated Git processes. This established that the selected decision
seams already existed in production and required no production refactor or second semantic
implementation.

The closed stateful comparison used the same five exact test IDs before and after:

1. `engine.tests.test_finish_hardening.CurrentEnvelopeAdversarialTest.test_non_destructive_casing_matrix_through_hook_envelope_and_current`
2. `engine.tests.test_finish_hardening.CurrentEnvelopeAdversarialTest.test_exact_five_choices_remain_canonical`
3. `engine.tests.test_finish_conversation.HookAndDispatcherTest.test_close_routes_only_literal_close_to_kernel_executor`
4. `engine.tests.test_finish_conversation.HookAndDispatcherTest.test_commit_retain_mixed_require_selection_state_and_never_close`
5. `engine.tests.test_finish_publication_projection.DispatcherProjectionTest.test_hostile_removed_refused_uncertain_and_branch_fallback_are_total`

Each side ran through:

`GIT_TRACE2_EVENT=<trace> AWA_TEST_LOAD_NOTE="<context>" /usr/bin/time -lp python3 -B -m
engine.tests.suite_runner --jobs 1 --json-out <receipt> -- <five exact IDs> -v`

| Metric | Clean baseline | Clean implementation | Change |
|---|---:|---:|---:|
| Tests passed | 5 | 5 | exact |
| Inventory SHA-256 | `45a7193b...b8fde1` | `45a7193b...b8fde1` | exact |
| Total Git processes | 101 | 65 | -36 / -35.644% |
| Test-generated Git processes | 96 | 60 | -36 / **-37.500%** |
| Engine elapsed | 176.910s | 107.498s | -69.412s / -39.236% |

The fixed runner probes are excluded from “test-generated.” The remaining before/after command
counts were:

- before: `add=1, branch=31, commit=1, init=1, maintenance=1, remote=1, reset=30,
  worktree=30`;
- after: `add=1, branch=19, commit=1, init=1, maintenance=1, remote=1, reset=18,
  worktree=18`.

The baseline trace SHA-256 is
`df7ff13e359078862bd02fcd2a2d59ce7ffac7fd82ad425c2b8ef24d28d1cbf0`;
the clean implementation trace SHA-256 is
`40c089233c591f409a84f348ebf9f224f46480d902d82923185000f4dc382b5b`.
The exact ID sequence, outcomes, and inventory digest match. Both receipts have stable source and
`authorizes_skip=false`; the implementation receipt is reusable.

The baseline started at load averages 3.04 / 4.18 / 5.22 and the clean implementation at
2.87 / 4.12 / 4.85. The child-process reduction is the acceptance measure. Elapsed reduction is an
observation from these controlled serial runs, not a performance SLA.

## Review gates

- Bugbot: no bugs found.
- Security review: no medium, high, or critical issues found.
- Informational assurance tradeoff: lower/upper/trimmed non-destructive choice combinations now
  exercise the shared production canonicalizer in the pure layer instead of rebuilding a
  repository for every combination. The physical layer still covers exact five-choice integration,
  mixed-case non-destructive choices, literal-Close variants, attachments, and every registered
  safety seam. Review found no divergent production path or authorization bypass.

## Closed case partition

`ALL_FINISH_CASES` contains 34 immutable, unique case IDs:

- 30 `pure` cases invoke the existing production `canonicalize_choice` and `is_exact_choice`
  functions through a thin adapter;
- four `physical` cases retain mixed-case Commit, Retain, Mixed, and Cancel execution through the
  real hook envelope, current-dialogue state, Git worktree, and terminal cleanup paths.

The canonical JSON projection of all 34 IDs, layers, supplied inputs, expected outputs, and oracle
names has SHA-256
`d5be2667c6ddddcb44c0d5e3c12319d7df3c3f6d662f41b6b89de7e19138fac8`.
The existing exact-five-choice physical matrix remains unchanged.

Pure execution is serial inside its module and uses removable `mock.patch.object` scopes. It
refuses built-in/file-descriptor opens, stat/lstat, rename/replace/unlink, directory creation,
permission changes, fsync, subprocess creation, flock, wall/monotonic clocks, and sockets with
`AssertionError("physical access from pure case")`. No audit hook, global semantic cache, alternate
decision function, or production source change exists. Tests prove both that representative
physical probes fail and that every patch is restored when the scoped runner returns.

## Physical canary registry

`PHYSICAL_CANARIES` is immutable and closes all nine required seams over 18 distinct, loadable
ordinary-suite IDs:

| Seam | Positive behavior | Negative/fault behavior |
|---|---|---|
| crash cut | `test_finish_kernel.OrdinaryCleanUnchangedTest.test_ordinary_clean_path_still_removes_merged_worktree` | `test_finish_publication_projection.RetainTrustLatchTest.test_crash_immediately_before_and_after_commit_marker_is_truthful` |
| fsync | `test_finish_durability.DestructiveDurabilityOrderingTest.test_namespace_sync_precedes_branch_update_and_journal_receipt` | `test_finish_durability.DurabilityPrimitiveTest.test_nested_private_creation_replace_visibility_adoption_and_unlink` |
| F_FULLFSYNC | `test_finish_durability.DurabilityPrimitiveTest.test_darwin_requires_fsync_then_fullfsync_and_retries_eintr` | `test_finish_durability.DurabilityPrimitiveTest.test_darwin_missing_or_failed_fullfsync_never_downgrades` |
| retention | `test_finish_conversation.RetainArtifactTest.test_typed_artifact_restore_proof_permissions_lifecycle_and_secret` | `test_finish_conversation.RetainArtifactTest.test_retain_lock_contention_refuses_and_preserves_source` |
| publication | `test_finish_publication_projection.RetainTrustLatchTest.test_committed_marker_binds_exact_true_manifest_and_suppression` | `test_finish_publication_projection.RetainTrustLatchTest.test_post_manifest_replace_pre_parent_sync_is_never_published` |
| stable snapshot recapture | `test_finish_kernel.DeterminismGateTest.test_fingerprint_stable_across_repeated_runs` | `test_finish_operations.GitOperationInventoryTest.test_operation_admin_links_specials_mounts_and_drift_refuse` |
| no-follow | `test_finish_kernel.InventoryTest.test_directory_traversal_scans_open_nofollow_descriptors` | `test_finish_kernel.InventoryTest.test_symlink_escape_refuses` |
| shared lock | `test_finish_kernel.EngineOffAndLockAbiTest.test_finish_execute_removes_with_engine_unimportable` | `test_finish_kernel.FoldedHardeningTest.test_finish_refuses_when_common_dir_lock_held` |
| removal journal | `test_finish_kernel.RemovalJournalTest.test_shell_reconciles_valid_removed_result_before_deferred_receipt` | `test_finish_kernel.RemovalJournalTest.test_prepared_state_write_failure_preserves_root_and_reports_no_removal` |

The registry test proves each ID loads exactly one test and appears in ordinary suite discovery.
On the clean implementation commit, all 18 passed in 64.177 seconds with inventory SHA-256
`5de5a3d809fe6c5afaf7c19fc3a95cb0acd457437cbd9a69128344da4e634ba5`,
stable clean source, and `authorizes_skip=false`.

## Deliberate-break evidence

An isolated, fully restored campaign temporarily bypassed each registered fault/refusal behavior.
Every registered negative test then failed: the crash-cut test produced its two expected subtest
failures and each other seam produced one expected failure, with zero errors or skips. A temporary
copy of `awa_finish.py` was used for the no-follow bypass; the source tree was never changed and the
copy was removed. Separate scoped replacements removed one registry entry and renamed one
registered test; both made the registry oracle fail.

The 11 machine-readable result rows all record `biting=true` and
`source_tree_modified=false`. Their log SHA-256 is
`aecfdfafac26718f05c25371469b8ac1f796471897b65457d1b2ddd109c1f055`.
After restoration, the ordinary 18-canary receipt above passed.

## Complete verification

Environment: macOS 26.6.2 arm64, Apple Git 2.50.1, Homebrew Python 3.14.6, system Python 3.9.6,
12 logical CPUs.

| Command | Result |
|---|---|
| `python3 -B -m engine.tests.suite_runner --jobs 1 --json-out <receipt> -- engine.tests.test_finish_case_manifest -v` | 6 passed in 0.172s; inventory `4044e87c...00956`; clean/stable/reusable |
| `/usr/bin/python3 -B -m unittest engine.tests.test_finish_case_manifest -v` | 6 passed in 0.539s on Python 3.9.6 |
| registered 18-canary suite through `suite_runner --jobs 2` | 18 passed in 64.177s; inventory `5de5a3d8...34ba5`; clean/stable/reusable |
| `AWA_TEST_RECEIPT=<receipt> AWA_TEST_LOAD_NOTE="<context>" /usr/bin/time -lp make verify` | 1,134 tests; 1,119 passed, 15 intentional skips, zero failures/errors |

The ordinary full gate used the verified `jobs=2` default and passed in engine elapsed
2,847.690 seconds / command wall 2,917.76 seconds. Its inventory SHA-256 is
`6eafb8101e27927d1b8d61f73861cb787fa4567ce68c63f86fa842ce5c45de02`;
its receipt SHA-256 is
`2c9caa7e0e788f5e7a4672cffaea073c7053b0016dd820d5e5d7234a0d82ed13`.
HEAD stayed exactly `328e3ddbfde07bd70d51b15477234714ca6bae16`; source was clean,
stable, and reusable; `authorizes_skip=false`; `verify-live-verify: OK` and `verify: OK`.

## Acceptance ledger and rollback

- **V01:** the closed before/after profile retained the same five test IDs, order, inventory, and
  outcomes; the 34 semantic case IDs are unique and immutable.
- **V06:** physical kernel-off, engine-off, lock, removal, crash, retention, and durability tests
  remained in ordinary full verification.
- **V12:** clean receipts bind exact HEAD, inventory, environment, outcome, and
  `authorizes_skip=false`.
- **V13:** every fixture and temporary patch stayed test-owned and private; no network operation,
  host configuration, service, or external state changed.
- **V15:** pure cases call existing production decisions under scoped physical-access denial; the
  18-ID registry closes every required physical seam; all 11 deliberate breaks bit.
- **V20–V21:** no production lifecycle/destructive action, hosted runner, service,
  `chaos-scheduler`, accepted plan, accepted ADR, or unrelated path changed.
- **V22:** sources, hashes, commands, versions, loads, IDs, counts, timings, caveats, deliberate
  breaks, review outcomes, and pass/fail state are recorded above.

Rollback reverts commit `328e3dd`; the original all-physical matrix returns with no stored-state or
production migration.
