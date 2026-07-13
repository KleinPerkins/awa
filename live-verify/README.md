# AWA live verification harness

## Start here — the three UAT / verification layers

AWA's UAT / verification material spans **three layers**. Route to the one you need:

| Layer | What it proves | Entry point | Under `make verify`? |
|-------|----------------|-------------|----------------------|
| **(a) Headless finish/retention transition runner** (the finish trial's *Layer A*) | Every finish/retention state transition (Phases 1–3) driven end-to-end through the production kernel/consumer/engine surfaces; emits the executed matrix | [`trial-runner/README.md`](trial-runner/README.md) → [`trial-runner/run_trial.py`](trial-runner/run_trial.py) | Discovery/parse only — `run_trial.py --list` runs via `verify-live-verify.sh`; the full end-to-end run is intentionally **not** wired per-commit (it is the heavier pre-live / pre-release rehearsal; the finish/retention *unit* suites are what run under `make verify`) |
| **(b) Live finish operator runbook** (the finish trial's *Layer B*) | The four inherently live-Desktop-only finish surfaces (D1–D4) | [`trial-runner/LIVE-OPERATOR-RUNBOOK.md`](trial-runner/LIVE-OPERATOR-RUNBOOK.md) | No — live-operator by nature |
| **(c) Live ON/OFF guard-mode session** | Per-repo ON/OFF guard (enforced `deny`) + MCP mode tools + cloud degrade-to-allow + apply-back | [`OPERATOR-UAT-SESSION.md`](OPERATOR-UAT-SESSION.md) | No — live-operator by nature |

**Canonical executed coverage artifact:**
[`RESULTS-finish-all-transitions-trial-20260712.md`](RESULTS-finish-all-transitions-trial-20260712.md)
(the executed Layer-A matrix). It **supersedes** the static source-side audit
[`RESULTS-finish-final-rollout-20260712.md`](RESULTS-finish-final-rollout-20260712.md) (retained for
history). Live finish proof to date (display + block + `Cancel`):
[`RESULTS-finish-phase2-uat-20260712.md`](RESULTS-finish-phase2-uat-20260712.md).

> Cohesion note: this loose stitch (index + supersede banner + reconciled counts/placeholders) is the
> minimal **Option A** pass; the deeper consolidation (single coverage artifact, one runner over both
> the finish and ON/OFF suites) is tracked in issue #47.

---

## Operator-driven live checks (layers (b) and (c))

Operator-driven checks that **cannot** run headlessly. Each runbook produces individually
verifiable evidence (date, surface, command/output) for the security/hook ledger.

**Interactive E2E session (2026-07-07 — ASK_ON removal):** start at
**[OPERATOR-UAT-SESSION.md](OPERATOR-UAT-SESSION.md)** — covers ON/OFF modes, the enforced-`deny`
guard + ask-then-deny platform probe, MCP write tools (on|off only), cloud degrade-to-allow, and
apply-back. Evidence: **[RESULTS-e2e-uat-20260707.md](RESULTS-e2e-uat-20260707.md)**. The prior
session is kept as history: **[RESULTS-e2e-uat-20260706.md](RESULTS-e2e-uat-20260706.md)**.

**Non-technical operator?** Legacy closeout: **[OPERATOR-CLOSEOUT.md](OPERATOR-CLOSEOUT.md)**.

| Runbook | Closes | Surface |
|---------|--------|---------|
| [OPERATOR-UAT-SESSION.md](OPERATOR-UAT-SESSION.md) | Full E2E UAT (mode + MCP + lifecycle) | Desktop + Cloud |
| [cloud-hooks-runbook.md](cloud-hooks-runbook.md) | L9/L10 — committed project hooks on a real cloud VM | Cloud agent |
| [awa-mcp-runbook.md](awa-mcp-runbook.md) | Live AWA MCP + `beforeMCPExecution` on `awa_*` (incl. write tools) | Desktop agent |
| [mode-uat-runbook.md](mode-uat-runbook.md) | Per-repo ON/OFF guard (enforced deny) + dashboard | Desktop agent |
| [apply-back-uat-runbook.md](apply-back-uat-runbook.md) | SHA-bound apply-back push/PR + clean | Desktop + gh |
| [move-agent-to-root-runbook.md](move-agent-to-root-runbook.md) | R-A — `move_agent_to_root` fetch/ff-merge behavior | Desktop agent |
| [desktop-hook-redrive-runbook.md](desktop-hook-redrive-runbook.md) | Optional: extra Desktop hook events | Desktop agent |

**Bootstrap scripts:**

- `bootstrap-hook-probe-uat.sh` — disposable hook-probe repo (cloud + Desktop MCP evidence)
- `bootstrap-eligible-uat.sh` — disposable eligible repo under `~/dev/personal` (mode/guard/lifecycle)

**After each run:** paste cited evidence into `SECURITY.md` and `RESULTS-*.md`. Do not write
self-referential blesses.
