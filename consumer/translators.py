"""translators.py — render router proposals, kernel confirmations, and kernel blocks into plain
language for a non-technical PM.

Two hard rules (the system-wide egress gate + honest confidence):
  1. ZERO banned terms. Every string a PM can see is jargon-free (no Tier A/B/C terms). This is
     tested against AWA's egress-terms snapshot in consumer/tests/test_consumer_egress.py.
  2. HONEST confidence, never a bare green pill. Every rendering states what was checked AND what
     was not — a partial understanding names its hole in plain words; a confident reading still
     says "I have not changed anything yet." No output ever implies an unauditable guarantee.

These are PURE functions over already-computed inputs (a proposal dict, a catalog entry, a kernel
consequence descriptor, a kernel block record). They never call the router or the kernel; the loop
passes them what it already has.
"""

from __future__ import annotations

from typing import Any

from . import egress

# Plain-language prompts for the router's missing_params (the raw slot names never reach the PM).
_PARAM_PLAIN = {
    "which_work": "which protected work you mean",
    "project": "which project you mean",
    "confirm": "that you're sure you want this",
    "note": "an optional short note to remember this by",
}


def _plain_param(name: str) -> str:
    """Plain prompt for a KNOWN catalog slot. An unknown/unmodeled slot name (e.g. one a router
    injects) is NEVER echoed into PM copy — it may itself be jargon (a banned term like `branch`) —
    so it falls back to a generic, jargon-free phrase (SHOULD-FIX 3)."""
    return _PARAM_PLAIN.get(name) or "one more detail"


def _confidence(verdict: str, missing: list[str]) -> dict:
    """Honest-confidence block: a plain sentence plus an explicit checked / not-yet-checked pair.
    Never a bare status — always names the limit of what was understood."""
    if verdict == "strong" and not missing:
        return {
            "level": "fairly sure",
            "plain": "I'm fairly sure this is what you mean.",
            "checked": "I matched your words to one clear request.",
            "not_checked": "I have not changed anything yet — I'll only continue if you're happy.",
        }
    if verdict == "strong" and missing:
        needs = " and ".join(_plain_param(m) for m in missing)
        return {
            "level": "sure of the goal, missing a detail",
            "plain": f"I'm fairly sure what you'd like to do, but first I need to know {needs}.",
            "checked": "I matched your words to one clear request.",
            "not_checked": f"I still need {needs}, and I have not changed anything yet.",
        }
    if verdict == "weak":
        return {
            "level": "not fully sure",
            "plain": "I think this might be what you mean, but I'm not fully sure.",
            "checked": "Some of your words matched this, but not all of them.",
            "not_checked": "I'm not certain this is right, so I won't do anything until you confirm.",
        }
    return {
        "level": "unsure",
        "plain": "I couldn't tell what you'd like to do from that, and I didn't want to guess.",
        "checked": "I looked for a clear match to something I can do.",
        "not_checked": "I didn't find one, so I have not done anything.",
    }


def render_proposal(proposal: dict, catalog_entry: dict | None) -> dict:
    """Plain-language rendering of a router proposal + the catalog entry it names. Honest confidence
    is always included; nothing here executes or authorizes anything."""
    verdict = proposal.get("verdict", "none")
    missing = list(proposal.get("missing_params", []) or [])
    conf = _confidence(verdict, missing)

    if verdict == "none" or not catalog_entry:
        return {
            "understood": False,
            "headline": "I'm not sure what you'd like to do",
            "plain": conf["plain"],
            "confidence": conf,
            "options": [
                "Start protecting this work",
                "Check whether your work is protected",
                "Go back to work you protected earlier",
                "Save your progress",
                "Remove an old safe copy",
            ],
            "next": "Tell me in your own words and I'll line it up for you.",
        }

    label = catalog_entry.get("plain_label", "do this")
    consequence_copy = catalog_entry.get("consequence_copy", "")
    return {
        "understood": True,
        "headline": label,
        "plain": f"{conf['plain']} {consequence_copy}".strip(),
        "confidence": conf,
        "needs": [_plain_param(m) for m in missing],
        "next": ("First tell me " + " and ".join(_plain_param(m) for m in missing) + "."
                 if missing else "Say yes and I'll do it, or tell me if I've got it wrong."),
    }


def render_confirmation(consequence: dict, catalog_entry: dict | None = None) -> dict:
    """Plain-language confirmation, sourced from the KERNEL consequence descriptor. When the kernel
    says a consequence is destructive/irreversible/shared, this spells out the risk, the undo, and
    the point of no return in plain words. When the kernel says it's benign, it says so plainly and
    does not nag."""
    label = consequence.get("action_label", "do this")
    destroys = consequence.get("destroys_unshared_work", False)
    irreversible = consequence.get("irreversible", False)
    affects_shared = consequence.get("affects_shared_ref", False)
    needs_confirm = consequence.get("requires_confirmation", False)

    if not needs_confirm:
        return {
            "needs_confirmation": False,
            "headline": label,
            "plain": consequence.get("risk", "This is safe to do — nothing will be lost."),
            "ask": None,
        }

    flags_plain = []
    if destroys:
        flags_plain.append("work that isn't saved anywhere else would be lost")
    if irreversible:
        flags_plain.append("this cannot be undone")
    if affects_shared:
        flags_plain.append("it would also change something other people rely on")

    return {
        "needs_confirmation": True,
        "headline": f"Before I {label[0].lower() + label[1:]}",
        "plain": consequence.get("risk", ""),
        "why_it_matters": flags_plain,
        "undo": consequence.get("undo", ""),
        "point_of_no_return": consequence.get("irreversible_step", ""),
        "ask": "Do you want me to continue? I'll only do it if you say yes.",
    }


_SAFE_BLOCK_REASON = "to keep your work safe"
_SAFE_BLOCK_NEXT = "Your work is untouched. Tell me what you'd like to do instead."


def _pm_safe(text: str, fallback: str) -> str:
    """Return `text` only when it is jargon-free (zero Tier A/B/C banned terms), otherwise the safe
    fallback. Guards kernel-emitted block copy so no raw guard/mechanism text can reach the PM."""
    return text if (text and not egress.find_banned_terms(text)) else fallback


def render_block(block: dict) -> dict:
    """Plain-language rendering of a KERNEL block/refusal (the guard or the clean gate said no).
    Never leaks the mechanism: it renders ONLY a kernel-emitted, PM-safe `plain_reason`/`plain_next`
    — the raw `reason`/`next` guard text (which carries jargon like "mutating command", "primary
    checkout", "worktree", "branch", "main", "merge") is DROPPED, not shown — and even the plain_*
    strings are scanned through the banned-term filter, so a mislabeled 'plain' string still cannot
    leak jargon (MUST-FIX 2)."""
    reason = _pm_safe(block.get("plain_reason", ""), _SAFE_BLOCK_REASON)
    next_step = _pm_safe(block.get("plain_next", ""), _SAFE_BLOCK_NEXT)
    return {
        "blocked": True,
        "headline": "I stopped before doing that to keep your work safe",
        "plain": f"I didn't continue because {reason}.",
        "reassurance": "Nothing was changed and nothing was lost.",
        "next": next_step,
    }


def render_outcome(ok: bool, *, did: str, detail: str = "") -> dict:
    """Plain-language narration of the REAL outcome after an AWA verb ran (verify-real-outcome ->
    narrate). Honest: reports what actually happened, not what was intended."""
    if ok:
        return {
            "ok": True,
            "headline": f"Done — {did}.",
            "plain": (detail or "I checked afterwards and it worked."),
        }
    return {
        "ok": False,
        "headline": f"That didn't finish — {did}.",
        "plain": (detail or "I checked afterwards and it did not complete, so I stopped. "
                            "Your work is untouched."),
    }
