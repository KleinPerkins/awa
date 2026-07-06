#!/usr/bin/env bash
# Cursor sessionStart hook (AWA kernel): provide lightweight worktree-policy context.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"   # kernel/hooks
KERNEL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"                        # kernel
DEV_WORKTREE="$KERNEL_DIR/bin/dev-worktree.sh"

input="$(cat 2>/dev/null || true)"
cwd="$(python3 - "$input" <<'PY'
import json, os, sys
try:
    data=json.loads(sys.argv[1] or "{}")
except Exception:
    data={}
for key in ("cwd","workspaceRoot","root","projectRoot"):
    if data.get(key):
        print(data[key]); break
else:
    print(os.getcwd())
PY
)"

if [ -x "$DEV_WORKTREE" ] && [ -d "$cwd" ]; then
  status="$(cd "$cwd" 2>/dev/null && "$DEV_WORKTREE" status 2>/dev/null || true)"
else
  status=""
fi

mkdir -p "$HOME/.cache/dev-worktree"
DEV_WORKTREE="$DEV_WORKTREE" python3 - "$cwd" "$status" "$HOME/.cache/dev-worktree/session-status.json" <<'PY'
import datetime, json, os, pathlib, sys
cwd, status, cache = sys.argv[1:4]
status = sys.argv[2].strip()
tool = os.environ.get("DEV_WORKTREE", "dev-worktree.sh")
payload = {
    "cwd": cwd,
    "status": status,
    "updated_at": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
}
pathlib.Path(cache).write_text(json.dumps(payload, indent=2) + "\n")
if status:
    msg = ("Worktree automation context:\n" + status +
           f"\nIf classification is include and linked-worktree is no, run '{tool} ensure' before local mutation.")
else:
    msg = f"Worktree automation context unavailable; run '{tool} status' before local mutation in governed repos."
print(json.dumps({"additional_context": msg}))
PY
