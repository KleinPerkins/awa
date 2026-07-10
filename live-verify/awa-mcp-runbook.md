# Live verification — AWA MCP server (Desktop)

**Goal:** confirm the `awa` MCP server registered in `~/.cursor/mcp.json` resolves its `awa_*`
tools in a live Desktop agent and that `beforeMCPExecution` fires for those calls — including
**write** mode tools (`awa_mode_set`, …) added in the per-repo mode feature (round-2 hardening
fixes MCP policy resolution via `AWA_POLICY` env).

Headless contract tests (`engine/tests/test_mcp.py`) prove the protocol; this runbook closes the
**live Desktop** row.

## Prereqs

- `awa` entry in `~/.cursor/mcp.json` with `env.AWA_POLICY` → host overlay policy and
  `env.AWA_GOVERNED_ROOT` → `~/dev` (re-run overlay install or local `install.sh --repair` with
  those env vars if missing).
- Hook-probe UAT repo (captures `beforeMCPExecution` payloads)
- Run these commands from the root of an AWA source checkout.

```bash
bash live-verify/bootstrap-hook-probe-uat.sh ~/awa-mcp-uat
rm -f "${XDG_STATE_HOME:-$HOME/.local/state}/awa/hook-probe/events.jsonl"
```

Open `~/awa-mcp-uat` as a **Desktop** agent (not cloud — cloud omits MCP hooks per L10).

## Drive steps

Paste into the agent chat (extends 2026-07-05 probe with mode write tools):

```
1. Call awa_status (no args). Paste JSON.
2. Call awa_guard_shell cwd="/tmp" command="git status". Paste JSON.
3. Call awa_mode_list (no args). Paste JSON — expect default_mode on.
4. Call awa_mode_set rel="." mode="off". MUST fail (broad-off). Paste JSON — expect ok:false.
5. Call awa_mode_set rel="personal/<your-fixture>" mode="on". Paste JSON.
   (Also try mode="ask_on" once — MUST fail: only on|off accepted.)
6. Run: cat "${HOME}/.local/state/awa/hook-probe/events.jsonl" 2>/dev/null | tail -30
7. Paste any beforeMCPExecution line with mcp_server_name "awa" and tool_name awa_mode_set
   (or say NO_AWA_MCP_WRITE_HOOK_RECORD).
```

## Analyze

```bash
python3 hook-probe/analyze.py
```

**Pass criteria:**

| Check | Evidence |
|-------|----------|
| `awa_status` resolves | JSON with `wal` / `active_leases` |
| `awa_guard_shell` resolves | JSON with `permission` field |
| `awa_mode_list` resolves host modes file | `default_mode: on` |
| Broad-off rejected | `awa_mode_set rel="."` → `ok: false`, MCP `isError: true` |
| `beforeMCPExecution` for **write** tool | Log: `tool_name: awa_mode_set`, `mcp_server_name: awa` |

**Quick headless smoke (before live run):**

```bash
export AWA_POLICY=~/dev/_ops/policy/worktree-policy.yml AWA_GOVERNED_ROOT=~/dev
ENGINE=~/.local/share/awa/current/bin/awa-engine.sh
printf '{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n' | "$ENGINE" mcp-serve \
  | python3 -c 'import json,sys; print([t["name"] for t in json.loads(sys.stdin.readline())["result"]["tools"]])'
# Expect 9 tools incl. awa_mode_set … awa_mode_sync
```

## Evidence to record

- Date, Desktop, Cursor version
- `tools/list` names from live agent or headless smoke
- `beforeMCPExecution` JSONL line for an **awa_mode_*** write tool
- Paste into `SECURITY.md` and `RESULTS-e2e-uat-*.md`
