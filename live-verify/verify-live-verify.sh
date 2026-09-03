#!/usr/bin/env bash
# verify-live-verify.sh — static check that live-verify harness files exist and bootstrap is sane.
set -euo pipefail
SELF="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
fail=0
has_executable_mode() {
  python3 - "$1" <<'PY'
import os
import stat
import sys

try:
    mode = os.lstat(sys.argv[1]).st_mode
except OSError:
    raise SystemExit(1)
raise SystemExit(
    0
    if stat.S_ISREG(mode) and os.access(sys.argv[1], os.R_OK) and mode & 0o111
    else 1
)
PY
}
for f in README.md OPERATOR-CLOSEOUT.md OPERATOR-UAT-SESSION.md bootstrap-hook-probe-uat.sh \
         bootstrap-eligible-uat.sh cloud-hooks-runbook.md awa-mcp-runbook.md mode-uat-runbook.md \
         apply-back-uat-runbook.md move-agent-to-root-runbook.md desktop-hook-redrive-runbook.md \
         RESULTS-R-A-2026-07-05.md RESULTS-e2e-uat-20260706.md RESULTS-e2e-uat-20260707.md \
         RESULTS-MCP-GUIDANCE-BASELINE-20260709.md; do
  if [ -f "$SELF/$f" ]; then echo "  PASS  $f"; else echo "  FAIL  missing $f"; fail=1; fi
done
if [ -f "$SELF/../hook-probe/RESULTS-MCP-2026-07-05.md" ]; then
  echo "  PASS  ../hook-probe/RESULTS-MCP-2026-07-05.md"
else
  echo "  FAIL  missing ../hook-probe/RESULTS-MCP-2026-07-05.md"; fail=1
fi
if [ -f "$SELF/../hook-probe/RESULTS-REDRIVE-2026-07-05.md" ]; then
  echo "  PASS  ../hook-probe/RESULTS-REDRIVE-2026-07-05.md"
else
  echo "  FAIL  missing ../hook-probe/RESULTS-REDRIVE-2026-07-05.md"; fail=1
fi
if has_executable_mode "$SELF/../hook-probe/redrive-capture.sh"; then
  echo "  PASS  ../hook-probe/redrive-capture.sh executable"
else
  echo "  FAIL  ../hook-probe/redrive-capture.sh not executable"; fail=1
fi
if has_executable_mode "$SELF/bootstrap-hook-probe-uat.sh"; then
  echo "  PASS  bootstrap-hook-probe-uat.sh executable"
else
  echo "  FAIL  bootstrap-hook-probe-uat.sh not executable"; fail=1
fi
if has_executable_mode "$SELF/bootstrap-eligible-uat.sh"; then
  echo "  PASS  bootstrap-eligible-uat.sh executable"
else
  echo "  FAIL  bootstrap-eligible-uat.sh not executable"; fail=1
fi
# Comprehensive finish/retention UAT trial runner (Layer A) + live operator runbook (Layer B).
for f in trial-runner/run_trial.py trial-runner/_trial_lib.py trial-runner/_trial_phase1.py \
         trial-runner/_trial_phase2.py trial-runner/_trial_phase3.py trial-runner/_trial_live.py \
         trial-runner/README.md trial-runner/LIVE-OPERATOR-RUNBOOK.md \
         RESULTS-finish-all-transitions-trial-20260712.md; do
  if [ -f "$SELF/$f" ]; then echo "  PASS  $f"; else echo "  FAIL  missing $f"; fail=1; fi
done
for f in trial-runner/provision-live-uat.sh trial-runner/teardown-live-uat.sh; do
  if has_executable_mode "$SELF/$f"; then echo "  PASS  $f executable"; else echo "  FAIL  $f not executable"; fail=1; fi
done
if python3 - "$SELF/trial-runner/LIVE-OPERATOR-RUNBOOK.md" <<'PY'
import pathlib
import re
import sys

text = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
if re.search(r"--(?:rows|commit-rows|retain-rows)\s+[0-9]", text):
    raise SystemExit("hard-coded finish row number")
required = (
    "live-number-next-to-UAT-RETAIN-SENTINEL.txt",
    "live-comma-separated-Commit-row-numbers",
    "live-comma-separated-Retain-row-numbers",
    "never assume an",
)
if any(value not in text for value in required):
    raise SystemExit("dynamic finish row guidance missing")
PY
then
  echo "  PASS  live finish row selection is display-derived"
else
  echo "  FAIL  live finish row selection must be display-derived"; fail=1
fi
# The trial runner must at least be import/parse clean + discover its transitions (no sandboxes).
if python3 "$SELF/trial-runner/run_trial.py" --list >/dev/null 2>&1; then
  echo "  PASS  trial-runner --list (transitions discoverable)"
else
  echo "  FAIL  trial-runner --list failed"; fail=1
fi
if [ "$fail" -eq 0 ]; then echo "verify-live-verify: OK"; else echo "verify-live-verify: FAILED"; exit 1; fi
