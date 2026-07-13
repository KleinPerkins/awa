#!/usr/bin/env bash
# Cursor sessionStart hook (AWA ENGINE) — SEPARATE from the kernel-only worktree-session.sh.
#
# It is one of the OPPORTUNISTIC secondary retention triggers (the deterministic PRIMARY trigger is
# prune-on-creation inside the engine). Two best-effort jobs, both FAIL-OPEN:
#   1. Fire ONE recovery-retention maintenance pass that contains NO retention logic itself and never
#      unlinks a file — it delegates 100% to the ENGINE evaluator
#      (`recover prune --maintenance --opportunistic`), which is throttled to at most once per 24h
#      (state `retention_last_run_epoch`) and takes the state-root lock NON-BLOCKING so a concurrent
#      pass simply skips. It is DETACHED so session start is never delayed.
#   2. Surface a SHORT, bounded session-context warning ONLY when the last maintenance recorded
#      errors, storage is over the soft watermark, or artifacts need repair (so automatic cleanup
#      never fails silently). Quiet (`{}`) on success.
#
# Kernel-first: everything here degrades to nothing when the engine is uninstalled/unusable, and
# kernel worktree safety/cleanup never depend on it.
set -uo pipefail

# Consume + ignore the sessionStart payload (we don't need the cwd/session identity here).
cat >/dev/null 2>&1 || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"   # kernel/hooks
AWA_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"                       # install root (…/awa/current)
ENGINE="$AWA_ROOT/bin/awa-engine.sh"

context=""
if [ -x "$ENGINE" ]; then
  # (2) Bounded, read-only prior-status surface. Only probe when engine state ALREADY exists so this
  # hook never CREATES state; parse it into a short warning ONLY on error/overage/needs-repair.
  state_base="${XDG_STATE_HOME:-$HOME/.local/state}"
  if [ -f "$state_base/awa/state.db" ]; then
    status_json="$("$ENGINE" recover status 2>/dev/null || true)"
    context="$(STATUS_JSON="$status_json" python3 - <<'PY' 2>/dev/null || true
import json, os
try:
    d = json.loads(os.environ.get("STATUS_JSON") or "{}")
except Exception:
    d = {}
msgs = []
if isinstance(d, dict):
    if d.get("last_status") == "errors":
        msgs.append("AWA recovery maintenance reported errors on its last run "
                    "(run 'awa-engine recover status' for detail).")
    over = d.get("watermark_overage_bytes") or 0
    if isinstance(over, int) and over > 0:
        mib = over / (1024 * 1024)
        msgs.append(f"AWA recovery storage is ~{mib:.0f} MiB over the soft watermark; "
                    "old unprotected artifacts will be pruned (protected ones are kept).")
    nr = d.get("needs_repair") or 0
    try:
        nr = int(nr)
    except (TypeError, ValueError):
        nr = 0
    if nr > 0:
        msgs.append(f"AWA recovery has {nr} artifact(s) needing repair "
                    "(an orphaned archive or manifest).")
print("\n".join(msgs))
PY
)"
    # (1) Detach the maintenance pass so session start is NEVER delayed (portable double-fork; macOS
    # has no `setsid`). GATED on the state db already existing (same as the probe above) so a passive
    # session start never CREATES engine state — prune-on-creation is the deterministic PRIMARY
    # trigger that first materializes it; once artifacts exist this ages them. Engine throttles +
    # serializes; all output discarded.
    ( "$ENGINE" recover prune --maintenance --opportunistic </dev/null >/dev/null 2>&1 & ) \
      >/dev/null 2>&1 || true
  fi
fi

if [ -n "${context//[[:space:]]/}" ]; then
  CTX="$context" python3 - <<'PY' 2>/dev/null || printf '{}\n'
import json, os
print(json.dumps({"additional_context": os.environ["CTX"].strip()}))
PY
else
  printf '{}\n'
fi
exit 0
