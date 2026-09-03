#!/usr/bin/env bash
# Preserve the standalone guard exactly; integrity observation has no authority.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
AWA_HOME="${AWA_HOME:-$(cd "$SCRIPT_DIR/../.." && pwd -P)}"
GUARD="${AWA_INTEGRITY_GUARD:-$SCRIPT_DIR/worktree-guard.sh}"
DETACHER="${AWA_INTEGRITY_DETACHER:-$AWA_HOME/engine/integrity_detach.py}"

python3 "$DETACHER" --trigger beforeShell \
  </dev/null >/dev/null 2>&1 || :

if [[ -z "${AWA_INTEGRITY_GUARD:-}" && -e "$AWA_HOME/.git" ]]; then
  exec bash "$GUARD"
fi
exec "$GUARD"
