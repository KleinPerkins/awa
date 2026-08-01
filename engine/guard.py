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

import os
import re
import shlex
from dataclasses import dataclass

from . import gitutil, lease as lease_mod, policy as policy_mod

_MUT = {"rm", "mv", "cp", "install", "truncate", "dd", "tee", "ln",
        "chmod", "chown", "mkdir", "rmdir", "shred", "unlink"}
_PKG = {"npm", "pnpm", "yarn", "pip", "pip3", "bundle", "poetry", "cargo", "go", "brew", "gem"}
_GITMUT = {"commit", "add", "reset", "rebase", "checkout", "switch", "clean",
           "merge", "cherry-pick", "apply", "restore", "stash", "rm", "mv",
           "pull", "am", "revert", "worktree", "push", "fetch"}
_INPLACE = {"sed", "perl", "gawk", "awk"}
_GIT_TAKES_ARG = ("-C", "-c", "--git-dir", "--work-tree", "--namespace",
                  "--exec-path", "--super-prefix")
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
        return sub in _GITMUT
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
