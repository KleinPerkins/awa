#!/usr/bin/env bash
# Cursor sessionStart handoff consumer. The stdlib authority validates the
# physical workspace/Git identity and performs the dedicated-lock CAS close.
# Every absent, malformed, mismatched, or contended case is intentionally quiet
# and fail-open: session start must never be blocked.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
HANDOFF="${AWA_HANDOFF_LIB:-$(cd "$SCRIPT_DIR/.." && pwd)/lib/awa_handoff.py}"
input="$(cat 2>/dev/null || true)"

if [ -f "$HANDOFF" ] && [ -r "$HANDOFF" ]; then
  printf '%s' "$input" | python3 "$HANDOFF" consume >/dev/null 2>&1 || true
fi
exit 0
