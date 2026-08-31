# M5-A fast operational discovery verification — 2026-08-31

## Decision

Promote the additive fast/deep dashboard profile and the fast interactive render
default.

The representative governed-root profile improved from a 7,846.200 ms deep p50
to a 2,852.594 ms fast p50, a **63.644% controlled improvement**, while the
normalized inventory projection remained exact. This clears the accepted 30%
interactive-default gate.

The emitter API and frozen `dev-worktree.sh dashboard-data` entrypoint still
default to `deep`. Only `dashboard.render.publish()` explicitly defaults to
`fast`; `render.py --detail deep` retains the complete interactive display.

## Exact source and scope

| Item | Value |
|---|---|
| live base | `a34f16aa65730fc84b2155f87ffa352fde1cd131` |
| final implementation commit | `4977b963cc9b301bc8ce0f7398b37eda41b916b8` |
| final implementation tree | `b4d1f945244873ddf7ef97badfe68aba40e483e0` |
| implementation diff | 5 dashboard files; 516 additions, 27 deletions |
| implementation diff SHA-256 | `0a814db49c6af024cfec51795915cdf56b011ac3fd70ffd32b8d6b328f88f6e7` |

Changed files are exactly:

- `dashboard/emitter.py`;
- `dashboard/render.py`;
- `dashboard/seed.canvas.tsx`, strictly required after review proved that
  unqueried history otherwise rendered as “never” in the fast default;
- `dashboard/test_emitter.py`;
- `dashboard/test_render.py`, created because the accepted plan named this
  focused render-test surface but the live base did not yet contain it.

No kernel, engine, consumer, lifecycle, cleanup, recovery, reconciliation,
deletion, workflow, runner, or frozen CLI file changed.

Source SHA-256 values at the implementation commit:

- emitter:
  `8c5def5b8bd7e5e255ddb67ea7990ba38320176d650c9eda750487e7994073e4`;
- renderer:
  `be50cd8a93ab3384a8cb5088be75843d7b42ac2eb2e9e7de72bbf6f8a44cd7e3`;
- Canvas seed:
  `3ff20c7629e05ab39ce8c3cae899af173721054a32d1e5bcc321454d4b4edd73`;
- emitter tests:
  `1b16db8552c67c554deaae5aa5f6d0e309c83d33d651534a58808e17fd709e6f`;
- render tests:
  `326ab7d0d41cc880d0407d6ec8b1bf09c27a9218b82f2279acee67f85007326c`.

## Legacy capture and expected failure

Before production edits, a one-repository hermetic fixture captured the
normalized legacy deep projection. Generated time, absolute temporary root,
commit object ID, and filesystem-dependent size values were replaced with
typed placeholders; every stable top-level summary, repository inventory, and
worktree field/value was retained. The committed literal has SHA-256
`c673b2d7bade473ec0eb796f7d057f3c9cb67f20b3d6d84d9d64cb763df3d172`.

With only the new tests present,

`python3 -B dashboard/test_emitter.py`

failed as expected: `emitter.build()` rejected `detail`, the deep-history helper
did not exist, `render.publish()` rejected `detail`, the renderer CLI rejected
`--detail`, and the fast-default assertion observed the legacy deep call.
Existing tests remained green.

## Behavior and compatibility

- `emitter.build(root, timeout, detail="deep")` accepts only `fast|deep`.
- Direct `emitter.py` and the unchanged frozen `dashboard-data` command remain
  deep by default; `AWA_DASHBOARD_DETAIL=fast|deep` is the internal direct
  profiling selector.
- `render.publish(..., detail="fast")` and the renderer CLI default fast;
  `render.py --detail deep` explicitly requests full enrichment.
- Fast performs inventory Git probes but zero recursive `du` or commit-history
  probes. Worktree and orphan-branch enrichment fields remain present, are
  nulled, and carry `enrichment_state=not_checked`; worktree
  `plain_size="not checked"` remains honest in the rendered payload. The
  Canvas renders both unqueried work descriptions and saved times as “not
  checked,” never “never.”
- Deep preserves the normalized legacy output except additive top-level
  `detail` and per-item `enrichment_state`.
- Deep timeout, exception, or worktree identity uncertainty produces
  `enrichment_state=unknown`, nulls all enrichment values, and never copies an
  exception.
- Repository, worktree, and orphan-branch output is deterministically sorted.
- A structural test proves dashboard enrichment is not imported by production
  kernel, engine, or consumer Python paths.
- An invalid direct profiling selector exits 2 with a controlled error instead
  of a traceback.
- No cache, concurrency, schema v2, new kernel flag, safety-evidence consumer,
  or production lifecycle behavior was added.

## Hermetic fixture profile

All fixtures were generated under private system temporary directories with
inert example origins and removed after the command. Each mode warmed once and
then ran seven alternating-order observations at the same clean commit,
30-second probe timeout, Python 3.14.6, Apple Git 2.50.1, and 12 logical CPUs.
Every fast/deep normalized inventory digest matched exactly.

| Fixture | Shape | Fast p50 / p90 | Deep p50 / p90 | p50 change |
|---|---|---:|---:|---:|
| small | one clean repository/worktree | 593.634 / 627.254 ms | 663.833 / 697.617 ms | 10.575% faster |
| many-worktree | one repository, primary plus six linked worktrees | 1,721.565 / 1,798.427 ms | 2,067.648 / 2,088.584 ms | 16.738% faster |
| dirty | one worktree with an untracked file | 600.605 / 611.551 ms | 650.524 / 680.833 ms | 7.674% faster |
| stale/unresponsive | one missing registered linked worktree | 740.094 / 784.746 ms | 806.466 / 825.131 ms | 8.230% faster |
| artifact-heavy | one repository with 8,000 ignored 1 KiB artifacts | 607.989 / 641.914 ms | 658.361 / 716.799 ms | 7.651% faster |

The fixed inventory-projection SHA-256 values were respectively:

- `e92702bba5637a3ac1f9025d76b9ad4267d368104559428a0b4d30c3a6bdffc4`;
- `6a5f9d35e3ee986a652db8108c2703b1c51341302108580b6121c42ec7d84180`;
- `954e38fc7355dd21407d3f6d0a6faf3c1178fad56a87886986e631a8b0ef1dbb`;
- `9f13f8c752138c2dd625f78e6ecc39b3e161182ddb56b06cb69a91ef416e508d`;
- `692c86ff5d41d7a3ad594d8df783cf53377d3197a1750e784720c0ccb1eab331`.

The campaign began at load averages 6.18 / 5.73 / 5.75. Fixture timings
describe controlled test shapes; none independently cleared the interactive
default gate.

## Representative common-path profile

The existing governed root was profiled read-only with real state redirected
away from the engine database. It contained one enumerated repository, 13
worktrees, and zero orphan branches. Absolute paths and repository names are
intentionally not committed.

Exact command shape:

`emitter.build(governed_root, 4.0, detail=<fast|deep>)`

After one warm-up per mode, five observations ran in alternating order:

| Mode | Observations (ms) | p50 | p90 |
|---|---|---:|---:|
| fast | 3,091.996; 2,852.594; 2,801.008; 3,012.984; 2,769.307 | 2,852.594 ms | 3,060.391 ms |
| deep | 7,777.858; 7,957.458; 7,846.200; 7,713.225; 8,349.748 | 7,846.200 ms | 8,192.832 ms |

The normalized inventory projection was exact with SHA-256
`38a9c79a059372f5d506eb9d716ce795e18924cb8416022c4f463cf4801590b7`.
Source was clean and unchanged at exact commit `b4a4144`; the campaign ended at
load averages 4.25 / 5.25 / 5.56.

A separate one-pair replay hashed six stable host roles before and after:
Cursor hooks, Cursor MCP configuration, AWA release pointer, guard/control
binding pointer, installed default policy, and installed entrypoint. The
combined before/after SHA-256 was exactly
`a99d5c44f1066a3cfde1688941d4d64ed622777dbe3e18681ff5b1847472e945`.
Live engine database bytes were excluded because an independently running
engine may change them. The replay remained source-clean and observed
3.308-second fast versus 7.551-second deep execution.

These measurements authorize only the fast interactive default. They are not
a general wall-clock SLA.

## Verification

| Command | Result |
|---|---|
| `python3 -B dashboard/test_emitter.py` | final review-fix run: 30 passed in 55.883s |
| `/usr/bin/python3 -B dashboard/test_emitter.py` | final review-fix run: 30 passed in 53.918s on Python 3.9.6 |
| `python3 -B dashboard/test_render.py` | final: 4 passed |
| `python3 -B -m unittest engine.tests.test_egress_surfaces engine.tests.test_integrity_invariants -v` | 44 passed |
| `make check` | contract, policy, dashboard seed, kernel floor: PASS |
| `AWA_TEST_RECEIPT=<private> AWA_TEST_LOAD_NOTE=<context> /usr/bin/time -lp make verify` | PASS |

The pre-review authoritative full gate used the ordinary two-worker path at
clean exact commit `b4a4144`. The receipt records 1,134 engine tests: 1,119 passed, 15
intentional skips, zero failures/errors; engine elapsed 3,688.154 seconds.
The separately invoked dashboard suite passed all 28 tests in 33.684 seconds.
`make verify` ended `verify-live-verify: OK` and `verify: OK` in 3,761.69
seconds command wall time.

The full receipt has inventory SHA-256
`6eafb8101e27927d1b8d61f73861cb787fa4567ce68c63f86fa842ce5c45de02`
and file SHA-256
`f3a58eda3e6c2edccb015958c75386ac1d568e7162f1499f8765df9325a3ed21`.
Its source is clean/stable/reusable and `authorizes_skip=false`. The full log
SHA-256 is
`079907064bde3327b6cbc0de5545360f1186a0e4e8ea9c51a7bd6220df4df296`.
The starting load note was 5.12 / 5.33 / 5.58; elevated later load makes this
correctness-gate wall time non-comparable to the focused profile.

Review then required only operator-copy rendering and invalid-selector
handling. The final commit `4977b96` passed the 30-test dashboard suite on both
supported Python interpreters, the 11-test egress surface, `make check`,
`git diff --check`, and live-evidence validation. The normal runnerless PR
check remains the authoritative complete gate for that final head.

## Review

The first Bugbot pass found the misleading fast-history “never” copy and an
uncaught invalid profiling selector. Both were fixed with targeted regressions.
The complete-body re-review found no bugs.

No separate security review was added. This body changes only read-only display
collection and operator rendering, adds no write, authorization, lifecycle,
guard, cleanup, recovery, network, cache, concurrency, or safety-consumer
boundary, and the accepted plan prescribes Bugbot. The full egress and
contract checks are the proportionate boundary-specific review.

## Acceptance ledger, conditional handoff, and rollback

- **V01:** fast/deep profile tests and all normalized inventory digests are
  deterministic.
- **V13:** fixtures and state redirection were test-owned; source and stable
  host fingerprints were unchanged.
- **V17:** fast is explicitly `not_checked`; deep timeout, exception, and
  identity uncertainty are `unknown` with enrichment nulled.
- **V18:** structural tests keep display enrichment out of safety/lifecycle
  production paths.
- **V20–V21:** no safety consumer, cache, concurrency, hosted runner, workflow,
  service, lifecycle action, or `chaos-scheduler` change exists.
- **V22:** exact source, commands, tools, loads, fixture shapes, timings,
  digests, outcomes, and caveats are recorded above.

Deep enrichment remains material at a representative 7.846-second p50.
Therefore M5-B must be evaluated after M5-A merges; this is qualification to
measure bounded enrichment, not evidence that concurrency will be promoted.

Rollback reverts the five dashboard files. The emitter and frozen
`dashboard-data` compatibility default is already deep; reverting restores the
interactive deep default and removes the additive fields.
