#!/usr/bin/env bash
# Desktop-only ADR 0025 Body C UAT. --check is read-only; --run requires R1 GO.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd -P)"
MODE="${1:---check}"

case "$MODE" in
  --check)
    test -f "$ROOT/contracts/awa-hook-owner.v4.json"
    test -x "$ROOT/kernel/hooks/awa-registration-admission.sh"
    test -x "$ROOT/kernel/hooks/awa-registration-startup.sh"
    test -x "$ROOT/kernel/bin/awa-registration-tick.sh"
    printf '%s\n' \
      "Body C Desktop UAT harness: packaged, not executed" \
      "Required catch-all ingress: preToolUse" \
      "Required launch ingress: subagentStart (Task)" \
      "Required discriminator probes: ordinary, MCP, renamed, unknown, Task" \
      "R1 canary GO required before --run" \
      "R2 remains unauthorized"
    ;;
  --run)
    receipt="${AWA_R1_CANARY_GO_RECEIPT:-}"
    if [ -z "$receipt" ] || [ ! -f "$receipt" ]; then
      printf '%s\n' "desktop UAT refused: exact R1 canary GO receipt required" >&2
      exit 2
    fi
    python3 - "$receipt" <<'PY'
import json
import os
import stat
import sys
from pathlib import Path

path = Path(sys.argv[1])
metadata = path.lstat()
if (
    stat.S_ISLNK(metadata.st_mode)
    or not stat.S_ISREG(metadata.st_mode)
    or metadata.st_uid != os.geteuid()
    or stat.S_IMODE(metadata.st_mode) != 0o600
):
    raise SystemExit(2)
value = json.loads(path.read_text(encoding="utf-8"))
if (
    not isinstance(value, dict)
    or value.get("schema") != "awa-registration-owner-gate/v1"
    or value.get("rollout_stage") != "R1"
    or value.get("authorized") is not True
    or not isinstance(value.get("candidate_digest"), str)
    or len(value["candidate_digest"]) != 64
):
    raise SystemExit(2)
PY
    cat <<'EOF'
Desktop UAT is authorization-gated and intentionally operator-driven.
1. Confirm the installed hook projection and DIRECT R1 receipt exact hashes.
2. Trigger one ordinary Shell, Read, Write, Grep, and Delete invocation.
3. Trigger one MCP invocation and record its MCP:<tool_name> discriminator.
4. Trigger one deliberately unknown/renamed test tool and confirm deny.
5. Trigger one Task/subagent launch and confirm TASK_SUBAGENT_DENIED.
6. Kill/timeout the receiver and confirm that invocation fails open without a denial claim.
7. Restore the receiver; confirm only the named canary root/member can reach READY.
Capture outputs externally; this script writes no acceptance or rollout state.
EOF
    ;;
  *)
    printf 'usage: %s [--check|--run]\n' "$0" >&2
    exit 2
    ;;
esac
