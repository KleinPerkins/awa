"""Phase 2 conversational finish: deterministic recall/UX with no new removal authority."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path

from consumer import egress
from consumer import finish_current as UX
from consumer.operator_loop import OperatorLoop
from .helpers import EngineTestCase, commit_all, git


_REPO = Path(__file__).resolve().parents[2]
_HOOK = _REPO / "kernel" / "hooks" / "before-submit-prompt.sh"
_INSTALL_HOOKS = _REPO / "kernel" / "hooks" / "install-hooks.sh"


class Phase2Base(EngineTestCase):
    def linked(self, name: str = "finish2") -> tuple[str, str]:
        repo = self.make_repo(name)
        wt = self.add_worktree(repo, f"cursor/worktree/{name}")
        return repo, wt

    def payload(self, wt: str, prompt: str = "I'm done", conv: str = "conv") -> dict:
        try:
            target = UX.resolve_linked_root({"cwd": wt})
        except UX.FinishUXError:
            target = None
        if target is not None:
            UX._load_finish()._roots_module().write_current_session(
                wt, session_id=conv, conversation_id=conv,
                branch=target["branch"], common_dir=target["common_dir"])
        return {
            "hook_event_name": "beforeSubmitPrompt",
            "prompt": prompt,
            "conversation_id": conv,
            "session_id": conv,
            "cwd": wt,
            "workspace_roots": [wt],
        }

    def live_payload(self, wt: str, prompt: str = "I'm done", *,
                     session: str = "live-session", conv: str = "live-conversation") -> dict:
        """Cursor 3.11.13 beforeSubmitPrompt shape observed in the Desktop UAT."""
        return {
            "conversation_id": conv,
            "generation_id": "request-generation",
            "composer_mode": "agent",
            "prompt": prompt,
            "attachments": [],
            "session_id": session,
            "hook_event_name": "beforeSubmitPrompt",
            "cursor_version": "3.11.13",
            "workspace_roots": [wt],
            "transcript_path": None,
        }


class RecognizerTest(Phase2Base):
    def test_all_approved_phrases_and_paraphrases(self) -> None:
        positives = [
            "I'm done", "remove worktree", "can we close", "end session", "finish",
            "finalize", "I am done!", "wrap this up", "close this workspace",
            "remove the workspace", "let's close", "I'M DONE", "FINISH",
            "REMOVE WORKTREE", "CAN WE CLOSE", "END SESSION", "FINALIZE",
        ]
        for phrase in positives:
            with self.subTest(phrase=phrase):
                self.assertTrue(UX.recognize_finish(phrase))

    def test_negated_quoted_documentation_feature_hypothetical_and_meta_rejected(self) -> None:
        negatives = [
            "don't finish", "how does `finish` work?", "add a finish feature",
            "the user said 'I'm done'", "document the close workflow",
            "if I were done, what happens?", "show an example of remove worktree",
            "explain the finish command", 'they wrote "finalize"',
            "DON'T FINISH", "DOCUMENT THE CLOSE WORKFLOW",
            "SHOW AN EXAMPLE OF REMOVE WORKTREE",
        ]
        for phrase in negatives:
            with self.subTest(phrase=phrase):
                self.assertFalse(UX.recognize_finish(phrase))

    def test_high_signal_match_runs_before_router(self) -> None:
        class BombRouter:
            def propose(self, *args):
                raise AssertionError("router must not receive direct finish wording")

        catalog = json.loads((_REPO / "consumer" / "intent-catalog.v1.json")
                             .read_text(encoding="utf-8"))
        loop = OperatorLoop(catalog, router=BombRouter())
        proposal = loop.map("I'm done")
        self.assertEqual(proposal["verb"], "finish_current")

    def test_finish_ignores_trusted_boolean_bypass(self) -> None:
        calls = []

        def executor(verb, params, target):
            calls.append((verb, params, target))
            return {"ok": True, "user_message": "preview"}

        catalog = json.loads((_REPO / "consumer" / "intent-catalog.v1.json")
                             .read_text(encoding="utf-8"))
        result = OperatorLoop(catalog, router=object(), executor=executor,
                              session_id="c").handle("finish", confirm=True)
        self.assertEqual(calls[0][0], "finish_current")
        self.assertEqual(calls[0][1], {"conversation_id": "c", "preview_only": True})
        self.assertNotIn("authorization", calls[0][1])
        self.assertIsNone(result["confirmation"])


class WarningSnapshotTest(Phase2Base):
    def test_static_warning_byte_snapshot(self) -> None:
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
            "Permanently deleted on Close:"
        )
        self.assertEqual(UX.WARNING_STATIC.encode(), expected.encode())

    def test_complete_warning_rows_none_and_no_truncation(self) -> None:
        rows = "\n".join(f"{i}. p{i} | d{i}." for i in range(1, 151))
        rendered = UX.render_warning(rows)
        self.assertTrue(rendered.endswith("150. p150 | d150."))
        self.assertEqual(rendered.count("\n"), UX.WARNING_STATIC.count("\n") + 150)
        none = UX.render_warning("")
        self.assertTrue(none.endswith("None | No operator work will be deleted."))

    def test_warning_has_narrow_egress_exception_only(self) -> None:
        warning = UX.render_warning("1. branch | A tracked file you changed.")
        self.assertEqual(egress.scan_finish_warning(warning), [])
        self.assertTrue(egress.scan_object(warning))
        self.assertTrue(egress.scan_finish_warning("Commit this branch"))


class HookAndDispatcherTest(Phase2Base):
    def _session_start(self, wt: str, *, session: str,
                       conversation: str | None = None) -> dict:
        payload = {
            "session_id": session,
            "hook_event_name": "sessionStart",
            "is_background_agent": False,
            "workspace_roots": [wt],
        }
        if conversation is not None:
            payload["conversation_id"] = conversation
        env = {**os.environ, "XDG_STATE_HOME": str(self.state_home)}
        env.pop("DEV_SESSION_ID", None)
        proc = subprocess.run(
            [str(_REPO / "kernel" / "hooks" / "worktree-session.sh")],
            input=json.dumps(payload), capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return json.loads(proc.stdout)

    def test_current_session_cas_uses_shared_common_dir_lock_abi(self) -> None:
        roots = UX._load_finish()._roots_module()
        fin = UX._load_finish()
        common = str(self.data_home / "repo" / ".git")
        self.assertEqual(roots._common_dir_key(common), fin.common_dir_key(common))
        expected = Path(fin.lockfile_for(common))
        self.assertEqual(
            Path(roots.locks_dir()) / f"common-{roots._common_dir_key(common)}.lock",
            expected)

    def test_live_first_prompt_binds_partial_session_and_never_reaches_model(self) -> None:
        _, wt = self.linked("live-bind")
        Path(wt, "draft.txt").write_text("x", encoding="utf-8")
        self._session_start(wt, session="live-session", conversation=None)
        roots = UX._load_finish()._roots_module()
        current, status = roots._read_current_session(wt, allow_partial=True)
        self.assertEqual(status, "partial")
        self.assertEqual(current["conversation_id"], "")

        model_calls = []
        payload = self.live_payload(wt)
        old = os.environ.pop("DEV_SESSION_ID", None)
        try:
            response = UX.handle_hook_payload(payload)
            if response["continue"]:
                model_calls.append(payload["prompt"])
        finally:
            if old is not None:
                os.environ["DEV_SESSION_ID"] = old
        self.assertEqual(model_calls, [], "a blocked finish prompt must not route to the model")
        self.assertEqual(set(response), {"continue", "user_message"})
        self.assertFalse(response["continue"])
        dialogue = UX.read_dialogue("live-conversation")
        self.assertEqual(response["user_message"], UX.WARNING_STATIC + "\n" + dialogue["rows"])
        current, status = roots.read_current_session(wt)
        self.assertEqual(status, "ok")
        self.assertEqual(current["session_id"], "live-session")
        self.assertEqual(current["conversation_id"], "live-conversation")

    def test_first_prompt_waits_for_fire_and_forget_session_start_rebind(self) -> None:
        _, wt = self.linked("live-race")
        Path(wt, "draft.txt").write_text("x", encoding="utf-8")
        target = UX.resolve_linked_root({"workspace_roots": [wt]})
        roots = UX._load_finish()._roots_module()
        roots.write_current_session(
            wt, session_id="previous-session", conversation_id="previous-conversation",
            branch=target["branch"], common_dir=target["common_dir"])

        def delayed_session_start() -> None:
            time.sleep(0.1)
            roots.bind_current_session(
                wt, session_id="new-session", conversation_id="new-conversation",
                branch=target["branch"], common_dir=target["common_dir"],
                source="sessionStart")

        worker = threading.Thread(target=delayed_session_start)
        worker.start()
        old_wait = os.environ.get("AWA_FINISH_SESSION_BIND_WAIT_SECONDS")
        os.environ["AWA_FINISH_SESSION_BIND_WAIT_SECONDS"] = "1"
        try:
            response = UX.handle_hook_payload(self.live_payload(
                wt, session="new-session", conv="new-conversation"))
        finally:
            worker.join()
            if old_wait is None:
                os.environ.pop("AWA_FINISH_SESSION_BIND_WAIT_SECONDS", None)
            else:
                os.environ["AWA_FINISH_SESSION_BIND_WAIT_SECONDS"] = old_wait
        self.assertFalse(response["continue"], response)
        current, status = roots.read_current_session(wt)
        self.assertEqual(status, "ok")
        self.assertEqual(
            (current["session_id"], current["conversation_id"]),
            ("new-session", "new-conversation"))

    def test_first_prompt_binding_refuses_second_session_conversation_and_ambiguous_root(
            self) -> None:
        _, wt = self.linked("bind-refuse")
        _, other = self.linked("bind-refuse-other")
        Path(wt, "draft.txt").write_text("x", encoding="utf-8")
        self._session_start(wt, session="bound-session", conversation=None)
        old_wait = os.environ.get("AWA_FINISH_SESSION_BIND_WAIT_SECONDS")
        os.environ["AWA_FINISH_SESSION_BIND_WAIT_SECONDS"] = "0"
        try:
            first = UX.handle_hook_payload(self.live_payload(
                wt, session="bound-session", conv="bound-conversation"))
            second_session = UX.handle_hook_payload(self.live_payload(
                wt, session="other-session", conv="other-conversation"))
            cross_conversation = UX.handle_hook_payload(self.live_payload(
                wt, session="bound-session", conv="different-conversation"))
            ambiguous = self.live_payload(
                wt, session="bound-session", conv="ambiguous-conversation")
            ambiguous["workspace_roots"] = [wt, other]
            cross_root = UX.handle_hook_payload(ambiguous)
        finally:
            if old_wait is None:
                os.environ.pop("AWA_FINISH_SESSION_BIND_WAIT_SECONDS", None)
            else:
                os.environ["AWA_FINISH_SESSION_BIND_WAIT_SECONDS"] = old_wait
        self.assertFalse(first["continue"])
        self.assertEqual(second_session, {"continue": True})
        self.assertEqual(cross_conversation, {"continue": True})
        self.assertEqual(cross_root, {"continue": True})
        for conv in ("other-conversation", "different-conversation",
                     "ambiguous-conversation"):
            self.assertEqual(UX._load_finish().read_challenge(conv)[1], "absent")
            self.assertIsNone(UX.read_dialogue(conv))

    def test_hook_mid_session_branch_switch_no_longer_fails_open(self) -> None:
        """END-TO-END regression for the reported field symptom: earlier in one long-lived agent
        session/conversation, a first `beforeSubmitPrompt` "I'm done" established a heartbeat +
        current-session binding on the worktree's FIRST branch. An ordinary mid-session
        `git checkout` to a second branch -- exactly the sequential-PR agent workflow this repo's
        own worktree conventions expect -- must not silently fail the finish hook open on the
        next "I'm done" from the SAME live session. BITING: before this fix, the second hook call
        returned {"continue": True} with the private hook-observation decision=fail_open /
        reason=heartbeat_existing_branch_mismatch -- the EXACT diagnostic recorded in the field.
        (Fixing heartbeat() alone still reproduces this end-to-end through
        bind_current_session's sibling check, just renamed to current_session_target_mismatch --
        both were fixed together for this test to pass.) After the fix, the real preview/warning
        fires for the new, freshly-reverified branch instead."""
        _, wt = self.linked("mid-session-switch")
        Path(wt, "draft.txt").write_text("x", encoding="utf-8")
        session, conv = "live-session", "live-conversation"
        first = UX.handle_hook_payload(self.live_payload(wt, session=session, conv=conv))
        self.assertFalse(first["continue"], first)

        git(wt, "checkout", "-q", "-b", "docs-followup")

        second = UX.handle_hook_payload(self.live_payload(wt, session=session, conv=conv))
        self.assertEqual(
            set(second), {"continue", "user_message"},
            "same live session's ordinary branch switch must not silently fail the hook open: "
            f"{second}")
        self.assertFalse(second["continue"], second)
        dialogue = UX.read_dialogue(conv)
        self.assertIsNotNone(dialogue)
        self.assertEqual(dialogue["target"]["branch"], "docs-followup")
        self.assertEqual(second["user_message"], UX.render_warning(dialogue["rows"]))

        directory = UX._hook_observation_dir()
        files = sorted(directory.glob("hook-*.json"), key=lambda p: p.stat().st_mtime)
        self.assertGreaterEqual(len(files), 2)
        latest = json.loads(files[-1].read_text(encoding="utf-8"))
        self.assertEqual(latest["decision"], "block_warning")

    def test_hook_stale_different_session_branch_disagreement_no_longer_fails_open(
            self) -> None:
        """END-TO-END regression for the NEW defect this task fixes (distinct from the PR #82
        fix above): a DIFFERENT, long-idle session/tab's heartbeat on this SAME worktree --
        recorded once, then never refreshed again, e.g. a chat left open and forgotten -- must
        not silently veto a live, different session's ordinary "I'm done" after the branch has
        since changed. This is the EXACT real field repro shape (two distinct session
        identities, one gone stale, the branch changed in between). BITING: before this fix, this
        returned {"continue": True} with decision=fail_open / reason=heartbeat_existing_branch_
        mismatch -- reproduced against the actual poisoned worktree during this investigation."""
        _, wt = self.linked("stale-other-session")
        Path(wt, "draft.txt").write_text("x", encoding="utf-8")
        roots = UX._load_finish()._roots_module()
        common = git(
            wt, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
        seeded = roots.heartbeat(
            wt, branch="cursor/worktree/stale-other-session", common_dir=common,
            session_id="idle-old-session")
        self.assertTrue(seeded.get("ok", True), seeded)
        path = Path(roots.record_path(wt))
        rec = json.loads(path.read_text(encoding="utf-8"))
        stale_epoch = roots._now_epoch() - (roots.BRANCH_DISAGREEMENT_STALE_SECONDS + 60)
        stale_timestamp = roots._iso_from_epoch(stale_epoch)
        member = rec["sessions"][roots.session_key("idle-old-session")]
        member["last_heartbeat_epoch"] = stale_epoch
        member["last_heartbeat"] = stale_timestamp
        member["first_seen"] = stale_timestamp
        # idle-old-session is (so far) also the record's top-level writer -- the record's own
        # member-projection invariant (top-level fields == that session's member fields) requires
        # aging those in lockstep too; this is fixture upkeep, not part of what is under test.
        if rec.get("session_id") == "idle-old-session":
            rec["last_heartbeat_epoch"] = stale_epoch
            rec["last_heartbeat"] = stale_timestamp
            rec["first_seen"] = stale_timestamp
        path.write_text(json.dumps(rec), encoding="utf-8")

        git(wt, "checkout", "-q", "-b", "docs-followup-live")

        response = UX.handle_hook_payload(self.live_payload(
            wt, session="live-session-2", conv="live-conversation-2"))
        self.assertEqual(
            set(response), {"continue", "user_message"},
            f"a different, stale session's frozen branch claim must not fail the hook open: "
            f"{response}")
        self.assertFalse(response["continue"], response)
        dialogue = UX.read_dialogue("live-conversation-2")
        self.assertIsNotNone(dialogue)
        self.assertEqual(dialogue["target"]["branch"], "docs-followup-live")

        directory = UX._hook_observation_dir()
        files = sorted(directory.glob("hook-*.json"), key=lambda p: p.stat().st_mtime)
        self.assertGreaterEqual(len(files), 1)
        latest = json.loads(files[-1].read_text(encoding="utf-8"))
        self.assertEqual(latest["decision"], "block_warning")

    def test_hook_preview_blocks_with_exact_warning_and_bare_choice_handoff(self) -> None:
        _, wt = self.linked("handoff")
        Path(wt, "draft.txt").write_text("x", encoding="utf-8")
        response = UX.handle_hook_payload(self.payload(wt))
        self.assertFalse(response["continue"])
        self.assertTrue(UX.mark_hook_published(self.payload(wt)))
        self.assertEqual(response["user_message"],
                         UX.render_warning(UX.read_dialogue("conv")["rows"]))
        self.assertIsNotNone(UX._load_finish().read_challenge("conv")[0])
        UX.handle_hook_payload(self.payload(wt, prompt="Retain"))
        old = os.getcwd()
        os.chdir(wt)
        try:
            choice = UX.dispatch_current()
        finally:
            os.chdir(old)
        self.assertEqual(choice["state"], "awaiting_retain_selection")

    def test_choice_canonicalizer_casing_trimming_and_reasons(self) -> None:
        variants = {
            "Commit": ("Commit", "commit", "COMMIT", "CoMmIt", " \tcommit\n"),
            "Retain": ("Retain", "retain", "RETAIN", "ReTaIn", "\nretain "),
            "Mixed": ("Mixed", "mixed", "MIXED", "MiXeD", " mixed\t"),
            "Cancel": ("Cancel", "cancel", "CANCEL", "CaNcEl", "\tcancel "),
        }
        for canonical, answers in variants.items():
            for answer in answers:
                with self.subTest(canonical=canonical, answer=answer):
                    self.assertEqual(UX.canonicalize_choice(answer), (canonical, "ok"))
                    self.assertTrue(UX.is_exact_choice(answer))
        self.assertEqual(UX.canonicalize_choice("Close"), ("Close", "ok"))
        for answer in ("close", "CLOSE", "cLoSe", " Close ", "\tClose\n"):
            with self.subTest(answer=answer):
                self.assertEqual(
                    UX.canonicalize_choice(answer), (None, "close_must_be_exact"))
                self.assertFalse(UX.is_exact_choice(answer))
        rejected = (
            ("Close please", "choice_not_standalone"),
            ("yes", "choice_not_standalone"),
            ("", "choice_empty"),
            (True, "boolean_not_allowed"),
            (False, "boolean_not_allowed"),
            (1, "choice_not_string"),
            (None, "choice_not_string"),
        )
        for answer, reason in rejected:
            with self.subTest(answer=answer):
                self.assertEqual(UX.canonicalize_choice(answer), (None, reason))
        self.assertEqual(
            UX.canonicalize_choice("Cancel", [{"name": "x"}]),
            (None, "attachments_present"))

    def test_cancel_is_literal_noop(self) -> None:
        _, wt = self.linked("cancel2")
        draft = Path(wt, "draft.txt")
        draft.write_text("keep", encoding="utf-8")
        UX.preview_payload(self.payload(wt, conv="cancel-conv"))
        before = draft.read_bytes()
        result = UX.dispatch_choice("cancel-conv", "Cancel")
        self.assertEqual(result, {"ok": True, "state": "cancelled", "mutated_repo": False})
        self.assertEqual(draft.read_bytes(), before)
        self.assertIsNone(UX.read_dialogue("cancel-conv"))
        self.assertEqual(UX._load_finish().read_challenge("cancel-conv")[1], "absent")

    def test_close_routes_only_literal_close_to_kernel_executor(self) -> None:
        _, wt = self.linked("routeclose")
        Path(wt, "draft").write_text("x", encoding="utf-8")
        UX.preview_payload(self.payload(wt, conv="close-conv"))
        seen = []

        def executor(**kwargs):
            seen.append(kwargs)
            return {"outcome": "removed", "branch_action": "retained"}

        for answer, reason in (
            ("close", "close_must_be_exact"),
            ("CLOSE", "close_must_be_exact"),
            ("cLoSe", "close_must_be_exact"),
            (" Close ", "close_must_be_exact"),
            ("Close please", "choice_not_standalone"),
            ("yes", "choice_not_standalone"),
            (True, "boolean_not_allowed"),
        ):
            rejected = UX.dispatch_choice("close-conv", answer, executor=executor)
            self.assertFalse(rejected["ok"], answer)
            self.assertEqual(rejected["reason"], reason)
            self.assertFalse(rejected["mutated_repo"])
            if reason == "close_must_be_exact":
                self.assertEqual(rejected["user_message"], UX.CLOSE_CORRECTION)
            self.assertEqual(seen, [])
        attached = UX.dispatch_choice(
            "close-conv", "Close", attachments=[{"name": "x"}], executor=executor)
        self.assertEqual(attached["reason"], "attachments_present")
        self.assertEqual(seen, [])
        removed = UX.dispatch_choice("close-conv", "Close", executor=executor)
        self.assertTrue(removed["workspace_removed"])
        self.assertEqual(seen[0]["authorization"], "Close")
        self.assertTrue(removed["agent_stopping"])
        self.assertTrue(removed["chat_remains_open"])

    def test_commit_retain_mixed_require_selection_state_and_never_close(self) -> None:
        for choice, state in (
            ("Commit", "awaiting_commit_selection"),
            ("Retain", "awaiting_retain_selection"),
            ("Mixed", "awaiting_mixed_selection"),
        ):
            _, wt = self.linked("state" + choice.lower())
            Path(wt, "draft").write_text("x", encoding="utf-8")
            conv = "conv-" + choice
            UX.preview_payload(self.payload(wt, conv=conv))
            out = UX.dispatch_choice(conv, choice)
            self.assertEqual(out["state"], state)
            self.assertIsNotNone(UX._load_finish().read_challenge(conv)[0])

    def test_unsupported_contexts_fail_open_without_challenge(self) -> None:
        repo = self.make_repo("primary2")
        _, cloud_wt = self.linked("cloud-linked")
        payloads = [
            self.payload(repo, conv="primary"),
            {**self.payload(cloud_wt, conv="cloud"), "is_background_agent": True},
            {**self.payload(repo, conv="multi"),
             "workspace_roots": [repo, str(self.data_home)]},
            {"prompt": "finish", "conversation_id": "absent"},
        ]
        for payload in payloads:
            conv = payload["conversation_id"]
            out = UX.handle_hook_payload(payload)
            self.assertEqual(out, {"continue": True})
            self.assertEqual(UX._load_finish().read_challenge(conv)[1], "absent")
            self.assertIsNone(UX.read_dialogue(conv))

    def test_opaque_top_level_and_nested_cloud_handles_fail_open_on_linked_root(self) -> None:
        cases = [
            ("top-background", "is_background_agent", "background-agent-handle", False),
            ("top-broker", "cloud_agent_identity_broker", "broker-handle", False),
            ("nested-background", "is_background_agent", "opaque-job-123", True),
            ("nested-broker", "cloud_agent_identity_broker", {"handle": "opaque"}, True),
        ]
        for label, field, value, nested in cases:
            with self.subTest(label=label):
                _, wt = self.linked(label)
                payload = self.payload(wt, conv=label)
                if nested:
                    payload["tool_input"] = {field: value}
                else:
                    payload[field] = value
                out = UX.handle_hook_payload(payload)
                self.assertEqual(out, {"continue": True})
                self.assertEqual(UX._load_finish().read_challenge(label)[1], "absent")
                self.assertIsNone(UX.read_dialogue(label))

    def test_explicit_false_cloud_values_keep_normal_desktop_linked_behavior(self) -> None:
        false_values = (None, False, 0, "", "false", "0", "no", "off", [], {})
        for field in ("is_background_agent", "cloud_agent_identity_broker"):
            for index, value in enumerate(false_values):
                with self.subTest(field=field, value=value):
                    _, wt = self.linked(
                        "desktop-" + field.replace("_", "-") + "-" + str(index))
                    payload = {"workspace_roots": [wt], field: value}
                    self.assertFalse(UX._unsupported(payload))
                    self.assertEqual(UX.resolve_linked_root(payload)["root"], os.path.realpath(wt))
        _, wt = self.linked("desktop-false-hook")
        payload = self.payload(wt, conv="desktop-false-hook")
        payload["is_background_agent"] = False
        payload["tool_input"] = {"cloud_agent_identity_broker": "off"}
        out = UX.handle_hook_payload(payload)
        self.assertFalse(out["continue"], out)
        self.assertEqual(UX._load_finish().read_challenge("desktop-false-hook")[1], "ok")

    def test_hook_preview_preserves_malformed_heartbeat_bytes_and_mints_no_dialogue(self) -> None:
        _, wt = self.linked("hook-malformed-heartbeat")
        payload = self.payload(wt, conv="hook-malformed-heartbeat")
        target = UX.resolve_linked_root(payload)
        roots = UX._load_finish()._roots_module()
        roots.heartbeat(
            wt, session_id="hook-malformed-heartbeat", branch=target["branch"],
            common_dir=target["common_dir"])
        record = Path(roots.record_path(wt))
        raw = b'{"schema":"active_root/v1","sessions":'
        record.write_bytes(raw)
        out = UX.handle_hook_payload(payload)
        self.assertEqual(out, {"continue": True})
        self.assertEqual(record.read_bytes(), raw)
        self.assertEqual(
            UX._load_finish().read_challenge("hook-malformed-heartbeat")[1], "absent")
        self.assertIsNone(UX.read_dialogue("hook-malformed-heartbeat"))

    def test_next_current_dispatch_repairs_power_loss_after_physical_removal(self) -> None:
        _, wt = self.linked("power-loss-recovery")
        Path(wt, "draft").write_text("discard", encoding="utf-8")
        conversation = "power-loss-recovery"
        UX.preview_payload(self.payload(wt, conv=conversation))
        dialogue = UX.read_dialogue(conversation)
        fin = UX._load_finish()
        challenge, status = fin._read_challenge_raw(conversation)
        self.assertEqual(status, "ok")
        target = dialogue["target"]
        inventory = fin.build_inventory(wt, target["git_dir"])
        disposition = fin.branch_disposition(
            wt, target["branch"], target["head"], target["common_dir"])
        identity = fin._operation_identity_payload(
            root=wt, git_dir=target["git_dir"], common_dir=target["common_dir"],
            branch=target["branch"], head=target["head"],
            conversation_id=conversation, nonce=challenge["nonce"],
            generation=challenge["generation"], session_id=dialogue["session_id"],
            session_key_value=fin._roots_module().session_key(dialogue["session_id"]),
            boot_id_value=challenge["boot_id"],
            install_id_value=challenge["install_id"],
            root_incarnation_value=challenge["root_incarnation"],
            git_dir_incarnation_value=challenge["git_dir_incarnation"],
            fingerprint=challenge["fingerprint"],
            claim="direct", branch_disposition_value=disposition,
            discard_count=len(inventory["entries"]))
        with fin.common_dir_lock(target["common_dir"]):
            fin._prepare_removal_journal_locked(identity=identity)
            removed = subprocess.run(
                ["git", "--git-dir=" + target["common_dir"], "worktree", "remove",
                 "--force", os.path.realpath(wt)],
                cwd=os.path.dirname(target["common_dir"]), capture_output=True, text=True)
        self.assertEqual(removed.returncode, 0, removed.stderr)
        kernel_recovered = fin.reconcile_removal(
            **target, conversation_id=dialogue["conversation_id"],
            session_id=dialogue["session_id"], expected_nonce=dialogue["nonce"],
            expected_generation=dialogue["generation"])
        self.assertEqual(kernel_recovered["outcome"], "removed", kernel_recovered)
        self.assertEqual(fin._roots_module().read_current_session(wt)[1], "absent")
        saved = os.environ.get("DEV_SESSION_ID")
        os.environ.pop("DEV_SESSION_ID", None)
        try:
            recovered = UX.dispatch_current()
        finally:
            if saved is None:
                os.environ.pop("DEV_SESSION_ID", None)
            else:
                os.environ["DEV_SESSION_ID"] = saved
        self.assertTrue(recovered["workspace_removed"], recovered)
        self.assertTrue(recovered["agent_stopping"])
        rendered = json.dumps(recovered, sort_keys=True)
        self.assertNotIn(dialogue["fingerprint"], rendered)
        self.assertNotIn(dialogue["nonce"], rendered)
        self.assertNotIn(kernel_recovered["operation_id"], rendered)
        self.assertIsNone(UX._read_dialogue_raw(conversation))

    def test_hook_script_fail_open_on_malformed_input(self) -> None:
        proc = subprocess.run([str(_HOOK)], input="{bad", capture_output=True, text=True,
                              env={**os.environ, "XDG_STATE_HOME": str(self.state_home)})
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout), {"continue": True})

    def test_hook_script_uses_current_block_schema_and_exact_message(self) -> None:
        _, wt = self.linked("hookscript")
        Path(wt, "draft.txt").write_text("x", encoding="utf-8")
        payload = self.payload(wt, conv="hook-script")
        proc = subprocess.run(
            [str(_HOOK)], input=json.dumps(payload), capture_output=True, text=True,
            env={**os.environ, "XDG_STATE_HOME": str(self.state_home)})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual(set(out), {"continue", "user_message"})
        self.assertFalse(out["continue"])
        self.assertEqual(out["user_message"],
                         UX.render_warning(UX.read_dialogue("hook-script")["rows"]))

    def test_hook_observability_is_bounded_private_and_metadata_only(self) -> None:
        _, wt = self.linked("hook-observation")
        Path(wt, "draft.txt").write_text("x", encoding="utf-8")
        payload = self.payload(wt, conv="observe")
        response = UX.handle_hook_payload(payload)
        self.assertFalse(response["continue"])
        directory = UX._hook_observation_dir()
        files = list(directory.glob("hook-*.json"))
        self.assertEqual(len(files), 1)
        record_text = files[0].read_text(encoding="utf-8")
        record = json.loads(record_text)
        self.assertEqual(record["schema"], UX.HOOK_OBSERVATION_SCHEMA)
        self.assertEqual(record["decision"], "block_warning")
        self.assertEqual(record["identity_outcome"], "matched")
        self.assertEqual(record["root_outcome"], "matched")
        self.assertEqual(record["root_candidate_count"], 1)
        self.assertEqual(len(record["output_sha256"]), 64)
        self.assertNotIn(payload["prompt"], record_text)
        self.assertNotIn(wt, record_text)
        self.assertNotIn("draft.txt", record_text)
        self.assertEqual(stat_mode(directory), 0o700)
        self.assertEqual(stat_mode(files[0]), 0o600)

        for number in range(UX.HOOK_OBSERVATION_LIMIT + 5):
            UX.handle_hook_payload({"prompt": f"ordinary message {number}"})
        self.assertLessEqual(
            len(list(directory.glob("hook-*.json"))), UX.HOOK_OBSERVATION_LIMIT)

    def test_preview_exception_cleans_partial_challenge(self) -> None:
        _, wt = self.linked("partial")
        Path(wt, "draft.txt").write_text("x", encoding="utf-8")
        original = UX.write_dialogue

        def fail(_record):
            raise OSError("disk full")

        UX.write_dialogue = fail
        try:
            out = UX.handle_hook_payload(self.payload(wt, conv="partial-conv"))
        finally:
            UX.write_dialogue = original
        self.assertEqual(out, {"continue": True})
        challenge, status = UX._load_finish().read_challenge("partial-conv")
        self.assertEqual(status, "ok")
        self.assertFalse(challenge["hook_activated"],
                         "partial hook state must remain unconfirmable")
        self.assertIsNone(UX.read_dialogue("partial-conv"))

    def test_hook_install_check_and_idempotency(self) -> None:
        hooks = self.data_home / "hooks.json"
        env = {**os.environ, "AWA_HOOKS_JSON": str(hooks)}
        first = subprocess.run([str(_INSTALL_HOOKS)], env=env, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        one = hooks.read_bytes()
        second = subprocess.run([str(_INSTALL_HOOKS)], env=env, capture_output=True, text=True)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(hooks.read_bytes(), one)
        check = subprocess.run([str(_INSTALL_HOOKS), "--check"], env=env,
                               capture_output=True, text=True)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        entry = json.loads(one)["hooks"]["beforeSubmitPrompt"][0]
        self.assertEqual(entry["matcher"], "UserPromptSubmit")
        self.assertFalse(entry["failClosed"])
        self.assertEqual(entry["timeout"], 20)

    def test_normal_uninstall_preserves_protected_retain(self) -> None:
        home = self.data_home / "install-home"
        env = {
            **os.environ,
            "HOME": str(home),
            "XDG_DATA_HOME": str(home / ".local" / "share"),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_STATE_HOME": str(home / ".local" / "state"),
        }
        install = _REPO / "install.sh"
        first = subprocess.run([str(install)], env=env, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        retained = Path(env["XDG_STATE_HOME"]) / "awa" / "protected-retain" / (
            "retain-" + "a" * 32)
        retained.mkdir(parents=True)
        (retained / "manifest.json").write_text('{"protected":true}\n', encoding="utf-8")
        ordinary = Path(env["XDG_STATE_HOME"]) / "awa" / "ordinary"
        ordinary.write_text("remove", encoding="utf-8")
        removed = subprocess.run([str(install), "--uninstall"], env=env,
                                 capture_output=True, text=True)
        self.assertEqual(removed.returncode, 0, removed.stdout + removed.stderr)
        self.assertTrue((retained / "manifest.json").exists())
        self.assertFalse(ordinary.exists())


class RetainArtifactTest(Phase2Base):
    def test_typed_artifact_restore_proof_permissions_lifecycle_and_secret(self) -> None:
        _, wt = self.linked("retainall")
        Path(wt, "tracked.txt").write_text("base\n", encoding="utf-8")
        Path(wt, "rename-old.txt").write_text("rename\n", encoding="utf-8")
        commit_all(wt, "tracked state")
        Path(wt, "tracked.txt").write_text("staged\n", encoding="utf-8")
        git(wt, "add", "tracked.txt")
        git(wt, "mv", "rename-old.txt", "rename-new.txt")
        Path(wt, ".env").write_text("TOKEN=secret\n", encoding="utf-8")
        Path(wt, "target.txt").write_text("target", encoding="utf-8")
        os.symlink("target.txt", Path(wt, "inside-link"))
        preview = UX.preview_payload(self.payload(wt, conv="retain-all"))
        self.assertFalse(preview["continue"])
        UX.dispatch_choice("retain-all", "Retain")
        dialogue = UX.read_dialogue("retain-all")
        indices = list(range(1, len(dialogue["visible"]) + 1))
        with self.assertRaises(UX.FinishUXError):
            UX.create_retain("retain-all", indices)
        result = UX.create_retain("retain-all", indices, allow_secrets=True)
        artifact_id = result["artifact_id"]
        artifact = UX._artifact_path(artifact_id)
        doc = UX._manifest(artifact)
        self.assertTrue(doc["protected"])
        self.assertTrue(doc["restore_proven"])
        self.assertTrue(doc["explicit_secrets"])
        self.assertTrue(doc["status_snapshot_hex"])
        self.assertTrue(doc["index_snapshot_hex"])
        self.assertEqual(stat_mode(artifact), 0o700)
        self.assertEqual(stat_mode(artifact / "manifest.json"), 0o600)
        self.assertIn(artifact_id, {x["artifact_id"] for x in UX.list_retained()})
        dest = self.data_home / "restored"
        restored = UX.restore_retain(artifact_id, str(dest))
        self.assertGreater(restored["restored_entries"], 0)
        self.assertEqual((dest / "tracked.txt").read_text(encoding="utf-8"), "staged\n")
        self.assertTrue((dest / "inside-link").is_symlink())
        with self.assertRaises(UX.FinishUXError):
            UX.delete_retain(artifact_id, "yes")
        self.assertTrue(artifact.exists())
        deleted = UX.delete_retain(artifact_id, artifact_id)
        self.assertEqual(deleted["deleted"], artifact_id)
        self.assertFalse(artifact.exists())

    def test_retain_action_requires_fresh_preview_and_separate_close(self) -> None:
        _, wt = self.linked("retainfresh")
        Path(wt, "draft.txt").write_text("x", encoding="utf-8")
        UX.preview_payload(self.payload(wt, conv="fresh"))
        UX.dispatch_choice("fresh", "Retain")
        out = UX.complete_retain("fresh", [1])
        self.assertTrue(out["close_still_required"])
        self.assertFalse(out["fresh_preview"]["continue"])
        self.assertTrue(out["fresh_preview"]["user_message"].endswith(
            "None | No operator work will be deleted."))
        self.assertIsNotNone(UX._load_finish().read_challenge("fresh")[0])

    def test_deleted_ignored_and_conflicted_types_are_manifested(self) -> None:
        _, wt = self.linked("retaintypes")
        Path(wt, ".gitignore").write_text("ignored.local\n", encoding="utf-8")
        Path(wt, "deleted.txt").write_text("delete me\n", encoding="utf-8")
        Path(wt, "conflict.txt").write_text("base\n", encoding="utf-8")
        commit_all(wt, "base typed files")
        branch = git(wt, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        git(wt, "branch", "other")
        git(wt, "checkout", "-q", "other")
        Path(wt, "conflict.txt").write_text("other\n", encoding="utf-8")
        commit_all(wt, "other side")
        git(wt, "checkout", "-q", branch)
        Path(wt, "conflict.txt").write_text("current\n", encoding="utf-8")
        commit_all(wt, "current side")
        git(wt, "merge", "other", check=False)
        git(wt, "rm", "-q", "deleted.txt")
        Path(wt, "ignored.local").write_text("ignored\n", encoding="utf-8")
        UX.preview_payload(self.payload(wt, conv="typed"))
        UX.dispatch_choice("typed", "Retain")
        dialogue = UX.read_dialogue("typed")
        classes = {entry["class"] for entry in dialogue["visible"]}
        self.assertTrue({"staged", "conflicted", "ignored", "operation"} <= classes)
        result = UX.create_retain(
            "typed", list(range(1, len(dialogue["visible"]) + 1)))
        doc = UX._manifest(UX._artifact_path(result["artifact_id"]))
        self.assertEqual(
            doc["operation_state"]["operation_manifest"]["groups"], ["merge"])
        self.assertTrue(doc["operation_abort_proven"])
        self.assertTrue(
            (UX._artifact_path(result["artifact_id"]) / "git-state" / "objects.pack").is_file())
        retained_inventory = UX._load_finish().build_inventory(
            wt, dialogue["target"]["git_dir"])
        retained_operation = next(
            item for item in retained_inventory["entries"]
            if item["class"] == "operation")
        self.assertTrue(retained_operation["retained"])
        self.assertTrue(any(item["type"] == "absent" and
                            item["path"] == "deleted.txt" for item in doc["entries"]))
        deleted_status = next(
            item for item in doc["selected_status"]
            if os.fsencode("deleted.txt").hex() in item["paths_hex"])
        self.assertEqual(
            (deleted_status["code"], deleted_status["class"]), ("D ", "staged"))
        self.assertTrue(any(item["class"] == "conflicted"
                            for item in doc["selected_status"]))
        self.assertEqual(doc["ignore_intent"], ["ignored.local"])
        destination = self.data_home / "typed-restore"
        UX.restore_retain(result["artifact_id"], str(destination))
        fin = UX._load_finish()
        binding = fin.validated_git_binding(str(destination), allow_primary=True)
        raw_index = fin._read_index_stable(binding["index_file"])
        status = fin._run_git_bound(
            binding, "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
            "status", "--porcelain=v1", "-z", "--untracked-files=all",
            "--ignored=matching")
        index = fin._run_git_bound(
            binding, "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
            "ls-files", "--stage", "-z")
        restored_operation = fin._capture_operation_manifest(
            binding, status_bytes=status.stdout, index_listing=index.stdout,
            raw_index=raw_index)
        self.assertEqual(
            restored_operation, doc["operation_state"]["operation_manifest"])
        self.assertIn(
            "ignored.local",
            (destination / ".git" / "info" / "exclude").read_text(encoding="utf-8"))

    def test_retain_lock_contention_refuses_and_preserves_source(self) -> None:
        _, wt = self.linked("retainlock")
        source = Path(wt, "draft.txt")
        source.write_text("preserve", encoding="utf-8")
        UX.preview_payload(self.payload(wt, conv="retain-lock"))
        UX.dispatch_choice("retain-lock", "Retain")
        dialogue = UX.read_dialogue("retain-lock")
        fin = UX._load_finish()
        with fin.common_dir_lock(dialogue["target"]["common_dir"], timeout=1):
            with self.assertRaises(Exception) as raised:
                UX.create_retain("retain-lock", [1], lock_timeout=0.1)
        self.assertIn("lock busy", str(raised.exception))
        self.assertEqual(source.read_text(encoding="utf-8"), "preserve")
        self.assertEqual(UX.list_retained(), [])


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


class CommitDeliveryProofTest(Phase2Base):
    def good(self) -> dict:
        oid = "a" * 40
        return {
            "github_repositories": ["KleinPerkins/awa"],
            "preserved_head_oid": oid,
            "merged_prs": [{"number": 7, "state": "MERGED", "headRefOid": oid}],
            "compare": {"status": "ahead"},
            "checks": [{"state": "SUCCESS"}, {"state": "NEUTRAL"}, {"state": "SKIPPED"}],
            "checks_complete": True,
        }

    def test_strict_delivery_success_and_complete_zero_checks(self) -> None:
        self.assertTrue(UX.verify_delivery_evidence(**self.good())["ok"])
        empty = self.good()
        empty["checks"] = []
        empty["checks_observations"] = [[], []]
        empty["zero_check_stable"] = True
        self.assertTrue(UX.verify_delivery_evidence(**empty)["ok"])

    def test_delivery_failure_matrix(self) -> None:
        mutations = [
            ("github_repositories", ["a/x", "b/y"]),
            ("preserved_head_oid", "bad"),
            ("merged_prs", []),
            ("compare", {"status": "diverged"}),
            ("checks_complete", False),
            ("checks", [{"state": "PENDING"}]),
            ("checks", [{"state": "FAILURE"}]),
            ("checks", [{"state": "UNKNOWN"}]),
        ]
        for key, value in mutations:
            evidence = self.good()
            evidence[key] = value
            with self.subTest(key=key, value=value):
                self.assertFalse(UX.verify_delivery_evidence(**evidence)["ok"])

    def test_network_calls_structurally_commit_only(self) -> None:
        _, wt = self.linked("nonet2")
        Path(wt, "draft").write_text("x", encoding="utf-8")
        real_run = UX.subprocess.run

        def bomb(cmd, *args, **kwargs):
            if isinstance(cmd, list) and cmd and cmd[0] == "gh":
                raise AssertionError("network escaped Commit delivery adapter")
            return real_run(cmd, *args, **kwargs)

        UX.subprocess.run = bomb
        try:
            out = UX.preview_payload(self.payload(wt, conv="nonet-conv"))
            self.assertFalse(out["continue"])
            UX.dispatch_choice("nonet-conv", "Cancel")
        finally:
            UX.subprocess.run = real_run

    def test_missing_gh_or_network_fails_honestly(self) -> None:
        _, wt = self.linked("ghfail")

        def missing(*args, **kwargs):
            raise FileNotFoundError("gh")

        proof = UX.verify_delivery_network(wt, "cursor/worktree/ghfail", "a" * 40,
                                           runner=missing)
        self.assertFalse(proof["ok"])
        self.assertEqual(proof["reason"], "delivery_evidence_unavailable")

    def test_selected_commit_excludes_unselected_rows_and_requires_fresh_preview(self) -> None:
        _, wt = self.linked("selectcommit")
        git(wt, "config", "user.name", "AWA Test")
        git(wt, "config", "user.email", "awa-test@example.invalid")
        marker = self.data_home / "pre-commit-ran"
        hook = Path(git(wt, "rev-parse", "--git-path", "hooks/pre-commit").stdout.strip())
        hook.write_text(f"#!/bin/sh\nprintf ran > '{marker}'\n", encoding="utf-8")
        hook.chmod(0o755)
        Path(wt, "selected.txt").write_text("selected", encoding="utf-8")
        Path(wt, "unselected.txt").write_text("unselected", encoding="utf-8")
        UX.preview_payload(self.payload(wt, conv="select-commit"))
        UX.dispatch_choice("select-commit", "Commit")
        dialogue = UX.read_dialogue("select-commit")
        by_path = {entry["path"]: idx for idx, entry in enumerate(dialogue["visible"], 1)}
        original_delivery = UX.deliver_commit
        UX.deliver_commit = lambda root, branch, head_oid, **kwargs: {
            "ok": True, "proof": {"ok": True}, "head_oid": head_oid,
        }
        try:
            result = UX.complete_commit(
                "select-commit", [by_path["selected.txt"]], "deliver selected")
        finally:
            UX.deliver_commit = original_delivery
        self.assertTrue(result["ok"])
        names = git(wt, "show", "--format=", "--name-only", "HEAD").stdout.splitlines()
        self.assertEqual(names, ["selected.txt"])
        self.assertTrue(marker.exists(), "selected commit must run normal commit hooks")
        self.assertTrue(Path(wt, "unselected.txt").exists())
        status = git(wt, "status", "--porcelain").stdout
        self.assertIn("?? unselected.txt", status)
        self.assertTrue(result["close_still_required"])
        self.assertFalse(result["fresh_preview"]["continue"])

    def test_commit_delivery_failure_is_honest_and_preserves_local_commit(self) -> None:
        _, wt = self.linked("commitfail")
        git(wt, "config", "user.name", "AWA Test")
        git(wt, "config", "user.email", "awa-test@example.invalid")
        Path(wt, "draft.txt").write_text("x", encoding="utf-8")
        UX.preview_payload(self.payload(wt, conv="commit-fail"))
        UX.dispatch_choice("commit-fail", "Commit")
        original_delivery = UX.deliver_commit
        UX.deliver_commit = lambda root, branch, head_oid, **kwargs: {
            "ok": False, "reason": "network",
        }
        try:
            result = UX.complete_commit("commit-fail", [1], "local preserved")
        finally:
            UX.deliver_commit = original_delivery
        self.assertFalse(result["ok"])
        self.assertTrue(result["local_commit_preserved"])
        self.assertEqual(git(wt, "show", "--format=%s", "-s", "HEAD").stdout.strip(),
                         "local preserved")
        self.assertTrue(Path(wt).exists())


if __name__ == "__main__":
    import unittest
    unittest.main()
