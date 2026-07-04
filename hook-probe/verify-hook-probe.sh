#!/usr/bin/env bash
# Static self-check for the AWA hook-probe harness. Read-only: it validates the
# harness FILES are well-formed. It does NOT run the probe, touch live machine
# state, create temp repos, or run git. Exits 0 on success, 1 on any failure.
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
HOOKS_JSON="$DIR/hooks.json"
PROBE="$DIR/probe-hook.sh"
ANALYZE="$DIR/analyze.py"

fail=0
pass() { printf 'PASS: %s\n' "$1"; }
bad()  { printf 'FAIL: %s\n' "$1"; fail=1; }

# Every event a project hook can receive that this harness must wire up.
EXPECTED_EVENTS="sessionStart beforeSubmitPrompt beforeShellExecution beforeReadFile beforeMCPExecution afterFileEdit stop sessionEnd workspaceOpen"

# --- hooks.json: exists, valid JSON, wires probe command to expected events ---
if [ ! -f "$HOOKS_JSON" ]; then
  bad "hooks.json missing at $HOOKS_JSON"
elif ! python3 -m json.tool "$HOOKS_JSON" >/dev/null 2>&1; then
  bad "hooks.json is not valid JSON"
else
  pass "hooks.json is valid JSON"
  if HP_JSON="$HOOKS_JSON" HP_EVENTS="$EXPECTED_EVENTS" python3 - <<'PY'
import json, os, sys
data = json.load(open(os.environ["HP_JSON"]))
hooks = data.get("hooks", {})
missing = []
for ev in os.environ["HP_EVENTS"].split():
    entries = hooks.get(ev)
    if not entries or not any("probe-hook.sh" in (e.get("command") or "") for e in entries):
        missing.append(ev)
if missing:
    sys.stderr.write("missing/unwired events: " + ", ".join(missing) + "\n")
    sys.exit(1)
sys.exit(0)
PY
  then
    pass "hooks.json wires probe-hook.sh to all expected events"
  else
    bad "hooks.json does not wire probe-hook.sh to all expected events"
  fi
fi

# --- probe-hook.sh: exists, has a shebang, references the events.jsonl path ---
if [ ! -f "$PROBE" ]; then
  bad "probe-hook.sh missing at $PROBE"
else
  if head -n 1 "$PROBE" | grep -q '^#!'; then
    pass "probe-hook.sh has a shebang"
  else
    bad "probe-hook.sh is missing a shebang"
  fi
  if grep -q 'events.jsonl' "$PROBE"; then
    pass "probe-hook.sh references the events.jsonl log path"
  else
    bad "probe-hook.sh does not reference events.jsonl"
  fi
fi

# --- analyze.py: exists and compiles cleanly ---
if [ ! -f "$ANALYZE" ]; then
  bad "analyze.py missing at $ANALYZE"
elif python3 -c "compile(open('$ANALYZE').read(), 'analyze.py', 'exec')" 2>/dev/null; then
  pass "analyze.py compiles"
else
  bad "analyze.py does not compile"
fi

if [ "$fail" -eq 0 ]; then
  printf 'ALL CHECKS PASSED\n'
  exit 0
fi
printf 'ONE OR MORE CHECKS FAILED\n'
exit 1
