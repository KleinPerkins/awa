#!/usr/bin/env bash
# install-lib.sh — shared helpers for the AWA standalone installer (SSP). Sourced by
# install.sh. Pure bash + python3 (stdlib). ZERO org/host literals; every path is XDG-derived
# and HOME-relative, so an install honors a HOME override (CI runs into a throwaway HOME).
#
# This library is the reusable Standalone-System-Package (SSP) install primitive set:
# idempotent, backup-before-write, add-only JSON merges, mirror-copy of the runtime tree.

awa_data_home()   { printf '%s' "${XDG_DATA_HOME:-$HOME/.local/share}"; }
awa_config_home() { printf '%s' "${XDG_CONFIG_HOME:-$HOME/.config}"; }
awa_state_home()  { printf '%s' "${XDG_STATE_HOME:-$HOME/.local/state}"; }

awa_log()  { printf 'awa-install: %s\n' "$*"; }
awa_warn() { printf 'awa-install: %s\n' "$*" >&2; }
awa_die()  { printf 'awa-install: %s\n' "$*" >&2; exit 1; }

# Write stdin to $1, backing up a differing prior copy first (idempotent: no-op if identical).
awa_write_backup() {
  local dest="$1" tmp
  tmp="$(mktemp)"
  cat > "$tmp"
  mkdir -p "$(dirname "$dest")"
  if [ -f "$dest" ] && cmp -s "$tmp" "$dest"; then
    rm -f "$tmp"; return 0
  fi
  if [ -f "$dest" ]; then
    cp -p "$dest" "$dest.bak-$(date -u +%Y%m%d%H%M%S)" 2>/dev/null || true
  fi
  mv "$tmp" "$dest"
}

# Mirror a source dir into a runtime dir (removes stale files). $1=src $2=dest.
awa_sync_tree() {
  local src="$1" dest="$2"
  [ -d "$src" ] || awa_die "missing source tree: $src"
  mkdir -p "$dest"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete --exclude '__pycache__' --exclude '*.pyc' --exclude '.pytest_cache' "$src/" "$dest/"
  else
    rm -rf "$dest"; mkdir -p "$dest"
    ( cd "$src" && tar cf - --exclude='__pycache__' --exclude='*.pyc' --exclude='.pytest_cache' . ) | ( cd "$dest" && tar xf - )
  fi
}

# Add-only merge of an MCP server entry into ~/.cursor/mcp.json. Never clobbers other servers;
# updates only the named server's command/args. $1=mcp.json path, $2=name, $3=command, rest=args.
awa_mcp_add() {
  local dest="$1" name="$2" command="$3"; shift 3
  local tmp; tmp="$(mktemp)"
  if [ -f "$dest" ]; then cp "$dest" "$tmp"; else printf '{}\n' > "$tmp"; fi
  AWA_MCP_NAME="$name" AWA_MCP_CMD="$command" AWA_MCP_ARGS="$*" python3 - "$tmp" <<'PY'
import json, os, sys
path = sys.argv[1]
try:
    data = json.load(open(path))
    if not isinstance(data, dict):
        data = {}
except Exception:
    data = {}
servers = data.setdefault("mcpServers", {}) if isinstance(data.get("mcpServers", {}), dict) else data.setdefault("mcpServers", {})
args = [a for a in os.environ.get("AWA_MCP_ARGS", "").split() if a]
servers[os.environ["AWA_MCP_NAME"]] = {"command": os.environ["AWA_MCP_CMD"], "args": args}
open(path, "w").write(json.dumps(data, indent=2) + "\n")
PY
  awa_write_backup "$dest" < "$tmp"
  rm -f "$tmp"
}

# Remove the named MCP server entry (add-only inverse). $1=mcp.json path, $2=name.
awa_mcp_remove() {
  local dest="$1" name="$2"
  [ -f "$dest" ] || return 0
  local tmp; tmp="$(mktemp)"
  AWA_MCP_NAME="$name" python3 - "$dest" > "$tmp" <<'PY'
import json, os, sys
try:
    data = json.load(open(sys.argv[1]))
except Exception:
    data = {}
if isinstance(data, dict) and isinstance(data.get("mcpServers"), dict):
    data["mcpServers"].pop(os.environ["AWA_MCP_NAME"], None)
print(json.dumps(data, indent=2))
PY
  awa_write_backup "$dest" < "$tmp"
  rm -f "$tmp"
}

# Resolve the engine version (canonical: engine.__version__), falling back to pyproject.
awa_engine_version() {
  local root="$1" v
  v="$(PYTHONPATH="$root" python3 -c 'import engine; print(engine.__version__)' 2>/dev/null || true)"
  if [ -z "$v" ] && [ -f "$root/pyproject.toml" ]; then
    v="$(awk -F'"' '/^version *=/{print $2; exit}' "$root/pyproject.toml" 2>/dev/null || true)"
  fi
  printf '%s' "${v:-unknown}"
}
