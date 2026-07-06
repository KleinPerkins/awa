# AWA live verification harness

Operator-driven checks that **cannot** run headlessly. Each runbook produces individually
verifiable evidence (date, surface, command/output) for the security/hook ledger.

**Interactive E2E session (2026-07-06):** start at **[OPERATOR-UAT-SESSION.md](OPERATOR-UAT-SESSION.md)** —
covers mode, MCP write tools, guard UX, cloud hooks, and apply-back. Evidence:
**[RESULTS-e2e-uat-20260706.md](RESULTS-e2e-uat-20260706.md)**.

**Non-technical operator?** Legacy closeout: **[OPERATOR-CLOSEOUT.md](OPERATOR-CLOSEOUT.md)**.

| Runbook | Closes | Surface |
|---------|--------|---------|
| [OPERATOR-UAT-SESSION.md](OPERATOR-UAT-SESSION.md) | Full E2E UAT (mode + MCP + lifecycle) | Desktop + Cloud |
| [cloud-hooks-runbook.md](cloud-hooks-runbook.md) | L9/L10 — committed project hooks on a real cloud VM | Cloud agent |
| [awa-mcp-runbook.md](awa-mcp-runbook.md) | Live AWA MCP + `beforeMCPExecution` on `awa_*` (incl. write tools) | Desktop agent |
| [mode-uat-runbook.md](mode-uat-runbook.md) | Per-repo ON/ASK_ON/OFF guard + dashboard | Desktop agent |
| [apply-back-uat-runbook.md](apply-back-uat-runbook.md) | SHA-bound apply-back push/PR + clean | Desktop + gh |
| [move-agent-to-root-runbook.md](move-agent-to-root-runbook.md) | R-A — `move_agent_to_root` fetch/ff-merge behavior | Desktop agent |
| [desktop-hook-redrive-runbook.md](desktop-hook-redrive-runbook.md) | Optional: extra Desktop hook events | Desktop agent |

**Bootstrap scripts:**

- `bootstrap-hook-probe-uat.sh` — disposable hook-probe repo (cloud + Desktop MCP evidence)
- `bootstrap-eligible-uat.sh` — disposable eligible repo under `~/dev/personal` (mode/guard/lifecycle)

**After each run:** paste cited evidence into `SECURITY.md` and `RESULTS-*.md`. Do not write
self-referential blesses.
