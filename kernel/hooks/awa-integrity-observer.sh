#!/usr/bin/env bash
# Fast stop-trigger integrity observation. This hook is deliberately fail-open.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
AWA_HOME="${AWA_HOME:-$(cd "$SCRIPT_DIR/../.." && pwd -P)}"
DETACHER="${AWA_INTEGRITY_DETACHER:-$AWA_HOME/engine/integrity_detach.py}"

python3 "$DETACHER" --trigger stop \
  </dev/null >/dev/null 2>&1 || :

exit 0
