#!/usr/bin/env bash
# provision-live-uat.sh — provision a fully DISPOSABLE AWA runtime + throwaway finish targets for the
# Layer-B live operator UAT (see LIVE-OPERATOR-RUNBOOK.md). AGENT-RUN: the operator runs nothing here.
#
# Creates ONLY disposable paths. It NEVER touches:
#   - the real state root      ~/.local/state/awa
#   - the released runtime     ~/.local/share/awa/current
#   - the operator's hooks     ~/.cursor/hooks.json         (it writes a SEPARATE disposable hooks file)
#   - the operator's mcp/rule   ~/.cursor/mcp.json, ~/.cursor/rules/awa-operator.mdc
#
# The optional live-hook step (D1) that DOES temporarily swap ~/.cursor/hooks.json is performed by the
# runbook (backup + swap + restore), never by this provisioner.
#
# Usage:
#   bash live-verify/trial-runner/provision-live-uat.sh [--dry-run]
# Env overrides (all default to disposable locations):
#   AWA_UAT_PREFIX  data home        (default ~/.local/share/awa-finish-trial-uat  -> runtime .../awa/current)
#   AWA_UAT_STATE   state home       (default ~/.local/state/awa-finish-trial-uat  -> finish state .../awa)
#   AWA_UAT_CONFIG  config home      (default ~/.config/awa-finish-trial-uat)
#   AWA_UAT_HOOKS   disposable hooks (default $AWA_UAT_PREFIX/uat-hooks.json)
set -euo pipefail

DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
run() { if [ "$DRY" = 1 ]; then echo "  + $*"; else eval "$*"; fi; }

TS="$(date +%Y%m%dT%H%M%S)"
SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../.." && pwd)"   # the awa source worktree

UAT_PREFIX="${AWA_UAT_PREFIX:-$HOME/.local/share/awa-finish-trial-uat}"
UAT_STATE="${AWA_UAT_STATE:-$HOME/.local/state/awa-finish-trial-uat}"
UAT_CONFIG="${AWA_UAT_CONFIG:-$HOME/.config/awa-finish-trial-uat}"
UAT_HOOKS="${AWA_UAT_HOOKS:-$UAT_PREFIX/uat-hooks.json}"
UAT_MCP="${AWA_UAT_MCP:-$UAT_PREFIX/uat-mcp.json}"
UAT_RULE="${AWA_UAT_RULE:-$UAT_PREFIX/uat-awa-operator.mdc}"
RUNTIME="$UAT_PREFIX/awa/current"

# --- defensive: never let a disposable path resolve onto a REAL one --------------------------------
_refuse() { echo "provision-live-uat: REFUSING — $1 resolves to the real path ($2)" >&2; exit 2; }
[ "${UAT_STATE%/}"  = "$HOME/.local/state/awa" ]     && _refuse "AWA_UAT_STATE"  "$UAT_STATE"
[ "${UAT_PREFIX%/}" = "$HOME/.local/share/awa" ]     && _refuse "AWA_UAT_PREFIX" "$UAT_PREFIX"
[ "${UAT_CONFIG%/}" = "$HOME/.config/awa" ]          && _refuse "AWA_UAT_CONFIG" "$UAT_CONFIG"
[ "${UAT_HOOKS%/}"  = "$HOME/.cursor/hooks.json" ]   && _refuse "AWA_UAT_HOOKS"  "$UAT_HOOKS"
[ "${UAT_MCP%/}"    = "$HOME/.cursor/mcp.json" ]     && _refuse "AWA_UAT_MCP"    "$UAT_MCP"

if [ -e "$UAT_PREFIX" ] && [ "$DRY" = 0 ]; then
  echo "provision-live-uat: $UAT_PREFIX already exists — run teardown-live-uat.sh first (or set AWA_UAT_PREFIX)." >&2
  exit 1
fi

echo "== provision-live-uat ($TS) =="
echo "  source (just-released v1.1.0): $SRC_ROOT"
echo "  disposable runtime:            $RUNTIME"
echo "  disposable state root:         $UAT_STATE/awa   (real ~/.local/state/awa untouched)"
echo "  disposable hooks file:         $UAT_HOOKS       (real ~/.cursor/hooks.json untouched)"
echo ""

# --- 1) install the disposable runtime from THIS worktree's source ---------------------------------
echo "-- installing disposable runtime --"
run "env XDG_DATA_HOME='$UAT_PREFIX' XDG_CONFIG_HOME='$UAT_CONFIG' XDG_STATE_HOME='$UAT_STATE' \
  AWA_HOOKS_JSON='$UAT_HOOKS' AWA_MCP_JSON='$UAT_MCP' AWA_OPERATOR_RULE='$UAT_RULE' \
  bash '$SRC_ROOT/install.sh' >/dev/null"

# --- 2) throwaway repo (bare origin stand-in + working repo on default branch 'main') --------------
ORIGIN="$UAT_PREFIX/target-origin.git"
TARGET="$UAT_PREFIX/target"
echo "-- building throwaway repo + linked worktrees --"
run "git init --bare -q '$ORIGIN'"
run "git init -q '$TARGET'"
run "git -C '$TARGET' config user.name  'AWA UAT'"
run "git -C '$TARGET' config user.email 'awa-uat@example.invalid'"
run "printf '# AWA finish live-UAT throwaway target (%s)\n' '$TS' > '$TARGET/README.md'"
run "git -C '$TARGET' add -A"
run "git -C '$TARGET' commit -q -m 'init: throwaway finish target'"
run "git -C '$TARGET' branch -M main"
run "git -C '$TARGET' remote add origin '$ORIGIN'"
run "git -C '$TARGET' push -q -u origin main"

# One linked worktree per destructive path so no live step clobbers another. Branch names mirror the
# 'cursor/worktree/*' ephemeral convention so branch disposition classifies them as delete-eligible.
for role in close retain commit; do
  WT="$UAT_PREFIX/target-$role.wt"
  BR="cursor/worktree/uat-$role-$TS"
  run "git -C '$TARGET' worktree add -q -b '$BR' '$WT'"
  echo "  worktree: $WT   (branch $BR)"
done

# --- 3) hand the operator the exact next step ------------------------------------------------------
cat <<EOF

== provisioned. NEXT (the AGENT runs these; the operator only submits chat prompts) ==

Disposable env the agent exports in the live session:
    export AWA_HOME="$RUNTIME"
    export XDG_STATE_HOME="$UAT_STATE"
    FINISH="$RUNTIME/consumer/finish_current.py"

FIRST OPERATOR STEP:
    Open a NEW Cursor Desktop window on the throwaway worktree:
        $UAT_PREFIX/target-close.wt
    then follow live-verify/trial-runner/LIVE-OPERATOR-RUNBOOK.md from step L1.

Throwaway finish targets (each removable without risking any real repo):
    L1/L2/L6 (preview / Close-variant / real Close):  $UAT_PREFIX/target-close.wt
    L3       (Retain artifact + restore):              $UAT_PREFIX/target-retain.wt
    L4/L5    (Mixed / Commit delivery):                $UAT_PREFIX/target-commit.wt

Tear everything down afterwards with:
    bash live-verify/trial-runner/teardown-live-uat.sh
EOF
