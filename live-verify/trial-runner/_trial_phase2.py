"""_trial_phase2.py — Phase 2 conversational-ergonomics transitions.

Driven through the REAL consumer surface: ``consumer/finish_current.py`` (in-process for the exact
predicates/flows the oracle suite asserts, and via the ``python3 finish_current.py <cmd>`` CLI for
the production entrypoints the operator-skill documents) plus the ``before-submit-prompt.sh`` hook.
Every row cites the ``test_finish_*`` oracle it mirrors. No new removal authority is exercised here:
the destructive ``Close`` routing uses an executor stub exactly like the oracle, and the ONE real
consumer->kernel removal (P2-DISPATCH-CLI-CLOSE) operates on a throwaway sandbox worktree.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from _trial_lib import (REPO, HOOK_BEFORE_SUBMIT, INSTALL_HOOKS, Row, Sandbox, UX,
                        check, check_eq, monkeypatch, stat_mode, transition)

CONTRACT = REPO / "contracts" / "awa-contract.v1.json"


def _fin():
    return UX._load_finish()


# =====================================================================================
# (a) trigger classification -> preview gating
# =====================================================================================
@transition(Row(
    id="P2-REC-POSITIVES", phase="P2", title="Every direct finish phrase (+ paraphrase/casing) recognized",
    precondition="none (pure recall matcher)",
    inp="recognize_finish over the approved-phrase matrix",
    expected="all direct triggers + paraphrases + uppercase -> True (would preview)",
    oracle="test_finish_conversation::RecognizerTest::test_all_approved_phrases_and_paraphrases"))
def rec_positives(sb: Sandbox) -> str:
    positives = ["I'm done", "remove worktree", "can we close", "end session", "finish",
                 "finalize", "I am done!", "wrap this up", "close this workspace",
                 "remove the workspace", "let's close", "I'M DONE", "FINISH",
                 "REMOVE WORKTREE", "CAN WE CLOSE", "END SESSION", "FINALIZE"]
    for phrase in positives:
        check(UX.recognize_finish(phrase), f"must recognize {phrase!r}")
    return f"{len(positives)} direct/paraphrase/uppercase triggers all -> preview"


@transition(Row(
    id="P2-REC-NEGATIVES", phase="P2", title="Metalinguistic negatives never preview",
    precondition="none",
    inp="recognize_finish over negated/quoted/doc/feature/hypothetical/meta phrases",
    expected="all -> False (no preview)",
    oracle="test_finish_conversation::RecognizerTest::test_negated_quoted_documentation_feature_hypothetical_and_meta_rejected"))
def rec_negatives(sb: Sandbox) -> str:
    negatives = ["don't finish", "how does `finish` work?", "add a finish feature",
                 "the user said 'I'm done'", "document the close workflow",
                 "if I were done, what happens?", "show an example of remove worktree",
                 "explain the finish command", 'they wrote "finalize"',
                 "DON'T FINISH", "DOCUMENT THE CLOSE WORKFLOW",
                 "SHOW AN EXAMPLE OF REMOVE WORKTREE"]
    for phrase in negatives:
        check(not UX.recognize_finish(phrase), f"must NOT recognize {phrase!r}")
    return f"{len(negatives)} negated/quoted/doc/feature/hypothetical/meta -> no preview"


@transition(Row(
    id="P2-REC-CLI", phase="P2", title="Production `recognize` CLI classifies a positive/negative pair",
    precondition="none",
    inp="python3 finish_current.py recognize <phrase>",
    expected="finish_current=true for a direct trigger, false for a negation",
    oracle="test_finish_conversation::RecognizerTest (CLI surface of recognize_finish)"))
def rec_cli(sb: Sandbox) -> str:
    pos = json.loads(sb.run_consumer("recognize", "I'm done").stdout)
    neg = json.loads(sb.run_consumer("recognize", "don't finish").stdout)
    check_eq(pos.get("finish_current"), True, "positive CLI")
    check_eq(neg.get("finish_current"), False, "negative CLI")
    return "CLI recognize: 'I'm done'=true 'don't finish'=false"


@transition(Row(
    id="P2-HIGH-SIGNAL", phase="P2", title="High-signal finish match runs BEFORE the router",
    precondition="OperatorLoop with a router that explodes if consulted",
    inp="OperatorLoop.map('I'm done')",
    expected="verb=finish_current without the router ever being consulted",
    oracle="test_finish_conversation::RecognizerTest::test_high_signal_match_runs_before_router"))
def high_signal(sb: Sandbox) -> str:
    from consumer.operator_loop import OperatorLoop

    class BombRouter:
        def propose(self, *args):
            raise AssertionError("router must not receive direct finish wording")

    catalog = json.loads((REPO / "consumer" / "intent-catalog.v1.json").read_text(encoding="utf-8"))
    proposal = OperatorLoop(catalog, router=BombRouter()).map("I'm done")
    check_eq(proposal["verb"], "finish_current", "verb")
    return "verb=finish_current (router never consulted)"


# =====================================================================================
# (b) the immutable warning
# =====================================================================================
@transition(Row(
    id="P2-WARNING-SNAPSHOT", phase="P2", title="Immutable warning is byte-exact (frozen contract)",
    precondition="none",
    inp="WARNING_STATIC bytes + contract cross-check",
    expected="byte-identical to the frozen approved copy; contract carries the heading + Close correction",
    oracle="test_finish_conversation::WarningSnapshotTest::test_static_warning_byte_snapshot"))
def warning_snapshot(sb: Sandbox) -> str:
    expected = (
        "WARNING: Finish workspace requested\n\n"
        "Removing this temporary workspace permanently deletes work you have not committed: "
        "the uncommitted changes and untracked or ignored files listed below. Commit or retain "
        "them first if you want to keep them. Anything already committed is preserved -- if "
        "the branch has commits that are not shared yet, the branch is kept -- so committed "
        "work is never lost.\n\n"
        "How do you want to proceed? Reply with exactly one of: Commit, Retain, Mixed, Cancel, "
        "or Close.\n\n"
        "Commit --> Choose which items below to deliver; the agent commits and pushes or merges them.\n\n"
        "Retain --> Choose which items below to keep; the agent saves them on your computer, "
        "outside the workspace, so removal cannot delete them.\n\n"
        "Mixed  --> Choose Commit or Retain for each item; the agent does both.\n\n"
        "Cancel --> Do nothing and continue what you were doing.\n\n"
        "Close  --> Remove the temporary workspace now. Everything listed below is permanently "
        "deleted, the agent stops, and this chat stays open.\n\n"
        "To remove the workspace, reply with exactly: Close\n\n"
        "Permanently deleted on Close:")
    check_eq(UX.WARNING_STATIC.encode(), expected.encode(), "WARNING_STATIC bytes")
    # The frozen contract binds the warning by RENDERER REFERENCE + a frozen choice list
    # (it stores no literal warning text; the byte-exactness above IS the immutable payload).
    contract = CONTRACT.read_text(encoding="utf-8")
    check("render_warning" in contract, "contract references the render_warning renderer")
    check('"choices": ["Commit", "Retain", "Mixed", "Cancel", "Close"]' in contract,
          "contract freezes the five canonical choices")
    return "WARNING_STATIC byte-exact; contract renderer + frozen five-choice list intact"


@transition(Row(
    id="P2-WARNING-ROWS", phase="P2", title="Warning renders all rows with no truncation + None default",
    precondition="none",
    inp="render_warning(150 rows) and render_warning('')",
    expected="150th row present, no truncation; empty rows -> the None default line",
    oracle="test_finish_conversation::WarningSnapshotTest::test_complete_warning_rows_none_and_no_truncation"))
def warning_rows(sb: Sandbox) -> str:
    rows = "\n".join(f"{i}. p{i} | d{i}." for i in range(1, 151))
    rendered = UX.render_warning(rows)
    check(rendered.endswith("150. p150 | d150."), "150th row must be present")
    check_eq(rendered.count("\n"), UX.WARNING_STATIC.count("\n") + 150, "no truncation")
    check(UX.render_warning("").endswith("None | No operator work will be deleted."), "None default")
    return "150 rows rendered untruncated; empty -> None default"


@transition(Row(
    id="P2-WARNING-CLI", phase="P2", title="Production `warning` CLI renders the immutable copy",
    precondition="none",
    inp="python3 finish_current.py warning [--rows ...]",
    expected="default ends with the None line; explicit rows are appended verbatim",
    oracle="test_finish_conversation::WarningSnapshotTest (CLI surface of render_warning)"))
def warning_cli(sb: Sandbox) -> str:
    default = sb.run_consumer("warning").stdout
    check(default.startswith("WARNING: Finish workspace requested"), "heading")
    check(default.rstrip("\n").endswith("None | No operator work will be deleted."), "None default")
    withrow = sb.run_consumer("warning", "--rows", "1. branch | A tracked file.").stdout
    check(withrow.rstrip("\n").endswith("1. branch | A tracked file."), "explicit row appended")
    return "warning CLI: default None-line + explicit row appended verbatim"


# =====================================================================================
# (c) hook preview: block schema, fail-open, unsupported contexts, observability
# =====================================================================================
@transition(Row(
    id="P2-HOOK-BLOCK", phase="P2", title="Hook preview blocks with the exact warning + mints a challenge",
    precondition="linked worktree with a dirty draft",
    inp="handle_hook_payload('I'm done')",
    expected="continue=false; user_message == render_warning(rows); challenge minted; never routes to model",
    oracle="test_finish_conversation::HookAndDispatcherTest::test_hook_preview_blocks_with_exact_warning_and_bare_choice_handoff"))
def hook_block(sb: Sandbox) -> str:
    _, wt = sb.linked("handoff")
    Path(wt, "draft.txt").write_text("x", encoding="utf-8")
    response = UX.handle_hook_payload(sb.finish_payload(wt, conv="conv"))
    check_eq(response["continue"], False, "must block (never reach model)")
    check_eq(response["user_message"], UX.render_warning(UX.read_dialogue("conv")["rows"]),
             "exact warning handoff")
    check(UX._load_finish().read_challenge("conv")[0] is not None, "challenge minted")
    return "continue=false; exact warning; challenge minted"


@transition(Row(
    id="P2-HOOK-SHELL-SCHEMA", phase="P2", title="before-submit-prompt.sh emits the current block schema",
    precondition="linked worktree with a dirty draft",
    inp="echo <payload> | before-submit-prompt.sh",
    expected="rc=0; keys=={continue,user_message}; continue=false; exact render_warning message",
    oracle="test_finish_conversation::HookAndDispatcherTest::test_hook_script_uses_current_block_schema_and_exact_message"))
def hook_shell_schema(sb: Sandbox) -> str:
    _, wt = sb.linked("hookscript")
    Path(wt, "draft.txt").write_text("x", encoding="utf-8")
    payload = sb.finish_payload(wt, conv="hook-script")
    proc = sb.run_hook(HOOK_BEFORE_SUBMIT, json.dumps(payload))
    check_eq(proc.returncode, 0, f"hook rc ({proc.stderr})")
    out = json.loads(proc.stdout)
    check_eq(set(out), {"continue", "user_message"}, "block schema keys")
    check_eq(out["continue"], False, "continue=false")
    check_eq(out["user_message"], UX.render_warning(UX.read_dialogue("hook-script")["rows"]),
             "exact message")
    return "shell hook: {continue:false, user_message==render_warning(rows)}"


@transition(Row(
    id="P2-HOOK-FAILOPEN", phase="P2", title="Hook script fails OPEN on malformed input",
    precondition="none",
    inp="echo '{bad' | before-submit-prompt.sh",
    expected="rc=0; {continue:true} (never blocks a user on a parse fault)",
    oracle="test_finish_conversation::HookAndDispatcherTest::test_hook_script_fail_open_on_malformed_input"))
def hook_failopen(sb: Sandbox) -> str:
    proc = sb.run_hook(HOOK_BEFORE_SUBMIT, "{bad")
    check_eq(proc.returncode, 0, "hook rc")
    check_eq(json.loads(proc.stdout), {"continue": True}, "fail-open continue:true")
    return "malformed input -> {continue:true} (fail-open)"


@transition(Row(
    id="P2-HOOK-UNSUPPORTED", phase="P2", title="Unsupported contexts fail open with no challenge",
    precondition="primary checkout / background(cloud) / multi-root / absent-target payloads",
    inp="handle_hook_payload for each unsupported shape",
    expected="{continue:true}; no challenge; no dialogue for each",
    oracle="test_finish_conversation::HookAndDispatcherTest::test_unsupported_contexts_fail_open_without_challenge"))
def hook_unsupported(sb: Sandbox) -> str:
    repo = sb.make_repo("primary2")
    _, cloud_wt = sb.linked("cloud-linked")
    payloads = [
        sb.finish_payload(repo, conv="primary"),
        {**sb.finish_payload(cloud_wt, conv="cloud"), "is_background_agent": True},
        {**sb.finish_payload(repo, conv="multi"), "workspace_roots": [repo, str(sb.data)]},
        {"prompt": "finish", "conversation_id": "absent"},
    ]
    for payload in payloads:
        conv = payload["conversation_id"]
        out = UX.handle_hook_payload(payload)
        check_eq(out, {"continue": True}, f"fail-open for {conv}")
        check_eq(UX._load_finish().read_challenge(conv)[1], "absent", f"no challenge for {conv}")
        check(UX.read_dialogue(conv) is None, f"no dialogue for {conv}")
    return "primary/background/multi-root/absent all fail-open; no challenge/dialogue"


@transition(Row(
    id="P2-HOOK-OBSERVABILITY", phase="P2", title="Hook observation is bounded, private, metadata-only",
    precondition="linked worktree; a blocking preview",
    inp="handle_hook_payload then inspect the observation record + bound",
    expected="decision=block_warning; no prompt/path/file leak; 0700/0600; count<=limit",
    oracle="test_finish_conversation::HookAndDispatcherTest::test_hook_observability_is_bounded_private_and_metadata_only"))
def hook_observability(sb: Sandbox) -> str:
    _, wt = sb.linked("hook-observation")
    Path(wt, "draft.txt").write_text("x", encoding="utf-8")
    payload = sb.finish_payload(wt, conv="observe")
    response = UX.handle_hook_payload(payload)
    check_eq(response["continue"], False, "blocked")
    directory = UX._hook_observation_dir()
    files = list(directory.glob("hook-*.json"))
    check_eq(len(files), 1, "one observation record")
    text = files[0].read_text(encoding="utf-8")
    record = json.loads(text)
    check_eq(record["schema"], UX.HOOK_OBSERVATION_SCHEMA, "schema")
    check_eq(record["decision"], "block_warning", "decision")
    check_eq(len(record["output_sha256"]), 64, "output digest length")
    check(payload["prompt"] not in text and wt not in text and "draft.txt" not in text,
          "metadata-only (no prompt/path/file leak)")
    check_eq(stat_mode(directory), 0o700, "dir 0700")
    check_eq(stat_mode(files[0]), 0o600, "file 0600")
    for number in range(UX.HOOK_OBSERVATION_LIMIT + 5):
        UX.handle_hook_payload({"prompt": f"ordinary message {number}"})
    check(len(list(directory.glob("hook-*.json"))) <= UX.HOOK_OBSERVATION_LIMIT, "bounded")
    return f"block_warning; metadata-only; 0700/0600; bounded<= {UX.HOOK_OBSERVATION_LIMIT}"


@transition(Row(
    id="P2-PREVIEW-EXC-CLEAN", phase="P2", title="A preview fault cleans partial challenge (unconfirmable)",
    precondition="linked worktree; write_dialogue raised mid-preview",
    inp="handle_hook_payload with write_dialogue injected to fail",
    expected="{continue:true}; challenge left with hook_activated=false; no dialogue",
    oracle="test_finish_conversation::HookAndDispatcherTest::test_preview_exception_cleans_partial_challenge"))
def preview_exc_clean(sb: Sandbox) -> str:
    _, wt = sb.linked("partial")
    Path(wt, "draft.txt").write_text("x", encoding="utf-8")

    def fail(_record):
        raise OSError("disk full")

    with monkeypatch(UX, "write_dialogue", fail):
        out = UX.handle_hook_payload(sb.finish_payload(wt, conv="partial-conv"))
    check_eq(out, {"continue": True}, "fail-open")
    challenge, status = UX._load_finish().read_challenge("partial-conv")
    check_eq(status, "ok", "challenge present")
    check_eq(challenge["hook_activated"], False, "partial hook state unconfirmable")
    check(UX.read_dialogue("partial-conv") is None, "no dialogue")
    return "{continue:true}; hook_activated=false; no dialogue"


# =====================================================================================
# (d) choice canonicalization + dispatch
# =====================================================================================
@transition(Row(
    id="P2-CANON-CHOICES", phase="P2", title="Choice canonicalizer: case/trim + exact-Close + rejects",
    precondition="none (pure canonicalizer)",
    inp="canonicalize_choice over the full choice matrix",
    expected="Commit/Retain/Mixed/Cancel case/trim-insensitive; Close exact-only; documented reject reasons",
    oracle="test_finish_conversation::HookAndDispatcherTest::test_choice_canonicalizer_casing_trimming_and_reasons"))
def canon_choices(sb: Sandbox) -> str:
    variants = {
        "Commit": ("Commit", "commit", "COMMIT", "CoMmIt", " \tcommit\n"),
        "Retain": ("Retain", "retain", "RETAIN", "ReTaIn", "\nretain "),
        "Mixed": ("Mixed", "mixed", "MIXED", "MiXeD", " mixed\t"),
        "Cancel": ("Cancel", "cancel", "CANCEL", "CaNcEl", "\tcancel "),
    }
    for canonical, answers in variants.items():
        for answer in answers:
            check_eq(UX.canonicalize_choice(answer), (canonical, "ok"), f"{answer!r}")
            check(UX.is_exact_choice(answer), f"{answer!r} exact")
    check_eq(UX.canonicalize_choice("Close"), ("Close", "ok"), "exact Close")
    for answer in ("close", "CLOSE", "cLoSe", " Close ", "\tClose\n"):
        check_eq(UX.canonicalize_choice(answer), (None, "close_must_be_exact"), f"{answer!r}")
        check(not UX.is_exact_choice(answer), f"{answer!r} not exact")
    rejected = (("Close please", "choice_not_standalone"), ("yes", "choice_not_standalone"),
                ("", "choice_empty"), (True, "boolean_not_allowed"), (False, "boolean_not_allowed"),
                (1, "choice_not_string"), (None, "choice_not_string"))
    for answer, reason in rejected:
        check_eq(UX.canonicalize_choice(answer), (None, reason), f"{answer!r}")
    check_eq(UX.canonicalize_choice("Cancel", [{"name": "x"}]), (None, "attachments_present"),
             "attachments rejected")
    return "case/trim ok; Close exact-only; extra-word/yes/bool/int/None/attachment rejected"


@transition(Row(
    id="P2-CANCEL-NOOP", phase="P2", title="Cancel is a literal no-op that clears the dialogue",
    precondition="pending dialogue; a draft present",
    inp="dispatch_choice(Cancel)",
    expected="{ok, cancelled, mutated_repo:false}; file untouched; dialogue+challenge gone",
    oracle="test_finish_conversation::HookAndDispatcherTest::test_cancel_is_literal_noop"))
def cancel_noop(sb: Sandbox) -> str:
    _, wt = sb.linked("cancel2")
    draft = Path(wt, "draft.txt")
    draft.write_text("keep", encoding="utf-8")
    UX.preview_payload(sb.finish_payload(wt, conv="cancel-conv"))
    before = draft.read_bytes()
    result = UX.dispatch_choice("cancel-conv", "Cancel")
    check_eq(result, {"ok": True, "state": "cancelled", "mutated_repo": False}, "cancel result")
    check_eq(draft.read_bytes(), before, "file untouched")
    check(UX.read_dialogue("cancel-conv") is None, "dialogue cleared")
    check_eq(UX._load_finish().read_challenge("cancel-conv")[1], "absent", "challenge gone")
    return "{ok,cancelled,mutated_repo:false}; file intact; dialogue+challenge gone"


@transition(Row(
    id="P2-CLOSE-ROUTING", phase="P2", title="Only literal Close routes to the kernel executor",
    precondition="pending dialogue; an executor spy",
    inp="dispatch_choice over Close variants, attachments, then exact Close",
    expected="variants refused (reason + CLOSE_CORRECTION), executor untouched; exact Close removes once",
    oracle="test_finish_conversation::HookAndDispatcherTest::test_close_routes_only_literal_close_to_kernel_executor"))
def close_routing(sb: Sandbox) -> str:
    _, wt = sb.linked("routeclose")
    Path(wt, "draft").write_text("x", encoding="utf-8")
    UX.preview_payload(sb.finish_payload(wt, conv="close-conv"))
    seen = []

    def executor(**kwargs):
        seen.append(kwargs)
        return {"outcome": "removed", "branch_action": "retained"}

    for answer, reason in (("close", "close_must_be_exact"), ("CLOSE", "close_must_be_exact"),
                           ("cLoSe", "close_must_be_exact"), (" Close ", "close_must_be_exact"),
                           ("Close please", "choice_not_standalone"), ("yes", "choice_not_standalone"),
                           (True, "boolean_not_allowed")):
        rejected = UX.dispatch_choice("close-conv", answer, executor=executor)
        check(not rejected["ok"], f"{answer!r} must be refused")
        check_eq(rejected["reason"], reason, f"{answer!r} reason")
        check(not rejected["mutated_repo"], f"{answer!r} no mutation")
        if reason == "close_must_be_exact":
            check_eq(rejected["user_message"], UX.CLOSE_CORRECTION, "CLOSE_CORRECTION")
        check_eq(seen, [], "executor must stay untouched on a refusal")
    attached = UX.dispatch_choice("close-conv", "Close", attachments=[{"name": "x"}],
                                  executor=executor)
    check_eq(attached["reason"], "attachments_present", "attachment reason")
    check_eq(seen, [], "attachment must not reach executor")
    removed = UX.dispatch_choice("close-conv", "Close", executor=executor)
    check(removed["workspace_removed"], "exact Close removes")
    check_eq(seen[0]["authorization"], "Close", "literal Close reaches kernel")
    check(removed["agent_stopping"] and removed["chat_remains_open"], "agent-stop semantics")
    return "variants refused (CLOSE_CORRECTION), executor untouched; exact Close removes once"


@transition(Row(
    id="P2-CRM-SELECTION", phase="P2", title="Commit/Retain/Mixed enter a selection state, never Close",
    precondition="pending dialogue per choice",
    inp="dispatch_choice(Commit|Retain|Mixed)",
    expected="awaiting_(commit|retain|mixed)_selection; challenge preserved; no removal",
    oracle="test_finish_conversation::HookAndDispatcherTest::test_commit_retain_mixed_require_selection_state_and_never_close"))
def crm_selection(sb: Sandbox) -> str:
    for choice, state in (("Commit", "awaiting_commit_selection"),
                          ("Retain", "awaiting_retain_selection"),
                          ("Mixed", "awaiting_mixed_selection")):
        _, wt = sb.linked("state" + choice.lower())
        Path(wt, "draft").write_text("x", encoding="utf-8")
        conv = "conv-" + choice
        UX.preview_payload(sb.finish_payload(wt, conv=conv))
        out = UX.dispatch_choice(conv, choice)
        check_eq(out["state"], state, f"{choice} state")
        check(UX._load_finish().read_challenge(conv)[0] is not None, f"{choice} challenge preserved")
    return "Commit/Retain/Mixed -> awaiting_*_selection; challenge preserved; never Close"


@transition(Row(
    id="P2-DISPATCH-CLI-CLOSE", phase="P2", title="Production `dispatch --current` really removes (throwaway)",
    precondition="hook preview + published + captured Close on a THROWAWAY worktree",
    inp="python3 finish_current.py dispatch --current (cwd=throwaway wt)",
    expected="workspace_removed=true; agent_stopping=true; chat_remains_open=true; worktree gone",
    oracle="test_finish_conversation::HookAndDispatcherTest (end-to-end consumer->kernel via the documented CLI)"))
def dispatch_cli_close(sb: Sandbox) -> str:
    _, wt = sb.linked("cli-close")
    Path(wt, "draft.txt").write_text("discard", encoding="utf-8")
    payload = sb.finish_payload(wt, conv="cli-close")
    check_eq(UX.handle_hook_payload(payload)["continue"], False, "preview blocks")
    check(UX.mark_hook_published(payload), "warning published")
    check(UX.handle_hook_payload({**payload, "prompt": "Close", "event_id": "cli-close-act"})["continue"],
          "captured Close continues")
    proc = sb.run_consumer("dispatch", "--current", cwd=wt)
    check_eq(proc.returncode, 0, f"dispatch rc ({proc.stderr})")
    result = json.loads(proc.stdout)
    check(result.get("workspace_removed") in (True, None), "workspace_removed")
    check_eq(result.get("agent_stopping"), True, "agent_stopping")
    check_eq(result.get("chat_remains_open"), True, "chat_remains_open")
    check(not Path(wt).exists(), "throwaway worktree physically removed")
    return "dispatch --current: workspace_removed; agent_stopping; chat_remains_open; wt gone"


@transition(Row(
    id="P2-CANCEL-UNDER-DRIFT", phase="P2", title="Cancel is unconditional even under live inventory drift",
    precondition="pending dialogue, then a new untracked file appears (drift)",
    inp="dispatch_choice(Cancel) after drift",
    expected="cancelled; no repo mutation; dialogue+challenge cleared despite drift",
    oracle="plan: Cancel unconditional (mirrors test_cancel_is_literal_noop under a drifted worktree)"))
def cancel_under_drift(sb: Sandbox) -> str:
    _, wt = sb.linked("cancel-drift")
    Path(wt, "draft.txt").write_text("keep", encoding="utf-8")
    UX.preview_payload(sb.finish_payload(wt, conv="cancel-drift"))
    Path(wt, "surprise.txt").write_text("drift after preview", encoding="utf-8")
    result = UX.dispatch_choice("cancel-drift", "Cancel")
    check_eq(result, {"ok": True, "state": "cancelled", "mutated_repo": False}, "cancel under drift")
    check(UX.read_dialogue("cancel-drift") is None, "dialogue cleared under drift")
    check(Path(wt, "surprise.txt").exists(), "drift file untouched")
    return "Cancel clears the dialogue under drift; no mutation"


@transition(Row(
    id="P2-CLOSE-REFUSE-UNDER-DRIFT", phase="P2", title="Close refuses under live inventory drift (preserves)",
    precondition="hook preview + published + captured Close, then drift appears",
    inp="dispatch --current after drift (real kernel executor)",
    expected="refused (fingerprint mismatch); worktree preserved; dialogue kept live",
    oracle="test_finish_kernel::IdenticalRefusalGateTest::test_fingerprint_drift_refuses (consumer surface)"))
def close_refuse_under_drift(sb: Sandbox) -> str:
    _, wt = sb.linked("close-drift")
    Path(wt, "draft.txt").write_text("x", encoding="utf-8")
    payload = sb.finish_payload(wt, conv="close-drift")
    UX.handle_hook_payload(payload)
    UX.mark_hook_published(payload)
    UX.handle_hook_payload({**payload, "prompt": "Close", "event_id": "drift-close"})
    Path(wt, "surprise.txt").write_text("drift after preview", encoding="utf-8")
    proc = sb.run_consumer("dispatch", "--current", cwd=wt)
    result = json.loads(proc.stdout)
    check(not result.get("workspace_removed"), "must NOT report removed under drift")
    check(Path(wt).exists(), "worktree preserved under drift")
    return f"drift -> not removed ({result.get('reason') or result.get('outcome')}); worktree preserved"


# =====================================================================================
# (e) retain lifecycle + row-selection gates
# =====================================================================================
@transition(Row(
    id="P2-RETAIN-LIFECYCLE", phase="P2", title="Retain artifact: protected, restore-proven, secret-gated, lifecycle",
    precondition="linked worktree with staged/renamed/secret/symlink content",
    inp="create_retain (secret gate), manifest, list, restore, delete-exact-id",
    expected="protected+restore_proven+explicit_secrets; 0700/0600; restore content+symlink; delete needs exact id",
    oracle="test_finish_conversation::RetainArtifactTest::test_typed_artifact_restore_proof_permissions_lifecycle_and_secret"))
def retain_lifecycle(sb: Sandbox) -> str:
    _, wt = sb.linked("retainall")
    Path(wt, "tracked.txt").write_text("base\n", encoding="utf-8")
    Path(wt, "rename-old.txt").write_text("rename\n", encoding="utf-8")
    sb.commit_all(wt, "tracked state")
    Path(wt, "tracked.txt").write_text("staged\n", encoding="utf-8")
    sb.git(wt, "add", "tracked.txt")
    sb.git(wt, "mv", "rename-old.txt", "rename-new.txt")
    Path(wt, ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    Path(wt, "target.txt").write_text("target", encoding="utf-8")
    os.symlink("target.txt", Path(wt, "inside-link"))
    preview = UX.preview_payload(sb.finish_payload(wt, conv="retain-all"))
    check(not preview["continue"], "preview blocks")
    UX.dispatch_choice("retain-all", "Retain")
    dialogue = UX.read_dialogue("retain-all")
    indices = list(range(1, len(dialogue["visible"]) + 1))
    raised = False
    try:
        UX.create_retain("retain-all", indices)
    except UX.FinishUXError:
        raised = True
    check(raised, "secret selection must require --allow-secrets")
    result = UX.create_retain("retain-all", indices, allow_secrets=True)
    artifact_id = result["artifact_id"]
    artifact = UX._artifact_path(artifact_id)
    doc = UX._manifest(artifact)
    check(doc["protected"] and doc["restore_proven"] and doc["explicit_secrets"],
          "protected+restore_proven+explicit_secrets")
    check_eq(stat_mode(artifact), 0o700, "artifact dir 0700")
    check_eq(stat_mode(artifact / "manifest.json"), 0o600, "manifest 0600")
    check(artifact_id in {x["artifact_id"] for x in UX.list_retained()}, "listed")
    dest = sb.data / "restored"
    restored = UX.restore_retain(artifact_id, str(dest))
    check(restored["restored_entries"] > 0, "restored entries")
    check_eq((dest / "tracked.txt").read_text(encoding="utf-8"), "staged\n", "restored staged content")
    check((dest / "inside-link").is_symlink(), "restored symlink")
    wrong = False
    try:
        UX.delete_retain(artifact_id, "yes")
    except UX.FinishUXError:
        wrong = True
    check(wrong and artifact.exists(), "delete requires the exact artifact id")
    deleted = UX.delete_retain(artifact_id, artifact_id)
    check_eq(deleted["deleted"], artifact_id, "deleted id")
    check(not artifact.exists(), "artifact removed on exact-id delete")
    return "protected+restore_proven+explicit_secrets; 0700/0600; restore ok; exact-id delete"


@transition(Row(
    id="P2-RETAIN-FRESH-PREVIEW", phase="P2", title="Retain forces a fresh preview + a separate Close",
    precondition="pending dialogue; a draft",
    inp="complete_retain then inspect the refreshed dialogue",
    expected="close_still_required=true; fresh_preview blocks; challenge preserved",
    oracle="test_finish_conversation::RetainArtifactTest::test_retain_action_requires_fresh_preview_and_separate_close"))
def retain_fresh_preview(sb: Sandbox) -> str:
    _, wt = sb.linked("retainfresh")
    Path(wt, "draft.txt").write_text("x", encoding="utf-8")
    UX.preview_payload(sb.finish_payload(wt, conv="fresh"))
    UX.dispatch_choice("fresh", "Retain")
    out = UX.complete_retain("fresh", [1])
    check(out["close_still_required"], "close_still_required")
    check(not out["fresh_preview"]["continue"], "fresh preview blocks")
    check(out["fresh_preview"]["user_message"].endswith("None | No operator work will be deleted."),
          "fresh preview None default")
    check(UX._load_finish().read_challenge("fresh")[0] is not None, "challenge preserved")
    return "close_still_required=true; fresh preview blocks; challenge preserved"


@transition(Row(
    id="P2-RETAIN-CLI", phase="P2", title="Production retain / retain-list / retain-restore / retain-delete CLIs",
    precondition="pending dialogue in awaiting_retain_selection (non-secret row)",
    inp="retain --rows; retain-list; retain-restore; retain-delete (wrong then exact id)",
    expected="artifact created + listed + restored; delete refuses a wrong confirmation, succeeds on exact id",
    oracle="test_finish_conversation::RetainArtifactTest (CLI surface of the retain lifecycle)"))
def retain_cli(sb: Sandbox) -> str:
    _, wt = sb.linked("retaincli")
    Path(wt, "draft.txt").write_text("keep-me", encoding="utf-8")
    UX.preview_payload(sb.finish_payload(wt, conv="retaincli"))
    UX.dispatch_choice("retaincli", "Retain")
    out = json.loads(sb.run_consumer("retain", "--conversation-id", "retaincli", "--rows", "1").stdout)
    artifact_id = out["artifact"]["artifact_id"]
    listed = json.loads(sb.run_consumer("retain-list").stdout)
    check(artifact_id in {a["artifact_id"] for a in listed["artifacts"]}, "retain-list shows artifact")
    dest = sb.data / "cli-restore"
    restored = json.loads(sb.run_consumer(
        "retain-restore", "--artifact-id", artifact_id, "--destination", str(dest)).stdout)
    check(restored["restored_entries"] > 0, "retain-restore restored entries")
    wrong = sb.run_consumer("retain-delete", "--artifact-id", artifact_id, "--confirm", "yes")
    check(wrong.returncode != 0, "retain-delete must refuse a non-exact confirmation")
    check(UX._artifact_path(artifact_id).exists(), "artifact survives a wrong confirmation")
    good = json.loads(sb.run_consumer(
        "retain-delete", "--artifact-id", artifact_id, "--confirm", artifact_id).stdout)
    check_eq(good["deleted"], artifact_id, "exact-id delete")
    check(not UX._artifact_path(artifact_id).exists(), "artifact gone after exact-id delete")
    return "retain CLI lifecycle: created, listed, restored; delete needs exact id"


@transition(Row(
    id="P2-IGNORED-RETAIN-ONLY", phase="P2", title="Ignored rows are Retain-only (commit refuses pre-mutation)",
    precondition="worktree with ignored files/dir + an ignored .env secret",
    inp="inventory eligibility flags + commit_selected_local(ignored rows)",
    expected="each ignored row commit_eligible=false/retain_eligible=true; commit raises retain_only pre-mutation",
    oracle="test_finish_phase2_final_blockers::IgnoredRowsRetainOnlyTest"))
def ignored_retain_only(sb: Sandbox) -> str:
    _, wt = sb.linked("ignored-classification")
    Path(wt, ".gitignore").write_text("ignored.txt\nignored-dir/\n.env.production\n", encoding="utf-8")
    sb.git(wt, "add", ".gitignore")
    sb.commit_all(wt, "ignore fixtures")
    Path(wt, "ignored.txt").write_text("ignored file\n", encoding="utf-8")
    Path(wt, "ignored-dir").mkdir()
    Path(wt, "ignored-dir/child.txt").write_text("ignored child\n", encoding="utf-8")
    Path(wt, ".env.production").write_text("TOKEN=not-a-real-secret\n", encoding="utf-8")
    Path(wt, "ordinary.txt").write_text("ordinary\n", encoding="utf-8")
    fin = _fin()
    target = fin.resolve_target(wt)
    inventory = fin.build_inventory(wt, target["git_dir"])
    ignored = [r for r in inventory["entries"] if r["class"] == "ignored" and not r["hidden"]]
    check(len(ignored) >= 3, "at least 3 visible ignored rows")
    for row in ignored:
        check(not row["commit_eligible"], f"ignored row {row.get('path')} must not be commit-eligible")
        check(row["retain_eligible"], f"ignored row {row.get('path')} must be retain-eligible")
    UX.preview_payload(sb.finish_payload(wt, conv="ignored-classification"))
    UX.dispatch_choice("ignored-classification", "Commit")
    dialogue = UX.read_dialogue("ignored-classification")
    ignored_rows = [n for n, row in enumerate(dialogue["visible"], 1) if row["class"] == "ignored"]
    before_head = sb.git(wt, "rev-parse", "HEAD").stdout.strip()
    raised = False
    try:
        UX.commit_selected_local("ignored-classification", ignored_rows, "must refuse")
    except UX.FinishUXError as exc:
        raised = "retain_only" in str(exc)
    check(raised, "commit of ignored rows must raise retain_only")
    check_eq(sb.git(wt, "rev-parse", "HEAD").stdout.strip(), before_head, "no commit occurred")
    return f"{len(ignored)} ignored rows commit-ineligible/retain-only; commit refused pre-mutation"


# =====================================================================================
# (f) commit delivery boundaries (network only in Commit/Mixed)
# =====================================================================================
@transition(Row(
    id="P2-COMMIT-EVIDENCE-OK", phase="P2", title="Strict delivery proof passes for a well-formed merge",
    precondition="none (pure evaluator)",
    inp="verify_delivery_evidence(good) and complete-zero-checks-stable",
    expected="ok=true for a single-repo exact-head merge-commit PR with complete passing checks",
    oracle="test_finish_conversation::CommitDeliveryProofTest::test_strict_delivery_success_and_complete_zero_checks"))
def commit_evidence_ok(sb: Sandbox) -> str:
    oid = "a" * 40
    good = {"github_repositories": ["KleinPerkins/awa"], "preserved_head_oid": oid,
            "merged_prs": [{"number": 7, "state": "MERGED", "headRefOid": oid}],
            "compare": {"status": "ahead"},
            "checks": [{"state": "SUCCESS"}, {"state": "NEUTRAL"}, {"state": "SKIPPED"}],
            "checks_complete": True}
    check(UX.verify_delivery_evidence(**good)["ok"], "good delivery ok")
    empty = dict(good)
    empty["checks"] = []
    empty["checks_observations"] = [[], []]
    empty["zero_check_stable"] = True
    check(UX.verify_delivery_evidence(**empty)["ok"], "stable zero-checks ok")
    return "ok for exact-head merge-commit PR (with checks and stable zero-checks)"


@transition(Row(
    id="P2-COMMIT-FAILURE-MATRIX", phase="P2", title="Delivery proof refuses every unsafe mutation",
    precondition="none",
    inp="verify_delivery_evidence over the failure matrix (+ merge_commit_enabled=false)",
    expected="ok=false for multi-repo, bad head, no PR, diverged, incomplete/pending/failing checks, squash/rebase-only",
    oracle="test_finish_conversation::CommitDeliveryProofTest::test_delivery_failure_matrix"))
def commit_failure_matrix(sb: Sandbox) -> str:
    oid = "a" * 40

    def good():
        return {"github_repositories": ["KleinPerkins/awa"], "preserved_head_oid": oid,
                "merged_prs": [{"number": 7, "state": "MERGED", "headRefOid": oid}],
                "compare": {"status": "ahead"},
                "checks": [{"state": "SUCCESS"}], "checks_complete": True}

    mutations = [("github_repositories", ["a/x", "b/y"]), ("preserved_head_oid", "bad"),
                 ("merged_prs", []), ("compare", {"status": "diverged"}),
                 ("checks_complete", False), ("checks", [{"state": "PENDING"}]),
                 ("checks", [{"state": "FAILURE"}]), ("checks", [{"state": "UNKNOWN"}]),
                 ("merge_commit_enabled", False)]
    for key, value in mutations:
        evidence = good()
        evidence[key] = value
        check(not UX.verify_delivery_evidence(**evidence)["ok"], f"{key}={value!r} must refuse")
    return f"{len(mutations)} unsafe deliveries all refused (incl. squash/rebase-only)"


@transition(Row(
    id="P2-COMMIT-NETWORK-COMMITONLY", phase="P2", title="No network on the preview/Cancel path",
    precondition="linked worktree; a gh-call bomb installed",
    inp="preview + Cancel with UX.subprocess.run trapping any gh call",
    expected="no gh invocation escapes outside Commit/Mixed delivery",
    oracle="test_finish_conversation::CommitDeliveryProofTest::test_network_calls_structurally_commit_only"))
def commit_network_commitonly(sb: Sandbox) -> str:
    _, wt = sb.linked("nonet2")
    Path(wt, "draft").write_text("x", encoding="utf-8")
    real_run = UX.subprocess.run

    def bomb(cmd, *args, **kwargs):
        if isinstance(cmd, list) and cmd and cmd[0] == "gh":
            raise AssertionError("network escaped Commit delivery adapter")
        return real_run(cmd, *args, **kwargs)

    with monkeypatch(UX.subprocess, "run", bomb):
        out = UX.preview_payload(sb.finish_payload(wt, conv="nonet-conv"))
        check(not out["continue"], "preview blocks")
        UX.dispatch_choice("nonet-conv", "Cancel")
    return "no gh call on preview/Cancel (network is Commit/Mixed-only)"


@transition(Row(
    id="P2-COMMIT-GH-MISSING", phase="P2", title="Missing gh / no network fails honestly",
    precondition="delivery runner raises FileNotFoundError('gh')",
    inp="verify_delivery_network with a missing-gh runner",
    expected="ok=false; reason=delivery_evidence_unavailable (never a false success)",
    oracle="test_finish_conversation::CommitDeliveryProofTest::test_missing_gh_or_network_fails_honestly"))
def commit_gh_missing(sb: Sandbox) -> str:
    def missing(*args, **kwargs):
        raise FileNotFoundError("gh")

    _, wt = sb.linked("ghfail")
    proof = UX.verify_delivery_network(wt, "cursor/worktree/ghfail", "a" * 40, runner=missing)
    check(not proof["ok"], "must fail")
    check_eq(proof["reason"], "delivery_evidence_unavailable", "honest reason")
    return "missing gh -> ok=false, delivery_evidence_unavailable"


@transition(Row(
    id="P2-COMMIT-SELECTED", phase="P2", title="Selected commit excludes unselected rows + forces fresh preview",
    precondition="linked worktree with selected + unselected files; deliver_commit stubbed ok",
    inp="complete_commit([selected]) with a pre-commit hook present",
    expected="only the selected file is committed; unselected stays untracked; close_still_required; fresh preview blocks",
    oracle="test_finish_conversation::CommitDeliveryProofTest::test_selected_commit_excludes_unselected_rows_and_requires_fresh_preview"))
def commit_selected(sb: Sandbox) -> str:
    _, wt = sb.linked("selectcommit")
    sb.git(wt, "config", "user.name", "AWA Test")
    sb.git(wt, "config", "user.email", "awa-test@example.invalid")
    marker = sb.data / "pre-commit-ran"
    hook = Path(sb.git(wt, "rev-parse", "--git-path", "hooks/pre-commit").stdout.strip())
    hook.write_text(f"#!/bin/sh\nprintf ran > '{marker}'\n", encoding="utf-8")
    hook.chmod(0o755)
    Path(wt, "selected.txt").write_text("selected", encoding="utf-8")
    Path(wt, "unselected.txt").write_text("unselected", encoding="utf-8")
    UX.preview_payload(sb.finish_payload(wt, conv="select-commit"))
    UX.dispatch_choice("select-commit", "Commit")
    dialogue = UX.read_dialogue("select-commit")
    by_path = {entry["path"]: idx for idx, entry in enumerate(dialogue["visible"], 1)}
    with monkeypatch(UX, "deliver_commit",
                     lambda root, branch, head_oid, **kw: {"ok": True, "proof": {"ok": True},
                                                           "head_oid": head_oid}):
        result = UX.complete_commit("select-commit", [by_path["selected.txt"]], "deliver selected")
    check(result["ok"], "commit ok")
    names = sb.git(wt, "show", "--format=", "--name-only", "HEAD").stdout.splitlines()
    check_eq(names, ["selected.txt"], "only selected committed")
    check(marker.exists(), "selected commit runs the normal pre-commit hook")
    check(Path(wt, "unselected.txt").exists(), "unselected file preserved")
    check("?? unselected.txt" in sb.git(wt, "status", "--porcelain").stdout, "unselected still untracked")
    check(result["close_still_required"] and not result["fresh_preview"]["continue"],
          "close still required; fresh preview blocks")
    return "only selected committed (hooks ran); unselected untracked; fresh preview + close required"


@transition(Row(
    id="P2-COMMIT-FAIL-HONEST", phase="P2", title="Commit delivery failure is honest + preserves the local commit",
    precondition="linked worktree; deliver_commit stubbed to fail",
    inp="complete_commit with a failing delivery",
    expected="ok=false; local_commit_preserved=true; the local commit remains; worktree preserved",
    oracle="test_finish_conversation::CommitDeliveryProofTest::test_commit_delivery_failure_is_honest_and_preserves_local_commit"))
def commit_fail_honest(sb: Sandbox) -> str:
    _, wt = sb.linked("commitfail")
    sb.git(wt, "config", "user.name", "AWA Test")
    sb.git(wt, "config", "user.email", "awa-test@example.invalid")
    Path(wt, "draft.txt").write_text("x", encoding="utf-8")
    UX.preview_payload(sb.finish_payload(wt, conv="commit-fail"))
    UX.dispatch_choice("commit-fail", "Commit")
    with monkeypatch(UX, "deliver_commit",
                     lambda root, branch, head_oid, **kw: {"ok": False, "reason": "network"}):
        result = UX.complete_commit("commit-fail", [1], "local preserved")
    check(not result["ok"], "delivery failed honestly")
    check(result["local_commit_preserved"], "local commit preserved")
    check_eq(sb.git(wt, "show", "--format=%s", "-s", "HEAD").stdout.strip(), "local preserved",
             "local commit remains")
    check(Path(wt).exists(), "worktree preserved on delivery failure")
    return "ok=false; local_commit_preserved; local commit remains; worktree preserved"


@transition(Row(
    id="P2-MIXED-EXECUTE", phase="P2", title="Mixed executes a disjoint+complete row partition (commit + retain)",
    precondition="linked worktree with >=3 rows; deliver_commit stubbed ok",
    inp="complete_mixed(commit_rows, retain_rows) incl. overlap + incomplete refusals",
    expected="overlap + incomplete refuse pre-mutation; disjoint+complete delivers commit + protected retain; re-previews",
    oracle="test_finish_hardening::StateMachineAdversarialTest::test_mixed_requires_exact_disjoint_complete_partition + ActionCompletionLatchTest"))
def mixed_execute(sb: Sandbox) -> str:
    _, wt = sb.linked("mixedexec")
    sb.git(wt, "config", "user.name", "AWA Test")
    sb.git(wt, "config", "user.email", "awa-test@example.invalid")
    Path(wt, "to-commit.txt").write_text("commit me", encoding="utf-8")
    Path(wt, "keep-a.txt").write_text("retain a", encoding="utf-8")
    Path(wt, "keep-b.txt").write_text("retain b", encoding="utf-8")
    UX.preview_payload(sb.finish_payload(wt, conv="mixed-exec"))
    UX.dispatch_choice("mixed-exec", "Mixed")
    dialogue = UX.read_dialogue("mixed-exec")
    visible = dialogue["visible"]
    n = len(visible)
    by_path = {entry["path"]: idx for idx, entry in enumerate(visible, 1)}
    c = by_path["to-commit.txt"]
    others = [i for i in range(1, n + 1) if i != c]   # retain ALL non-commit rows -> complete partition
    check(n >= 3 and len(others) >= 2, f"need >=3 visible rows for a partition (got {n})")

    def stub(root, branch, head_oid, **kw):
        return {"ok": True, "proof": {"ok": True}, "head_oid": head_oid}

    def refused(commit_rows, retain_rows):
        try:
            UX.complete_mixed("mixed-exec", commit_rows, retain_rows, "must refuse")
            return None
        except UX.FinishUXError as exc:
            return str(exc)

    with monkeypatch(UX, "deliver_commit", stub):
        overlap = refused([c], [c] + others)          # same row in both partitions -> refuse (pre-mutation)
        incomplete = refused([c], others[:-1])        # leaves a row unassigned -> refuse (pre-mutation)
        check(overlap is not None, "overlapping partition refuses")
        check(incomplete is not None, "incomplete partition refuses")
        result = UX.complete_mixed("mixed-exec", [c], others, "mixed deliver")
    check(result["ok"] and result["action"] == "Mixed", f"mixed completes ({result.get('action')})")
    check(result["commit"]["ok"], "commit partition delivered")
    check(result["retained"]["protected"], "retain partition is a protected artifact")
    check(result["close_still_required"], "Mixed still requires a separate exact Close")
    check(not result["fresh_preview"]["continue"], "Mixed re-previews (fresh preview blocks); never removes")
    names = sb.git(wt, "show", "--format=", "--name-only", "HEAD").stdout.splitlines()
    check_eq(names, ["to-commit.txt"], "only the commit-row was committed")
    check(Path(wt).exists(), "worktree preserved (Mixed never removes)")
    return (f"overlap={overlap}; incomplete={incomplete}; disjoint+complete -> "
            "commit delivered + protected retain; re-previews; wt preserved")


# =====================================================================================
# (g) post-action fresh recon + hook republish (second exact Close required)
# =====================================================================================
@transition(Row(
    id="P2-REPUBLISH-2ND-CLOSE", phase="P2", title="After a hook-owned action, the next Close only republishes",
    precondition="a completed hook-owned Retain (action_complete_refresh_pending)",
    inp="Close #1 (republishes) -> publish -> Close #2 (acts once)",
    expected="first Close republishes the warning (no removal); only the second exact Close invokes removal once",
    oracle="test_finish_phase2_final_blockers::HookOwnedActionRefreshTest::test_exact_close_trigger_only_publishes_then_second_close_invokes_once"))
def republish_second_close(sb: Sandbox) -> str:
    from unittest import mock
    name = "hook-owned-close"
    _, wt = sb.linked(name)
    Path(wt, "draft.txt").write_text("preserve\n", encoding="utf-8")
    payload = sb.finish_payload(wt, conv=name)
    check(not UX.handle_hook_payload(payload)["continue"], "preview blocks")
    check(UX.mark_hook_published(payload), "warning published")
    UX.handle_hook_payload({**payload, "prompt": "Retain", "event_id": name + "-retain"})
    check_eq(UX.dispatch_choice(name)["state"], "awaiting_retain_selection", "retain selection")
    dialogue = UX.read_dialogue(name)
    completed = UX.complete_retain(name, list(range(1, len(dialogue["visible"]) + 1)))
    check(completed["action_complete"], "retain completed")
    check_eq(UX.read_dialogue(name)["state"], "action_complete_refresh_pending", "latched")

    first_close = {**payload, "prompt": "Close", "event_id": "first-close-publishes"}
    warning = UX.handle_hook_payload(first_close)
    check(not warning["continue"], "first Close only republishes (no act)")
    check(UX.mark_hook_published(first_close), "republish published")
    check_eq(UX.read_dialogue(name)["state"], "awaiting_choice", "now awaiting choice")
    second_close = UX.handle_hook_payload({**payload, "prompt": "Close", "event_id": "second-close-acts"})
    check(second_close["continue"], "second Close continues to dispatch")
    executor = mock.Mock(return_value={"outcome": "removed", "reason": "finish_removed",
                                       "branch_action": "retained"})
    removed = UX.dispatch_choice(name, executor=executor)
    check(removed["workspace_removed"], "second Close removes")
    executor.assert_called_once()
    check(Path(wt).exists(), "unit executor must not remove the throwaway test root")
    check_eq(len(UX.list_retained()), 1, "the retained artifact persists")
    return "first Close republishes; second exact Close invokes removal exactly once"


# =====================================================================================
# (h) hook registration schema that Layer B depends on
# =====================================================================================
@transition(Row(
    id="P2-HOOK-INSTALL", phase="P2", title="install-hooks.sh is idempotent with the current entry schema",
    precondition="a disposable hooks.json path",
    inp="install-hooks.sh twice + --check",
    expected="idempotent bytes; matcher=UserPromptSubmit; failClosed=false; timeout=20",
    oracle="test_finish_conversation::HookAndDispatcherTest::test_hook_install_check_and_idempotency"))
def hook_install(sb: Sandbox) -> str:
    hooks = sb.data / "hooks.json"
    env = {**os.environ, "AWA_HOOKS_JSON": str(hooks)}
    first = sb.run_raw([str(INSTALL_HOOKS)], env=env)
    check_eq(first.returncode, 0, f"install rc ({first.stderr})")
    one = hooks.read_bytes()
    second = sb.run_raw([str(INSTALL_HOOKS)], env=env)
    check_eq(second.returncode, 0, "second install rc")
    check_eq(hooks.read_bytes(), one, "idempotent bytes")
    check_eq(sb.run_raw([str(INSTALL_HOOKS), "--check"], env=env).returncode, 0, "--check ok")
    entry = json.loads(one)["hooks"]["beforeSubmitPrompt"][0]
    check_eq(entry["matcher"], "UserPromptSubmit", "matcher")
    check_eq(entry["failClosed"], False, "failClosed=false (advisory; Layer B caveat)")
    check_eq(entry["timeout"], 20, "timeout")
    return "idempotent; matcher=UserPromptSubmit; failClosed=false; timeout=20"
