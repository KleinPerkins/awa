# Verification lanes

Use the narrow lanes for feedback, then the required authoritative lane for the
changed surface. A receipt describes one run; it never authorizes skipping a
command.

## Select a lane

- **Docs:** `make verify-docs VERIFY_BASE=<ref>` is non-authoritative. It is
  eligible only when every changed old and new path is a contained, regular
  Markdown path. Add, modify, delete, rename, and copy are supported. An empty,
  mixed, unknown, non-Markdown, absolute/escaping, symlink, or special-file
  change selects pre-PR.
- **Focused:** `make verify-focused TESTS="<explicit selectors>"` is
  non-authoritative. Selectors are operator-supplied; no dependency inference
  chooses tests. Arbitrary focused runs have no lane-wide timing budget.
- **Pre-PR:** `make verify` is required for every runtime, test, Makefile, or
  contract change and for every mixed or unknown change. It runs the complete
  approved engine inventory, dashboard checks, the source contract freeze
  through `install.sh --check`, and live-evidence checks.
- **Install:** additionally run `make verify-install` for changes to
  `install.sh`, package/runtime projection, hook-owner behavior, installer
  behavior, or uninstall behavior. This retains direct and external
  install/repair/doctor/uninstall checks plus the complete installed-guard
  fallback.
- **Release:** run the affected release rehearsal for PM, router, finish, or
  retention surface changes. `make trial TRIAL_ARGS="..."` is the filtered
  PM/router path. Before a finish or retention release, run the complete
  transition rehearsal:
  `python3 live-verify/trial-runner/run_trial.py`. Do not run that complete
  finish matrix for unrelated changes.

## Live and fallback checks

Headless success does not prove Cursor Desktop UI rendering, hook submission,
or live agent cessation. Complete the affected steps in
`live-verify/trial-runner/LIVE-OPERATOR-RUNBOOK.md` when those surfaces change.

The authoritative serial fallback is:

```bash
AWA_TEST_JOBS=1 make verify
```

Use `make verify-guard-installed-full` when installed identity verification
refuses the layered canaries or when validating install/projection changes.

## Performance evidence

Timing and inventory findings are advisory warnings. Docs and pre-PR timing
targets remain hypotheses until each fixed workload has five passing
observations across at least two ordinary-load sessions. Focused timing remains
descriptive. Missing or incompatible process observation is reported as `not
measured`, never zero.

`make verify-performance` runs one authoritative `make verify`, then the
explicit M3 source-boundary process profile. Ordinary `make verify` does not run
that second guard corpus. Baselines are reviewed files and are never rewritten
automatically.

Receipts never skip verification, safety checks, install checks, or release
rehearsals. No local verification lane uses a paid GitHub Actions runner or a
new remote service. These local lanes remain available independently of source
CI. The G1 source CI workflow uses sharded standard GitHub-hosted runners
under the [current owner policy](https://github.com/KleinPerkins/dev/blob/main/_ops/POLICY.md#5-enforcement--source-hosted-delivery-and-installed-host).
Self-hosted runners remain forbidden. Hosted CI success does not establish App
qualification or authorize installation, the held AWA rollout, host activation,
or a product release. App writer activation additionally requires verified
initial source admission, passing merged-main CI, effective successor controls,
and actual read-only App qualification.
