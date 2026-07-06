#!/usr/bin/env bash
# Cursor mutation backstop hook (AWA kernel). It is a soft backstop for the always-applied
# worktree rule: fail open outside repos, ask before included primary mutations, and allow
# an explicit operator override for deliberate primary work.
#
# ZERO-LINK: carries NO org/host literals. "Is this an included primary checkout?" is decided
# GENERICALLY by dev-worktree.sh (via kernel/lib/awa_policy.py + the policy). The only fallback
# heuristic (included_looking_path) consults the policy's governed roots, never a hard literal.
#
# FAIL-SAFE (incident 2026-07-05): this is a nudge-to-worktree backstop, NOT a security
# sandbox. On hook-internal failure, timeout (SIGTERM), or invalid state we MUST emit
# valid allow JSON and exit 0 so a global/project failClosed gate cannot brick every
# workspace on load. Genuine ask/allow decisions are unchanged on the happy path.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"   # kernel/hooks
KERNEL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"                        # kernel
DEV_WORKTREE="$KERNEL_DIR/bin/dev-worktree.sh"
AWA_POLICY_LIB="$KERNEL_DIR/lib/awa_policy.py"
POLICY="${AWA_POLICY:-$KERNEL_DIR/policy/default-worktree-policy.yml}"

input="$(cat 2>/dev/null || true)"

respond_allow() {
  printf '{ "permission": "allow" }\n'
}

# Degrade-to-allow on unexpected failure or Cursor timeout kill (SIGTERM).
_degrade_allow() {
  respond_allow
  exit 0
}
trap '_degrade_allow' ERR TERM

# Single-parse fast path (perf + timeout margin). ONE python invocation reads the entire hook
# payload and emits shell-eval-safe (shlex.quoted) assignments. Values are pre-seeded so a
# python failure degrades exactly as before (payload_ok=no, non-mutating, empty cwd -> allow).
payload_ok="no"
cmd=""
cwd=""
is_mutating="0"
has_paths="no"
paths=()
eval "$(HOOK_INPUT="$input" python3 - <<'PY'
import json, os, re, sys, shlex
raw = os.environ.get("HOOK_INPUT", "")
try:
    data = json.loads(raw or "{}")
    payload_ok = True
except Exception:
    data = {}
    payload_ok = False

tool_input = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
cmd = data.get("command") or tool_input.get("command") or ""
workspace = (
    data.get("cwd")
    or data.get("workspaceRoot")
    or data.get("workspace_path")
    or data.get("root")
    or data.get("projectRoot")
    or tool_input.get("cwd")
    or tool_input.get("workspaceRoot")
    or os.getcwd()
)

paths = []
for source in (data, tool_input):
    for key in ("filePath", "file_path", "path", "targetPath", "target_path", "uri"):
        value = source.get(key)
        if isinstance(value, str) and value:
            paths.append(value.removeprefix("file://"))
    value = source.get("files")
    if isinstance(value, list):
        paths.extend(item for item in value if isinstance(item, str) and item)


_CONTROL_OPS = {";", "&&", "||", "&", "|"}
_REDIRECT_OPS = {">", ">>", ">&", "&>", ">|"}
_SAFE_REDIRECT_TARGETS = ("/dev/null", "/dev/stdout", "/dev/stderr")


def _segments(command: str):
    """Split into per-sub-command token lists at top-level control operators (`;`,
    `&&`, `||`, `&`, `|`, subshell parens, newlines), respecting quoting. Raises
    ValueError on unparseable input (unbalanced quotes)."""
    segs = []
    current = []
    for line in command.split("\n"):
        if not line.strip():
            continue
        lex = shlex.shlex(line, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        for tok in lex:
            if tok in _CONTROL_OPS or tok in ("(", ")"):
                if current:
                    segs.append(current)
                    current = []
                continue
            current.append(tok)
    if current:
        segs.append(current)
    return segs


def _segment_is_mutating(toks) -> bool:
    for idx, tok in enumerate(toks):
        if tok in _REDIRECT_OPS:
            target = toks[idx + 1] if idx + 1 < len(toks) else ""
            if not target or target.isdigit() or target.startswith(_SAFE_REDIRECT_TARGETS):
                continue
            return True
    i = 0
    while i < len(toks) and (re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[i])
                             or toks[i] in ("sudo", "command", "nice", "env", "time", "nohup", "xargs")):
        i += 1
    if i >= len(toks):
        return False
    prog = os.path.basename(toks[i])
    rest = toks[i + 1:]
    MUT = {"rm", "mv", "cp", "install", "truncate", "dd", "tee", "ln",
           "chmod", "chown", "mkdir", "rmdir", "shred", "unlink"}
    if prog in MUT:
        return True
    if prog in ("sed", "perl", "gawk", "awk") and any(a == "-i" or a.startswith("-i") for a in rest):
        return True
    if prog in ("npm", "pnpm", "yarn", "pip", "pip3", "bundle", "poetry", "cargo", "go", "brew", "gem") \
       and any(a in ("install", "add", "i") for a in rest):
        return True
    if prog == "git":
        j = 0
        takes_arg = ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--super-prefix")
        while j < len(rest):
            a = rest[j]
            if a in takes_arg:
                j += 2; continue
            if a.startswith(("--git-dir=", "--work-tree=", "--namespace=", "--exec-path=", "--super-prefix=")) \
               or (a.startswith("-c") and len(a) > 2):
                j += 1; continue
            if a.startswith("-"):
                j += 1; continue
            break
        sub = rest[j] if j < len(rest) else ""
        GITMUT = {"commit", "add", "reset", "rebase", "checkout", "switch", "clean",
                  "merge", "cherry-pick", "apply", "restore", "stash", "rm", "mv",
                  "pull", "am", "revert", "worktree", "push", "fetch"}
        return sub in GITMUT
    return False


def classify_mutating(command: str) -> bool:
    """Robust mutating-command detector for the shell gate. Adversary-aware: catches the
    review-flagged bypasses `git -C <path> commit` (global options before the subcommand),
    `sed -i` in-place edits, `>`/`>>` file redirection, and command chaining (`;`, `&&`,
    `||`, `|`) that would otherwise hide a mutating sub-command behind a read-only leader
    (e.g. `git status && git commit`) — not just a bare `git commit`. Conservative on
    purpose: the gate only fires on an INCLUDED PRIMARY checkout, so over-asking there is
    the desired nudge-to-worktree, never a silent bypass."""
    if not command or not command.strip():
        return False
    try:
        segs = _segments(command)
    except ValueError:
        return True  # unparseable -> fail safe (ask)
    return any(_segment_is_mutating(toks) for toks in segs)


resolved = []
for p in paths:
    if not os.path.isabs(p):
        p = os.path.join(workspace, p)
    resolved.append(p)

print("payload_ok=%s" % ("yes" if payload_ok else "no"))
print("cmd=%s" % shlex.quote(cmd))
print("cwd=%s" % shlex.quote(workspace))
print("is_mutating=%s" % ("1" if classify_mutating(cmd) else "0"))
print("has_paths=%s" % ("yes" if paths else "no"))
print("paths=(%s)" % " ".join(shlex.quote(p) for p in resolved))
PY
)"

respond_ask() {
  local user_message="$1" agent_message="$2"
  python3 - "$user_message" "$agent_message" <<'PY'
import json, sys
print(json.dumps({
  "permission": "ask",
  "user_message": sys.argv[1],
  "agent_message": sys.argv[2],
}))
PY
}

# Generic "included-looking" heuristic: a path under a governed root (from AWA_GOVERNED_ROOT or
# the policy). NO org/host literal. Absent a governed root (standalone default), we cannot guess,
# so return 1 and let classify_dir be the real decision (on its failure we fail OPEN).
included_looking_path() {
  local path="$1" roots root
  roots="$(python3 "$AWA_POLICY_LIB" governed-roots --policy "$POLICY" --governed-root "${AWA_GOVERNED_ROOT:-}" 2>/dev/null || true)"
  [ -n "$roots" ] || return 1
  while IFS= read -r root; do
    [ -n "$root" ] || continue
    case "$path" in
      "$root"/*|"$root") return 0 ;;
    esac
  done <<EOF
$roots
EOF
  return 1
}

dir_for_probe() {
  local path="$1"
  if [ -d "$path" ]; then
    printf '%s\n' "$path"
  elif [ -n "$path" ]; then
    dirname "$path"
  fi
}

classify_dir() {
  local dir="$1"
  [ -x "$DEV_WORKTREE" ] || return 1
  [ -d "$dir" ] || return 1
  # HOT PATH: the guard reads only `classification`/`linked-worktree`, never `explicit-mode`.
  # Export AWA_STATUS_NO_MODE=1 so `status` skips the second python3 (`mode-for`) spawn — the
  # pre-mutation gate stays single-spawn (one classify), avoiding a latency regression.
  (cd "$dir" 2>/dev/null && AWA_STATUS_NO_MODE=1 "$DEV_WORKTREE" status 2>/dev/null) || return 1
}

# Which event is this invocation serving? beforeShellExecution carries a command;
# afterFileEdit carries file paths and no command. Cursor IGNORES any permission we return on
# afterFileEdit (observation-only), so on that path we MUST NOT emit a no-op `ask` (X2) — we
# record an honest detection receipt and allow instead.
event="unknown"
if [ -n "$cmd" ]; then
  event="shell"
elif [ "$payload_ok" = "yes" ] && [ "$has_paths" = "yes" ]; then
  event="file-edit"
fi

if [ "${DEV_WORKTREE_GUARD_ALLOW_PRIMARY:-0}" = "1" ]; then
  respond_allow
  exit 0
fi

# FAST PATH (perf; behavior-preserving). A well-formed, non-mutating shell command is provably
# an ALLOW regardless of classify_dir, so return allow now and skip the expensive status probe.
if [ "$event" = "shell" ] && [ "$payload_ok" = "yes" ] && [ "$is_mutating" -eq 0 ]; then
  respond_allow
  exit 0
fi

# X2: honest detection receipt for a native edit landing in an included primary checkout.
# METADATA ONLY — never the file content (S1/S5 secret/PII avoidance).
write_detection_receipt() {
  local path="$1" repo="$2" dir ts
  dir="${XDG_STATE_HOME:-$HOME/.local/state}/awa/detections"
  mkdir -p "$dir" 2>/dev/null || return 0
  chmod 700 "$dir" 2>/dev/null || true
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  DR_LOG="$dir/receipts.jsonl" DR_TS="$ts" DR_PATH="$path" DR_REPO="$repo" python3 - <<'PY'
import json, os
rec = {
    "kind": "primary-file-edit-detected",
    "time": os.environ["DR_TS"],
    "path": os.environ["DR_PATH"],
    "repo": os.environ["DR_REPO"],
    "note": ("Native edit to an included primary checkout was detected. afterFileEdit is "
             "observation-only, so this could not be pre-blocked. Uncommitted-file recovery is "
             "available once the AWA recovery manager ships."),
}
with open(os.environ["DR_LOG"], "a", encoding="utf-8") as fh:
    fh.write(json.dumps(rec) + "\n")
PY
}

if [ "$event" = "file-edit" ]; then
  if [ "${#paths[@]}" -gt 0 ]; then
    for target in "${paths[@]}"; do
      [ -n "$target" ] || continue
      probe="$(dir_for_probe "$target")"
      status="$(classify_dir "$probe" || true)"
      [ -n "$status" ] || continue
      classification="$(printf '%s\n' "$status" | awk -F': ' '$1=="classification"{print $2; exit}')"
      linked="$(printf '%s\n' "$status" | awk -F': ' '$1=="linked-worktree"{print $2; exit}')"
      # Detection receipt for BOTH on(include) and ask_on primary hits (observation-only).
      if { [ "$classification" = "include" ] || [ "$classification" = "ask_on" ]; } && [ "$linked" = "no" ]; then
        write_detection_receipt "$target" "$probe"
      fi
    done
  fi
  respond_allow
  exit 0
fi

check_probe() {
  local probe="$1" reason="$2" status classification linked
  status="$(classify_dir "$probe" || true)"
  if [ -z "$status" ]; then
    if included_looking_path "$probe"; then
      respond_ask \
        "AWA could not verify worktree safety for an included-looking checkout." \
        "Hook payload/status could not be classified for $probe ($reason). Run '$DEV_WORKTREE status' there, or set DEV_WORKTREE_GUARD_ALLOW_PRIMARY=1 only for deliberate primary mutation."
      exit 0
    fi
    return 0
  fi
  classification="$(printf '%s\n' "$status" | awk -F': ' '$1=="classification"{print $2; exit}')"
  linked="$(printf '%s\n' "$status" | awk -F': ' '$1=="linked-worktree"{print $2; exit}')"
  # ASK_ON asks on primary mutation exactly like on(include); exclude/advisory allow.
  if { [ "$classification" = "include" ] || [ "$classification" = "ask_on" ]; } && [ "$linked" = "no" ]; then
    if [ "$payload_ok" != "yes" ] || [ "$is_mutating" -eq 1 ] || [ "$reason" = "file-edit" ]; then
      respond_ask \
        "This appears to target an included primary checkout. Use a Safe Workspace first?" \
        "Run '$DEV_WORKTREE ensure', then call move_agent_to_root with the printed rootPath before mutating this repo. Override only deliberately with DEV_WORKTREE_GUARD_ALLOW_PRIMARY=1."
      exit 0
    fi
  fi
}

# Shell / unknown-payload path: the real pre-exec gate. beforeShellExecution `ask`/`deny` IS
# honored by Cursor, so this is where prevention actually happens.
check_probe "$(dir_for_probe "$cwd")" "workspace"

respond_allow
