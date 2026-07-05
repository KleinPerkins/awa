# AWA hook-probe — Desktop re-drive log retention (2026-07-05)

> Follow-up to `RESULTS-2026-07-05.md`. Closes **log-level** evidence for events that were
> operator-observed but **not retained** in the original `events.jsonl`.

## Method

- **Harness:** `hook-probe/redrive-capture.sh` (scripted `probe-hook.sh` invocations with realistic
  payloads — not a live Cursor agent session).
- **Workspace:** `~/awa-hook-probe-redrive` (bootstrapped via `live-verify/bootstrap-hook-probe-uat.sh`).
- **Log:** `${XDG_STATE_HOME:-~/.local/state}/awa/hook-probe/events.jsonl` (8 records).

## Log retention table

| Event | Captured in JSONL? | Notes |
|-------|-------------------|--------|
| `beforeReadFile` | **yes** | `filePath`, `workspaceRoot` |
| `afterFileEdit` | **yes** | `edits`, `filePath`, `workspaceRoot`; probe returned `deny` |
| `sessionEnd` | **yes** | `session_id`, `workspace_roots` |
| `workspaceOpen` | **yes** | `workspaceRoot`, `cursor_version` |

Also retained in this re-drive: `sessionStart`, `beforeSubmitPrompt`, `beforeShellExecution`, `stop`.

## Ledger impact

- **L4 (`afterFileEdit`):** log record now retained; original operator observation (deny ignored,
  edit landed) unchanged — this re-drive adds the missing JSONL line.
- **L3:** `beforeReadFile` shape captured (`filePath`, `workspaceRoot`).
- **sessionEnd / workspaceOpen:** recorded as **harness-captured** (proves probe wiring + logging;
  live Desktop platform fire remains corroborated by deliberate operator steps in
  `live-verify/desktop-hook-redrive-runbook.md`).

## Analyzer output (2026-07-05)

```
records:  8
surface:  Desktop
beforeReadFile         yes     1
afterFileEdit          yes     1
sessionEnd             yes     1
workspaceOpen          yes     1
```
