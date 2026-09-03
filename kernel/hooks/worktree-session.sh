#!/usr/bin/env bash
# Cursor sessionStart hook (AWA kernel): provide lightweight worktree-policy context, refresh
# the per-root active_root/v1 heartbeat when the session is in a Safe Workspace, and surface
# DEAD-root guidance (a previously-active workspace whose path is gone). FAIL-SAFE: every added
# step is best-effort and must NEVER break session start.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"   # kernel/hooks
KERNEL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"                        # kernel
AWA_ROOT="$(cd "$KERNEL_DIR/.." && pwd)"
DEV_WORKTREE="$KERNEL_DIR/bin/dev-worktree.sh"
AWA_ROOTS_LIB="$KERNEL_DIR/lib/awa_roots.py"

input="$(cat 2>/dev/null || true)"
cwd=""
session_id=""
conversation_id=""
identity_ok="no"
eval "$(HOOK_INPUT="$input" python3 - <<'PY'
import json, os, shlex
try:
    data=json.loads(os.environ.get("HOOK_INPUT", "") or "{}")
except Exception:
    data={}
found = None
for key in ("cwd","workspaceRoot","root","projectRoot"):
    if data.get(key):
        found = data[key]; break
if found is None:
    # Cursor real payload carries workspace_roots (plural, snake_case, a list), not
    # workspaceRoot (parity fix with worktree-guard.sh, incident 2026-07-06).
    # NOTE: keep this heredoc body free of backticks/apostrophes -- bash 3.2 (macOS
    # /bin/bash) misparses them inside a command-substitution heredoc.
    roots = data.get("workspace_roots")
    if isinstance(roots, list):
        for item in roots:
            if isinstance(item, str) and item:
                found = item; break
cwd = found if found is not None else os.getcwd()

def one(keys):
    vals = {str(data[k]).strip() for k in keys
            if isinstance(data.get(k), str) and data[k].strip()}
    return next(iter(vals)) if len(vals) == 1 else ""

conversation = one(("conversation_id", "conversationId", "chat_id", "chatId"))
session = one(("session_id", "sessionId"))
if not session:
    session = os.environ.get("DEV_SESSION_ID", "").strip()
if not conversation:
    conversation = os.environ.get("AWA_FINISH_CONVERSATION_ID", "").strip()
if not session:
    session = conversation
ok = bool(session)
print("cwd=" + shlex.quote(cwd))
print("session_id=" + shlex.quote(session))
print("conversation_id=" + shlex.quote(conversation))
print("identity_ok=" + ("yes" if ok else "no"))
PY
)"

if [ -x "$DEV_WORKTREE" ] && [ -d "$cwd" ]; then
  status="$(cd "$cwd" 2>/dev/null && bash "$DEV_WORKTREE" status 2>/dev/null || true)"
else
  status=""
fi

# K1: refresh this root's active_root/v1 heartbeat when the session is in a LINKED worktree
# (a Safe Workspace). The hook is EPHEMERAL, so NO pid is recorded — disposition uses TTL-based
# liveness (a live pid would be instantly-dead and wrongly read as stale). Best-effort.
if [ -n "$status" ] && [ -f "$AWA_ROOTS_LIB" ]; then
  linked="$(printf '%s\n' "$status" | awk -F': ' '$1=="linked-worktree"{print $2; exit}')"
  repo="$(printf '%s\n' "$status" | awk -F': ' '$1=="repo"{print $2; exit}')"
  cdir="$(printf '%s\n' "$status" | awk -F': ' '$1=="git-common-dir"{print $2; exit}')"
  if [ "$linked" = "yes" ] && [ -n "$repo" ] && [ "$identity_ok" = "yes" ]; then
    branch="$(git -C "$repo" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
    [ "$branch" != "HEAD" ] || branch=""
    # Current-session identity may be projected only after the heartbeat writer has revalidated
    # this exact linked target under the shared lock. A failed heartbeat leaves no phantom binding.
    if python3 "$AWA_ROOTS_LIB" heartbeat --root "$repo" --common-dir "${cdir:-}" \
      --branch "$branch" --session-id "$session_id" >/dev/null 2>&1 \
      && [ -n "$branch" ] && [ -n "$cdir" ]; then
      python3 "$AWA_ROOTS_LIB" current-session-bind --root "$repo" \
        --session-id "$session_id" --conversation-id "$conversation_id" \
        --branch "$branch" --common-dir "$cdir" --source sessionStart >/dev/null 2>&1 || true
    fi
  fi
fi

# K1: dead-root guidance — a previously-active Safe Workspace whose recorded path no longer
# exists (removed/moved). Surfaced so the operator/agent knows work is not where it was.
dead_json=""
[ -f "$AWA_ROOTS_LIB" ] && dead_json="$(python3 "$AWA_ROOTS_LIB" dead-roots 2>/dev/null || true)"

mkdir -p "$HOME/.cache/dev-worktree"
DEV_WORKTREE="$DEV_WORKTREE" AWA_ROOT="$AWA_ROOT" DEAD_JSON="$dead_json" python3 - "$cwd" "$status" "$HOME/.cache/dev-worktree/session-status.json" <<'PY'
import datetime, json, os, pathlib, sys
cwd, status, cache = sys.argv[1:4]
status = sys.argv[2].strip()
tool = os.environ.get("DEV_WORKTREE", "dev-worktree.sh")
awa_root = os.environ.get("AWA_ROOT", "")

dead = []
try:
    parsed = json.loads(os.environ.get("DEAD_JSON") or "[]")
    if isinstance(parsed, list):
        dead = [d for d in parsed if isinstance(d, dict) and d.get("root_path")]
except Exception:
    dead = []

payload = {
    "cwd": cwd,
    "status": status,
    "dead_roots": [d.get("root_path") for d in dead],
    "updated_at": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
}
pathlib.Path(cache).write_text(json.dumps(payload, indent=2) + "\n")

parts = []
if status:
    parts.append("Worktree automation context:\n" + status +
                 f"\nIf classification is include and linked-worktree is no, run '{tool} ensure' before local mutation.")
else:
    parts.append(f"Worktree automation context unavailable; run '{tool} status' before local mutation in governed repos.")

if dead:
    listing = "\n".join(f"  - {d.get('root_path')}" for d in dead[:10])
    parts.append(
        "AWA notice: a previously-active Safe Workspace no longer exists on disk (it was "
        "removed or moved). If you expected work there, recover it from the AWA recovery "
        "archives rather than recreating it:\n" + listing
    )

parts.append(
    "AWA finish dispatcher: standalone Commit, Retain, Mixed, and Cancel are case-insensitive; "
    "destructive Close must be exactly `Close` with no surrounding whitespace. These choices may "
    "refer to persisted finish dialogue for this same conversation even when its initiating prompt "
    "was blocked before model context. Resolve them through "
    f"'python3 {awa_root}/consumer/finish_current.py dispatch --current'. "
    "Never translate yes/approval into Close. Only that dispatcher's Close path may invoke "
    "kernel finish authorization; after a removed outcome, report that the workspace was removed, "
    "the branch result, the agent is stopping, and the chat remains open, then issue no more tools."
)

print(json.dumps({"additional_context": "\n\n".join(parts)}))
PY
