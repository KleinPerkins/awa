#!/usr/bin/env bash
# bootstrap-eligible-uat.sh — create a disposable eligible repo under ~/dev/personal for AWA UAT.
#
# The repo is classified include/on (has origin, under governed root, not excluded).
# Use for mode, guard, ensure, and apply-back live verification. NEVER copy into a governed repo.
#
# Usage:
#   bootstrap-eligible-uat.sh [TARGET_DIR]
# Default: ~/dev/personal/awa-uat-<timestamp>
set -euo pipefail

TARGET="${1:-$HOME/dev/personal/awa-uat-$(date +%Y%m%dT%H%M%S)}"
TS="$(basename "$TARGET" | sed 's/awa-uat-//')"

if [ -e "$TARGET" ]; then
  echo "bootstrap-eligible-uat: target already exists: $TARGET" >&2
  exit 1
fi

mkdir -p "$(dirname "$TARGET")"
mkdir -p "$TARGET" && cd "$TARGET"
git init -q
git config user.name "${GIT_USER_NAME:-KleinPerkins}"
git config user.email "${GIT_USER_EMAIL:-49759187+KleinPerkins@users.noreply.github.com}"
echo "# AWA UAT eligible fixture ($TS)" > README.md
git add . && git commit -q -m "init: AWA UAT eligible fixture"
git branch -M main
git remote add origin "git@github.com:KleinPerkins/awa-uat-eligible-${TS}.git"

REL="personal/$(basename "$TARGET")"
echo "bootstrap-eligible-uat: OK"
echo "  repo:       $TARGET"
echo "  rel:        $REL (under AWA_GOVERNED_ROOT=~/dev)"
echo "  remote:     origin -> KleinPerkins/awa-uat-eligible-${TS} (create with gh before push)"
echo ""
echo "Next:"
echo "  gh repo create KleinPerkins/awa-uat-eligible-${TS} --private --source=\"$TARGET\" --push"
echo "  ~/dev/_ops/bin/dev-worktree.sh status   # expect classification include (host default_mode on)"
echo "  See live-verify/OPERATOR-UAT-SESSION.md"
