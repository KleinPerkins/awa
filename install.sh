#!/usr/bin/env bash
# install.sh — AWA Standalone System Package (SSP) installer.
#
# Clone KleinPerkins/awa and run bash ./install.sh: it installs a self-contained AWA (generic kernel +
# engine + dashboard + frozen contract) into your XDG dirs with NO sibling-repo dependency, then
# reconciles the selected Cursor hook owner + an add-only MCP server. Idempotent,
# backup-before-write.
#
#   bash ./install.sh                 install/reconcile (idempotent)
#   bash ./install.sh --repair        force re-copy the runtime + re-wire hooks/mcp
#   bash ./install.sh --doctor        read-only health check of the install
#   bash ./install.sh --check         CI-safe static preflight (no writes to $HOME)
#   bash ./install.sh --uninstall [--keep-state]   remove the install (--keep-state preserves recovery state)
#
# Layout (all HOME/XDG-relative — honors a HOME override):
#   runtime  $XDG_DATA_HOME/awa/current/           kernel + engine + dashboard + contracts + bin
#   config   $XDG_CONFIG_HOME/awa/env              AWA_HOME, AWA_POLICY, (AWA_GOVERNED_ROOT)
#   owner    $XDG_CONFIG_HOME/awa/hook-owner.json  direct|external hook-file owner
#   hooks    $HOME/.cursor/hooks.json              merged only in direct mode
#   mcp      $HOME/.cursor/mcp.json                add-only "awa" server
#   state    $XDG_STATE_HOME/awa/                  durable recovery/detection state (local disk)
#   pointer  $XDG_DATA_HOME/awa/release-pointer.json   self-describing release record
set -euo pipefail

SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
# shellcheck source=kernel/lib/install-lib.sh
. "$SRC_ROOT/kernel/lib/install-lib.sh"

# True if $1 currently carries the macOS/BSD user-immutable flag (uchg). Always false on a
# platform without `chflags` (e.g. Linux) or when the target does not exist yet. Lives here
# (not kernel/lib/install-lib.sh) — see the NOTE beside awa_log/awa_warn/awa_die in that file.
_awa_has_uchg() {
  command -v chflags >/dev/null 2>&1 || return 1
  [ -e "$1" ] || return 1
  case "$(stat -f '%Sf' "$1" 2>/dev/null || true)" in
    *uchg*) return 0 ;;
    *) return 1 ;;
  esac
}

# Write stdin to $1, backing up a differing prior copy first (idempotent: no-op if identical).
# Defined here rather than kernel/lib/install-lib.sh purely to keep the macOS immutable-flag
# handling out of kernel/ scope (see the NOTE in that file) — awa_mcp_add/awa_mcp_remove (defined
# there) still call this by name and resolve it here since install.sh sources that file first.
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
  # macOS/BSD user-immutable flag (uchg) blocks rename(2) onto $dest even for the owning user
  # (Cursor sets this on files it manages, e.g. ~/.cursor/mcp.json). Clear it immediately before
  # the atomic rename -- a guarded no-op on Linux (no `chflags`) or when the flag isn't set -- and
  # restore it after a successful write so AWA never permanently weakens a file's existing
  # protection. A REMAINING failure (e.g. the system-immutable `schg`, which a non-root owner
  # cannot clear) must not surface as a raw, unexplained `mv` error under the caller's `set -e`.
  local had_uchg=0
  if _awa_has_uchg "$dest"; then
    had_uchg=1
    chflags nouchg "$dest" 2>/dev/null || true
  fi
  if ! mv "$tmp" "$dest" 2>/dev/null; then
    rm -f "$tmp" 2>/dev/null || true
    if [ "$had_uchg" = "1" ]; then
      chflags uchg "$dest" 2>/dev/null || \
        awa_warn "could not restore the user-immutable (uchg) flag on $dest after a failed write"
    fi
    awa_die "cannot write $dest (rename failed — a system-immutable flag (schg) or permission issue may be blocking it; inspect with: ls -lO \"$dest\")"
  fi
  if [ "$had_uchg" = "1" ]; then
    chflags uchg "$dest" 2>/dev/null || \
      awa_warn "could not restore the user-immutable (uchg) flag on $dest after writing it"
  fi
}

RUNTIME="$(awa_data_home)/awa/current"
CONFIG_DIR="$(awa_config_home)/awa"
ENV_FILE="$CONFIG_DIR/env"
STATE_DIR="$(awa_state_home)/awa"
POINTER="$(awa_data_home)/awa/release-pointer.json"
HOOK_OWNER_FILE="$CONFIG_DIR/hook-owner.json"
HOOKS_JSON="${AWA_HOOKS_JSON:-$HOME/.cursor/hooks.json}"
MCP_JSON="${AWA_MCP_JSON:-$HOME/.cursor/mcp.json}"
OPERATOR_RULE="${AWA_OPERATOR_RULE:-$HOME/.cursor/rules/awa-operator.mdc}"

# Top-level items copied into the runtime (a self-describing, re-runnable install).
COPY_TREES=(kernel engine dashboard contracts bin consumer)
COPY_FILES=(pyproject.toml Makefile install.sh bootstrap.sh ARCHITECTURE.md README.md SECURITY.md LICENSE)

# Ensure the host-configured per-repo modes file exists (schema awa-modes/v1 + a default_mode),
# delegating to engine/modes.py `sync` (idempotent create; preserves an existing valid default_mode
# and entries — never clobbers operator intent). ZERO-LINK: the modes-file PATH and default come
# from the host policy's `modes_file:` pointer (resolved by engine/modes.py), never a literal here.
# A policy WITHOUT a `modes_file` pointer (e.g. the generic product template) opts out -> no-op.
ensure_modes_file() {
  local policy="$1"
  [ -f "$policy" ] || return 0
  local engine_sh="$RUNTIME/bin/awa-engine.sh"
  [ -x "$engine_sh" ] || return 0
  # Read-only probe: does the host policy declare a modes_file pointer? `mode list` resolves the
  # pointer without writing. Distinguish the two non-zero outcomes rather than silently skipping
  # BOTH: exit 2 = "no modes_file pointer configured" (host opted out -> skip); any other non-zero
  # = "engine crashed/misbehaved" (warn, then still attempt sync/repair rather than swallow it).
  local rc=0
  "$engine_sh" mode list --policy "$policy" >/dev/null 2>&1 || rc=$?
  if [ "$rc" -eq 2 ]; then
    return 0  # host declares no modes_file pointer -> nothing to ensure
  elif [ "$rc" -ne 0 ]; then
    awa_warn "modes-file probe failed (engine rc=$rc) — attempting sync/repair"
  fi
  if "$engine_sh" mode sync --policy "$policy" >/dev/null 2>&1; then
    awa_log "ensured host-configured modes file (schema awa-modes/v1) via policy modes_file pointer"
  else
    awa_warn "modes-file sync reported an issue (non-fatal; kernel guarantee holds engine-off)"
  fi
}

configure_dashboard_refresh() {
  local root="${AWA_GOVERNED_ROOT:-}"
  local policy="${AWA_POLICY:-$1}"
  [ -n "$root" ] || {
    awa_log "dashboard publication skipped (no AWA_GOVERNED_ROOT configured)"
    return 0
  }

  # Publish the product-owned seed first. This writes only derived machine-local Canvas output plus
  # its narrowly named bridge alias; governed repositories remain read-only.
  if "$RUNTIME/dashboard/render.py" --root "$root" --policy "$policy" >/dev/null; then
    awa_log "published AWA dashboard from the product-owned seed"
  else
    awa_warn "dashboard publication reported an issue (non-fatal; kernel guarantee holds)"
    return 0
  fi

  # Reuse local-jobs only when its operator-adopted Canvas bridge is already enabled. AWA never
  # silently opts a machine into that shared bridge. The fixed job only re-runs the read-only
  # renderer and remains disabled for scheduling.
  local rc=0
  AWA_HOME="$RUNTIME" AWA_GOVERNED_ROOT="$root" AWA_POLICY="$policy" \
    "$RUNTIME/dashboard/install_actions.sh" --root "$root" --policy "$policy" >/dev/null 2>&1 || rc=$?
  if [ "$rc" -eq 0 ]; then
    awa_log "registered dashboard Refresh with the existing background Canvas bridge"
  elif [ "$rc" -eq 3 ]; then
    awa_log "background Canvas bridge not enabled; dashboard remains refreshable from the CLI"
  else
    awa_warn "background dashboard refresh unavailable (optional local-jobs integration not ready)"
  fi
  return 0
}

validate_integrity_product_assets() {
  local root="$1"
  local access_mode="${2:-runtime}"
  case "$access_mode" in
    source|runtime) ;;
    *) return 1 ;;
  esac
  [ -f "$root/contracts/awa-integrity-schedule.v1.json" ] || return 1
  [ -f "$root/contracts/awa-hook-owner.v2.json" ] || return 1
  [ -f "$root/engine/integrity_console.py" ] || return 1
  [ -f "$root/engine/integrity_alert.py" ] || return 1
  [ -f "$root/engine/native_entry.py" ] || return 1
  python3 - "$root" "$access_mode" <<'PY'
import json
import os
import stat
import sys
from pathlib import Path

root = Path(sys.argv[1])
access_mode = sys.argv[2]
scripts = (
    root / "kernel" / "bin" / "awa-integrity-sweep.sh",
    root / "kernel" / "hooks" / "worktree-guard-with-integrity.sh",
    root / "kernel" / "hooks" / "awa-integrity-observer.sh",
    root / "kernel" / "hooks" / "awa-session-handoff.sh",
    root / "engine" / "integrity_detach.py",
)


def valid_script(path):
    if not path.is_file():
        return False
    if access_mode == "runtime":
        return os.access(path, os.X_OK)
    try:
        mode = path.lstat().st_mode
    except OSError:
        return False
    return stat.S_ISREG(mode) and os.access(path, os.R_OK) and mode & 0o111 != 0


contract = json.loads(
    (root / "contracts" / "awa-integrity-schedule.v1.json").read_text(
        encoding="utf-8"
    )
)
owner = json.loads(
    (root / "contracts" / "awa-hook-owner.v2.json").read_text(
        encoding="utf-8"
    )
)
minimum = contract.get("minimum_interval_seconds")
interval = contract.get("interval_seconds")
maximum = contract.get("maximum_interval_seconds")
valid = (
    all(valid_script(path) for path in scripts)
    and contract.get("schema") == "awa-integrity-schedule/v1"
    and contract.get("label") == "com.kleinperkins.awa-integrity"
    and type(minimum) is int
    and type(interval) is int
    and type(maximum) is int
    and 0 < minimum <= interval <= maximum <= 86400
    and contract.get("profile") == "deep"
    and contract.get("trigger") == "launchd"
    and contract.get("ships_plist") is False
    and contract.get("exit_codes_verbatim") is True
    and contract.get("executable") == "kernel/bin/awa-integrity-sweep.sh"
    and not any(root.rglob("*.plist"))
    and owner.get("schema") == "awa-hook-owner/v2"
    and owner.get("version") == 2
    and owner.get("successor_of") == "awa-hook-owner/v1"
    and owner.get("v1_contract")
    == "contracts/awa-contract.v1.json#hook_ownership"
    and owner.get("modes") == ["direct", "external"]
    and owner.get("default_mode") == "direct"
    and owner.get("selection_schema") == "awa-hook-owner-selection/v1"
    and owner.get("external_real_hook_file_writes") is False
    and owner.get("supersedes_roles") == ["worktree.shell-guard"]
    and [
        (
            role.get("id"),
            role.get("event"),
            role.get("direct_command_role"),
        )
        for role in owner.get("roles", [])
    ]
    == [
        (
            "worktree.shell-guard-composite",
            "beforeShellExecution",
            "kernel/hooks/worktree-guard-with-integrity.sh",
        ),
        (
            "worktree.stop-observer",
            "stop",
            "kernel/hooks/awa-integrity-observer.sh",
        ),
        (
            "worktree.session-handoff",
            "sessionStart",
            "kernel/hooks/awa-session-handoff.sh",
        ),
    ]
    and owner.get("roles", [{}])[-1].get("dormant_until_milestone")
    == "M2.4"
)
raise SystemExit(0 if valid else 1)
PY
}

persist_hook_owner() {
  local mode="$1"
  {
    printf '%s\n' '{'
    printf '%s\n' '  "schema": "awa-hook-owner-selection/v1",'
    printf '%s\n' '  "contract": "awa-hook-owner/v1",'
    printf '  "mode": "%s"\n' "$mode"
    printf '%s\n' '}'
  } | awa_write_backup "$HOOK_OWNER_FILE"
  chmod 600 "$HOOK_OWNER_FILE" 2>/dev/null || awa_die "cannot protect hook-owner selection"
}

do_install() {
  local force="${1:-0}"
  local selected_hook_owner resolve_rc
  if selected_hook_owner="$(awa_hook_owner_resolve "$HOOK_OWNER_FILE" "$POINTER")"; then
    :
  else
    resolve_rc=$?
    return "$resolve_rc"
  fi

  awa_log "installing AWA runtime -> $RUNTIME"
  for d in "${COPY_TREES[@]}"; do
    [ -d "$SRC_ROOT/$d" ] && awa_sync_tree "$SRC_ROOT/$d" "$RUNTIME/$d"
  done
  mkdir -p "$RUNTIME"
  for f in "${COPY_FILES[@]}"; do
    [ -f "$SRC_ROOT/$f" ] && install -m 0644 "$SRC_ROOT/$f" "$RUNTIME/$f" 2>/dev/null || \
      { [ -f "$SRC_ROOT/$f" ] && cp "$SRC_ROOT/$f" "$RUNTIME/$f"; }
  done
  # Preserve executability of shims.
  chmod +x "$RUNTIME"/install.sh "$RUNTIME"/bootstrap.sh 2>/dev/null || true
  chmod +x "$RUNTIME"/kernel/bin/*.sh "$RUNTIME"/kernel/hooks/*.sh "$RUNTIME"/kernel/checks/*.sh 2>/dev/null || true
  chmod +x "$RUNTIME"/kernel/lib/*.py "$RUNTIME"/bin/*.sh "$RUNTIME"/dashboard/*.py \
    "$RUNTIME"/dashboard/*.sh "$RUNTIME"/engine/integrity_detach.py \
    "$RUNTIME"/consumer/finish_current.py 2>/dev/null || true
  # Product boundary: ship and validate the executable/contract/renderer only.
  # Host scheduling/activation stays exclusively with local-jobs.
  validate_integrity_product_assets "$RUNTIME" || \
    awa_die "installed integrity product assets are missing or invalid"

  local default_policy="$RUNTIME/kernel/policy/default-worktree-policy.yml"
  mkdir -p "$STATE_DIR"; chmod 700 "$STATE_DIR" 2>/dev/null || true

  # Persist the strict owner selection before any hook reconciliation. The record is deterministic,
  # private, and becomes the default for later repair/doctor/uninstall invocations that omit the env.
  persist_hook_owner "$selected_hook_owner"

  # AWA_POLICY ownership boundary: an EXPLICIT env value always wins (an operator/host deliberately
  # (re)configuring it). Otherwise, PRESERVE whatever value is already recorded in mcp.json -- a
  # reconcile invoked without that env exported (e.g. a bootstrap wrapper that doesn't re-export a
  # host overlay's AWA_POLICY) must never silently downgrade an already-configured host policy back
  # to the generic zero-governed-root default. Only a truly fresh entry (no prior value either way)
  # falls back to the installed default template. Resolved ONCE here and reused by every
  # policy-consuming step below (modes-file sync, the MCP entry, dashboard rendering) so a single
  # install/reconcile run can never have them disagree with each other.
  local host_policy="${AWA_POLICY:-}"
  if [ -z "$host_policy" ]; then
    host_policy="$(awa_mcp_env_get "$MCP_JSON" "awa" "AWA_POLICY")"
  fi
  [ -n "$host_policy" ] || host_policy="$default_policy"

  # Config env (host overlay may append env.d files; we keep AWA_GOVERNED_ROOT commented here).
  # Deterministic content (no timestamp) so a re-install is a true no-op (idempotency).
  awa_write_backup "$ENV_FILE" <<EOF
# AWA environment — generated by install.sh. Source this to put AWA on your PATH.
export AWA_HOME="$RUNTIME"
export AWA_POLICY="\${AWA_POLICY:-$default_policy}"
export AWA_HOOK_OWNER="\${AWA_HOOK_OWNER:-$selected_hook_owner}"
# export AWA_GOVERNED_ROOT="\$HOME/your-governed-root"   # optional; a host overlay sets this
export PATH="$RUNTIME/kernel/bin:$RUNTIME/bin:\$PATH"
EOF
  awa_log "wrote config env -> $ENV_FILE"

  # Ensure the host-configured per-repo modes file exists + is normalized (runs on install AND
  # --repair). ZERO-LINK: path/default resolved from the host policy's modes_file pointer, not here.
  ensure_modes_file "$host_policy"

  # Cursor hooks (merged, soft backstop) — the installed hooks reference the installed kernel.
  AWA_HOOK_OWNER="$selected_hook_owner" AWA_HOOKS_JSON="$HOOKS_JSON" \
    "$RUNTIME/kernel/hooks/install-hooks.sh"

  # Always-loaded user rule: makes the operator entrypoint and bare-choice dispatcher available
  # even when beforeSubmitPrompt blocked the initiating closeout prompt from model context.
  {
    printf '%s\n' '---' 'description: AWA operator and finish dispatcher' 'alwaysApply: true' '---'
    cat "$RUNTIME/consumer/operator-skill.md"
  } | awa_write_backup "$OPERATOR_RULE"
  awa_log "installed AWA operator entrypoint -> $OPERATOR_RULE"

  # Add-only MCP server (never clobbers other servers). Emit AWA_POLICY + AWA_GOVERNED_ROOT so
  # mode tools resolve the host-configured policy without patching _DEFAULT_POLICY at runtime.
  # (host_policy resolved once above, per the AWA_POLICY ownership boundary described there.)
  local governed_root="${AWA_GOVERNED_ROOT:-}"
  local mcp_env="AWA_POLICY=${host_policy}"
  [ -n "$governed_root" ] && mcp_env="${mcp_env}
AWA_GOVERNED_ROOT=${governed_root}"
  AWA_MCP_ENV="$mcp_env" awa_mcp_add "$MCP_JSON" "awa" "$RUNTIME/bin/awa-engine.sh" "mcp-serve"
  awa_log "registered MCP server 'awa' -> $MCP_JSON"

  configure_dashboard_refresh "$host_policy"

  # Self-describing release pointer. `installed_at` is preserved across re-installs whose
  # identity (version/commit/runtime/source/policy) is unchanged, so a re-install is a no-op.
  local version commit contract_sha256
  version="$(awa_engine_version "$RUNTIME")"
  commit="$(git -C "$SRC_ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
  contract_sha256="$(awa_sha256_file "$RUNTIME/contracts/awa-contract.v1.json")" || \
    awa_die "cannot digest installed hook-owner contract"
  AWA_PTR="$POINTER" AWA_V="$version" AWA_COMMIT="$commit" AWA_SRC="$SRC_ROOT" \
  AWA_RUNTIME="$RUNTIME" AWA_POL="$default_policy" \
  AWA_HOOK_OWNER_MODE="$selected_hook_owner" AWA_HOOK_OWNER_SHA256="$contract_sha256" \
  python3 - <<'PY'
import datetime, json, os
ptr = os.environ["AWA_PTR"]
identity = {
    "schema": "awa-release-pointer/v1",
    "version": os.environ["AWA_V"],
    "source": os.environ["AWA_SRC"],
    "commit": os.environ["AWA_COMMIT"],
    "runtime": os.environ["AWA_RUNTIME"],
    "policy": os.environ["AWA_POL"],
    "hook_owner_contract": "awa-hook-owner/v1",
    "hook_owner_mode": os.environ["AWA_HOOK_OWNER_MODE"],
    "hook_owner_contract_sha256": os.environ["AWA_HOOK_OWNER_SHA256"],
}
installed_at = None
if os.path.exists(ptr):
    try:
        cur = json.load(open(ptr))
        if all(cur.get(k) == v for k, v in identity.items()):
            installed_at = cur.get("installed_at")  # unchanged identity -> keep timestamp
    except Exception:
        pass
if installed_at is None:
    installed_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
out = dict(identity)
out["installed_at"] = installed_at
os.makedirs(os.path.dirname(ptr), exist_ok=True)
new = json.dumps(out, indent=2) + "\n"
old = open(ptr).read() if os.path.exists(ptr) else None
if old != new:
    open(ptr, "w").write(new)
PY
  awa_log "wrote release pointer -> $POINTER (version $version)"
  if [ "$force" = "1" ]; then
    awa_log "(--repair) forced re-copy complete."
  fi
  awa_log "install OK. Source '$ENV_FILE' (or add it to your shell profile) to put AWA on PATH."
  return 0
}

do_uninstall() {
  local keep_state=0
  local selected_hook_owner resolve_rc
  [ "${1:-}" = "--keep-state" ] && keep_state=1
  if selected_hook_owner="$(awa_hook_owner_resolve "$HOOK_OWNER_FILE" "$POINTER")"; then
    :
  else
    resolve_rc=$?
    return "$resolve_rc"
  fi
  awa_log "uninstalling AWA"
  if [ "$selected_hook_owner" = "direct" ]; then
    AWA_HOOKS_JSON="$HOOKS_JSON" _remove_hooks
  else
    awa_warn "external hook owner selected; host must reconcile its hook rows before or with runtime removal; selected hook file not inspected by AWA"
  fi
  awa_mcp_remove "$MCP_JSON" "awa"
  if [ -x "$RUNTIME/dashboard/install_actions.sh" ]; then
    if AWA_HOME="$RUNTIME" "$RUNTIME/dashboard/install_actions.sh" --remove >/dev/null; then
      awa_log "reconciled background dashboard refresh job removal"
    else
      awa_warn "preserved background dashboard job because its AWA ownership was not proven"
    fi
  fi
  rm -rf "$RUNTIME"
  rm -f "$ENV_FILE" "$POINTER" "$HOOK_OWNER_FILE"
  if [ -f "$OPERATOR_RULE" ] && \
     grep -q '^description: AWA operator and finish dispatcher$' "$OPERATOR_RULE" && \
     grep -q '^# AWA operator entrypoint$' "$OPERATOR_RULE"; then
    rm -f "$OPERATOR_RULE"
  elif [ -e "$OPERATOR_RULE" ]; then
    awa_warn "preserving non-AWA rule at $OPERATOR_RULE"
  fi
  rmdir "$CONFIG_DIR" 2>/dev/null || true
  if [ "$keep_state" = "1" ]; then
    awa_log "kept recovery/detection state at $STATE_DIR (--keep-state)"
  else
    if [ -d "$STATE_DIR" ]; then
      awa_warn "removing ordinary state at $STATE_DIR; protected Retain + protected recovery artifacts survive normal uninstall"
      STATE_DIR="$STATE_DIR" python3 - <<'PY'
import json, os, shutil, stat
from pathlib import Path

root = Path(os.environ["STATE_DIR"])
protected_retain = root / "protected-retain"   # kernel Retain artifacts (already protected)
recovery = root / "recovery"                    # engine recovery artifacts (some protected)
quarantine = recovery / "quarantine"            # explicit digest-bound preservation namespace


def real_directory(path):
    try:
        mode = os.lstat(path).st_mode
    except OSError:
        return False
    return stat.S_ISDIR(mode) and not stat.S_ISLNK(mode)


def recovery_entries_nonfollowing(recovery_dir, preserved):
    """Enumerate lexically without entering symlink directories or the preserved quarantine."""
    files = []
    directories = []
    pending = [recovery_dir]
    while pending:
        current = pending.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for entry in entries:
            path = Path(entry.path)
            if path == preserved:
                continue
            if entry.is_dir(follow_symlinks=False) and not entry.is_symlink():
                directories.append(path)
                pending.append(path)
            else:
                files.append(path)
    return files, directories


def protected_recovery_files(recovery_dir):
    """Resolved paths of every file belonging to a PROTECTED recovery artifact (its manifest +
    archive). Fail-safe: an unreadable manifest is PRESERVED (never delete under uncertainty)."""
    keep = set()
    if not recovery_dir.is_dir():
        return keep
    for m in recovery_dir.iterdir():
        if not (m.is_file() and m.name.endswith(".manifest.json")):
            continue
        try:
            doc = json.loads(m.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            keep.add(str(m.resolve()))
            continue
        if isinstance(doc, dict) and doc.get("protected"):
            keep.add(str(m.resolve()))
            if doc.get("archive"):
                keep.add(str(Path(str(doc["archive"])).resolve()))
            if doc.get("archive_name"):
                keep.add(str((recovery_dir / str(doc["archive_name"])).resolve()))
    return keep


keep = protected_recovery_files(recovery)
quarantine_is_real = real_directory(quarantine)
if os.path.lexists(quarantine) and not quarantine_is_real:
    # Remove only the lexical unsafe entry. Never inspect or traverse its target.
    try:
        quarantine.unlink()
    except OSError:
        pass

for child in list(root.iterdir()):
    if child == protected_retain:
        continue
    if child == recovery and (keep or quarantine_is_real):
        # Prune ONLY ordinary artifacts; preserve protected artifacts and the complete quarantine
        # subtree byte-identically, including any crash-resume journal.
        files, directories = recovery_entries_nonfollowing(
            recovery, quarantine if quarantine_is_real else None
        )
        for f in files:
            if f.is_symlink():
                continue
            if str(f.resolve()) in keep:
                continue
            try:
                f.unlink()
            except OSError:
                pass
        for d in reversed(directories):
            try:
                d.rmdir()
            except OSError:
                pass
        continue
    if child.is_dir() and not child.is_symlink():
        shutil.rmtree(child)
    else:
        child.unlink()

# Remove the state root only when NOTHING protected survived.
if not protected_retain.exists() and not (recovery.is_dir() and any(recovery.iterdir())):
    try:
        root.rmdir()
    except OSError:
        pass
PY
    fi
  fi
  awa_log "uninstall complete."
}

_remove_hooks() {
  [ -f "$HOOKS_JSON" ] || return 0
  local tmp; tmp="$(mktemp)"
  RUNTIME="$RUNTIME" python3 - "$HOOKS_JSON" > "$tmp" <<'PY'
import json, os, pathlib, sys
try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        data = json.load(fh)
except Exception as exc:
    print(f"uninstall: refusing malformed hooks JSON: {exc}", file=sys.stderr)
    sys.exit(1)
if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("hooks"), dict):
    print("uninstall: refusing malformed hooks object/version/hooks", file=sys.stderr)
    sys.exit(1)
hooks = data["hooks"]
owned = {
    (pathlib.Path(os.environ["RUNTIME"]) / "kernel" / "hooks" / name).resolve()
    for name in ("worktree-guard.sh", "worktree-session.sh", "before-submit-prompt.sh",
                 "awa-recovery-maintenance.sh",
                 "worktree-guard-with-integrity.sh",
                 "awa-integrity-observer.sh", "awa-session-handoff.sh")
}
def is_owned(entry):
    command = str(entry.get("command", ""))
    return len(command.split()) == 1 and pathlib.Path(command).expanduser().resolve() in owned
for event in list(hooks.keys()):
    if not isinstance(hooks[event], list):
        print("uninstall: refusing malformed hook event", file=sys.stderr)
        sys.exit(1)
    hooks[event] = [e for e in hooks[event]
                    if not (isinstance(e, dict) and is_owned(e))]
    if not hooks[event]:
        hooks.pop(event, None)
print(json.dumps(data, indent=2))
PY
  awa_write_backup "$HOOKS_JSON" < "$tmp"
  rm -f "$tmp"
  awa_log "removed AWA hook entries from $HOOKS_JSON"
}

do_doctor() {
  local rc=0 selected_hook_owner resolve_rc owner_ok=0 expected_version expected_commit
  echo "== awa install doctor =="
  echo "   runtime=$RUNTIME"
  if selected_hook_owner="$(awa_hook_owner_resolve "$HOOK_OWNER_FILE" "$POINTER")"; then
    :
  else
    resolve_rc=$?
    echo "  FAIL  hook-owner selection invalid"
    echo "awa doctor: FAILED"
    return "$resolve_rc"
  fi
  if [ -d "$RUNTIME" ]; then echo "  PASS  runtime present"; else echo "  FAIL  runtime missing (run bash ./install.sh)"; rc=1; fi
  if [ -f "$ENV_FILE" ]; then echo "  PASS  config env present"; else echo "  FAIL  config env missing"; rc=1; fi
  if [ -f "$POINTER" ] && python3 -c 'import json,sys;json.load(open(sys.argv[1]))' "$POINTER" 2>/dev/null; then
    echo "  PASS  release pointer present + valid"
  else echo "  FAIL  release pointer missing/invalid"; rc=1; fi
  if [ -f "$RUNTIME/contracts/awa-contract.v1.json" ] && \
     python3 -c 'import json,sys;json.load(open(sys.argv[1]))' "$RUNTIME/contracts/awa-contract.v1.json" 2>/dev/null; then
    echo "  PASS  frozen contract present + valid"
  else echo "  FAIL  frozen contract missing/invalid"; rc=1; fi
  if [ -f "$RUNTIME/kernel/policy/default-worktree-policy.yml" ]; then echo "  PASS  default policy present"; else echo "  FAIL  default policy missing"; rc=1; fi
  if validate_integrity_product_assets "$RUNTIME"; then
    echo "  PASS  integrity sweep/console + awa-hook-owner/v2 assets valid (host activation external)"
  else
    echo "  FAIL  integrity sweep/console or awa-hook-owner/v2 assets missing or invalid"
    rc=1
  fi
  if [ -x "$RUNTIME/kernel/bin/dev-worktree.sh" ] && "$RUNTIME/kernel/bin/dev-worktree.sh" policy-check >/dev/null 2>&1; then
    echo "  PASS  kernel CLI runnable (policy-check OK)"
  else echo "  FAIL  kernel CLI not runnable"; rc=1; fi

  expected_version="$(awa_engine_version "$RUNTIME")"
  expected_commit="$(git -C "$SRC_ROOT" rev-parse HEAD 2>/dev/null || true)"
  if AWA_OWNER_SELECTION="$HOOK_OWNER_FILE" AWA_OWNER_POINTER="$POINTER" \
    AWA_OWNER_CONTRACT="$RUNTIME/contracts/awa-contract.v1.json" \
    AWA_OWNER_SOURCE_CONTRACT="$SRC_ROOT/contracts/awa-contract.v1.json" \
    AWA_OWNER_RUNTIME="$RUNTIME" AWA_OWNER_MODE="$selected_hook_owner" \
    AWA_OWNER_VERSION="$expected_version" AWA_OWNER_COMMIT="$expected_commit" \
    python3 - <<'PY'
import hashlib
import json
import os
import re
import sys
from pathlib import Path

try:
    selection_path = Path(os.environ["AWA_OWNER_SELECTION"])
    pointer_path = Path(os.environ["AWA_OWNER_POINTER"])
    contract_path = Path(os.environ["AWA_OWNER_CONTRACT"])
    source_contract_path = Path(os.environ["AWA_OWNER_SOURCE_CONTRACT"])
    runtime = Path(os.environ["AWA_OWNER_RUNTIME"])
    mode = os.environ["AWA_OWNER_MODE"]
    expected_version = os.environ["AWA_OWNER_VERSION"]
    expected_commit = os.environ["AWA_OWNER_COMMIT"]

    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    if (
        type(selection) is not dict
        or set(selection) != {"schema", "contract", "mode"}
        or selection != {
            "schema": "awa-hook-owner-selection/v1",
            "contract": "awa-hook-owner/v1",
            "mode": mode,
        }
    ):
        raise ValueError

    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    required_pointer = {
        "schema", "version", "source", "commit", "runtime", "policy",
        "hook_owner_contract", "hook_owner_mode",
        "hook_owner_contract_sha256", "installed_at",
    }
    if (
        type(pointer) is not dict
        or not required_pointer.issubset(pointer)
        or pointer.get("schema") != "awa-release-pointer/v1"
        or pointer.get("hook_owner_contract") != "awa-hook-owner/v1"
        or pointer.get("hook_owner_mode") != mode
        or pointer.get("runtime") != str(runtime)
        or pointer.get("policy") != str(
            runtime / "kernel" / "policy" / "default-worktree-policy.yml")
        or pointer.get("version") != expected_version
        or type(pointer.get("commit")) is not str
        or re.fullmatch(r"[0-9a-f]{40}", pointer["commit"]) is None
        or (expected_commit and pointer["commit"] != expected_commit)
    ):
        raise ValueError

    contract_bytes = contract_path.read_bytes()
    contract = json.loads(contract_bytes.decode("utf-8"))
    owner = contract.get("hook_ownership")
    if (
        type(owner) is not dict
        or owner.get("schema") != "awa-hook-owner/v1"
        or owner.get("modes") != ["direct", "external"]
        or owner.get("default_mode") != "direct"
        or owner.get("selection_schema") != "awa-hook-owner-selection/v1"
        or owner.get("external_real_hook_file_writes") is not False
    ):
        raise ValueError
    digest = hashlib.sha256(contract_bytes).hexdigest()
    if pointer.get("hook_owner_contract_sha256") != digest:
        raise ValueError
    if source_contract_path.read_bytes() != contract_bytes:
        raise ValueError

    required_scripts = (
        "worktree-session.sh", "worktree-guard.sh",
        "awa-recovery-maintenance.sh", "before-submit-prompt.sh",
        "worktree-guard-with-integrity.sh", "awa-integrity-observer.sh",
        "awa-session-handoff.sh",
    )
    for name in required_scripts:
        script = runtime / "kernel" / "hooks" / name
        if not script.is_file() or not os.access(script, os.X_OK):
            raise ValueError
except (KeyError, OSError, TypeError, UnicodeError, ValueError,
        json.JSONDecodeError):
    raise SystemExit(1)
PY
  then
    owner_ok=1
  else
    echo "  FAIL  hook-owner selection/pointer/runtime contract drift"
    rc=1
  fi

  if [ "$selected_hook_owner" = "direct" ]; then
    [ "$owner_ok" -eq 1 ] && echo "  PASS  hook owner selected: direct"
    if AWA_HOOK_OWNER=direct AWA_HOOKS_JSON="$HOOKS_JSON" \
      "$RUNTIME/kernel/hooks/install-hooks.sh" --check >/dev/null 2>&1; then
      echo "  PASS  Cursor hooks reference installed AWA (no failClosed drift)"
    else
      echo "  FAIL  Cursor hook deployment drift"
      rc=1
    fi
  elif [ "$owner_ok" -eq 1 ]; then
    echo "  PASS  hook owner selected: external (host-managed; hook file not inspected by AWA)"
  else
    echo "  FAIL  hook owner selected: external (AWA-owned state drift; hook file not inspected by AWA)"
  fi

  if [ -f "$OPERATOR_RULE" ] && grep -q '^alwaysApply: true$' "$OPERATOR_RULE"; then
    echo "  PASS  AWA operator entrypoint installed (always-loaded dispatcher)"
  else echo "  FAIL  AWA operator entrypoint missing/drifted"; rc=1; fi
  if "$RUNTIME/bin/awa-engine.sh" doctor >/dev/null 2>&1; then
    echo "  PASS  engine runnable (engine doctor)"
  else echo "  WARN  engine not runnable (kernel guarantee holds engine-off)"; fi
  if AWA_HOME="$RUNTIME" "$RUNTIME/kernel/checks/awa-contract-freeze.sh" >/dev/null 2>&1; then
    echo "  PASS  installed kernel satisfies the frozen behavior contract"
  else echo "  FAIL  installed kernel drifted from the frozen contract"; rc=1; fi
  if [ "$rc" -eq 0 ]; then echo "awa doctor: OK"; else echo "awa doctor: FAILED"; fi
  return "$rc"
}

# CI-safe static preflight — validates the SOURCE tree is install-ready. Writes NOTHING to $HOME.
do_check() {
  local rc=0
  echo "== awa install --check (static preflight, no writes) =="
  if python3 -c 'import json,sys;json.load(open(sys.argv[1]))' "$SRC_ROOT/contracts/awa-contract.v1.json" 2>/dev/null; then
    echo "  PASS  contract valid JSON"
  else echo "  FAIL  contract invalid"; rc=1; fi
  # frozen behavior keys present
  if python3 - "$SRC_ROOT/contracts/awa-contract.v1.json" <<'PY'
import json, sys
c = json.load(open(sys.argv[1]))
need_cli = set(["status","ensure","list","clean","doctor","policy-check","dashboard-data"])
owner = c.get("hook_ownership", {})
owner_ids = [
    "worktree.session-context", "worktree.shell-guard", "worktree.file-observer",
    "recovery.maintenance", "finish.prompt-recall",
]
ok = (set(c["cli"]["verbs"]) >= need_cli and c["dashboard_data"]["schema"] == "awa-worktree/v1"
      and c["lease"]["schema"] == "awa-lease/v1" and c.get("version") == 1
      and owner.get("schema") == "awa-hook-owner/v1"
      and owner.get("modes") == ["direct", "external"]
      and owner.get("default_mode") == "direct"
      and owner.get("selection_schema") == "awa-hook-owner-selection/v1"
      and owner.get("external_real_hook_file_writes") is False
      and [role.get("id") for role in owner.get("roles", [])] == owner_ids)
sys.exit(0 if ok else 1)
PY
  then echo "  PASS  frozen behavior floor present (verbs, schemas, hook owner, version=1)"; else echo "  FAIL  frozen behavior floor drifted"; rc=1; fi
  if bash "$SRC_ROOT/kernel/bin/dev-worktree.sh" policy-check >/dev/null 2>&1; then
    echo "  PASS  default policy valid"
  else echo "  FAIL  default policy invalid"; rc=1; fi
  if python3 "$SRC_ROOT/kernel/lib/awa_policy.py" dump --policy "$SRC_ROOT/kernel/policy/default-worktree-policy.yml" >/dev/null 2>&1; then
    echo "  PASS  policy resolver loads"
  else echo "  FAIL  policy resolver failed"; rc=1; fi
  if [ -f "$SRC_ROOT/consumer/operator-skill.md" ] && [ -f "$SRC_ROOT/consumer/finish_current.py" ]; then
    echo "  PASS  finish operator entrypoint sources present"
  else echo "  FAIL  finish operator entrypoint sources missing"; rc=1; fi
  if validate_integrity_product_assets "$SRC_ROOT" source; then
    echo "  PASS  integrity product + awa-hook-owner/v2 assets valid (no plist; host activation external)"
  else echo "  FAIL  integrity product assets invalid"; rc=1; fi
  if [ -f "$SRC_ROOT/dashboard/seed.canvas.tsx" ] && \
     [ -f "$SRC_ROOT/dashboard/render.py" ] && \
     [ -f "$SRC_ROOT/dashboard/install_actions.sh" ] && \
     ! grep -q '/Users/' "$SRC_ROOT/dashboard/seed.canvas.tsx"; then
    echo "  PASS  dashboard seed + background refresh sources present and data-free"
  else echo "  FAIL  dashboard refresh sources carry data / are missing"; rc=1; fi
  if AWA_HOME="$SRC_ROOT" /bin/bash "$SRC_ROOT/kernel/checks/awa-contract-freeze.sh" >/dev/null 2>&1; then
    echo "  PASS  kernel satisfies the frozen behavior contract"
  else echo "  FAIL  kernel drifted from frozen contract"; rc=1; fi
  if [ "$rc" -eq 0 ]; then echo "awa --check: OK"; else echo "awa --check: FAILED"; fi
  return "$rc"
}

# Sourcing guard: allow tests to `source`/`.` this file (e.g. to exercise awa_write_backup in
# isolation) without triggering an actual install. Every real invocation runs it as the top-level
# script (`./install.sh`, `bash install.sh`, or install-lib.sh's own BASH_SOURCE idiom), where
# BASH_SOURCE[0] always equals $0 — identical to how this script tests BASH_SOURCE when locating
# its own SRC_ROOT above.
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  case "${1:-install}" in
    install|"")   do_install 0 ;;
    --repair)     do_install 1 ;;
    --doctor)     do_doctor ;;
    --check)      do_check ;;
    --uninstall)  shift; do_uninstall "${1:-}" ;;
    -h|--help)    sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//' ;;
    *) awa_die "unknown argument: $1 (see --help)" ;;
  esac
fi
