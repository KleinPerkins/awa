# Live verification — AWA MCP server (Desktop)

**Goal:** confirm the `awa` MCP server registered in `~/.cursor/mcp.json` resolves its `awa_*`
tools in a live Desktop agent and that `beforeMCPExecution` fires for those calls.

Headless contract tests (`engine/tests/test_mcp.py`) prove the protocol; this runbook closes the
**live Desktop** row.

## Prereqs

- `awa` entry in `~/.cursor/mcp.json` pointing at `…/capabilities/awa/bin/awa-engine.sh` with
  args `["mcp-serve"]`
- Hook-probe UAT repo (captures `beforeMCPExecution` payloads)

```bash
bash ~/dev/capabilities/awa/live-verify/bootstrap-hook-probe-uat.sh ~/awa-mcp-uat
rm -f "${XDG_STATE_HOME:-$HOME/.local/state}/awa/hook-probe/events.jsonl"
```

Open `~/awa-mcp-uat` as a **Desktop** agent (not cloud — cloud omits MCP hooks per L10).

## Drive steps

Paste into the agent chat:

```
1. Confirm the awa MCP server is connected (list MCP tools if your UI shows them).
2. Call the awa MCP tool awa_status with no arguments. Paste the JSON result.
3. Call awa_guard_shell with cwd="/tmp" and command="git status". Paste the JSON result.
4. Report whether any beforeMCPExecution hook fired (check hook log below).
5. Run: cat "${XDG_STATE_HOME:-$HOME/.local/state}/awa/hook-probe/events.jsonl" 2>/dev/null | tail -20
```

## Analyze

```bash
python3 ~/dev/capabilities/awa/hook-probe/analyze.py
```

**Pass criteria:**

| Check | Evidence |
|-------|----------|
| `awa_status` resolves | Agent returns JSON with `wal` / `active_leases` (or honest error if state uninitialized) |
| `awa_guard_shell` resolves | JSON with `permission` field |
| `beforeMCPExecution` fired for **awa** | Log record with `tool_name` ∈ `{awa_status, awa_lease_read, awa_guard_shell}` and `mcp_server_name` = `awa` |

**Quick headless smoke (operator, before live run):**

```bash
printf '{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n' \
  | ~/dev/capabilities/awa/bin/awa-engine.sh mcp-serve \
  | python3 -c 'import json,sys; print([t["name"] for t in json.loads(sys.stdin.readline())["result"]["tools"]])'
# Expect: ['awa_status', 'awa_lease_read', 'awa_guard_shell']
```

## Evidence to record

- Date, Desktop, Cursor version
- `tools/list` names from live agent or headless smoke
- `beforeMCPExecution` JSONL line showing `mcp_server_name: awa` and an `awa_*` tool_name
- Paste into `SECURITY.md` live-verification section
