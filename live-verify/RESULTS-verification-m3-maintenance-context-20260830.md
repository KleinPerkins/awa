# Verification M3 invocation-local maintenance context — 2026-08-30

## Decision

**Apply the invocation-local maintenance context.**

The complete accepted four-boundary guard corpus fell from 372 to 297
PATH-resolved Git children: **20.161% fewer**, above the accepted 20% gate.
Every eligible maintenance case improved by at least 34.091%. Permissions,
case IDs, refusal reasons, kernel-off behavior, source/install identity, and
owner-mode parity remained unchanged.

The context exists only inside one exact ADR 0019 bare-Git maintenance
decision. Every command invocation captures live state again. There is no
module/global cache, file artifact, environment export, memoization decorator,
or process-lifetime singleton.

## Dependency gates

| Gate | Evidence |
|---|---|
| M3-A.2 boundary mode applied | PR #142 exact head `a366cfe7db84e825f24c7d1eb30bc8cf06926859` merged normally as `2000087ecd11ce95f8025e51e6700f72a338decb` |
| repeated probes material | M3-A baseline used 18 engine, 22 source, 22 installed, and 44 owner Git children for each eligible clean maintenance decision |
| production boundary authorization | accepted plan execution and all plan-prescribed decisions were explicitly preauthorized by the operator |
| profile first | clean `origin/main` baseline was captured before the implementation and reproduced from a clean archive in the final controlled campaign |

## Closed context

Engine and embedded kernel independently produce the same private values:

- physical worktree root plus common Git directory repository identity;
- fixed physical session cwd;
- local branch, full configured upstream, and upstream remote;
- porcelain-v2 status bytes;
- operation-in-progress, hidden-index, and fast-forward ancestry results;
- merge source and complete fetch-refspec values already read for this decision;
- immutable state tokens before and after collection.

Each state token closes:

- physical worktree root and common Git directory;
- HEAD and upstream identity/OIDs;
- repository maintenance-config hash;
- porcelain-v2 status hash;
- operation-marker hash;
- index hash covering hidden-index bit changes.

Each capture also brackets its Git status read with direct config,
operation-marker, and index fingerprints and verifies the current branch ref
against the returned HEAD. Detectable drift within either capture or between
the two captures returns the existing `inspection_failed` deny.

The ordinary eligible path performs exactly two porcelain-v2 state captures,
one closed config read, and the required hidden-index inspection. It reuses
those values for the remainder of the decision. Fast-forward decisions add
the existing ancestry check. No legacy symbolic-ref, per-key config,
per-OID, per-directory, or porcelain-v1 Git reread follows a complete
context.

Invalid, multi-segment, in-command `cd`, `git -C`, `--git-dir`, and other
ineligible forms never call the collector. A missing, malformed, unsupported,
or incomplete collection calls the pre-change uncached implementation and
preserves its permission and reason. A complete but changing collection never
falls back to potentially mixed evidence.

## Controlled process campaign

The final campaign used a clean archive of
`2000087ecd11ce95f8025e51e6700f72a338decb` as baseline and the stable
five-file implementation candidate as the comparison. The candidate
implementation diff SHA-256 before this evidence file was added was
`99f48bb006d4b7e6bf478038c7696abee14318a88acc53c398e9867fa4243cdc`.
The final two-production-file diff remained unchanged after profiling and has
SHA-256
`879c7b9a7316201607c5db8c6848af3b7ce5ec97154025f91d265cf23a550d2c`.

| Context | Value |
|---|---|
| campaign UTC | `2026-08-31T00:09:48.378626+00:00` → `2026-08-31T00:11:36.168969+00:00` |
| Python | `3.14.6` |
| Git | `git version 2.50.1 (Apple Git-155)` |
| platform | `macOS-26.6.2-arm64-arm-64bit-Mach-O` |
| counter | PATH-resolved Git children only |
| load before | 6.071 / 5.487 / 5.222 |
| load after baseline | 5.608 / 5.427 / 5.212 |
| load after candidate | 7.253 / 5.899 / 5.398 |
| raw local campaign root | `/tmp/awa-m3b-campaign.bZ9S1l` |

### Complete accepted boundary corpus

| Boundary | Baseline | Candidate | Reduction | Permissions |
|---|---:|---:|---:|---|
| engine | 64 | 49 | 23.438% | unchanged, all 5 passed |
| source | 77 | 62 | 19.481% | unchanged, all 5 passed |
| installed | 77 | 62 | 19.481% | unchanged, all 5 passed |
| owner | 154 | 124 | 19.481% | unchanged, all 5 passed |
| **complete corpus** | **372** | **297** | **20.161%** | **unchanged, all 20 passed** |

The source/installed/owner whole-boundary totals each include fixed
non-maintenance cases and therefore individually show 19.481%. The closed
promotion oracle is the complete accepted four-boundary corpus above, not a
selected favorable boundary. It clears 20%. The eligible maintenance subset
also clears 20% independently on every boundary:

| Boundary | Eligible baseline | Eligible candidate | Reduction |
|---|---:|---:|---:|
| engine | 36 | 21 | 41.667% |
| source | 44 | 29 | 34.091% |
| installed | 44 | 29 | 34.091% |
| owner | 88 | 58 | 34.091% |

Near-miss, ordinary mutation, and read-only case counts were unchanged. This
confirms that ineligible forms did not enter the reusable context.

## State freshness and failure evidence

The pre-fix five-test run produced the required process failure:

- two-capture/no-reread assertion: **failed**, observed zero porcelain-v2
  captures plus the legacy symbolic-ref, three per-key config, three ref/OID,
  two directory, hidden-index, and porcelain-v1 probes;
- context/upstream, ineligible-bypass, and drift/fallback tests: **errored**
  because no collector existed;
- the existing second-invocation dirty behavior remained green.

After implementation:

- HEAD, untracked dirty state, upstream ref, repository config, and operation
  marker changes injected during collection all produced the existing
  `inspection_failed` deny in engine, source hook, and privately installed
  hook paths;
- every state-change test passed repeatedly;
- a second hook/engine invocation observed a newly dirty worktree and returned
  the existing `dirty` deny;
- a later context observed an advanced upstream OID;
- corruption of repository identity in one complete context returned
  `inspection_failed`;
- forced incomplete porcelain-v2 collection fell back to the old live probes:
  clean remained allow and dirty remained deny in source and installed hooks.

## Identity and inventory

| Artifact | SHA-256 |
|---|---|
| engine guard | `f250badd7c2b466ee865658135648692b7d5d2f5efaea59746085d59eb3656b9` |
| source and privately installed guard | `e79d650d71769998dc02d71129312eee7c3a974bb877ca641cedaf7f9661803e` |
| source and privately installed checker | `11b80f1124a4f33c840689a1e69c88ec79ea643b49e85db002485699b98b2edf` |
| source and privately installed policy | `9fcc3f184502fc1bcbee46fabe2a38b5a7abe9ec1c32d3f8a6835cdbe0c2950b` |

Source and installed interpreters were also exact: Python 3.14.6 and
`/bin/bash` 3.2.57.

The accepted M3-A.2 inventory contained 1,109 sorted unique IDs. M3-B contains
1,121 sorted unique IDs with SHA-256
`d2efdce049345b7ddc4f033cf8e3ce5342ed8cd2550b73cdd8340b65e59a63d4`.
No prior ID was removed or renamed. The 12 additions cover:

- exact two-capture/no-legacy-reread process shape;
- fresh dirty and advanced-upstream second invocations;
- ineligible collector bypass;
- five-way engine and source/installed drift;
- incomplete uncached fallback;
- corrupt-context failure;
- proof that optional-lock-disabled status leaves stale index bytes and mtime
  unchanged;
- kernel-off live behavior;
- absence of a persistent cache surface.

## Verification

| Verification | Result |
|---|---|
| required three modules on Python 3.14 | 118 tests passed in 648.538 s; 648.78 s wall |
| 11 new context tests on system Python 3.9.6 | passed in 56.752 s |
| stale-index non-refresh regression, Python 3.14 / 3.9 | passed in 1.172 s / 1.222 s |
| source + privately installed drift matrix | all five mutations denied with existing uncertainty reason |
| source + installed incomplete fallback | clean allow and dirty deny preserved |
| final four-boundary campaign | 20/20 cases passed; 372 → 297 Git children |
| `make check` | PASS |
| `bash -n`, Python compilation, `git diff --check` | PASS |
| live-evidence validator | PASS |

The required three-module command was:

`python3 -B -m unittest engine.tests.test_guard engine.tests.test_guard_hook_wrappers engine.tests.test_kernel_off_matrix -v`

## Review

The first full-branch Bugbot pass raised one medium concern that Git status
could refresh the index and create a false drift deny. The claim did not
account for the collector's explicit `GIT_OPTIONAL_LOCKS=0`. A stale-index
runtime probe preserved exact index bytes and mtime, and the permanent
regression passed on Python 3.14 and 3.9. The final full-branch Bugbot pass
reported no bugs.

The proportionate security review reported no medium, high, or critical
issues. It confirmed fail-safe drift handling, uncached fallback, ref/path
validation, no persistent context, no new secret logging, and no production
authorization bypass.

## Acceptance ledger and rollback

- **V01:** 1,109 prior test IDs remain; 12 additions are accounted for.
- **V06–V08:** permissions, case manifest, refusal reasons, engine/source/
  installed/owner parity, biting installed coverage, and kernel-off execution
  remain green.
- **V12–V13:** the candidate is serial and deterministic; context collection
  is closed, bounded by existing Git time/output limits, and fails safe.
- **V16:** every new private fixture is owned by a test temporary root; no
  shared repository, index, ref, or state root exists.
- **V20–V21:** no hosted runner, service, lifecycle/destructive action,
  `chaos-scheduler`, or unrelated production path changed.
- **V22:** base, candidate digest, commands, versions, load, counts, timings,
  counter scope, manifests, identities, and pass/fail state are recorded.

Rollback reverts this PR. The independent uncached probes are deliberately
retained in the same files and resume all decisions without migration or
stored-state cleanup.
