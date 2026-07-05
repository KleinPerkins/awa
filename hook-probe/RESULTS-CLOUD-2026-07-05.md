# AWA hook-probe — live CLOUD results (2026-07-05)

> Empirical results from a **live Cursor Cloud** agent on committed project hooks in
> `KleinPerkins/awa-cloud-hook-uat`. Promotes **L9 / L10** and the **cloud kernel-gate** row from
> open to **Verified (probe, cloud)**. Operator transcript redacted: broker tokens and full
> `raw_stdin` secrets are **omitted** from this file.

## Provenance

- **When:** 2026-07-05 (`20:19:52Z`–`20:20:08Z` in log timestamps).
- **Surface:** Cursor **Cloud** agent (`cursor_version` `1.0.0`, workspace root `/workspace`,
  `cloud_agent_identity_broker` in hook env — broker token redacted in operator capture).
- **Repo:** disposable `KleinPerkins/awa-cloud-hook-uat` with committed `.cursor/hooks.json` +
  `probe-hook.sh` (hook-probe harness).
- **Log:** `${XDG_STATE_HOME}/awa/hook-probe/events.jsonl` on the **cloud VM** (6 records).

## Observed events (6 records)

| Event | Count | Load-bearing payload fields |
|-------|-------|------------------------------|
| `beforeShellExecution` | 3 | `command`, `cwd`, `sandbox`, `workspace_roots` |
| `afterFileEdit` | 1 | `file_path`, `edits[]` (`old_string`/`new_string`) |
| `beforeReadFile` | 2 | `file_path`, `content`, `workspace_roots` |

**Commands gated (sample):** `cat sample.txt`, `cat README.md`, log read via `cat`.

## Desktop-only events — absent (L9)

Not present in the cloud log: `sessionStart`, `beforeSubmitPrompt`, `beforeMCPExecution`,
`stop`, `sessionEnd`, `workspaceOpen`.

**L9 (`beforeSubmitPrompt` Desktop-only):** **Verified (probe, cloud)** — absent on cloud.

## Committed project hooks on cloud (L10)

**L10:** **Verified (probe, cloud)** — committed project hooks **do fire** on a real cloud VM:
`beforeShellExecution`, `afterFileEdit`, and `beforeReadFile` all recorded with `payload_ok: true`.

User-level `~/.cursor/hooks.json` hooks are **not** in scope on cloud (unchanged design fact).

## Kernel / safety behavior

| Check | Result |
|-------|--------|
| Shell blocked? | **No** — `pwd`, edits, and `cat` all ran |
| File edit landed? | **Yes** — `sample.txt` → `edit-me: 2` |
| Cloud VM bricked? | **No** |

## Honest doc delta

The vendored doc-snapshot (2026-07-03) did not list `beforeReadFile` as cloud-available; this run
**observed** it on cloud. Treat as **empirical update**, not a refutation of L9/L10 closure.

## Verdict

**L9/L10 — Verified (probe, cloud, 2026-07-05).** Cloud committed hooks fire; Desktop-only prompt/MCP
events absent; shell gate receives `command`+`sandbox` on cloud; agent work was not blocked.
