#!/usr/bin/env bash
# verify-live-verify.sh — static check that live-verify harness files exist and bootstrap is sane.
set -euo pipefail
SELF="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
fail=0
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
if [ -x "$SELF/../hook-probe/redrive-capture.sh" ]; then
  echo "  PASS  ../hook-probe/redrive-capture.sh executable"
else
  echo "  FAIL  ../hook-probe/redrive-capture.sh not executable"; fail=1
fi
if [ -x "$SELF/bootstrap-hook-probe-uat.sh" ]; then
  echo "  PASS  bootstrap-hook-probe-uat.sh executable"
else
  echo "  FAIL  bootstrap-hook-probe-uat.sh not executable"; fail=1
fi
if [ -x "$SELF/bootstrap-eligible-uat.sh" ]; then
  echo "  PASS  bootstrap-eligible-uat.sh executable"
else
  echo "  FAIL  bootstrap-eligible-uat.sh not executable"; fail=1
fi
if [ "$fail" -eq 0 ]; then echo "verify-live-verify: OK"; else echo "verify-live-verify: FAILED"; exit 1; fi
