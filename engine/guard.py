"""guard.py — minimal local guard: the kernel guarantee with the engine OFF (Phase 5).

This is the load-bearing fallback. With the daemon dead / never started, the guard
still: (1) denies/asks-before primary mutation, (2) refuses unsafe cleanup, and
(3) preserves work — using ONLY atomic policy snapshots + `.awa/lease.json`. It never
requires the SQLite state or the daemon (those are bookkeeping/UX). If state IS
available it opportunistically records a detection, but the decision never depends on it.

Decision surface (mirrors the frozen guard permission schema: allow/ask/deny):
  * mutating shell command on an INCLUDED PRIMARY checkout (not a linked worktree,
    no active lease) -> DENY. Cursor enforces `deny`, but treats `ask` as non-blocking
    (L4), so prevention on the one case that matters uses an enforced deny. Recovery is an
    operator action (relaunch in a Safe Workspace, or the explicit env override).
  * a Cursor Cloud / background agent (isolated own-branch /workspace clone) -> allow
    (degrade-to-allow BEFORE the deny branch; never hard-block an already-isolated VM).
  * anything on an excluded/advisory repo, a linked worktree, or a read-only command
    -> allow.
"""

from __future__ import annotations

import hashlib
import os
import re
import selectors
import shlex
import subprocess
import time
from dataclasses import dataclass

from . import gitutil, lease as lease_mod, policy as policy_mod

_MUT = {"rm", "mv", "cp", "install", "truncate", "dd", "tee", "ln",
        "chmod", "chown", "mkdir", "rmdir", "shred", "unlink"}
_PKG = {"npm", "pnpm", "yarn", "pip", "pip3", "bundle", "poetry", "cargo", "go", "brew", "gem"}
_GITMUT = {"commit", "add", "reset", "rebase", "checkout", "switch", "clean",
           "merge", "cherry-pick", "apply", "restore", "stash", "rm", "mv",
           "pull", "am", "revert", "worktree", "push", "fetch",
           "branch", "remote", "config", "submodule", "sparse-checkout",
           "gc", "maintenance"}
_INPLACE = {"sed", "perl", "gawk", "awk"}
_GIT_TAKES_ARG = ("-C", "-c", "--git-dir", "--work-tree", "--namespace",
                  "--exec-path", "--super-prefix")
_GIT_WORKTREE_READONLY_ACTIONS = {"list"}
_GIT_STASH_READONLY_ACTIONS = {"list", "show"}
_GIT_WORKTREE_LIST_FLAGS = {"--porcelain", "-z", "--verbose", "-v"}
_GIT_STASH_LIST_FLAGS: set[str] = set()
_GIT_STASH_SHOW_FLAGS = {"--stat", "--patch", "-p"}
_GIT_CLEAN_DRY_RUN_FLAGS = {"-n", "--dry-run"}
_GIT_CLEAN_READONLY_FLAGS = {"-n", "--dry-run", "-d", "-x", "-X", "-q"}
_GIT_CLEAN_MUTATING_FLAGS = {"-f", "--force", "-i", "--interactive"}


def _git_subcommand(rest: list[str]) -> tuple[str, list[str]]:
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


def _parse_git_invocation(
        rest: list[str],
) -> tuple[list[str], str, list[str]] | None:
    global_args: list[str] = []
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


def _git_global_args_block_readonly(global_args: list[str]) -> bool:
    return any(
        arg in {"-p", "--paginate", "-c"}
        or (arg.startswith("-c") and len(arg) > 2)
        or arg.startswith("--config-env=")
        for arg in global_args
    )


def _git_exact_nested_action(args: list[str]) -> tuple[str, list[str]]:
    if not args or args[0].startswith("-"):
        return "", args
    return args[0], args[1:]


def _git_flag_name(arg: str) -> str:
    return arg.split("=", 1)[0]


def _git_args_are_known_readonly_flags(args: list[str], allowed: set[str]) -> bool:
    return all(arg in allowed for arg in args)


def _git_worktree_list_is_readonly(args: list[str]) -> bool:
    return _git_args_are_known_readonly_flags(args, _GIT_WORKTREE_LIST_FLAGS)


def _git_stash_list_is_readonly(args: list[str]) -> bool:
    return args == []


def _git_stash_show_is_readonly(args: list[str]) -> bool:
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


def _git_clean_is_readonly(args: list[str]) -> bool:
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


def _git_branch_is_readonly(args: list[str]) -> bool:
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


def _git_remote_is_readonly(args: list[str]) -> bool:
    if not args:
        return True
    i = 0
    if args[i] in ("-v", "--verbose"):
        i += 1
        if i == len(args):
            return True
    if args[i] == "get-url":
        i += 1
        seen_options: set[str] = set()
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


def _git_config_is_readonly(args: list[str]) -> bool:
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


def _git_submodule_is_readonly(args: list[str]) -> bool:
    if not args or args[0] != "status":
        return False
    i = 1
    if i < len(args) and args[i] == "--cached":
        i += 1
    if i == len(args):
        return True
    return args[i] == "--"


def _git_sparse_checkout_is_readonly(args: list[str]) -> bool:
    return args == ["list"]


def _git_is_mutating(rest: list[str]) -> bool:
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
# Prefix wrappers whose OPTIONS (not just their name) must be skipped before we resolve the
# real program. Skipping only the name lets `nice -n 10 git commit`, `env -C /r git commit`,
# `sudo -u root git commit`, `timeout 5 git commit`, `xargs -I{} git commit`, etc. classify
# non-mutating and fast-path ALLOW — a silent bypass of the deny on an included primary.
_PREFIX_WRAPPERS = ("sudo", "command", "nice", "env", "time", "nohup", "xargs",
                    "timeout", "ionice", "chrt", "stdbuf", "builtin", "exec", "doas",
                    "run0", "setsid")
# Per-wrapper VALUE-TAKING options (consume the following token). Leading `-` flags NOT in
# these sets are treated as valueless flags. Long `--opt=value` forms carry their own value.
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
# Shell/script interpreters whose -c/-e body must be recursively classified.
_INTERPRETERS = frozenset({"bash", "sh", "dash", "zsh", "python3", "python", "perl", "ruby", "node"})
_SCRIPT_BODY_PROGS = _INTERPRETERS | frozenset({"script"})
_SCRIPT_OPTS = frozenset({"-c", "-e"})
# Wrappers whose grammar carries a leading POSITIONAL value after their options (timeout
# DURATION, chrt PRIORITY) that must also be consumed before the real program.
_WRAPPER_POSITIONAL = {"timeout", "chrt"}
_CONTROL_OPS = {";", "&&", "||", "&", "|"}
_REDIRECT_OPS = {">", ">>", ">&", "&>", ">|"}
_SAFE_REDIRECT_TARGETS = ("/dev/null", "/dev/stdout", "/dev/stderr")


def _segments(command: str) -> list[list[str]]:
    """Split a shell command into per-sub-command token lists at top-level control
    operators (`;`, `&&`, `||`, `&`, `|`, subshell parens, newlines), respecting
    quoting, so a mutating sub-command can't hide behind a leading read-only one
    (e.g. `git status && git commit -am x`). Raises ValueError on unparseable input
    (unbalanced quotes) so the caller fails safe.
    """
    segs: list[list[str]] = []
    current: list[str] = []
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


def _skip_wrappers(toks: list[str]) -> int:
    """Advance past leading `VAR=value` assignments and prefix wrappers WITH their options,
    returning the index of the resolved program. Option-aware (see _WRAPPER_VALUE_OPTS /
    _WRAPPER_POSITIONAL) so `nice -n 10 git commit`, `env -C /r git commit`, `timeout 5 git
    commit`, `xargs -I {} git commit`, etc. resolve to the REAL program, not a dangling flag.
    """
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
                i += 1  # consume the option's value token
        if i < len(toks) and toks[i] == "--":
            i += 1
        if base in _WRAPPER_POSITIONAL and i < len(toks) \
                and os.path.basename(toks[i]) not in _PREFIX_WRAPPERS \
                and not re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[i]):
            i += 1  # consume the wrapper's positional value (timeout DURATION / chrt PRIORITY)
    return i


def _interpreter_script_body(rest: list[str]) -> str | None:
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


def _rescan_for_mutation(toks: list[str]) -> bool:
    """Conservative backstop: our wrapper-option model left a dangling `-`-prefixed prog, so
    re-scan every token for a known mutating program (git is treated as mutating-capable) and
    flag mutating. Over-denies on an included primary — the desired protection, never a bypass.
    """
    for t in toks:
        b = os.path.basename(t)
        if b in _MUT or b in _PKG or b in _INPLACE or b == "git":
            return True
    return False


def _segment_is_mutating(toks: list[str]) -> bool:
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
    # Backstop: if stripping wrappers left a dangling option (unmodeled wrapper flag), re-scan.
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
    """Adversary-aware mutating-command detector (parity with worktree-guard.sh).

    Segments the command at top-level control operators (`;`, `&&`, `||`, `&`, `|`,
    subshell parens, newlines) and checks every segment, so `git status && git commit`
    or `true; rm -rf x` can't hide a mutation behind a read-only leader. Per-segment,
    catches `git -C <path> commit`, `git -c k=v commit`, `sed -i`, `>`/`>>` redirection
    to a real path, in-place mutators, and package installs. Unparseable -> True (fail
    safe / ask).
    """
    if not command or not command.strip():
        return False
    try:
        segs = _segments(command)
    except ValueError:
        return True
    return any(_segment_is_mutating(toks) for toks in segs)


# ---- ADR 0019: exact protected-primary maintenance lane ---------------------------
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
_PRIMARY_MAINTENANCE_ALLOW_REASONS = {
    "fetch": "clean protected primary: exact configured-upstream fetch maintenance",
    "fast_forward": (
        "clean protected primary: exact configured-upstream fast-forward maintenance"
    ),
}


@dataclass(frozen=True)
class PrimaryMaintenanceDecision:
    allowed: bool
    kind: str
    reason_code: str
    matched: bool


@dataclass(frozen=True)
class _PrimaryMaintenanceShape:
    valid: bool
    kind: str
    operand: str
    matched: bool


@dataclass(frozen=True)
class RepositoryStateToken:
    worktree_root: str
    common_git_dir: str
    head_oid: str
    upstream_name: str
    upstream_oid: str
    maintenance_config_sha256: str
    status_sha256: str
    operation_markers_sha256: str
    hidden_index_sha256: str


@dataclass(frozen=True)
class PrimaryMaintenanceGitContext:
    repository_identity: tuple[str, str]
    session_cwd: str
    branch: str
    upstream: str
    upstream_remote: str
    status_porcelain_v2: bytes
    operation_in_progress: bool
    hidden_index_bits: bool
    head_is_ancestor_of_upstream: bool | None
    state_before: RepositoryStateToken
    state_after: RepositoryStateToken
    errors: tuple[str, ...]
    merge_ref: str
    fetch_refspecs: tuple[str, ...]


def _primary_maintenance_related(command: str, depth: int = 0) -> bool:
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


def _primary_maintenance_shape(command: str) -> _PrimaryMaintenanceShape:
    related = _primary_maintenance_related(command)
    if not command or "\n" in command or "\r" in command:
        return _PrimaryMaintenanceShape(False, "none", "", related)
    bare_git = re.match(r"^\s*git(?:\s|$)", command) is not None
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        lex.commenters = ""
        tokens = list(lex)
    except ValueError:
        return _PrimaryMaintenanceShape(False, "none", "", False)
    if (
        not bare_git
        or not tokens
        or tokens[0] != "git"
        or any(
            token in _CONTROL_OPS
            or token in _REDIRECT_OPS
            or token in {"(", ")", "{", "}"}
            or "$" in token
            or "`" in token
            for token in tokens
        )
    ):
        return _PrimaryMaintenanceShape(False, "none", "", related)
    if len(tokens) >= 2 and tokens[1] == "fetch":
        if len(tokens) == 2:
            return _PrimaryMaintenanceShape(True, "fetch", "", True)
        if len(tokens) == 3 and tokens[2] and not tokens[2].startswith("-"):
            return _PrimaryMaintenanceShape(True, "fetch", tokens[2], True)
        return _PrimaryMaintenanceShape(False, "fetch", "", True)
    if len(tokens) >= 2 and tokens[1] == "merge":
        prefix = ["git", "merge", "--ff-only", "--no-overwrite-ignore"]
        if tokens[:4] != prefix:
            return _PrimaryMaintenanceShape(False, "fast_forward", "", True)
        if len(tokens) == 4:
            return _PrimaryMaintenanceShape(True, "fast_forward", "", True)
        if len(tokens) == 5 and tokens[4] and not tokens[4].startswith("-"):
            return _PrimaryMaintenanceShape(
                True,
                "fast_forward",
                tokens[4],
                True,
            )
        return _PrimaryMaintenanceShape(False, "fast_forward", "", True)
    return _PrimaryMaintenanceShape(False, "none", "", related)


def _run_primary_maintenance_git(
        cwd: str,
        *args: str,
) -> tuple[int, str, str] | None:
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_NO_LAZY_FETCH"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        proc = subprocess.run(
            ["git", "-C", cwd, *args],
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


def _primary_maintenance_has_hidden_index_bits(cwd: str) -> bool | None:
    """Return whether skip-worktree/assume-unchanged can hide tracked edits."""
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_NO_LAZY_FETCH"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        proc = subprocess.Popen(
            ["git", "-C", cwd, "ls-files", "-v", "-z"],
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


def _primary_maintenance_lines(
        result: tuple[int, str, str] | None,
) -> list[str] | None:
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


def _primary_maintenance_config_values(
        cwd: str,
        key: str,
) -> tuple[str, list[str]]:
    result = _run_primary_maintenance_git(cwd, "config", "--get-all", key)
    if result is None:
        return "error", []
    returncode, stdout, stderr = result
    if returncode == 1 and not stdout and not stderr:
        return "missing", []
    lines = _primary_maintenance_lines(result)
    if lines is None:
        return "error", []
    return "ok", lines


def _valid_refspec_ref(ref: str, *, allow_wildcard: bool) -> bool:
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


def _refspec_pattern_matches(pattern: str, ref: str) -> bool:
    if "*" not in pattern:
        return pattern == ref
    prefix, suffix = pattern.split("*", 1)
    return (
        ref.startswith(prefix)
        and ref.endswith(suffix)
        and len(ref) >= len(prefix) + len(suffix)
    )


def _map_fetch_refspec(source: str, destination: str, ref: str) -> str | None:
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


def _safe_fetch_destination(
        remote: str,
        source_ref: str,
        refspecs: list[str],
) -> str | None:
    namespace = "refs/remotes/{0}/".format(remote)
    mapped: list[str] = []
    excluded = False
    for raw in refspecs:
        if not raw or any(ord(char) < 32 or ord(char) == 127 for char in raw):
            return None
        if raw.startswith("^"):
            source = raw[1:]
            if (
                not source
                or ":" in source
                or not _valid_refspec_ref(source, allow_wildcard=True)
            ):
                return None
            excluded = excluded or _refspec_pattern_matches(source, source_ref)
            continue
        spec = raw[1:] if raw.startswith("+") else raw
        if spec.count(":") != 1:
            return None
        source, destination = spec.split(":", 1)
        if (
            not _valid_refspec_ref(source, allow_wildcard=True)
            or not _valid_refspec_ref(destination, allow_wildcard=True)
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
        or not _valid_refspec_ref(destination, allow_wildcard=False)
    ):
        return None
    return destination


def _primary_maintenance_git_dirs(cwd: str) -> tuple[str, str] | None:
    directories: list[str] = []
    for option in ("--git-dir", "--git-common-dir"):
        lines = _primary_maintenance_lines(
            _run_primary_maintenance_git(
                cwd,
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


def _primary_maintenance_is_idle(
        git_dir: str,
        common_dir: str,
        branch: str,
) -> bool | None:
    paths = {
        os.path.join(directory, marker)
        for directory in {git_dir, common_dir}
        for marker in _PRIMARY_MAINTENANCE_IN_PROGRESS
    }
    paths.update(
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
        return not any(os.path.lexists(path) for path in paths)
    except OSError:
        return None


def _primary_maintenance_paths_sha256(paths: list[str]) -> str | None:
    digest = hashlib.sha256()
    try:
        for raw in sorted(paths):
            path = os.path.abspath(raw)
            digest.update(path.encode("utf-8", "surrogateescape"))
            digest.update(b"\x00")
            if not os.path.lexists(path):
                digest.update(b"missing\x00")
                continue
            stat_result = os.lstat(path)
            digest.update(
                "{0}:{1}:{2}:{3}".format(
                    stat_result.st_mode,
                    stat_result.st_size,
                    stat_result.st_mtime_ns,
                    stat_result.st_ino,
                ).encode("ascii")
            )
            digest.update(b"\x00")
            if os.path.isfile(path):
                with open(path, "rb") as handle:
                    while True:
                        chunk = handle.read(65536)
                        if not chunk:
                            break
                        digest.update(chunk)
            digest.update(b"\x00")
    except (OSError, UnicodeError, ValueError):
        return None
    return digest.hexdigest()


def _primary_maintenance_operation_paths(
        git_dir: str,
        common_dir: str,
        branch: str,
) -> list[str]:
    paths = [
        os.path.join(directory, marker)
        for directory in {git_dir, common_dir}
        for marker in _PRIMARY_MAINTENANCE_IN_PROGRESS
    ]
    paths.extend(
        [
            os.path.join(git_dir, "index.lock"),
            os.path.join(git_dir, "HEAD.lock"),
            os.path.join(common_dir, "packed-refs.lock"),
            os.path.join(common_dir, "config.lock"),
            os.path.join(common_dir, "shallow.lock"),
        ]
    )
    if branch:
        paths.append(
            os.path.join(
                common_dir,
                "refs",
                "heads",
                branch + ".lock",
            )
        )
    return paths


def _primary_maintenance_repository_identity(
        cwd: str,
) -> tuple[str, str, str] | None:
    lines = _primary_maintenance_lines(
        _run_primary_maintenance_git(
            cwd,
            "rev-parse",
            "--show-toplevel",
            "--path-format=absolute",
            "--git-dir",
            "--git-common-dir",
        )
    )
    if (
        lines is None
        or len(lines) != 3
        or any(not os.path.isabs(line) for line in lines)
        or not os.path.isdir(lines[0])
        or not os.path.isdir(lines[1])
        or not os.path.isdir(lines[2])
    ):
        return None
    return tuple(os.path.realpath(line) for line in lines)  # type: ignore[return-value]


def _primary_maintenance_status_v2(
        result: tuple[int, str, str] | None,
) -> tuple[bytes, str, str, str, bool] | None:
    if result is None:
        return None
    returncode, stdout, stderr = result
    if returncode != 0 or stderr or not stdout or not stdout.endswith("\x00"):
        return None
    records = stdout[:-1].split("\x00")
    fields: dict[str, str] = {}
    dirty = False
    for record in records:
        if record.startswith("# "):
            name, separator, value = record[2:].partition(" ")
            if not separator or name in fields:
                return None
            fields[name] = value
        else:
            dirty = True
    head_oid = fields.get("branch.oid", "")
    branch = fields.get("branch.head", "")
    upstream = fields.get("branch.upstream", "")
    if (
        len(head_oid) not in (40, 64)
        or re.fullmatch(r"[0-9a-f]+", head_oid) is None
        or not branch
        or branch == "(detached)"
        or not upstream
        or upstream.startswith(".")
        or upstream.endswith("/")
    ):
        return None
    upstream_ref = "refs/remotes/" + upstream
    if not _valid_refspec_ref(
        "refs/heads/" + branch,
        allow_wildcard=False,
    ) or not _valid_refspec_ref(upstream_ref, allow_wildcard=False):
        return None
    return (
        stdout.encode("utf-8", "surrogateescape"),
        branch,
        upstream_ref,
        head_oid,
        dirty,
    )


def _primary_maintenance_read_ref(
        common_dir: str,
        ref: str,
) -> str | None:
    if not _valid_refspec_ref(ref, allow_wildcard=False):
        return None
    loose = os.path.join(common_dir, *ref.split("/"))
    try:
        if os.path.isfile(loose):
            with open(loose, "r", encoding="ascii") as handle:
                value = handle.read(129)
            oid = value.strip()
            if len(value) > 128:
                return None
            if (
                len(oid) in (40, 64)
                and re.fullmatch(r"[0-9a-f]+", oid) is not None
            ):
                return oid
            return None
        packed = os.path.join(common_dir, "packed-refs")
        if not os.path.isfile(packed):
            return None
        with open(packed, "r", encoding="ascii") as handle:
            for line in handle:
                if line.startswith(("#", "^")):
                    continue
                oid, separator, name = line.rstrip("\n").partition(" ")
                if separator and name == ref:
                    if (
                        len(oid) in (40, 64)
                        and re.fullmatch(r"[0-9a-f]+", oid) is not None
                    ):
                        return oid
                    return None
    except (OSError, UnicodeError):
        return None
    return None


def _capture_primary_maintenance_state(
        cwd: str,
        worktree_root: str,
        git_dir: str,
        common_dir: str,
) -> tuple[RepositoryStateToken, bytes, bool, bool] | None:
    config_paths = [
        os.path.join(common_dir, "config"),
        os.path.join(git_dir, "config.worktree"),
    ]
    index_paths = [os.path.join(git_dir, "index")]
    generic_operation_paths = _primary_maintenance_operation_paths(
        git_dir,
        common_dir,
        "",
    )
    pre_config_sha256 = _primary_maintenance_paths_sha256(config_paths)
    pre_operation_sha256 = _primary_maintenance_paths_sha256(
        generic_operation_paths
    )
    pre_index_sha256 = _primary_maintenance_paths_sha256(index_paths)
    if (
        pre_config_sha256 is None
        or pre_operation_sha256 is None
        or pre_index_sha256 is None
    ):
        return None
    status = _primary_maintenance_status_v2(
        _run_primary_maintenance_git(
            cwd,
            "status",
            "--porcelain=v2",
            "-z",
            "--branch",
            "--untracked-files=all",
        )
    )
    if status is None:
        return None
    status_bytes, branch, upstream_ref, head_oid, dirty = status
    head_ref_oid = _primary_maintenance_read_ref(
        common_dir,
        "refs/heads/" + branch,
    )
    upstream_oid = _primary_maintenance_read_ref(common_dir, upstream_ref)
    config_sha256 = _primary_maintenance_paths_sha256(config_paths)
    operation_sha256 = _primary_maintenance_paths_sha256(
        _primary_maintenance_operation_paths(git_dir, common_dir, branch)
    )
    generic_operation_sha256 = _primary_maintenance_paths_sha256(
        generic_operation_paths
    )
    hidden_index_sha256 = _primary_maintenance_paths_sha256(index_paths)
    if (
        head_ref_oid is None
        or upstream_oid is None
        or config_sha256 is None
        or operation_sha256 is None
        or generic_operation_sha256 is None
        or hidden_index_sha256 is None
    ):
        return None
    token = RepositoryStateToken(
        worktree_root=worktree_root,
        common_git_dir=common_dir,
        head_oid=head_oid,
        upstream_name=upstream_ref,
        upstream_oid=upstream_oid,
        maintenance_config_sha256=config_sha256,
        status_sha256=hashlib.sha256(status_bytes).hexdigest(),
        operation_markers_sha256=operation_sha256,
        hidden_index_sha256=hidden_index_sha256,
    )
    stable = (
        head_ref_oid == head_oid
        and pre_config_sha256 == config_sha256
        and pre_operation_sha256 == generic_operation_sha256
        and pre_index_sha256 == hidden_index_sha256
    )
    return token, status_bytes, dirty, stable


def _primary_maintenance_config_map(
        cwd: str,
) -> dict[str, list[str]] | None:
    result = _run_primary_maintenance_git(cwd, "config", "--null", "--list")
    if result is None:
        return None
    returncode, stdout, stderr = result
    if returncode != 0 or stderr or not stdout.endswith("\x00"):
        return None
    values: dict[str, list[str]] = {}
    for record in stdout[:-1].split("\x00"):
        key, separator, value = record.partition("\n")
        if not separator or not key:
            return None
        values.setdefault(key.lower(), []).append(value)
    return values


def _collect_primary_maintenance_context(
        cwd: str,
        shape: _PrimaryMaintenanceShape,
        repository_context: gitutil.RepoContext | None = None,
) -> PrimaryMaintenanceGitContext | None:
    if not shape.valid:
        return None
    if repository_context is None:
        identity = _primary_maintenance_repository_identity(cwd)
        if identity is None:
            return None
        seed_branch = None
        seed_head = None
    else:
        if (
            not repository_context.is_git
            or not repository_context.toplevel
            or not repository_context.git_dir
            or not repository_context.common_dir
            or not repository_context.branch
            or not repository_context.head
        ):
            return None
        identity = (
            os.path.realpath(repository_context.toplevel),
            os.path.realpath(repository_context.git_dir),
            os.path.realpath(repository_context.common_dir),
        )
        if (
            any(not os.path.isabs(path) for path in identity)
            or any(not os.path.isdir(path) for path in identity)
        ):
            return None
        seed_branch = repository_context.branch
        seed_head = repository_context.head
    worktree_root, git_dir, common_dir = identity
    before_capture = _capture_primary_maintenance_state(
        cwd,
        worktree_root,
        git_dir,
        common_dir,
    )
    if before_capture is None:
        return None
    state_before, status_bytes, dirty, before_stable = before_capture
    upstream = state_before.upstream_name
    branch_name = _primary_maintenance_status_v2(
        (0, status_bytes.decode("utf-8", "surrogateescape"), "")
    )
    if branch_name is None:
        return None
    _status, local_branch, upstream_ref, _head, _is_dirty = branch_name
    config = _primary_maintenance_config_map(cwd)
    if config is None:
        return None
    remote_values = config.get(
        "branch.{0}.remote".format(local_branch).lower(),
        [],
    )
    merge_refs = config.get(
        "branch.{0}.merge".format(local_branch).lower(),
        [],
    )
    if len(remote_values) != 1 or len(merge_refs) != 1:
        return None
    remote = remote_values[0]
    fetch_refspecs = tuple(
        config.get("remote.{0}.fetch".format(remote).lower(), [])
    )
    idle = _primary_maintenance_is_idle(
        git_dir,
        common_dir,
        local_branch,
    )
    if idle is None:
        return None
    if dirty or not idle:
        hidden_index_bits = False
    else:
        hidden_index_bits = _primary_maintenance_has_hidden_index_bits(cwd)
        if hidden_index_bits is None:
            return None
    ancestry: bool | None = None
    if shape.kind == "fast_forward":
        result = _run_primary_maintenance_git(
            cwd,
            "merge-base",
            "--is-ancestor",
            "HEAD",
            upstream_ref,
        )
        if result is None or result[1] or result[2] or result[0] not in (0, 1):
            return None
        ancestry = result[0] == 0
    after_capture = _capture_primary_maintenance_state(
        cwd,
        worktree_root,
        git_dir,
        common_dir,
    )
    if after_capture is None:
        return None
    state_after, _after_status, _after_dirty, after_stable = after_capture
    errors: tuple[str, ...] = ()
    if (
        state_before != state_after
        or not before_stable
        or not after_stable
        or (seed_branch is not None and seed_branch != local_branch)
        or (seed_head is not None and seed_head != state_before.head_oid)
    ):
        errors = ("state_changed",)
    return PrimaryMaintenanceGitContext(
        repository_identity=(worktree_root, common_dir),
        session_cwd=os.path.realpath(cwd),
        branch=local_branch,
        upstream=upstream,
        upstream_remote=remote,
        status_porcelain_v2=status_bytes,
        operation_in_progress=not idle,
        hidden_index_bits=hidden_index_bits,
        head_is_ancestor_of_upstream=ancestry,
        state_before=state_before,
        state_after=state_after,
        errors=errors,
        merge_ref=merge_refs[0],
        fetch_refspecs=fetch_refspecs,
    )


def _maintenance_result(
        allowed: bool,
        kind: str,
        reason_code: str,
        matched: bool = True,
) -> PrimaryMaintenanceDecision:
    return PrimaryMaintenanceDecision(allowed, kind, reason_code, matched)


def _classify_primary_maintenance_uncached(
        command: str,
        cwd: str,
) -> PrimaryMaintenanceDecision:
    """Prove the exact command and local state needed for ADR 0019 maintenance."""
    shape = _primary_maintenance_shape(command)
    if not shape.valid:
        return _maintenance_result(
            False,
            shape.kind,
            "unsupported_form",
            shape.matched,
        )
    if any(
        key in _PRIMARY_MAINTENANCE_RISKY_GIT_ENV
        or key.startswith("GIT_CONFIG_")
        for key in os.environ
    ):
        return _maintenance_result(False, shape.kind, "inspection_failed")

    branch_result = _run_primary_maintenance_git(
        cwd,
        "symbolic-ref",
        "--quiet",
        "HEAD",
    )
    if branch_result is None:
        return _maintenance_result(False, shape.kind, "inspection_failed")
    if branch_result[0] == 1 and not branch_result[1] and not branch_result[2]:
        return _maintenance_result(False, shape.kind, "missing_upstream")
    branch_lines = _primary_maintenance_lines(branch_result)
    if (
        branch_lines is None
        or len(branch_lines) != 1
        or not branch_lines[0].startswith("refs/heads/")
        or len(branch_lines[0]) <= len("refs/heads/")
    ):
        return _maintenance_result(False, shape.kind, "inspection_failed")
    branch = branch_lines[0][len("refs/heads/"):]

    remote_status, remotes = _primary_maintenance_config_values(
        cwd,
        "branch.{0}.remote".format(branch),
    )
    merge_status, merge_refs = _primary_maintenance_config_values(
        cwd,
        "branch.{0}.merge".format(branch),
    )
    if remote_status == "error" or merge_status == "error":
        return _maintenance_result(False, shape.kind, "inspection_failed")
    if (
        remote_status != "ok"
        or merge_status != "ok"
        or len(remotes) != 1
        or len(merge_refs) != 1
        or not remotes[0]
        or remotes[0] == "."
        or not _valid_refspec_ref(merge_refs[0], allow_wildcard=False)
        or not merge_refs[0].startswith("refs/heads/")
    ):
        return _maintenance_result(False, shape.kind, "missing_upstream")
    remote = remotes[0]
    if (
        any(ord(char) < 32 or ord(char) == 127 for char in remote)
        or any(token in remote for token in ("..", "@{", "\\", ":", "*", "?", "["))
        or remote.startswith(".")
        or remote.endswith("/")
    ):
        return _maintenance_result(False, shape.kind, "missing_upstream")

    fetch_status, refspecs = _primary_maintenance_config_values(
        cwd,
        "remote.{0}.fetch".format(remote),
    )
    if fetch_status == "error":
        return _maintenance_result(False, shape.kind, "inspection_failed")
    if fetch_status != "ok":
        return _maintenance_result(False, shape.kind, "unsafe_fetch_config")
    upstream_ref = _safe_fetch_destination(remote, merge_refs[0], refspecs)
    if upstream_ref is None:
        return _maintenance_result(False, shape.kind, "unsafe_fetch_config")

    upstream_lines = _primary_maintenance_lines(
        _run_primary_maintenance_git(
            cwd,
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
        return _maintenance_result(False, shape.kind, "unsafe_fetch_config")
    upstream_oid = _primary_maintenance_lines(
        _run_primary_maintenance_git(
            cwd,
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
        return _maintenance_result(False, shape.kind, "unsafe_fetch_config")
    head_oid = _primary_maintenance_lines(
        _run_primary_maintenance_git(
            cwd,
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
        return _maintenance_result(False, shape.kind, "inspection_failed")

    short_upstream = upstream_ref[len("refs/remotes/"):]
    if shape.kind == "fetch":
        if shape.operand and shape.operand != remote:
            return _maintenance_result(False, shape.kind, "wrong_upstream")
    else:
        accepted_operands = {"", "@{u}", "@{upstream}", short_upstream}
        if shape.operand not in accepted_operands:
            return _maintenance_result(False, shape.kind, "wrong_upstream")
        if shape.operand:
            explicit_lines = _primary_maintenance_lines(
                _run_primary_maintenance_git(
                    cwd,
                    "rev-parse",
                    "--symbolic-full-name",
                    "--verify",
                    shape.operand,
                )
            )
            if (
                explicit_lines is None
                or len(explicit_lines) != 1
                or explicit_lines[0] != upstream_ref
            ):
                return _maintenance_result(False, shape.kind, "wrong_upstream")

    git_dirs = _primary_maintenance_git_dirs(cwd)
    if git_dirs is None:
        return _maintenance_result(False, shape.kind, "inspection_failed")
    idle = _primary_maintenance_is_idle(git_dirs[0], git_dirs[1], branch)
    if idle is None:
        return _maintenance_result(False, shape.kind, "inspection_failed")
    if not idle:
        return _maintenance_result(False, shape.kind, "busy")

    hidden_index_bits = _primary_maintenance_has_hidden_index_bits(cwd)
    if hidden_index_bits is None:
        return _maintenance_result(False, shape.kind, "inspection_failed")
    if hidden_index_bits:
        return _maintenance_result(False, shape.kind, "dirty")

    status_result = _run_primary_maintenance_git(
        cwd,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    )
    if status_result is None:
        return _maintenance_result(False, shape.kind, "inspection_failed")
    if status_result[0] != 0 or status_result[2]:
        return _maintenance_result(False, shape.kind, "inspection_failed")
    if status_result[1]:
        return _maintenance_result(False, shape.kind, "dirty")

    if shape.kind == "fast_forward":
        ancestry = _run_primary_maintenance_git(
            cwd,
            "merge-base",
            "--is-ancestor",
            "HEAD",
            upstream_ref,
        )
        if ancestry is None:
            return _maintenance_result(False, shape.kind, "inspection_failed")
        if ancestry[1] or ancestry[2]:
            return _maintenance_result(False, shape.kind, "inspection_failed")
        if ancestry[0] == 1:
            return _maintenance_result(False, shape.kind, "diverged")
        if ancestry[0] != 0:
            return _maintenance_result(False, shape.kind, "inspection_failed")
    return _maintenance_result(True, shape.kind, "allowed")


def _classify_primary_maintenance_context(
        shape: _PrimaryMaintenanceShape,
        context: PrimaryMaintenanceGitContext,
) -> PrimaryMaintenanceDecision:
    if (
        context.errors
        or context.state_before != context.state_after
        or context.repository_identity
        != (
            context.state_before.worktree_root,
            context.state_before.common_git_dir,
        )
        or context.session_cwd != os.path.realpath(context.session_cwd)
        or context.branch == ""
        or context.upstream != context.state_before.upstream_name
        or context.state_before.head_oid != context.state_after.head_oid
        or context.state_before.upstream_oid != context.state_after.upstream_oid
    ):
        return _maintenance_result(False, shape.kind, "inspection_failed")
    remote = context.upstream_remote
    merge_ref = context.merge_ref
    if (
        not remote
        or remote == "."
        or not _valid_refspec_ref(merge_ref, allow_wildcard=False)
        or not merge_ref.startswith("refs/heads/")
    ):
        return _maintenance_result(False, shape.kind, "missing_upstream")
    if (
        any(ord(char) < 32 or ord(char) == 127 for char in remote)
        or any(token in remote for token in ("..", "@{", "\\", ":", "*", "?", "["))
        or remote.startswith(".")
        or remote.endswith("/")
    ):
        return _maintenance_result(False, shape.kind, "missing_upstream")
    upstream_ref = _safe_fetch_destination(
        remote,
        merge_ref,
        list(context.fetch_refspecs),
    )
    if upstream_ref is None or upstream_ref != context.upstream:
        return _maintenance_result(False, shape.kind, "unsafe_fetch_config")
    for oid, reason in (
        (context.state_after.upstream_oid, "unsafe_fetch_config"),
        (context.state_after.head_oid, "inspection_failed"),
    ):
        if (
            len(oid) not in (40, 64)
            or re.fullmatch(r"[0-9a-f]+", oid) is None
        ):
            return _maintenance_result(False, shape.kind, reason)
    short_upstream = upstream_ref[len("refs/remotes/"):]
    if shape.kind == "fetch":
        if shape.operand and shape.operand != remote:
            return _maintenance_result(False, shape.kind, "wrong_upstream")
    else:
        if shape.operand not in {"", "@{u}", "@{upstream}", short_upstream}:
            return _maintenance_result(False, shape.kind, "wrong_upstream")
    if context.operation_in_progress:
        return _maintenance_result(False, shape.kind, "busy")
    if context.hidden_index_bits:
        return _maintenance_result(False, shape.kind, "dirty")
    parsed_status = _primary_maintenance_status_v2(
        (
            0,
            context.status_porcelain_v2.decode(
                "utf-8",
                "surrogateescape",
            ),
            "",
        )
    )
    if parsed_status is None:
        return _maintenance_result(False, shape.kind, "inspection_failed")
    if parsed_status[4]:
        return _maintenance_result(False, shape.kind, "dirty")
    if shape.kind == "fast_forward":
        if context.head_is_ancestor_of_upstream is None:
            return _maintenance_result(False, shape.kind, "inspection_failed")
        if not context.head_is_ancestor_of_upstream:
            return _maintenance_result(False, shape.kind, "diverged")
    return _maintenance_result(True, shape.kind, "allowed")


def classify_primary_maintenance(
        command: str,
        cwd: str,
        repository_context: gitutil.RepoContext | None = None,
) -> PrimaryMaintenanceDecision:
    """Use one invocation-local context or preserve the uncached decision."""

    shape = _primary_maintenance_shape(command)
    if not shape.valid:
        return _maintenance_result(
            False,
            shape.kind,
            "unsupported_form",
            shape.matched,
        )
    if any(
        key in _PRIMARY_MAINTENANCE_RISKY_GIT_ENV
        or key.startswith("GIT_CONFIG_")
        for key in os.environ
    ):
        return _maintenance_result(False, shape.kind, "inspection_failed")
    context = _collect_primary_maintenance_context(
        cwd,
        shape,
        repository_context,
    )
    if context is None:
        return _classify_primary_maintenance_uncached(command, cwd)
    return _classify_primary_maintenance_context(shape, context)


# ---- ADR 0001: target-path-aware mutation scope -----------------------------------
# A precise target-path check may only ever convert an existing `deny` into `allow`
# when every resolved target is affirmatively proven safe; any uncertainty (an
# unresolvable target, a glob metacharacter, an out-of-v1-scope verb) collapses back
# to today's cwd-only behavior for the WHOLE command (ADR 0001 §1, §4). See the
# companion plan (docs/plans/guard-target-path-precision-v1.md) §3.1 for the design.
_PATH_ARG_VERBS = {"rm", "mv", "cp", "mkdir", "rmdir", "ln", "chmod", "chown",
                    "unlink", "shred"}
# Explicitly OUT of scope for v1 (conservative fallback unchanged) -- see ADR 0001 §3:
# "install", "truncate", "dd", "tee" (ambiguous/key-value argument shapes), all _PKG
# package-manager verbs (cwd-relative mutation with no explicit path argument -- cwd-based
# classification is already correct for these, not a gap), and interpreter -c/-e bodies
# (recursion already exists via classify_mutating; left conservative for v1, see §6).


def _has_glob_metachar(s: str) -> bool:
    return any(c in s for c in "*?[")


def _extract_candidate_targets(prog, rest, cwd):
    """Positional (non-flag) arguments for a path-mutating verb, resolved to absolute
    paths. Returns None (== "extraction not confident, fall back to cwd-only
    classification for this whole command") when there are no positional args, or
    when ANY of them contains a shell glob metacharacter (cannot be resolved without
    actually running the shell) -- never a partial list."""
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


def _extract_git_target_dirs(global_args: list[str], cwd: str) -> list[str]:
    """Resolve every real mutation surface named by git's VALIDATED global prefix only
    (the `global_args` returned by _parse_git_invocation) -- never by rescanning family
    arguments, so a family-local flag (e.g. `git branch -C <dir> copied`) can NEVER be
    reinterpreted as a global `-C` chdir/target laundering the scope. git honors -C /
    --git-dir / --work-tree simultaneously: -C changes git's effective cwd (and the
    fallback work tree when --work-tree is absent); --git-dir names where objects/refs
    are written; --work-tree names where checked-out files land. Returns ALL applicable
    targets (the -C-adjusted cwd, always, plus any explicit --git-dir / --work-tree) so
    the caller must prove EVERY one safe before converting a deny into an allow (ADR 0001
    §4: any single unsafe/unresolved target poisons the whole command). global_args is
    well-formed by construction -- _parse_git_invocation pairs every bare -C / --git-dir
    / --work-tree with its value or returns None -- so indexing the value is safe."""
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


def _prog_is_independently_mutating(prog: str, rest: list[str]) -> bool:
    """True when PROG ITSELF (irrespective of any co-occurring redirect in the same
    segment) is a recognized mutating trigger per classify_mutating's own rules.

    Needed so an incidental redirect never stands in for a verb's OWN out-of-v1-scope
    target: e.g. `dd if=x of=<protected file> > /tmp/log` must not be judged solely on
    the harmless stdout redirect -- dd's own (unresolved, out-of-scope) `of=` write
    target must still poison the whole command back to conservative cwd-only handling.
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
    (classify_mutating(command) is True). Returns None when ANY mutating segment's
    target(s) cannot be confidently resolved -- one command, one decision (ADR 0001
    §4): a single unscoped mutating segment poisons the whole command back to
    cwd-only classification. Returns a deduped list (possibly empty only if there
    were zero mutating segments, which cannot happen given the precondition) otherwise."""
    try:
        segs = _segments(command)
    except ValueError:
        return None
    targets = []
    for toks in segs:
        if not _segment_is_mutating(toks):
            continue
        # Redirect targets are already detected by _segment_is_mutating's own scan;
        # fold any real (non-safe) target into this segment's contribution rather than
        # duplicating the safe-target-suffix logic a second time.
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
            # This segment's ONLY mutation signal is the redirect (the program itself
            # -- e.g. a plain `echo` -- carries none of its own); the redirect target
            # fully explains the mutation, so it alone is confident enough to use.
            targets.extend(redirect_targets)
            continue
        # Mutating segment via a verb/package/interpreter-body rule this v1 does not
        # extract precise targets for (ADR 0001 §3: install/truncate/dd/tee, a _PKG
        # install, or an interpreter -c/-e body) -- fall back to conservative for the
        # whole command, regardless of any co-occurring redirect on this same segment.
        return None
    deduped = sorted(set(targets))
    return deduped[:_MAX_PRECISE_TARGETS] if len(deduped) <= _MAX_PRECISE_TARGETS else None


@dataclass
class Decision:
    permission: str  # allow | ask | deny
    reason: str
    classification: str = ""


def _allow(reason: str, cls: str = "") -> Decision:
    return Decision("allow", reason, cls)


# The recovery guidance surfaced on a DENY. Reworked around the observed platform facts:
# the hook reads its OWN process env (an inline `DEV_WORKTREE_GUARD_ALLOW_PRIMARY=1 <cmd>`
# prefix does NOT reach it), `cd <worktree> && <cmd>` is still on the primary, and
# `move_agent_to_root` is observed-broken for AWA worktrees (finding R-A) — so it is NOT
# offered. Recovery is an operator action; `mode set ... off` is a deliberate last resort.
_DENY_REASON = (
    "AWA DENIED a mutating command on an INCLUDED PRIMARY checkout (mode ON). STOP retrying: "
    "re-running it — including `cd <worktree> && <cmd>` or an inline "
    "`DEV_WORKTREE_GUARD_ALLOW_PRIMARY=1 <cmd>` prefix (the hook reads its own env, not the "
    "command's inline env) — will be denied again. Recovery is an OPERATOR action: relaunch "
    "this agent in a Safe Workspace via the Cursor Agents-Window Worktree dropdown (AWA adopts "
    "the linked worktree, then allows), or set DEV_WORKTREE_GUARD_ALLOW_PRIMARY=1 in Cursor's "
    "environment/settings and relaunch. Last resort, only if the operator deliberately wants "
    "this repo unprotected: `dev-worktree.sh mode set <rel> off`."
)

# Env vars that mark a Cursor Cloud / background agent. A *_broker var counts by PRESENCE
# (its value is a handle/path); the boolean flags count only when truthy.
_CLOUD_ENV_FLAGS = (
    "CURSOR_BACKGROUND_AGENT", "CURSOR_CLOUD_AGENT", "IS_BACKGROUND_AGENT",
    "is_background_agent", "cloud_agent_identity_broker", "CURSOR_AGENT_IDENTITY_BROKER",
    "AWA_FORCE_CLOUD",
)


def _affirmative_context_handle(val) -> bool:
    """Both context fields may carry booleans or opaque handles; reject only false-like values."""
    if val is None:
        return False
    if val is False or val == 0:
        return False
    if isinstance(val, (list, dict)) and not val:
        return False
    s = str(val).strip()
    if not s:
        return False
    if s.lower() in ("false", "0", "no", "off"):
        return False
    return True


def _is_cloud(cwd: str) -> bool:
    """Detect a Cursor Cloud / background agent so the guard degrades to ALLOW *before* any
    deny branch. Cloud VMs are already-isolated, own-branch `/workspace` clones — hard-blocking
    one would brick a legitimate isolated workspace, and it never mutates a shared primary.
    Signals (any): a truthy background-agent env flag, an affirmative identity-broker handle,
    or a `/workspace` root.
    """
    for name in _CLOUD_ENV_FLAGS:
        val = os.environ.get(name)
        if val is None:
            continue
        if _affirmative_context_handle(val):
            return True
    top = os.path.abspath(cwd or "")
    return top == "/workspace" or top.startswith("/workspace" + os.sep)


def _probe_dir(path: str) -> str:
    """Mirrors dir_for_probe() in kernel/hooks/worktree-guard.sh: `git -C` requires an
    actual directory, so a FILE target (the common case -- e.g. `rm -f file.txt`,
    existing or not) must be probed via its parent directory, never itself, or
    gitutil.resolve() silently reports is_git=False for every such target regardless
    of whether it is really inside a protected checkout (verified: `git -C
    <file-path>` fails with "cannot change to ... Not a directory" / "No such file or
    directory" for both an existing file and a not-yet-created one)."""
    return path if os.path.isdir(path) else (os.path.dirname(path) or path)


def _reattribute_dotgit_probe(probe: str) -> str:
    """Redirect a `.git`-internal probe to its ENCLOSING work tree, so a mutation
    aimed at git's own metadata is attributed to the repo that actually owns it.
    Mirrored byte-for-byte by reattribute_dotgit_probe() in
    kernel/hooks/worktree-guard.sh (parity is contract-enforced).

    git's own `--is-inside-work-tree` semantics (which gitutil.resolve mirrors)
    EXCLUDE the `.git` directory itself: `git -C <repo>/.git rev-parse
    --show-toplevel` fails with "this operation must be run in a work tree", so
    gitutil.resolve(<repo>/.git) reports is_git=False. That is correct GIT semantics
    but the WRONG question for a mutation-safety boundary -- `rm -rf .git/objects`
    (or `.git`, `.git/config`, `.git/HEAD`, `.git/refs`, `.git/hooks/<name>`,
    `.git/worktrees/<name>`, ...) destroys the object DB / refs / hooks of the
    enclosing repo: at least as catastrophic as deleting tracked files and, unlike a
    tracked-file delete, IRRECOVERABLE. AWA's protection boundary must therefore
    INCLUDE `.git/` (ADR 0001 §2: the unit of protection is "some protected primary",
    and §1: uncertainty resolves toward protection).

    Behavior: if `probe` is a `.git` directory itself or lies inside one, return the
    PARENT of the nearest enclosing `.git` path component -- a genuine work-tree root
    that gitutil.resolve / policy.classify handle NORMALLY, so the enclosing repo's
    real include/exclude/advisory classification is respected (NOT a blanket deny of
    every `.git`-shaped path -- a `.git`-internal target inside an advisory/excluded
    repo still resolves to allow). When there is no `.git` component, return `probe`
    UNCHANGED -- byte-for-byte the pre-fix behavior for every non-`.git` target.

    Two subtleties:
    * A LINKED worktree's `.git` is a FILE (a `gitdir:` pointer), which _probe_dir
      already redirects to the worktree root BEFORE this runs -- so a worktree's
      `.git` never reaches here as a `.git` component, and its (correct, unprotected)
      Safe-Workspace classification is unaffected (ADR 0001 requirement 3).
    * normpath first: a target like `.git/../outside` names a path OUTSIDE `.git`, so
      it must NOT be reattributed; collapsing `.`/`..` ensures only a genuinely
      `.git`-internal probe is redirected (git itself collapses the `..` when the
      unchanged probe is later resolved)."""
    cur = os.path.normpath(probe)
    while cur and cur != os.sep:
        if os.path.basename(cur) == ".git":
            return os.path.dirname(cur) or os.sep
        cur = os.path.dirname(cur)
    return probe


def _path_looks_governed(path: str, cfg: policy_mod.PolicyConfig) -> bool:
    """Mirrors included_looking_path() in kernel/hooks/worktree-guard.sh: a pure
    path-string containment check against the policy's configured governed roots
    (realpath-normalized, matching _is_standalone's symlink handling). Used ONLY as
    the fail-closed fallback in _path_is_protected_primary when the probe directory
    cannot be checked via git at all -- never a substitute for real classification."""
    p = os.path.realpath(os.path.expanduser(path))
    for gr in cfg.governed_roots:
        gr_abs = os.path.realpath(os.path.expanduser(gr))
        if p == gr_abs or p.startswith(gr_abs + os.sep):
            return True
    return False


def _path_is_protected_primary(path: str, cfg: policy_mod.PolicyConfig) -> bool:
    """Is `path` (an already-resolved absolute candidate mutation target) inside a
    PROTECTED PRIMARY checkout? Mirrors decide_shell's own primary-classification
    steps (ADR 0001 §2: the unit of protection is "some protected primary", not just
    the cwd's own repo) -- reuses gitutil.resolve / lease_mod.read_lease /
    policy_mod.classify rather than reimplementing policy logic a second time.

    Every git-adapter call below (_hooks_path/_origin, not just gitutil.resolve) is
    made against `probe` -- a directory, never the raw (possibly-file) `path` -- and
    once resolved, against `ctx.toplevel` specifically. `git -C <file>` always fails
    (128, "Not a directory"), which would otherwise make _origin()/_hooks_path()
    silently return "" for the common file-target case (e.g. `rm -f tracked-file`),
    forcing classify()'s "no origin remote" branch to fire and misclassify an
    INCLUDED primary as ADVISORY -- silently turning off protection for exactly the
    files this fix must keep protecting. See docs/adr/0001 §2 and the
    test_precise_target_inside_same_primary_still_denies regression test.

    `git -C` also requires `probe` to ALREADY EXIST -- a not-yet-created nested path
    (e.g. `mkdir -p <repo>/new/nested/dir`, or `rm -f <repo>/newdir/f` where `newdir`
    was never created) cannot be probed via git at all, even though an EXISTING
    ancestor (`<repo>`) may be a real, protected primary. Mirrors
    target_is_protected_primary()'s classify_dir-failure fallback: fail toward
    "protected" whenever the target merely LOOKS governed (_path_looks_governed),
    never toward a silent allow on this uncertainty.

    A `.git`-internal target (`.git` itself or any path within it) is re-attributed
    to its ENCLOSING work tree by _reattribute_dotgit_probe FIRST, because git's own
    `--is-inside-work-tree` semantics exclude `.git/` and would otherwise report it as
    outside every work tree -- silently allowing a catastrophic `rm -rf .git/objects`
    on a protected primary. See that helper's docstring and ADR 0001 §2/§4."""
    probe = _reattribute_dotgit_probe(_probe_dir(path))
    if not probe or not os.path.isdir(probe):
        return _path_looks_governed(probe or path, cfg)
    ctx = gitutil.resolve(probe)
    if not ctx.is_git or ctx.is_linked:
        return False
    top = ctx.toplevel or probe
    lz = lease_mod.read_lease(top)
    if lz and lz.get("status", "active") == "active":
        return False
    root = _governed_root(top, cfg)
    rel = _rel(top, root)
    cls = policy_mod.classify(
        rel, ctx.toplevel, cfg,
        hooks_path=_hooks_path(top), has_origin=bool(_origin(top)),
        is_root=(rel == "."), is_standalone=_is_standalone(top, cfg))
    return cls.classification == policy_mod.INCLUDE


def decide_shell(cwd: str, command: str, policy_path: str,
                 *, allow_primary: bool = False) -> Decision:
    """Engine-OFF decision for a shell command. Reads only policy + lease (+ git).

    Order: operator override -> cloud degrade-to-allow -> not-git/linked/leased allow ->
    non-INCLUDED allow -> mutating on an included primary => DENY -> read-only allow.
    """
    if allow_primary:
        return _allow("operator override (DEV_WORKTREE_GUARD_ALLOW_PRIMARY)")
    # Cloud degrade-to-allow, BEFORE any deny: never hard-block an isolated /workspace VM.
    if _is_cloud(cwd):
        return _allow("cloud/background agent (isolated own-branch workspace)", "cloud")
    ctx = gitutil.resolve(cwd)
    if not ctx.is_git:
        return _allow("not a git repo — fail open")
    # A linked worktree with an adopted lease is a Safe Workspace: allow.
    if ctx.is_linked:
        return _allow("linked worktree (Safe Workspace)", "worktree")
    lz = lease_mod.read_lease(ctx.toplevel or cwd)
    if lz and lz.get("status", "active") == "active":
        return _allow("adopted AWA lease present", "leased")

    cfg = policy_mod.PolicyConfig.load(policy_path)
    root = _governed_root(ctx.toplevel or cwd, cfg)
    rel = _rel(ctx.toplevel or cwd, root)
    has_origin = bool(_origin(cwd))
    hooks_path = _hooks_path(cwd)
    is_standalone = _is_standalone(ctx.toplevel or cwd, cfg)
    cls = policy_mod.classify(rel, ctx.toplevel, cfg, hooks_path=hooks_path,
                              has_origin=has_origin, is_root=(rel == "."),
                              is_standalone=is_standalone)
    # Only an INCLUDED primary checkout (mode ON) is protected; every other classification
    # (exclude/advisory/not-git) allows.
    if cls.classification != policy_mod.INCLUDE:
        return _allow(f"{cls.classification}: {cls.reason}", cls.classification)
    if classify_mutating(command):
        # ADRs 0010/0019: fetch and merge remain mutating. Only the exact,
        # state-proven maintenance intersection converts this included-primary deny
        # to allow; every false/unknown result denies before ADR 0001 narrowing.
        maintenance = classify_primary_maintenance(
            command,
            cwd,
            repository_context=ctx,
        )
        if maintenance.allowed:
            return _allow(
                _PRIMARY_MAINTENANCE_ALLOW_REASONS[maintenance.kind],
                cls.classification,
            )
        if maintenance.matched:
            return Decision(
                "deny",
                _PRIMARY_MAINTENANCE_MESSAGES[maintenance.reason_code],
                cls.classification,
            )
        # ADR 0001: additive narrowing. Only when EVERY resolved target is confidently
        # outside any protected primary does this convert the deny below into an allow;
        # any uncertainty (targets is None) or any protected target falls through
        # unchanged to the existing enforced deny.
        targets = _collect_precise_targets(command, cwd)
        if targets is not None and not any(
                _path_is_protected_primary(t, cfg) for t in targets):
            return _allow(
                "mutating command, but every resolved target is outside any "
                "protected primary checkout", cls.classification)
        # Enforced DENY (not ask): Cursor honors deny and ignores ask (L4). This is the one
        # case where prevention must actually happen.
        return Decision("deny", _DENY_REASON, cls.classification)
    return _allow("read-only command on primary", cls.classification)


def can_clean(worktree_path: str) -> tuple[bool, str]:
    """Kernel cleanup-refusal guarantee (engine-off): refuse unsafe removal.

    Refuses when: not a linked worktree, dirty, detached HEAD, has local-only commits
    (not merged/pushed), or has git-ignored files (which would be silently deleted).
    """
    ctx = gitutil.resolve(worktree_path)
    if not ctx.is_git:
        return False, "not a git worktree"
    if not ctx.is_linked:
        return False, "refusing to clean a primary checkout"
    if gitutil.is_dirty(worktree_path):
        return False, "worktree is dirty (uncommitted changes)"
    if not ctx.branch:
        return False, "detached-HEAD worktree"
    if not _branch_is_safe(worktree_path, ctx.branch, ctx.head or ""):
        return False, "local-only commits (not merged/pushed) — preserve first"
    if gitutil.ignored_files(worktree_path):
        return False, "git-ignored files present — bundle-or-refuse before removal"
    return True, "safe to clean (merged/pushed, no dirty/ignored files)"


# INTENTIONAL divergence: kernel branch_is_cleanup_safe also accepts patch-id/squash
# equivalence (git cherry). This engine mirror stays ancestry-only (over-refuses, safe)
# until fast-follow B aligns it. Never relax engine refusal below the kernel gate.
def _branch_is_safe(path: str, branch: str, head: str) -> bool:
    for ref in ("refs/heads/main", "refs/remotes/origin/main"):
        if gitutil.ref_exists(path, ref) and gitutil.merge_base_is_ancestor(path, head, ref):
            return True
    rc, out, _ = gitutil.git(path, "branch", "-r", "--contains", head, timeout=15)
    if rc == 0 and out.strip():
        return True
    return False


def _governed_root(toplevel: str, cfg: policy_mod.PolicyConfig) -> str:
    for gr in cfg.governed_roots:
        gr_abs = os.path.abspath(os.path.expanduser(gr))
        tl = os.path.abspath(toplevel)
        if tl == gr_abs or tl.startswith(gr_abs + os.sep):
            return gr_abs
    return os.path.dirname(os.path.abspath(toplevel))


def _is_standalone(toplevel: str, cfg: policy_mod.PolicyConfig) -> bool:
    """True when no configured governed root contains `toplevel` — mirrors the kernel's
    resolve_governed_root() returning "" (kernel/lib/awa_policy.py). Deliberately NOT derived
    from _governed_root()'s return value: that function falls back to dirname(toplevel) for
    the standalone case (never ""), so its result can't double as an is-standalone signal.

    Normalizes with realpath (not plain abspath) to byte-for-byte match the kernel's _norm()
    (kernel/lib/awa_policy.py:334-335) -- required so the two independently-computed
    is_standalone signals cannot disagree across a symlinked governed_root or toplevel (e.g.
    a path through /tmp on macOS, itself a symlink to /private/tmp). This intentionally does
    NOT change the pre-existing, unrelated _governed_root()/_rel() (still abspath-only, out of
    scope for this fix) -- so is_standalone's containment check and _governed_root()'s are not
    byte-identical in their symlink handling, but that pre-existing behavior is unchanged by
    this fix either way.
    """
    tl = os.path.realpath(os.path.expanduser(toplevel))
    for gr in cfg.governed_roots:
        gr_abs = os.path.realpath(os.path.expanduser(gr))
        if tl == gr_abs or tl.startswith(gr_abs + os.sep):
            return False
    return True


def _rel(toplevel: str, root: str) -> str:
    tl, r = os.path.abspath(toplevel), os.path.abspath(root)
    if tl == r:
        return "."
    if tl.startswith(r + os.sep):
        return tl[len(r) + 1:]
    return tl


def _origin(cwd: str) -> str:
    rc, out, _ = gitutil.git(cwd, "config", "--get", "remote.origin.url", timeout=10)
    return out.strip() if rc == 0 else ""


def _hooks_path(cwd: str) -> str:
    rc, out, _ = gitutil.git(cwd, "config", "--get", "core.hooksPath", timeout=10)
    return out.strip() if rc == 0 else ""
