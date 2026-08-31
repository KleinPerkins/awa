# Verification M4-A independent finish seeds — 2026-08-31

## Decision

**Promote the independent copy-only Git seed implementation.**

Across the closed seven-module finish cohort, setup Git processes fell from
2,544 to 874: **65.645% fewer**, above the accepted 10% gate. All 261 prior
test IDs, per-ID outcomes, and per-module inventory digests remained exact.
Total Git processes fell from 3,876 to 1,872 (**51.703% fewer**).

Wall time did not improve: the summed module observations rose from
2,320.930 seconds to 2,747.837 seconds (**18.394% slower**) on a variably
loaded host. Wall time is therefore recorded only as a caveat, not claimed as
a benefit or used as the promotion oracle.

## Source and scope

| Item | Value |
|---|---|
| controlled baseline | clean `697f9b59032d2118b432283f5ece48b5139eb68c` |
| live default base | `01c3b58b466885b7e95f410c2abcd6bf4793ac33` |
| measured implementation | clean `9e796ece9efe576929fcbd4c6f676ff958cb7b5b` |
| preserved source commit | `d2d4188eb2a144030a31f3668ca130c0b54c2c01` |
| source/current stable patch ID | `d0d283814e45ea2a665b314d2c439a8e01398967` |
| implementation diff SHA-256 | `e58de7b514bda4a6bc65405a7bebe63e84eff8ca756283b916ded8274a39ca60` |
| implementation diff | 7 test files; 328 insertions, 8 deletions |

The M4 implementation was transplanted as one content-identical commit onto
the live default base rather than merging its divergent pre-squash history.
The baseline-to-live-base delta did not alter `engine/tests/helpers.py` or any
of the seven profiled finish modules; it only promoted two-worker ordinary
verification and its own tests/docs.

The implementation changes `engine/tests/helpers.py`, adds
`engine/tests/test_helpers_seed.py`, and changes fixture construction in five
finish modules. `test_finish_phase2_final_blockers` and
`test_finish_publication_projection` are included in the measured cohort
because both consume the migrated `FinalHardeningBase` fixture. No production
file changed, including `kernel/lib/awa_finish.py`,
`kernel/lib/awa_durability.py`, and `consumer/finish_current.py`.

## Controlled process campaign

Each module ran alone through `suite_runner --jobs 1` with Git Trace2 event
capture. A setup Git process is a Trace2 `cmd_name` whose first token is
`init`, `add`, `commit`, `branch`, `remote`, or `worktree`; total Git processes
count all Trace2 `start` events. The baseline and candidate used the same Git
2.50.1 executable and Python 3.14.6.

| Module | Tests | Setup Git before → after | Reduction | Wall before → after |
|---|---:|---:|---:|---:|
| `test_finish_hardening` | 40 | 538 → 163 | 69.703% | 744.336s → 762.805s |
| `test_finish_phase2_final_blockers` | 33 | 409 → 129 | 68.460% | 354.660s → 544.800s |
| `test_finish_final_hardening` | 17 | 276 → 116 | 57.971% | 262.879s → 448.626s |
| `test_finish_kernel` | 101 | 653 → 228 | 65.084% | 295.638s → 352.691s |
| `test_finish_publication_projection` | 19 | 168 → 53 | 68.452% | 234.258s → 230.835s |
| `test_finish_conversation` | 39 | 373 → 123 | 67.024% | 248.714s → 224.663s |
| `test_finish_semantic_drift` | 12 | 127 → 62 | 51.181% | 180.445s → 183.417s |
| **closed cohort** | **261** | **2,544 → 874** | **65.645%** | **2,320.930s → 2,747.837s** |

Every row passed before and after with `source_state=stable`. Every candidate
receipt has `authorizes_skip=false`. The exact per-module inventory digests
were unchanged:

| Module | Inventory SHA-256 |
|---|---|
| `test_finish_hardening` | `950ca02dd37d74e4d44325dfffbdad5facdb0717759012415707d42d830974bf` |
| `test_finish_phase2_final_blockers` | `29c6acce40f7b7ba95e8f12400db4c323f30286d26c4606c6d8f7bd1382632c3` |
| `test_finish_final_hardening` | `67d19eb49dc266dc37aa52b3d73964a10d27b9266fb62a324000fc8fbebc3c56` |
| `test_finish_kernel` | `df8c7fbce33f7ad380415aa900ac0cc18227702d89f2a6a9eb0f626aed076934` |
| `test_finish_publication_projection` | `fe9b5d7ce6b158986914ace2a4f8d4b88615bf21f8902c954be65d15682af97b` |
| `test_finish_conversation` | `9ce5a831148bb51ee9fba72504c418fe2972b9560ee941699fdd56be4c88a943` |
| `test_finish_semantic_drift` | `b0047300ff216f9c3fd056d06fe6041c412885dd7fd5f283878ed20c725a530a` |

Raw disposable evidence roots:

- baseline: `/tmp/awa-m4a-before-697f9b5`
- candidate: `/tmp/awa-m4a-after-9e796ec`

The machine comparison is
`/tmp/awa-m4a-after-9e796ec/comparison.json`; it records
`schema=awa-m4a-profile-comparison/v1`, `valid=true`, exact inventories and
outcomes, per-row counts, aggregates, stable source, and
`authorizes_skip=false`.

The command template for each campaign row was:

`GIT_TRACE2_EVENT=<module.trace.jsonl> AWA_TEST_LOAD_NOTE="<context>" /usr/bin/time -lp python3 -B -m engine.tests.suite_runner --jobs 1 --json-out <module.receipt.json> -- <module> -v`

## Seed isolation and immutable audit

The six new seed tests first failed on the clean baseline because
`make_seeded_repo` and `_process_repo_seed` did not exist. They pass on both
supported interpreters:

| Command | Result |
|---|---|
| `python3 -B -m unittest engine.tests.test_helpers_seed -v` | 6 passed in 3.651s; Python 3.14.6 |
| `/usr/bin/python3 -B -m unittest engine.tests.test_helpers_seed -v` | 6 passed in 3.625s; Python 3.9.6 |

The tests prove:

- independent refs, config, hooks, index, common Git directories, loose
  object files, and private XDG roots;
- no alternates, `commondir`, symlink, hard link, shared inode, or special
  file;
- every file and directory is private, every regular file has link count one,
  and destinations must be new and beneath the active test temporary root;
- `fresh=True` remains an explicit escape and `origin=False` remains explicit;
- repository mutation after materialization cannot change the published
  process seed.

An exact-head audit built a 43-entry seed, observed root mode `0700`, and
returned the same digest before and after read-only audit:
`27f9dcc804b4011074fa8854a10d941b646e51e1a3195e8cfe86a0ac7705b0c8`.
This is audit-enforced process-local immutability: it detects and refuses a
changed seed at the next audit boundary. It is not an OS immutable flag or a
claim against a malicious writer inside the test process.

## Physical seams and complete verification

The focused physical cohort ran:

`AWA_TEST_LOAD_NOTE="<context>" /usr/bin/time -lp python3 -B -m engine.tests.suite_runner --jobs 1 --json-out /tmp/awa-m4a-physical-9e796ec/receipt.json -- engine.tests.test_finish_operations engine.tests.test_retention engine.tests.test_finish_durability engine.tests.test_finish_index_visibility engine.tests.test_kernel_off_matrix -v`

All 80 selected tests passed in 413.076 seconds (413.54 seconds wall) with
inventory SHA-256
`738413837baded6a6e6b6152f1e3d5e69ead5cb021298f95c8e40a28bcb22320`,
stable clean source, and `authorizes_skip=false`. This retains real Git
operation, crash-cut, fsync/`F_FULLFSYNC`, retention, publication,
descriptor/no-follow, shared-lock, removal-journal, stable-recapture,
index-visibility, and kernel-off coverage.

The ordinary final implementation gate ran:

`AWA_TEST_RECEIPT=/tmp/awa-m4a-full-9e796ec/receipt.json AWA_TEST_LOAD_NOTE="<context>" /usr/bin/time -lp make verify`

It used the ordinary `jobs=2` default and passed:

- 1,128 tests: 1,113 passed, 15 intentional skips, zero failures/errors;
- engine elapsed 3,383.523 seconds; command wall 3,474.96 seconds;
- inventory SHA-256
  `765bc15d0fd929e1aec25bebae26b180cea7a9efe2b200cd1be24b6741b616f2`;
- clean unchanged HEAD
  `9e796ece9efe576929fcbd4c6f676ff958cb7b5b`;
- `source_state=stable`, `reusable=true`, and
  `authorizes_skip=false`;
- `verify-live-verify: OK` and `verify: OK`.

The receipt load note recorded 12 logical CPUs and starting load averages
4.78 / 5.76 / 6.23. Later load varied, so neither the focused nor complete
wall observation is an SLA or a speed claim.

The controlled baseline campaign's before/after host fingerprints were exact.
After the candidate campaign, the static operator hook/config/install/pointer
hashes still matched that baseline. Live AWA database bytes are intentionally
not used as a stable oracle because the independently running engine may
update them.

## Review

Bugbot reviewed the complete branch and reported no bugs. The proportionate
security review found no medium, high, or critical issue. It confirmed that
the diff is test-only, fixture copies are independently audited and contained,
failure cleanup avoids following a replacement symlink, and the existing
production finish paths and physical tests remain in use.

The security pass also tightened two evidence descriptions: seed immutability
is explicitly the process-local audit contract described above, and seeded
repositories retain the same inert SSH `origin` as `make_repo`. The change
adds no fetch, push, clone, or other network operation; it does not claim that
materialized repositories have no configured remote.

## Acceptance ledger and rollback

- **V01:** all 261 profiled IDs and outcomes are exact; the six new IDs are
  only the closed seed-isolation proofs.
- **V06:** `test_kernel_off_matrix` passed in the physical cohort and the
  ordinary full gate.
- **V12:** every receipt is schema-validated; candidate and full receipts
  bind clean unchanged source and set `authorizes_skip=false`.
- **V13:** test repositories and XDG roots remain private and test-owned;
  controlled host fingerprints were unchanged and no new network operation
  was added.
- **V14:** independent ref/config/hook/index/common-dir/object inodes,
  no-alternate/no-link constraints, private permissions, destination
  containment, and audit-enforced process-local seed integrity all passed on
  Python 3.14 and 3.9.
- **V20–V21:** no production lifecycle/destructive action, hosted runner,
  service, `chaos-scheduler`, or unrelated path changed.
- **V22:** source, commands, versions, loads, counter scope, inventories,
  counts, timings, raw evidence locations, caveats, and pass/fail state are
  recorded above.

Rollback reverts the helper and five direct finish-fixture migrations. There
is no stored-state or production migration.
