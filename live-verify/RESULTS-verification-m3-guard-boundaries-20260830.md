# Verification M3 guard boundaries — 2026-08-30

## Decision

**`installed_matrix_decision=byte_identity_plus_canaries`.**

The source and installed guard, checker, and policy bytes were exact; both
boundaries used the same Python and Bash interpreters; the shared case manifest
produced identical permissions; and every closed decision canary passed. This
makes M3-A.2 eligible for a later, separately authorized evaluation. It does
**not** reduce the ordinary installed matrix in this body, authorize M3-A.2, or
authorize M3-B.

No production guard, checker, policy, installer, Makefile, or test-runner byte
changed in M3-A.1. The body adds only a profile producer, its closed validator,
tests that bind existing boundaries to one manifest, and this evidence record.

## M2 serial retention

M2-B was not executed. M2-A selected `jobs=1`: the only passing parallel
candidate, `jobs=2`, improved p50 by 22.376%, below the accepted 25% promotion
threshold, and `jobs=4` safely timed out. The authoritative default therefore
remains serial. M3-A.1 proceeds under the plan's "M2 complete or explicitly
retained serial default" dependency without manufacturing a promotion.

## Controlled source and environment

| Item | Value |
|---|---|
| Base merged `origin/main` | `21f4e1229e901abe112cb26a7cbab14a50d6cb60` (PR #140) |
| Profile implementation HEAD | `3cda75440d82e4d05358016b9ec8824198490439` |
| Source state before/after profiles and exact-head suite | clean and stable |
| Branch | `cursor/verification-m3a` |
| Python profile interpreter | `Python 3.14.6` |
| Compatibility interpreter | `/usr/bin/python3`, `Python 3.9.6` |
| Git | `git version 2.50.1 (Apple Git-155)` |
| Bash | GNU Bash `3.2.57(1)-release` |
| Platform / architecture | `darwin` / `arm64` |
| Logical CPUs | 12 |
| Initial profile load | `6.28 6.65 6.76`; no competing AWA suite |
| Profile schema | `awa-guard-boundary-profile/v1` |
| Producer SHA-256 | `a36317c04018c650e85b08ed47155159ac08106518139e0f261c2059a8c2af54` |
| Case-manifest SHA-256 | `eb4e7662f096cecc6d0a99717d71e1868552596f22abe1db61536e61d4476435` |

Each case received a fresh repository plus private HOME, TMP, and XDG data,
config, state, and cache roots. Direct and externally delegated owner paths
received independent repositories and environments. Every temporary root was
removed after its case; no profile process survived.

## Shared closed case manifest

| Case ID | Command | State fixture | Expected permission |
|---|---|---|---|
| `maintenance_allow` | `git fetch` | clean, configured upstream | `allow` |
| `maintenance_dirty_deny` | `git fetch` | dirty untracked file | `deny` |
| `maintenance_near_miss_deny` | `git fetch --prune` | clean, configured upstream | `deny` |
| `mutation_deny` | `git commit --allow-empty -m profile` | clean, configured upstream | `deny` |
| `readonly_allow` | `git status` | clean, configured upstream | `allow` |

All four boundaries consumed those five case IDs in the same sorted order and
returned the exact expected permission map. The owner boundary runs both direct
and generic externally delegated paths and returns a case result only when both
agree.

## Boundary process profile

The counter scope is exactly **`PATH-resolved git children only`**. A temporary
`git` wrapper records children that resolve through PATH and then `exec`s the
real Git binary. It does not claim to count absolute-path Git children. Fixture
construction and isolated installation happen before the wrapper is active, so
the machine profile's `elapsed_ms` and Git counts describe guard decisions;
`/usr/bin/time -lp` wall time includes setup and teardown.

| Boundary | Permission result | Profile decision time | Git processes | Timed wall | User / system | Max RSS |
|---|---|---:|---:|---:|---:|---:|
| engine | exact | 7.037 s | 64 | 10.68 s | 1.05 / 1.49 s | 32,047,104 B |
| source hook | exact | 9.145 s | 77 | 11.87 s | 1.56 / 1.79 s | 31,784,960 B |
| installed hook | exact | 10.298 s | 77 | 15.48 s | 1.88 / 2.20 s | 31,965,184 B |
| direct + external owner | exact | 19.696 s | 154 | 25.91 s | 3.09 / 3.57 s | 31,703,040 B |

Per-case Git counts:

| Case ID | Engine | Source | Installed | Owner |
|---|---:|---:|---:|---:|
| `maintenance_allow` | 18 | 22 | 22 | 44 |
| `maintenance_dirty_deny` | 18 | 22 | 22 | 44 |
| `maintenance_near_miss_deny` | 7 | 11 | 11 | 22 |
| `mutation_deny` | 14 | 19 | 19 | 38 |
| `readonly_allow` | 7 | 3 | 3 | 6 |

The installed and source boundaries have the same 77-process shape, while the
owner profile is exactly the two independent paths. This identifies installed
corpus replay as a measurable boundary without yet removing it.

Exact commands, one at a time:

```bash
PYTHONDONTWRITEBYTECODE=1 /usr/bin/time -lp \
  python3 -B -m engine.tests.guard_boundary_profile \
  --boundary engine --count-git --json-out /tmp/.../engine.json

# Repeated with --boundary source, installed, and owner.
```

The four machine-validated raw documents were generated under
`/tmp/awa-m3a-profile.kP74wa/`. They are disposable local evidence; this record
retains their bounded facts and digests.

## Installed identity and interpreter proof

| Dependency | Source SHA-256 | Installed SHA-256 | Result |
|---|---|---|---|
| `kernel/hooks/worktree-guard.sh` | `4a1c81064fccf8ca8fb5bd82a4787fc6e6e17111d5fcc8c99e578cee11606974` | `4a1c81064fccf8ca8fb5bd82a4787fc6e6e17111d5fcc8c99e578cee11606974` | exact |
| `kernel/bin/dev-worktree.sh` | `11b80f1124a4f33c840689a1e69c88ec79ea643b49e85db002485699b98b2edf` | `11b80f1124a4f33c840689a1e69c88ec79ea643b49e85db002485699b98b2edf` | exact |
| `kernel/lib/awa_policy.py` | `9fcc3f184502fc1bcbee46fabe2a38b5a7abe9ec1c32d3f8a6835cdbe0c2950b` | `9fcc3f184502fc1bcbee46fabe2a38b5a7abe9ec1c32d3f8a6835cdbe0c2950b` | exact |

Independent source and installed environment probes both resolved:

- Python:
  `/opt/homebrew/Cellar/python@3.14/3.14.6/Frameworks/Python.framework/Versions/3.14/bin/python3.14|Python 3.14.6`
- Bash:
  `/bin/bash|GNU bash, version 3.2.57(1)-release (arm64-apple-darwin25)`

The installed copy came from a fresh direct install in a private HOME/XDG tree,
not the operator's installed runtime.

## Biting decision canaries

The closed decision registry contains nine required predicates. Eight unique
clean-head tests exercised them in 228.297 seconds:

| Predicate | Suite-executed proof |
|---|---|
| direct allow/deny | `TestBashGuardWrapperParity.test_m3_profile_manifest_matches_source_and_installed_permissions` |
| external zero-access | `TestHookOwnerV2Matrix.test_external_mode_is_zero_access` |
| installed allow/deny | `GuardBoundaryProfileTest.test_all_boundaries_consume_same_case_ids` |
| kernel off | `KernelOffMatrixTest.test_engine_is_actually_off_under_matrix_env` |
| maintenance | `TestBashGuardWrapperParity.test_primary_maintenance_command_corpus_engine_source_installed_parity` |
| malformed input | `TestBashGuardWrapperParity.test_unparseable_payload_on_included_primary_asks` |
| owner mode | `TestHookOwnerParity.test_m3_profile_manifest_matches_owner_paths` |
| source/engine parity | `GuardBoundaryProfileTest.test_all_boundaries_consume_same_case_ids` |
| uncertainty | `TestBashGuardWrapperParity.test_classifier_unavailable_asks_not_denies` |

The canaries bite:

- a temporary guard forced to return `allow` failed the shared profile on deny
  cases;
- classifier unavailability and malformed JSON reached their existing `ask`
  paths;
- external owner mode succeeded against an impossible hook path without
  touching it;
- changing any installed guard/checker/policy hash, Python/Bash identity,
  canary result, or full-parity result independently forced
  `installed_matrix_decision=retain_full`.

No canary or profile result authorizes a verification skip or guard action.

## Exact test inventory

The merged M2 baseline had 1,092 sorted unique IDs with SHA-256
`9199d59491b3542ea2369f3832988c7480bc31fea37d5cc2f66bdd3a6f9376d0`.
M3-A.1 has 1,104 IDs with SHA-256
`db2fdb967b83fd5949f25b98694457f33d7124dea4b168ec0edc7197075eb3f7`.
No baseline ID disappeared. The 12 planned additions are:

- `engine.tests.test_guard.TestDecideShellDegraded.test_m3_profile_manifest_matches_engine_permissions`
- `engine.tests.test_guard_boundary_profile.GuardBoundaryProfileTest.test_all_boundaries_consume_same_case_ids`
- `engine.tests.test_guard_boundary_profile.GuardBoundaryProfileTest.test_cases_use_distinct_private_home_and_xdg_roots`
- `engine.tests.test_guard_boundary_profile.GuardBoundaryProfileTest.test_cli_writes_valid_profile_document`
- `engine.tests.test_guard_boundary_profile.GuardBoundaryProfileTest.test_deliberate_guard_break_is_detected`
- `engine.tests.test_guard_boundary_profile.GuardBoundaryProfileTest.test_git_counter_reports_scope_and_never_changes_verdicts`
- `engine.tests.test_guard_boundary_profile.GuardBoundaryProfileTest.test_installed_decision_canaries_are_closed_and_suite_loadable`
- `engine.tests.test_guard_boundary_profile.GuardBoundaryProfileTest.test_installed_decision_rejects_unclosed_canary_input`
- `engine.tests.test_guard_boundary_profile.GuardBoundaryProfileTest.test_installed_decision_requires_every_identity_and_canary_gate`
- `engine.tests.test_guard_boundary_profile.GuardBoundaryProfileTest.test_profile_validator_rejects_unknown_key`
- `engine.tests.test_guard_hook_wrappers.TestBashGuardWrapperParity.test_m3_profile_manifest_matches_source_and_installed_permissions`
- `engine.tests.test_hook_owner_modes.TestHookOwnerParity.test_m3_profile_manifest_matches_owner_paths`

## Verification

| Command | Result |
|---|---|
| initial TDD run of `engine.tests.test_guard_boundary_profile` | expected import failure before the producer existed |
| full current profile integrations on Python 3.14 | 12 passed in 168.294 s |
| full current profile integrations on Python 3.9 | 12 passed in 138.252 s |
| full guard/source/installed/owner/kernel-off/policy/profile modules on clean `3cda754` | 155 passed in 1,587.527 s; wall 1,587.67 s |
| M2 runner + parallel regression modules | 39 passed in 7.066 s |
| clean-head closed decision canaries | 8 unique tests passed in 228.297 s |
| `make check` | PASS |
| Python 3.14 and 3.9 `py_compile` over changed Python files | PASS |
| `git diff --check` | PASS |

The exact-head full suite used 235.44 seconds user, 230.24 seconds system,
66,404,352 bytes max RSS, and left HEAD/status unchanged with no surviving
profile process.

## Acceptance ledger

- **V01:** 1,092 baseline IDs remained; all 12 additions are mapped above.
- **V06–V08:** kernel-off, independent engine/source parity, installed/direct/
  external owner seams, identity, uncertainty, malformed-input, maintenance,
  and deliberate-break canaries passed.
- **V12:** the profile schema rejects unknown/missing/inconsistent evidence and
  binds producer plus case-manifest digests.
- **V13:** every case uses independent temp repository/HOME/XDG roots; cleanup
  and survivor checks passed.
- **V20–V21:** no lifecycle/cleanup/destructive action, hosted runner, service,
  or `chaos-scheduler` change was added.
- **V22:** HEAD, inventory, commands, versions, machine/load context, process
  scope, timings, and results are recorded above.
- **V24:** the fixed M3 producer reports current scoped process counts; this
  body adds one bounded five-case profile/canary set, not a second full guard
  corpus.

## Rollback and next gate

Reverting commit `3cda754` removes the profile, validator, and tests; no product
state or data migration exists. The full installed matrix remains ordinary
today.

M3-A.2 may start only after this M3-A.1 Draft PR merges normally and the
operator gives a new explicit GO. It must retain the full fallback and meet its
15% process-reduction threshold or record an evidence-backed no-change result.
M3-B remains separately gated and was not started.
