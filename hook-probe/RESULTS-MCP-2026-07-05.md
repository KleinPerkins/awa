# AWA MCP — live Desktop results (2026-07-05)

> Closes the **Live AWA-MCP** ledger row: `awa` MCP tools resolve in a live Desktop agent and
> `beforeMCPExecution` fires with `mcp_server_name: awa` for real `awa_*` tool calls.

## Provenance

- **When:** 2026-07-05 (`20:29:59Z`–`20:30:06Z` in log timestamps).
- **Surface:** Cursor Desktop (`cursor_version` `3.9.16`, layout `glass`, `is_background_agent: false`).
- **Repo:** disposable `~/awa-mcp-uat` with hook-probe harness (project hooks).
- **MCP:** `awa` server via `~/.cursor/mcp.json` → `awa-engine.sh mcp-serve`.

## Tool resolution (live agent)

**`awa_status` (no args):**

```json
{"wal": "wal", "active_leases": [], "detections": []}
```

**`awa_guard_shell` (`cwd` `/tmp`, `command` `git status`):**

```json
{"permission": "allow", "reason": "not a git repo — fail open", "classification": ""}
```

## `beforeMCPExecution` for `mcp_server_name: awa`

Two records (tools called in order):

| `tool_name` | `tool_input` (summary) | `mcp_server_name` | `command` |
|-------------|------------------------|-------------------|-----------|
| `awa_status` | `{}` | `awa` | `awa` |
| `awa_guard_shell` | `cwd=/tmp`, `command=git status` | `awa` | `awa` |

**Representative log fields (redacted):** `event=beforeMCPExecution`, `payload_ok=true`,
`tool_name=awa_status`, `mcp_server_name=awa`, `workspace_roots=["…/awa-mcp-uat"]`.

Headless contract tests (`engine/tests/test_mcp.py`) covered the protocol; this run closes the
**live Desktop** integration row.

## Verdict

**Live AWA-MCP — Verified (Desktop, 2026-07-05).** Tools resolve; hook gate receives `awa_*`
calls on the `awa` MCP server.
