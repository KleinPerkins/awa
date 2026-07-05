# AWA live verification harness

Operator-driven checks that **cannot** run headlessly. Each runbook produces individually
verifiable evidence (date, surface, command/output) for the security/hook ledger.

**Non-technical operator?** Start here: **[OPERATOR-CLOSEOUT.md](OPERATOR-CLOSEOUT.md)** — step-by-step
instructions for the **two remaining** closeout checks (cloud hooks + AWA MCP). No code or git required.

| Runbook | Closes | Surface |
|---------|--------|---------|
| [cloud-hooks-runbook.md](cloud-hooks-runbook.md) | L9/L10 — committed project hooks on a real cloud VM + degrade-to-allow | Cloud agent |
| [awa-mcp-runbook.md](awa-mcp-runbook.md) | Live AWA MCP tool resolution + `beforeMCPExecution` on `awa_*` tools | Desktop agent |
| [move-agent-to-root-runbook.md](move-agent-to-root-runbook.md) | R-A — `move_agent_to_root` fetch/ff-merge behavior | Desktop agent |
| [desktop-hook-redrive-runbook.md](desktop-hook-redrive-runbook.md) | Optional: capture `sessionEnd`, `workspaceOpen`, `beforeReadFile`, `afterFileEdit` records | Desktop agent |

**Bootstrap:** `bootstrap-hook-probe-uat.sh` creates a disposable local git repo with the
committed hook-probe harness wired. Use it for cloud **and** Desktop hook evidence; never copy
probe hooks into a governed repo.

**After each run:** paste the cited evidence into `SECURITY.md` (and `hook-probe/RESULTS-*.md`
for hook rows). Do not write self-referential blesses.
