#!/usr/bin/env bash
# bootstrap.sh — one-command "clone + install" for AWA.
#
# Run from a checkout (it just installs), or standalone (it clones KleinPerkins/awa to a durable
# location first, then installs). Idempotent: an existing clone is fast-forwarded, not re-cloned.
#
# Both paths below hand off to install.sh through Bash, so the clone+install flow carries through its
# modes-file ensure step (schema awa-modes/v1 + default_mode from the host policy's modes_file
# pointer) with NO duplicated logic here.
#
#   bash bootstrap.sh [install-args...]     # e.g. bash bootstrap.sh --repair
set -euo pipefail

REPO="${AWA_REPO_URL:-git@github.com:KleinPerkins/awa.git}"
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

product_script_ready() {
  python3 - "$1" <<'PY'
import os
import stat
import sys

try:
    mode = os.stat(sys.argv[1]).st_mode
except OSError:
    raise SystemExit(1)
raise SystemExit(
    0
    if stat.S_ISREG(mode) and mode & 0o111 and os.access(sys.argv[1], os.R_OK)
    else 1
)
PY
}

# Running from a checkout — install in place.
if [ -f "$SELF_DIR/install.sh" ] && [ -d "$SELF_DIR/kernel" ]; then
  product_script_ready "$SELF_DIR/install.sh" || {
    echo "bootstrap: install.sh is not a readable regular executable-mode file" >&2
    exit 126
  }
  exec bash "$SELF_DIR/install.sh" "$@"
fi

CLONE_DIR="${AWA_CLONE_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/awa/checkout}"
if [ -d "$CLONE_DIR/.git" ]; then
  echo "bootstrap: updating existing clone at $CLONE_DIR"
  git -C "$CLONE_DIR" fetch --quiet origin || true
  git -C "$CLONE_DIR" pull --ff-only --quiet || echo "bootstrap: could not fast-forward; installing current checkout"
else
  echo "bootstrap: cloning $REPO -> $CLONE_DIR"
  mkdir -p "$(dirname "$CLONE_DIR")"
  git clone --quiet "$REPO" "$CLONE_DIR"
fi

product_script_ready "$CLONE_DIR/install.sh" || {
  echo "bootstrap: cloned install.sh is not a readable regular executable-mode file" >&2
  exit 126
}
exec bash "$CLONE_DIR/install.sh" "$@"
