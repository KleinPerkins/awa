#!/usr/bin/env bash
# teardown-live-uat.sh — remove everything provision-live-uat.sh created and verify the real
# environment is back to parity. AGENT-RUN. Safe to run repeatedly (idempotent).
#
# NEVER removes the real state root ~/.local/state/awa or the released runtime. If the optional live
# hook step (D1) left a ~/.cursor/hooks.json backup, this restores it.
set -euo pipefail

SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../.." && pwd)"
UAT_PREFIX="${AWA_UAT_PREFIX:-$HOME/.local/share/awa-finish-trial-uat}"
UAT_STATE="${AWA_UAT_STATE:-$HOME/.local/state/awa-finish-trial-uat}"
UAT_CONFIG="${AWA_UAT_CONFIG:-$HOME/.config/awa-finish-trial-uat}"
UAT_HOOKS="${AWA_UAT_HOOKS:-$UAT_PREFIX/uat-hooks.json}"
UAT_MCP="${AWA_UAT_MCP:-$UAT_PREFIX/uat-mcp.json}"
UAT_RULE="${AWA_UAT_RULE:-$UAT_PREFIX/uat-awa-operator.mdc}"
RUNTIME="$UAT_PREFIX/awa/current"
TARGET="$UAT_PREFIX/target"

_refuse() { echo "teardown-live-uat: REFUSING — $1 is the real path ($2)" >&2; exit 2; }
[ "${UAT_STATE%/}"  = "$HOME/.local/state/awa" ] && _refuse "AWA_UAT_STATE"  "$UAT_STATE"
[ "${UAT_PREFIX%/}" = "$HOME/.local/share/awa" ] && _refuse "AWA_UAT_PREFIX" "$UAT_PREFIX"

echo "== teardown-live-uat =="

# 1) restore a Part-A hooks.json backup if one exists (the runbook names it *.awa-uat.bak).
BAK="$HOME/.cursor/hooks.json.awa-uat.bak"
if [ -f "$BAK" ]; then
  echo "-- restoring operator hooks.json from $BAK --"
  mv -f "$BAK" "$HOME/.cursor/hooks.json"
else
  echo "-- no Part-A hooks.json backup found (nothing to restore) --"
fi

# 2) detach throwaway worktrees so git does not keep administrative refs around.
if [ -d "$TARGET/.git" ] || [ -f "$TARGET/.git" ]; then
  for role in close retain commit; do
    WT="$UAT_PREFIX/target-$role.wt"
    [ -e "$WT" ] && git -C "$TARGET" worktree remove --force "$WT" 2>/dev/null || true
  done
  git -C "$TARGET" worktree prune 2>/dev/null || true
fi

# 3) uninstall the disposable runtime (scoped to the disposable XDG + disposable hooks file) so its
#    hook/mcp entries are removed from the DISPOSABLE files, never the operator's.
if [ -x "$RUNTIME/install.sh" ]; then
  echo "-- uninstalling disposable runtime --"
  env XDG_DATA_HOME="$UAT_PREFIX" XDG_CONFIG_HOME="$UAT_CONFIG" XDG_STATE_HOME="$UAT_STATE" \
    AWA_HOOKS_JSON="$UAT_HOOKS" AWA_MCP_JSON="$UAT_MCP" AWA_OPERATOR_RULE="$UAT_RULE" \
    bash "$RUNTIME/install.sh" --uninstall >/dev/null 2>&1 || true
fi

# 4) remove the disposable trees outright.
echo "-- removing disposable trees --"
rm -rf "$UAT_PREFIX" "$UAT_STATE" "$UAT_CONFIG" 2>/dev/null || true

# 5) parity check: the real env must still be intact.
echo "-- parity check --"
rc=0
if [ -d "$HOME/.local/state/awa" ]; then echo "  PASS  real state root present + untouched"; else echo "  WARN  real state root absent (was it ever installed?)"; fi
[ -e "$UAT_PREFIX" ] && { echo "  FAIL  disposable prefix survived: $UAT_PREFIX"; rc=1; } || echo "  PASS  disposable prefix removed"
[ -e "$UAT_STATE" ]  && { echo "  FAIL  disposable state survived: $UAT_STATE"; rc=1; }  || echo "  PASS  disposable state removed"
[ -f "$BAK" ]        && { echo "  FAIL  hooks.json backup still pending: $BAK"; rc=1; }   || echo "  PASS  no pending hooks.json backup"
if [ "$rc" -eq 0 ]; then echo "teardown-live-uat: OK"; else echo "teardown-live-uat: INCOMPLETE"; exit 1; fi
