#!/usr/bin/env bash
# User-level finish recall hook. This convenience fails open; Phase-1 literal-Close enforcement
# remains authoritative when this hook is missing, unsupported, malformed, or interrupted.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
AWA_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
EXECUTOR="$AWA_ROOT/consumer/finish_current.py"
input="$(cat 2>/dev/null || true)"

if [ ! -f "$EXECUTOR" ] || ! command -v python3 >/dev/null 2>&1; then
  printf '{"continue":true}\n'
  exit 0
fi

set +e
invocation_id="$(python3 - <<'PY' 2>/dev/null
import secrets
print(secrets.token_hex(16))
PY
)"
if [[ ! "$invocation_id" =~ ^[0-9a-f]{32}$ ]]; then
  printf '{"continue":true}\n'
  exit 0
fi
out="$(printf '%s' "$input" | \
  AWA_FINISH_HOOK_PUBLICATION_INVOCATION="$invocation_id" \
  python3 "$EXECUTOR" hook 2>/dev/null)"
rc=$?
set -e
if [ "$rc" -eq 0 ] && printf '%s' "$out" | python3 -c \
  'import json,sys; d=json.load(sys.stdin); assert isinstance(d.get("continue"),bool)' \
  >/dev/null 2>&1; then
  if ! printf '%s\n' "$out"; then
    # Publication is a post-output transition. A failed write leaves this generation unpublished
    # so a retry emits and blocks on the same immutable warning instead of activating a choice.
    exit 1
  fi
  # Publication is deliberately AFTER the complete JSON has been written to stdout. If this
  # process is killed at any earlier transition, hook_warning_published stays false and the
  # challenge can never be activated by a later guessed choice.
  if printf '%s' "$out" | python3 -c \
    'import json,sys; assert json.load(sys.stdin).get("continue") is False' \
    >/dev/null 2>&1; then
    printf '%s' "$input" | \
      AWA_FINISH_HOOK_PUBLICATION_INVOCATION="$invocation_id" \
      python3 "$EXECUTOR" hook-published >/dev/null 2>&1 || true
  fi
  exit 0
fi

# If preview failed after creating state, remove both dialogue and challenge before failing open.
printf '%s' "$input" | python3 "$EXECUTOR" hook-cleanup >/dev/null 2>&1 || true
printf '{"continue":true}\n'
exit 0
