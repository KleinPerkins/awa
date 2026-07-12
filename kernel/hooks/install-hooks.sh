#!/usr/bin/env bash
# install-hooks.sh — install (or verify) Cursor user hooks for AWA worktree automation
# without clobbering existing hooks. Path-relative: it wires whatever checkout/install of
# the kernel hooks it lives beside, so it works both from a clone and from the installed
# runtime (~/.local/share/awa/current/kernel/hooks).
#
# Usage:
#   install-hooks.sh            install/reconcile ~/.cursor/hooks.json (idempotent)
#   install-hooks.sh --check    verify deployed==intended for the AWA hook entries
#                               (X1: catches failClosed drift). Exit 0 if OK/absent, 1 if wrong.
#
# Intended failClosed policy (X1/X2; incident 2026-07-05):
#   beforeShellExecution -> false  (soft backstop / nudge-to-worktree; hook failure MUST NOT brick)
#   beforeSubmitPrompt   -> false  (finish recall convenience; kernel remains authoritative)
#   afterFileEdit        -> unset  (observation-only, no permission gate; failClosed is a no-op here)
#   sessionStart         -> false  (fire-and-forget context; never blocks)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"   # kernel/hooks
HOOKS_JSON="${AWA_HOOKS_JSON:-$HOME/.cursor/hooks.json}"
SESSION_HOOK="$SCRIPT_DIR/worktree-session.sh"
GUARD_HOOK="$SCRIPT_DIR/worktree-guard.sh"
PROMPT_HOOK="$SCRIPT_DIR/before-submit-prompt.sh"

MODE="install"
case "${1:-}" in
  --check) MODE="check" ;;
  "") MODE="install" ;;
  *) printf 'usage: %s [--check]\n' "$0" >&2; exit 2 ;;
esac

if [ "$MODE" = "check" ]; then
  HOOKS_JSON="$HOOKS_JSON" SESSION_HOOK="$SESSION_HOOK" GUARD_HOOK="$GUARD_HOOK" \
    PROMPT_HOOK="$PROMPT_HOOK" python3 - <<'PY'
import json, os, pathlib, sys

path = os.environ["HOOKS_JSON"]
if not os.path.exists(path):
    print(f"install-hooks --check: missing required {path}", file=sys.stderr)
    sys.exit(1)
try:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
except Exception as exc:  # noqa: BLE001
    print(f"install-hooks --check: {path} is not valid JSON: {exc}", file=sys.stderr)
    sys.exit(1)
if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("hooks"), dict):
    print("install-hooks --check: object/version/hooks shape drift", file=sys.stderr)
    sys.exit(1)
hooks = data["hooks"]
expect = {
    "sessionStart": {"command": os.path.realpath(os.environ["SESSION_HOOK"]),
                     "type": "command", "timeout": 5, "failClosed": False},
    "beforeShellExecution": {"command": os.path.realpath(os.environ["GUARD_HOOK"]),
                             "type": "command", "timeout": 20, "failClosed": False},
    "beforeSubmitPrompt": {"command": os.path.realpath(os.environ["PROMPT_HOOK"]),
                           "type": "command", "matcher": "UserPromptSubmit",
                           "timeout": 20, "failClosed": False},
    "afterFileEdit": {"command": os.path.realpath(os.environ["GUARD_HOOK"]),
                      "type": "command", "timeout": 20},
}
errors = []
def awa_owned(entry, wanted_path):
    command = str(entry.get("command", ""))
    if not command or len(command.split()) != 1:
        return False
    resolved = os.path.realpath(command)
    if resolved == wanted_path:
        return True
    parts = pathlib.Path(resolved).parts
    return (len(parts) >= 5 and parts[-5:] == (
        "awa", "current", "kernel", "hooks", pathlib.Path(wanted_path).name))
for event, wanted in expect.items():
    arr = hooks.get(event)
    if not isinstance(arr, list):
        errors.append(f"{event}: missing/non-list")
        continue
    matches = [entry for entry in arr if isinstance(entry, dict)
               and awa_owned(entry, wanted["command"])]
    if len(matches) != 1:
        errors.append(f"{event}: expected one exact AWA path, found {len(matches)}")
    elif matches[0] != wanted:
        errors.append(f"{event}: exact entry drift {matches[0]!r}")
if errors:
    print("install-hooks --check: " + "; ".join(errors), file=sys.stderr)
    sys.exit(1)
print("install-hooks --check: exact AWA entries OK")
PY
  exit $?
fi

mkdir -p "$(dirname "$HOOKS_JSON")"
chmod +x "$SESSION_HOOK" "$GUARD_HOOK" "$PROMPT_HOOK"

tmp="$(mktemp)"
if [ -f "$HOOKS_JSON" ]; then
  cp "$HOOKS_JSON" "$tmp"
else
  printf '{"version":1,"hooks":{}}\n' > "$tmp"
fi

python3 - "$tmp" "$HOOKS_JSON" "$SESSION_HOOK" "$GUARD_HOOK" "$PROMPT_HOOK" <<'PY'
import json, pathlib, shutil, sys, time
src, dest, session_hook, guard_hook, prompt_hook = map(pathlib.Path, sys.argv[1:6])
try:
    data = json.loads(src.read_text())
except Exception as exc:
    print(f"install-hooks: refusing malformed JSON without writing: {exc}", file=sys.stderr)
    sys.exit(1)
if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("hooks"), dict):
    print("install-hooks: refusing invalid object/version/hooks shape without writing", file=sys.stderr)
    sys.exit(1)
hooks = data["hooks"]
for event, arr in hooks.items():
    if not isinstance(event, str) or not isinstance(arr, list):
        print("install-hooks: refusing malformed hooks shape without writing", file=sys.stderr)
        sys.exit(1)
    if not all(isinstance(entry, dict) for entry in arr):
        print("install-hooks: refusing non-object hook entry without writing", file=sys.stderr)
        sys.exit(1)

session_hook = session_hook.resolve()
guard_hook = guard_hook.resolve()
prompt_hook = prompt_hook.resolve()

def awa_owned(existing, wanted_path):
    command = str(existing.get("command", ""))
    if not command or len(command.split()) != 1:
        return False
    resolved = pathlib.Path(command).expanduser().resolve()
    if resolved == wanted_path:
        return True
    parts = resolved.parts
    return (len(parts) >= 5 and parts[-5:] == (
        "awa", "current", "kernel", "hooks", wanted_path.name))

def ensure(event, entry):
    arr = hooks.setdefault(event, [])
    wanted_path = pathlib.Path(entry["command"])
    kept = [existing for existing in arr if not awa_owned(existing, wanted_path)]
    kept.append(entry)
    hooks[event] = kept

ensure("sessionStart", {
    "command": str(session_hook),
    "type": "command",
    "timeout": 5,
    "failClosed": False,
})
# beforeShellExecution is the soft worktree backstop -> fail OPEN on hook failure (incident
# 2026-07-05: failClosed:true on a global gate bricked every workspace under load/timeout).
ensure("beforeShellExecution", {
    "command": str(guard_hook),
    "type": "command",
    "timeout": 20,
    "failClosed": False,
})
# beforeSubmitPrompt may block only a successfully rendered local preview. Infrastructure failure
# stays fail-open globally; missing/invalid authorization still fails closed in the Phase-1 kernel.
ensure("beforeSubmitPrompt", {
    "command": str(prompt_hook),
    "type": "command",
    "matcher": "UserPromptSubmit",
    "timeout": 20,
    "failClosed": False,
})
# afterFileEdit is observation-only (Cursor ignores any returned permission). failClosed is a
# no-op here, so we do NOT set it (X2); drop it if a prior install wrote it.
ensure("afterFileEdit", {
    "command": str(guard_hook),
    "type": "command",
    "timeout": 20,
})

new = json.dumps(data, indent=2, sort_keys=False) + "\n"
old = dest.read_text() if dest.exists() else None
if old != new:
    if dest.exists():
        shutil.copy2(dest, dest.with_name(dest.name + f".bak-{int(time.time())}"))
    dest.write_text(new)
    print(f"install-hooks: updated {dest}")
else:
    print(f"install-hooks: already current {dest}")
PY

rm -f "$tmp"
