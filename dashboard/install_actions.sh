#!/usr/bin/env bash
# Register AWA's fixed read-only refresh with an already-adopted local-jobs Canvas bridge.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
AWA_HOME="${AWA_HOME:-$(cd "$SCRIPT_DIR/.." && pwd)}"
JOB_ID="awa-dashboard-refresh"
INTERVAL=2147483647
OWNER_KEY="AWA_DASHBOARD_REFRESH_OWNER"
OWNER_VALUE="awa-dashboard-refresh/v1"
root="${AWA_GOVERNED_ROOT:-}"
policy="${AWA_POLICY:-}"
canvas_dir="${AWA_DASHBOARD_CANVAS_DIR:-}"
enable_bridge=0
remove_job=0

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

job_is_owned() {
  "$1" view-jobs --json 2>/dev/null | python3 -c '
import json, sys
job_id, owner_key, owner_value = sys.argv[1:]
try:
    rows = json.load(sys.stdin).get("instances", [])
except Exception:
    raise SystemExit(1)
matches = [row for row in rows if isinstance(row, dict) and row.get("id") == job_id]
if len(matches) != 1:
    raise SystemExit(1)
row = matches[0]
owned = (
    row.get("type") == "command"
    and row.get("role") == "instance"
    and isinstance(row.get("env"), dict)
    and row["env"].get(owner_key) == owner_value
)
raise SystemExit(0 if owned else 1)
' "$JOB_ID" "$OWNER_KEY" "$OWNER_VALUE"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) shift; root="${1:-}" ;;
    --policy) shift; policy="${1:-}" ;;
    --canvas-dir) shift; canvas_dir="${1:-}" ;;
    --enable-bridge) enable_bridge=1 ;;
    --remove) remove_job=1 ;;
    -h|--help)
      sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) die "unknown argument: $1" ;;
  esac
  shift
done

(( enable_bridge == 0 || remove_job == 0 )) || die "--enable-bridge and --remove cannot be combined"
if (( remove_job == 1 )); then
  local_jobs="$(find_local_jobs)" || {
    note "local-jobs is not installed; no background refresh job to remove"
    exit 0
  }
  if ! "$local_jobs" explain-job --id "$JOB_ID" >/dev/null 2>&1; then
    note "background refresh job is already absent"
    exit 0
  fi
  job_is_owned "$local_jobs" ||
    die "existing $JOB_ID job is not AWA-owned; preserving it"
  "$local_jobs" delete-job --type command --id "$JOB_ID" --confirm
  note "removed AWA-owned background refresh job"
  exit 0
fi

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
  --env "$OWNER_KEY=$OWNER_VALUE"
)
if [[ -n "$canvas_dir" ]]; then
  args+=(--arg=--canvas-dir --arg "$canvas_dir")
fi

if "$local_jobs" explain-job --id "$JOB_ID" >/dev/null 2>&1; then
  job_is_owned "$local_jobs" ||
    die "existing $JOB_ID job is not AWA-owned; refusing to replace it"
  # Preserve an operator's existing enabled state and cadence (the host may already schedule this
  # same read-only refresh); repair only the fixed program and arguments.
  "$local_jobs" update-job "${args[@]}"
else
  "$local_jobs" add-job "${args[@]}" --interval-seconds "$INTERVAL" --enabled false
fi
"$local_jobs" run-job --id "$JOB_ID"
note "background refresh registered through the existing Canvas bridge"
