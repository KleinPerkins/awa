# Verification M3 installed-guard layering — 2026-08-30

## Decision

**Apply `installed_matrix_decision=byte_identity_plus_canaries`.**

The ordinary guard lane keeps the complete independent engine/source corpus,
verifies fresh source/install guard, checker, policy, Python, and Bash identity,
and executes a closed nine-category installed/owner canary set. The complete
pre-layering installed matrix remains serially available through
`AWA_FULL_INSTALLED_GUARD_MATRIX=1` and
`make verify-guard-installed-full`.

The measured ordinary candidate used 2,868 PATH-resolved Git children versus
3,661 before layering: **21.661% fewer**, above the accepted 15% threshold.
The candidate includes the new canaries and identity gate, so this comparison
does not hide their cost.

No production guard, checker, policy, installer, or engine decision byte
changed. Guard permissions, uncertainty behavior, direct/external owner
behavior, and kernel-off behavior remain the existing oracles.

## Accepted dependency and source

| Item | Value |
|---|---|
| M3-A.1 merged base / PR | `4dfad92472d2820f28411a9d8e552fb87b5fb2ea` / #141 |
| M3-A.2 implementation commit | `ceccbf13a8a2480dd340e7ebb1045e6a747e9158` |
| Branch | `cursor/verification-m3a2` |
| Accepted M3-A case-manifest SHA-256 | `eb4e7662f096cecc6d0a99717d71e1868552596f22abe1db61536e61d4476435` |
| Python | `3.14.6`; compatibility `3.9.6` |
| Git | `git version 2.50.1 (Apple Git-155)` |
| Platform | `macOS-26.6.2-arm64-arm-64bit-Mach-O` |
| Counter scope | `PATH-resolved git children only; hardcoded real-git exec` |

The valid candidate profiles ran immediately before the candidate was
committed. Their metadata therefore records base HEAD `4dfad924`; the measured
working bytes were then committed without alteration as `ceccbf1`, and the
expanded exact-head verification below ran cleanly on that commit.

## Instrumentation correction

The first attempted baseline is **invalid and non-counting**. It reused the
M3-A environment-dependent wrapper while a nested private profile deliberately
removed `AWA_REAL_GIT`; the owner fixture therefore reached a wrapper with an
empty real-Git path and failed as instrumentation self-contamination. Four
tests happened to pass and 3,437 wrapper entries were observed, but neither is
used as evidence. Its temporary root
`awa-m3a2-baseline.dteb6at6` was removed.

The corrected counter embeds the resolved real-Git executable in its private
wrapper. Nested private environments can therefore sanitize all `AWA_*`
variables without invalidating the measurement.

## Process and timing evidence

| Profile | Coverage | Result | Git children | Elapsed | Load average at completion |
|---|---|---:|---:|---:|---|
| valid pre-layering baseline | five accepted full parity/fallback tests | 5 passed | 3,661 | 395.732 s | 4.922 / 4.826 / 4.543 |
| ordinary layered candidate | baseline tests plus identity and nine-category canary coverage | 12 passed | 2,868 | 298.684 s | 6.851 / 5.464 / 5.190 |
| explicit full fallback | same five selectors as the baseline, full switch set | 5 passed | 3,664 | 536.738 s | 8.097 / 7.068 / 6.364 |

The ordinary comparison is intentionally conservative: it includes seven
additional selection/identity/canary tests and the runner identity preflight,
while the baseline contains only the five pre-layering tests. Despite the
higher observed load and added safety work, the count fell by 793 children.
Wall time is recorded but is not the promotion oracle.

Raw local evidence roots:

- baseline:
  `/var/folders/_q/4vp8ssd11zbg_jclqgkgyqr00000gq/T/awa-m3a2-baseline.lgvz2qe3`
- ordinary:
  `/var/folders/_q/4vp8ssd11zbg_jclqgkgyqr00000gq/T/awa-m3a2-layered.7_b6fzqz`
- fallback:
  `/var/folders/_q/4vp8ssd11zbg_jclqgkgyqr00000gq/T/awa-m3a2-fallback.e_l2h3nd`

Those roots are disposable machine evidence. This bounded record is the audit
artifact; the roots are removed after review.

## Identity, selection, and fallback

The ordinary `engine/tests/run-tests.sh` entrypoint performs a fresh private
install and refuses layered mode unless all source/installed guard, checker,
and policy hashes and the Python/Bash interpreter identities are exact.
Changing any installed guard hash or interpreter marker produced
`full installed matrix required: make verify-guard-installed-full`.

`AWA_FULL_INSTALLED_GUARD_MATRIX` accepts only `0`, empty, or exact `1`.
An ambiguous value failed before test execution with exit 2 and named the full
fallback.

`make verify-guard-installed-full` passed the exact five pre-layering test IDs
in 316.014 seconds. The fallback manifest contract independently reproduced
the accepted M3-A installed case IDs, permission outcomes, empty skip set, and
case-manifest digest.

`make verify-install` now includes the complete fallback before its private
install lifecycle.

## Closed canary registry

| Category | Registered suite test |
|---|---|
| direct allow | `TestBashGuardWrapperParity.test_m3_profile_manifest_matches_source_and_installed_permissions` |
| direct deny | `TestBashGuardWrapperParity.test_m3_profile_manifest_matches_source_and_installed_permissions` |
| external allow | `TestHookOwnerParity.test_installed_guard_owner_canaries` |
| external deny | `TestHookOwnerParity.test_installed_guard_owner_canaries` |
| uncertainty | `TestBashGuardWrapperParity.test_classifier_unavailable_asks_not_denies` |
| maintenance | `TestBashGuardWrapperParity.test_m3_profile_manifest_matches_source_and_installed_permissions` |
| malformed input | `TestBashGuardWrapperParity.test_unparseable_payload_on_included_primary_asks` |
| owner mode | `TestHookOwnerParity.test_installed_guard_owner_canaries` |
| kernel off | `InstalledGuardKernelOffCanary.test_engine_is_unimportable_in_kernel_off_canary` |

All registry IDs are loadable from ordinary suite discovery. The canary set
passed on Python 3.14 and Python 3.9. Each category was then run against its own
private wrong-verdict guard (or an importable engine for the kernel-off
negative); all nine registered tests failed with an assertion, proving that no
category is decorative.

## Inventory and verification

The accepted M3-A.1 inventory had 1,104 sorted unique test IDs with SHA-256
`db2fdb967b83fd5949f25b98694457f33d7124dea4b168ec0edc7197075eb3f7`.
M3-A.2 has 1,109 IDs with SHA-256
`0844e88ba4186767e1a2a80075c1836f917042dd8bdd1d9bb45c1b9a1f5c62ba`.
No prior ID was renamed or removed. The five additions are:

- `engine.tests.test_hook_owner_modes.TestHookOwnerParity.test_installed_guard_owner_canaries`
- `engine.tests.test_installed_guard_layering.InstalledGuardKernelOffCanary.test_engine_is_unimportable_in_kernel_off_canary`
- `engine.tests.test_installed_guard_layering.InstalledGuardLayeringTest.test_byte_or_interpreter_mismatch_refuses_layered_mode`
- `engine.tests.test_installed_guard_layering.InstalledGuardLayeringTest.test_canary_registry_covers_every_accepted_boundary`
- `engine.tests.test_installed_guard_layering.InstalledGuardLayeringTest.test_full_fallback_manifest_matches_pre_layering_manifest`

| Verification | Result |
|---|---|
| initial TDD selection/identity/fallback test | expected import failure before implementation |
| ordinary nine-category canary set, Python 3.14 | 8 tests passed in 43.478 s |
| ordinary nine-category canary set, Python 3.9 | 8 tests passed in 60.895 s |
| deliberate-break registry, Python 3.14 and 3.9 | all nine categories bit on both interpreters |
| `make verify-guard-installed-full` | 5 tests passed in 316.014 s |
| expanded exact-head guard/source/owner/kernel-off/policy/profile/layering modules | 191 tests passed in 1,680.323 s; 1,687.04 s wall |
| `make check` | PASS |
| Python 3.14 and 3.9 compilation | PASS |
| `bash -n engine/tests/run-tests.sh`; `git diff --check` | PASS |

## Acceptance ledger and rollback

- **V01:** all 1,104 prior IDs remain and the five additions are mapped above.
- **V06–V08:** kernel-off and full independent engine/source parity remain
  ordinary; every installed/direct/external/owner/uncertainty category is
  loadable and biting; the exact full fallback remains available.
- **V12–V13:** selection and identity are closed and fail safe; private
  install/repository/HOME/XDG roots are removed by their owning tests.
- **V20–V21:** no production lifecycle/destructive action, hosted runner,
  service, or `chaos-scheduler` change exists.
- **V22:** source, commands, tool versions, counter scope, counts, timings,
  load, correction, and results are recorded above.

Rollback restores the three installed loops to ordinary execution and removes
the preflight/canary/fallback wiring; no data or runtime migration exists. The
M3-A.1 profile remains valid.
