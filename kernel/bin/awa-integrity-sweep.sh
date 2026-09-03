#!/usr/bin/env bash
# Session-independent AWA integrity deep sweep.
#
# AWA owns this executable and the schedule contract only. The host's local-jobs
# wrapper owns launchd activation and any 0/1/2 scheduler-success normalization.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
ROOT="${AWA_HOME:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
ENGINE="$ROOT/bin/awa-engine.sh"

# exec preserves evaluator severities (0/1/2), unexpected exits, and signals.
python3 - "$ENGINE" <<'PY' || exit 126
import os
import stat
import sys

try:
    mode = os.stat(sys.argv[1]).st_mode
except OSError:
    raise SystemExit(1)
raise SystemExit(
    0
    if stat.S_ISREG(mode) and mode & 0o111 and os.access(sys.argv[1], os.R_OK)
    else 1
)
PY
exec bash "$ENGINE" integrity verify --profile deep --trigger launchd
