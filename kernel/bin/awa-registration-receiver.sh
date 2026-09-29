#!/usr/bin/env bash
# Versioned receiver launched only through an exact active projection receipt.
set -u

ROUTE="${1:-}"
AWA_ROOT="${AWA_HOME:-}"
[ -n "$AWA_ROOT" ] || exit 1
[ -d "$AWA_ROOT/engine" ] || exit 1

case "$ROUTE" in
  admission)
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="$AWA_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
      exec python3 -B -m engine.registration_hook_runtime
    ;;
  startup)
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="$AWA_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
      exec python3 -B -m engine.registration_host startup
    ;;
  tick)
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="$AWA_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
      exec python3 -B -m engine.registration_host tick
    ;;
  *)
    exit 2
    ;;
esac
