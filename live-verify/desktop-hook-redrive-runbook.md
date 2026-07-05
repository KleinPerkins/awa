# Optional Desktop hook re-drive (capture missed records)

**Goal:** cheap follow-up to the 2026-07-05 Desktop probe — capture hook records that were **not
retained** in `events.jsonl`: `sessionEnd`, `workspaceOpen`, `beforeReadFile`, and an
`afterFileEdit` **log line** (L4 was operator-observed but not logged).

## Steps

```bash
bash ~/dev/capabilities/awa/live-verify/bootstrap-hook-probe-uat.sh ~/awa-hook-probe-redrive
rm -f "${XDG_STATE_HOME:-$HOME/.local/state}/awa/hook-probe/events.jsonl"
```

1. **Quit and reopen** Cursor with `~/awa-hook-probe-redrive` as the workspace (or File → Open)
   → targets `workspaceOpen` / `sessionStart`
2. Start a **new Desktop agent** in that window
3. Submit a one-line prompt → `beforeSubmitPrompt`
4. **Read** `README.md` → `beforeReadFile`
5. **Edit** `sample.txt` (change the number) → `afterFileEdit` (note if edit landed)
6. Run `pwd` in shell → `beforeShellExecution`
7. **Close the chat / end session** → `sessionEnd` (may require ending the composer session)
8. **Quit Cursor** → `sessionEnd` (if not already captured)

```bash
python3 ~/dev/capabilities/awa/hook-probe/analyze.py
wc -l "${XDG_STATE_HOME:-$HOME/.local/state}/awa/hook-probe/events.jsonl"
```

## Record honestly

| Event | Captured in JSONL? |
|-------|-------------------|
| `beforeReadFile` | yes/no |
| `afterFileEdit` | yes/no (+ edit landed?) |
| `sessionEnd` | yes/no |
| `workspaceOpen` | yes/no |

If an event still does not appear after deliberate driving, record **not-observed** (not
"cannot fire") unless you have evidence of platform refusal.

Append results to `hook-probe/RESULTS-2026-07-05.md` or a dated `RESULTS-YYYY-MM-DD.md`.
