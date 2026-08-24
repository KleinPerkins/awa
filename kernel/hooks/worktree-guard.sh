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
AWA_ROOTS_LIB="${AWA_ROOTS_LIB:-$KERNEL_DIR/lib/awa_roots.py}"
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
session_id=""
paths=()
has_mut_targets="no"
mut_targets=()
maintenance_allowed="no"
maintenance_kind="none"
maintenance_reason="unsupported_form"
maintenance_matched="no"
maintenance_message=""
eval "$(HOOK_INPUT="$input" python3 - <<'PY'
import json, os, re, sys, shlex, subprocess, selectors, time
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
session_values = {
    str(src.get(key)).strip()
    for src in (data, tool_input)
    for key in ("session_id", "sessionId", "conversation_id", "conversationId")
    if isinstance(src.get(key), str) and str(src.get(key)).strip()
}
session_id = next(iter(session_values)) if len(session_values) == 1 else ""

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
_GIT_TAKES_ARG = ("-C", "-c", "--git-dir", "--work-tree", "--namespace",
                  "--exec-path", "--super-prefix")
_GITMUT = {"commit", "add", "reset", "rebase", "checkout", "switch", "clean",
           "merge", "cherry-pick", "apply", "restore", "stash", "rm", "mv",
           "pull", "am", "revert", "worktree", "push", "fetch",
           "branch", "remote", "config", "submodule", "sparse-checkout",
           "gc", "maintenance"}
_GIT_WORKTREE_READONLY_ACTIONS = {"list"}
_GIT_STASH_READONLY_ACTIONS = {"list", "show"}
_GIT_WORKTREE_LIST_FLAGS = {"--porcelain", "-z", "--verbose", "-v"}
_GIT_STASH_LIST_FLAGS = set()
_GIT_STASH_SHOW_FLAGS = {"--stat", "--patch", "-p"}
_GIT_CLEAN_DRY_RUN_FLAGS = {"-n", "--dry-run"}
_GIT_CLEAN_READONLY_FLAGS = {"-n", "--dry-run", "-d", "-x", "-X", "-q"}
_GIT_CLEAN_MUTATING_FLAGS = {"-f", "--force", "-i", "--interactive"}


def _git_subcommand(rest):
    j = 0
    while j < len(rest):
        a = rest[j]
        if a in _GIT_TAKES_ARG:
            j += 2
            continue
        if a.startswith(("--git-dir=", "--work-tree=", "--namespace=",
                         "--exec-path=", "--super-prefix=")) or (a.startswith("-c") and len(a) > 2):
            j += 1
            continue
        if a.startswith("-"):
            j += 1
            continue
        break
    sub = rest[j] if j < len(rest) else ""
    return sub, rest[j + 1:] if j < len(rest) else []


_GIT_GLOBAL_VALUE_OPTS = {
    "-C",
    "-c",
    "--git-dir",
    "--work-tree",
    "--namespace",
    "--super-prefix",
}
_GIT_GLOBAL_FLAG_OPTS = {
    "-p",
    "--paginate",
    "-P",
    "--no-pager",
    "--no-replace-objects",
    "--bare",
    "--literal-pathspecs",
    "--glob-pathspecs",
    "--noglob-pathspecs",
    "--icase-pathspecs",
    "--no-optional-locks",
    "--no-lazy-fetch",
}
_GIT_GLOBAL_ATTACHED_PREFIXES = (
    "--git-dir=",
    "--work-tree=",
    "--namespace=",
    "--super-prefix=",
    "--config-env=",
)


def _parse_git_invocation(rest):
    """Strict git prefix parser (parity with engine/guard.py). Returns
    (global_args, subcommand, sub_args) or None. None means a bare global value
    option is missing its value, an attached global prefix is empty, or an
    unrecognized dash-prefixed global token appears (conservative: the caller
    treats a None parse as mutating via the compatibility fallback). ONLY the
    VALIDATED global prefix returned here may later name a mutation target, so a
    family-local flag (for example a branch -C) can never launder the scope."""
    global_args = []
    i = 0
    while i < len(rest):
        arg = rest[i]
        if arg in _GIT_GLOBAL_VALUE_OPTS:
            if i + 1 >= len(rest) or not rest[i + 1]:
                return None
            global_args.extend((arg, rest[i + 1]))
            i += 2
            continue
        if arg in _GIT_GLOBAL_FLAG_OPTS:
            global_args.append(arg)
            i += 1
            continue
        if arg.startswith(_GIT_GLOBAL_ATTACHED_PREFIXES):
            prefix = next(
                item for item in _GIT_GLOBAL_ATTACHED_PREFIXES
                if arg.startswith(item)
            )
            if len(arg) == len(prefix):
                return None
            global_args.append(arg)
            i += 1
            continue
        if arg.startswith("-c") and len(arg) > 2:
            global_args.append(arg)
            i += 1
            continue
        if arg.startswith("-"):
            return None
        return global_args, arg, rest[i + 1:]
    return global_args, "", []


def _git_global_args_block_readonly(global_args):
    return any(
        arg in {"-p", "--paginate", "-c"}
        or (arg.startswith("-c") and len(arg) > 2)
        or arg.startswith("--config-env=")
        for arg in global_args
    )


def _git_exact_nested_action(args):
    if not args or args[0].startswith("-"):
        return "", args
    return args[0], args[1:]


def _git_flag_name(arg):
    return arg.split("=", 1)[0]


def _git_args_are_known_readonly_flags(args, allowed):
    return all(arg in allowed for arg in args)


def _git_worktree_list_is_readonly(args):
    return _git_args_are_known_readonly_flags(args, _GIT_WORKTREE_LIST_FLAGS)


def _git_stash_list_is_readonly(args):
    return args == []


def _git_stash_show_is_readonly(args):
    seen_ref = False
    for arg in args:
        if arg in _GIT_STASH_SHOW_FLAGS:
            continue
        if arg == "--":
            return False
        if arg.startswith("-"):
            return False
        if seen_ref:
            return False
        seen_ref = True
    return True


def _git_clean_is_readonly(args):
    has_dry_run = False
    parsing_options = True
    for a in args:
        if parsing_options and a == "--":
            parsing_options = False
            continue
        if not parsing_options:
            continue
        if a in _GIT_CLEAN_DRY_RUN_FLAGS:
            has_dry_run = True
            continue
        if a in _GIT_CLEAN_MUTATING_FLAGS:
            return False
        if len(a) > 2 and a.startswith("-") and not a.startswith("--"):
            chars = set(a[1:])
            if "n" in chars:
                has_dry_run = True
            if "f" in chars or "i" in chars:
                return False
            if not chars.issubset(set("ndxXq")):
                return False
            continue
        if not a.startswith("-"):
            if not has_dry_run:
                return False
            continue
        if _git_flag_name(a) not in _GIT_CLEAN_READONLY_FLAGS:
            return False
    return has_dry_run


_GIT_BRANCH_LIST_FLAGS = {
    "--list", "-a", "--all", "-r", "--remotes",
    "-v", "-vv", "--verbose",
}
_GIT_CONFIG_PREFIX_FLAGS = {
    "--local", "--global", "--system", "--worktree",
    "--includes", "--no-includes", "--null", "-z",
    "--name-only", "--show-origin", "--show-scope", "--fixed-value",
}
_GIT_CONFIG_PREFIX_VALUE_OPTS = {"--file", "--type"}
_GIT_CONFIG_GETTER_ARITY = {
    "--list": {0},
    "-l": {0},
    "--get": {1, 2},
    "--get-all": {1, 2},
    "--get-regexp": {1, 2},
    "--get-urlmatch": {2},
    "--get-color": {1, 2},
    "--get-colorbool": {1, 2},
}


def _git_branch_is_readonly(args):
    if not args:
        return True
    if args == ["--show-current"]:
        return True
    seen_list = False
    saw_pattern = False
    explicit_boundary = False
    parsing_flags = True
    for arg in args:
        if parsing_flags and arg == "--":
            explicit_boundary = True
            parsing_flags = False
            continue
        if parsing_flags and arg in _GIT_BRANCH_LIST_FLAGS:
            seen_list = seen_list or arg == "--list"
            continue
        if parsing_flags and arg.startswith("-"):
            return False
        if not seen_list:
            return False
        if not explicit_boundary and arg.startswith("-"):
            return False
        saw_pattern = True
        parsing_flags = False
    return seen_list or (not saw_pattern and not explicit_boundary)


def _git_remote_is_readonly(args):
    if not args:
        return True
    i = 0
    if args[i] in ("-v", "--verbose"):
        i += 1
        if i == len(args):
            return True
    if args[i] == "get-url":
        i += 1
        seen_options = set()
        while i < len(args) and args[i] in ("--push", "--all"):
            if args[i] in seen_options:
                return False
            seen_options.add(args[i])
            i += 1
        return (
            i == len(args) - 1
            and bool(args[i])
            and not args[i].startswith("-")
        )
    if args[i] == "show":
        return (
            i + 2 == len(args) - 1
            and args[i + 1] == "-n"
            and bool(args[i + 2])
            and not args[i + 2].startswith("-")
        )
    return False


def _git_config_is_readonly(args):
    i = 0
    while i < len(args):
        if args[i] in _GIT_CONFIG_PREFIX_FLAGS:
            i += 1
            continue
        if args[i] in _GIT_CONFIG_PREFIX_VALUE_OPTS:
            if i + 1 >= len(args):
                return False
            i += 2
            continue
        break
    if i >= len(args) or args[i] not in _GIT_CONFIG_GETTER_ARITY:
        return False
    return len(args[i + 1:]) in _GIT_CONFIG_GETTER_ARITY[args[i]]


def _git_submodule_is_readonly(args):
    if not args or args[0] != "status":
        return False
    i = 1
    if i < len(args) and args[i] == "--cached":
        i += 1
    if i == len(args):
        return True
    return args[i] == "--"


def _git_sparse_checkout_is_readonly(args):
    return args == ["list"]


def _git_is_mutating(rest):
    compatibility_sub, _compatibility_args = _git_subcommand(rest)
    parsed = _parse_git_invocation(rest)
    if parsed is None:
        return (
            not compatibility_sub
            or compatibility_sub in _GITMUT
            or any(token in _GITMUT for token in rest)
        )
    global_args, sub, sub_args = parsed
    if not sub or sub not in _GITMUT:
        return False
    if sub in {"fetch", "push"}:
        return True
    if _git_global_args_block_readonly(global_args):
        return True
    if sub == "branch":
        return not _git_branch_is_readonly(sub_args)
    if sub == "remote":
        return not _git_remote_is_readonly(sub_args)
    if sub == "config":
        return not _git_config_is_readonly(sub_args)
    if sub == "submodule":
        return not _git_submodule_is_readonly(sub_args)
    if sub == "sparse-checkout":
        return not _git_sparse_checkout_is_readonly(sub_args)
    if sub == "worktree":
        action, action_args = _git_exact_nested_action(sub_args)
        return not (
            action in _GIT_WORKTREE_READONLY_ACTIONS
            and _git_worktree_list_is_readonly(action_args)
        )
    if sub == "stash":
        action, action_args = _git_exact_nested_action(sub_args)
        if action == "list":
            return not _git_stash_list_is_readonly(action_args)
        if action == "show":
            return not _git_stash_show_is_readonly(action_args)
        return True
    if sub == "clean":
        return not _git_clean_is_readonly(sub_args)
    return True


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
        return _git_is_mutating(rest)
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


# ---- ADR 0019: exact protected-primary maintenance lane ---------------------------
# Keep this recognizer and inspector independent from the engine. Every helper in
# this block is annotation-free for Python 3.9, and comments contain no apostrophe
# because macOS Bash 3.2 misparses that character in this nested heredoc shape.
_PRIMARY_MAINTENANCE_TIMEOUT = 5
_PRIMARY_MAINTENANCE_MAX_OUTPUT = 65536
_PRIMARY_MAINTENANCE_RELATED_GIT = {
    "fetch",
    "merge",
    "pull",
    "push",
    "remote",
    "gc",
    "maintenance",
}
_PRIMARY_MAINTENANCE_RISKY_GIT_ENV = {
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CONFIG",
    "GIT_CONFIG_GLOBAL",
    "GIT_CONFIG_SYSTEM",
    "GIT_EXEC_PATH",
    "GIT_NAMESPACE",
    "GIT_SHALLOW_FILE",
    "GIT_REPLACE_REF_BASE",
    "GIT_NO_REPLACE_OBJECTS",
    "GIT_CEILING_DIRECTORIES",
    "GIT_DISCOVERY_ACROSS_FILESYSTEM",
}
_PRIMARY_MAINTENANCE_IN_PROGRESS = {
    "MERGE_HEAD",
    "rebase-merge",
    "rebase-apply",
    "CHERRY_PICK_HEAD",
    "REVERT_HEAD",
    "sequencer",
    "BISECT_LOG",
    "BISECT_START",
    "BISECT_NAMES",
    "BISECT_TERMS",
}
_PRIMARY_MAINTENANCE_MESSAGES = {
    "unsupported_form": (
        "AWA did not run this command. On a protected primary, maintenance supports only "
        "git fetch, git fetch <configured upstream remote>, and "
        "git merge --ff-only --no-overwrite-ignore with no target, @{u}, "
        "@{upstream}, or the exact configured upstream branch. Extra flags and targets "
        "stay blocked."
    ),
    "dirty": (
        "AWA did not run maintenance because this primary has local files. Preserve or "
        "move that work in a Safe Workspace, then retry when git status --short is empty."
    ),
    "missing_upstream": (
        "AWA did not run maintenance because it could not identify one tracked remote "
        "branch for the current branch. Repair branch tracking in a Safe Workspace, then retry."
    ),
    "wrong_upstream": (
        "AWA did not run maintenance because the command target does not exactly match "
        "the configured upstream for the current branch. Use the configured upstream "
        "remote or branch exactly."
    ),
    "unsafe_fetch_config": (
        "AWA did not run maintenance because the configured fetch rules can write outside "
        "the remote-tracking area or no longer map the tracked branch. Repair the remote "
        "fetch configuration in a Safe Workspace, then retry."
    ),
    "diverged": (
        "AWA did not run maintenance because this primary contains local-only or "
        "conflicting history. Reconcile that history in a Safe Workspace; AWA will not "
        "rewrite or reset the primary."
    ),
    "busy": (
        "AWA did not run maintenance because another Git operation is in progress. "
        "Finish or diagnose that operation in a Safe Workspace, then retry."
    ),
    "inspection_failed": (
        "AWA did not run maintenance because it could not prove that this primary is safe "
        "to maintain. Stop and diagnose the repository from a Safe Workspace before retrying."
    ),
}


def _primary_maintenance_related(command, depth=0):
    try:
        segments = _segments(command)
    except ValueError:
        return False
    for tokens in segments:
        program_index = _skip_wrappers(tokens)
        if program_index >= len(tokens):
            continue
        program = os.path.basename(tokens[program_index])
        rest = tokens[program_index + 1:]
        if (
            program == "git"
            and any(token in _PRIMARY_MAINTENANCE_RELATED_GIT for token in rest)
        ):
            return True
        if program in _SCRIPT_BODY_PROGS and depth < 3:
            body = _interpreter_script_body(rest)
            if body is not None and _primary_maintenance_related(body, depth + 1):
                return True
    return False


def _primary_maintenance_shape(command):
    related = _primary_maintenance_related(command)
    if not command or "\n" in command or "\r" in command:
        return {
            "valid": False,
            "kind": "none",
            "operand": "",
            "matched": related,
        }
    bare_git = re.match(r"^\s*git(?:\s|$)", command) is not None
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        lex.commenters = ""
        tokens = list(lex)
    except ValueError:
        return {"valid": False, "kind": "none", "operand": "", "matched": False}
    if (
        not bare_git
        or not tokens
        or tokens[0] != "git"
        or any(
            token in _CONTROL_OPS
            or token in _REDIRECT_OPS
            or token in {"(", ")", "{", "}"}
            or "$" in token
            or chr(96) in token
            for token in tokens
        )
    ):
        return {"valid": False, "kind": "none", "operand": "", "matched": related}
    if len(tokens) >= 2 and tokens[1] == "fetch":
        if len(tokens) == 2:
            return {"valid": True, "kind": "fetch", "operand": "", "matched": True}
        if len(tokens) == 3 and tokens[2] and not tokens[2].startswith("-"):
            return {
                "valid": True,
                "kind": "fetch",
                "operand": tokens[2],
                "matched": True,
            }
        return {"valid": False, "kind": "fetch", "operand": "", "matched": True}
    if len(tokens) >= 2 and tokens[1] == "merge":
        prefix = ["git", "merge", "--ff-only", "--no-overwrite-ignore"]
        if tokens[:4] != prefix:
            return {
                "valid": False,
                "kind": "fast_forward",
                "operand": "",
                "matched": True,
            }
        if len(tokens) == 4:
            return {
                "valid": True,
                "kind": "fast_forward",
                "operand": "",
                "matched": True,
            }
        if len(tokens) == 5 and tokens[4] and not tokens[4].startswith("-"):
            return {
                "valid": True,
                "kind": "fast_forward",
                "operand": tokens[4],
                "matched": True,
            }
        return {
            "valid": False,
            "kind": "fast_forward",
            "operand": "",
            "matched": True,
        }
    return {"valid": False, "kind": "none", "operand": "", "matched": related}


def _run_primary_maintenance_git(cwd_value, *args):
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_NO_LAZY_FETCH"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        proc = subprocess.run(
            ["git", "-C", cwd_value] + list(args),
            capture_output=True,
            text=True,
            env=env,
            timeout=_PRIMARY_MAINTENANCE_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return None
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    if (
        len(stdout.encode("utf-8", "replace"))
        + len(stderr.encode("utf-8", "replace"))
        > _PRIMARY_MAINTENANCE_MAX_OUTPUT
    ):
        return None
    return proc.returncode, stdout, stderr


def _primary_maintenance_has_hidden_index_bits(cwd_value):
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_NO_LAZY_FETCH"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        proc = subprocess.Popen(
            ["git", "-C", cwd_value, "ls-files", "-v", "-z"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
    except OSError:
        return None
    if proc.stdout is None or proc.stderr is None:
        proc.kill()
        proc.wait()
        return None

    selector = selectors.DefaultSelector()
    try:
        selector.register(proc.stdout, selectors.EVENT_READ, "stdout")
        selector.register(proc.stderr, selectors.EVENT_READ, "stderr")
    except (OSError, ValueError):
        selector.close()
        proc.kill()
        proc.wait()
        proc.stdout.close()
        proc.stderr.close()
        return None
    deadline = time.monotonic() + _PRIMARY_MAINTENANCE_TIMEOUT
    tail = b""
    stderr_seen = False
    hidden = False
    failed = False
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                failed = True
                break
            try:
                events = selector.select(remaining)
            except OSError:
                failed = True
                break
            if not events:
                failed = True
                break
            for key, _mask in events:
                try:
                    chunk = os.read(key.fd, 65536)
                except OSError:
                    failed = True
                    break
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                if key.data == "stderr":
                    stderr_seen = True
                    continue
                tail += chunk
                records = tail.split(b"\x00")
                tail = records.pop()
                if len(tail) > _PRIMARY_MAINTENANCE_MAX_OUTPUT:
                    failed = True
                    break
                for record in records:
                    if len(record) < 3 or record[1:2] != b" ":
                        failed = True
                        break
                    tag = record[0]
                    if tag == ord("S") or ord("a") <= tag <= ord("z"):
                        hidden = True
                if failed:
                    break
            if failed:
                break
        if not failed:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                failed = True
            else:
                try:
                    proc.wait(timeout=remaining)
                except subprocess.TimeoutExpired:
                    failed = True
    finally:
        selector.close()
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        proc.stdout.close()
        proc.stderr.close()
    if failed or proc.returncode != 0 or stderr_seen or tail:
        return None
    return hidden


def _primary_maintenance_lines(result):
    if result is None:
        return None
    returncode, stdout, stderr = result
    if (
        returncode != 0
        or stderr
        or not stdout
        or not stdout.endswith("\n")
        or "\x00" in stdout
        or "\r" in stdout
    ):
        return None
    lines = stdout[:-1].split("\n")
    if not lines or any(not line for line in lines):
        return None
    return lines


def _primary_maintenance_config_values(cwd_value, key):
    result = _run_primary_maintenance_git(cwd_value, "config", "--get-all", key)
    if result is None:
        return "error", []
    returncode, stdout, stderr = result
    if returncode == 1 and not stdout and not stderr:
        return "missing", []
    lines = _primary_maintenance_lines(result)
    if lines is None:
        return "error", []
    return "ok", lines


def _valid_refspec_ref(ref, allow_wildcard):
    if not ref.startswith("refs/") or ref.endswith("/"):
        return False
    if ref.count("*") > (1 if allow_wildcard else 0):
        return False
    if any(
        ord(char) < 32 or ord(char) == 127 or char in " ~^:?[\\" for char in ref
    ):
        return False
    if ".." in ref or "@{" in ref or "//" in ref:
        return False
    for component in ref.split("/"):
        if (
            not component
            or component in {".", ".."}
            or component.startswith(".")
            or component.endswith(".")
            or component.endswith(".lock")
        ):
            return False
    return True


def _refspec_pattern_matches(pattern, ref):
    if "*" not in pattern:
        return pattern == ref
    prefix, suffix = pattern.split("*", 1)
    return (
        ref.startswith(prefix)
        and ref.endswith(suffix)
        and len(ref) >= len(prefix) + len(suffix)
    )


def _map_fetch_refspec(source, destination, ref):
    if "*" not in source:
        return destination if source == ref else None
    prefix, suffix = source.split("*", 1)
    if (
        not ref.startswith(prefix)
        or not ref.endswith(suffix)
        or len(ref) < len(prefix) + len(suffix)
    ):
        return None
    capture_end = len(ref) - len(suffix) if suffix else len(ref)
    capture = ref[len(prefix):capture_end]
    return destination.replace("*", capture)


def _safe_fetch_destination(remote, source_ref, refspecs):
    namespace = "refs/remotes/{0}/".format(remote)
    mapped = []
    excluded = False
    for raw_spec in refspecs:
        if not raw_spec or any(
            ord(char) < 32 or ord(char) == 127 for char in raw_spec
        ):
            return None
        if raw_spec.startswith("^"):
            source = raw_spec[1:]
            if (
                not source
                or ":" in source
                or not _valid_refspec_ref(source, True)
            ):
                return None
            excluded = excluded or _refspec_pattern_matches(source, source_ref)
            continue
        spec = raw_spec[1:] if raw_spec.startswith("+") else raw_spec
        if spec.count(":") != 1:
            return None
        source, destination = spec.split(":", 1)
        if (
            not _valid_refspec_ref(source, True)
            or not _valid_refspec_ref(destination, True)
            or not destination.startswith(namespace)
            or source.count("*") != destination.count("*")
        ):
            return None
        candidate = _map_fetch_refspec(source, destination, source_ref)
        if candidate is not None:
            mapped.append(candidate)
    if excluded or len(mapped) != 1:
        return None
    destination = mapped[0]
    if (
        not destination.startswith(namespace)
        or not _valid_refspec_ref(destination, False)
    ):
        return None
    return destination


def _primary_maintenance_git_dirs(cwd_value):
    directories = []
    for option in ("--git-dir", "--git-common-dir"):
        lines = _primary_maintenance_lines(
            _run_primary_maintenance_git(
                cwd_value,
                "rev-parse",
                "--path-format=absolute",
                option,
            )
        )
        if (
            lines is None
            or len(lines) != 1
            or not os.path.isabs(lines[0])
            or not os.path.isdir(lines[0])
        ):
            return None
        directories.append(os.path.realpath(lines[0]))
    return directories[0], directories[1]


def _primary_maintenance_is_idle(git_dir, common_dir, branch):
    paths_to_check = {
        os.path.join(directory, marker)
        for directory in {git_dir, common_dir}
        for marker in _PRIMARY_MAINTENANCE_IN_PROGRESS
    }
    paths_to_check.update(
        {
            os.path.join(git_dir, "index.lock"),
            os.path.join(git_dir, "HEAD.lock"),
            os.path.join(common_dir, "packed-refs.lock"),
            os.path.join(common_dir, "config.lock"),
            os.path.join(common_dir, "shallow.lock"),
            os.path.join(common_dir, "refs", "heads", branch + ".lock"),
        }
    )
    try:
        return not any(os.path.lexists(path) for path in paths_to_check)
    except OSError:
        return None


def _maintenance_result(allowed, kind, reason_code, matched=True):
    return {
        "allowed": allowed,
        "kind": kind,
        "reason_code": reason_code,
        "matched": matched,
    }


def classify_primary_maintenance(command, cwd_value):
    shape = _primary_maintenance_shape(command)
    if not shape["valid"]:
        return _maintenance_result(
            False,
            shape["kind"],
            "unsupported_form",
            shape["matched"],
        )
    if any(
        key in _PRIMARY_MAINTENANCE_RISKY_GIT_ENV
        or key.startswith("GIT_CONFIG_")
        for key in os.environ
    ):
        return _maintenance_result(False, shape["kind"], "inspection_failed")

    branch_result = _run_primary_maintenance_git(
        cwd_value,
        "symbolic-ref",
        "--quiet",
        "HEAD",
    )
    if branch_result is None:
        return _maintenance_result(False, shape["kind"], "inspection_failed")
    if branch_result[0] == 1 and not branch_result[1] and not branch_result[2]:
        return _maintenance_result(False, shape["kind"], "missing_upstream")
    branch_lines = _primary_maintenance_lines(branch_result)
    if (
        branch_lines is None
        or len(branch_lines) != 1
        or not branch_lines[0].startswith("refs/heads/")
        or len(branch_lines[0]) <= len("refs/heads/")
    ):
        return _maintenance_result(False, shape["kind"], "inspection_failed")
    branch = branch_lines[0][len("refs/heads/"):]

    remote_status, remotes = _primary_maintenance_config_values(
        cwd_value,
        "branch.{0}.remote".format(branch),
    )
    merge_status, merge_refs = _primary_maintenance_config_values(
        cwd_value,
        "branch.{0}.merge".format(branch),
    )
    if remote_status == "error" or merge_status == "error":
        return _maintenance_result(False, shape["kind"], "inspection_failed")
    if (
        remote_status != "ok"
        or merge_status != "ok"
        or len(remotes) != 1
        or len(merge_refs) != 1
        or not remotes[0]
        or remotes[0] == "."
        or not _valid_refspec_ref(merge_refs[0], False)
        or not merge_refs[0].startswith("refs/heads/")
    ):
        return _maintenance_result(False, shape["kind"], "missing_upstream")
    remote = remotes[0]
    if (
        any(ord(char) < 32 or ord(char) == 127 for char in remote)
        or any(token in remote for token in ("..", "@{", "\\", ":", "*", "?", "["))
        or remote.startswith(".")
        or remote.endswith("/")
    ):
        return _maintenance_result(False, shape["kind"], "missing_upstream")

    fetch_status, refspecs = _primary_maintenance_config_values(
        cwd_value,
        "remote.{0}.fetch".format(remote),
    )
    if fetch_status == "error":
        return _maintenance_result(False, shape["kind"], "inspection_failed")
    if fetch_status != "ok":
        return _maintenance_result(False, shape["kind"], "unsafe_fetch_config")
    upstream_ref = _safe_fetch_destination(remote, merge_refs[0], refspecs)
    if upstream_ref is None:
        return _maintenance_result(False, shape["kind"], "unsafe_fetch_config")

    upstream_lines = _primary_maintenance_lines(
        _run_primary_maintenance_git(
            cwd_value,
            "rev-parse",
            "--symbolic-full-name",
            "--verify",
            "@{upstream}",
        )
    )
    if (
        upstream_lines is None
        or len(upstream_lines) != 1
        or upstream_lines[0] != upstream_ref
    ):
        return _maintenance_result(False, shape["kind"], "unsafe_fetch_config")
    upstream_oid = _primary_maintenance_lines(
        _run_primary_maintenance_git(
            cwd_value,
            "rev-parse",
            "--verify",
            "{0}^{{commit}}".format(upstream_ref),
        )
    )
    if (
        upstream_oid is None
        or len(upstream_oid) != 1
        or len(upstream_oid[0]) not in (40, 64)
        or re.fullmatch(r"[0-9a-f]+", upstream_oid[0]) is None
    ):
        return _maintenance_result(False, shape["kind"], "unsafe_fetch_config")
    head_oid = _primary_maintenance_lines(
        _run_primary_maintenance_git(
            cwd_value,
            "rev-parse",
            "--verify",
            "HEAD^{commit}",
        )
    )
    if (
        head_oid is None
        or len(head_oid) != 1
        or len(head_oid[0]) not in (40, 64)
        or re.fullmatch(r"[0-9a-f]+", head_oid[0]) is None
    ):
        return _maintenance_result(False, shape["kind"], "inspection_failed")

    short_upstream = upstream_ref[len("refs/remotes/"):]
    if shape["kind"] == "fetch":
        if shape["operand"] and shape["operand"] != remote:
            return _maintenance_result(False, shape["kind"], "wrong_upstream")
    else:
        accepted_operands = {"", "@{u}", "@{upstream}", short_upstream}
        if shape["operand"] not in accepted_operands:
            return _maintenance_result(False, shape["kind"], "wrong_upstream")
        if shape["operand"]:
            explicit_lines = _primary_maintenance_lines(
                _run_primary_maintenance_git(
                    cwd_value,
                    "rev-parse",
                    "--symbolic-full-name",
                    "--verify",
                    shape["operand"],
                )
            )
            if (
                explicit_lines is None
                or len(explicit_lines) != 1
                or explicit_lines[0] != upstream_ref
            ):
                return _maintenance_result(False, shape["kind"], "wrong_upstream")

    git_dirs = _primary_maintenance_git_dirs(cwd_value)
    if git_dirs is None:
        return _maintenance_result(False, shape["kind"], "inspection_failed")
    idle = _primary_maintenance_is_idle(git_dirs[0], git_dirs[1], branch)
    if idle is None:
        return _maintenance_result(False, shape["kind"], "inspection_failed")
    if not idle:
        return _maintenance_result(False, shape["kind"], "busy")

    hidden_index_bits = _primary_maintenance_has_hidden_index_bits(cwd_value)
    if hidden_index_bits is None:
        return _maintenance_result(False, shape["kind"], "inspection_failed")
    if hidden_index_bits:
        return _maintenance_result(False, shape["kind"], "dirty")

    status_result = _run_primary_maintenance_git(
        cwd_value,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    )
    if status_result is None:
        return _maintenance_result(False, shape["kind"], "inspection_failed")
    if status_result[0] != 0 or status_result[2]:
        return _maintenance_result(False, shape["kind"], "inspection_failed")
    if status_result[1]:
        return _maintenance_result(False, shape["kind"], "dirty")

    if shape["kind"] == "fast_forward":
        ancestry = _run_primary_maintenance_git(
            cwd_value,
            "merge-base",
            "--is-ancestor",
            "HEAD",
            upstream_ref,
        )
        if ancestry is None:
            return _maintenance_result(False, shape["kind"], "inspection_failed")
        if ancestry[1] or ancestry[2]:
            return _maintenance_result(False, shape["kind"], "inspection_failed")
        if ancestry[0] == 1:
            return _maintenance_result(False, shape["kind"], "diverged")
        if ancestry[0] != 0:
            return _maintenance_result(False, shape["kind"], "inspection_failed")
    return _maintenance_result(True, shape["kind"], "allowed")


# ---- ADR 0001: target-path-aware mutation scope (parity with engine/guard.py) ------
# NOTE for maintainers: this block lives inside a quoted-delimiter heredoc that is
# itself nested inside command substitution above. Old bash (3.2, still the macOS
# default) has a real parser bug where a bare apostrophe in heredoc text breaks that
# combination even though the delimiter is quoted -- see docs/adr/0001 background.
# Keep every comment/docstring in this heredoc apostrophe-free (write "it is", not
# a contraction); do not reintroduce contractions or possessives here even though
# they would read more naturally.
#
# A precise target-path check may only ever convert an existing `deny` into `allow`
# when every resolved target is affirmatively proven safe; any uncertainty (an
# unresolvable target, a glob metacharacter, an out-of-v1-scope verb) collapses back
# to the existing cwd-only behavior for the WHOLE command (ADR 0001 §1, §4). See
# docs/plans/guard-target-path-precision-v1.md §3.1 for the design.
_PATH_ARG_VERBS = {"rm", "mv", "cp", "mkdir", "rmdir", "ln", "chmod", "chown",
                    "unlink", "shred"}
# Explicitly OUT of scope for v1 (conservative fallback unchanged) -- see ADR 0001 §3:
# install/truncate/dd/tee, all _PKG package-manager verbs, and interpreter -c/-e bodies.


def _has_glob_metachar(s: str) -> bool:
    return any(c in s for c in "*?[")


def _extract_candidate_targets(prog, rest, cwd):
    """Positional (non-flag) arguments for a path-mutating verb, resolved to absolute
    paths. Returns None (extraction not confident -> fall back to cwd-only
    classification for this whole command) when there are no positional args, or ANY
    of them contains a shell glob metacharacter -- never a partial list."""
    if prog in _PATH_ARG_VERBS or (prog in _INPLACE and any(
            a == "-i" or a.startswith("-i") for a in rest)):
        positional = [a for a in rest if not a.startswith("-")]
        if not positional or any(_has_glob_metachar(a) for a in positional):
            return None
        return [a if os.path.isabs(a) else os.path.join(cwd, a) for a in positional]
    return None


_GIT_NO_TARGET_NARROWING = {
    "fetch",
    "push",
    "remote",
    "config",
    "submodule",
}


def _extract_git_target_dirs(global_args, cwd):
    """Resolve every real mutation surface named by git VALIDATED global prefix
    ONLY (the global_args returned by _parse_git_invocation) -- never by
    rescanning family arguments, so a family-local flag (for example
    `git branch -C <dir> copied`) can NEVER be reinterpreted as a global -C
    chdir/target laundering the scope. git honors -C / --git-dir / --work-tree
    simultaneously: -C changes the effective cwd (and the fallback work tree when
    --work-tree is absent); --git-dir names where objects/refs are written;
    --work-tree names where checked-out files land. Returns ALL applicable targets
    (the -C-adjusted cwd, always, plus any explicit --git-dir / --work-tree) so the
    caller must prove EVERY one safe before converting a deny into an allow (ADR
    0001 §4: any single unsafe/unresolved target poisons the whole command).
    global_args is well-formed by construction -- _parse_git_invocation pairs every
    bare -C / --git-dir / --work-tree with its value or returns None -- so indexing
    the value is safe."""
    j, c_path, git_dir, work_tree = 0, cwd, None, None
    while j < len(global_args):
        arg = global_args[j]
        if arg == "-C":
            nxt = global_args[j + 1]
            c_path = nxt if os.path.isabs(nxt) else os.path.join(c_path, nxt)
            j += 2
            continue
        if arg.startswith("--git-dir="):
            git_dir = arg.split("=", 1)[1]
            j += 1
            continue
        if arg == "--git-dir":
            git_dir = global_args[j + 1]
            j += 2
            continue
        if arg.startswith("--work-tree="):
            work_tree = arg.split("=", 1)[1]
            j += 1
            continue
        if arg == "--work-tree":
            work_tree = global_args[j + 1]
            j += 2
            continue
        j += 1
    targets = [c_path]
    if git_dir is not None:
        targets.append(
            git_dir if os.path.isabs(git_dir)
            else os.path.join(c_path, git_dir)
        )
    if work_tree is not None:
        targets.append(
            work_tree if os.path.isabs(work_tree)
            else os.path.join(c_path, work_tree)
        )
    return targets


_MAX_PRECISE_TARGETS = 8  # bound worst-case classification calls per command; more
                          # than this falls back to cwd-only (conservative, cheap check)


def _prog_is_independently_mutating(prog, rest) -> bool:
    """True when PROG ITSELF (irrespective of any co-occurring redirect in the same
    segment) is a recognized mutating trigger per the classify_mutating rules above.

    Needed so an incidental redirect never substitutes for a verb that is, on its
    own, out of v1 scope: e.g. `dd if=x of=<protected file> > /tmp/log` must not be
    judged solely on the harmless stdout redirect -- the unresolved, out-of-scope
    `of=` write target belongs to dd itself and must still poison the whole command
    back to conservative cwd-only handling.
    """
    if prog in _MUT:
        return True
    if prog in _INPLACE and any(a == "-i" or a.startswith("-i") for a in rest):
        return True
    if prog in _PKG and any(a in ("install", "add", "i") for a in rest):
        return True
    if prog in _SCRIPT_BODY_PROGS:
        body = _interpreter_script_body(rest)
        return body is not None and classify_mutating(body)
    return False


def _collect_precise_targets(command, cwd):
    """Per-segment target collection for a command already known to be mutating
    (classify_mutating(command) is True). Returns None when the target(s) of ANY
    mutating segment cannot be confidently resolved -- one command, one decision
    (ADR 0001 §4): a single unscoped mutating segment poisons the whole command
    back to cwd-only classification. Returns a deduped list otherwise."""
    try:
        segs = _segments(command)
    except ValueError:
        return None
    targets = []
    for toks in segs:
        if not _segment_is_mutating(toks):
            continue
        # Redirect targets are already detected by the _segment_is_mutating scan above;
        # fold any real (non-safe) target into the contribution for this segment rather
        # than duplicating the safe-target-suffix logic a second time.
        redirect_targets = []
        has_redirect = False
        for idx, tok in enumerate(toks):
            if tok in _REDIRECT_OPS:
                rtarget = toks[idx + 1] if idx + 1 < len(toks) else ""
                if not rtarget or rtarget.isdigit() or rtarget.startswith(_SAFE_REDIRECT_TARGETS):
                    continue
                has_redirect = True
                if _has_glob_metachar(rtarget):
                    return None
                redirect_targets.append(
                    rtarget if os.path.isabs(rtarget) else os.path.join(cwd, rtarget))
        i = _skip_wrappers(toks)
        if i >= len(toks) or toks[i].startswith("-"):
            return None  # dangling/wrapper-obscured program -- do not guess
        prog = os.path.basename(toks[i])
        rest = toks[i + 1:]
        if prog == "git":
            parsed = _parse_git_invocation(rest)
            if parsed is None:
                return None
            global_args, sub, _sub_args = parsed
            if sub in _GIT_NO_TARGET_NARROWING:
                return None
            targets.extend(_extract_git_target_dirs(global_args, cwd))
            targets.extend(redirect_targets)
            continue
        found = _extract_candidate_targets(prog, rest, cwd)
        if found is not None:
            targets.extend(found)
            targets.extend(redirect_targets)
            continue
        if has_redirect and not _prog_is_independently_mutating(prog, rest):
            # The ONLY mutation signal for this segment is the redirect (the program
            # itself -- e.g. a plain `echo` -- carries no mutation signal on its own);
            # the redirect target fully explains the mutation, so it alone is
            # confident enough to use.
            targets.extend(redirect_targets)
            continue
        # Mutating segment via a verb/package/interpreter-body rule this v1 does not
        # extract precise targets for -- fall back to conservative for the whole
        # command, regardless of any co-occurring redirect on this same segment.
        return None
    deduped = sorted(set(targets))
    return deduped[:_MAX_PRECISE_TARGETS] if len(deduped) <= _MAX_PRECISE_TARGETS else None


resolved = []
for p in paths:
    if not os.path.isabs(p):
        p = os.path.join(workspace, p)
    resolved.append(p)

# Classify once, then compute the two additive decision-layer candidates.
command_is_mutating = classify_mutating(cmd)
maintenance = (
    classify_primary_maintenance(cmd, workspace)
    if command_is_mutating
    else _maintenance_result(False, "none", "unsupported_form", False)
)

# ADR 0001: precise mutation-target candidates for THIS command, resolved against the
# workspace cwd. None means "not confidently resolvable" -- the bash side must fall back
# to the existing cwd-only deny/allow decision unchanged (see check_probe /
# target_is_protected_primary).
mut_targets = _collect_precise_targets(cmd, workspace) if command_is_mutating else None


def _affirmative_context_handle(v):
    """Context fields may be booleans or opaque handles; reject only false-like values."""
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
    if _affirmative_context_handle(src.get("is_background_agent")):
        is_cloud = True
    if _affirmative_context_handle(src.get("cloud_agent_identity_broker")):
        is_cloud = True
if workspace == "/workspace" or workspace.startswith("/workspace/"):
    is_cloud = True
for name in ("CURSOR_BACKGROUND_AGENT", "CURSOR_CLOUD_AGENT", "IS_BACKGROUND_AGENT",
             "is_background_agent", "AWA_FORCE_CLOUD", "cloud_agent_identity_broker",
             "CURSOR_AGENT_IDENTITY_BROKER"):
    if _affirmative_context_handle(os.environ.get(name)):
        is_cloud = True

print("payload_ok=%s" % ("yes" if payload_ok else "no"))
print("cmd=%s" % shlex.quote(cmd))
print("cwd=%s" % shlex.quote(workspace))
print("is_mutating=%s" % ("1" if command_is_mutating else "0"))
print("is_cloud=%s" % ("yes" if is_cloud else "no"))
print("has_paths=%s" % ("yes" if paths else "no"))
print("session_id=%s" % shlex.quote(session_id))
print("paths=(%s)" % " ".join(shlex.quote(p) for p in resolved))
print("has_mut_targets=%s" % ("yes" if mut_targets is not None else "no"))
print("mut_targets=(%s)" % " ".join(shlex.quote(t) for t in (mut_targets or [])))
print("maintenance_allowed=%s" % ("yes" if maintenance["allowed"] else "no"))
print("maintenance_kind=%s" % shlex.quote(maintenance["kind"]))
print("maintenance_reason=%s" % shlex.quote(maintenance["reason_code"]))
print("maintenance_matched=%s" % ("yes" if maintenance["matched"] else "no"))
print(
    "maintenance_message=%s"
    % shlex.quote(_PRIMARY_MAINTENANCE_MESSAGES.get(maintenance["reason_code"], ""))
)
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

# ADR 0001 §2/§4: re-attribute a .git-internal probe to its ENCLOSING work tree
# (byte-for-byte parity with engine/guard.py._reattribute_dotgit_probe). git's own
# --is-inside-work-tree semantics EXCLUDE the .git directory itself, so classify_dir on
# a .git-internal target (cd .git && dev-worktree.sh status) returns a NON-EMPTY
# "classification: not-git" -- the [ -z "$status" ] conservative fallback in
# target_is_protected_primary then never fires and the not-git result was (wrongly)
# trusted as a definitive "not protected", so `rm -rf .git/objects` (or .git,
# .git/config, .git/HEAD, .git/refs, .git/hooks/<name>, .git/worktrees/<name>, ...) on a
# protected primary was ALLOWED. Destroying the object DB / refs / hooks is at least as
# catastrophic as deleting tracked files and, unlike a tracked-file delete,
# IRRECOVERABLE, so AWA's protection boundary MUST include .git/. Return the PARENT of
# the nearest enclosing .git path component -- a genuine work tree that classify_dir
# handles NORMALLY, so the enclosing repo's real include/exclude/advisory
# classification is respected (NOT a blanket deny of every .git-shaped path). No .git
# component -> the probe is returned UNCHANGED (pre-fix behavior for every non-.git
# target). A LINKED worktree's .git is a FILE, which dir_for_probe already redirects to
# the worktree root BEFORE this runs, so a worktree Safe Workspace is never touched.
# python3 performs the normpath walk-up so both mirrors stay byte-identical and a path
# that escapes .git via .. (OUTSIDE .git) is not misattributed.
reattribute_dotgit_probe() {
  DG_PROBE="$1" python3 - <<'PY'
import os
probe = os.environ.get("DG_PROBE", "")
cur = os.path.normpath(probe)
while cur and cur != os.sep:
    if os.path.basename(cur) == ".git":
        print(os.path.dirname(cur) or os.sep)
        break
    cur = os.path.dirname(cur)
else:
    print(probe)
PY
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

# ADR 0001: is $1 (an already-resolved absolute path -- a candidate mutation target,
# not necessarily an edited file) inside a PROTECTED PRIMARY checkout? Mirrors the
# file-edit handler's own dir_for_probe + classify_dir probe below, applied to a
# mutation target instead. Fails CLOSED (treats as protected) when the path looks
# governed but couldn't be classified -- uncertainty must never resolve toward
# allowing an unscoped mutation.
target_is_protected_primary() {
  local target="$1" probe reattr status classification linked
  probe="$(dir_for_probe "$target")"
  [ -n "$probe" ] || return 0
  # A .git-internal target must be attributed to its enclosing work tree (see
  # reattribute_dotgit_probe). Preserve the original probe if reattribution somehow
  # yields nothing, so uncertainty still resolves toward protection, never a silent allow.
  reattr="$(reattribute_dotgit_probe "$probe" 2>/dev/null || true)"
  [ -n "$reattr" ] && probe="$reattr"
  status="$(classify_dir "$probe" || true)"
  if [ -z "$status" ]; then
    included_looking_path "$probe"   # 0 (protected) if plausibly governed, else 1
    return $?
  fi
  classification="$(printf '%s\n' "$status" | awk -F': ' '$1=="classification"{print $2; exit}')"
  linked="$(printf '%s\n' "$status" | awk -F': ' '$1=="linked-worktree"{print $2; exit}')"
  [ "$classification" = "include" ] && [ "$linked" = "no" ]
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

# MAJOR #3: keep an ACTIVELY-USED session's protection ALIVE. sessionStart writes the heartbeat
# once, but a long working session can outlive the 12h TTL (or sessionStart may never have fired),
# after which the canonical disposition flips to STALE and the Safe Workspace becomes freely
# removable even though a live session is using it. Every shell command IS an activity signal, so
# refresh the per-root heartbeat here. THROTTLED to keep the hot path cheap: the common case is a
# single stat() of a stamp file; the git+python refresh runs at most once per throttle window
# (AWA_HEARTBEAT_REFRESH_THROTTLE, default 180s). Best-effort ONLY — every error is swallowed and
# it NEVER changes the gate decision, delays a deny, or takes an OS lock (a deliberate non-goal).
maybe_refresh_active_heartbeat() {
  [ "$event" = "shell" ] || return 0
  [ -f "$AWA_ROOTS_LIB" ] || return 0
  [ -n "$cwd" ] && [ -d "$cwd" ] || return 0
  # FULLY ISOLATED + best-effort. The entire body runs in a subshell whose stdout/stderr are
  # discarded and whose non-zero exit is swallowed, so it can NEVER (a) pollute the guard's JSON
  # stdout, (b) change the gate decision, or (c) fire the parent ERR trap (a subshell does not
  # inherit ERR without errtrace, which the guard does not set). This is why an internal fault —
  # a missing tool, an arithmetic slip, a git error — stays contained and the guard still emits
  # valid JSON. (Regression: a non-numeric stat() result on the 2nd+ command for a cwd once
  # corrupted the guard's stdout in CI.)
  (
    stamp_dir="${XDG_STATE_HOME:-$HOME/.local/state}/awa/roots"
    key="$(printf '%s' "$cwd" | cksum | awk '{print $1"_"$2}')"
    [ -n "$key" ] || exit 0
    stamp="$stamp_dir/.hb-hot-$key"
    throttle="${AWA_HEARTBEAT_REFRESH_THROTTLE:-180}"
    if [ -f "$stamp" ]; then
      now="$(date +%s)"
      # GNU (`-c %Y`) FIRST, then BSD/macOS (`-f %m`). Order matters: on Linux `stat -f` means
      # --file-system and SUCCEEDS with a non-numeric value, so a BSD-first probe would never fall
      # through to the GNU form. Any non-numeric result is forced to 0 (=> treat as expired).
      mtime="$(stat -c %Y "$stamp" 2>/dev/null || stat -f %m "$stamp" 2>/dev/null || echo 0)"
      case "$mtime" in ''|*[!0-9]*) mtime=0 ;; esac
      case "$now" in ''|*[!0-9]*) now=0 ;; esac
      [ "$now" -gt 0 ] && [ "$mtime" -gt 0 ] && [ "$((now - mtime))" -lt "$throttle" ] && exit 0
    fi
    # Throttle elapsed (or first command in this cwd): only NOW pay for git + python.
    top="$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null)" || { mkdir -p "$stamp_dir" 2>/dev/null && : >"$stamp" 2>/dev/null; exit 0; }
    [ -n "$top" ] || exit 0
    gd="$(git -C "$cwd" rev-parse --path-format=absolute --git-dir 2>/dev/null)" || exit 0
    common="$(git -C "$cwd" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" || exit 0
    [ -n "$gd" ] && [ -n "$common" ] || exit 0
    mkdir -p "$stamp_dir" 2>/dev/null || true
    chmod 700 "$stamp_dir" 2>/dev/null || true
    : >"$stamp" 2>/dev/null || true
    # Only a LINKED worktree (Safe Workspace) is heart-beaten; the primary checkout is never a
    # removal target and must not acquire a removal-blocking heartbeat (git-dir == git-common-dir).
    [ "$gd" != "$common" ] || exit 0
    sid="${session_id:-${DEV_SESSION_ID:-}}"
    if [ -z "$sid" ]; then
      sid="$(python3 "$AWA_ROOTS_LIB" current-session-read --root "$top" 2>/dev/null | \
        python3 -c 'import json,sys; print((json.load(sys.stdin).get("current_session") or {}).get("session_id",""))' \
        2>/dev/null || true)"
    fi
    [ -n "$sid" ] || exit 0
    branch="$(git -C "$top" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
    [ -n "$branch" ] && [ "$branch" != "HEAD" ] || exit 0
    python3 "$AWA_ROOTS_LIB" heartbeat --root "$top" --common-dir "$common" \
      --branch "$branch" --session-id "$sid" >/dev/null 2>&1 || true
    exit 0
  ) >/dev/null 2>&1 || true
  return 0
}
maybe_refresh_active_heartbeat

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
    # PM-facing, jargon-free line for the timeline (the operator reads THIS one).
    "plain": ("A change was made straight to your original files. I noticed it right afterward, "
              "but I could only notice it — I wasn't able to stop it in advance. If anything "
              "looks wrong, I can help you get it back."),
    # Internal mechanism note (agent/maintainer-facing; never shown to the operator).
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
  local any_target_protected _t
  status="$(classify_dir "$probe" || true)"
  if [ -z "$status" ]; then
    if included_looking_path "$probe"; then
      respond_ask \
        "I couldn't fully check whether this is safe here, so I paused instead of guessing." \
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
          "I couldn't fully check whether this is safe here, so I paused instead of guessing." \
          "Classifier was unavailable for $probe ($cls_reason). Run '$DEV_WORKTREE status' there, or relaunch in a Safe Workspace via the Cursor Agents-Window Worktree dropdown."
        exit 0
      fi
      # ADRs 0010/0019: fetch and merge stay mutating. Only a command and
      # live-state result proven by the independent embedded inspector allows.
      # Every maintenance-shaped false or unknown result denies here, before
      # ADR 0001 target narrowing. Genuine embedded-Python failure still follows
      # the pre-seeded product-wide fail-open path above.
      if [ "$maintenance_allowed" = "yes" ]; then
        respond_allow
        exit 0
      fi
      if [ "$maintenance_matched" = "yes" ]; then
        respond_deny "$maintenance_message" "$maintenance_message"
        exit 0
      fi
      # ADR 0001: additive narrowing. If every resolved target is confidently outside
      # any protected primary, the command cannot mutate protected content -> allow.
      # Any uncertainty (has_mut_targets=no, or ANY target IS protected) falls through
      # to the existing, unchanged deny below.
      if [ "$has_mut_targets" = "yes" ]; then
        any_target_protected=0
        for _t in "${mut_targets[@]}"; do
          target_is_protected_primary "$_t" && { any_target_protected=1; break; }
        done
        if [ "$any_target_protected" -eq 0 ]; then
          respond_allow
          exit 0
        fi
      fi
      # CONFIRMED mutating command on an included primary -> enforced DENY. Cursor honors deny;
      # ask is non-blocking (L4), so deny is the only shape that actually prevents the mutation.
      respond_deny \
        "I didn't make that change, so nothing in your original files was touched. Let's keep going in a separate safe copy instead." \
        "AWA DENIED a mutating command on an INCLUDED PRIMARY checkout (mode ON). STOP retrying: re-running it — including 'cd <worktree> && <cmd>' or an inline 'DEV_WORKTREE_GUARD_ALLOW_PRIMARY=1 <cmd>' prefix (this hook reads its OWN process env, not the command's inline env) — will be denied again. Recovery is an OPERATOR action: relaunch this agent in a Safe Workspace via the Cursor Agents-Window Worktree dropdown (AWA adopts the linked worktree, then allows), or set DEV_WORKTREE_GUARD_ALLOW_PRIMARY=1 in Cursor's environment/settings and relaunch. Last resort, only if the operator deliberately wants this repo unprotected: '$DEV_WORKTREE mode set <rel> off'."
      exit 0
    fi
    if [ "$payload_ok" != "yes" ]; then
      # Genuine uncertainty (unparseable payload) on an included-looking primary -> ask. An
      # honest no-op: Cursor ignores ask, so we never silently downgrade an uncertain case to
      # allow, but we also never claim ask prevents anything.
      respond_ask \
        "I couldn't tell what this would do, so I paused to be safe." \
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
