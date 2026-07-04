"""guard.py — minimal local guard: the kernel guarantee with the engine OFF (Phase 5).

This is the load-bearing fallback. With the daemon dead / never started, the guard
still: (1) denies/asks-before primary mutation, (2) refuses unsafe cleanup, and
(3) preserves work — using ONLY atomic policy snapshots + `.awa/lease.json`. It never
requires the SQLite state or the daemon (those are bookkeeping/UX). If state IS
available it opportunistically records a detection, but the decision never depends on it.

Decision surface (mirrors the frozen guard permission schema: allow/ask/deny):
  * mutating shell command on an INCLUDED PRIMARY checkout (not a linked worktree,
    no active lease) -> ask (nudge to a Safe Workspace). Override is explicit.
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
_GIT_TAKES_ARG = ("-C", "-c", "--git-dir", "--work-tree", "--namespace",
                  "--exec-path", "--super-prefix")
_PREFIX_WRAPPERS = ("sudo", "command", "nice", "env", "time", "nohup", "xargs")


def classify_mutating(command: str) -> bool:
    """Adversary-aware mutating-command detector (parity with worktree-guard.sh).

    Catches `git -C <path> commit`, `git -c k=v commit`, `sed -i`, `>`/`>>`
    redirection to a real path, in-place mutators, and package installs — not just a
    bare `git commit`. Unparseable -> True (fail safe / ask).
    """
    if not command or not command.strip():
        return False
    for m in re.finditer(r"\d*>>?", command):
        tail = command[m.end():].lstrip()
        if not tail or tail.startswith("&"):
            continue
        if tail.startswith(("/dev/null", "/dev/stdout", "/dev/stderr")):
            continue
        return True
    try:
        toks = shlex.split(command)
    except ValueError:
        return True
    i = 0
    while i < len(toks) and (re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[i])
                             or toks[i] in _PREFIX_WRAPPERS):
        i += 1
    if i >= len(toks):
        return False
    prog = os.path.basename(toks[i])
    rest = toks[i + 1:]
    if prog in _MUT:
        return True
    if prog in ("sed", "perl", "gawk", "awk") and any(a == "-i" or a.startswith("-i") for a in rest):
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


@dataclass
class Decision:
    permission: str  # allow | ask | deny
    reason: str
    classification: str = ""


def _allow(reason: str, cls: str = "") -> Decision:
    return Decision("allow", reason, cls)


def decide_shell(cwd: str, command: str, policy_path: str,
                 *, allow_primary: bool = False) -> Decision:
    """Engine-OFF decision for a shell command. Reads only policy + lease (+ git)."""
    if allow_primary:
        return _allow("operator override (DEV_WORKTREE_GUARD_ALLOW_PRIMARY)")
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
    cls = policy_mod.classify(rel, ctx.toplevel, cfg, hooks_path=hooks_path,
                              has_origin=has_origin, is_root=(rel == "."))
    if cls.classification != policy_mod.INCLUDE:
        return _allow(f"{cls.classification}: {cls.reason}", cls.classification)
    if classify_mutating(command):
        return Decision(
            "ask",
            "mutating shell command on an included PRIMARY checkout — use a Safe Workspace first",
            cls.classification,
        )
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
