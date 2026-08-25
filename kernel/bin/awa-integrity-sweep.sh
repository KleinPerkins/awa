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
exec "$ENGINE" integrity verify --profile deep --trigger launchd
