#!/usr/bin/env bash
# One-shot registration tick. Host scheduling remains outside AWA.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd -P)" || exit 1
AWA_ROOT="$(cd "$SCRIPT_DIR/../.." 2>/dev/null && pwd -P)" || exit 1
[ -f "$AWA_ROOT/engine/registration_receiver.py" ] || exit 1

AWA_HOME="$AWA_ROOT" \
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH="$AWA_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -B -m engine.registration_receiver tick
