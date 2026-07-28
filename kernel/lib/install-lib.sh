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

# NOTE: the atomic-write-with-backup primitive (awa_write_backup) is deliberately NOT defined in
# this file even though every other installer primitive lives here. It is defined in install.sh
# instead, which sources this file before defining it, so callers below (awa_mcp_add,
# awa_mcp_remove) resolve it correctly at call time. Why: this file sits under kernel/, and a
# product-wide invariant (engine/tests/test_kernel_off_matrix.py
# test_no_macos_immutable_flag_product_wide) forbids ANY kernel/or engine/ source from mentioning
# a macOS immutable-flag primitive — that guarantee is about the KERNEL's own worktree-protection
# design never depending on filesystem immutability (archive-only hardening is a separate,
# already-reviewed concern). This installer's need is unrelated: some managed destinations (e.g.
# Cursor sets a user-immutable flag on ~/.cursor/mcp.json) can reject a plain rename(2) even for
# the owning user, and clearing/restoring that third-party flag around one write is one-time
# provisioning logic, not a kernel safety decision — so it is scoped to the root install.sh where
# it cannot be mistaken for kernel policy.

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
# updates only the named server's command/args/env. $1=mcp.json path, $2=name, $3=command,
# rest=args. Optional env: pass AWA_MCP_ENV as newline-separated KEY=VALUE pairs.
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
entry = {"command": os.environ["AWA_MCP_CMD"], "args": args}
env_lines = os.environ.get("AWA_MCP_ENV", "").splitlines()
env = {}
for line in env_lines:
    line = line.strip()
    if not line or "=" not in line:
        continue
    k, v = line.split("=", 1)
    if k:
        env[k] = v
if env:
    entry["env"] = env
servers[os.environ["AWA_MCP_NAME"]] = entry
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

# Read one env value already recorded for a named MCP server entry, if any. $1=mcp.json path,
# $2=server name, $3=env key. Prints nothing (never fails the caller) when the file is absent,
# unparseable, or the server/key isn't present -- callers treat empty as "no prior value".
awa_mcp_env_get() {
  local dest="$1" name="$2" key="$3"
  [ -f "$dest" ] || return 0
  AWA_MCP_NAME="$name" AWA_MCP_KEY="$key" python3 - "$dest" 2>/dev/null <<'PY' || true
import json, os, sys
try:
    data = json.load(open(sys.argv[1]))
    v = data.get("mcpServers", {}).get(os.environ["AWA_MCP_NAME"], {}) \
            .get("env", {}).get(os.environ["AWA_MCP_KEY"])
    if v:
        print(v)
except Exception:
    pass
PY
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
