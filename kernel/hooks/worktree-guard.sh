#!/usr/bin/env bash
# Cursor mutation backstop hook (AWA kernel). It is a backstop for the always-applied worktree
# rule: fail open outside repos, DENY a confirmed mutating command on an included primary
# checkout (Cursor enforces `deny`, treats `ask` as non-blocking — L4), degrade-to-allow for a
# Cursor Cloud / background agent, and allow an explicit operator override for deliberate work.
#
# ZERO-LINK: carries NO org/host literals. "Is this an included primary checkout?" is decided
# GENERICALLY by dev-worktree.sh (via kernel/lib/awa_policy.py + the policy). The only fallback
# heuristic (included_looking_path) consults the policy's governed roots, never a hard literal.
#
# FAIL-SAFE (incident 2026-07-05): this is a nudge-to-worktree backstop, NOT a security
# sandbox. On hook-internal failure, timeout (SIGTERM), or invalid state we MUST emit
# valid allow JSON and exit 0 so a global/project failClosed gate cannot brick every
# workspace on load. Genuine deny/ask/allow decisions are unchanged on the happy path.
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
is_cloud="no"
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


def _first_root(value):
    """Cursor's real beforeShellExecution/afterFileEdit payload carries `workspace_roots`
    (plural, snake_case, a list) — NOT `workspaceRoot`. Without this, `cwd` is empty
    whenever the caller relies on the chat's default root (no explicit override, the
    COMMON case for a chat rooted directly in the target checkout), and every other key
    below is also absent, so the old chain fell through to os.getcwd() — the HOOK
    SCRIPT's own execution directory (~/.cursor), never the actual target repo. That
    silently misclassified the target as outside any governed root -> ALLOW, defeating
    the guard on exactly the scenario AWA exists to catch. FAIL-SAFE (incident 2026-07-06)."""
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item:
                return item
    return None


workspace = (
    data.get("cwd")
    or data.get("workspaceRoot")
    or data.get("workspace_path")
    or data.get("root")
    or data.get("projectRoot")
    or tool_input.get("cwd")
    or tool_input.get("workspaceRoot")
    or _first_root(data.get("workspace_roots"))
    or _first_root(tool_input.get("workspace_roots"))
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
_MUT = {"rm", "mv", "cp", "install", "truncate", "dd", "tee", "ln",
        "chmod", "chown", "mkdir", "rmdir", "shred", "unlink"}
_PKG = {"npm", "pnpm", "yarn", "pip", "pip3", "bundle", "poetry", "cargo", "go", "brew", "gem"}
_INPLACE = {"sed", "perl", "gawk", "awk"}
# Prefix wrappers whose OPTIONS (not just their name) must be skipped before resolving the
# real program (parity with engine/guard.py). Skipping only the name lets `nice -n 10 git
# commit`, `env -C /r git commit`, `timeout 5 git commit`, `xargs -I{} git commit`, etc.
# classify non-mutating and fast-path ALLOW — a silent bypass of the deny on an included primary.
_PREFIX_WRAPPERS = ("sudo", "command", "nice", "env", "time", "nohup", "xargs",
                    "timeout", "ionice", "chrt", "stdbuf", "builtin", "exec", "doas",
                    "run0", "setsid")
_WRAPPER_VALUE_OPTS = {
    "env": {"-C", "--chdir", "-u", "--unset", "-S", "--split-string"},
    "nice": {"-n", "--adjustment"},
    "sudo": {"-u", "--user", "-g", "--group", "-C", "--close-from", "-h", "--host",
             "-p", "--prompt", "-r", "--role", "-t", "--type", "-U", "--other-user",
             "-D", "--chdir", "-R", "--chroot"},
    "xargs": {"-I", "-i", "-n", "--max-args", "-P", "--max-procs", "-L", "-s",
              "--max-chars", "-E", "-d", "--delimiter", "-a", "--arg-file"},
    "ionice": {"-c", "--class", "-n", "--classdata", "-p", "--pid"},
    "chrt": {"-p", "--pid"},
    "stdbuf": {"-i", "--input", "-o", "--output", "-e", "--error"},
    "timeout": {"-s", "--signal", "-k", "--kill-after"},
    "doas": {"-u", "-a", "-C", "-n", "-L", "-l", "-i", "-k", "-p", "-r", "-s", "-t", "-w"},
    "run0": {"-u", "-g", "-G", "-D", "-M"},
}
_WRAPPER_POSITIONAL = {"timeout", "chrt"}
_INTERPRETERS = frozenset({"bash", "sh", "dash", "zsh", "python3", "python", "perl", "ruby", "node"})
_SCRIPT_BODY_PROGS = _INTERPRETERS | frozenset({"script"})
_SCRIPT_OPTS = frozenset({"-c", "-e"})


def _segments(command: str):
    """Split into per-sub-command token lists at top-level control operators (`;`,
    `&&`, `||`, `&`, `|`, subshell parens, brace groups `{`/`}`, newlines), respecting
    quoting. Raises ValueError on unparseable input (unbalanced quotes)."""
    segs = []
    current = []
    for line in command.split("\n"):
        if not line.strip():
            continue
        lex = shlex.shlex(line, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        for tok in lex:
            if tok in _CONTROL_OPS or tok in ("(", ")", "{", "}"):
                if current:
                    segs.append(current)
                    current = []
                continue
            current.append(tok)
    if current:
        segs.append(current)
    return segs


def _skip_wrappers(toks) -> int:
    """Advance past leading `VAR=value` assignments and prefix wrappers WITH their options,
    returning the index of the resolved program (parity with engine/guard.py._skip_wrappers)."""
    i = 0
    while i < len(toks):
        tok = toks[i]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tok):
            i += 1
            continue
        base = os.path.basename(tok)
        if base not in _PREFIX_WRAPPERS:
            break
        i += 1
        valopts = _WRAPPER_VALUE_OPTS.get(base, set())
        while i < len(toks) and toks[i].startswith("-") and toks[i] != "--":
            opt = toks[i]
            key = opt.split("=", 1)[0]
            i += 1
            if "=" not in opt and key in valopts and i < len(toks):
                i += 1
        if i < len(toks) and toks[i] == "--":
            i += 1
        if base in _WRAPPER_POSITIONAL and i < len(toks) \
                and os.path.basename(toks[i]) not in _PREFIX_WRAPPERS \
                and not re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[i]):
            i += 1
    return i


def _interpreter_script_body(rest):
    """Extract the script string from an interpreter's -c/-e option, if present."""
    i = 0
    while i < len(rest):
        a = rest[i]
        key = a.split("=", 1)[0]
        if key in _SCRIPT_OPTS:
            if "=" in a:
                return a.split("=", 1)[1]
            return rest[i + 1] if i + 1 < len(rest) else ""
        if a.startswith("-") and not a.startswith("--"):
            i += 1
            continue
        if a.startswith("--"):
            i += 1
            continue
        break
    return None


def _rescan_for_mutation(toks) -> bool:
    """Conservative backstop when wrapper-stripping leaves a dangling `-`-prefixed prog."""
    for t in toks:
        b = os.path.basename(t)
        if b in _MUT or b in _PKG or b in _INPLACE or b == "git":
            return True
    return False


def _segment_is_mutating(toks) -> bool:
    for idx, tok in enumerate(toks):
        if tok in _REDIRECT_OPS:
            target = toks[idx + 1] if idx + 1 < len(toks) else ""
            if not target or target.isdigit() or target.startswith(_SAFE_REDIRECT_TARGETS):
                continue
            return True
    i = _skip_wrappers(toks)
    if i >= len(toks):
        return False
    prog = os.path.basename(toks[i])
    rest = toks[i + 1:]
    if prog.startswith("-"):
        return _rescan_for_mutation(toks[i:])
    if prog in _SCRIPT_BODY_PROGS:
        if prog in _INPLACE and any(a == "-i" or a.startswith("-i") for a in rest):
            return True
        body = _interpreter_script_body(rest)
        if body is not None:
            return classify_mutating(body)
        return False
    if prog in _MUT:
        return True
    if prog in _INPLACE and any(a == "-i" or a.startswith("-i") for a in rest):
        return True
    if prog in _PKG and any(a in ("install", "add", "i") for a in rest):
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


def _truthy(v):
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _affirmative_broker(v):
    """Only a real broker HANDLE counts as cloud — Desktop payloads often carry
    `cloud_agent_identity_broker: false` (or 0 / \"false\"), which must NOT degrade to allow."""
    if v is None:
        return False
    if v is False or v == 0:
        return False
    if isinstance(v, (list, dict)) and not v:
        return False
    s = str(v).strip()
    if not s:
        return False
    if s.lower() in ("false", "0", "no", "off"):
        return False
    return True


# Cloud / background-agent detection -> the shell gate degrades to allow BEFORE the deny
# branch (a Cursor Cloud VM is an already-isolated, own-branch /workspace clone; never
# hard-block it). Signals (any): a truthy background-agent flag, an affirmative identity
# broker handle (not false/0/\"false\"), or a /workspace root.
is_cloud = False
for src in (data, tool_input):
    if _truthy(src.get("is_background_agent")):
        is_cloud = True
    if _affirmative_broker(src.get("cloud_agent_identity_broker")):
        is_cloud = True
if workspace == "/workspace" or workspace.startswith("/workspace/"):
    is_cloud = True
for name in ("CURSOR_BACKGROUND_AGENT", "CURSOR_CLOUD_AGENT", "IS_BACKGROUND_AGENT",
             "is_background_agent", "AWA_FORCE_CLOUD"):
    if _truthy(os.environ.get(name, "")):
        is_cloud = True
for name in ("cloud_agent_identity_broker", "CURSOR_AGENT_IDENTITY_BROKER"):
    if _affirmative_broker(os.environ.get(name)):
        is_cloud = True

print("payload_ok=%s" % ("yes" if payload_ok else "no"))
print("cmd=%s" % shlex.quote(cmd))
print("cwd=%s" % shlex.quote(workspace))
print("is_mutating=%s" % ("1" if classify_mutating(cmd) else "0"))
print("is_cloud=%s" % ("yes" if is_cloud else "no"))
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

# Enforced block. Cursor honors `deny` (unlike `ask`, which it treats as non-blocking — L4),
# so this is the shape AWA uses to actually prevent a mutation on an included primary checkout.
# deny_shape (frozen in the contract): permission + user_message + agent_message.
respond_deny() {
  local user_message="$1" agent_message="$2"
  python3 - "$user_message" "$agent_message" <<'PY'
import json, sys
print(json.dumps({
  "permission": "deny",
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

# Cloud degrade-to-allow, BEFORE any deny branch: a Cursor Cloud / background agent runs in an
# already-isolated, own-branch /workspace clone; hard-blocking it would brick a legitimate VM.
if [ "$is_cloud" = "yes" ]; then
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
      # Detection receipt for an included (mode ON) primary hit (observation-only; afterFileEdit
      # cannot pre-block, so we record an honest receipt and allow).
      if [ "$classification" = "include" ] && [ "$linked" = "no" ]; then
        write_detection_receipt "$target" "$probe"
      fi
    done
  fi
  respond_allow
  exit 0
fi

is_uncertain_include() {
  local reason="$1"
  case "$reason" in
    *"fail-safe: ask"*|classifier\ unavailable*) return 0 ;;
    *) return 1 ;;
  esac
}

check_probe() {
  local probe="$1" probe_ctx="$2" status classification linked cls_reason
  status="$(classify_dir "$probe" || true)"
  if [ -z "$status" ]; then
    if included_looking_path "$probe"; then
      respond_ask \
        "AWA could not verify worktree safety for an included-looking checkout." \
        "Hook payload/status could not be classified for $probe ($probe_ctx). Run '$DEV_WORKTREE status' there, or set DEV_WORKTREE_GUARD_ALLOW_PRIMARY=1 only for deliberate primary mutation."
      exit 0
    fi
    return 0
  fi
  classification="$(printf '%s\n' "$status" | awk -F': ' '$1=="classification"{print $2; exit}')"
  linked="$(printf '%s\n' "$status" | awk -F': ' '$1=="linked-worktree"{print $2; exit}')"
  cls_reason="$(printf '%s\n' "$status" | awk -F': ' '$1=="reason"{print $2; exit}')"
  # Only an INCLUDED primary checkout (mode ON) is protected; exclude/advisory/off allow.
  if [ "$classification" = "include" ] && [ "$linked" = "no" ]; then
    if [ "$is_mutating" -eq 1 ]; then
      if is_uncertain_include "$cls_reason"; then
        # Classifier unavailable / uncertainty path -> ask (honest no-op), never deny.
        respond_ask \
          "AWA could not verify worktree safety for an included-looking checkout." \
          "Classifier was unavailable for $probe ($cls_reason). Run '$DEV_WORKTREE status' there, or relaunch in a Safe Workspace via the Cursor Agents-Window Worktree dropdown."
        exit 0
      fi
      # CONFIRMED mutating command on an included primary -> enforced DENY. Cursor honors deny;
      # ask is non-blocking (L4), so deny is the only shape that actually prevents the mutation.
      respond_deny \
        "AWA blocked a mutating command on your primary checkout. Relaunch in a Safe Workspace (Cursor Agents-Window Worktree dropdown) to continue." \
        "AWA DENIED a mutating command on an INCLUDED PRIMARY checkout (mode ON). STOP retrying: re-running it — including 'cd <worktree> && <cmd>' or an inline 'DEV_WORKTREE_GUARD_ALLOW_PRIMARY=1 <cmd>' prefix (this hook reads its OWN process env, not the command's inline env) — will be denied again. Recovery is an OPERATOR action: relaunch this agent in a Safe Workspace via the Cursor Agents-Window Worktree dropdown (AWA adopts the linked worktree, then allows), or set DEV_WORKTREE_GUARD_ALLOW_PRIMARY=1 in Cursor's environment/settings and relaunch. Last resort, only if the operator deliberately wants this repo unprotected: '$DEV_WORKTREE mode set <rel> off'."
      exit 0
    fi
    if [ "$payload_ok" != "yes" ]; then
      # Genuine uncertainty (unparseable payload) on an included-looking primary -> ask. An
      # honest no-op: Cursor ignores ask, so we never silently downgrade an uncertain case to
      # allow, but we also never claim ask prevents anything.
      respond_ask \
        "AWA could not classify this command for an included primary checkout." \
        "Hook payload was unparseable ($probe_ctx) for an included primary checkout. If this was a mutating command, relaunch in a Safe Workspace via the Cursor Agents-Window Worktree dropdown, or set DEV_WORKTREE_GUARD_ALLOW_PRIMARY=1 in Cursor's environment."
      exit 0
    fi
  fi
}

# Shell / unknown-payload path: the real pre-exec gate. Cursor enforces `deny` (it treats `ask`
# as non-blocking — L4), so a confirmed mutation on an included primary returns deny here — this
# is where prevention actually happens.
check_probe "$(dir_for_probe "$cwd")" "workspace"

respond_allow
