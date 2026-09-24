#!/usr/bin/env bash
# Cursor sessionStart handoff consumer. The stdlib authority validates the
# physical workspace/Git identity and performs the dedicated-lock CAS close.
# Every absent, malformed, mismatched, or contended case is intentionally quiet
# and fail-open: session start must never be blocked.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
KERNEL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
AWA_ROOT="$(cd "$KERNEL_DIR/.." && pwd)"
HANDOFF="${AWA_HANDOFF_LIB:-$KERNEL_DIR/lib/awa_handoff.py}"
input="$(cat 2>/dev/null || true)"

if [ -f "$HANDOFF" ] && [ -r "$HANDOFF" ]; then
  printf '%s' "$input" | python3 "$HANDOFF" consume >/dev/null 2>&1 || true
fi

# Distinct post-entry registration: the engine strictly parses and revalidates
# the same sessionStart payload, then adopts/attests eligible native worktrees.
# It never relies on the sibling session-context hook running first. Missing,
# slow, contended, or failed engine work stays quiet and fail-open.
if [ -f "$AWA_ROOT/engine/native_entry.py" ] && [ -r "$AWA_ROOT/engine/native_entry.py" ]; then
  printf '%s' "$input" | \
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$AWA_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
    python3 -B -m engine.native_entry >/dev/null 2>&1 || true
fi
exit 0
