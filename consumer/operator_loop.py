"""operator_loop.py — the thin AWA operator loop (phase A0).

    hear -> intent map -> confirm-consequence -> AWA verb -> verify-real-outcome -> narrate ->
    record-feedback

The loop is the ONLY place the pieces meet, and it enforces the constitutional split:
  * The router PROPOSES (L0-L2+L5). It never executes and never authorizes. The loop calls it
    through `intent map` only to understand the utterance.
  * AWA's OWN verbs EXECUTE — and only AFTER the confirmation gate passes. The loop never runs a
    verb straight from the router's output.
  * Every consequence confirmation is sourced from the KERNEL (awa_consequence) and the CONSUMER
    CATALOG, never the router. The confirmation gate fires on THREE router-independent triggers:
    (1) the KERNEL per-target consequence is destructive/irreversible/shared; (2) the CATALOG marks
    the verb destructive-class or gives it a required literal `confirm` slot (CR9 — derived from the
    catalog entry, NOT the router's `missing_params`, so a lying router that empties missing_params
    and claims verdict=strong cannot suppress it); (3) the router is UNCERTAIN (verdict != strong).
    So even if the router downgrades a destructive intent to a read (its documented structural
    limit), a destructive-class verb still confirms. The router's own `requires_confirmation` is
    deliberately NOT a trigger — it is True for every write and would nag benign writes.

KERNEL-FIRST / OFF-SWITCH (KI1 + CR6): the router is OPTIONAL. If it is not installed/importable,
`map` returns nothing and the loop DEGRADES to ask + a secondary explicit path (the six plain
options). It never guesses, and it never auto-runs a destructive action. AWA's own `make verify`
passes with the router uninstalled because this module imports and runs without it.
"""

from __future__ import annotations

import hashlib
import importlib.util as _ilu
import json
import time
from pathlib import Path
from typing import Any, Callable

from . import translators


def _load_kernel_consequence():
    """Load the KERNEL consequence module BY PATH (kernel/lib/awa_consequence.py), never as a
    `kernel.lib` package import. This is the repo's kernel-first convention (the kernel libs stay a
    standalone, stdlib-only, engine-off surface loaded by path — see the K0/K1 kernel-off matrix);
    the consumer depends on the kernel, never the reverse."""
    path = Path(__file__).resolve().parents[1] / "kernel" / "lib" / "awa_consequence.py"
    spec = _ilu.spec_from_file_location("awa_consequence", path)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod

# Decision states the loop can end a turn in.
EXECUTE = "execute"
AWAITING_CONFIRMATION = "awaiting_confirmation"
NEED_MORE_INFO = "need_more_info"
DEGRADED_TO_ASK = "degraded_to_ask"
NOT_UNDERSTOOD = "not_understood"

# Operator-choice vocabulary (aligns with intent-feedback/v1.operator_choice for forward-compat).
CHOICE_ACCEPT = "accept"
CHOICE_CLARIFY = "clarify"
CHOICE_ABORT = "abort"

_SECONDARY_EXPLICIT_PATH = {
    "note": "I can still help without guessing — tell me which of these you want, in your words.",
    "options": [
        {"say": "protect this work", "means": "Start protecting this work"},
        {"say": "is everything okay", "means": "Check whether your work is protected"},
        {"say": "show my safe copies", "means": "Show all your protected work"},
        {"say": "go back to earlier work", "means": "Go back to work you protected earlier"},
        {"say": "save my progress", "means": "Save your progress"},
        {"say": "clean up an old copy", "means": "Remove an old safe copy"},
    ],
}

_TARGET_PARAMS = {"which_work", "project"}


def _resolved_missing_params(missing: list[str], target: str | None,
                             confirm: bool | None) -> list[str]:
    """Remove slots already resolved by trusted loop inputs before PM rendering."""
    return [
        name for name in missing
        if not (name in _TARGET_PARAMS and target)
        # The loop's dedicated confirmation gate owns this slot; proposal rendering never should.
        and name != "confirm"
    ]


def _confirmation_fingerprint(verb: str, target: str | None, consequence: dict) -> str:
    """Bind a confirmation replay to the exact verb, target, and kernel consequence shown."""
    payload = {
        "verb": verb,
        "target": consequence.get("target") or target or "",
        "consequence": {
            key: consequence.get(key)
            for key in (
                "action",
                "destroys_unshared_work",
                "irreversible",
                "affects_shared_ref",
                "requires_confirmation",
                "risk",
                "undo",
                "irreversible_step",
            )
        },
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _import_router():
    """Best-effort import of the router engine. Returns the module or None (router uninstalled).
    Importing the router is NEVER on the kernel safety path — a failure here only degrades the
    loop to ask; it can never weaken a kernel decision."""
    try:
        from intent_router import engine  # type: ignore
        return engine
    except Exception:
        return None


def _catalog_entry(catalog: dict, verb: str) -> dict | None:
    for e in catalog.get("verbs", []) or []:
        if isinstance(e, dict) and e.get("verb") == verb:
            return e
    return None


def _catalog_requires_literal_confirm(entry: dict | None) -> bool:
    """CR9, sourced from the CONSUMER CATALOG (never the router). A verb requires an explicit
    literal confirmation iff its catalog entry is destructive-class OR declares a required `confirm`
    slot whose value must be supplied literally (`source: literal`). Deriving this from the catalog
    — not the router's `missing_params` — makes the destructive-class confirmation gate fully
    router-independent: a lying router (`missing_params=[]`, `verdict=strong`) cannot empty it."""
    if not isinstance(entry, dict):
        return False
    if entry.get("safety_class") == "destructive":
        return True
    for p in entry.get("param_schema", []) or []:
        if (isinstance(p, dict) and p.get("name") == "confirm"
                and p.get("required") and p.get("source") == "literal"):
            return True
    return False


class OperatorLoop:
    """One instance per catalog. Dependencies are injected so the loop is testable without a live
    router / real mutations, and so the kernel path is explicit and swappable ONLY for tests."""

    def __init__(self, catalog: dict, *, router: Any = None, kernel_consequence: Any = None,
                 executor: Callable[[str, dict, str | None], dict] | None = None,
                 catalog_version: str = "awa-catalog/v1",
                 session_id: str = "local") -> None:
        self.catalog = catalog
        # router is resolved lazily so "uninstalled" is observed at call time, not construction.
        self._router = router
        self._router_resolved = router is not None
        self.executor = executor
        self.catalog_version = catalog_version
        self.session_id = session_id
        if kernel_consequence is None:
            kernel_consequence = _load_kernel_consequence()
        self.kernel = kernel_consequence

    # -- hear -> map -------------------------------------------------------------------
    def _router_engine(self):
        if self._router_resolved:
            return self._router
        self._router = _import_router()
        self._router_resolved = True
        return self._router

    def map(self, utterance: str) -> dict | None:
        """`intent map`: ask the router for a proposal. Returns None when the router is not
        installed (the off-switch path). Never executes anything."""
        engine = self._router_engine()
        if engine is None:
            return None
        return engine.propose("awa", utterance, self.catalog)

    # -- the whole turn ----------------------------------------------------------------
    def handle(self, utterance: str, *, target: str | None = None, facts: dict | None = None,
               confirm: bool | None = None,
               expected_confirmation_fingerprint: str | None = None) -> dict:
        """Run one operator turn. `confirm` is the operator's answer to a consequence question
        (None = not yet asked/answered). `facts`/`target` let a caller (and tests) supply the
        kernel target facts deterministically; in real use the kernel probes them.

        `confirm=True` remains a trusted caller attestation for compatibility. Stateless or
        untrusted replay adapters must also pass `expected_confirmation_fingerprint`; when supplied,
        a mismatch always re-opens the gate instead of executing."""
        result: dict = {
            "utterance": utterance,
            "router_available": None,
            "understanding": None,
            "verb": None,
            "target": target,
            "consequence": None,
            "confirmation": None,
            "decision": None,
            "outcome": None,
            "narration": None,
            "feedback": None,
            # Internal machinery — NOT PM-facing. The raw router envelope carries routing metadata
            # (tool_path/why[]/safety_class/start_point) that must never be shown to the operator; it
            # lives here (and in the feedback record), and an agent serializes the PM subset via
            # pm_view() (SHOULD-FIX 8). The rendered `understanding` is the PM-facing version.
            "_internal": {
                "proposal": None,
                "confirmation_fingerprint": None,
                "confirmation_replay_valid": None,
            },
        }

        proposal = self.map(utterance)
        result["router_available"] = proposal is not None

        # OFF-SWITCH: router uninstalled -> degrade to ask + secondary explicit path. Never guess.
        if proposal is None:
            result["decision"] = DEGRADED_TO_ASK
            result["understanding"] = {
                "understood": False,
                "headline": "I can't line that up automatically right now",
                "plain": ("I couldn't check your words against what I can do, so I won't guess. "
                          "Nothing has changed."),
                "confidence": {
                    "level": "unsure",
                    "plain": "I would rather ask than guess.",
                    "checked": "I tried to understand your request on my own.",
                    "not_checked": "I couldn't confirm it, so I have not done anything.",
                },
            }
            result["secondary_explicit_path"] = _SECONDARY_EXPLICIT_PATH
            result["feedback"] = self._feedback(utterance, None, CHOICE_CLARIFY, "noop")
            return result

        result["_internal"]["proposal"] = proposal
        verb = proposal.get("verb") or None
        entry = _catalog_entry(self.catalog, verb) if verb else None
        result["verb"] = verb

        verdict = proposal.get("verdict")
        missing = list(proposal.get("missing_params", []) or [])
        unresolved = _resolved_missing_params(missing, target, confirm)
        proposal_for_render = dict(proposal)
        proposal_for_render["missing_params"] = unresolved
        result["understanding"] = translators.render_proposal(proposal_for_render, entry)

        # NOT UNDERSTOOD: no confident verb -> ask, offer options. Never guess.
        if verdict == "none" or not verb or not entry:
            result["decision"] = NOT_UNDERSTOOD
            result["secondary_explicit_path"] = _SECONDARY_EXPLICIT_PATH
            result["feedback"] = self._feedback(utterance, proposal, CHOICE_CLARIFY, "noop")
            return result

        # CONFIRM-CONSEQUENCE (kernel-sourced, independent of the router). A verb whose CATALOG entry
        # declares `removes_shared_reference: true` (optional; default false — no current AWA verb
        # sets it, so it is wired defensively) tells the kernel this removal also drops a shared
        # reference, so the kernel's `affects_shared_ref` reason ("changes something other people
        # rely on") can surface on the product path. Derived from the CATALOG, never the router
        # (SHOULD-FIX 4).
        remove_saved_reference = bool(entry.get("removes_shared_reference"))
        consequence = self.kernel.consequence_for_verb(
            verb, target or "", facts=facts, remove_saved_reference=remove_saved_reference)
        result["consequence"] = consequence
        confirmation = translators.render_confirmation(consequence, entry)
        result["confirmation"] = confirmation
        fingerprint = _confirmation_fingerprint(verb, target, consequence)
        result["_internal"]["confirmation_fingerprint"] = fingerprint
        if confirmation.get("needs_confirmation") and isinstance(
            result.get("understanding"), dict
        ):
            # The exact consequence question below owns the prompt. Do not render a second generic
            # "say yes" prompt from the proposal beside it.
            result["understanding"] = dict(result["understanding"])
            result["understanding"]["next"] = None
            confidence = dict(result["understanding"].get("confidence") or {})
            confidence["not_checked"] = None
            result["understanding"]["confidence"] = confidence

        # The confirmation gate — THREE precise triggers, so a destructive consequence ALWAYS
        # confirms while a benign verb NEVER nags (deliverable: "a safe-looking verb with a
        # destructive consequence MUST confirm; a benign verb must not nag"):
        #   1. KERNEL consequence is destructive/irreversible/shared (the airtight backstop; this is
        #      the real defense for the router's destructive->read downgrade — it is computed from
        #      the ACTUAL verb+target facts, never the router's label).
        #   2. The CONSUMER CATALOG marks the verb destructive-class or gives it a required literal
        #      `confirm` slot (CR9) — read from the catalog ENTRY, never the router's missing_params,
        #      so a lying router (missing_params=[], verdict=strong) cannot empty this trigger.
        #   3. The router is UNCERTAIN (verdict weak/none) — honest confidence asks before acting.
        # A STRONG, benign write (save/protect/resume) trips none of these -> it runs without a nag.
        # NOTE: the blanket router `requires_confirmation` (True for every write) is deliberately NOT
        # OR'd in — that would nag benign writes; the kernel term + CR9 + uncertainty cover safety.
        literal_confirm_required = _catalog_requires_literal_confirm(entry)
        must_confirm = bool(
            consequence.get("requires_confirmation")
            or literal_confirm_required
            or verdict != "strong"
        )

        # NEED MORE INFO: required params still missing, EXCEPT (a) the `confirm` slot, which the
        # confirmation gate below handles, and (b) the target slot (`which_work`/`project`), which
        # a provided/resolved `target` satisfies (R-core's router reports it missing because it does
        # no param extraction; the loop resolves the target and passes it here).
        info_missing = [
            m for m in unresolved
            if m != "confirm" and not (m in _TARGET_PARAMS and target)
        ]
        if info_missing:
            result["decision"] = NEED_MORE_INFO
            result["feedback"] = self._feedback(utterance, proposal, CHOICE_CLARIFY, "noop")
            return result

        # CONFIRMATION REPLAY BINDING. A caller that supplies a fingerprint must match the exact
        # verb/target/consequence previously shown; drift re-opens the gate and never executes.
        if confirm is True and expected_confirmation_fingerprint is not None:
            replay_valid = (
                isinstance(expected_confirmation_fingerprint, str)
                and expected_confirmation_fingerprint == fingerprint
            )
            result["_internal"]["confirmation_replay_valid"] = replay_valid
            if not replay_valid:
                result["decision"] = AWAITING_CONFIRMATION
                result["feedback"] = self._feedback(
                    utterance, proposal, CHOICE_CLARIFY, "noop")
                return result

        # CONFIRMATION GATE.
        if must_confirm and confirm is not True:
            result["decision"] = AWAITING_CONFIRMATION
            result["feedback"] = self._feedback(utterance, proposal, CHOICE_CLARIFY, "noop")
            return result

        # EXECUTE — AWA's OWN verb, never the router. Only reached once the gate is satisfied.
        result["decision"] = EXECUTE
        # Resolved/executed turns must not carry a stale "say yes" or missing-input prompt.
        if isinstance(result.get("understanding"), dict):
            result["understanding"] = dict(result["understanding"])
            result["understanding"]["needs"] = []
            result["understanding"]["next"] = None
            confidence = dict(result["understanding"].get("confidence") or {})
            confidence["not_checked"] = None
            result["understanding"]["confidence"] = confidence
        if self.executor is None:
            # Dry-run (tests / rehearsal without real mutation): report what WOULD run.
            result["outcome"] = {"ok": None, "dry_run": True, "verb": verb, "target": target}
            result["narration"] = translators.render_outcome(
                True, did=entry.get("plain_label", verb).lower(),
                detail="(rehearsal) I would do this now and then check it worked.")
            result["feedback"] = self._feedback(utterance, proposal, CHOICE_ACCEPT, "unknown")
            return result

        outcome = self.executor(verb, {}, target)
        result["outcome"] = outcome
        # VERIFY-REAL-OUTCOME + NARRATE (honest: report what actually happened).
        ok = bool(outcome.get("ok")) and bool(outcome.get("verified", outcome.get("ok")))
        result["narration"] = translators.render_outcome(
            ok, did=entry.get("plain_label", verb).lower(),
            detail=outcome.get("detail", ""))
        result["feedback"] = self._feedback(
            utterance, proposal, CHOICE_ACCEPT, "success" if ok else "failed")
        return result

    # -- record-feedback ---------------------------------------------------------------
    def _feedback(self, utterance: str, proposal: dict | None, choice: str, outcome: str) -> dict:
        """Produce an intent-feedback/v1-shaped record (NOT persisted in A0 — persistence is the
        router's C0 concern and the router is read-only here). Kept shape-compatible so C0 can
        append it verbatim later."""
        return {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "consumer": "awa",
            "catalog_version": self.catalog_version,
            "utterance": utterance,
            "proposal": proposal,
            "operator_choice": choice,
            "verdict": (proposal or {}).get("verdict", "none"),
            "confidence": (proposal or {}).get("confidence", 0.0),
            "outcome": outcome,
            "session_id": self.session_id,
        }


# PM-facing view (SHOULD-FIX 8): the ONLY keys an agent should serialize back to the operator.
# Everything else in a loop result — the raw router `proposal` (now under `_internal`), the `verb`
# token, the kernel `consequence` descriptor, the `feedback` record, and `_internal` — is internal
# machinery that carries routing/kernel metadata the PM must never see. `understanding`/
# `confirmation`/`narration` are the plain-language renderings the operator actually reads.
_PM_FACING_KEYS = ("utterance", "decision", "understanding", "confirmation", "narration",
                   "secondary_explicit_path")


def pm_view(result: dict) -> dict:
    """Return the strictly PM-facing subset of a loop result — what an agent renders to the operator.
    The raw router envelope (tool_path/why[]/safety_class/start_point) and other internal machinery
    are deliberately excluded, so no routing metadata can leak into PM output."""
    return {k: result[k] for k in _PM_FACING_KEYS if k in result}
