#!/usr/bin/env bash
# install.sh — AWA Standalone System Package (SSP) installer.
#
# Clone KleinPerkins/awa and run ./install.sh: it installs a self-contained AWA (generic kernel +
# engine + dashboard + frozen contract) into your XDG dirs with NO sibling-repo dependency, then
# wires the Cursor hooks + an add-only MCP server. Idempotent, backup-before-write.
#
#   ./install.sh                 install/reconcile (idempotent)
#   ./install.sh --repair        force re-copy the runtime + re-wire hooks/mcp
#   ./install.sh --doctor        read-only health check of the install
#   ./install.sh --check         CI-safe static preflight (no writes to $HOME)
#   ./install.sh --uninstall [--keep-state]   remove the install (‑‑keep-state preserves recovery state)
#
# Layout (all HOME/XDG-relative — honors a HOME override):
#   runtime  $XDG_DATA_HOME/awa/current/           kernel + engine + dashboard + contracts + bin
#   config   $XDG_CONFIG_HOME/awa/env              AWA_HOME, AWA_POLICY, (AWA_GOVERNED_ROOT)
#   hooks    $HOME/.cursor/hooks.json              merged (soft worktree backstop)
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

do_install() {
  local force="${1:-0}"
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
    "$RUNTIME"/dashboard/*.sh \
    "$RUNTIME"/consumer/finish_current.py 2>/dev/null || true

  local default_policy="$RUNTIME/kernel/policy/default-worktree-policy.yml"
  mkdir -p "$STATE_DIR"; chmod 700 "$STATE_DIR" 2>/dev/null || true

  # Config env (host overlay may append env.d files; we keep AWA_GOVERNED_ROOT commented here).
  # Deterministic content (no timestamp) so a re-install is a true no-op (idempotency).
  awa_write_backup "$ENV_FILE" <<EOF
# AWA environment — generated by install.sh. Source this to put AWA on your PATH.
export AWA_HOME="$RUNTIME"
export AWA_POLICY="\${AWA_POLICY:-$default_policy}"
# export AWA_GOVERNED_ROOT="\$HOME/your-governed-root"   # optional; a host overlay sets this
export PATH="$RUNTIME/kernel/bin:$RUNTIME/bin:\$PATH"
EOF
  awa_log "wrote config env -> $ENV_FILE"

  # Ensure the host-configured per-repo modes file exists + is normalized (runs on install AND
  # --repair). ZERO-LINK: path/default resolved from the host policy's modes_file pointer, not here.
  ensure_modes_file "${AWA_POLICY:-$default_policy}"

  # Cursor hooks (merged, soft backstop) — the installed hooks reference the installed kernel.
  AWA_HOOKS_JSON="$HOOKS_JSON" "$RUNTIME/kernel/hooks/install-hooks.sh"

  # Always-loaded user rule: makes the operator entrypoint and bare-choice dispatcher available
  # even when beforeSubmitPrompt blocked the initiating closeout prompt from model context.
  {
    printf '%s\n' '---' 'description: AWA operator and finish dispatcher' 'alwaysApply: true' '---'
    cat "$RUNTIME/consumer/operator-skill.md"
  } | awa_write_backup "$OPERATOR_RULE"
  awa_log "installed AWA operator entrypoint -> $OPERATOR_RULE"

  # Add-only MCP server (never clobbers other servers). Emit AWA_POLICY + AWA_GOVERNED_ROOT so
  # mode tools resolve the host-configured policy without patching _DEFAULT_POLICY at runtime.
  #
  # AWA_POLICY ownership boundary: an EXPLICIT env value always wins (an operator/host deliberately
  # (re)configuring it). Otherwise, PRESERVE whatever value is already recorded in mcp.json -- a
  # reconcile invoked without that env exported (e.g. a bootstrap wrapper that doesn't re-export a
  # host overlay's AWA_POLICY) must never silently downgrade an already-configured host policy back
  # to the generic zero-governed-root default. Only a truly fresh entry (no prior value either way)
  # falls back to the installed default template.
  local host_policy="${AWA_POLICY:-}"
  if [ -z "$host_policy" ]; then
    host_policy="$(awa_mcp_env_get "$MCP_JSON" "awa" "AWA_POLICY")"
  fi
  [ -n "$host_policy" ] || host_policy="$default_policy"
  local governed_root="${AWA_GOVERNED_ROOT:-}"
  local mcp_env="AWA_POLICY=${host_policy}"
  [ -n "$governed_root" ] && mcp_env="${mcp_env}
AWA_GOVERNED_ROOT=${governed_root}"
  AWA_MCP_ENV="$mcp_env" awa_mcp_add "$MCP_JSON" "awa" "$RUNTIME/bin/awa-engine.sh" "mcp-serve"
  awa_log "registered MCP server 'awa' -> $MCP_JSON"

  configure_dashboard_refresh "$default_policy"

  # Self-describing release pointer. `installed_at` is preserved across re-installs whose
  # identity (version/commit/runtime/source/policy) is unchanged, so a re-install is a no-op.
  local version commit
  version="$(awa_engine_version "$RUNTIME")"
  commit="$(git -C "$SRC_ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
  AWA_PTR="$POINTER" AWA_V="$version" AWA_COMMIT="$commit" AWA_SRC="$SRC_ROOT" \
  AWA_RUNTIME="$RUNTIME" AWA_POL="$default_policy" python3 - <<'PY'
import datetime, json, os
ptr = os.environ["AWA_PTR"]
identity = {
    "schema": "awa-release-pointer/v1",
    "version": os.environ["AWA_V"],
    "source": os.environ["AWA_SRC"],
    "commit": os.environ["AWA_COMMIT"],
    "runtime": os.environ["AWA_RUNTIME"],
    "policy": os.environ["AWA_POL"],
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
  [ "${1:-}" = "--keep-state" ] && keep_state=1
  awa_log "uninstalling AWA"
  AWA_HOOKS_JSON="$HOOKS_JSON" _remove_hooks
  awa_mcp_remove "$MCP_JSON" "awa"
  if [ -x "$RUNTIME/dashboard/install_actions.sh" ]; then
    if AWA_HOME="$RUNTIME" "$RUNTIME/dashboard/install_actions.sh" --remove >/dev/null; then
      awa_log "reconciled background dashboard refresh job removal"
    else
      awa_warn "preserved background dashboard job because its AWA ownership was not proven"
    fi
  fi
  rm -rf "$RUNTIME"
  rm -f "$ENV_FILE" "$POINTER"
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
import json, os, shutil
from pathlib import Path

root = Path(os.environ["STATE_DIR"])
protected_retain = root / "protected-retain"   # kernel Retain artifacts (already protected)
recovery = root / "recovery"                    # engine recovery artifacts (some protected)


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

for child in list(root.iterdir()):
    if child == protected_retain:
        continue
    if child == recovery and keep:
        # Prune ONLY ordinary artifacts; preserve every protected archive + manifest.
        for f in list(recovery.rglob("*")):
            if f.is_dir() or f.is_symlink():
                continue
            if str(f.resolve()) in keep:
                continue
            try:
                f.unlink()
            except OSError:
                pass
        for d in sorted((p for p in recovery.rglob("*") if p.is_dir()), reverse=True):
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
                 "awa-recovery-maintenance.sh")
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
  local rc=0
  echo "== awa install doctor =="
  echo "   runtime=$RUNTIME"
  if [ -d "$RUNTIME" ]; then echo "  PASS  runtime present"; else echo "  FAIL  runtime missing (run ./install.sh)"; rc=1; fi
  if [ -f "$ENV_FILE" ]; then echo "  PASS  config env present"; else echo "  FAIL  config env missing"; rc=1; fi
  if [ -f "$POINTER" ] && python3 -c 'import json,sys;json.load(open(sys.argv[1]))' "$POINTER" 2>/dev/null; then
    echo "  PASS  release pointer present + valid"
  else echo "  FAIL  release pointer missing/invalid"; rc=1; fi
  if [ -f "$RUNTIME/contracts/awa-contract.v1.json" ] && \
     python3 -c 'import json,sys;json.load(open(sys.argv[1]))' "$RUNTIME/contracts/awa-contract.v1.json" 2>/dev/null; then
    echo "  PASS  frozen contract present + valid"
  else echo "  FAIL  frozen contract missing/invalid"; rc=1; fi
  if [ -f "$RUNTIME/kernel/policy/default-worktree-policy.yml" ]; then echo "  PASS  default policy present"; else echo "  FAIL  default policy missing"; rc=1; fi
  if [ -x "$RUNTIME/kernel/bin/dev-worktree.sh" ] && "$RUNTIME/kernel/bin/dev-worktree.sh" policy-check >/dev/null 2>&1; then
    echo "  PASS  kernel CLI runnable (policy-check OK)"
  else echo "  FAIL  kernel CLI not runnable"; rc=1; fi
  if AWA_HOOKS_JSON="$HOOKS_JSON" "$RUNTIME/kernel/hooks/install-hooks.sh" --check >/dev/null 2>&1; then
    echo "  PASS  Cursor hooks reference installed AWA (no failClosed drift)"
  else echo "  FAIL  Cursor hook deployment drift"; rc=1; fi
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
ok = (set(c["cli"]["verbs"]) >= need_cli and c["dashboard_data"]["schema"] == "awa-worktree/v1"
      and c["lease"]["schema"] == "awa-lease/v1" and c.get("version") == 1)
sys.exit(0 if ok else 1)
PY
  then echo "  PASS  frozen behavior floor present (verbs, schemas, version=1)"; else echo "  FAIL  frozen behavior floor drifted"; rc=1; fi
  if "$SRC_ROOT/kernel/bin/dev-worktree.sh" policy-check >/dev/null 2>&1; then
    echo "  PASS  default policy valid"
  else echo "  FAIL  default policy invalid"; rc=1; fi
  if python3 "$SRC_ROOT/kernel/lib/awa_policy.py" dump --policy "$SRC_ROOT/kernel/policy/default-worktree-policy.yml" >/dev/null 2>&1; then
    echo "  PASS  policy resolver loads"
  else echo "  FAIL  policy resolver failed"; rc=1; fi
  if [ -f "$SRC_ROOT/consumer/operator-skill.md" ] && [ -f "$SRC_ROOT/consumer/finish_current.py" ]; then
    echo "  PASS  finish operator entrypoint sources present"
  else echo "  FAIL  finish operator entrypoint sources missing"; rc=1; fi
  if [ -f "$SRC_ROOT/dashboard/seed.canvas.tsx" ] && \
     [ -f "$SRC_ROOT/dashboard/render.py" ] && \
     [ -f "$SRC_ROOT/dashboard/install_actions.sh" ] && \
     ! grep -q '/Users/' "$SRC_ROOT/dashboard/seed.canvas.tsx"; then
    echo "  PASS  dashboard seed + background refresh sources present and data-free"
  else echo "  FAIL  dashboard refresh sources carry data / are missing"; rc=1; fi
  if AWA_HOME="$SRC_ROOT" "$SRC_ROOT/kernel/checks/awa-contract-freeze.sh" >/dev/null 2>&1; then
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
