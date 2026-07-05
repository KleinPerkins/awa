#!/usr/bin/env bash
# verify-live-verify.sh — static check that live-verify harness files exist and bootstrap is sane.
set -euo pipefail
SELF="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
fail=0
for f in README.md OPERATOR-CLOSEOUT.md bootstrap-hook-probe-uat.sh cloud-hooks-runbook.md awa-mcp-runbook.md \
         move-agent-to-root-runbook.md desktop-hook-redrive-runbook.md \
         RESULTS-R-A-2026-07-05.md; do
  if [ -f "$SELF/$f" ]; then echo "  PASS  $f"; else echo "  FAIL  missing $f"; fail=1; fi
done
if [ -f "$SELF/../hook-probe/RESULTS-CLOUD-2026-07-05.md" ]; then
  echo "  PASS  ../hook-probe/RESULTS-CLOUD-2026-07-05.md"
else
  echo "  FAIL  missing ../hook-probe/RESULTS-CLOUD-2026-07-05.md"; fail=1
fi
if [ -x "$SELF/bootstrap-hook-probe-uat.sh" ]; then
  echo "  PASS  bootstrap-hook-probe-uat.sh executable"
else
  echo "  FAIL  bootstrap-hook-probe-uat.sh not executable"; fail=1
fi
if [ "$fail" -eq 0 ]; then echo "verify-live-verify: OK"; else echo "verify-live-verify: FAILED"; exit 1; fi
