#!/usr/bin/env bash
# run-tests.sh — run the AWA engine test suite (stdlib unittest; local-only, no network).
#
# SAFETY: the tests build scratch git repos in the SYSTEM temp dir (outside any governed
# repo), so their `git commit`s carry NO governed hooks and cannot chain into a host
# verifier (the historical fork-bomb). A re-entrancy guard refuses a nested run for
# defense-in-depth. Invoked as `make test` (and by a host's worktree verifier, if wired).
set -uo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
AWA_PKG_PARENT="$(cd "$SELF_DIR/../.." && pwd)"   # _ops/awa (parent of the `engine` package)

if [ "${AWA_ENGINE_TESTS_ACTIVE:-0}" = "1" ]; then
  echo "awa-engine tests: refusing re-entrant invocation" >&2
  exit 0
fi
export AWA_ENGINE_TESTS_ACTIVE=1

# Never inherit a parent repo's git env into the scratch repos.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES 2>/dev/null || true

cd "$AWA_PKG_PARENT"
rc=0
PYTHONPATH="$AWA_PKG_PARENT${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -B -m engine.tests.suite_runner "$@" || rc=$?

# Runner-only flags still execute the full inventory and must not suppress the
# dashboard gate. Ask the runner's parser instead of duplicating its grammar in
# Bash; a classifier error fails closed rather than silently dropping coverage.
dashboard_scope="filtered"
if [ "$rc" -eq 0 ]; then
  dashboard_scope="$(
    PYTHONPATH="$AWA_PKG_PARENT${PYTHONPATH:+:$PYTHONPATH}" \
      python3 -B -c '
import sys
from engine.tests.suite_runner import invocation_runs_full_inventory
print("full" if invocation_runs_full_inventory(tuple(sys.argv[1:])) else "filtered")
' "$@"
  )" || rc=$?
  if [ "$rc" -eq 0 ] && [ "$dashboard_scope" != "full" ] && [ "$dashboard_scope" != "filtered" ]; then
    echo "awa-engine tests: invalid dashboard scope classification" >&2
    rc=2
  fi
fi

# The dashboard emitter ships its own focused test suite (dashboard/test_emitter.py) that both
# PRODUCES and validates the emitted awa-worktree/v1 data. Wire it into the same gate so
# `make verify`/`make test` cover it. Only run the full dashboard pass on an unfiltered run
# (no extra args select specific engine tests), and fail the whole run if it fails.
if [ "$rc" -eq 0 ] && [ "$dashboard_scope" = "full" ] && [ -f "$AWA_PKG_PARENT/dashboard/test_emitter.py" ]; then
  PYTHONPATH="$AWA_PKG_PARENT${PYTHONPATH:+:$PYTHONPATH}" \
    python3 "$AWA_PKG_PARENT/dashboard/test_emitter.py" || rc=$?
fi

exit "$rc"
