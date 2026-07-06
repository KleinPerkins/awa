#!/usr/bin/env bash
# dev-worktree.sh — policy-driven helper for agent worktree isolation (AWA kernel).
#
# The script intentionally owns only git/worktree mechanics. It cannot call Cursor
# MCP tools itself, so `ensure` prints the exact move_agent_to_root instruction that
# the agent must execute after the worktree exists.
#
# ZERO-LINK: this script carries NO org/host literals. Repo classification (including
# excluding a self-governed sibling repo) is decided GENERICALLY by kernel/lib/awa_policy.py
# reading a machine-local policy file. Org/vendor literals live ONLY in a host overlay policy
# resolved by role via AWA_POLICY (see kernel/policy/default-worktree-policy.yml).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"   # kernel/bin
KERNEL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"                        # kernel
AWA_HOME="$(cd "$KERNEL_DIR/.." && pwd)"                          # install root
SELF_NAME="$(basename "${BASH_SOURCE[0]:-$0}")"

# Policy + classifier resolved BY ROLE: AWA_POLICY (host overlay) else the installed
# generic default template. The classifier is the single kernel-layer policy resolver.
POLICY="${AWA_POLICY:-$KERNEL_DIR/policy/default-worktree-policy.yml}"
AWA_POLICY_LIB="$KERNEL_DIR/lib/awa_policy.py"

# X3: agent-created worktrees live on a DURABLE root, not ~/.cursor/worktrees (which Cursor
# subjects to its own count/size cleanup — conflicting with the no-lost-work guarantee). The
# Cursor-native Agents-Window path (H2 default) still uses Cursor's own location; this default
# governs only the agent-created fallback path.
MANAGED_LOCATION="${DEV_WORKTREE_MANAGED_LOCATION:-${XDG_DATA_HOME:-$HOME/.local/share}/awa/worktrees}"
DEFAULT_BRANCH_PREFIX="${DEV_WORKTREE_BRANCH_PREFIX:-cursor/worktree}"
AWA_RECOVERY_DIR="${AWA_RECOVERY_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/awa/recovery}"

usage() {
  cat <<EOF
usage: $SELF_NAME <verb> [options]

verbs:
  status         show current repo classification and root/worktree state
  ensure         create/select a worktree when policy says this repo is included
  list           list git worktrees for the current repo
  clean          safely remove a clean merged worktree (requires --path)
  doctor         run policy and worktree-health checks
  policy-check   validate the policy file and print a summary
  dashboard-data emit READ-ONLY awa-worktree/v1 JSON for the status dashboard
  mode           manage the tool-owned per-repo modes file (list|get|set|remove|repair|sync)

mode subcommands (delegated to the engine modes manager; edits ONLY the host modes file):
  mode list                      list all explicit modes + default_mode
  mode get <rel>                 show the effective mode for a repo path/glob
  mode set <rel> <on|ask_on|off> set an explicit mode
  mode remove <rel>              remove an explicit mode entry
  mode repair                    re-materialize/reconcile eligible repos (idempotent)
  mode sync [--default-mode M]   reconcile new/removed repos (creates the file if absent)
  (accepts --policy P / --modes-file F; defaults to the resolved host policy)

dashboard-data options:
  --root DIR       governed root to scan (default: resolved governed root / AWA_GOVERNED_ROOT)
  --timeout SECS   per-git-probe timeout (default: 4)

ensure options:
  --base REF       base ref for git worktree add (default: HEAD)
  --branch NAME    branch to create (default: cursor/worktree/<repo>-<timestamp>)
  --path PATH      explicit worktree path (default: managed-location/<repo>/<slug>)
  --json           machine-readable output

clean options:
  --path PATH      worktree path to remove
  --bundle         archive git-ignored local files to the recovery dir before removal (X3)
  --force          discard git-ignored files (no bundle) and pass --force to worktree remove
  --delete-branch  also delete the local branch when it still points at captured HEAD

policy:
  AWA_POLICY           path to the worktree policy (default: installed generic template)
  AWA_GOVERNED_ROOT    governed root override (else derived from the policy)

security:
  Repo-committed .cursor/worktrees.json setup commands are NOT executed by default (H3).
  Opt in per-repo (out-of-repo, re-armed on config change) via DEV_WORKTREE_SETUP_OPT_IN=1
  or an allow file under \${XDG_CONFIG_HOME:-~/.config}/awa/setup-allow/.
EOF
}

die() { printf '%s: %s\n' "$SELF_NAME" "$*" >&2; exit 1; }
note() { printf '%s: %s\n' "$SELF_NAME" "$*"; }

json_escape() {
  python3 -c 'import json,sys; print(json.dumps(sys.stdin.read())[1:-1])'
}

top_level() {
  git rev-parse --show-toplevel 2>/dev/null || return 1
}

git_dir_abs() {
  git rev-parse --path-format=absolute --git-dir 2>/dev/null || return 1
}

git_common_abs() {
  git rev-parse --path-format=absolute --git-common-dir 2>/dev/null || return 1
}

is_linked_worktree() {
  local gd cg
  gd="$(git_dir_abs)" || return 1
  cg="$(git_common_abs)" || return 1
  [ "$gd" != "$cg" ]
}

policy_value() {
  local key="$1"
  [ -f "$POLICY" ] || return 1
  awk -F: -v key="$key" '$1 == key {gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2); print $2; exit}' "$POLICY"
}

# Generic classification — the SINGLE kernel-layer resolver (kernel/lib/awa_policy.py) reads
# the policy file and decides include/exclude/advisory. Emits: class<TAB>reason<TAB>rel<TAB>root.
classify_context() {
  local top hp origin has_origin
  top="$(top_level)" || { printf 'not-git\tNot a git repository\t.\t\n'; return; }
  hp="$(git config --get core.hooksPath 2>/dev/null || true)"
  origin="$(git config --get remote.origin.url 2>/dev/null || true)"
  if [ -n "$origin" ]; then has_origin=1; else has_origin=0; fi
  python3 "$AWA_POLICY_LIB" classify --policy "$POLICY" \
    --governed-root "${AWA_GOVERNED_ROOT:-}" \
    --toplevel "$top" --hooks-path "$hp" --has-origin "$has_origin" 2>/dev/null \
    || printf 'advisory\tclassifier unavailable\t%s\t\n' "$(basename "$top")"
}

# Back-compat 2-field verdict (class<TAB>reason) for callers that only need the decision.
classify_repo() {
  classify_context | cut -f1,2
}

# Resolve the EXPLICIT per-repo mode (on|ask_on|off|invalid|(none)) via the generic
# `mode-for` CLI — the SAME kernel resolver + host policy the classifier uses (zero-link;
# the modes map / default_mode / modes_file all live in the host policy). Empty output
# (no explicit entry) is surfaced as `(none)`. This is a READ; it never mutates anything.
explicit_mode_for() {
  local top="$1" m
  m="$(python3 "$AWA_POLICY_LIB" mode-for --policy "$POLICY" \
        --governed-root "${AWA_GOVERNED_ROOT:-}" --toplevel "$top" 2>/dev/null || true)"
  if [ -z "$m" ]; then printf '(none)'; else printf '%s' "$m"; fi
}

current_state() {
  local top class reason rel gr linked
  top="$(top_level)" || { printf 'repo: <none>\nclassification: not-git\nreason: Not a git repository\n'; return; }
  IFS=$'\t' read -r class reason rel gr < <(classify_context)
  if is_linked_worktree; then linked=yes; else linked=no; fi
  printf 'repo: %s\n' "$top"
  printf 'path-under-root: %s\n' "$rel"
  printf 'governed-root: %s\n' "${gr:-<none>}"
  printf 'classification: %s\n' "$class"
  printf 'reason: %s\n' "$reason"
  printf 'linked-worktree: %s\n' "$linked"
  printf 'git-dir: %s\n' "$(git_dir_abs 2>/dev/null || true)"
  printf 'git-common-dir: %s\n' "$(git_common_abs 2>/dev/null || true)"
  # Additive line ONLY (existing fields above are unchanged/unreordered — bash readers
  # depend on them). Surfaces the explicitly-set mode, distinct from the derived class.
  printf 'explicit-mode: %s\n' "$(explicit_mode_for "$top")"
}

slugify() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's#[^a-z0-9._/-]+#-#g; s#/#-#g; s#^-+|-+$##g'
}

origin_owner_repo() {
  local url rest
  url="$(git config --get remote.origin.url 2>/dev/null || true)"
  case "$url" in
    *github.com[:/]*)
      rest="${url#*github.com}"
      rest="${rest#[:/]}"
      rest="${rest%.git}"
      printf '%s' "$rest" | awk -F/ 'NF>=2{print $1"/"$2; exit}'
      ;;
  esac
}

ensure_worktree() {
  local base="HEAD" branch="" path="" json=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --base) shift; base="${1:?--base requires a ref}" ;;
      --branch) shift; branch="${1:?--branch requires a name}" ;;
      --path) shift; path="${1:?--path requires a path}" ;;
      --json) json=1 ;;
      *) die "unknown ensure option: $1" ;;
    esac
    shift
  done

  local top class reason repo slug ts status_out
  top="$(top_level)" || die "not a git repository"
  IFS=$'\t' read -r class reason < <(classify_repo)
  # Eligible to create/adopt a Safe Workspace: `include` (ON) OR `ask_on` (ASK_ON). The
  # nudge is coherent for ASK_ON too (guard asks -> ensure gives a place to work); ASK_ON
  # is NOT setup-exec eligible (run_worktree_setup keeps its `include`-only gate).
  if [ "$class" != "include" ] && [ "$class" != "ask_on" ]; then
    if [ "$json" -eq 1 ]; then
      printf '{"action":"noop","classification":"%s","reason":"%s"}\n' "$class" "$(printf '%s' "$reason" | json_escape)"
    else
      note "no-op: $class — $reason"
    fi
    return 0
  fi
  if is_linked_worktree; then
    if [ "$json" -eq 1 ]; then
      printf '{"action":"noop","classification":"%s","reason":"already in linked worktree","root":"%s"}\n' "$(printf '%s' "$class" | json_escape)" "$(printf '%s' "$top" | json_escape)"
    else
      note "already in linked worktree: $top"
    fi
    return 0
  fi
  status_out="$(git status --porcelain 2>/dev/null || true)"
  if [ -n "$status_out" ] && [ "${DEV_WORKTREE_ALLOW_DIRTY:-0}" != "1" ]; then
    die "primary tree has uncommitted changes; commit/stash or set DEV_WORKTREE_ALLOW_DIRTY=1"
  fi

  repo="$(basename "$top")"
  ts="$(date -u +%Y%m%d%H%M%S)"
  slug="$(slugify "$repo-$ts")"
  [ -n "$branch" ] || branch="$DEFAULT_BRANCH_PREFIX/$slug"
  [ -n "$path" ] || path="$MANAGED_LOCATION/$(slugify "$repo")/$slug"
  mkdir -p "$(dirname "$path")"

  if [ -e "$path" ]; then
    die "target worktree path already exists: $path"
  fi
  if git show-ref --verify --quiet "refs/heads/$branch"; then
    die "branch already exists: $branch"
  fi

  if [ "$json" -eq 1 ]; then
    git worktree add -q -b "$branch" "$path" "$base"
  else
    git worktree add -b "$branch" "$path" "$base"
  fi
  set +e
  run_worktree_setup "$top" "$path"
  local setup_rc=$?
  set -e
  if [ "$setup_rc" -ne 0 ]; then
    local guidance
    guidance="Setup failed after creating the worktree. Inspect the setup stderr, fix the cause, then either run setup again from the worktree root or remove the disposable worktree with: git worktree remove \"$path\""
    if [ "$json" -eq 1 ]; then
      printf '{"action":"setup_failed","rootPath":"%s","branch":"%s","guidance":"%s"}\n' \
        "$(printf '%s' "$path" | json_escape)" \
        "$(printf '%s' "$branch" | json_escape)" \
        "$(printf '%s' "$guidance" | json_escape)"
    else
      note "setup failed after creating worktree: $path" >&2
      note "branch: $branch" >&2
      note "$guidance" >&2
    fi
    return "$setup_rc"
  fi

  if [ "$json" -eq 1 ]; then
    printf '{"action":"created","rootPath":"%s","branch":"%s","move_agent_to_root":{"rootPath":"%s"}}\n' \
      "$(printf '%s' "$path" | json_escape)" "$(printf '%s' "$branch" | json_escape)" "$(printf '%s' "$path" | json_escape)"
  else
    note "created worktree: $path"
    note "branch: $branch"
    printf '\nNEXT: call cursor-app-control move_agent_to_root with:\n'
    printf '  {"rootPath":"%s"}\n' "$path"
  fi
}

run_worktree_setup() {
  local root="$1" wt="$2" cfg
  cfg=""
  if [ -f "$root/.cursor/worktrees.json" ]; then
    cfg="$root/.cursor/worktrees.json"
  elif [ -f "$wt/.cursor/worktrees.json" ]; then
    cfg="$wt/.cursor/worktrees.json"
  fi
  [ -n "$cfg" ] || return 0

  # H3 (SECURITY / RCE-worm mitigation): $cfg is REPO-CONTROLLED and can run arbitrary commands
  # (incl. shell=True). Executing it on every `ensure` turns any cloned repo into remote code
  # execution, amplified once AWA is shared. So it is OFF BY DEFAULT and only runs under an
  # explicit, OUT-OF-REPO, per-repo opt-in that RE-ARMS when the committed config changes.
  local class reason
  IFS=$'\t' read -r class reason < <(classify_repo)
  if [ "$class" != "include" ]; then
    note "repo-controlled setup config present but repo is '$class' — refusing to execute (H3)" >&2
    return 0
  fi
  local repo_key confighash allow_dir allow_file
  repo_key="$(origin_owner_repo || true)"; [ -n "$repo_key" ] || repo_key="$(basename "$root")"
  repo_key="$(slugify "$repo_key")"
  confighash="$(shasum -a 256 "$cfg" 2>/dev/null | awk '{print $1}')"
  [ -n "$confighash" ] || confighash="$(cksum "$cfg" 2>/dev/null | awk '{print $1"-"$2}')"
  allow_dir="${XDG_CONFIG_HOME:-$HOME/.config}/awa/setup-allow"
  allow_file="$allow_dir/${repo_key}.${confighash}"
  if [ "${DEV_WORKTREE_SETUP_OPT_IN:-0}" = "1" ]; then
    mkdir -p "$allow_dir" 2>/dev/null && : > "$allow_file" 2>/dev/null || true
  fi
  if [ ! -f "$allow_file" ]; then
    note "repo-controlled setup config present but NOT allow-listed for this repo (default-off, H3)." >&2
    note "It executes repo-committed commands. To opt in for THIS repo + THIS config:" >&2
    note "  mkdir -p \"$allow_dir\" && touch \"$allow_file\"" >&2
    note "(re-armed automatically: editing the committed setup config invalidates the approval)" >&2
    return 0
  fi
  note "repo-controlled setup config is operator-allow-listed for this repo+config — executing (H3 opt-in)" >&2
  python3 - "$cfg" "$root" "$wt" <<'PY'
import json, os, pathlib, shlex, subprocess, sys
cfg, root, wt = sys.argv[1:4]
timeout = float(os.environ.get("DEV_WORKTREE_SETUP_TIMEOUT", "300"))
data = json.load(open(cfg))
key = "setup-worktree-unix" if os.name != "nt" and "setup-worktree-unix" in data else "setup-worktree"
cmds = data.get(key)
if not cmds:
    sys.exit(0)
env = os.environ.copy()
env["ROOT_WORKTREE_PATH"] = root

def fail(message: str) -> None:
    print(f"dev-worktree setup: {message}", file=sys.stderr)
    sys.exit(1)

def argv_from_string(command: str) -> list[str]:
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        fail(f"could not parse setup command {command!r}: {exc}")
    if not argv:
        fail("empty setup command")
    first = pathlib.Path(argv[0])
    if not first.is_absolute() and "/" not in argv[0] and (pathlib.Path(wt) / argv[0]).exists():
        argv[0] = f"./{argv[0]}"
    return argv

def command_entries(value):
    if isinstance(value, (str, dict)):
        return [value]
    if isinstance(value, list):
        return value
    fail(f"unsupported {key} value in {cfg}; use a string, list, or explicit shell object")

def normalize(entry):
    if isinstance(entry, str):
        return {"argv": argv_from_string(entry), "shell": False}
    if isinstance(entry, list) and all(isinstance(part, str) for part in entry):
        if not entry:
            fail("empty setup argv entry")
        return {"argv": entry, "shell": False}
    if isinstance(entry, dict):
        if "shell" in entry:
            shell_cmd = entry.get("shell")
            if entry.get("allowShell") is True and isinstance(shell_cmd, str) and shell_cmd.strip():
                return {"argv": shell_cmd, "shell": True}
            fail("setup shell object requires {'shell': '...', 'allowShell': true}")
        if "argv" in entry and isinstance(entry["argv"], list) and all(isinstance(part, str) for part in entry["argv"]):
            if not entry["argv"]:
                fail("empty setup argv object")
            return {"argv": entry["argv"], "shell": False}
        fail("unsupported setup object; use a string, argv list, or {'shell': '...', 'allowShell': true}")
    fail(f"unsupported setup command entry {entry!r}")

for raw in command_entries(cmds):
    spec = normalize(raw)
    try:
        proc = subprocess.run(
            spec["argv"],
            cwd=wt,
            env=env,
            shell=spec["shell"],
            text=True,
            stdout=sys.stderr,
            stderr=sys.stderr,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        fail(f"setup command timed out after {timeout:g}s: {spec['argv']!r}")
    except OSError as exc:
        fail(f"could not execute setup command {spec['argv']!r}: {exc}")
    if proc.returncode != 0:
        fail(f"setup command failed with exit {proc.returncode}: {spec['argv']!r}")
PY
}

list_worktrees() {
  top_level >/dev/null || die "not a git repository"
  git worktree list --porcelain
}

branch_ref_points_at() {
  local common_dir="$1" branch="$2" head="$3" current
  current="$(git --git-dir="$common_dir" rev-parse -q --verify "refs/heads/$branch" 2>/dev/null || true)"
  [ "$current" = "$head" ]
}

branch_is_cleanup_safe() {
  local path="$1" branch="$2" head="$3" upstream remotes
  if git -C "$path" show-ref --verify --quiet refs/heads/main &&
     git -C "$path" merge-base --is-ancestor "$head" refs/heads/main 2>/dev/null; then
    printf 'merged into local main'
    return 0
  fi
  if git -C "$path" show-ref --verify --quiet refs/remotes/origin/main &&
     git -C "$path" merge-base --is-ancestor "$head" refs/remotes/origin/main 2>/dev/null; then
    printf 'merged into origin/main'
    return 0
  fi
  upstream="$(git -C "$path" rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null || true)"
  if [ -n "$upstream" ] && git -C "$path" merge-base --is-ancestor "$head" "$upstream" 2>/dev/null; then
    printf 'present in upstream %s' "$upstream"
    return 0
  fi
  remotes="$(git -C "$path" branch -r --contains "$head" 2>/dev/null | sed 's/^[*[:space:]]*//' | grep -v ' -> ' || true)"
  if [ -n "$remotes" ]; then
    printf 'present on remote branch %s' "$(printf '%s\n' "$remotes" | paste -sd, -)"
    return 0
  fi
  return 1
}

print_clean_recovery() {
  local path="$1" branch="$2" head="$3"
  cat >&2 <<EOF
$SELF_NAME: refusing to remove worktree with local-only commits
  path:   $path
  branch: $branch
  HEAD:   $head

Next actions:
  1. Inspect unshared commits: git -C "$path" log --oneline --decorate --not main --not --remotes
  2. Preserve them:          git -C "$path" push -u origin "$branch"
  3. Retry cleanup:          $SELF_NAME clean --path "$path"

Use --delete-branch only after those commits are preserved or intentionally disposable.
EOF
}

# X3/S1: bundle ignored (git-ignored) files to the durable recovery dir before a worktree is
# removed, so `git worktree remove` can never silently delete local .env / *.db / build output.
# Secret-pattern files are EXCLUDED from the archive by default (S1: "refused or redacted") and
# recorded in the manifest as skipped; set AWA_BUNDLE_ALLOW_SECRETS=1 to include them deliberately.
awa_bundle_ignored() {
  local path="$1" ignored_nl="$2" repo_slug ts dest manifest
  repo_slug="$(slugify "$(basename "$path")")"
  repo_slug="$(printf '%s' "$repo_slug" | sed -E 's#^\.+##')"
  [ -n "$repo_slug" ] || repo_slug="worktree"
  ts="$(date -u +%Y%m%d%H%M%S)"
  mkdir -p "$AWA_RECOVERY_DIR" 2>/dev/null || { die "cannot create recovery dir: $AWA_RECOVERY_DIR"; }
  chmod 700 "$AWA_RECOVERY_DIR" 2>/dev/null || true
  dest="$AWA_RECOVERY_DIR/${repo_slug}-${ts}.tar.gz"
  manifest="$AWA_RECOVERY_DIR/${repo_slug}-${ts}.manifest.json"
  AWA_SRC="$path" AWA_DEST="$dest" AWA_MANIFEST="$manifest" \
  AWA_ALLOW_SECRETS="${AWA_BUNDLE_ALLOW_SECRETS:-0}" IGNORED_NL="$ignored_nl" \
  python3 - <<'PY'
import json, os, re, subprocess, sys
src = os.environ["AWA_SRC"]; dest = os.environ["AWA_DEST"]; manifest = os.environ["AWA_MANIFEST"]
allow_secrets = os.environ.get("AWA_ALLOW_SECRETS") == "1"
entries = [e for e in os.environ["IGNORED_NL"].splitlines() if e.strip()]
SECRET = re.compile(r'(\.env$|\.env\.|\.(pem|key|p12|pfx|keystore|jks)$|(^|/)(id_rsa|id_ed25519)|credential|secret|token|\.netrc$|\.npmrc$)', re.I)
src_real = os.path.realpath(src)
included, skipped, skipped_symlink = [], [], []
for e in entries:
    real = os.path.realpath(os.path.join(src, e))
    if real != src_real and not real.startswith(src_real + os.sep):
        skipped_symlink.append(e); continue
    (skipped if (SECRET.search(e) and not allow_secrets) else included).append(e)
os.makedirs(os.path.dirname(dest), exist_ok=True)
if included:
    listfile = dest + ".list"
    with open(listfile, "w", encoding="utf-8") as fh:
        fh.write("\n".join(included) + "\n")
    rc = subprocess.run(["tar", "-czf", dest, "-C", src, "-T", listfile]).returncode
    os.remove(listfile)
    if rc != 0:
        print(f"dev-worktree: tar failed ({rc}) creating {dest}", file=sys.stderr); sys.exit(1)
else:
    open(dest, "wb").close()
with open(manifest, "w", encoding="utf-8") as fh:
    json.dump({"source": src, "archive": dest, "included": included,
               "skipped_secrets": skipped, "skipped_symlink_escape": skipped_symlink,
               "allow_secrets": allow_secrets}, fh, indent=2)
print(dest)
if skipped:
    print("dev-worktree: NOT archived (secret-pattern; set AWA_BUNDLE_ALLOW_SECRETS=1 to include):", file=sys.stderr)
    for s in skipped:
        print(f"    {s}", file=sys.stderr)
if skipped_symlink:
    print("dev-worktree: NOT archived (S2 symlink escaping worktree root):", file=sys.stderr)
    for s in skipped_symlink:
        print(f"    {s}", file=sys.stderr)
PY
}

clean_worktree() {
  local path="" force=0 delete_branch=0 bundle=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --path) shift; path="${1:?--path requires a path}" ;;
      --force) force=1 ;;
      --bundle) bundle=1 ;;
      --delete-branch) delete_branch=1 ;;
      *) die "unknown clean option: $1" ;;
    esac
    shift
  done
  [ -n "$path" ] || die "clean requires --path"
  # S2 (symlink-traversal guard): reject a symlinked worktree path, then canonicalize.
  if [ -L "$path" ]; then
    die "refusing symlinked worktree path (S2 symlink-traversal guard): $path"
  fi
  [ -d "$path" ] || die "not a directory: $path"
  path="$(cd "$path" 2>/dev/null && pwd -P)" || die "cannot canonicalize worktree path: $path"
  local dirty branch head git_dir common_dir safe_reason ignored
  dirty="$(git -C "$path" status --porcelain 2>/dev/null || true)"
  [ -z "$dirty" ] || die "refusing to remove dirty worktree: $path"
  branch="$(git -C "$path" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  [ -n "$branch" ] || die "cannot determine worktree branch: $path"
  [ "$branch" != "HEAD" ] || die "refusing to remove detached-HEAD worktree: $path"
  head="$(git -C "$path" rev-parse HEAD 2>/dev/null)" || die "cannot determine HEAD for $path"
  git_dir="$(git -C "$path" rev-parse --path-format=absolute --git-dir 2>/dev/null)" || die "cannot determine git-dir for $path"
  common_dir="$(git -C "$path" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" || die "cannot determine git common-dir for $path"
  safe_reason="$(branch_is_cleanup_safe "$path" "$branch" "$head" || true)"
  if [ -z "$safe_reason" ]; then
    print_clean_recovery "$path" "$branch" "$head"
    return 1
  fi

  # X3: `git status --porcelain` does NOT list git-ignored files, so `git worktree remove` would
  # delete local .env / *.db / build output with no recovery. Bundle-or-refuse before removal.
  ignored="$(git -C "$path" -c core.untrackedCache=false -c core.fsmonitor=false \
    status --porcelain --ignored=matching --untracked-files=all 2>/dev/null | sed -n 's/^!! //p' || true)"
  if [ -n "$ignored" ]; then
    if [ "$bundle" -eq 1 ]; then
      local archive
      archive="$(awa_bundle_ignored "$path" "$ignored")" || return 1
      note "bundled git-ignored files to recovery archive before removal: $archive"
    elif [ "$force" -eq 1 ]; then
      note "WARNING: --force discarding git-ignored files without a recovery bundle:" >&2
      printf '    %s\n' $ignored >&2
    else
      {
        printf '%s: refusing to remove worktree with git-ignored local files\n' "$SELF_NAME"
        printf '  path: %s\n' "$path"
        printf '  ignored (would be permanently deleted):\n'
        printf '    %s\n' $ignored
        printf '\nNext actions:\n'
        printf '  1. Preserve them:  %s clean --path "%s" --bundle\n' "$SELF_NAME" "$path"
        printf '  2. Or discard:     %s clean --path "%s" --force\n' "$SELF_NAME" "$path"
      } >&2
      return 1
    fi
  fi
  note "clean safety captured: path=$path branch=$branch head=${head:0:12} git-dir=$git_dir git-common-dir=$common_dir safe=$safe_reason"
  if [ "$force" -eq 1 ]; then
    git --git-dir="$common_dir" worktree remove --force "$path"
  else
    git --git-dir="$common_dir" worktree remove "$path"
  fi
  if [ "$delete_branch" -eq 1 ]; then
    if branch_ref_points_at "$common_dir" "$branch" "$head"; then
      git --git-dir="$common_dir" branch -D "$branch"
    else
      die "branch $branch no longer points at captured HEAD $head; leaving branch in place"
    fi
  else
    note "removed worktree; left branch '$branch' in place (rerun with --delete-branch to delete after safety checks)"
  fi
}

doctor() {
  policy_check
  printf '\n== current repo ==\n'
  current_state
  if top_level >/dev/null 2>&1; then
    printf '\n== worktrees ==\n'
    list_worktrees
  fi
}

dashboard_data() {
  # Thin, READ-ONLY delegation to the source-tracked generic emitter. It never mutates a
  # repo; it only walks governed repos and prints awa-worktree/v1 JSON that the status
  # canvas consumes (see the dashboard installer).
  local emitter="$AWA_HOME/dashboard/emitter.py"
  [ -f "$emitter" ] || die "missing dashboard emitter: $emitter"
  python3 "$emitter" "$@"
}

policy_check() {
  [ -f "$POLICY" ] || die "missing policy: $POLICY"
  python3 - "$POLICY" "$KERNEL_DIR/lib" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1])
sys.path.insert(0, sys.argv[2])
text = p.read_text()
required = ["version:", "governed_roots:", "managed_location:", "default:", "include:", "exclude:", "detectors:", "overrides:"]
missing = [k for k in required if k not in text]
if missing:
    raise SystemExit(f"policy missing keys: {', '.join(missing)}")
print(f"policy: {p}")

# Additive per-repo MODE validation (schema awa-modes/v1). Validate `modes:` /
# `default_mode:` when present — inline OR via a `modes_file:` pointer — parsed with the
# SAME kernel loader the classifier uses. Absence is valid (these are NOT required keys).
# Invalid entries WARN only; they NEVER hard-fail (back-compat: only missing required
# keys fail policy-check).
warnings = []
try:
    import awa_policy
    data = awa_policy.parse_mini_yaml(text)
    if any(k in data for k in ("modes", "default_mode", "modes_file")):
        modes, default_mode = awa_policy._resolve_modes(data, str(p))
        allowed = "|".join(awa_policy.MODE_VALUES)
        if default_mode not in awa_policy.MODE_VALUES:
            warnings.append(f"default_mode '{default_mode}' is not one of {allowed}")
        for key, val in modes.items():
            if not str(key).strip():
                warnings.append("empty modes key")
            if val not in awa_policy.MODE_VALUES:
                warnings.append(f"mode for '{key}': '{val}' is not one of {allowed}")
except Exception as exc:  # noqa: BLE001 — additive check never hard-fails
    warnings.append(f"mode-config check skipped: {exc}")

for w in warnings:
    print(f"policy-check: WARN {w}", file=sys.stderr)
print("policy-check: OK")
PY
}

# Additive `mode` verb: pass-through to the engine's tool-owned modes-file manager
# (engine/modes.py via `python3 -m engine mode ...`). ZERO-LINK: the modes-file PATH is
# resolved by the engine from the SAME host policy this script already uses ($POLICY);
# this script carries no org/host literals. Verbs: list|get|set|remove|repair|sync.
run_engine() {
  local launcher="$AWA_HOME/bin/awa-engine.sh"
  if [ -x "$launcher" ]; then
    "$launcher" "$@"
  else
    PYTHONPATH="$AWA_HOME${PYTHONPATH:+:$PYTHONPATH}" python3 -m engine "$@"
  fi
}

mode_verb() {
  # Default --policy to the resolved host policy; a caller-supplied --policy/--modes-file
  # later on the line still wins (argparse: last value for a repeated option).
  run_engine mode --policy "$POLICY" "$@"
}

verb="${1:-}"
case "$verb" in
  status) shift; current_state "$@" ;;
  ensure) shift; ensure_worktree "$@" ;;
  list) shift; list_worktrees "$@" ;;
  clean) shift; clean_worktree "$@" ;;
  doctor) shift; doctor "$@" ;;
  policy-check) shift; policy_check "$@" ;;
  dashboard-data) shift; dashboard_data "$@" ;;
  mode) shift; mode_verb "$@" ;;
  -h|--help|help|"") usage ;;
  *) die "unknown verb: $verb" ;;
esac
