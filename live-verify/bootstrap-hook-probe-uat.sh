#!/usr/bin/env bash
# bootstrap-hook-probe-uat.sh — create a disposable repo with the hook-probe harness committed.
#
# Use for LIVE cloud (L9/L10) and Desktop hook verification. The repo is intentionally outside
# any governed tree. Cloud agents require COMMITTED project hooks — this script commits them.
#
# Usage:
#   bootstrap-hook-probe-uat.sh [TARGET_DIR]
# Default TARGET_DIR: ~/awa-hook-probe-uat
set -euo pipefail

SELF="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
AWA_ROOT="$(cd "$SELF/.." && pwd)"
PROBE="$AWA_ROOT/hook-probe"
TARGET="${1:-$HOME/awa-hook-probe-uat}"

if [ ! -f "$PROBE/hooks.json" ] || [ ! -f "$PROBE/probe-hook.sh" ]; then
  echo "bootstrap-hook-probe-uat: hook-probe harness missing under $PROBE" >&2
  exit 1
fi

if [ -e "$TARGET" ]; then
  echo "bootstrap-hook-probe-uat: target already exists: $TARGET" >&2
  echo "  Remove it or pass a different path." >&2
  exit 1
fi

mkdir -p "$TARGET/.cursor"
cp "$PROBE/hooks.json" "$TARGET/.cursor/hooks.json"
cp "$PROBE/probe-hook.sh" "$TARGET/.cursor/probe-hook.sh"
chmod +x "$TARGET/.cursor/probe-hook.sh"

# Seed file for the afterFileEdit L4 probe.
printf 'edit-me: 1\n' >"$TARGET/sample.txt"
cat >"$TARGET/README.md" <<'EOF'
# AWA hook-probe UAT (disposable)

Drive a Cursor agent here to collect hook evidence. See KleinPerkins/awa `live-verify/` runbooks.
EOF

(
  cd "$TARGET"
  git init -q
  git config user.name "AWA UAT"
  git config user.email "awa-uat@local.invalid"
  git add .
  git commit -q -m "init: hook-probe harness for live verification"
)

LOG="${XDG_STATE_HOME:-$HOME/.local/state}/awa/hook-probe/events.jsonl"
echo "bootstrap-hook-probe-uat: OK"
echo "  repo:  $TARGET"
echo "  log:   $LOG  (rm before each fresh run)"
echo ""
echo "Next:"
echo "  1. rm -f \"$LOG\""
echo "  2. Open $TARGET as a Cursor agent (Desktop or Cloud per runbook)"
echo "  3. Drive the steps in live-verify/*-runbook.md"
echo "  4. python3 \"$PROBE/analyze.py\""
