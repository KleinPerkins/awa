# ADR 0022: Make two-worker verification the ordinary default
Status: accepted — 2026-08-30 (direct owner decision)

## Context

ADR 0021 required serial/parallel inventory and outcome equivalence, isolated
workers, bounded failure handling, repeatability, and a 25% performance gain
before promoting parallel verification. The completed M2 campaign proved every
correctness and safety condition for two workers across four passing parallel
runs. Their median engine time was 3,527.072 seconds versus 4,543.763 seconds
serial: 1,016.691 seconds (16.945 minutes), or 22.376%, faster.

The missed 25% planning threshold was not a safety, correctness, cleanup, or
repeatability failure. The owner has directly accepted the measured two-worker
path and rejected that arbitrary cutoff as promotion authority.

## Decision

Unqualified ordinary `make test`, `make verify`, and
`engine/tests/run-tests.sh` use two process-isolated module workers.

Explicit caller choices remain authoritative. `--jobs 1` and
`AWA_TEST_JOBS=1` select the serial fallback; an explicit command-line
`--jobs` value wins over the environment and default. Four workers remain
explicit-only because the M2 campaign hit the existing worker deadline and
failed closed.

Parallel fail-fast remains unsupported because concurrent modules cannot
preserve serial fail-fast semantics. Callers requiring `--failfast` must also
select `--jobs 1`; ambiguous use fails before any worker starts.

This decision supersedes only ADR 0021's 25% M2 promotion threshold and the M2
record's resulting `selected_jobs=1`. It preserves deterministic complete
inventory, exact outcomes and intentional skips, private worker state,
monotonic deadlines, crash/signal/timeout/malformed-result refusal, child
cleanup, receipt validation and non-authorizing semantics, the one full-run
dashboard gate, serial fallback, no-retry/no-skip behavior, and Python 3.9
compatibility.

No new execution plan is required for this bounded default-selection change.

## Evidence

- [M2 parallel-equivalence campaign](../../live-verify/RESULTS-verification-parallel-equivalence-20260829.md):
  four equivalent two-worker passes, zero selected-candidate flakes, exact
  inventory/outcome/skip manifests, strict state preservation, and complete
  worker cleanup.
- [Controlled serial baseline](../../live-verify/RESULTS-verification-serial-baseline-20260829.md):
  clean stable source, complete inventory, dashboard pass, validated receipt,
  and 4,918.76-second ordinary `make verify` observation.
- The operator's 2026-08-30 instruction is the acceptance decision.

## Consequences

Ordinary verification returns about 17 minutes sooner on the controlled M2
comparison while retaining the complete proof. Loaded hosts may realize a
different gain; timing remains descriptive and never overrides a failed gate.

Rollback is a normal reviewed change restoring the wrapper's literal default
to one worker. It requires no data migration, receipt rewrite, deadline change,
or removal of the tested parallel implementation.
