#!/usr/bin/env bash
# awa-engine.sh — launcher for the AWA engine CLI (Python, stdlib + sqlite3 only).
#
# The engine (kernel core + engine layers) is the Python package `engine` at the repo
# root. This shim puts the repo root on PYTHONPATH and runs `python3 -m engine` so the
# engine's relative imports resolve regardless of the caller's cwd.
#
# The engine BACKS the frozen kernel contract (contracts/awa-contract.v1.json). It never
# changes a frozen surface; a breaking change requires a versioned contract bump.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m engine "$@"
