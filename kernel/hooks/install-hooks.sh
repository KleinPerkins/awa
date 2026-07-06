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
#   afterFileEdit        -> unset  (observation-only, no permission gate; failClosed is a no-op here)
#   sessionStart         -> false  (fire-and-forget context; never blocks)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"   # kernel/hooks
HOOKS_JSON="${AWA_HOOKS_JSON:-$HOME/.cursor/hooks.json}"
SESSION_HOOK="$SCRIPT_DIR/worktree-session.sh"
GUARD_HOOK="$SCRIPT_DIR/worktree-guard.sh"

MODE="install"
case "${1:-}" in
  --check) MODE="check" ;;
  "") MODE="install" ;;
  *) printf 'usage: %s [--check]\n' "$0" >&2; exit 2 ;;
esac

if [ "$MODE" = "check" ]; then
  # Path-robust: match AWA entries by the hook script BASENAME, not the full path (the deployed
  # command may point at any checkout/install of this repo). Assert failClosed matches intent.
  HOOKS_JSON="$HOOKS_JSON" python3 - <<'PY'
import json, os, sys

path = os.environ["HOOKS_JSON"]
if not os.path.exists(path):
    print(f"install-hooks --check: no {path} (nothing deployed) — OK")
    sys.exit(0)
try:
    data = json.load(open(path))
except Exception as exc:  # noqa: BLE001
    print(f"install-hooks --check: {path} is not valid JSON: {exc}", file=sys.stderr)
    sys.exit(1)

hooks = data.get("hooks", {}) if isinstance(data, dict) else {}

EXPECT = [
    ("beforeShellExecution", "worktree-guard.sh", False),
    ("afterFileEdit", "worktree-guard.sh", None),
    ("sessionStart", "worktree-session.sh", False),
]

def basename(cmd):
    for tok in str(cmd).split():
        if tok.endswith(".sh"):
            return os.path.basename(tok)
    return os.path.basename(str(cmd).split()[0]) if str(cmd).split() else ""

fail = 0
checked = 0
for event, want_base, want_fc in EXPECT:
    for entry in hooks.get(event, []) or []:
        if not isinstance(entry, dict):
            continue
        if basename(entry.get("command", "")) != want_base:
            continue
        checked += 1
        have_fc = entry.get("failClosed", "<unset>")
        if want_fc is None:
            if "failClosed" in entry and entry["failClosed"] is not False:
                print(f"  FAIL  {event}: {want_base} failClosed={have_fc!r} (expected unset/false — no-op gate, X2)", file=sys.stderr)
                fail = 1
            else:
                print(f"  OK    {event}: {want_base} failClosed={have_fc!r} (observation-only)")
        else:
            if have_fc == want_fc:
                print(f"  OK    {event}: {want_base} failClosed={have_fc!r}")
            else:
                print(f"  FAIL  {event}: {want_base} failClosed={have_fc!r} (expected {want_fc!r}) — deployment drift", file=sys.stderr)
                fail = 1

if checked == 0:
    print("install-hooks --check: no AWA hook entries deployed — OK (run the installer to deploy)")
sys.exit(fail)
PY
  exit $?
fi

mkdir -p "$(dirname "$HOOKS_JSON")"
chmod +x "$SESSION_HOOK" "$GUARD_HOOK"

tmp="$(mktemp)"
if [ -f "$HOOKS_JSON" ]; then
  cp "$HOOKS_JSON" "$tmp"
else
  printf '{"version":1,"hooks":{}}\n' > "$tmp"
fi

python3 - "$tmp" "$HOOKS_JSON" "$SESSION_HOOK" "$GUARD_HOOK" <<'PY'
import json, pathlib, shutil, sys, time
src, dest, session_hook, guard_hook = map(pathlib.Path, sys.argv[1:5])
try:
    data = json.loads(src.read_text())
except Exception:
    data = {"version": 1, "hooks": {}}
data.setdefault("version", 1)
hooks = data.setdefault("hooks", {})

def ensure(event, entry, drop_keys=()):
    arr = hooks.setdefault(event, [])
    cmd = entry["command"]
    for existing in arr:
        if existing.get("command") == cmd:
            existing.update(entry)
            for k in drop_keys:
                existing.pop(k, None)
            return False
    arr.append(entry)
    return True

changed = False
changed |= ensure("sessionStart", {
    "command": str(session_hook),
    "timeout": 5,
    "failClosed": False,
})
# beforeShellExecution is the soft worktree backstop -> fail OPEN on hook failure (incident
# 2026-07-05: failClosed:true on a global gate bricked every workspace under load/timeout).
changed |= ensure("beforeShellExecution", {
    "command": str(guard_hook),
    "timeout": 20,
    "failClosed": False,
})
# afterFileEdit is observation-only (Cursor ignores any returned permission). failClosed is a
# no-op here, so we do NOT set it (X2); drop it if a prior install wrote it.
changed |= ensure("afterFileEdit", {
    "command": str(guard_hook),
    "timeout": 20,
}, drop_keys=("failClosed",))

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
