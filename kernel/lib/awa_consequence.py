#!/usr/bin/env python3
"""awa_consequence.py — KERNEL-sourced consequence descriptor for a proposed AWA action.

KERNEL-OWNED, engine-OFF, router-OFF: stdlib only, ZERO imports of the engine package and ZERO
imports/reads of any router artifact (proven by consumer/tests/test_consumer_contamination_structural).
It is a sibling of awa_roots.py and is consulted BY the operator loop at confirm time to answer,
from REAL kernel facts, "what would this action actually do?".

WHY THIS EXISTS (the real defense for the router's structural limit)
--------------------------------------------------------------------
The router's deterministic floor has a DOCUMENTED structural limit: an utterance whose true intent
is destructive but that best matches a read verb's language can be classified `read` (a
"destructive -> read downgrade"). If confirmation copy were sourced from the router's proposal
(its safety_class / a verb list), that downgrade would silently skip a confirmation. So it is NOT:
the confirmation is sourced HERE, from the kernel's inspection of the ACTUAL target, and the
destructive FLAGS below are COMPUTED PER-TARGET FROM LIVE FACTS — never a constant looked up per
verb. A safe-looking action with a destructive consequence on THIS target MUST confirm; a benign
action never nags.

THREE KERNEL CONSEQUENCE FLAGS (the descriptor the loop reads)
-------------------------------------------------------------
  * destroys_unshared_work — the action would remove work that is not saved anywhere else.
  * irreversible          — the loss cannot be undone (the unsaved work cannot be brought back).
  * affects_shared_ref    — the action would change something other people also rely on.

FAIL-SAFE: whenever the kernel cannot PROVE that a target's work is already saved elsewhere, it
assumes it is NOT (destroys_unshared_work=True). Unknown evidence always resolves toward confirming.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

# Kernel sibling ONLY (never the engine, never a router artifact). The relative import (level 1) is
# the normal path; the fallback loads the sibling by FILE PATH via importlib (stdlib) so this module
# also runs as a standalone script — and so the kernel-off AST scan sees no non-stdlib import name.
try:
    from . import awa_roots  # type: ignore
except ImportError:  # invoked as a script (python3 awa_consequence.py ...)
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location(
        "awa_roots", os.path.join(os.path.dirname(os.path.abspath(__file__)), "awa_roots.py"))
    awa_roots = _ilu.module_from_spec(_spec)  # type: ignore
    _spec.loader.exec_module(awa_roots)  # type: ignore

SCHEMA_CONSEQUENCE = "consequence_descriptor/v1"

# ---- kernel-owned ACTION EFFECT vocabulary ----------------------------------------------
# What the kernel operation DOES to real state. This is the kernel describing its OWN operations;
# it is NOT the router's safety_class and NOT a lookup of the destructive flags (those are computed
# per-target from live facts in describe_consequence, never a constant per action).
ACTION_INSPECT = "inspect"   # read-only: look, report. Changes nothing.
ACTION_CREATE = "create"     # make a NEW safe copy. Adds; removes nothing.
ACTION_OPEN = "open"         # open an EXISTING safe copy to keep working. Removes nothing.
ACTION_RECORD = "record"     # save progress INTO a safe copy. The opposite of destructive.
ACTION_REMOVE = "remove"     # remove a safe copy. The ONLY action whose consequence can destroy.
ACTIONS = (ACTION_INSPECT, ACTION_CREATE, ACTION_OPEN, ACTION_RECORD, ACTION_REMOVE)

# The kernel's own knowledge of what each AWA verb's operation DOES (its effect on real state).
# Unknown/unrecognized verbs resolve to the MOST CAUTIOUS effect (remove) so a spoofed or novel
# verb is treated as potentially destructive and confirmed, never waved through.
_VERB_ACTION = {
    "status": ACTION_INSPECT,
    "list_protected": ACTION_INSPECT,
    "protect": ACTION_CREATE,
    "resume": ACTION_OPEN,
    "save": ACTION_RECORD,
    "cleanup": ACTION_REMOVE,
}


def action_for_verb(verb: str | None) -> str:
    """Map an AWA verb to the kernel EFFECT its operation has. Unknown -> the most cautious effect
    (remove), so an unrecognized verb is treated as potentially destructive (fail-safe)."""
    return _VERB_ACTION.get(verb or "", ACTION_REMOVE)


# ---- live target facts (read-only) ------------------------------------------------------
def _git(path: str, *args: str) -> tuple[int, str]:
    try:
        p = subprocess.run(
            ["git", "-C", path, *args],
            capture_output=True, text=True, timeout=15,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        )
        return p.returncode, (p.stdout or "")
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def _has_uncommitted_changes(path: str) -> bool:
    rc, out = _git(path, "status", "--porcelain")
    if rc != 0:
        return True  # fail-safe: can't tell -> assume there is unsaved work
    return bool(out.strip())


def _work_is_saved_elsewhere(path: str) -> bool:
    """Mirror of the kernel's dev-worktree.sh `branch_is_cleanup_safe`: True only when this copy's
    work is PROVABLY present somewhere shared (local main / origin/main / its upstream / any remote
    branch / patch-equivalent squash-merge). If none of those can be proven, returns False so the
    caller treats the work as UNSHARED (fail-safe toward confirming)."""
    rc, head = _git(path, "rev-parse", "HEAD")
    if rc != 0 or not head.strip():
        return False  # not a resolvable checkout -> cannot prove shared
    head = head.strip()
    # merged into local main / origin/main
    for ref in ("refs/heads/main", "refs/remotes/origin/main"):
        rc, _ = _git(path, "show-ref", "--verify", "--quiet", ref)
        if rc == 0:
            rc2, _ = _git(path, "merge-base", "--is-ancestor", head, ref)
            if rc2 == 0:
                return True
    # present in the tracked upstream
    rc, up = _git(path, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    if rc == 0 and up.strip():
        rc2, _ = _git(path, "merge-base", "--is-ancestor", head, up.strip())
        if rc2 == 0:
            return True
    # present on ANY remote branch
    rc, rem = _git(path, "branch", "-r", "--contains", head)
    if rc == 0:
        for line in rem.splitlines():
            line = line.strip()
            if line and "->" not in line:
                return True
    # squash-merge: every change already patch-present in main / origin/main
    for ref in ("refs/heads/main", "refs/remotes/origin/main"):
        rc, _ = _git(path, "show-ref", "--verify", "--quiet", ref)
        if rc != 0:
            continue
        rc, cherry = _git(path, "cherry", ref, head)
        if rc == 0 and cherry.strip() and not any(l.startswith("+") for l in cherry.splitlines()):
            return True
    return False


def _branch_on_remote(path: str) -> bool:
    rc, head = _git(path, "rev-parse", "HEAD")
    if rc != 0 or not head.strip():
        return False
    rc, rem = _git(path, "branch", "-r", "--contains", head.strip())
    if rc != 0:
        return False
    return any(l.strip() and "->" not in l for l in rem.splitlines())


def probe_target(target_path: str) -> dict:
    """Gather the LIVE kernel facts a consequence is computed from. Read-only. Never raises: any
    probe failure resolves toward the fail-safe (work is treated as unsaved / unshared)."""
    ap = awa_roots.canon(target_path)
    exists = os.path.exists(ap)
    if not exists:
        return {
            "target": ap, "exists": False, "disposition": awa_roots.DISP_ABSENT,
            "has_uncommitted_changes": False, "has_unshared_work": False, "branch_on_remote": False,
        }
    disp = awa_roots.disposition(ap).get("disposition", awa_roots.DISP_UNTRACKED)
    uncommitted = _has_uncommitted_changes(ap)
    saved_elsewhere = _work_is_saved_elsewhere(ap)
    return {
        "target": ap,
        "exists": True,
        "disposition": disp,
        "has_uncommitted_changes": bool(uncommitted),
        # UNSHARED = there is committed work that is not provably saved elsewhere.
        "has_unshared_work": (not saved_elsewhere),
        "branch_on_remote": _branch_on_remote(ap),
    }


# ---- the consequence descriptor ---------------------------------------------------------
_ACTION_LABEL = {
    ACTION_INSPECT: "Look at your work and report back",
    ACTION_CREATE: "Set up a new safe copy to work in",
    ACTION_OPEN: "Open a safe copy so you can keep working",
    ACTION_RECORD: "Save the progress in your safe copy",
    ACTION_REMOVE: "Remove a safe copy",
}


def describe_consequence(action: str, target_path: str, *, facts: dict | None = None,
                         remove_saved_reference: bool = False) -> dict:
    """Return the KERNEL consequence descriptor for `action` on `target_path`.

    The three flags are COMPUTED FROM LIVE FACTS (never a per-verb/per-action constant):
      * Only a REMOVE can destroy, and only when THIS target holds work not saved elsewhere.
      * `irreversible` tracks destroys_unshared_work — a fully-saved copy can simply be set up
        again, so its removal is recoverable; unsaved work cannot be brought back.
      * `affects_shared_ref` is true only when the action would also remove something shared that
        other people rely on.

    `requires_confirmation` is true iff ANY flag is set. A benign action (inspect/create/open/
    record, or a remove whose work is fully saved elsewhere) has every flag false -> no nag.
    Copy is plain-language and jargon-free (kernel-owned, never sourced from the router)."""
    if action not in ACTIONS:
        action = ACTION_REMOVE  # unknown effect -> most cautious
    facts = facts if facts is not None else probe_target(target_path)
    target = facts.get("target", awa_roots.canon(target_path))

    destroys = False
    irreversible = False
    affects_shared = False

    if action == ACTION_REMOVE:
        destroys = bool(facts.get("has_uncommitted_changes") or facts.get("has_unshared_work"))
        irreversible = destroys
        affects_shared = bool(remove_saved_reference and facts.get("branch_on_remote"))

    requires_confirmation = bool(destroys or irreversible or affects_shared)

    if action == ACTION_REMOVE:
        if destroys:
            risk = ("This safe copy still has work in it that is not saved anywhere else. "
                    "Removing it would lose that work for good.")
            undo = ("You could set up a new safe copy later, but the unsaved work inside this one "
                    "cannot be brought back.")
            irreversible_step = "Once this safe copy is removed, the unsaved work in it is gone."
        else:
            risk = ("Everything in this safe copy is already saved somewhere else, so removing it "
                    "would not lose any of your work.")
            undo = "You can set up a new safe copy whenever you want."
            irreversible_step = ""
    else:
        risk = "This does not remove anything or change your original files."
        undo = "There is nothing to undo — your work stays as it is."
        irreversible_step = ""

    return {
        "schema": SCHEMA_CONSEQUENCE,
        "action": action,
        "action_label": _ACTION_LABEL.get(action, _ACTION_LABEL[ACTION_REMOVE]),
        "target": target,
        "destroys_unshared_work": destroys,
        "irreversible": irreversible,
        "affects_shared_ref": affects_shared,
        "requires_confirmation": requires_confirmation,
        "risk": risk,
        "undo": undo,
        "irreversible_step": irreversible_step,
    }


def consequence_for_verb(verb: str | None, target_path: str, *, facts: dict | None = None,
                         remove_saved_reference: bool = False) -> dict:
    """Convenience: resolve an AWA verb to its kernel effect, then describe the consequence. The
    operator loop calls THIS so the confirmation is always kernel-sourced for the ACTUAL verb it is
    about to run (never the router's classification)."""
    return describe_consequence(action_for_verb(verb), target_path, facts=facts,
                                remove_saved_reference=remove_saved_reference)


# ---- CLI (invoked by the shell kernel / for inspection) ---------------------------------
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="awa_consequence",
                                description="AWA kernel: consequence descriptor for a proposed action")
    sub = p.add_subparsers(dest="cmd", required=True)

    de = sub.add_parser("describe", help="describe the consequence of a verb on a target")
    de.add_argument("--verb", required=True)
    de.add_argument("--target", required=True)
    de.add_argument("--remove-saved-reference", dest="remove_saved_reference",
                    action="store_true")

    pr = sub.add_parser("probe", help="print the live kernel facts for a target")
    pr.add_argument("--target", required=True)

    args = p.parse_args(argv)
    if args.cmd == "describe":
        d = consequence_for_verb(args.verb, args.target,
                                 remove_saved_reference=args.remove_saved_reference)
        json.dump(d, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    if args.cmd == "probe":
        json.dump(probe_target(args.target), sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
