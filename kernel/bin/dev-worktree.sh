#!/usr/bin/env bash
# dev-worktree.sh — policy-driven helper for agent worktree isolation (AWA kernel).
#
# The script intentionally owns only git/worktree mechanics. `ensure` records
# metadata-only handoff intent, then tells the operator how to open the target
# through Cursor's Agents Window. It never claims relocation or session success.
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
# K1: canonical per-root disposition + heartbeat + clean-receipt writer (kernel-owned, stdlib
# only; holds engine/router-off). The SINGLE SOURCE OF TRUTH for a root's disposition and for
# the clean_receipt/v1 written on EVERY terminal `clean` path.
# Env-overridable so an operator/harness can point at a co-located copy; its ABSENCE is treated
# as fail-CLOSED by the active-root gate (a corrupt install must not silently disable protection).
AWA_ROOTS_LIB="${AWA_ROOTS_LIB:-$KERNEL_DIR/lib/awa_roots.py}"
# Root-bound finish core (kernel-owned, stdlib-only; holds engine/router-off). Drives the
# deterministic inventory/fingerprint/challenge/authorize/lock/branch-disposition primitives for
# `clean --finish-current`. Its ABSENCE is fail-CLOSED on the finish path (refuse, never remove).
# Export AWA_ROOTS_LIB so the finish lib loads the SAME sibling awa_roots.py this script uses.
AWA_FINISH_LIB="${AWA_FINISH_LIB:-$KERNEL_DIR/lib/awa_finish.py}"
# Narrow validator/remover for engine-authored `.awa/lease.json`. Ordinary clean may tolerate this
# one in-worktree file only when the helper proves the private directory contains no other content
# and the lease identity matches the live worktree path + branch + common dir.
AWA_BOOKKEEPING_LIB="$KERNEL_DIR/lib/awa_bookkeeping.py"
AWA_HANDOFF_LIB="${AWA_HANDOFF_LIB:-$KERNEL_DIR/lib/awa_handoff.py}"
export AWA_ROOTS_LIB

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
  mode list                      list all explicit entries + default_mode
  mode get <rel>                 show the explicit entry (exact key) for a repo path/glob
  mode set <rel> <on|off>        set an explicit mode (on = protected; off = disabled)
  mode remove <rel>              remove an explicit mode entry (idempotent)
  mode repair                    normalize the file's own contents: coerce invalid values to on,
                                 drop unsafe/empty keys, normalize default_mode (idempotent;
                                 requires an existing file; no filesystem scan)
  mode sync [--default-mode M]   ensure-exists + normalize the file (creates it if absent;
                                 preserves entries + a valid default_mode; no filesystem scan)
  (accepts --policy P / --modes-file F; defaults to the resolved host policy)
  Note: sync/repair do NOT scan the filesystem, materialize per-repo entries, or prune stale
  repos — the runtime default_mode is what protects new eligible repos.

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
  --expected-branch NAME
  --expected-head SHA
  --expected-common-dir PATH
                    optional all-or-none identity guard; rechecked under the existing
                    common-dir lock immediately before ordinary clean removal

  --finish-current       finish (discard + remove) the CURRENT linked worktree (takes NO --path;
                         the target is the physical current dir, which must be a linked worktree).
                         The flag alone is NOT authorization — see --preview / --authorization.
  --preview              (with --finish-current) READ-ONLY: render the inventory of work that a
                         discard would destroy + create a pending challenge; performs NO mutation.
  --authorization ANS    (with --finish-current) consume the pending challenge and remove ONLY when
                         ANS is the exact literal 'Close' AND the re-derived full or path-granularity
                         structural fingerprint byte-equals the challenge. Also accepted via
                         AWA_FINISH_AUTHORIZATION.
  --conversation-id ID   (with --finish-current) stable id keying the pending challenge across the
                         preview->authorize round-trip (default: AWA_FINISH_CONVERSATION_ID /
                         DEV_SESSION_ID / 'cli').
  --expected-nonce ID    (with --finish-current) hook dispatcher binding for the selected challenge.
  --expected-generation N
                         (with --finish-current) hook dispatcher generation binding. Hook-mode Close
                         requires both exact values; direct Phase-1 preview/Close remains compatible
                         without either flag.

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
  # FAIL-SAFE: a classifier crash must NOT degrade to a non-protective class. `advisory`
  # makes the guard ALLOW a mutating command on an included primary checkout (silent
  # host-wide fail-open, since ~/dev wires modes_file by default). Fall back to `include`
  # so the guard ASKS (fail safe = ask, never silently allow).
  python3 "$AWA_POLICY_LIB" classify --policy "$POLICY" \
    --governed-root "${AWA_GOVERNED_ROOT:-}" \
    --toplevel "$top" --hooks-path "$hp" --has-origin "$has_origin" 2>/dev/null \
    || printf 'include\tclassifier unavailable (fail-safe: ask)\t%s\t\n' "$(basename "$top")"
}

# Back-compat 2-field verdict (class<TAB>reason) for callers that only need the decision.
classify_repo() {
  classify_context | cut -f1,2
}

# Resolve the EXPLICIT per-repo mode (on|off|invalid|(none)) via the generic
# `mode-for` CLI — the SAME kernel resolver + host policy the classifier uses (zero-link;
# inline/file modes and defaults all come from the host policy). Empty output (no exact or
# matching glob entry) is surfaced as `(none)`. This is a READ; it never mutates anything.
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
  # HOT-PATH: computing it spawns a SECOND python3 (`mode-for`). The beforeShellExecution
  # guard never reads this line, so it exports AWA_STATUS_NO_MODE=1 to keep the pre-mutation
  # gate single-spawn. Interactive `status` (env unset/0) still prints the line.
  if [ "${AWA_STATUS_NO_MODE:-0}" != "1" ]; then
    printf 'explicit-mode: %s\n' "$(explicit_mode_for "$top")"
  fi
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
  # Eligible to create/adopt a Safe Workspace: `include` (ON = protected). The guard denies a
  # mutating command on an included primary, so `ensure` gives a Safe Workspace to work in.
  # exclude/advisory are not eligible (run_worktree_setup keeps its `include`-only gate).
  if [ "$class" != "include" ]; then
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
  path="$(cd "$path" && pwd -P)" || die "created worktree identity is unavailable"
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

  # M2.4 entry handoff: publish intent only after the exact created target and
  # Git identity exist. The authority owns schema validation, private modes,
  # its dedicated lock, monotonic generations, and the atomic durable replace.
  # If intent cannot be recorded, do not print guidance that implies a usable
  # handoff; preserve the created worktree for explicit operator inspection.
  if [ ! -f "$AWA_HANDOFF_LIB" ] || [ ! -r "$AWA_HANDOFF_LIB" ] || \
     ! python3 "$AWA_HANDOFF_LIB" create --root "$path" >/dev/null; then
    die "worktree created but handoff intent could not be recorded; inspect and preserve: $path"
  fi

  if [ "$json" -eq 1 ]; then
    printf '{"action":"created","rootPath":"%s","branch":"%s","handoff":"pending"}\n' \
      "$(printf '%s' "$path" | json_escape)" "$(printf '%s' "$branch" | json_escape)"
  else
    note "created worktree: $path"
    note "branch: $branch"
    printf '\nNEXT: open a new Cursor Agents Window session with Worktree selected:\n'
    printf '  %s\n' "$path"
    printf 'The new session will validate and close this pending handoff intent.\n'
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
  local path="$1" branch="$2" head="$3" upstream remotes ref cherry
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
  # Squash-merge detection: every branch commit is already present upstream by PATCH-ID
  # (survives squash). Hardened so it can NEVER mark genuinely-unshared work safe.
  for ref in refs/heads/main refs/remotes/origin/main; do
    git -C "$path" show-ref --verify --quiet "$ref" || continue
    if [ "$(git -C "$path" rev-list --merges --count "$ref..$head" 2>/dev/null || echo 1)" != "0" ]; then
      continue
    fi
    cherry="$(git -C "$path" cherry "$ref" "$head" 2>/dev/null || true)"
    [ -n "$cherry" ] || continue
    if ! printf '%s\n' "$cherry" | grep -q '^+'; then
      printf 'patch-equivalent already in %s (squash-merged)' "${ref##*/}"
      return 0
    fi
  done
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
  4. If squash-merged:       git -C "$path" fetch origin && $SELF_NAME clean --path "$path"
                             (local main or origin/main must include the squash commit)

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
import hashlib, json, os, re, subprocess, sys, time
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
# Unified recovery-artifact manifest (awa_recovery_artifact/v1): the SAME shape the engine writers
# emit, so kernel bundles participate directly in the engine's retention lifecycle (TTL/pressure)
# without a legacy-normalization guess. Kernel-first: computed with the stdlib only, zero network.
_h = hashlib.sha256()
with open(dest, "rb") as _fh:
    for _chunk in iter(lambda: _fh.read(1024 * 1024), b""):
        _h.update(_chunk)
_epoch = int(time.time())
with open(manifest, "w", encoding="utf-8") as fh:
    json.dump({"schema": "awa_recovery_artifact/v1",
               "artifact_id": "bundle-" + os.urandom(16).hex(),
               "kind": "bundle", "protected": False,
               "source": src, "archive": dest, "archive_name": os.path.basename(dest),
               "size": os.path.getsize(dest), "sha256": _h.hexdigest(),
               "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(_epoch)),
               "created_at_epoch": _epoch,
               "included": included,
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

# --- K1 clean receipts + active-root disposition (kernel-owned; holds engine/router-off) ---
# A durable clean_receipt/v1 is written on EVERY terminal `clean` path (removed / refused /
# error). The receipt context is defaulted to a FAIL-SAFE REFUSAL, so ANY unclassified exit
# (a new path a future edit forgets to classify, an unexpected error) records a refusal —
# never a silent success. An EXIT trap armed for the clean verb guarantees exactly one receipt
# is emitted regardless of how clean_worktree returns/dies.
_CLEAN_RECEIPT_WRITTEN=0
_CLEAN_DISPOSITION="refused"
_CLEAN_REASON="unattributed_exit"
_CLEAN_MESSAGE="clean exited without classifying a disposition (fail-safe refusal receipt)"
_CLEAN_PATH=""
_CLEAN_BRANCH=""
_CLEAN_HEAD=""
_CLEAN_COMMON_DIR=""
_CLEAN_BUNDLE=0
_CLEAN_FORCE=0
_CLEAN_DELETE_BRANCH=0
_CLEAN_IGNORED_PRESENT=0
_CLEAN_IGNORED_COUNT=0
_CLEAN_SAFE_REASON=""
_CLEAN_ARCHIVE=""
_CLEAN_ROOT_DISPOSITION=""
_CLEAN_ROOT_DISPOSITION_REASON=""
# Additive-within-v1 finish receipt fields (populated only on the `clean --finish-current` path;
# left empty on the ordinary `clean --path` path so existing receipts are unchanged).
_CLEAN_FINISH_CURRENT=0
_CLEAN_AUTH_NONCE=""
_CLEAN_DISCARD_COUNT=0
_CLEAN_BRANCH_ACTION=""
_CLEAN_CHALLENGE_FP=""
_CLEAN_OPERATION_ID=""
# A removed finish whose kernel receipt is not yet durable must leave its operation journal as the
# sole recovery authority; the generic EXIT receipt writer must not mint a premature identity.
_CLEAN_FINISH_RECEIPT_DEFERRED=0
# MINOR #5: set when the receipt (audit record) could NOT be written, so the failure surfaces as
# a non-zero audit exit status instead of being swallowed.
_CLEAN_RECEIPT_ERROR=0

clean_set_disposition() {
  _CLEAN_DISPOSITION="$1"; _CLEAN_REASON="$2"; _CLEAN_MESSAGE="$3"
}

# MINOR #5: a real receipt-write failure (disk-full / perms / py-error) MUST NOT be swallowed.
# Capture the rc, emit a stderr breadcrumb, and record an audit-error flag (surfaced as a
# non-zero exit by the EXIT trap). A missing kernel lib is likewise breadcrumbed (we cannot write
# a receipt when the writer itself is gone).
emit_clean_receipt() {
  [ "$_CLEAN_RECEIPT_WRITTEN" = "1" ] && return 0
  _CLEAN_RECEIPT_WRITTEN=1
  [ "$_CLEAN_FINISH_RECEIPT_DEFERRED" = "1" ] && return 0
  if [ ! -f "$AWA_ROOTS_LIB" ]; then
    _CLEAN_RECEIPT_ERROR=1
    printf '%s: WARNING: cannot write clean receipt — kernel lib missing: %s\n' \
      "$SELF_NAME" "$AWA_ROOTS_LIB" >&2
    return 0
  fi
  local out rc
  # set +e around the capture: under `set -e` a failing command substitution would abort the
  # trap itself (swallowing exactly the failure we must surface). We capture the rc explicitly.
  set +e
  out="$(python3 "$AWA_ROOTS_LIB" write-receipt \
    --disposition "$_CLEAN_DISPOSITION" --reason "$_CLEAN_REASON" --message "$_CLEAN_MESSAGE" \
    --path "$_CLEAN_PATH" --branch "$_CLEAN_BRANCH" --head "$_CLEAN_HEAD" \
    --common-dir "$_CLEAN_COMMON_DIR" --bundle "$_CLEAN_BUNDLE" --force "$_CLEAN_FORCE" \
    --delete-branch "$_CLEAN_DELETE_BRANCH" --ignored-present "$_CLEAN_IGNORED_PRESENT" \
    --ignored-count "$_CLEAN_IGNORED_COUNT" --safe-reason "$_CLEAN_SAFE_REASON" \
    --archive "$_CLEAN_ARCHIVE" --root-disposition "$_CLEAN_ROOT_DISPOSITION" \
    --root-disposition-reason "$_CLEAN_ROOT_DISPOSITION_REASON" \
    --finish-current "$_CLEAN_FINISH_CURRENT" --authorization-nonce "$_CLEAN_AUTH_NONCE" \
    --discard-count "$_CLEAN_DISCARD_COUNT" --branch-action "$_CLEAN_BRANCH_ACTION" \
    --challenge-fingerprint "$_CLEAN_CHALLENGE_FP" --operation-id "$_CLEAN_OPERATION_ID" 2>&1)"
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    _CLEAN_RECEIPT_ERROR=1
    printf '%s: WARNING: clean receipt write FAILED (rc=%s): %s\n' "$SELF_NAME" "$rc" "$out" >&2
  fi
  return 0
}

# EXIT-trap backstop: fires on `die` (exit), `return`, or normal completion. Preserves the
# original exit status. This is what makes "a receipt on every terminal clean path" structural
# rather than a per-path discipline a future edit can forget. MINOR #5: if the audit receipt
# could not be written on an OTHERWISE-successful clean, surface it as a distinct non-zero
# audit status (3) rather than reporting a clean success with no durable record.
_clean_exit_trap() {
  local rc=$?
  emit_clean_receipt
  if [ "$_CLEAN_RECEIPT_ERROR" = "1" ] && [ "$rc" -eq 0 ]; then
    printf '%s: clean completed but its audit receipt could not be written (see WARNING above)\n' \
      "$SELF_NAME" >&2
    rc=3
  fi
  exit "$rc"
}

# K1 + fail-CLOSED hardening: per-root active_root/v1 disposition gate. Canonical disposition is
# kernel/lib/awa_roots.py (the SINGLE source of truth). An ACTIVE root (a live session's Safe
# Workspace) BLOCKS removal; STALE/UNTRACKED/DEAD/ABSENT proceed to the content-safety checks.
# Returns non-zero to block. Every UNCERTAIN outcome fails CLOSED (refuse), never open:
#   * lib missing            -> refused/roots_lib_missing            (MINOR #4)
#   * gate tool empty/nonzero-> refused/disposition_unavailable      (BLOCKER #1)
#   * disposition == active  -> refused/active_root | reactivated_during_clean (MAJOR #2 phase)
# An operator `--force` overrides ONLY a fail-safe/unavailable active (unknown evidence, NOT
# backed by a live pid); a genuine fresh-heartbeat or live-pid active is NEVER force-removable
# (MINOR #7). phase=pre (initial gate) or phase=recheck (TOCTOU re-read immediately before remove).
clean_active_root_gate() {
  local path="$1" phase="${2:-pre}" line="" rc=0
  local disp="" reason="" failsafe="0" pidbacked="0" recpresent="0"
  # MINOR #4: the kernel lib is co-located with this script; its ABSENCE is a corrupt install.
  # For the active-root gate that is fail-CLOSED (refuse), never protection-silently-off.
  if [ ! -f "$AWA_ROOTS_LIB" ]; then
    if [ "$_CLEAN_FORCE" = "1" ]; then
      _CLEAN_ROOT_DISPOSITION="unavailable"
      _CLEAN_ROOT_DISPOSITION_REASON="roots_lib_missing_forced"
      printf '%s: WARNING: active-root gate lib missing (%s) — --force overriding (operator ack)\n' \
        "$SELF_NAME" "$AWA_ROOTS_LIB" >&2
      return 0
    fi
    _CLEAN_ROOT_DISPOSITION="unavailable"
    _CLEAN_ROOT_DISPOSITION_REASON="roots_lib_missing"
    clean_set_disposition refused roots_lib_missing \
      "active-root gate unavailable (kernel lib missing: $AWA_ROOTS_LIB) — fail-closed refusal"
    {
      printf '%s: refusing to remove — the active-root safety gate is unavailable\n' "$SELF_NAME"
      printf '  path:   %s\n' "$path"
      printf '  reason: kernel lib missing (%s)\n' "$AWA_ROOTS_LIB"
      printf '\nThis is a corrupt/incomplete AWA install. Reinstall AWA, or (only if you accept the\n'
      printf 'risk of removing a possibly-active workspace) rerun with --force.\n'
    } >&2
    return 1
  fi
  # One canonical gate line: disposition<TAB>reason<TAB>failsafe<TAB>pid_backed<TAB>record.
  line="$(python3 "$AWA_ROOTS_LIB" gate --root "$path" 2>/dev/null)"; rc=$?
  if [ "$rc" -ne 0 ] || [ -z "$line" ]; then
    # BLOCKER #1: the canonical disposition could not be computed. UNKNOWN evidence about whether
    # a live session is using this workspace MUST block the destructive action (fail CLOSED),
    # mirroring classify_context's fail-to-include. NEVER `return 0` here.
    if [ "$_CLEAN_FORCE" = "1" ]; then
      _CLEAN_ROOT_DISPOSITION="unavailable"
      _CLEAN_ROOT_DISPOSITION_REASON="disposition_unavailable_forced"
      printf '%s: WARNING: canonical disposition unavailable (rc=%s) — --force overriding (operator ack)\n' \
        "$SELF_NAME" "$rc" >&2
      return 0
    fi
    _CLEAN_ROOT_DISPOSITION="unavailable"
    _CLEAN_ROOT_DISPOSITION_REASON="disposition_unavailable(rc=$rc)"
    clean_set_disposition refused disposition_unavailable \
      "canonical disposition unavailable (gate rc=$rc, empty output) — fail-closed refusal (unknown evidence blocks removal)"
    {
      printf '%s: refusing to remove — could not determine if a live session is using this workspace\n' "$SELF_NAME"
      printf '  path: %s\n' "$path"
      printf '  reason: canonical disposition tool failed (rc=%s)\n' "$rc"
      printf '\nUnknown evidence blocks a destructive action. Fix the AWA install, or (only if you\n'
      printf 'accept the risk) rerun with --force to override.\n'
    } >&2
    return 1
  fi
  IFS=$'\t' read -r disp reason failsafe pidbacked recpresent <<EOF
$line
EOF
  _CLEAN_ROOT_DISPOSITION="$disp"
  _CLEAN_ROOT_DISPOSITION_REASON="$reason"
  if [ "$disp" = "active" ]; then
    # MINOR #7: an operator --force may override ONLY a fail-safe active (unknown evidence:
    # corrupt/unparseable record) that is NOT backed by a live pid. A genuine fresh heartbeat
    # or a live-pid owner is never force-removable — the operator must close/park the session
    # (or, if they are certain it is dead, `awa_roots.py forget --root <path>`).
    if [ "$_CLEAN_FORCE" = "1" ] && [ "$failsafe" = "1" ] && [ "$pidbacked" != "1" ]; then
      _CLEAN_ROOT_DISPOSITION_REASON="forced_over_failsafe_active:$reason"
      printf '%s: WARNING: --force overriding a FAIL-SAFE active record (unknown evidence, no live pid): %s\n' \
        "$SELF_NAME" "$reason" >&2
      return 0
    fi
    # Literal reason codes (the receipt-coverage meta-test locks the authored reason_code set).
    if [ "$phase" = "recheck" ]; then
      clean_set_disposition refused reactivated_during_clean \
        "root RE-ACTIVATED during clean (a live session started using it mid-operation): $reason"
    else
      clean_set_disposition refused active_root \
        "refusing to remove an ACTIVE Safe Workspace (a live session is using it): $reason"
    fi
    {
      printf '%s: %s\n' "$SELF_NAME" "$_CLEAN_MESSAGE"
      printf '  path:   %s\n' "$path"
      printf '  reason: %s\n' "$reason"
      printf '\nClose/park that session first; once its heartbeat expires (TTL) or its owning\n'
      printf 'process exits, the workspace becomes removable. If you are CERTAIN it is dead, clear\n'
      printf 'its record: python3 "%s" forget --root "%s"\n' "$AWA_ROOTS_LIB" "$path"
    } >&2
    return 1
  fi
  return 0
}

# Extract a single scalar key from a finish JSON blob on stdin (tabs/newlines flattened so the
# value is safe to store in a shell var). Missing key -> the supplied default.
_finish_json_get() {
  local json="$1" key="$2" def="${3:-}"
  printf '%s' "$json" | python3 -c '
import json, sys
key, default = sys.argv[1], sys.argv[2]
try:
    d = json.load(sys.stdin)
    v = d.get(key, default)
except Exception:
    v = default
print(str(v).replace("\t", " ").replace("\n", " "))
' "$key" "$def" 2>/dev/null || printf '%s' "$def"
}

# Machine-facing finish output is a closed projection. It never copies the kernel message, reason,
# paths, object ids, hashes, or extra child JSON. Human CLI output remains unchanged unless the
# consumer explicitly requests this mode.
_finish_emit_public_projection() {
  [ "${AWA_FINISH_PUBLIC_PROJECTION:-0}" = "1" ] || return 1
  local outcome="$1" branch_action="${2:-}"
  case "$outcome" in
    removed)
      case "$branch_action" in
        retained|retained_local_only|deleted)
          printf '{"outcome":"removed","reason":"finish_removed","branch_action":"%s"}\n' \
            "$branch_action"
          ;;
        *)
          printf '{"outcome":"uncertain","reason":"removal_uncertain"}\n'
          ;;
      esac
      ;;
    uncertain)
      printf '{"outcome":"uncertain","reason":"removal_uncertain"}\n'
      ;;
    *)
      printf '{"outcome":"refused","reason":"workspace_preserved"}\n'
      ;;
  esac
  return 0
}

# clean --finish-current: discard + remove the CURRENT linked worktree. The kernel refusal is the
# ENTIRE safety guarantee in Phase 1 — removal happens ONLY when awa_finish.py, under the shared
# per-common-dir lock, re-derives a full or path-granularity structural fingerprint that byte-equals
# the matching pending challenge proof AND the authorization is the exact literal 'Close'. The flag
# is NOT authorization. Any uncertainty PRESERVES the worktree with a precise receipt. Uses
# finish_session_gate (inside finish-execute), NOT the ordinary active-root gate, so the confirming
# session's own heartbeat does not self-block.
clean_finish_current() {
  local preview="$1" have_auth="$2" authorization="$3" conversation_id="$4" path_given="$5"
  local expected_nonce="$6" expected_generation="$7"
  _CLEAN_FINISH_CURRENT=1
  _CLEAN_ROOT_DISPOSITION="finish"

  # --finish-current takes NO --path (the target is the physical current dir) and --preview /
  # --authorization are meaningful ONLY here.
  if [ -n "$path_given" ]; then
    clean_set_disposition refused finish_bad_args "clean --finish-current takes no --path (target is the current worktree)"
    die "clean --finish-current takes no --path"
  fi
  if { [ -n "$expected_nonce" ] && [ -z "$expected_generation" ]; } || \
     { [ -z "$expected_nonce" ] && [ -n "$expected_generation" ]; }; then
    clean_set_disposition refused finish_bad_args \
      "--expected-nonce and --expected-generation must be supplied together"
    die "--expected-nonce and --expected-generation must be supplied together"
  fi

  # Fail-CLOSED if either kernel lib is missing (a corrupt install must never silently disable
  # the finish safety gate).
  if [ ! -f "$AWA_FINISH_LIB" ] || [ ! -f "$AWA_ROOTS_LIB" ]; then
    clean_set_disposition refused finish_lib_missing "AWA finish kernel lib missing ($AWA_FINISH_LIB) — fail-closed refusal"
    die "AWA finish kernel lib missing: $AWA_FINISH_LIB"
  fi

  # Target resolution is delegated to the stdlib finish kernel from the FIRST Git probe. It strips
  # every inherited GIT_* selector/config/object variable, validates the linked-worktree
  # administration files, binds the real worktree/index, and repeats the identity probes through
  # that exact binding. Any mismatch/spoof -> refuse.
  local here branch head git_dir common_dir target_json target_rc
  here="$(pwd -P 2>/dev/null)" || { clean_set_disposition error finish_error "cannot resolve current directory"; die "cannot resolve current directory"; }
  _CLEAN_PATH="$here"
  set +e
  target_json="$(python3 "$AWA_FINISH_LIB" resolve-target --root "$here" 2>/dev/null)"
  target_rc=$?
  set -e
  if [ "$target_rc" -ne 0 ] || [ -z "$target_json" ]; then
    clean_set_disposition refused finish_not_linked \
      "current directory is not one exactly bound linked worktree"
    die "current directory is not one exactly bound linked worktree"
  fi
  git_dir="$(_finish_json_get "$target_json" git_dir '')"
  common_dir="$(_finish_json_get "$target_json" common_dir '')"
  branch="$(_finish_json_get "$target_json" branch '')"
  head="$(_finish_json_get "$target_json" head '')"
  if [ -z "$git_dir" ] || [ -z "$common_dir" ] || [ -z "$branch" ] || [ -z "$head" ]; then
    clean_set_disposition refused finish_not_linked \
      "linked-worktree target identity is incomplete"
    die "linked-worktree target identity is incomplete"
  fi
  _CLEAN_BRANCH="$branch"; _CLEAN_HEAD="$head"; _CLEAN_COMMON_DIR="$common_dir"

  [ -n "$conversation_id" ] || conversation_id="${AWA_FINISH_CONVERSATION_ID:-${DEV_SESSION_ID:-cli}}"
  local session_id="${DEV_SESSION_ID:-}"

  # ---- READ-ONLY preview: inventory + fingerprint + pending challenge, no mutation ----
  if [ "$preview" -eq 1 ]; then
    local out rc rows
    set +e
    out="$(python3 "$AWA_FINISH_LIB" preview --root "$here" --git-dir "$git_dir" \
      --common-dir "$common_dir" --branch "$branch" --head "$head" \
      --session-id "$session_id" --conversation-id "$conversation_id" 2>/dev/null)"
    rc=$?
    set -e
    if [ "$rc" -ne 0 ] || [ -z "$out" ]; then
      clean_set_disposition refused finish_inventory_unsafe \
        "finish preview refused: $(_finish_json_get "$out" reason inventory_unsafe)"
      note "finish preview refused (inventory unsafe or unreadable)" >&2
      return 1
    fi
    _CLEAN_CHALLENGE_FP="$(_finish_json_get "$out" fingerprint '')"
    _CLEAN_DISCARD_COUNT="$(_finish_json_get "$out" discard_count 0)"
    rows="$(printf '%s' "$out" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("rows",""))' 2>/dev/null || true)"
    printf 'AWA finish preview — the following local work would be permanently discarded:\n\n'
    printf '%s\n\n' "$rows"
    printf 'To CONFIRM removal, re-run with the exact authorization word:\n'
    printf '  %s clean --finish-current --authorization Close\n' "$SELF_NAME"
    printf 'To CANCEL, do nothing (this preview performed no changes).\n'
    clean_set_disposition refused finish_preview "finish preview rendered; pending challenge created (no removal performed)"
    return 0
  fi

  # ---- EXECUTE: the flag is NOT authorization; an explicit literal 'Close' is required ----
  if [ "$have_auth" -ne 1 ] && [ -n "${AWA_FINISH_AUTHORIZATION+set}" ]; then
    authorization="${AWA_FINISH_AUTHORIZATION}"; have_auth=1
  fi
  if [ "$have_auth" -ne 1 ]; then
    clean_set_disposition refused finish_no_authorization \
      "finish requires an explicit authorization (the literal 'Close'); the flag alone is not authorization"
    {
      printf '%s: refusing to finish — no authorization provided\n' "$SELF_NAME"
      printf '  Run a preview first:  %s clean --finish-current --preview\n' "$SELF_NAME"
      printf '  Then confirm:         %s clean --finish-current --authorization Close\n' "$SELF_NAME"
    } >&2
    return 1
  fi

  # CWD SAFETY: the removal unlinks this dir; move to a surviving dir so the EXIT-trap receipt
  # writer (and any child) can still fork/exec after the worktree is gone.
  local safe_cwd
  safe_cwd="$(dirname "$common_dir")"
  [ -d "$safe_cwd" ] || safe_cwd="/"
  cd "$safe_cwd" 2>/dev/null || cd / 2>/dev/null || true

  local out rc outcome receipt_code message receipt_committed
  set +e
  if [ -n "$expected_nonce" ] && [ -n "$expected_generation" ]; then
    out="$(python3 "$AWA_FINISH_LIB" finish-execute --root "$here" --git-dir "$git_dir" \
      --common-dir "$common_dir" --branch "$branch" --head "$head" \
      --session-id "$session_id" --conversation-id "$conversation_id" \
      --answer "$authorization" --expected-nonce "$expected_nonce" \
      --expected-generation "$expected_generation" 2>/dev/null)"
  else
    out="$(python3 "$AWA_FINISH_LIB" finish-execute --root "$here" --git-dir "$git_dir" \
      --common-dir "$common_dir" --branch "$branch" --head "$head" \
      --session-id "$session_id" --conversation-id "$conversation_id" \
      --answer "$authorization" 2>/dev/null)"
  fi
  rc=$?
  set -e
  # A child can disappear after Git has removed the worktree, or can truthfully report an
  # uncertified post-removal namespace/state write. Reconcile in a fresh process immediately so the
  # shell never narrates that removed root as present and never trusts in-process visibility.
  if [ -z "$out" ] || [ -z "$(_finish_json_get "$out" outcome '')" ] || \
     [ "$(_finish_json_get "$out" outcome '')" = "uncertain" ]; then
    local recovered
    set +e
    if [ -n "$expected_nonce" ] && [ -n "$expected_generation" ]; then
      recovered="$(python3 "$AWA_FINISH_LIB" finish-reconcile --root "$here" --git-dir "$git_dir" \
        --common-dir "$common_dir" --branch "$branch" --head "$head" \
        --session-id "$session_id" --conversation-id "$conversation_id" \
        --expected-nonce "$expected_nonce" --expected-generation "$expected_generation" \
        2>/dev/null)"
    else
      recovered="$(python3 "$AWA_FINISH_LIB" finish-reconcile --root "$here" --git-dir "$git_dir" \
        --common-dir "$common_dir" --branch "$branch" --head "$head" \
        --session-id "$session_id" --conversation-id "$conversation_id" 2>/dev/null)"
    fi
    rc=$?
    set -e
    out="$recovered"
    if [ -z "$out" ]; then
      clean_set_disposition error finish_error \
        "finish removal outcome could not be reconciled (rc=$rc) — fail-safe uncertainty"
      return 1
    fi
  fi
  # A valid removed result can still report that its operation-bound receipt was deferred because
  # the removed/branch state write failed. Retry reconciliation in a fresh kernel process before
  # narration; never let the generic EXIT writer race ahead of the journal's durable branch result.
  outcome="$(_finish_json_get "$out" outcome refused)"
  receipt_committed="$(_finish_json_get "$out" receipt_committed false)"
  if [ "$outcome" = "removed" ] && [ "$receipt_committed" != "True" ]; then
    local recovered
    set +e
    if [ -n "$expected_nonce" ] && [ -n "$expected_generation" ]; then
      recovered="$(python3 "$AWA_FINISH_LIB" finish-reconcile --root "$here" --git-dir "$git_dir" \
        --common-dir "$common_dir" --branch "$branch" --head "$head" \
        --session-id "$session_id" --conversation-id "$conversation_id" \
        --expected-nonce "$expected_nonce" --expected-generation "$expected_generation" \
        2>/dev/null)"
    else
      recovered="$(python3 "$AWA_FINISH_LIB" finish-reconcile --root "$here" --git-dir "$git_dir" \
        --common-dir "$common_dir" --branch "$branch" --head "$head" \
        --session-id "$session_id" --conversation-id "$conversation_id" 2>/dev/null)"
    fi
    rc=$?
    set -e
    if [ -n "$recovered" ] && \
       [ "$(_finish_json_get "$recovered" outcome '')" = "removed" ]; then
      out="$recovered"
    fi
  fi
  outcome="$(_finish_json_get "$out" outcome refused)"
  receipt_committed="$(_finish_json_get "$out" receipt_committed false)"
  receipt_code="$(_finish_json_get "$out" receipt_code finish_error)"
  message="$(_finish_json_get "$out" message 'finish-execute did not report a message')"
  _CLEAN_BRANCH_ACTION="$(_finish_json_get "$out" branch_action '')"
  _CLEAN_DISCARD_COUNT="$(_finish_json_get "$out" discard_count 0)"
  _CLEAN_AUTH_NONCE="$(_finish_json_get "$out" authorization_nonce '')"
  _CLEAN_CHALLENGE_FP="$(_finish_json_get "$out" challenge_fingerprint '')"
  _CLEAN_OPERATION_ID=""
  if [ "$outcome" = "removed" ]; then
    _CLEAN_OPERATION_ID="$(_finish_json_get "$out" operation_id '')"
  fi
  if [ "$outcome" = "removed" ] && [ "$receipt_committed" != "True" ]; then
    _CLEAN_FINISH_RECEIPT_DEFERRED=1
  fi
  if [ "$outcome" = "uncertain" ]; then
    clean_set_disposition error finish_error "finish removal outcome is uncertain: $message"
    if ! _finish_emit_public_projection uncertain; then
      note "finish removal outcome is uncertain: $message" >&2
    fi
    return 1
  fi

  # Map the bounded receipt_code to a LITERAL clean_set_disposition call (the receipt-coverage
  # meta-test locks the authored disposition/reason universe; Python remains the decision authority).
  case "$receipt_code" in
    finish_removed)              clean_set_disposition removed finish_removed "$message" ;;
    finish_not_close)            clean_set_disposition refused finish_not_close "$message" ;;
    finish_no_challenge)         clean_set_disposition refused finish_no_challenge "$message" ;;
    finish_fingerprint_mismatch) clean_set_disposition refused finish_fingerprint_mismatch "$message" ;;
    finish_target_mismatch)      clean_set_disposition refused finish_target_mismatch "$message" ;;
    finish_session_blocked)      clean_set_disposition refused finish_session_blocked "$message" ;;
    finish_recheck_failed)       clean_set_disposition refused finish_recheck_failed "$message" ;;
    finish_inventory_unsafe)     clean_set_disposition refused finish_inventory_unsafe "$message" ;;
    finish_lock_busy)            clean_set_disposition refused finish_lock_busy "$message" ;;
    finish_remove_failed)        clean_set_disposition error finish_remove_failed "$message" ;;
    *)                           clean_set_disposition error finish_error "$message" ;;
  esac
  if [ "$outcome" = "removed" ]; then
    if ! _finish_emit_public_projection removed "$_CLEAN_BRANCH_ACTION"; then
      note "$message"
    fi
    return 0
  fi
  if ! _finish_emit_public_projection refused; then
    note "$message" >&2
  fi
  return 1
}

clean_worktree() {
  # Arm the receipt backstop FIRST so even an early arg-parse exit records a receipt.
  trap '_clean_exit_trap' EXIT
  local path="" force=0 delete_branch=0 bundle=0
  local finish_current=0 preview=0 authorization="" conversation_id="" have_auth=0
  local expected_nonce="" expected_generation=""
  local expected_clean_branch="" expected_clean_head="" expected_clean_common_dir=""
  while [ $# -gt 0 ]; do
    case "$1" in
      --path) shift; path="${1:?--path requires a path}" ;;
      --force) force=1 ;;
      --bundle) bundle=1 ;;
      --delete-branch) delete_branch=1 ;;
      --expected-branch) shift; expected_clean_branch="${1:?--expected-branch requires a value}" ;;
      --expected-head) shift; expected_clean_head="${1:?--expected-head requires a value}" ;;
      --expected-common-dir) shift; expected_clean_common_dir="${1:?--expected-common-dir requires a value}" ;;
      --finish-current) finish_current=1 ;;
      --preview) preview=1 ;;
      --authorization) shift; authorization="${1?--authorization requires a value}"; have_auth=1 ;;
      --conversation-id) shift; conversation_id="${1?--conversation-id requires a value}" ;;
      --expected-nonce) shift; expected_nonce="${1?--expected-nonce requires a value}" ;;
      --expected-generation) shift; expected_generation="${1?--expected-generation requires a value}" ;;
      *) clean_set_disposition refused unknown_option "unknown clean option: $1"; die "unknown clean option: $1" ;;
    esac
    shift
  done
  _CLEAN_BUNDLE="$bundle"; _CLEAN_FORCE="$force"; _CLEAN_DELETE_BRANCH="$delete_branch"

  # Route the root-bound finish path separately from the ordinary `clean --path` lifecycle flow.
  if [ "$finish_current" -eq 1 ]; then
    if [ -n "$expected_clean_branch" ] || [ -n "$expected_clean_head" ] || \
       [ -n "$expected_clean_common_dir" ]; then
      clean_set_disposition refused finish_bad_args \
        "--expected-branch/--expected-head/--expected-common-dir apply only to ordinary clean --path"
      die "--expected-branch/--expected-head/--expected-common-dir require ordinary clean --path"
    fi
    clean_finish_current "$preview" "$have_auth" "$authorization" "$conversation_id" "$path" \
      "$expected_nonce" "$expected_generation"
    return $?
  fi
  # --preview / --authorization / --conversation-id are meaningful ONLY with --finish-current.
  if [ "$preview" -eq 1 ] || [ "$have_auth" -eq 1 ] || [ -n "$conversation_id" ] || \
     [ -n "$expected_nonce" ] || [ -n "$expected_generation" ]; then
    clean_set_disposition refused finish_bad_args \
      "--preview/--authorization/--conversation-id/--expected-* require --finish-current"
    die "--preview/--authorization/--conversation-id/--expected-* require --finish-current"
  fi
  local expected_clean_count=0
  [ -n "$expected_clean_branch" ] && expected_clean_count=$((expected_clean_count + 1))
  [ -n "$expected_clean_head" ] && expected_clean_count=$((expected_clean_count + 1))
  [ -n "$expected_clean_common_dir" ] && expected_clean_count=$((expected_clean_count + 1))
  if [ "$expected_clean_count" -ne 0 ] && [ "$expected_clean_count" -ne 3 ]; then
    clean_set_disposition refused expected_identity_mismatch \
      "ordinary clean expected identity must supply branch, HEAD, and common-dir together"
    die "--expected-branch/--expected-head/--expected-common-dir must be supplied together"
  fi

  _CLEAN_PATH="$path"
  if [ -z "$path" ]; then
    clean_set_disposition refused missing_path "clean requires --path"
    die "clean requires --path"
  fi
  # S2 (symlink-traversal guard): reject a symlinked worktree path, then canonicalize.
  if [ -L "$path" ]; then
    clean_set_disposition refused symlinked_path "refusing symlinked worktree path (S2 symlink-traversal guard): $path"
    die "refusing symlinked worktree path (S2 symlink-traversal guard): $path"
  fi
  if [ ! -d "$path" ]; then
    clean_set_disposition refused not_a_directory "not a directory: $path"
    die "not a directory: $path"
  fi
  path="$(cd "$path" 2>/dev/null && pwd -P)" || {
    clean_set_disposition error canonicalize_failed "cannot canonicalize worktree path"
    die "cannot canonicalize worktree path: $path"
  }
  _CLEAN_PATH="$path"
  local dirty dirty_rc branch head git_dir common_dir safe_reason ignored ignored_rc _lockfile=""
  local tracked_awa tracked_awa_rc owned_awa=0 status_line dirty_without_owned
  branch="$(git -C "$path" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  if [ -z "$branch" ]; then
    clean_set_disposition error no_branch "cannot determine worktree branch: $path"
    die "cannot determine worktree branch: $path"
  fi
  _CLEAN_BRANCH="$branch"
  if [ "$branch" = "HEAD" ]; then
    clean_set_disposition refused detached_head "refusing to remove detached-HEAD worktree: $path"
    die "refusing to remove detached-HEAD worktree: $path"
  fi
  head="$(git -C "$path" rev-parse HEAD 2>/dev/null)" || {
    clean_set_disposition error no_head "cannot determine HEAD for $path"
    die "cannot determine HEAD for $path"
  }
  _CLEAN_HEAD="$head"
  git_dir="$(git -C "$path" rev-parse --path-format=absolute --git-dir 2>/dev/null)" || {
    clean_set_disposition error no_git_dir "cannot determine git-dir for $path"
    die "cannot determine git-dir for $path"
  }
  common_dir="$(git -C "$path" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" || {
    clean_set_disposition error no_common_dir "cannot determine git common-dir for $path"
    die "cannot determine git common-dir for $path"
  }
  _CLEAN_COMMON_DIR="$common_dir"

  # Adoption writes `.awa/lease.json` inside the worktree. That file is AWA's own lifecycle
  # bookkeeping, not operator work, but it may be tolerated only under a deliberately narrow proof:
  # no tracked `.awa` path; exactly one private, regular file; valid lease contract + identity bound
  # to this live path/branch/common-dir. Any missing helper, malformed/mismatched lease, symlink,
  # permission drift, or sibling content falls through to the ordinary dirty/ignored gates.
  set +e
  tracked_awa="$(git -C "$path" ls-files -- .awa 2>/dev/null)"
  tracked_awa_rc=$?
  set -e
  if [ "$tracked_awa_rc" -eq 0 ] && [ -z "$tracked_awa" ] && \
     [ -f "$AWA_BOOKKEEPING_LIB" ] && \
     python3 "$AWA_BOOKKEEPING_LIB" validate --root "$path" --branch "$branch" \
       --common-dir "$common_dir" >/dev/null 2>&1; then
    owned_awa=1
  fi

  set +e
  dirty="$(git -C "$path" -c core.untrackedCache=false -c core.fsmonitor=false \
    status --porcelain=v1 --untracked-files=all 2>/dev/null)"
  dirty_rc=$?
  set -e
  if [ "$dirty_rc" -ne 0 ]; then
    clean_set_disposition refused dirty "refusing to remove worktree whose dirty state cannot be read: $path"
    die "refusing to remove worktree whose dirty state cannot be read: $path"
  fi
  if [ "$owned_awa" -eq 1 ]; then
    dirty_without_owned=""
    while IFS= read -r status_line; do
      [ "$status_line" = "?? .awa/lease.json" ] && continue
      [ -z "$status_line" ] && continue
      dirty_without_owned="${dirty_without_owned}${dirty_without_owned:+$'\n'}${status_line}"
    done <<< "$dirty"
    dirty="$dirty_without_owned"
  fi
  if [ -n "$dirty" ]; then
    clean_set_disposition refused dirty "refusing to remove dirty worktree: $path"
    die "refusing to remove dirty worktree: $path"
  fi

  # K1: an ACTIVE root (a live session's Safe Workspace) blocks removal (canonical disposition).
  clean_active_root_gate "$path" || return 1

  safe_reason="$(branch_is_cleanup_safe "$path" "$branch" "$head" || true)"
  if [ -z "$safe_reason" ]; then
    clean_set_disposition refused local_only_commits "local-only commits (not merged/pushed) — preserve first"
    print_clean_recovery "$path" "$branch" "$head"
    return 1
  fi
  _CLEAN_SAFE_REASON="$safe_reason"

  # X3 + "ignored-files-are-child-state" + "unknown-evidence-blocks": `git status --porcelain`
  # does NOT list git-ignored files, so `git worktree remove` would delete local .env / *.db /
  # build output with no recovery. Git-ignored files are CHILD STATE (not safe-to-delete):
  # bundle-or-refuse before removal. If the ignored-file scan itself FAILS, that is UNKNOWN
  # evidence about child state -> REFUSE (never proceed to remove on an unclassifiable tree).
  set +e
  ignored="$(git -C "$path" -c core.untrackedCache=false -c core.fsmonitor=false \
    status --porcelain --ignored=matching --untracked-files=all 2>/dev/null)"
  ignored_rc=$?
  set -e
  if [ "$ignored_rc" -ne 0 ]; then
    clean_set_disposition refused ignored_scan_failed "git-ignored-file scan failed (rc=$ignored_rc) — refusing on unknown child-state evidence"
    printf '%s: refusing to remove worktree — could not scan for git-ignored child state (rc=%s)\n' "$SELF_NAME" "$ignored_rc" >&2
    return 1
  fi
  ignored="$(printf '%s\n' "$ignored" | sed -n 's/^!! //p' || true)"
  if [ "$owned_awa" -eq 1 ]; then
    local ignored_without_owned="" ignored_path
    while IFS= read -r ignored_path; do
      case "$ignored_path" in
        .awa/|.awa/lease.json|"") continue ;;
      esac
      ignored_without_owned="${ignored_without_owned}${ignored_without_owned:+$'\n'}${ignored_path}"
    done <<< "$ignored"
    ignored="$ignored_without_owned"
  fi
  if [ -n "$ignored" ]; then
    _CLEAN_IGNORED_PRESENT=1
    _CLEAN_IGNORED_COUNT="$(printf '%s\n' "$ignored" | grep -c . || true)"
    if [ "$bundle" -eq 1 ]; then
      local archive
      archive="$(awa_bundle_ignored "$path" "$ignored")" || {
        clean_set_disposition error bundle_failed "bundling git-ignored child state failed"
        return 1
      }
      _CLEAN_ARCHIVE="$archive"
      note "bundled git-ignored files to recovery archive before removal: $archive"
    elif [ "$force" -eq 1 ]; then
      note "WARNING: --force discarding git-ignored files without a recovery bundle:" >&2
      printf '    %s\n' $ignored >&2
    else
      clean_set_disposition refused ignored_present "git-ignored local files present (child state) — bundle-or-refuse before removal"
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
  # ADDITIVE-WITHIN-v1 (Fix 3): hold the SHARED per-common-dir advisory lock across the ORDINARY
  # destructive section (TOCTOU disposition re-read + `git worktree remove` + branch-delete), the
  # SAME lock ABI kernel finish + engine maintenance use, so an ordinary clean serializes against a
  # concurrent finish/engine mutation on this git_common_dir. The lock is held on fd 9 (opened
  # here, kept open across the section; the flock persists because THIS shell keeps the fd open —
  # the standard flock(1) <fd> pattern) and released when this single-invocation process exits.
  # Uncontended acquisition is transparent (instant). On contention within the bounded timeout we
  # REFUSE fail-safe (clean_lock_busy) and preserve the worktree. Lock setup is part of destructive
  # authorization: a missing helper, failed/empty/unsafe lock path, open failure, or acquisition
  # failure can never degrade to an unlocked remove (including under --force).
  if [ ! -f "$AWA_FINISH_LIB" ]; then
    clean_set_disposition refused clean_lock_busy "finish lock helper unavailable — worktree preserved"
    die "refusing to remove worktree — finish lock helper unavailable"
  fi
  if ! _lockfile="$(python3 "$AWA_FINISH_LIB" lock-ensure \
      --common-dir "$common_dir" 2>/dev/null)"; then
    clean_set_disposition refused clean_lock_busy "per-common-dir lock setup failed — worktree preserved"
    die "refusing to remove worktree — per-common-dir lock setup failed"
  fi
  case "$_lockfile" in
    ""|*$'\n'*)
      clean_set_disposition refused clean_lock_busy "per-common-dir lock path invalid — worktree preserved"
      die "refusing to remove worktree — per-common-dir lock path invalid"
      ;;
  esac
  if [[ "$_lockfile" != /* ]] || [ ! -f "$_lockfile" ] || [ -L "$_lockfile" ] \
      || [ ! -r "$_lockfile" ] || [ ! -w "$_lockfile" ]; then
    clean_set_disposition refused clean_lock_busy "per-common-dir lock path unusable — worktree preserved"
    die "refusing to remove worktree — per-common-dir lock path unusable"
  fi
  if ! { exec 9<>"$_lockfile"; } 2>/dev/null; then
    clean_set_disposition refused clean_lock_busy "cannot open per-common-dir lockfile — worktree preserved"
    die "refusing to remove worktree — cannot open per-common-dir lockfile"
  fi
  if ! python3 "$AWA_FINISH_LIB" flock-fd --fd 9 \
      --timeout "${AWA_CLEAN_LOCK_TIMEOUT:-30}"; then
    exec 9>&-
    clean_set_disposition refused clean_lock_busy "per-common-dir lock busy or unavailable — worktree preserved"
    die "refusing to remove worktree — the per-common-dir lock is busy or unavailable"
  fi
  # MAJOR #2 (TOCTOU): the disposition read at the top ran BEFORE branch_is_cleanup_safe, the
  # git-ignored scan, and an optional --bundle tar (which can take minutes). RE-READ the canonical
  # disposition IMMEDIATELY before the destructive remove; if the root was re-activated in the
  # window, REFUSE (reason_code reactivated_during_clean). There is no OS lock (a deliberate
  # non-goal) — this shrinks the race window from minutes to ~microseconds, fail-closed.
  clean_active_root_gate "$path" recheck || return 1
  # M2.2 digest-bound repair hands its authorized branch/HEAD/common-dir identity to THIS
  # existing clean authority. Re-read all three while the ordinary clean common-dir lock is
  # held, immediately before any AWA bookkeeping unlink or `git worktree remove`. Existing
  # callers omit the optional all-or-none guard and retain byte-for-byte behavior.
  if [ "$expected_clean_count" -eq 3 ]; then
    local recheck_branch="" recheck_head="" recheck_common_dir=""
    local expected_common_canonical="" recheck_common_canonical=""
    recheck_branch="$(git -C "$path" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
    recheck_head="$(git -C "$path" rev-parse HEAD 2>/dev/null || true)"
    recheck_common_dir="$(git -C "$path" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
    # Use the same physical-directory canonicalization primitive as clean's target path.
    # This treats aliases such as /var and /private/var as one identity without accepting
    # an absent or genuinely different common directory.
    expected_common_canonical="$(cd "$expected_clean_common_dir" 2>/dev/null && pwd -P || true)"
    recheck_common_canonical="$(cd "$recheck_common_dir" 2>/dev/null && pwd -P || true)"
    if [ -z "$recheck_branch" ] || [ -z "$recheck_head" ] || [ -z "$recheck_common_dir" ] || \
       [ -z "$expected_common_canonical" ] || [ -z "$recheck_common_canonical" ] || \
       [ "$recheck_branch" != "$expected_clean_branch" ] || \
       [ "$recheck_head" != "$expected_clean_head" ] || \
       [ "$recheck_common_canonical" != "$expected_common_canonical" ]; then
      clean_set_disposition refused expected_identity_mismatch \
        "expected identity changed before removal — worktree preserved"
      die "refusing to remove worktree — expected identity changed before removal"
    fi
  fi
  # Remove only the already-proven AWA lease, under the shared lifecycle lock, and revalidate it in
  # the helper immediately before unlink. The helper uses a no-follow directory fd and unlinks only
  # `lease.json`; it deliberately leaves the now-empty `.awa/` directory for Git to remove with the
  # worktree. If anything changed since classification, preserve the worktree.
  if [ "$owned_awa" -eq 1 ]; then
    if [ ! -f "$AWA_BOOKKEEPING_LIB" ] || \
       ! python3 "$AWA_BOOKKEEPING_LIB" remove --root "$path" --branch "$branch" \
         --common-dir "$common_dir" >/dev/null 2>&1; then
      clean_set_disposition refused dirty \
        "AWA-owned bookkeeping changed before removal — worktree preserved"
      die "refusing to remove worktree — AWA-owned bookkeeping changed"
    fi
    set +e
    dirty="$(git -C "$path" -c core.untrackedCache=false -c core.fsmonitor=false \
      status --porcelain=v1 --untracked-files=all 2>/dev/null)"
    dirty_rc=$?
    set -e
    if [ "$dirty_rc" -ne 0 ] || [ -n "$dirty" ]; then
      clean_set_disposition refused dirty \
        "worktree changed after AWA bookkeeping removal — worktree preserved"
      die "refusing to remove worktree — dirty state changed before removal"
    fi
  fi
  if [ "$force" -eq 1 ]; then
    git --git-dir="$common_dir" worktree remove --force "$path"
  else
    git --git-dir="$common_dir" worktree remove "$path"
  fi
  # The worktree is now gone; drop any active_root heartbeat record so a removed root never
  # lingers as a phantom 'dead' record (best-effort; never fails the clean).
  [ -f "$AWA_ROOTS_LIB" ] && python3 "$AWA_ROOTS_LIB" remove-root --root "$path" >/dev/null 2>&1 || true
  if [ "$delete_branch" -eq 1 ]; then
    if git --git-dir="$common_dir" update-ref -d "refs/heads/$branch" "$head" 2>/dev/null; then
      clean_set_disposition removed removed_with_branch "removed worktree and deleted branch '$branch' at ${head:0:12} (safe: $safe_reason)"
      note "deleted branch '$branch' at $head (atomic update-ref)"
    else
      clean_set_disposition error branch_moved "branch $branch no longer points at captured HEAD $head; leaving branch in place"
      die "branch $branch no longer points at captured HEAD $head; leaving branch in place"
    fi
  else
    clean_set_disposition removed removed_kept_branch "removed worktree; left branch '$branch' in place (safe: $safe_reason)"
    note "removed worktree; left branch '$branch' in place (rerun with --delete-branch to delete after safety checks)"
  fi
}

hook_owner_role_matrix() {
  python3 - "$AWA_HOME/contracts/awa-contract.v1.json" \
    "$AWA_HOME/contracts/awa-hook-owner.v2.json" \
    "$AWA_HOME/contracts/awa-hook-owner.v3.json" <<'PY'
import json
import os
import stat
import sys
from pathlib import Path

V1_IDS = (
    "worktree.session-context",
    "worktree.shell-guard",
    "worktree.file-observer",
    "recovery.maintenance",
    "finish.prompt-recall",
)
V2_LAYOUT = (
    (
        "worktree.shell-guard-composite",
        "beforeShellExecution",
        "kernel/hooks/worktree-guard-with-integrity.sh",
        "host-policy-delegator",
        {"type": "command", "timeout": 20, "failClosed": False},
        None,
    ),
    (
        "worktree.stop-observer",
        "stop",
        "kernel/hooks/awa-integrity-observer.sh",
        "host-policy-delegator",
        {"type": "command", "timeout": 5, "failClosed": False},
        None,
    ),
    (
        "worktree.session-handoff",
        "sessionStart",
        "kernel/hooks/awa-session-handoff.sh",
        "host-policy-delegator",
        {"type": "command", "timeout": 5, "failClosed": False},
        "M2.4",
    ),
)
V3_LAYOUT = (
    (
        "finish.prompt-recall-with-entry",
        "before" + "SubmitPrompt",
        "kernel/hooks/before-submit-prompt-with-entry.sh",
        "host-policy-delegator",
        {
            "type": "command",
            "matcher": "UserPromptSubmit",
            "timeout": 20,
            "failClosed": False,
        },
        None,
    ),
)


def fail(contract):
    print("== hook-owner role matrix ==")
    print(f"  FAIL  {contract} contract invalid")
    raise SystemExit(1)


def load(path, contract):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        fail(contract)
    if not isinstance(value, dict):
        fail(contract)
    return value


def valid_entry(entry):
    if not isinstance(entry, dict):
        return False
    if entry.get("type") != "command":
        return False
    if type(entry.get("timeout")) is not int or entry["timeout"] <= 0:
        return False
    if "failClosed" in entry and type(entry["failClosed"]) is not bool:
        return False
    if "matcher" in entry and not isinstance(entry["matcher"], str):
        return False
    return "command" not in entry


def valid_role(role, *, allow_dormant):
    if not isinstance(role, dict):
        return False
    required = {
        "id",
        "event",
        "direct_command_role",
        "external_command_path_class",
        "entry",
    }
    allowed = required | ({"dormant_until_milestone"} if allow_dormant else set())
    if set(role) - allowed or not required.issubset(role):
        return False
    if not all(
        isinstance(role[key], str) and role[key]
        for key in (
            "id",
            "event",
            "direct_command_role",
            "external_command_path_class",
        )
    ):
        return False
    if role["external_command_path_class"] not in {
        "host-policy-delegator",
        "installed-awa",
    }:
        return False
    relative = Path(role["direct_command_role"])
    if relative.is_absolute() or ".." in relative.parts:
        return False
    command = (root / relative).resolve()
    try:
        command.relative_to(root)
    except ValueError:
        return False
    try:
        mode = command.lstat().st_mode
    except OSError:
        return False
    if (
        not stat.S_ISREG(mode)
        or mode & 0o111 == 0
        or not os.access(command, os.R_OK)
    ):
        return False
    if "dormant_until_milestone" in role and not isinstance(
        role["dormant_until_milestone"], str
    ):
        return False
    return valid_entry(role["entry"])


def roles_match(roles, layout):
    if not isinstance(roles, list) or len(roles) != len(layout):
        return False
    for role, expected in zip(roles, layout):
        if not isinstance(role, dict):
            return False
        observed = (
            role.get("id"),
            role.get("event"),
            role.get("direct_command_role"),
            role.get("external_command_path_class"),
            role.get("entry"),
            role.get("dormant_until_milestone"),
        )
        if observed != expected:
            return False
    return True


v1_path = Path(sys.argv[1])
v2_path = Path(sys.argv[2])
v3_path = Path(sys.argv[3])
root = v1_path.parent.parent.resolve()
v1_doc = load(v1_path, "hook-owner v1")
v1 = v1_doc.get("hook_ownership")
if (
    not isinstance(v1, dict)
    or v1.get("schema") != "awa-hook-owner/v1"
    or v1.get("modes") != ["direct", "external"]
    or v1.get("default_mode") != "direct"
    or v1.get("selection_env") != "AWA_HOOK_OWNER"
    or v1.get("selection_schema") != "awa-hook-owner-selection/v1"
    or v1.get("external_real_hook_file_writes") is not False
    or not isinstance(v1.get("roles"), list)
    or tuple(
        role.get("id") for role in v1["roles"] if isinstance(role, dict)
    )
    != V1_IDS
    or not all(valid_role(role, allow_dormant=False) for role in v1["roles"])
):
    fail("hook-owner v1")
roles = list(v1["roles"])
preferred = v1["schema"]
if v2_path.is_file():
    v2 = load(v2_path, "hook-owner v2")
    if (
        v2.get("schema") != "awa-hook-owner/v2"
        or v2.get("version") != 2
        or v2.get("successor_of") != "awa-hook-owner/v1"
        or v2.get("v1_contract")
        != "contracts/awa-contract.v1.json#hook_ownership"
        or v2.get("modes") != ["direct", "external"]
        or v2.get("default_mode") != "direct"
        or v2.get("selection_env") != "AWA_HOOK_OWNER"
        or v2.get("selection_schema") != "awa-hook-owner-selection/v1"
        or v2.get("external_real_hook_file_writes") is not False
        or v2.get("supersedes_roles") != ["worktree.shell-guard"]
        or not isinstance(v2.get("composition_rule"), str)
        or not v2["composition_rule"]
        or not isinstance(v2.get("external_rule"), str)
        or not v2["external_rule"]
        or not roles_match(v2.get("roles"), V2_LAYOUT)
        or not all(
            valid_role(role, allow_dormant=True)
            for role in v2.get("roles", [])
        )
    ):
        fail("hook-owner v2")
    superseded = set(v2["supersedes_roles"])
    roles = [role for role in roles if role["id"] not in superseded]
    roles.extend(v2["roles"])
    preferred = v2["schema"]

if v3_path.is_file():
    v3 = load(v3_path, "hook-owner v3")
    if (
        preferred != "awa-hook-owner/v2"
        or v3.get("schema") != "awa-hook-owner/v3"
        or v3.get("version") != 3
        or v3.get("successor_of") != "awa-hook-owner/v2"
        or v3.get("v2_contract") != "contracts/awa-hook-owner.v2.json"
        or v3.get("modes") != ["direct", "external"]
        or v3.get("default_mode") != "direct"
        or v3.get("selection_env") != "AWA_HOOK_OWNER"
        or v3.get("selection_schema") != "awa-hook-owner-selection/v1"
        or v3.get("external_real_hook_file_writes") is not False
        or v3.get("supersedes_roles") != ["finish.prompt-recall"]
        or not isinstance(v3.get("composition_rule"), str)
        or not v3["composition_rule"]
        or not isinstance(v3.get("external_rule"), str)
        or not v3["external_rule"]
        or not roles_match(v3.get("roles"), V3_LAYOUT)
        or not all(
            valid_role(role, allow_dormant=False)
            for role in v3.get("roles", [])
        )
    ):
        fail("hook-owner v3")
    superseded = set(v3["supersedes_roles"])
    roles = [role for role in roles if role["id"] not in superseded]
    roles.extend(v3["roles"])
    preferred = v3["schema"]

print("== hook-owner role matrix ==")
print(f"preferred: {preferred}")
if v2_path.is_file():
    print("compatibility: awa-hook-owner/v2")
print("compatibility: awa-hook-owner/v1")
for role in roles:
    entry = role["entry"]
    fail_closed = entry.get("failClosed")
    fail_text = "unset" if fail_closed is None else str(fail_closed).lower()
    dormant = (
        f" dormant-until={role['dormant_until_milestone']}"
        if role.get("dormant_until_milestone")
        else ""
    )
    print(
        f"role: {role['id']} event={role['event']} "
        f"timeout={entry['timeout']} failClosed={fail_text}{dormant}"
    )
PY
}

doctor() {
  local rc=0
  policy_check
  printf '\n'
  if ! hook_owner_role_matrix; then
    rc=1
  fi
  printf '\n== current repo ==\n'
  current_state
  if top_level >/dev/null 2>&1; then
    printf '\n== worktrees ==\n'
    list_worktrees
  fi
  return "$rc"
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
# EVERYTHING here WARNs only; it NEVER hard-fails (back-compat: only missing required keys
# fail policy-check). policy-check ALWAYS prints `policy-check: OK` and exits 0.
warnings = []
# A glob/broad key set to `off` disables the guard for EVERY matched repo: explicit OFF beats
# the safety-excludes, so a glob off key is the ONLY thing that can silence AWA for repos the
# safety detectors would otherwise protect. WARN so it is a deliberate, visible choice.
# `.` (the umbrella) is a literal but equally broad, so it is warned too.
BROAD_LITERAL_KEYS = {".", "*", "**"}
try:
    import awa_policy
    data = awa_policy.parse_mini_yaml(text)
    if any(k in data for k in ("modes", "default_mode", "modes_file")):
        modes, default_mode = awa_policy._resolve_modes(data, str(p))
        allowed = "|".join(awa_policy.MODE_VALUES)
        if default_mode not in awa_policy.MODE_VALUES:
            warnings.append(f"default_mode '{default_mode}' is not one of {allowed}")
        # (d) default_mode: off silences AWA for eligible repos with no exact/glob match.
        if str(default_mode).strip().lower() == "off":
            warnings.append(
                "default_mode 'off' disables AWA for ALL eligible repos with no exact or "
                "matching glob entry — confirm this is intended"
            )
        for key, val in modes.items():
            k = str(key).strip()
            if not k:
                warnings.append("empty modes key")
            if val not in awa_policy.MODE_VALUES:
                warnings.append(f"mode for '{key}': '{val}' is not one of {allowed}")
            # (a) glob/broad `off` key — matches multiple repos and beats safety excludes.
            # Quote-strip so a quoted `"*": off` is caught too. WARN on ANY glob metachar
            # (`*`, `?`, `[`) — not just the literals `*`/`**`/`.`.
            kk = k.strip("'\"")
            if str(val).strip().lower() == "off" and (awa_policy._is_glob(kk) or kk in BROAD_LITERAL_KEYS):
                warnings.append(
                    f"broad/glob off key '{key}': disables the guard for matched repos "
                    "(explicit OFF beats safety excludes) — confirm this is intended"
                )

    # (c) dangling `modes_file:` pointer — resolves to a missing/unparseable file, which the
    # loader silently skips (posture reverts to defaults with no visible signal).
    mf = data.get("modes_file")
    if mf:
        import os as _os
        mfp = _os.path.expanduser(str(mf))
        if not _os.path.isabs(mfp):
            mfp = str(pathlib.Path(str(p)).resolve().parent / mfp)
        if not pathlib.Path(mfp).exists():
            warnings.append(
                f"modes_file '{mf}' does not resolve to an existing file ({mfp}) — "
                "posture silently reverts to defaults"
            )
        elif not pathlib.Path(mfp).is_file():
            warnings.append(
                f"modes_file '{mf}' exists but is not a readable regular file ({mfp}) — "
                "posture silently reverts to defaults"
            )
        else:
            try:
                awa_policy.parse_mini_yaml(pathlib.Path(mfp).read_text(encoding="utf-8"))
            except OSError as exc:
                warnings.append(
                    f"modes_file '{mf}' exists but is unreadable ({mfp}): {exc}"
                )
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"modes_file '{mf}' is unparseable: {exc}")

    # (b) non-empty legacy `overrides.include` — legacy unsafe precedence (beats safety).
    overrides = data.get("overrides") if isinstance(data.get("overrides"), dict) else {}
    ovinc = overrides.get("include") or []
    if ovinc:
        warnings.append(
            f"legacy overrides.include is non-empty ({ovinc}) — legacy unsafe precedence "
            "(beats safety excludes); migrate via `mode set`"
        )
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
