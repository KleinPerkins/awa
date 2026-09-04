# AWA authoritative verification v4 live evidence — 2026-09-03

## Result

The replacement AWA canary passed the ordinary exact-head verifier/reviewer-App
path and merged. This record supplies the AWA-side evidence for the separately
governed parent A01–A21 closure ledger; it does not replace that ledger.

Evidence was reconciled against GitHub, the live controller journal and host,
the current 18-repository default branches, and AWA `main` through
`2026-09-04T00:05:45Z`.

## Authority and delivery chain

- Controller plan:
  [`awa-authoritative-verify-fleet-relock-v4.md`](https://github.com/KleinPerkins/pr-automation-controller/blob/b0401e7c51fa13cde0b255dc4401020e018d7d67/docs/plans/awa-authoritative-verify-fleet-relock-v4.md).
- Host-authority plan:
  [`awa-authoritative-verify-fleet-relock-v4.md`](https://github.com/KleinPerkins/dev/blob/c0a7c0fe0eae1c54e81ec114ad7db05917d28098/_ops/plans/awa-authoritative-verify-fleet-relock-v4.md).
- Controller release PRs:
  [#348](https://github.com/KleinPerkins/pr-automation-controller/pull/348) and
  [#349](https://github.com/KleinPerkins/pr-automation-controller/pull/349).
- Host-authority PR:
  [KleinPerkins/dev#331](https://github.com/KleinPerkins/dev/pull/331).
- AWA bootstrap, noexec boundary, recipe, repair, and proof:
  [#151](https://github.com/KleinPerkins/awa/pull/151),
  [#152](https://github.com/KleinPerkins/awa/pull/152),
  [#153](https://github.com/KleinPerkins/awa/pull/153),
  [#156](https://github.com/KleinPerkins/awa/pull/156), and
  [#157](https://github.com/KleinPerkins/awa/pull/157).
- PR #153 was the operator-accepted delivery deviation: its exact checked head
  was merged by `KleinPerkins`, not the reviewer App. The parent ledger must
  preserve that exception rather than describe the entire chain as App-only.

## Locked command and runtime

Current AWA `main` binds:

- profile `awa-authoritative-verify.v1` at
  `sha256:85b7430a0b7974b007448e4f8d9449b140b39aefe2a234c265395372193626e5`;
- recipe digest
  `sha256:ba11d849224739e314adcde107987703c8ab620034a2b60d2e9d6e1dbf0e94bd`;
- lock digest
  `sha256:fc8e659d478dcacc0baf13b9673fe74569c78f2e5f8b02c274092175b5537494`;
- exactly one custom job, `repo.awa.engine-tests`, whose recipe and compiled
  lock both contain exactly one literal argv:
  `["run-literal", "make", "verify"]`;
- image
  `ghcr.io/kleinperkins/awa-authoritative-verify@sha256:b703c579ac68cfedf72f76f9272bae5f6fd7379a9afec40b79ff40b9fc9d90ce`;
- `network: none`, `dependency_method: none`, and no custom environment;
- limits: 7,200 seconds, 2 CPUs, 2,048 MiB memory, 512 PIDs, 8,192 MiB
  disk, 65,536 inodes, and 16,777,216 output bytes.

The host uses an ordered finite envelope: 7,200-second sandbox deadline,
8,100-second controller poll deadline, 8,400-second systemd start deadline,
and 180-second systemd stop deadline.

An independent `--pull=never` probe of that exact image used Docker runtime
`runsc`, `network=none`, a read-only root, all capabilities dropped,
`no-new-privileges`, the locked CPU/memory/PID limits, and a noexec temporary
filesystem. It found only loopback networking, zero token/secret/password/
credential/key-shaped environment names, and every declared tool at the
locked version:

`bash 5.2.15`, `Python 3.11.2`, `git 2.39.5`, `make 4.3`, `jq 1.6`,
`ripgrep 13.0.0`, `mawk 1.3.4 20200120`, `grep 3.8`, `sed 4.9`,
`cmp 3.8`, `find 4.9.0`, and GNU coreutils `9.1`.

The probe removed its container and found no residue.

## Replacement canary identity

- PR:
  [#157](https://github.com/KleinPerkins/awa/pull/157), merged.
- Base:
  `90ec7a7d62af24a27c7b2d744de6c48f19bfa10b`.
- Reviewed head:
  `17747255a2da1c04473a09bd49587ab53645cbd6`.
- Squash merge:
  `3debd94d5dd1385212aded95398abfe15e0346ba`.
- Diff: one inert 12-line canary marker plus the mechanically required
  seven-line process-evidence rebind; no runtime behavior changed.
- Controller run:
  `34f90e31-b13c-4229-baa8-2808c07a4fd8`.
- Verified attempt:
  `a6f7bc0d-55bb-471c-b832-6d09d7a4bf23`.
- Exact-head tuple:
  `sha256:66b123b48723457fdfb57af0d295ddcaab364b991891a2f05016ffc99b5b7392`.
- Changed-files digest:
  `sha256:68f75711c6ac9c211345e8bf9ed0ea9aeb323bc92298864e4baa7edef6f366ff`.
- Manifest digest:
  `sha256:0ffe9f617d17153bd6265d5f527b6c67939fd950999a0762a7d1a32c6d19cbd8`.
- Policy digest:
  `sha256:dc2aeb22a6585aa6182ff015ac52181f09c8b6bef6b070e78ef89b530c4caf34`.
- Ruleset digest:
  `sha256:93697dd878c124040be6952cbf741c87b2435e7fdd2108fcaad622582262353d`.

The journal has one current successful run, one verified attempt, and one
`job:repo.awa.engine-tests` projection for this PR/head. Execution started at
`2026-09-03T21:09:28.120975888Z` and verified at
`2026-09-03T21:54:49.062265247Z`: 2,720.941 seconds, or 45.349 minutes.

## Exact-head Checks and review

Every Check below was created by verifier App
`kleinperkins-verify-bot` integration `4274739` against the reviewed head:

| Check | Check ID | Result | GitHub interval |
|---|---:|---|---|
| [`pr-automation / verify`](https://github.com/KleinPerkins/awa/runs/100817660274) | `100817660274` | success | `21:09:07Z`–`21:55:10Z` (2,763s) |
| [`pr-automation / job:repo.awa.engine-tests`](https://github.com/KleinPerkins/awa/runs/100830803528) | `100830803528` | success | `21:54:55Z`–`21:54:56Z` |
| [`pr-automation / source`](https://github.com/KleinPerkins/awa/runs/100830874179) | `100830874179` | success | `21:55:11Z` |
| [`pr-automation / contract`](https://github.com/KleinPerkins/awa/runs/100830879722) | `100830879722` | success | `21:55:12Z` |
| [`pr-automation / tests`](https://github.com/KleinPerkins/awa/runs/100830886440) | `100830886440` | success | `21:55:13Z`–`21:55:14Z` |

Reviewer App user `kleinperkins-review-bot[bot]` (`302328093`) approved exact
head in [review `5107200879`](https://github.com/KleinPerkins/awa/pull/157#pullrequestreview-5107200879)
at `2026-09-03T21:54:59Z`. The reviewer App armed squash auto-merge one second
earlier; it merged the PR at `2026-09-03T21:55:21Z`.

## Retained output and complete inventory

The journal retained four bounded outputs:

- repository-contract stdout: 24 bytes,
  `sha256:c3aee5ed28c503f0671cd90bcc5d4761baf670c14843750901de3d1e6b4021b0`,
  with exactly one `PR_AUTOMATION_VERIFY_OK`;
- repository-contract stderr: zero bytes,
  `sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`;
- authoritative-job stdout: 1,909 bytes,
  `sha256:ab89669802c0e4ba5ffd8406859312f1733bdaad9d2e1409ce8fb0d05aee2697`;
- authoritative-job stderr: bounded 65,536 bytes,
  `sha256:b56d0a2e77520a20efbe3a4e46bb59689f8244f434112ed79df8e685de17cf74`,
  with one explicit middle-truncation marker.

The retained stdout contains the positive discovery literal, the frozen-source
contract pass, `verify: OK`, and exactly one each of the non-gating
`load_context_missing` and `inventory_growth` performance advisories. The
retained stderr closes with the dashboard result, `Ran 33 tests`.

At the merged canary source:

- the authoritative engine discovery contains 1,170 sorted unique test IDs;
- its contract digest, using `sha256("\n".join(test_ids))`, is
  `20a40d3eecd5ac040005861a3c232765d385cfcaab9ce87ce914496000279a39`;
- the gated `dashboard/test_emitter.py` inventory contains 33 sorted unique
  IDs, for 1,203 engine-plus-dashboard IDs;
- the dashboard ID-list digest is
  `bb44091d3e575ed4c5b59d353c3debf96c6a95d32fe5ca472dd322f7bca5496f`;
- the gated dashboard source digest is
  `8404b9146ca284fba3242a7aecfa6f0dcb1706722e685f78b04cc4fd62e767af`.

The `Makefile` authoritative lane invokes `bash ./install.sh --check` exactly
once. That check owns the single source-contract freeze invocation. These
topology invariants are locked by:

- `engine.tests.test_verify_lane.VerifyLaneTest.test_makefile_has_named_lanes_and_only_two_freeze_paths`;
- `engine.tests.test_contract_schemas.ContractSchemasTest.test_install_check_is_single_pre_pr_freeze_owner`;
- `engine.tests.test_performance_policy.PerformancePolicyTest.test_make_verify_advisory_runs_after_authoritative_result`.

## Failure, timeout, and child-reaping evidence

The authoritative inventory retains the named fail-closed cases:

- `engine.tests.test_performance_policy.PerformancePolicyTest.test_baseline_contract_rejects_unknown_or_incomplete_shape`;
- `engine.tests.test_performance_policy.PerformancePolicyTest.test_malformed_baseline_is_cli_failure`;
- `engine.tests.test_performance_policy.PerformancePolicyTest.test_missing_or_incompatible_process_measurement_is_not_zero`;
- `engine.tests.test_parallel_equivalence.ParallelEquivalenceTest.test_completed_peer_is_reaped_when_another_worker_times_out`;
- `engine.tests.test_parallel_equivalence.ParallelEquivalenceTest.test_every_worker_fault_fails_overall_and_reaps_processes`;
- `engine.tests.test_parallel_equivalence.ParallelEquivalenceTest.test_keyboard_interrupt_terminates_and_reaps_active_worker`;
- `engine.tests.test_parallel_equivalence.ParallelEquivalenceTest.test_parallel_cli_rejects_malformed_prior_before_worker_launch`;
- `engine.tests.test_parallel_equivalence.ParallelEquivalenceTest.test_slow_completed_output_cannot_delay_sibling_timeout_cleanup`;
- `engine.tests.test_parallel_equivalence.ParallelEquivalenceTest.test_stop_worker_escalates_to_kill_and_reaps`;
- `engine.tests.test_parallel_equivalence.ParallelEquivalenceTest.test_unmeasured_worker_gets_safe_bounded_deadline`;
- `engine.tests.test_parallel_equivalence.ParallelEquivalenceTest.test_valid_json_with_partial_default_inventory_is_rejected`;
- `engine.tests.test_parallel_equivalence.ParallelEquivalenceTest.test_valid_worker_test_failure_is_aggregated_not_retried`;
- `engine.tests.test_suite_runner.SuiteRunnerTest.test_failure_summary_is_last_bounded_actionable_evidence`;
- `engine.tests.test_suite_runner.SuiteRunnerTest.test_receipt_validator_rejects_cross_field_mismatch`;
- `engine.tests.test_suite_runner.SuiteRunnerTest.test_receipt_validator_rejects_unknown_missing_and_wrong_type`.

The controller preserved the two red predecessor heads rather than converting
failure to success:

- [#154](https://github.com/KleinPerkins/awa/pull/154), head
  `625fc94b9ad3bca478007039a0103f96d4ef0ef0`: aggregate, AWA job, and tests
  failed; source and contract passed;
- [#155](https://github.com/KleinPerkins/awa/pull/155), head
  `ce41580abf6069de59c2d5e6ea70a754ee862ad6`: aggregate, AWA job, and tests
  failed; source and contract passed.

Both PRs are now closed as superseded, unmerged, with no review or auto-merge
request. [#156](https://github.com/KleinPerkins/awa/pull/156) fixed the
remaining named-source noexec boundary and passed at exact head
`02fd239cb8a2825ac06f20a468e8de9d6b819638`.

After the canary and the independent image probe, no labeled sandbox container
remained. Only the standing, labeled fetch-egress proxy remained, as designed.

## Timing observation

The repaired implementation run in PR #156 executed for 2,779.796 seconds.
The inert replacement canary in PR #157 executed for 2,720.941 seconds: 58.855
seconds faster, or 2.12%. This is one paired operational observation, not a new
baseline, performance promise, or statistically meaningful speedup claim.

## Live host and fleet reconciliation

A fresh controller status/doctor read reported:

- release
  `sha256:ba69356cbd0c1c1ce661c79c09cc78944f5dafe9313a052b684117a19d939468`;
- activation generation `3`, 18 repositories, admission `admit`, normal
  pressure, zero in-flight attempts, zero owed runs, and zero recovery
  candidates;
- valid config, journal, and live attestation;
- AWA in `local` coverage mode with the exact profile and required job above;
- journal SQLite `integrity_check=ok`;
- the controller, recovery, and heartbeat timers active and enabled;
- the one-shot controller service last exited successfully, with
  `KillMode=control-group`.

The status also retained diagnostic `pause_cause: "crash"` while explicitly
reporting `paused: false`. The controller contract treats
`record_pause_cause` as diagnostic-only and mode-preserving. This evidence run
did not clear or otherwise mutate that field.

Fresh remote verification passed all 18 current default branches:

- 18/18 policies bind the release digest above;
- 18/18 locks validate as `pr-automation-lock/v2`, epoch 1, activation
  generation 3;
- AWA alone has a 7,200-second job limit; every other repository remains at
  300 seconds;
- all 18 have native GitHub Actions disabled and no
  `.github/workflows/*` content.

## Rollback snapshot

Before production mutation, the G1 validator reported all 25 snapshotted
artifacts valid:

- forward manifest:
  `sha256:26ccf022e0f1b2a1b03da90254a81b1e6a35e79339ea3668d49e06e9d30ab1f3`;
- rollback manifest:
  `sha256:8a14bafd259472c4fd9acaa4b1011486732424a13cb516f4c458c02e0b4e9e8f`;
- manifest index:
  `sha256:9c12e63fd50376dadc0e9adf803db847a30b71459bf47222cf5a4bdd71f4cf7c`.

Current revalidation proves 24 artifacts remain exact. The 25th,
`receipts/v4-recovery-journal.md`, is intentionally append-only: its first
14,166 bytes still match the snapshotted
`sha256:f9f6f8117b8eeba68b768cca3f1e5a9ebc7f5edd6da7ae5a25117e894fecb37a`,
with 47,868 later journal bytes appended. The original exact-size validator
therefore fails today even though the frozen prefix remains intact. The
pre-mutation receipt preserves the original 25/25 valid result.

## Local receipt registry

The detailed local receipts remain outside Git; this file records their
portable identities and salient outcomes:

| Receipt | SHA-256 |
|---|---|
| compact canary journal | `88bb024d233d3f92d6d7eaf0329dcee08b093abceb8ed91be8c77578409129da` |
| exact GitHub Checks and review | `0368a9a4268c8e08af7b7b82f9550259c7bb62e4ab9aba4b6f5c303f43daf2a8` |
| AWA PR chain | `b11c5098603cdcde25436c26bf852ed99a213cc1db178d8eec8a69d3b50b4098` |
| locked command/runtime | `cc3eeec753e3abfec815ab9e385137660e1e3cc93292925ecc51b89ecf6dad66` |
| gVisor image probe | `69d60d3c345a96b7e69049f198fa9af36358786d3b42442c479b74c3dac1b1b9` |
| selected live-host state | `0884cd27b8ca5288cdf5517ffb3ca175370c63af41875af63ae7fae8d33a1612` |
| fresh remote fleet verification | `9cddd2f8afee91b24c613526c0b3492114243f45f9adac81cd44cb5fd5669827` |
| 18-repository digest/timeout ledger | `0c05c18e4b200eea5123bfd955a6efda3696044caec61384662cb9ae822ad48f` |
| G1 snapshot revalidation | `42fb443be9d04ecba355b77278eebfbd9db4854de6552d6c8742b0b66d2043c8` |

No complete local suite was run to create this document. The new documentation
and its mechanically required process-evidence rebind must pass the ordinary
authoritative PR-controller lane before this evidence itself is final.
