#!/usr/bin/env bash
# AWA hook-probe logging hook (read-only observer).
#
# Registered against every project-level Cursor hook event (see hooks.json).
# For each invocation it appends one JSONL record capturing the raw stdin
# payload + hook-related env, then emits a deliberately chosen `permission`
# response for the gating events so we can OBSERVE whether Cursor honors it.
#
# It NEVER blocks real work except the intentional afterFileEdit probe-deny
# (which the AWA ledger claims Cursor ignores — this harness exists to prove
# that empirically). The only side effect is appending to its own log file.
#
# No `set -e`: a hook that errors out must still fail open, not abort actions.
set -uo pipefail

LOG_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/awa/hook-probe"
LOG_FILE="$LOG_DIR/events.jsonl"

mkdir -p "$LOG_DIR" 2>/dev/null || true

# Read the raw stdin payload verbatim (may be empty for some events).
input="$(cat 2>/dev/null || true)"

# Event name hint from an argument, if the operator wires one.
arg_event="${1:-}"

# Log the event and emit the appropriate response. All JSON handling is done in
# python3 so the raw payload and env are encoded safely and never corrupted.
HOOK_INPUT="$input" HOOK_ARG_EVENT="$arg_event" HOOK_LOG_FILE="$LOG_FILE" \
python3 - <<'PY' || true
import datetime
import json
import os
import sys

raw = os.environ.get("HOOK_INPUT", "")
arg_event = os.environ.get("HOOK_ARG_EVENT", "")
log_file = os.environ.get("HOOK_LOG_FILE", "")

# Parse the payload if we can; keep the verbatim string regardless.
try:
    payload = json.loads(raw) if raw.strip() else None
    payload_ok = True
except Exception:
    payload = None
    payload_ok = False

# Derive the event name: env var wins, then the payload, then a CLI arg.
event = os.environ.get("CURSOR_HOOK_EVENT") or os.environ.get("HOOK_EVENT_NAME")
if not event and isinstance(payload, dict):
    for key in ("hook_event_name", "hookEventName", "event", "eventName", "hook_event"):
        val = payload.get(key)
        if isinstance(val, str) and val:
            event = val
            break
if not event and arg_event:
    event = arg_event
if not event:
    event = "unknown"

# Collect hook-related env vars (CURSOR* / HOOK*), excluding our own plumbing.
skip = {"HOOK_INPUT", "HOOK_ARG_EVENT", "HOOK_LOG_FILE"}
hook_env = {
    k: v
    for k, v in os.environ.items()
    if (k.startswith("CURSOR") or k.startswith("HOOK")) and k not in skip
}

# Observed top-level field names in the payload (for shape analysis).
if isinstance(payload, dict):
    payload_keys = sorted(payload.keys())
else:
    payload_keys = []

record = {
    "ts": datetime.datetime.now(datetime.timezone.utc)
    .isoformat()
    .replace("+00:00", "Z"),
    "event": event,
    "payload_ok": payload_ok,
    "payload_keys": payload_keys,
    "raw_stdin": raw,
    "hook_env": hook_env,
}

if log_file:
    try:
        with open(log_file, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass

# Emit the response for gating events. The whole point of the afterFileEdit
# case is to return a deny and observe that Cursor ignores it (post-action).
response = None
if event == "afterFileEdit":
    response = {
        "permission": "deny",
        "user_message": "probe: does afterFileEdit deny actually block?",
    }
elif event in ("beforeShellExecution", "beforeReadFile", "beforeMCPExecution"):
    # Never block real work — always allow these pre-action gating events.
    response = {"permission": "allow"}

if response is not None:
    sys.stdout.write(json.dumps(response))
PY
