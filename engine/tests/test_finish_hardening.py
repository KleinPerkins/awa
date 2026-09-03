"""Adversarial Phase-2 hardening for root/session-bound finish."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from consumer import finish_current as UX
from .finish_case_manifest import finish_cases
from .helpers import EngineTestCase, commit_all, git


REPO = Path(__file__).resolve().parents[2]
INSTALL_HOOKS = REPO / "kernel" / "hooks" / "install-hooks.sh"


class HardeningBase(EngineTestCase):
    def linked(self, name: str) -> tuple[str, str]:
        repo = self.make_seeded_repo(name)
        return repo, self.add_worktree(repo, f"cursor/worktree/{name}")

    def target(self, wt: str) -> dict:
        return UX.resolve_linked_root({"cwd": wt})

    def payload(self, wt: str, prompt: str, conv: str,
                *, attachments=None, event_id: str = "") -> dict:
        target = self.target(wt)
        roots = UX._load_finish()._roots_module()
        roots.write_current_session(
            wt, session_id=conv, conversation_id=conv,
            branch=target["branch"], common_dir=target["common_dir"])
        payload = {
            "hook_event_name": "beforeSubmitPrompt",
            "prompt": prompt,
            "conversation_id": conv,
            "session_id": conv,
            "cwd": wt,
            "workspace_roots": [wt],
        }
        if attachments is not None:
            payload["attachments"] = attachments
        if event_id:
            payload["event_id"] = event_id
        return payload

    def start(self, wt: str, conv: str) -> dict:
        payload = self.payload(wt, "please finish", conv)
        out = UX.handle_hook_payload(payload)
        self.assertFalse(out["continue"], out)
        self.assertTrue(UX.mark_hook_published(payload))
        return UX.read_dialogue(conv)

    def current(self, wt: str, *, executor=None) -> dict:
        old = os.getcwd()
        os.chdir(wt)
        try:
            return UX.dispatch_current(executor=executor)
        finally:
            os.chdir(old)

    @staticmethod
    def removed_outcome() -> dict:
        return {"outcome": "removed", "branch_action": "retained"}


class CurrentEnvelopeAdversarialTest(HardeningBase):
    def test_non_destructive_casing_matrix_through_hook_envelope_and_current(self) -> None:
        for number, case in enumerate(finish_cases(layer="physical")):
            choice = case.expected["canonical_choice"]
            submitted = case.input["answer"]
            with self.subTest(case_id=case.case_id):
                _, wt = self.linked(f"case-{choice.lower()}-{number}")
                draft = Path(wt, "draft")
                draft.write_text("x", encoding="utf-8")
                before = draft.read_bytes()
                conv = f"conv-{choice}-{number}"
                self.start(wt, conv)
                hook = UX.handle_hook_payload(self.payload(
                    wt, submitted, conv, event_id=f"event-{choice}-{number}"))
                self.assertTrue(hook["continue"])
                envelope_file = next(UX._envelope_dir().glob("envelope-*.json"))
                envelope = json.loads(envelope_file.read_text(encoding="utf-8"))
                self.assertEqual(envelope["exact_text"], submitted)
                self.assertEqual(envelope["canonical_choice"], choice)
                out = self.current(wt)
                self.assertTrue(out["ok"], out)
                self.assertEqual(out["state"], case.expected["state"])
                if choice == "Cancel":
                    self.assertEqual(draft.read_bytes(), before)
                    self.assertIsNone(UX.read_dialogue(conv))
                    self.assertEqual(
                        UX._load_finish().read_challenge(conv)[1], "absent")

    def test_exact_close_succeeds_through_current_path(self) -> None:
        _, wt = self.linked("exact-close")
        Path(wt, "draft").write_text("x", encoding="utf-8")
        conv = "conv-Close"
        self.start(wt, conv)
        UX.handle_hook_payload(self.payload(
            wt, "Close", conv, event_id="event-Close"))
        out = self.current(wt, executor=lambda **_: self.removed_outcome())
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["state"], "removed")

    def test_close_variants_correct_without_activation_or_mutation(self) -> None:
        _, wt = self.linked("close-correction")
        draft = Path(wt, "draft")
        draft.write_text("x", encoding="utf-8")
        before = draft.read_bytes()
        conv = "close-correction"
        self.start(wt, conv)
        calls = []

        for number, submitted in enumerate(("close", "CLOSE", "cLoSe", " Close ")):
            with self.subTest(submitted=submitted):
                hook = UX.handle_hook_payload(self.payload(
                    wt, submitted, conv, event_id=f"close-variant-{number}"))
                self.assertTrue(hook["continue"])
                out = self.current(
                    wt, executor=lambda **kwargs: (
                        calls.append(kwargs) or self.removed_outcome()))
                self.assertEqual(out, {
                    "ok": False,
                    "state": "awaiting_choice",
                    "reason": "close_must_be_exact",
                    "mutated_repo": False,
                    "user_message": UX.CLOSE_CORRECTION,
                })
                challenge, status = UX._load_finish().read_challenge(conv)
                self.assertEqual(status, "ok")
                self.assertFalse(challenge["hook_activated"])
                self.assertEqual(draft.read_bytes(), before)
                self.assertEqual(calls, [])

        UX.handle_hook_payload(self.payload(
            wt, "Close", conv, event_id="exact-close-after-corrections"))
        removed = self.current(
            wt, executor=lambda **kwargs: (
                calls.append(kwargs) or self.removed_outcome()))
        self.assertEqual(removed["state"], "removed")
        self.assertEqual(calls[0]["authorization"], "Close")

    def test_exact_five_choices_remain_canonical(self) -> None:
        for choice in UX.CHOICES:
            with self.subTest(choice=choice):
                _, wt = self.linked("canonical-" + choice.lower())
                Path(wt, "draft").write_text("x", encoding="utf-8")
                conv = "conv-" + choice
                self.start(wt, conv)
                UX.handle_hook_payload(self.payload(
                    wt, choice, conv, event_id="event-" + choice))
                executor = None
                if choice == "Close":
                    executor = lambda **_: self.removed_outcome()
                out = self.current(wt, executor=executor)
                self.assertTrue(out["ok"], out)
                expected = {
                    "Commit": "awaiting_commit_selection",
                    "Retain": "awaiting_retain_selection",
                    "Mixed": "awaiting_mixed_selection",
                    "Cancel": "cancelled",
                    "Close": "removed",
                }[choice]
                self.assertEqual(out["state"], expected)

    def test_attachment_provenance_refuses_every_choice(self) -> None:
        for choice in UX.CHOICES:
            with self.subTest(choice=choice):
                _, wt = self.linked("attach-" + choice.lower())
                Path(wt, "draft").write_text("x", encoding="utf-8")
                conv = "attached-" + choice
                self.start(wt, conv)
                UX.handle_hook_payload(self.payload(
                    wt, choice, conv, attachments=[{"name": "proof.png"}]))
                out = self.current(
                    wt, executor=lambda **_: self.removed_outcome())
                self.assertFalse(out["ok"], out)
                self.assertEqual(out["reason"], "attachments_present")
                self.assertTrue(Path(wt).exists())

    def test_envelope_replay_and_model_substitution_refuse(self) -> None:
        _, wt = self.linked("replay-envelope")
        Path(wt, "draft").write_text("x", encoding="utf-8")
        self.start(wt, "replay")
        UX.handle_hook_payload(self.payload(wt, "Commit", "replay", event_id="once"))
        contract = json.loads(
            (REPO / "contracts" / "awa-contract.v1.json").read_text(encoding="utf-8"))[
                "finish_conversation"]
        dialogue = UX.read_dialogue("replay")
        self.assertEqual(set(dialogue), set(contract["dialogue"]["declared_keys"]))
        index = json.loads(UX.index_path("replay").read_text(encoding="utf-8"))
        self.assertEqual(set(index), set(contract["current_index"]["declared_keys"]))
        envelope_file = next(UX._envelope_dir().glob("envelope-*.json"))
        envelope = json.loads(envelope_file.read_text(encoding="utf-8"))
        self.assertEqual(set(envelope), set(contract["choice_envelope"]["declared_keys"]))
        first = self.current(wt)
        self.assertEqual(first["state"], "awaiting_commit_selection")
        replay = UX.dispatch_choice("replay", "Close",
                                    executor=lambda **_: self.removed_outcome())
        self.assertFalse(replay["ok"])
        self.assertEqual(replay["reason"].split(":", 1)[0], "wrong_dialogue_state")
        self.assertTrue(Path(wt).exists())

        _, wt2 = self.linked("substitute-envelope")
        Path(wt2, "draft").write_text("x", encoding="utf-8")
        self.start(wt2, "substitute")
        UX.handle_hook_payload(self.payload(wt2, "cancel", "substitute"))
        substituted = UX.dispatch_choice(
            "substitute", "Close", executor=lambda **_: self.removed_outcome())
        self.assertEqual(substituted["state"], "cancelled")
        self.assertTrue(Path(wt2).exists(), "model-provided Close must be ignored")

    def test_additive_canonical_field_accepts_legacy_absence_and_rejects_tampering(self) -> None:
        _, wt = self.linked("legacy-envelope")
        Path(wt, "draft").write_text("x", encoding="utf-8")
        self.start(wt, "legacy-envelope")
        UX.handle_hook_payload(self.payload(wt, "commit", "legacy-envelope"))
        envelope_path = next(UX._envelope_dir().glob("envelope-*.json"))
        envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
        envelope.pop("canonical_choice")
        UX._json_write(envelope_path, envelope)
        self.assertEqual(
            self.current(wt)["state"], "awaiting_commit_selection")

        _, wt2 = self.linked("tampered-envelope")
        Path(wt2, "draft").write_text("x", encoding="utf-8")
        self.start(wt2, "tampered-envelope")
        UX.handle_hook_payload(self.payload(wt2, "cancel", "tampered-envelope"))
        tampered_path = next(UX._envelope_dir().glob("envelope-*.json"))
        tampered = json.loads(tampered_path.read_text(encoding="utf-8"))
        tampered["canonical_choice"] = "Close"
        UX._json_write(tampered_path, tampered)
        out = self.current(
            wt2, executor=lambda **_: self.removed_outcome())
        self.assertEqual(out["reason"], "choice_envelope_canonical_mismatch")
        challenge, status = UX._load_finish().read_challenge("tampered-envelope")
        self.assertEqual(status, "ok")
        self.assertFalse(challenge["hook_activated"])
        self.assertTrue(Path(wt2).exists())

    def test_zero_duplicate_and_stale_current_index_refuse(self) -> None:
        _, wt = self.linked("current-index")
        Path(wt, "draft").write_text("x", encoding="utf-8")
        dialogue = self.start(wt, "current-index")
        idx = UX.index_path("current-index")
        saved = idx.read_bytes()
        idx.unlink()
        self.assertEqual(self.current(wt)["reason"], "current_dialogue_absent")
        idx.write_bytes(saved)
        duplicate = idx.with_name("index-duplicate.json")
        duplicate.write_bytes(saved)
        self.assertEqual(self.current(wt)["reason"], "current_dialogue_ambiguous")
        duplicate.unlink()
        record = json.loads(idx.read_text(encoding="utf-8"))
        record["generation"] = dialogue["generation"] + 1
        idx.write_text(json.dumps(record), encoding="utf-8")
        self.assertEqual(self.current(wt)["reason"],
                         "current_dialogue_generation_mismatch")

    def test_stale_cleanup_cannot_delete_new_generation(self) -> None:
        _, wt = self.linked("cleanup-cas")
        Path(wt, "draft").write_text("x", encoding="utf-8")
        old = self.start(wt, "cleanup-cas")
        new = UX.preview_payload(
            self.payload(wt, "finish", "cleanup-cas"), hook_mode=True)
        self.assertTrue(new["ok"])
        current = UX.read_dialogue("cleanup-cas")
        self.assertGreater(current["generation"], old["generation"])
        self.assertFalse(UX.cleanup_pending(
            "cleanup-cas", generation=old["generation"], nonce=old["nonce"]))
        challenge, status = UX._load_finish().read_challenge("cleanup-cas")
        self.assertEqual(status, "ok")
        self.assertEqual(challenge["generation"], current["generation"])

    def test_cleanup_removes_all_exact_generation_envelopes_only(self) -> None:
        _, wt = self.linked("cleanup-envelopes")
        Path(wt, "draft").write_text("x", encoding="utf-8")
        dialogue = self.start(wt, "cleanup-envelopes")
        for event in ("first", "second"):
            self.assertTrue(UX._persist_choice_envelope(
                self.payload(wt, "Close", "cleanup-envelopes", event_id=event), "Close"))
        pattern = (f"envelope-{UX._conversation_key('cleanup-envelopes')}-"
                   f"{dialogue['generation']}-*.json")
        current = list(UX._envelope_dir().glob(pattern))
        self.assertEqual(len(current), 2)

        newer = json.loads(current[0].read_text(encoding="utf-8"))
        newer["generation"] = dialogue["generation"] + 1
        newer["nonce"] = "newer-generation-nonce"
        newer_path = UX.envelope_path(
            "cleanup-envelopes", newer["generation"], "newer-event")
        UX._json_write(newer_path, newer)

        self.assertTrue(UX.cleanup_pending(
            "cleanup-envelopes", generation=dialogue["generation"],
            nonce=dialogue["nonce"]))
        self.assertEqual(list(UX._envelope_dir().glob(pattern)), [])
        self.assertTrue(newer_path.exists(), "cleanup must remain generation-bounded")

    def test_cleanup_leaves_malformed_and_nonce_mismatched_envelopes(self) -> None:
        _, wt = self.linked("cleanup-malformed")
        Path(wt, "draft").write_text("x", encoding="utf-8")
        dialogue = self.start(wt, "cleanup-malformed")
        key = UX._conversation_key("cleanup-malformed")
        UX._private_dir(UX._envelope_dir())
        malformed = UX._envelope_dir() / (
            f"envelope-{key}-{dialogue['generation']}-malformed.json")
        malformed.write_text("{", encoding="utf-8")
        mismatched = UX._envelope_dir() / (
            f"envelope-{key}-{dialogue['generation']}-mismatch.json")
        UX._json_write(mismatched, {
            "schema": UX.CHOICE_ENVELOPE_SCHEMA,
            "root": dialogue["target"]["root"],
            "session_id": dialogue["session_id"],
            "conversation_id": dialogue["conversation_id"],
            "generation": dialogue["generation"],
            "nonce": "different-nonce",
            "exact_text": "Close",
            "attachments_present": False,
            "event_id": "mismatch",
            "created_at_epoch": 1,
        })

        self.assertTrue(UX.cleanup_pending(
            "cleanup-malformed", generation=dialogue["generation"],
            nonce=dialogue["nonce"]))
        self.assertTrue(malformed.exists(), "malformed state must fail safe")
        self.assertTrue(mismatched.exists(), "nonce-mismatched state must fail safe")

    def test_cancel_and_removed_terminal_flows_leave_no_envelopes(self) -> None:
        for choice in ("Cancel", "Close"):
            with self.subTest(choice=choice):
                conv = "terminal-" + choice.lower()
                _, wt = self.linked(conv)
                Path(wt, "draft").write_text("x", encoding="utf-8")
                dialogue = self.start(wt, conv)
                UX.handle_hook_payload(self.payload(
                    wt, choice, conv, event_id="terminal-event"))
                pattern = (f"envelope-{UX._conversation_key(conv)}-"
                           f"{dialogue['generation']}-*.json")
                self.assertEqual(len(list(UX._envelope_dir().glob(pattern))), 1)
                out = self.current(
                    wt, executor=(lambda **_: self.removed_outcome())
                    if choice == "Close" else None)
                self.assertTrue(out["ok"], out)
                self.assertEqual(list(UX._envelope_dir().glob(pattern)), [])

    def test_partial_hook_challenge_is_unconfirmable(self) -> None:
        _, wt = self.linked("inactive-hook")
        Path(wt, "draft").write_text("x", encoding="utf-8")
        dialogue = self.start(wt, "inactive")
        target = dialogue["target"]
        result = UX._load_finish().finish_execute(
            **target, session_id=dialogue["session_id"],
            conversation_id="inactive", answer="Close")
        self.assertEqual(result["reason"], "challenge_unactivated")
        self.assertTrue(Path(wt).exists())

    def test_fully_written_but_unpublished_hook_state_is_unconfirmable(self) -> None:
        _, wt = self.linked("unpublished-hook")
        Path(wt, "draft").write_text("x", encoding="utf-8")
        payload = self.payload(wt, "finish", "unpublished")
        UX.preview_payload(payload, hook_mode=True)
        UX.handle_hook_payload(self.payload(wt, "Close", "unpublished"))
        current = self.current(
            wt, executor=lambda **_: self.removed_outcome())
        self.assertFalse(current["ok"])
        self.assertEqual(current["reason"], "choice_envelope_absent")
        dialogue = UX.read_dialogue("unpublished")
        result = UX._load_finish().finish_execute(
            **dialogue["target"], session_id=dialogue["session_id"],
            conversation_id="unpublished", answer="Close")
        self.assertEqual(result["reason"], "challenge_unactivated")
        script = (REPO / "kernel" / "hooks" / "before-submit-prompt.sh").read_text(
            encoding="utf-8")
        self.assertLess(script.index("printf '%s\\n' \"$out\""),
                        script.index("hook-published"))

    def test_injected_exit_three_never_uses_child_stderr_as_removal_truth(self) -> None:
        for index, stderr in enumerate((
            "dev-worktree.sh: clean completed but its audit receipt could not be written "
            "(see WARNING above)\n",
            "unrelated failure",
        )):
            _, wt = self.linked("exit3-" + str(index))
            Path(wt, "draft").write_text("x", encoding="utf-8")
            UX.preview_payload(self.payload(wt, "finish", "exit3-" + str(index)))
            out = UX.dispatch_choice(
                "exit3-" + str(index), "Close",
                executor=lambda **_: {"returncode": 3, "stderr": stderr})
            self.assertIsNone(out.get("workspace_removed"))
            self.assertNotIn(stderr.strip(), json.dumps(out))
            self.assertTrue(out["agent_stopping"])


class StateMachineAdversarialTest(HardeningBase):
    def test_cancel_delete_failure_and_newer_generation_are_truthful(self) -> None:
        _, wt = self.linked("cancel-failure")
        source = Path(wt, "draft")
        source.write_text("keep", encoding="utf-8")
        target = self.target(wt)
        fin = UX._load_finish()
        first = fin.preview(
            **target, session_id="cancel-session", conversation_id="cancel-kernel")
        real_delete = fin._delete_challenge_raw_cas
        fin._delete_challenge_raw_cas = lambda *args, **kwargs: False
        try:
            failed = fin.cancel_challenge(
                conversation_id="cancel-kernel", common_dir=target["common_dir"],
                root=wt, session_id="cancel-session", nonce=first["nonce"],
                generation=first["generation"])
        finally:
            fin._delete_challenge_raw_cas = real_delete
        self.assertEqual(failed["reason"], "challenge_cleanup_failed")
        self.assertTrue(failed["inert"])
        self.assertEqual(fin.read_challenge("cancel-kernel")[1], "cancelled")
        self.assertEqual(source.read_text(encoding="utf-8"), "keep")

        newer = fin.preview(
            **target, session_id="cancel-session", conversation_id="cancel-kernel")
        stale = fin.cancel_challenge(
            conversation_id="cancel-kernel", common_dir=target["common_dir"],
            root=wt, session_id="cancel-session", nonce=first["nonce"],
            generation=first["generation"])
        self.assertEqual(stale["reason"], "cancelled_superseded")
        self.assertTrue(stale["inert"])
        current, status = fin.read_challenge("cancel-kernel")
        self.assertEqual(status, "ok")
        self.assertEqual(current["generation"], newer["generation"])
        self.assertEqual(source.read_text(encoding="utf-8"), "keep")

    def test_wrong_action_and_inventory_drift_refuse(self) -> None:
        _, wt = self.linked("wrong-action")
        Path(wt, "draft").write_text("x", encoding="utf-8")
        UX.preview_payload(self.payload(wt, "finish", "wrong-action"))
        UX.dispatch_choice("wrong-action", "Commit")
        with self.assertRaisesRegex(UX.FinishUXError, "wrong_dialogue_state"):
            UX.complete_retain("wrong-action", [1])

        _, wt2 = self.linked("selection-drift")
        Path(wt2, "draft").write_text("x", encoding="utf-8")
        UX.preview_payload(self.payload(wt2, "finish", "selection-drift"))
        UX.dispatch_choice("selection-drift", "Retain")
        Path(wt2, "new-after-row-number").write_text("drift", encoding="utf-8")
        with self.assertRaisesRegex(UX.FinishUXError, "live_inventory_drift"):
            UX.complete_retain("selection-drift", [1])

    def test_mixed_requires_exact_disjoint_complete_partition(self) -> None:
        cases = [
            ([1], [], "mixed_requires_both_dispositions"),
            ([1], [1], "duplicate_row"),
        ]
        for number, (commit_rows, retain_rows, reason) in enumerate(cases):
            _, wt = self.linked(f"mixed-invalid-{number}")
            Path(wt, "a").write_text("a", encoding="utf-8")
            Path(wt, "b").write_text("b", encoding="utf-8")
            conv = f"mixed-invalid-{number}"
            UX.preview_payload(self.payload(wt, "finish", conv))
            UX.dispatch_choice(conv, "Mixed")
            with self.assertRaisesRegex(UX.FinishUXError, reason):
                UX.complete_mixed(conv, commit_rows, retain_rows, "msg")


class OneUseGenerationAdversarialTest(HardeningBase):
    def _kernel_call(self, fin, dialogue, kwargs, **overrides):
        values = {
            **dialogue["target"],
            "session_id": dialogue["session_id"],
            "conversation_id": dialogue["conversation_id"],
            "answer": kwargs["authorization"],
            "expected_nonce": kwargs["expected_nonce"],
            "expected_generation": kwargs["expected_generation"],
        }
        values.update(overrides)
        return fin.finish_execute(**values)

    def _activated_attempt(self, name: str, executor):
        _, wt = self.linked(name)
        Path(wt, "draft").write_text("keep", encoding="utf-8")
        dialogue = self.start(wt, name)
        UX.handle_hook_payload(self.payload(
            wt, "Close", name, event_id=name + "-close"))
        result = self.current(wt, executor=executor(dialogue))
        return wt, dialogue, result

    def _assert_consumed_replay(self, fin, wt: str, dialogue: dict) -> None:
        replay = fin.finish_execute(
            **dialogue["target"], session_id=dialogue["session_id"],
            conversation_id=dialogue["conversation_id"], answer="Close",
            expected_nonce=dialogue["nonce"],
            expected_generation=dialogue["generation"])
        self.assertEqual(replay["reason"], "challenge_consumed", replay)
        self.assertTrue(Path(wt).exists())

    def test_close_claim_is_one_use_across_validation_and_remove_faults(self) -> None:
        cases = (
            "claim_sync", "literal", "target", "session", "fingerprint", "recheck", "remove",
        )
        for case in cases:
            with self.subTest(case=case):
                fin = UX._load_finish()

                def factory(dialogue, *, case=case, fin=fin):
                    def execute(**kwargs):
                        if case == "claim_sync":
                            # Fault the generation CLAIM's namespace sync (NOT an earlier durability
                            # re-sync during the challenge read). The one-use O_EXCL marker becomes
                            # visible and file-durable, but its parent-directory sync fails; the
                            # kernel must still treat the selected generation as permanently consumed.
                            dur = fin._durability_module()
                            real_cpe = dur.create_private_exclusive

                            def fail_claim_sync(path, data, **cpe_kwargs):
                                if os.path.basename(path).startswith("generation-"):
                                    fd = os.open(
                                        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                                    try:
                                        os.write(
                                            fd,
                                            data if isinstance(data, (bytes, bytearray))
                                            else str(data).encode("utf-8"))
                                        os.fsync(fd)
                                    finally:
                                        os.close(fd)
                                    raise OSError("injected generation-directory sync failure")
                                return real_cpe(path, data, **cpe_kwargs)

                            dur.create_private_exclusive = fail_claim_sync
                            try:
                                return self._kernel_call(fin, dialogue, kwargs)
                            finally:
                                dur.create_private_exclusive = real_cpe
                        if case == "literal":
                            return self._kernel_call(
                                fin, dialogue, kwargs, answer="close")
                        if case == "target":
                            return self._kernel_call(
                                fin, dialogue, kwargs, session_id="wrong-session")
                        if case == "session":
                            roots = fin._roots_module()
                            real_roots_module = fin._roots_module
                            real_gate = roots.finish_session_gate
                            roots.finish_session_gate = lambda *args, **call_kwargs: {
                                "blocked": True, "reason": "session_malformed",
                                "detail": "injected",
                            }
                            fin._roots_module = lambda: roots
                            try:
                                return self._kernel_call(fin, dialogue, kwargs)
                            finally:
                                roots.finish_session_gate = real_gate
                                fin._roots_module = real_roots_module
                        if case == "fingerprint":
                            Path(dialogue["target"]["root"], "late-file").write_text(
                                "drift", encoding="utf-8")
                            return self._kernel_call(fin, dialogue, kwargs)
                        if case == "recheck":
                            real = fin.final_recheck
                            fin.final_recheck = lambda *args: {
                                "ok": False, "reason": "injected"}
                            try:
                                return self._kernel_call(fin, dialogue, kwargs)
                            finally:
                                fin.final_recheck = real
                        real = fin.subprocess.run

                        def fail_remove(command, *args, **call_kwargs):
                            if (isinstance(command, (list, tuple))
                                    and "worktree" in command and "remove" in command):
                                return subprocess.CompletedProcess(
                                    command, 1, stdout="", stderr="injected remove failure")
                            return real(command, *args, **call_kwargs)

                        fin.subprocess.run = fail_remove
                        try:
                            return self._kernel_call(fin, dialogue, kwargs)
                        finally:
                            fin.subprocess.run = real
                    return execute

                wt, dialogue, result = self._activated_attempt(
                    "one-use-" + case, factory)
                self.assertFalse(result["ok"], result)
                self.assertTrue(result["fresh_preview_required"], result)
                self.assertEqual(
                    fin.generation_state_status(
                        dialogue["conversation_id"], dialogue["nonce"],
                        dialogue["generation"]),
                    "consumed")
                self._assert_consumed_replay(fin, wt, dialogue)
                fresh = UX.preview_payload(
                    self.payload(wt, "finish", dialogue["conversation_id"]),
                    hook_mode=True)
                self.assertTrue(fresh["ok"])
                replacement = UX.read_dialogue(dialogue["conversation_id"])
                self.assertGreater(replacement["generation"], dialogue["generation"])
                self.assertNotEqual(replacement["nonce"], dialogue["nonce"])

    def test_lock_contention_consumes_activated_close_before_lock_attempt(self) -> None:
        fin = UX._load_finish()

        def factory(dialogue):
            def execute(**kwargs):
                with fin.common_dir_lock(
                        dialogue["target"]["common_dir"], blocking=True, timeout=1.0):
                    return self._kernel_call(
                        fin, dialogue, kwargs, lock_timeout=0.05)
            return execute

        wt, dialogue, result = self._activated_attempt("one-use-lock", factory)
        self.assertFalse(result["ok"], result)
        self.assertEqual(result["outcome"]["reason"], "lock_busy")
        self._assert_consumed_replay(fin, wt, dialogue)

    def test_hook_generation_binding_rejects_replacement_without_consuming_new(self) -> None:
        _, wt = self.linked("replacement-generation")
        Path(wt, "draft").write_text("keep", encoding="utf-8")
        old = self.start(wt, "replacement-generation")
        UX.handle_hook_payload(self.payload(
            wt, "Close", "replacement-generation", event_id="old-close"))
        UX.preview_payload(
            self.payload(wt, "finish", "replacement-generation"), hook_mode=True)
        new = UX.read_dialogue("replacement-generation")
        self.assertNotEqual((new["nonce"], new["generation"]),
                            (old["nonce"], old["generation"]))
        fin = UX._load_finish()
        result = fin.finish_execute(
            **old["target"], session_id=old["session_id"],
            conversation_id=old["conversation_id"], answer="Close",
            expected_nonce=old["nonce"], expected_generation=old["generation"])
        self.assertEqual(result["reason"], "challenge_generation_mismatch", result)
        current, status = fin.read_challenge("replacement-generation")
        self.assertEqual(status, "ok")
        self.assertEqual((current["nonce"], current["generation"]),
                         (new["nonce"], new["generation"]))
        self.assertEqual(
            fin.generation_state_status(
                new["conversation_id"], new["nonce"], new["generation"]),
            "live")
        self.assertTrue(Path(wt).exists())

    def test_stale_hook_handoff_cannot_execute_replacement_direct_challenge(self) -> None:
        _, wt = self.linked("replacement-direct-generation")
        Path(wt, "draft").write_text("keep", encoding="utf-8")
        old = self.start(wt, "replacement-direct-generation")
        UX.handle_hook_payload(self.payload(
            wt, "Close", "replacement-direct-generation", event_id="old-direct-close"))
        UX.preview_payload(
            self.payload(wt, "finish", "replacement-direct-generation"),
            hook_mode=False)
        direct = UX.read_dialogue("replacement-direct-generation")
        fin = UX._load_finish()
        result = fin.finish_execute(
            **old["target"], session_id=old["session_id"],
            conversation_id=old["conversation_id"], answer="Close",
            expected_nonce=old["nonce"], expected_generation=old["generation"])
        self.assertEqual(result["reason"], "challenge_generation_mismatch", result)
        current, status = fin.read_challenge("replacement-direct-generation")
        self.assertEqual(status, "ok")
        self.assertFalse(current["hook_mode"])
        self.assertEqual(
            (current["nonce"], current["generation"]),
            (direct["nonce"], direct["generation"]))
        self.assertEqual(
            fin.generation_state_status(
                direct["conversation_id"], direct["nonce"], direct["generation"]),
            "live")
        self.assertEqual(
            fin.generation_state_status(
                old["conversation_id"], old["nonce"], old["generation"]),
            "consumed")
        self.assertTrue(Path(wt).exists())

    def test_any_partial_expected_binding_refuses_without_consuming_direct_challenge(self) -> None:
        _, wt = self.linked("partial-expected-binding")
        Path(wt, "draft").write_text("keep", encoding="utf-8")
        UX.preview_payload(self.payload(
            wt, "finish", "partial-expected-binding"), hook_mode=False)
        dialogue = UX.read_dialogue("partial-expected-binding")
        fin = UX._load_finish()
        for expected in (
                {"expected_nonce": dialogue["nonce"]},
                {"expected_generation": dialogue["generation"]}):
            with self.subTest(expected=expected):
                result = fin.finish_execute(
                    **dialogue["target"], session_id=dialogue["session_id"],
                    conversation_id=dialogue["conversation_id"], answer="Close",
                    **expected)
                self.assertEqual(result["reason"], "challenge_generation_required", result)
                current, status = fin.read_challenge(dialogue["conversation_id"])
                self.assertEqual(status, "ok")
                self.assertEqual(current["nonce"], dialogue["nonce"])


    def test_failed_heartbeat_never_attempts_current_session_bind(self) -> None:
        roots = SimpleNamespace()
        roots.heartbeat = lambda *args, **kwargs: {
            "ok": False, "reason": "heartbeat_target_root_absent"}
        roots.bind_current_session = mock.Mock(
            side_effect=AssertionError("bind must not run after failed heartbeat"))
        fin = SimpleNamespace(_roots_module=lambda: roots)
        target = {
            "root": "/gone", "branch": "feat/gone", "common_dir": "/repo/.git",
        }
        with mock.patch.object(UX, "_load_finish", return_value=fin):
            with self.assertRaisesRegex(UX.FinishUXError, "heartbeat_target_root_absent"):
                UX._bind_hook_current_session(target, "session", "conversation")
        roots.bind_current_session.assert_not_called()

    def test_failed_post_bind_validation_cas_preserves_superseding_record(self) -> None:
        _, wt = self.linked("binding-supersession")
        target = self.target(wt)
        payload = {
            "hook_event_name": "beforeSubmitPrompt",
            "prompt": "finish",
            "conversation_id": "binding-original",
            "session_id": "binding-original",
            "cwd": wt,
            "workspace_roots": [wt],
        }
        fin = UX._load_finish()
        roots = fin._roots_module()
        real_current = UX._current_session

        def supersede(root: str) -> dict:
            result = roots.bind_current_session(
                root, session_id="binding-new", conversation_id="binding-new",
                branch=target["branch"], common_dir=target["common_dir"],
                source="sessionStart")
            self.assertTrue(result["ok"], result)
            return real_current(root)

        with mock.patch.object(UX, "_current_session", side_effect=supersede):
            with self.assertRaisesRegex(
                    UX.FinishUXError, "current_session_identity_mismatch"):
                UX.preview_payload(payload, hook_mode=True)
        current, status = roots.read_current_session(wt)
        self.assertEqual(status, "ok")
        self.assertEqual(current["session_id"], "binding-new")
        self.assertEqual(current["conversation_id"], "binding-new")

    def test_later_preview_failure_cas_removes_only_just_created_binding(self) -> None:
        _, wt = self.linked("binding-preview-failure")
        payload = {
            "hook_event_name": "beforeSubmitPrompt",
            "prompt": "finish",
            "conversation_id": "binding-preview-failure",
            "session_id": "binding-preview-failure",
            "cwd": wt,
            "workspace_roots": [wt],
        }
        fin = UX._load_finish()
        roots = fin._roots_module()
        self.assertEqual(roots.read_current_session(wt)[1], "absent")
        with mock.patch.object(UX, "_load_finish", return_value=fin), \
                mock.patch.object(
                    fin, "preview",
                    return_value={"ok": False, "reason": "injected_preview_failure"}):
            with self.assertRaisesRegex(
                    UX.FinishUXError, "injected_preview_failure"):
                UX.preview_payload(payload, hook_mode=True)
        self.assertEqual(roots.read_current_session(wt)[1], "absent")

    def test_hook_close_without_expected_binding_is_consumed_and_refused(self) -> None:
        _, wt = self.linked("missing-generation-binding")
        Path(wt, "draft").write_text("keep", encoding="utf-8")
        dialogue = self.start(wt, "missing-generation-binding")
        UX.handle_hook_payload(self.payload(
            wt, "Close", "missing-generation-binding", event_id="close"))
        envelope, reason = UX._consume_choice_envelope(dialogue)
        self.assertEqual(reason, "ok")
        fin = UX._load_finish()
        self.assertTrue(UX._activate_envelope(
            fin, dialogue, envelope, "Close")[0])
        result = fin.finish_execute(
            **dialogue["target"], session_id=dialogue["session_id"],
            conversation_id=dialogue["conversation_id"], answer="Close")
        self.assertEqual(result["reason"], "challenge_generation_required", result)
        self._assert_consumed_replay(fin, wt, dialogue)

    def test_removed_outcome_surfaces_challenge_and_root_cleanup_faults(self) -> None:
        fin = UX._load_finish()
        roots = fin._roots_module()
        real_cleanup_challenge = fin._cleanup_challenge_locked
        real_remove_root_locked = roots._remove_root_locked

        def factory(dialogue):
            def execute(**kwargs):
                fin._cleanup_challenge_locked = (
                    lambda *args, **call_kwargs: (False, "challenge_cleanup_failed"))
                roots._remove_root_locked = lambda *args, **call_kwargs: {
                    "ok": False, "reason": "active_root_cleanup_failed", "removed": False,
                }
                try:
                    return self._kernel_call(fin, dialogue, kwargs)
                finally:
                    fin._cleanup_challenge_locked = real_cleanup_challenge
                    roots._remove_root_locked = real_remove_root_locked
            return execute

        wt, dialogue, result = self._activated_attempt(
            "removed-cleanup-warning", factory)
        self.assertTrue(result["workspace_removed"], result)
        self.assertTrue(result["state_cleanup_failed"], result)
        self.assertIn(
            "challenge_cleanup_failed", result["state_cleanup_warnings"])
        self.assertIn(
            "active_root_cleanup_failed", result["state_cleanup_warnings"])
        self.assertFalse(Path(wt).exists())
        self.assertEqual(
            fin.read_challenge(dialogue["conversation_id"])[1], "consumed")


class CancelTransactionAdversarialTest(HardeningBase):
    def _repo_snapshot(self, wt: str) -> tuple[bytes, bytes]:
        status = subprocess.run(
            ["git", "-C", wt, "status", "--porcelain=v1", "-z",
             "--untracked-files=all", "--ignored=matching"],
            capture_output=True, check=True).stdout
        return status, Path(wt, "draft").read_bytes()

    def _prepare(self, name: str) -> tuple[str, dict]:
        _, wt = self.linked(name)
        Path(wt, "draft").write_text("keep", encoding="utf-8")
        dialogue = self.start(wt, name)
        UX.handle_hook_payload(self.payload(
            wt, "Cancel", name, event_id=name + "-cancel"))
        return wt, dialogue

    def _assert_cancel_inert_and_preserved(
            self, wt: str, dialogue: dict, before: tuple[bytes, bytes]) -> None:
        fin = UX._load_finish()
        self.assertIn(
            fin.read_challenge(dialogue["conversation_id"])[1],
            {"absent", "cancelled"})
        self.assertIsNone(UX.read_dialogue(dialogue["conversation_id"]))
        current = self.current(wt)
        self.assertFalse(current["ok"])
        self.assertEqual(current["reason"], "current_dialogue_absent")
        self.assertEqual(self._repo_snapshot(wt), before)

    def test_normal_cancel_clears_all_projections(self) -> None:
        wt, dialogue = self._prepare("cancel-normal")
        before = self._repo_snapshot(wt)
        result = self.current(wt)
        self.assertEqual(
            result, {"ok": True, "state": "cancelled", "mutated_repo": False})
        self.assertFalse(UX.dialogue_path(dialogue["conversation_id"]).exists())
        self.assertFalse(UX.index_path(dialogue["conversation_id"]).exists())
        pattern = (f"envelope-{UX._conversation_key(dialogue['conversation_id'])}-"
                   f"{dialogue['generation']}-*.json")
        self.assertEqual(list(UX._envelope_dir().glob(pattern)), [])
        self.assertEqual(
            UX._load_finish()._read_challenge_raw(
                dialogue["conversation_id"])[1],
            "absent")
        self.assertEqual(self._repo_snapshot(wt), before)

    def test_cancel_faults_never_leave_live_authority_or_report_success(self) -> None:
        for boundary in ("challenge", "current_index", "dialogue", "choice_envelope"):
            with self.subTest(boundary=boundary):
                wt, dialogue = self._prepare("cancel-fault-" + boundary)
                before = self._repo_snapshot(wt)
                real_unlink = os.unlink
                real_clear = UX._clear_projection
                real_cleanup = UX._cleanup_terminal_projections
                injected_envelope = None

                if boundary == "challenge":
                    challenge_path = os.path.realpath(
                        UX._load_finish().challenge_path(dialogue["conversation_id"]))

                    # Durable challenge deletion goes through durable_unlink -> os.unlink (NOT
                    # os.remove), so the fault must be injected on os.unlink for the exact challenge.
                    def fail_challenge(path, *unlink_args, **unlink_kwargs):
                        if os.path.realpath(path) == challenge_path:
                            raise PermissionError("injected challenge unlink failure")
                        return real_unlink(path, *unlink_args, **unlink_kwargs)
                    os.unlink = fail_challenge
                elif boundary in {"current_index", "dialogue"}:
                    target_path = (
                        UX.index_path(dialogue["conversation_id"])
                        if boundary == "current_index"
                        else UX.dialogue_path(dialogue["conversation_id"]))

                    def fail_projection(path, **kwargs):
                        if path == target_path:
                            return False, "injected"
                        return real_clear(path, **kwargs)
                    UX._clear_projection = fail_projection
                else:
                    key = UX._conversation_key(dialogue["conversation_id"])
                    source = next(UX._envelope_dir().glob(
                        f"envelope-{key}-{dialogue['generation']}-*.json"))
                    envelope = json.loads(source.read_text(encoding="utf-8"))
                    envelope["event_id"] = "injected-cleanup-fault"
                    injected_envelope = UX._envelope_dir() / (
                        f"envelope-{key}-{dialogue['generation']}-"
                        "injected-cleanup-fault.json")

                    def fail_projection(path, **kwargs):
                        if kwargs.get("schema") == UX.CHOICE_ENVELOPE_SCHEMA:
                            return False, "injected"
                        return real_clear(path, **kwargs)

                    def inject_envelope_cleanup(selected, **kwargs):
                        UX._json_write(injected_envelope, envelope)
                        return real_cleanup(selected, **kwargs)

                    UX._clear_projection = fail_projection
                    UX._cleanup_terminal_projections = inject_envelope_cleanup
                try:
                    result = self.current(wt)
                finally:
                    os.unlink = real_unlink
                    UX._clear_projection = real_clear
                    UX._cleanup_terminal_projections = real_cleanup
                self.assertFalse(result["ok"], result)
                self.assertEqual(result["state"], "cancelled_cleanup_incomplete")
                self.assertTrue(result["authority_inert"])
                self.assertTrue(result["cleanup_warnings"])
                self._assert_cancel_inert_and_preserved(wt, dialogue, before)
                if injected_envelope is not None:
                    injected_envelope.unlink()

    def test_cancel_succeeds_despite_live_inventory_drift(self) -> None:
        # LIVE Phase-2 defect (Desktop UAT): the agent edits the tree between the warning and the
        # answer, so the re-derived fingerprint no longer byte-equals the challenge. Cancel is
        # UNCONDITIONAL -- it must still atomically discard the pending challenge and make zero
        # repo/Git/archive/worktree change. BITES: pre-fix the shared live-drift gate ran before the
        # Cancel branch, so this returned {refused, live_inventory_drift} with every projection left
        # live and the challenge unconsumed.
        wt, dialogue = self._prepare("cancel-drift")
        conv = dialogue["conversation_id"]
        Path(wt, "drift-after-warning.txt").write_text(
            "agent edit between warning and answer", encoding="utf-8")
        before = self._repo_snapshot(wt)
        result = self.current(wt)
        self.assertEqual(
            result, {"ok": True, "state": "cancelled", "mutated_repo": False})
        # All four persisted projections are cleared: dialogue, current-index, choice-envelope, and
        # the kernel challenge.
        self.assertFalse(UX.dialogue_path(conv).exists())
        self.assertFalse(UX.index_path(conv).exists())
        pattern = (f"envelope-{UX._conversation_key(conv)}-"
                   f"{dialogue['generation']}-*.json")
        self.assertEqual(list(UX._envelope_dir().glob(pattern)), [])
        self.assertEqual(
            UX._load_finish()._read_challenge_raw(conv)[1], "absent")
        # Zero repo/Git/worktree mutation: the agent's drift edit is preserved byte-for-byte.
        self.assertEqual(self._repo_snapshot(wt), before)
        self.assertTrue(Path(wt, "drift-after-warning.txt").exists())

    def test_cancel_direct_nonhook_dispatch_ignores_live_inventory_drift(self) -> None:
        # The same unconditional guarantee on the direct (non-hook) dispatch_choice entry point.
        _, wt = self.linked("cancel-drift-direct")
        Path(wt, "draft").write_text("keep", encoding="utf-8")
        UX.preview_payload(self.payload(wt, "finish", "cancel-drift-direct"))
        Path(wt, "drift-after-warning.txt").write_text("agent edit", encoding="utf-8")
        result = UX.dispatch_choice("cancel-drift-direct", "Cancel")
        self.assertEqual(
            result, {"ok": True, "state": "cancelled", "mutated_repo": False})
        self.assertIsNone(UX.read_dialogue("cancel-drift-direct"))
        self.assertEqual(
            UX._load_finish().read_challenge("cancel-drift-direct")[1], "absent")

    def test_close_still_refuses_under_live_inventory_drift(self) -> None:
        # Companion guard proving the Cancel fix did NOT broaden drift tolerance: under identical
        # drift an exact Close must still refuse with live_inventory_drift, preserve the workspace
        # and its authorization, and never reach the kernel executor.
        _, wt = self.linked("close-drift")
        Path(wt, "draft").write_text("keep", encoding="utf-8")
        dialogue = self.start(wt, "close-drift")
        conv = dialogue["conversation_id"]
        UX.handle_hook_payload(self.payload(
            wt, "Close", "close-drift", event_id="close-drift-close"))
        Path(wt, "drift-after-warning.txt").write_text("agent edit", encoding="utf-8")
        calls = []

        def executor(**kwargs):
            calls.append(kwargs)
            return self.removed_outcome()

        result = self.current(wt, executor=executor)
        self.assertFalse(result["ok"], result)
        self.assertEqual(result["state"], "refused")
        self.assertEqual(result["reason"], "live_inventory_drift")
        self.assertFalse(result["workspace_removed"])
        self.assertEqual(calls, [], "Close must never reach the kernel executor under drift")
        self.assertTrue(Path(wt).exists())
        self.assertEqual(UX._load_finish().read_challenge(conv)[1], "ok")
        self.assertIsNotNone(UX.read_dialogue(conv))


class PersistedStateContractTest(HardeningBase):
    def test_dialogue_transitions_never_add_undeclared_fields(self) -> None:
        contract = json.loads(
            (REPO / "contracts" / "awa-contract.v1.json").read_text(encoding="utf-8"))
        declared = set(contract["finish_conversation"]["dialogue"]["declared_keys"])
        for choice in ("Commit", "Retain", "Mixed"):
            with self.subTest(choice=choice):
                _, wt = self.linked("state-keys-" + choice.lower())
                Path(wt, "draft").write_text("x", encoding="utf-8")
                conv = "state-keys-" + choice.lower()
                UX.preview_payload(self.payload(wt, "finish", conv))
                UX.dispatch_choice(conv, choice)
                persisted = json.loads(
                    UX.dialogue_path(conv).read_text(encoding="utf-8"))
                self.assertEqual(set(persisted), declared)
                self.assertNotIn("choice", persisted)
                self.assertNotIn("transitioned_at_epoch", persisted)


class RetainSnapshotAdversarialTest(HardeningBase):
    def _artifact(self, wt: str, conv: str) -> tuple[dict, object]:
        UX.preview_payload(self.payload(wt, "finish", conv))
        UX.dispatch_choice(conv, "Retain")
        dialogue = UX.read_dialogue(conv)
        result = UX.create_retain(
            conv, list(range(1, len(dialogue["visible"]) + 1)))
        return UX._manifest(UX._artifact_path(result["artifact_id"])), UX._load_finish()

    def test_exact_snapshot_suppresses_then_descendant_mode_link_drift_reappears(self) -> None:
        _, wt = self.linked("retain-snapshot")
        Path(wt, ".gitignore").write_text("cache/\n", encoding="utf-8")
        commit_all(wt, "ignore cache")
        cache = Path(wt, "cache")
        cache.mkdir()
        item = cache / "item"
        item.write_text("x", encoding="utf-8")
        manifest, fin = self._artifact(wt, "snapshot")
        self.assertEqual(manifest["selected_snapshot"]["schema"],
                         fin.SCHEMA_SELECTED_SNAPSHOT)
        contract = json.loads(
            (REPO / "contracts" / "awa-contract.v1.json").read_text(encoding="utf-8"))
        declared = set(contract["finish_conversation"]["protected_retain"][
            "manifest_declared_keys"])
        self.assertEqual(set(manifest), declared)
        inventory = fin.build_inventory(wt, self.target(wt)["git_dir"])
        self.assertTrue(inventory["entries"][0]["retained"])

        (cache / "extra").write_text("new", encoding="utf-8")
        inventory = fin.build_inventory(wt, self.target(wt)["git_dir"])
        self.assertFalse(inventory["entries"][0]["retained"])
        (cache / "extra").unlink()
        item.unlink()
        self.assertFalse(fin.build_inventory(
            wt, self.target(wt)["git_dir"])["entries"][0]["retained"])
        item.write_text("x", encoding="utf-8")
        item.chmod(0o755)
        self.assertFalse(fin.build_inventory(
            wt, self.target(wt)["git_dir"])["entries"][0]["retained"])
        item.chmod(0o644)
        item.unlink()
        os.symlink("different", item)
        self.assertFalse(fin.build_inventory(
            wt, self.target(wt)["git_dir"])["entries"][0]["retained"])

    def test_same_status_index_change_and_status_error_never_suppress(self) -> None:
        _, wt = self.linked("retain-index")
        tracked = Path(wt, "tracked")
        tracked.write_text("base", encoding="utf-8")
        commit_all(wt, "base")
        tracked.write_text("first", encoding="utf-8")
        git(wt, "add", "tracked")
        manifest, fin = self._artifact(wt, "index-change")
        self.assertTrue(fin.build_inventory(
            wt, self.target(wt)["git_dir"])["entries"][0]["retained"])
        original_status = git(
            wt, "status", "--porcelain=v1", "-z", "--", "tracked").stdout
        tracked.write_text("second", encoding="utf-8")
        git(wt, "add", "tracked")
        changed_status = git(
            wt, "status", "--porcelain=v1", "-z", "--", "tracked").stdout
        self.assertEqual(original_status, changed_status,
                         "precondition: status bytes stay identical while index OID changes")
        self.assertFalse(fin.build_inventory(
            wt, self.target(wt)["git_dir"])["entries"][0]["retained"])

        real_git_bytes = fin._git_bytes
        fin._git_bytes = lambda *args: subprocess.CompletedProcess(
            args, 1, stdout=b"", stderr=b"status unavailable")
        try:
            self.assertEqual(fin._retained_signatures(wt), set())
        finally:
            fin._git_bytes = real_git_bytes

    def test_malformed_snapshot_and_status_failure_never_suppress(self) -> None:
        _, wt = self.linked("retain-malformed")
        Path(wt, "draft").write_text("x", encoding="utf-8")
        manifest, fin = self._artifact(wt, "malformed")
        artifact = UX._artifact_path(manifest["artifact_id"])
        manifest["selected_snapshot"] = {"schema": "bad"}
        (artifact / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.assertFalse(fin.build_inventory(
            wt, self.target(wt)["git_dir"])["entries"][0]["retained"])


class DeliveryAndInstallAdversarialTest(HardeningBase):
    def test_delivery_pending_failed_and_unstable_empty_refuse(self) -> None:
        base = {
            "github_repositories": ["o/r"],
            "preserved_head_oid": "a" * 40,
            "merged_prs": [{"number": 1, "state": "MERGED", "headRefOid": "a" * 40}],
            "compare": {"status": "ahead"},
        }
        for checks in ([{"state": "PENDING"}], [{"state": "FAILURE"}], []):
            with self.subTest(checks=checks):
                self.assertFalse(UX.verify_delivery_evidence(
                    **base, checks=checks, checks_observations=[[]],
                    zero_check_stable=False)["ok"])
        self.assertTrue(UX.verify_delivery_evidence(
            **base, checks=[], checks_observations=[[], []],
            zero_check_stable=True)["ok"])
        self.assertEqual(UX.verify_delivery_evidence(
            **base, checks=[{"state": "SUCCESS"}],
            merge_commit_enabled=False)["reason"],
            "merge_commit_required_unsupported")

    def test_hook_installer_refuses_malformed_and_preserves_basename_collision(self) -> None:
        hooks = self.data_home / "hooks.json"
        hooks.write_text("{ malformed", encoding="utf-8")
        before = hooks.read_bytes()
        env = {**os.environ, "AWA_HOOKS_JSON": str(hooks)}
        bad = subprocess.run(["bash", str(INSTALL_HOOKS)], env=env,
                             capture_output=True, text=True)
        self.assertNotEqual(bad.returncode, 0)
        self.assertEqual(hooks.read_bytes(), before)

        third_party = self.data_home / "third-party" / "worktree-guard.sh"
        third_party.parent.mkdir()
        third_party.write_text("#!/bin/sh\n", encoding="utf-8")
        hooks.write_text(json.dumps({
            "version": 1,
            "hooks": {"beforeShellExecution": [{
                "command": str(third_party), "type": "command", "timeout": 9,
            }]},
        }), encoding="utf-8")
        ok = subprocess.run(["bash", str(INSTALL_HOOKS)], env=env,
                            capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        entries = json.loads(hooks.read_text(encoding="utf-8"))[
            "hooks"]["beforeShellExecution"]
        self.assertTrue(any(entry["command"] == str(third_party) for entry in entries))
        self.assertEqual(len(entries), 2)

    def test_hook_check_catches_missing_and_exact_field_drift(self) -> None:
        hooks = self.data_home / "missing-hooks.json"
        env = {**os.environ, "AWA_HOOKS_JSON": str(hooks)}
        missing = subprocess.run(["bash", str(INSTALL_HOOKS), "--check"], env=env,
                                 capture_output=True, text=True)
        self.assertNotEqual(missing.returncode, 0)
        subprocess.run(["bash", str(INSTALL_HOOKS)], env=env, check=True,
                       capture_output=True, text=True)
        doc = json.loads(hooks.read_text(encoding="utf-8"))
        doc["hooks"]["beforeSubmitPrompt"][0]["timeout"] = 19
        hooks.write_text(json.dumps(doc), encoding="utf-8")
        drift = subprocess.run(["bash", str(INSTALL_HOOKS), "--check"], env=env,
                               capture_output=True, text=True)
        self.assertNotEqual(drift.returncode, 0)


if __name__ == "__main__":
    import unittest
    unittest.main()
