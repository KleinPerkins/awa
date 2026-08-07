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


def _extract_git_target_dirs(rest, cwd):
    """git's -C / --git-dir / --work-tree flags each redirect a DIFFERENT real
    mutation surface, and git honors ALL of them simultaneously when several are
    given together: -C changes git's own effective cwd (and is the fallback
    git-dir-discovery root, becoming the work tree too whenever --work-tree /
    GIT_WORK_TREE is absent -- even when --git-dir IS explicitly given); --git-dir
    names where objects/refs are actually written (commit, index updates, fetch,
    ...); --work-tree names where checked-out files are written (checkout, reset
    --hard, clean, ...). A previous version of this function kept only the
    LAST-seen flag's value as "the" target -- so `git --git-dir=<protected>/.git
    --work-tree=<safe> commit` was classified solely on the trailing safe
    --work-tree, even though --git-dir still pointed the actual commit (object +
    ref write) at the protected primary: a guard bypass. Returns ALL applicable
    targets (the -C-adjusted cwd, always, plus any explicit --git-dir / --work-tree
    values) so the caller must prove EVERY one of them safe before converting a
    deny into an allow (ADR 0001 §4: any single unsafe/unresolved target poisons
    the whole command)."""
    j, c_path, git_dir, work_tree = 0, cwd, None, None
    while j < len(rest):
        a = rest[j]
        if a == "-C" and j + 1 < len(rest):
            nxt = rest[j + 1]
            c_path = nxt if os.path.isabs(nxt) else os.path.join(c_path, nxt)
            j += 2; continue
        if a.startswith("--git-dir="):
            git_dir = a.split("=", 1)[1]; j += 1; continue
        if a == "--git-dir" and j + 1 < len(rest):
            git_dir = rest[j + 1]; j += 2; continue
        if a.startswith("--work-tree="):
            work_tree = a.split("=", 1)[1]; j += 1; continue
        if a == "--work-tree" and j + 1 < len(rest):
            work_tree = rest[j + 1]; j += 2; continue
        j += 1
    targets = [c_path]
    if git_dir is not None:
        targets.append(git_dir if os.path.isabs(git_dir) else os.path.join(c_path, git_dir))
    if work_tree is not None:
        targets.append(work_tree if os.path.isabs(work_tree) else os.path.join(c_path, work_tree))
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
            targets.extend(_extract_git_target_dirs(rest, cwd))
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
