#!/usr/bin/env bash
# redrive-capture.sh — scripted hook-probe re-drive for log retention (Desktop follow-up).
#
# Invokes probe-hook.sh with realistic payloads for events that were operator-observed
# but not retained in the original events.jsonl. This closes log-level evidence for
# beforeReadFile, afterFileEdit, sessionEnd, and workspaceOpen — distinct from proving
# Cursor fired them (live Desktop re-drive still authoritative for platform behavior).
set -uo pipefail

PROBE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PROBE="$PROBE_DIR/probe-hook.sh"
LOG="${XDG_STATE_HOME:-$HOME/.local/state}/awa/hook-probe/events.jsonl"
WT="${1:-$HOME/awa-hook-probe-redrive}"

mkdir -p "$(dirname "$LOG")"
rm -f "$LOG"

invoke() {
  local event="$1" payload="$2"
  printf '%s' "$payload" | CURSOR_HOOK_EVENT="$event" bash "$PROBE" "$event" >/dev/null 2>&1 || true
}

# workspaceOpen / sessionStart (Desktop context)
invoke workspaceOpen '{"workspaceRoot":"'"$WT"'","cursor_version":"3.9.16"}'
invoke sessionStart '{"workspace_roots":["'"$WT"'"],"is_background_agent":false,"cursor_version":"3.9.16","session_id":"redrive-2026-07-05"}'

invoke beforeSubmitPrompt '{"prompt":"redrive capture","attachments":[],"workspace_roots":["'"$WT"'"]}'
invoke beforeReadFile '{"filePath":"README.md","workspaceRoot":"'"$WT"'"}'
invoke afterFileEdit '{"filePath":"sample.txt","edits":[{"oldString":"edit-me: 1","newString":"edit-me: 2"}],"workspaceRoot":"'"$WT"'"}'
invoke beforeShellExecution '{"command":"pwd","cwd":"'"$WT"'","sandbox":false,"workspace_roots":["'"$WT"'"]}'
invoke stop '{"status":"completed","loop_count":0,"workspace_roots":["'"$WT"'"]}'
invoke sessionEnd '{"workspace_roots":["'"$WT"'"],"session_id":"redrive-2026-07-05"}'

echo "== redrive-capture: events.jsonl =="
wc -l "$LOG"
python3 "$PROBE_DIR/analyze.py" "$LOG"
