#!/usr/bin/env bash
# First-prompt native-entry recovery followed by the unchanged finish hook.
# Registration is quiet, hard-bounded, and fail-open. The finish hook remains
# the sole source of stdout, stderr, and exit status.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
AWA_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ADAPTER="$AWA_ROOT/engine/native_entry_prompt_adapter.py"
FINISH="$SCRIPT_DIR/before-submit-prompt.sh"
# Command substitution normally strips trailing newlines. A non-newline
# sentinel keeps every valid JSON byte intact until the in-memory copy is made.
input="$(cat 2>/dev/null || true; printf '.')"
input="${input%.}"

if [ -f "$ADAPTER" ] && [ -r "$ADAPTER" ] && command -v python3 >/dev/null 2>&1; then
  {
    printf '%s' "$input" | \
      PYTHONDONTWRITEBYTECODE=1 \
      python3 -B "$ADAPTER" >/dev/null
  } 2>/dev/null || true
fi

# Disable pipeline aggregation for the relay: the hook result is exactly the
# unchanged finish hook's status even if the stdin writer encounters SIGPIPE.
set +o pipefail
printf '%s' "$input" 2>/dev/null | "$FINISH"
rc="${PIPESTATUS[1]}"
exit "$rc"
