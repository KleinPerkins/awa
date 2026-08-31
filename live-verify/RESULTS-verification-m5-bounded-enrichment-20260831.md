# M5-B bounded deep enrichment evaluation — 2026-08-31

## Decision

**No promotion.** Preserve M5-A's serial deep enrichment.

The snapshot-safe four-worker candidate improved representative p50 from
14,002.508 ms to 11,267.893 ms, or **19.529%**. This misses the accepted 20%
gate by 0.471 percentage points. It also regresses against M5-A's existing
7,846.200 ms deep p50 because the required before/after identity probes cost
more than bounded parallel enrichment saves.

No concurrency, worker selector, persistent cache, or deep-path implementation
ships. This evidence-backed rejection completes the conditional M5-B body.

## Gate and exact source

M5-A merged first through [PR #147](https://github.com/KleinPerkins/awa/pull/147)
as live commit `61454d2e340c40f43dd87e4a73e897c323604287`, with all five
runnerless checks successful.

| Item | Value |
|---|---|
| evaluated live base | `61454d2e340c40f43dd87e4a73e897c323604287` |
| candidate commit | `e2f1476d4e0d96665e70222111b6e91b4e9fd786` |
| candidate tree | `653e4ffac1d3ae7cbad09e651222b18fffd7c4cb` |
| candidate diff SHA-256 | `5ce483103fe41cefd3240b171d9c5a590fdb7eae686a71aa1360d59806dd8370` |
| rejection commit | `f1d576345624653c8682206e00bb13630a678d07` |
| final tree | `7f0f74334abb6ee826f76411331a100636c2a0d9`, exact to live M5-A |

The candidate changed only `dashboard/emitter.py` and
`dashboard/test_emitter.py`. The rejection commit restored both byte-for-byte
to the M5-A merge before this evidence file was added.

## Candidate and expected failure

Focused tests were written first for:

- closed worker choices `1|2|4`;
- deterministic input order despite reverse completion;
- canonical path, common Git directory, HEAD, and inventory-status digest
  identity;
- before/after identity drift, exception, and timeout degradation to
  per-item `unknown`;
- null worktree size and commit enrichment on uncertainty;
- no raw exception text;
- no surviving `awa-dashboard-enrich` thread;
- exact normalized deep output across worker choices.

The direct-runner inventory was reconstructed from the exact live and candidate
Git archives with `unittest.TestLoader`, normalizing the loaded main module to
the entrypoint's real `__main__` name and hashing the sorted newline-delimited
IDs. Live M5-A had 30 IDs with SHA-256
`ec09b97bf0c0bf429c3315b5db9083ffd3f54a24bc0254f9ff03801454e7dc96`;
the candidate had 36 with SHA-256
`35d70a5a951ba5b7ebd273ef4922f4cb6179b01a094f27951ef838276cda8fdd`.
No ID was removed. The exact six additions were:

- `__main__.TestBoundedDeepEnrichment.test_completion_order_cannot_change_output_order`;
- `__main__.TestBoundedDeepEnrichment.test_deep_output_is_exact_across_worker_choices`;
- `__main__.TestBoundedDeepEnrichment.test_exception_and_identity_drift_are_unknown_and_nulled`;
- `__main__.TestBoundedDeepEnrichment.test_identity_binds_path_common_dir_head_and_status_digest`;
- `__main__.TestBoundedDeepEnrichment.test_worker_choices_are_closed`;
- `__main__.TestBoundedDeepEnrichment.test_worker_threads_are_gone_when_enrichment_returns`.

The initial focused command

`python3 -B -m unittest dashboard.test_emitter.TestBoundedDeepEnrichment -v`

failed as expected because `display_item`, `read_display_identity`,
`enrich_many`, and the internal `workers` build selector did not exist.

The measured candidate then implemented:

- fixed worker choices only;
- independent read-only worktree/orphan enrichment;
- deterministic index restoration;
- bounded subprocess/future budgets;
- before/after per-item identity comparison;
- unknown/null fallback without exception copying;
- blocking executor shutdown with cancelled pending futures;
- a serial default until quantitative selection.

The candidate's six focused tests passed in 8.999 seconds on Python 3.14.6 and
15.918 seconds on system Python 3.9.6. The complete dashboard suite passed all
36 tests in 82.827 seconds.

## Hermetic worker profile

The exact M5-A fixture shapes were recreated in private system temporary
directories: small, many-worktree, dirty, stale/unresponsive, and
artifact-heavy. Each worker count warmed once, then ran three observations in
rotated order at the same clean candidate commit and 30-second timeout.

Exact profiling invocation:

`python3 -B -` with each measured call
`emitter.build(fixture_root, 30.0, detail="deep", workers=<1|2|4>)`.
The measured worker orders were `1,2,4`, `4,2,1`, then `2,4,1`; one unmeasured
warm-up used each worker count first. Fixture definitions were exactly those
listed above and in the M5-A record: one clean repository/worktree; one primary
plus six linked worktrees; one untracked dirty file; one removed-but-registered
linked worktree; and 8,000 ignored 1 KiB artifact files.

Tool/load context: Python 3.14.6, Apple Git 2.50.1, 12 logical CPUs, ending load
averages 8.80 / 7.98 / 7.49. Source was clean and unchanged. Every fixture had
one exact output digest across every observation and worker count. No worker
thread survived.

| Fixture | Workers 1 p50 / p90 | Workers 2 p50 / p90 | Workers 4 p50 / p90 |
|---|---:|---:|---:|
| small | 1,169.830 / 1,306.292 ms | 1,464.486 / 1,545.468 ms | 1,324.818 / 1,356.790 ms |
| many-worktree | 5,840.331 / 6,432.302 ms | 5,312.871 / 5,615.967 ms | 5,222.597 / 5,712.855 ms |
| dirty | 1,260.723 / 1,420.364 ms | 1,339.771 / 1,398.647 ms | 1,242.690 / 1,245.272 ms |
| stale/unresponsive | 1,657.985 / 1,661.835 ms | 1,516.310 / 1,532.842 ms | 1,419.352 / 1,468.740 ms |
| artifact-heavy | 1,342.207 / 1,415.977 ms | 1,236.102 / 1,271.304 ms | 1,275.062 / 1,278.200 ms |

The three-observation samples in worker order 1 / 2 / 4 were:

- small: `1137.659, 1169.830, 1340.408` /
  `1009.557, 1565.714, 1464.486` /
  `1139.584, 1324.818, 1364.783` ms;
- many-worktree: `5403.404, 5840.331, 6580.295` /
  `5312.871, 5202.627, 5691.741` /
  `5222.597, 5175.388, 5835.420` ms;
- dirty: `1460.274, 1260.723, 1227.967` /
  `1287.235, 1339.771, 1413.366` /
  `1228.495, 1245.917, 1242.690` ms;
- stale/unresponsive: `1657.985, 1594.827, 1662.797` /
  `1491.835, 1516.310, 1536.975` /
  `1481.087, 1378.419, 1419.352` ms;
- artifact-heavy: `1434.420, 1342.207, 1296.015` /
  `1280.105, 1236.102, 1207.933` /
  `1275.062, 1278.985, 1150.030` ms.

Output SHA-256 values in fixture order were:

- `5c1bba21cc1833862a170acc5a1135983b0f54c54c717d40bb912432fd48ebc5`;
- `858dfd35d484262aa5abcfcd6174b0b80b5cc2842785f60a9e83bfd193669e49`;
- `f8248b8ea5f88029b452eb48fae79216d02e393b8e481d533a9bbafb5bc83274`;
- `55fb51310a04eed4640d338f4e18eef275a28ca8b3fb9cacf1ff5a851aa98e19`;
- `4944fcd836e6c557bbf880e603f7c6695b0edeb7c5ed457c11ac3e6680864ba2`.

No hermetic fixture reached the required 20% p50 improvement. Four workers
improved the many-worktree p50 by 10.577%; worker overhead made the one-item
small p50 13.248% slower.

## Representative common-path profile

The existing governed root was profiled read-only with live engine state
redirected to a private empty temporary root. Absolute paths and repository
names are not committed. The inventory contained one enumerated repository,
13 worktrees, and zero orphan branches for every run.

Each worker count warmed once, then ran three observations in rotated order at
the same clean candidate commit and four-second probe timeout:

Exact profiling invocation:

`python3 -B -` with each measured call
`emitter.build(governed_root, 4.0, detail="deep", workers=<1|2|4>)`.
The measured worker orders were `1,2,4`, `4,2,1`, then `2,4,1`, after one
unmeasured warm-up per count. `XDG_STATE_HOME` pointed to the harness-owned
empty temporary directory for the entire campaign.

| Workers | Observations | p50 | p90 | Change vs worker 1 |
|---|---|---:|---:|---:|
| 1 | 12,774.139; 14,071.773; 14,002.508 ms | 14,002.508 ms | 14,057.920 ms | baseline |
| 2 | 11,439.842; 11,691.717; 11,882.888 ms | 11,691.717 ms | 11,844.654 ms | p50 16.503% faster; p90 15.744% lower |
| 4 | 11,286.455; 11,242.241; 11,267.893 ms | 11,267.893 ms | 11,282.743 ms | p50 19.529% faster; p90 19.741% lower |

All nine outputs were exact with SHA-256
`c3227b40edfc6fa14e18eb776dfa30f598d8b58f88f22455c9bdfeb60283a82f`.
Source was clean/unchanged and no worker survived. Ending load averages were
7.77 / 7.91 / 7.54.

The selected-looking four-worker result fails two honest comparisons:

1. it misses M5-B's relative p50 gate by 0.471 percentage points; and
2. versus M5-A's existing serial deep profile, p50 regresses from 7,846.200 ms
   to 11,267.893 ms and p90 from 8,192.832 ms to 11,282.743 ms.

The extra identity proof is correct but not free. Relaxing it to manufacture a
timing win would violate the accepted snapshot-consistency boundary.

## Final verification and governance

After the explicit rejection, `git diff --exit-code origin/main --` proved that
the source tree exactly matched live M5-A. The ordinary M5-A dashboard suite
then passed all 30 tests in 46.255 seconds.

The net shippable change is this evidence file only. Bugbot's evidence review
first required correct acceptance-ledger mapping, exact direct-runner IDs and
digests, and explicit profiling invocation shapes. After those corrections,
the complete-body pass found no bugs. A separate security review is not
proportionate because no candidate production code remains and no
authorization, safety, lifecycle, cleanup, recovery, network, or data boundary
changes.

## Acceptance ledger and disposition

- **V01:** the candidate dashboard inventory was the live 30-test inventory
  plus exactly the six named bounded-enrichment test IDs listed above; no
  existing ID disappeared. Rejection restored the exact 30-test live
  inventory.
- **V13:** private temporary fixtures/state were removed; source stayed clean.
- **V17:** candidate timeout, exception, and identity drift produced
  per-item `unknown` with every enrichment value nulled.
- **V18:** the evaluated work remained display-only and imported nowhere into
  safety/lifecycle paths.
- **V19:** output order and values were exact across worker completion order,
  fixed choices `1|2|4`, and repeated observations. The separate M5-B
  promotion threshold failed despite this correctness result.
- **V20–V21:** no concurrency, cache, new flag, workflow, hosted runner,
  service, lifecycle action, or `chaos-scheduler` change ships.
- **V22:** exact source, commands, fixtures, tools, load, observations,
  percentiles, digests, truth, cleanup, and decision are recorded.

`authorizes_skip=false` for both profile campaigns and this decision. M6 must
run its prescribed authoritative verification; this M5-B record cannot replace
or suppress it.
