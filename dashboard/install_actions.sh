#!/usr/bin/env bash
# Register AWA's fixed read-only refresh with an already-adopted local-jobs Canvas bridge.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
AWA_HOME="${AWA_HOME:-$(cd "$SCRIPT_DIR/.." && pwd)}"
JOB_ID="awa-dashboard-refresh"
INTERVAL=2147483647
root="${AWA_GOVERNED_ROOT:-}"
policy="${AWA_POLICY:-}"
canvas_dir="${AWA_DASHBOARD_CANVAS_DIR:-}"
enable_bridge=0

die() { printf 'awa-dashboard-actions: %s\n' "$*" >&2; exit 1; }
note() { printf 'awa-dashboard-actions: %s\n' "$*"; }

find_local_jobs() {
  if [[ -n "${AWA_LOCAL_JOBS_CLI:-}" && -x "$AWA_LOCAL_JOBS_CLI" ]]; then
    printf '%s\n' "$AWA_LOCAL_JOBS_CLI"
    return 0
  fi
  local candidate
  candidate="$(command -v local-jobs.sh 2>/dev/null || true)"
  if [[ -n "$candidate" && -x "$candidate" ]]; then
    printf '%s\n' "$candidate"
    return 0
  fi
  for candidate in \
    "$HOME/.cursor/skills/local-jobs/scripts/local-jobs.sh" \
    "$HOME/.claude/skills/local-jobs/scripts/local-jobs.sh"
  do
    if [[ -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

bridge_enabled() {
  "$1" dashboard --json 2>/dev/null | python3 -c \
    'import json,sys; raise SystemExit(0 if json.load(sys.stdin).get("run_bridge_enabled") is True else 1)'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) shift; root="${1:-}" ;;
    --policy) shift; policy="${1:-}" ;;
    --canvas-dir) shift; canvas_dir="${1:-}" ;;
    --enable-bridge) enable_bridge=1 ;;
    -h|--help)
      sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) die "unknown argument: $1" ;;
  esac
  shift
done

[[ -n "$root" ]] || die "--root or AWA_GOVERNED_ROOT is required"
[[ -n "$policy" ]] || die "--policy or AWA_POLICY is required"
[[ -d "$root" ]] || die "governed root is not a directory: $root"
[[ -f "$policy" ]] || die "policy is not a file: $policy"
local_jobs="$(find_local_jobs)" || die "local-jobs Canvas bridge is not installed"

if (( enable_bridge == 1 )); then
  "$local_jobs" enable-canvas-runs
elif ! bridge_enabled "$local_jobs"; then
  note "existing Canvas bridge is not enabled; leaving background refresh unregistered"
  exit 3
fi

program="$AWA_HOME/dashboard/render.py"
[[ -x "$program" ]] || die "dashboard renderer is not executable: $program"
args=(
  --type command
  --id "$JOB_ID"
  --program "$program"
  --arg=--root
  --arg "$root"
  --arg=--policy
  --arg "$policy"
)
if [[ -n "$canvas_dir" ]]; then
  args+=(--arg=--canvas-dir --arg "$canvas_dir")
fi

if "$local_jobs" explain-job --id "$JOB_ID" >/dev/null 2>&1; then
  # Preserve an operator's existing enabled state and cadence (the host may already schedule this
  # same read-only refresh); repair only the fixed program and arguments.
  "$local_jobs" update-job "${args[@]}"
else
  "$local_jobs" add-job "${args[@]}" --interval-seconds "$INTERVAL" --enabled false
fi
"$local_jobs" run-job --id "$JOB_ID"
note "background refresh registered through the existing Canvas bridge"
