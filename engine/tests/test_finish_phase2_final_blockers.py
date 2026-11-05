"""Biting regressions for the independently confirmed final Phase-2 blockers."""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
from unittest import mock

from consumer import finish_current as UX
from .helpers import git
from .test_finish_final_hardening import FinalHardeningBase, FIN


class ActionCompletionLatchTest(FinalHardeningBase):
    HOSTILE = "/private/action-refresh/SHOULD-NOT-ESCAPE"

    def _start(self, name: str, files: tuple[str, ...], choice: str) -> tuple[str, dict]:
        _repo, wt = self.linked(name)
        for rel in files:
            Path(wt, rel).write_text(rel + "\n", encoding="utf-8")
        UX.preview_payload(self.payload(wt, name))
        UX.dispatch_choice(name, choice)
        return wt, UX.read_dialogue(name)

    def test_retain_latches_before_refresh_and_retry_never_duplicates_artifact(self) -> None:
        _wt, dialogue = self._start("action-retain-latch", ("draft.txt",), "Retain")
        indices = list(range(1, len(dialogue["visible"]) + 1))
        with mock.patch.object(
                UX, "preview_payload", side_effect=RuntimeError(self.HOSTILE)):
            first = UX.complete_retain("action-retain-latch", indices)
            second = UX.complete_retain("action-retain-latch", indices)
        self.assertTrue(first["ok"])
        self.assertTrue(first["action_complete"])
        self.assertFalse(first["refresh_ok"])
        self.assertTrue(first["fresh_preview_required"])
        self.assertTrue(first["close_still_required"])
        self.assertNotIn(self.HOSTILE, json.dumps(first, sort_keys=True))
        self.assertNotIn(self.HOSTILE, json.dumps(second, sort_keys=True))
        self.assertEqual(len(UX.list_retained()), 1)
        latched = UX.read_dialogue("action-retain-latch")
        self.assertEqual(latched["state"], "action_complete_refresh_pending")
        self.assertEqual(latched["action_kind"], "Retain")
        self.assertTrue(latched["action_retain_complete"])

        refreshed = UX.complete_retain("action-retain-latch", indices)
        self.assertTrue(refreshed["refresh_ok"])
        self.assertFalse(refreshed["fresh_preview_required"])
        self.assertEqual(UX.read_dialogue("action-retain-latch")["state"], "awaiting_choice")
        self.assertEqual(len(UX.list_retained()), 1)

    def test_commit_latches_delivered_head_and_retry_never_recommits(self) -> None:
        wt, dialogue = self._start("action-commit-latch", ("commit.txt",), "Commit")
        indices = list(range(1, len(dialogue["visible"]) + 1))
        delivered = mock.Mock(return_value={"ok": True, "proof": {"checks": 0}})
        with mock.patch.object(UX, "deliver_commit", delivered), \
                mock.patch.object(
                    UX, "preview_payload", side_effect=RuntimeError(self.HOSTILE)):
            first = UX.complete_commit(
                "action-commit-latch", indices, "deliver selected work")
            committed_head = git(wt, "rev-parse", "HEAD").stdout.strip()
            second = UX.complete_commit(
                "action-commit-latch", indices, "must not run twice")
        self.assertEqual(delivered.call_count, 1)
        self.assertEqual(git(wt, "rev-parse", "HEAD").stdout.strip(), committed_head)
        for result in (first, second):
            self.assertTrue(result["action_complete"])
            self.assertFalse(result["refresh_ok"])
            self.assertNotIn(self.HOSTILE, json.dumps(result, sort_keys=True))
        latched = UX.read_dialogue("action-commit-latch")
        self.assertEqual(latched["state"], "action_complete_refresh_pending")
        self.assertTrue(latched["action_commit_complete"])

    def test_mixed_is_complete_when_both_actions_finish_even_if_refresh_fails(self) -> None:
        wt, dialogue = self._start(
            "action-mixed-latch", ("commit.txt", "retain.txt"), "Mixed")
        by_path = {
            row["path"]: index
            for index, row in enumerate(dialogue["visible"], 1)
        }
        delivered = mock.Mock(return_value={"ok": True, "proof": {"checks": 0}})
        with mock.patch.object(UX, "deliver_commit", delivered), \
                mock.patch.object(
                    UX, "preview_payload", side_effect=RuntimeError(self.HOSTILE)):
            first = UX.complete_mixed(
                "action-mixed-latch", [by_path["commit.txt"]],
                [by_path["retain.txt"]], "deliver mixed work")
            head = git(wt, "rev-parse", "HEAD").stdout.strip()
            second = UX.complete_mixed(
                "action-mixed-latch", [by_path["commit.txt"]],
                [by_path["retain.txt"]], "must not run twice")
        self.assertTrue(first["ok"])
        self.assertTrue(first["action_complete"])
        self.assertFalse(first["refresh_ok"])
        self.assertNotIn("partial", first)
        self.assertNotIn(self.HOSTILE, json.dumps(first, sort_keys=True))
        self.assertTrue(second["action_complete"])
        self.assertEqual(delivered.call_count, 1)
        self.assertEqual(git(wt, "rev-parse", "HEAD").stdout.strip(), head)
        self.assertEqual(len(UX.list_retained()), 1)
        latched = UX.read_dialogue("action-mixed-latch")
        self.assertTrue(latched["action_commit_complete"])
        self.assertTrue(latched["action_retain_complete"])

    def test_cli_refresh_failure_is_closed_success_and_retry_is_idempotent(self) -> None:
        _wt, dialogue = self._start("action-cli-latch", ("cli.txt",), "Retain")
        rows = ",".join(str(index) for index in range(1, len(dialogue["visible"]) + 1))
        outputs = []
        with mock.patch.object(
                UX, "preview_payload", side_effect=RuntimeError(self.HOSTILE)):
            for _ in range(2):
                stdout, stderr = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    rc = UX.main([
                        "retain", "--conversation-id", "action-cli-latch",
                        "--rows", rows,
                    ])
                self.assertEqual(rc, 0)
                self.assertEqual(stderr.getvalue(), "")
                outputs.append(json.loads(stdout.getvalue()))
        self.assertEqual(len(UX.list_retained()), 1)
        for result in outputs:
            self.assertTrue(result["action_complete"])
            self.assertFalse(result["refresh_ok"])
            self.assertNotIn(self.HOSTILE, json.dumps(result, sort_keys=True))


class HookOwnedActionRefreshTest(FinalHardeningBase):
    def _retained_hook_action(self, name: str) -> tuple[str, dict, dict]:
        _repo, wt = self.linked(name)
        Path(wt, "draft.txt").write_text("preserve\n", encoding="utf-8")
        payload = self.payload(wt, name)
        preview = UX.handle_hook_payload(payload)
        self.assertFalse(preview["continue"])
        self.assertTrue(UX.mark_hook_published(payload))
        UX.handle_hook_payload({
            **payload, "prompt": "Retain", "event_id": name + "-retain",
        })
        selection = UX.dispatch_choice(name)
        self.assertEqual(selection["state"], "awaiting_retain_selection")
        dialogue = UX.read_dialogue(name)
        rows = list(range(1, len(dialogue["visible"]) + 1))
        completed = UX.complete_retain(name, rows)
        self.assertTrue(completed["action_complete"])
        self.assertFalse(completed["refresh_ok"])
        self.assertNotIn("fresh_preview", completed)
        latched = UX.read_dialogue(name)
        self.assertEqual(latched["state"], "action_complete_refresh_pending")
        return wt, payload, latched

    def test_exact_close_trigger_only_publishes_then_second_close_invokes_once(self) -> None:
        wt, payload, old = self._retained_hook_action("hook-owned-close")
        first_close = {
            **payload, "prompt": "Close", "event_id": "first-close-publishes",
        }
        warning = UX.handle_hook_payload(first_close)
        self.assertFalse(warning["continue"])
        self.assertEqual(warning["user_message"], UX.render_warning(
            UX.read_dialogue("hook-owned-close")["rows"]))
        refreshed = UX.read_dialogue("hook-owned-close")
        self.assertGreater(refreshed["generation"], old["generation"])
        self.assertEqual(refreshed["state"], "action_complete_refresh_pending")
        self.assertEqual(
            list(UX._envelope_dir().glob(
                f"envelope-{UX._conversation_key('hook-owned-close')}-*.json")),
            [])
        self.assertTrue(UX.mark_hook_published(first_close))
        self.assertEqual(
            UX.read_dialogue("hook-owned-close")["state"], "awaiting_choice")

        second_close = UX.handle_hook_payload({
            **payload, "prompt": "Close", "event_id": "second-close-acts",
        })
        self.assertTrue(second_close["continue"])
        executor = mock.Mock(return_value={
            "outcome": "removed", "reason": "finish_removed",
            "branch_action": "retained",
        })
        removed = UX.dispatch_choice("hook-owned-close", executor=executor)
        self.assertTrue(removed["workspace_removed"])
        executor.assert_called_once()
        self.assertTrue(Path(wt).exists(), "unit executor must not remove the test root")
        self.assertEqual(len(UX.list_retained()), 1)

    def test_faults_around_output_and_publication_never_repeat_action(self) -> None:
        _wt, payload, old = self._retained_hook_action("hook-owned-faults")
        with mock.patch.object(
                UX, "preview_payload", side_effect=RuntimeError("before output")):
            failed = UX.handle_hook_payload({
                **payload, "prompt": "Close", "event_id": "fault-before-output",
            })
        self.assertTrue(failed["continue"])
        self.assertEqual(
            UX.read_dialogue("hook-owned-faults")["generation"], old["generation"])

        emitted = UX.handle_hook_payload({
            **payload, "prompt": "Close", "event_id": "fault-after-output",
        })
        self.assertFalse(emitted["continue"])
        after_output = UX.read_dialogue("hook-owned-faults")
        self.assertEqual(after_output["state"], "action_complete_refresh_pending")
        # Simulate process death after complete stdout and before hook-published.
        retried = UX.handle_hook_payload({
            **payload, "prompt": "anything", "event_id": "retry-after-output",
        })
        self.assertFalse(retried["continue"])
        before_publication = UX.read_dialogue("hook-owned-faults")
        self.assertGreater(before_publication["generation"], after_output["generation"])

        fin = UX._load_finish()
        with mock.patch.object(UX, "_load_finish", return_value=fin), \
                mock.patch.object(
                fin, "publish_hook_challenge", side_effect=OSError("before publication")):
            self.assertFalse(UX.mark_hook_published(payload))
        self.assertEqual(
            UX.read_dialogue("hook-owned-faults")["state"],
            "action_complete_refresh_pending")
        final_retry = UX.handle_hook_payload({
            **payload, "prompt": "Close", "event_id": "retry-before-publication",
        })
        self.assertFalse(final_retry["continue"])
        self.assertEqual(len(UX.list_retained()), 1)
        self.assertEqual(list(UX._envelope_dir().glob("envelope-*.json")), [])

    def test_publication_ticket_cannot_publish_a_replacement_generation(self) -> None:
        contract = json.loads(
            (Path(__file__).resolve().parents[2] / "contracts" /
             "awa-contract.v1.json").read_text(encoding="utf-8"))
        declared = contract["finish_conversation"]["hook"]["publication_ticket"]
        self.assertEqual(declared["schema"], UX.HOOK_PUBLICATION_TICKET_SCHEMA)
        self.assertEqual(
            set(declared["declared_keys"]), set(UX.HOOK_PUBLICATION_TICKET_KEYS))
        hook_script = (
            Path(__file__).resolve().parents[2] / "kernel" / "hooks" /
            "before-submit-prompt.sh").read_text(encoding="utf-8")
        self.assertLess(
            hook_script.index("if ! printf '%s\\n' \"$out\""),
            hook_script.index("hook-published"))
        _repo, wt = self.linked("hook-ticket-generation")
        Path(wt, "draft.txt").write_text("keep\n", encoding="utf-8")
        payload = self.payload(wt, "hook-ticket-generation")
        invocation = "a" * 32
        with mock.patch.dict(
                os.environ, {UX.HOOK_PUBLICATION_INVOCATION_ENV: invocation}):
            emitted = UX.handle_hook_payload(payload)
        self.assertFalse(emitted["continue"])
        old = UX.read_dialogue("hook-ticket-generation")
        UX.preview_payload(payload, hook_mode=True)
        replacement = UX.read_dialogue("hook-ticket-generation")
        self.assertGreater(replacement["generation"], old["generation"])
        with mock.patch.dict(
                os.environ, {UX.HOOK_PUBLICATION_INVOCATION_ENV: invocation}):
            self.assertFalse(UX.mark_hook_published(payload))
        challenge, status = UX._load_finish()._read_challenge_raw(
            "hook-ticket-generation")
        self.assertEqual(status, "ok")
        self.assertEqual(challenge["generation"], replacement["generation"])
        self.assertFalse(challenge["hook_warning_published"])

    def test_crash_between_new_dialogue_and_index_never_exposes_choice_state(self) -> None:
        class Crash(BaseException):
            pass

        _wt, payload, old = self._retained_hook_action("hook-latch-write-order")
        with mock.patch.object(UX, "write_current_index", side_effect=Crash()), \
                self.assertRaises(Crash):
            UX.handle_hook_payload({
                **payload, "prompt": "Close", "event_id": "crash-before-index",
            })
        survived = UX._read_dialogue_raw("hook-latch-write-order")
        self.assertGreater(survived["generation"], old["generation"])
        self.assertEqual(survived["state"], "action_complete_refresh_pending")
        self.assertEqual(survived["action_kind"], "Retain")
        retry = UX.handle_hook_payload({
            **payload, "prompt": "Close", "event_id": "retry-after-index-crash",
        })
        self.assertFalse(retry["continue"])
        self.assertEqual(
            UX.read_dialogue("hook-latch-write-order")["state"],
            "action_complete_refresh_pending")
        self.assertEqual(len(UX.list_retained()), 1)


class RetainCrashRecoveryMatrixTest(FinalHardeningBase):
    def _ready(self, name: str) -> tuple[str, Path, list[int]]:
        return self.retain_ready(name)

    def _list_cli(self) -> dict:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            rc = UX.main(["retain-list"])
        self.assertEqual(rc, 0)
        self.assertEqual(stderr.getvalue(), "")
        return json.loads(stdout.getvalue())

    def _marker_bytes(self, artifact_id: str) -> bytes:
        _pending, committed, _rollback = UX._publication_paths(artifact_id)
        return committed.read_bytes()

    def test_failed_precommit_final_plus_pending_is_promoted_listed_restored_and_suppressed(
            self) -> None:
        class Crash(BaseException):
            pass

        wt, source, indices = self._ready("recover-final-pending")
        real_write = UX._private_write

        def crash_before_committed(path, data):
            if Path(path).name.endswith(".publication.committed.json"):
                raise Crash()
            return real_write(path, data)

        with mock.patch.object(UX, "_private_write", side_effect=crash_before_committed), \
                self.assertRaises(Crash):
            UX.create_retain("recover-final-pending", indices)
        finals = [
            item for item in UX._retain_dir().iterdir()
            if item.name.startswith("retain-") and item.is_dir()
        ]
        self.assertEqual(len(finals), 1)
        artifact_id = finals[0].name
        pending, committed, _rollback = UX._publication_paths(artifact_id)
        self.assertTrue(pending.exists())
        self.assertFalse(committed.exists())

        listed = {item["artifact_id"] for item in UX.list_retained()}
        self.assertIn(artifact_id, listed)
        self.assertTrue(committed.exists())
        destination = self.data_home / "recovered-restore"
        UX.restore_retain(artifact_id, str(destination))
        self.assertEqual((destination / "draft.txt").read_bytes(), source.read_bytes())
        target = FIN.resolve_target(wt)
        row = next(
            item for item in FIN.build_inventory(wt, target["git_dir"])["entries"]
            if item["path"] == "draft.txt")
        self.assertTrue(row["retained"])

    def test_committed_parent_sync_reboot_rollback_preserves_pending_and_recovers(self) -> None:
        wt, source, indices = self._ready("recover-parent-sync")
        root = UX._retain_dir()
        real_sync = UX._sync_dir

        def fail_committed_parent_sync(path):
            if (Path(path) == root
                    and any(root.glob(".*.publication.pending.json"))
                    and any(root.glob(".*.publication.committed.json"))):
                raise OSError("hostile parent sync")
            return real_sync(path)

        with mock.patch.object(UX, "_sync_dir", side_effect=fail_committed_parent_sync):
            created = UX.create_retain("recover-parent-sync", indices)
        artifact_id = created["artifact_id"]
        pending, committed, _rollback = UX._publication_paths(artifact_id)
        self.assertTrue(pending.exists())
        self.assertTrue(committed.exists())
        committed.unlink()  # simulate the unsynced directory entry disappearing on reboot
        UX._sync_dir(root)
        self.assertIn(
            artifact_id, {item["artifact_id"] for item in UX.list_retained()})
        self.assertTrue(committed.exists())
        self.assertTrue(source.exists())
        target = FIN.resolve_target(wt)
        row = next(
            item for item in FIN.build_inventory(wt, target["git_dir"])["entries"]
            if item["path"] == "draft.txt")
        self.assertTrue(row["retained"])

    def test_staging_and_rollback_pending_candidates_are_preserved_hidden_untrusted(self) -> None:
        for state in ("staging", "rollback"):
            with self.subTest(state=state):
                _wt, source, indices = self._ready("preserve-" + state)
                created = UX.create_retain("preserve-" + state, indices)
                artifact_id = created["artifact_id"]
                final = UX._artifact_path(artifact_id)
                pending, committed, rollback = UX._publication_paths(artifact_id)
                marker = committed.read_bytes()
                UX._private_write(pending, marker)
                committed.unlink()
                candidate = (
                    UX._retain_dir() / ("." + artifact_id + ".staging")
                    if state == "staging" else rollback
                )
                os.replace(final, candidate)
                UX._sync_dir(UX._retain_dir())
                warnings = UX._resume_retain_publications()
                self.assertIn("publication_repair_required", warnings)
                self.assertTrue(candidate.exists())
                self.assertTrue(pending.exists())
                self.assertEqual(UX.list_retained(), [])
                self.assertTrue(source.exists())
                UX.delete_retain(artifact_id, artifact_id)

    def test_mismatch_and_multiple_candidates_are_preserved_and_surfaced(self) -> None:
        _wt, _source, indices = self._ready("preserve-mismatch")
        created = UX.create_retain("preserve-mismatch", indices)
        artifact_id = created["artifact_id"]
        final = UX._artifact_path(artifact_id)
        pending, committed, _rollback = UX._publication_paths(artifact_id)
        committed.unlink()
        UX._private_write(pending, b'{"schema":"mismatch"}\n')
        warnings = UX._resume_retain_publications()
        self.assertIn("publication_repair_required", warnings)
        self.assertTrue(final.exists())
        self.assertTrue(pending.exists())
        mismatch_report = self._list_cli()
        self.assertIn(
            "publication_repair_required",
            mismatch_report["publication_warnings"])
        self.assertNotIn(
            artifact_id,
            {item["artifact_id"] for item in mismatch_report["artifacts"]})

        _wt2, _source2, indices2 = self._ready("preserve-multiple")
        created2 = UX.create_retain("preserve-multiple", indices2)
        artifact_id2 = created2["artifact_id"]
        final2 = UX._artifact_path(artifact_id2)
        staging2 = UX._retain_dir() / ("." + artifact_id2 + ".staging")
        shutil.copytree(final2, staging2)
        warnings2 = UX._resume_retain_publications()
        self.assertIn("publication_repair_required", warnings2)
        self.assertTrue(final2.exists())
        self.assertTrue(staging2.exists())
        multiple_report = self._list_cli()
        self.assertIn(
            "publication_repair_required",
            multiple_report["publication_warnings"])


class ShellMachineTrustTest(FinalHardeningBase):
    def _ready(self, name: str) -> str:
        _repo, wt = self.linked(name)
        Path(wt, "draft.txt").write_text("discard\n", encoding="utf-8")
        UX.preview_payload(self.payload(wt, name))
        return wt

    def _dispatch_shell(self, name: str, stdout: str, returncode: int,
                        *, reconciled: dict | None = None) -> dict:
        self._ready(name)
        real_run = subprocess.run

        def run(command, *args, **kwargs):
            if (isinstance(command, list) and len(command) > 1
                    and command[0] == "bash"
                    and str(command[1]).endswith("kernel/bin/dev-worktree.sh")):
                return subprocess.CompletedProcess(
                    command, returncode, stdout=stdout, stderr="hostile stderr")
            return real_run(command, *args, **kwargs)

        original_load = UX._load_finish
        fin = original_load()
        reconcile_result = reconciled or {
            "outcome": "absent", "reason": "removal_journal_absent",
        }
        with mock.patch.object(UX, "_load_finish", return_value=fin), \
                mock.patch.object(
                    fin, "reconcile_removal", return_value=reconcile_result), \
                mock.patch.object(UX.subprocess, "run", side_effect=run):
            return UX.dispatch_choice(name, "Close")

    def test_malformed_and_contradictory_rc_zero_or_three_never_prove_removal(self) -> None:
        malformed = (
            "",
            "{",
            "[]",
            '{"outcome":"removed","reason":"finish_removed"}',
            '{"outcome":"removed","reason":"finish_removed","branch_action":true}',
            '{"outcome":"removed","reason":"finish_removed","branch_action":"unknown"}',
            '{"outcome":"removed","reason":"finish_removed","branch_action":"deleted","x":1}',
            '{"outcome":"removed","outcome":"removed","reason":"finish_removed",'
            '"branch_action":"deleted"}',
            '{"outcome":"unknown","reason":"finish_removed","branch_action":"deleted"}',
            "x" * 5000,
        )
        contradictory = (
            '{"outcome":"refused","reason":"workspace_preserved"}',
            '{"outcome":"uncertain","reason":"removal_uncertain"}',
        )
        case = 0
        for rc in (0, 3):
            for output in malformed + contradictory:
                with self.subTest(rc=rc, output=output[:40]):
                    result = self._dispatch_shell(
                        f"shell-untrusted-{case}", output, rc)
                    case += 1
                    self.assertIsNone(result["workspace_removed"])
                    self.assertNotIn("branch_action", result)
                    self.assertTrue(result["agent_stopping"])

    def test_exact_projection_and_exit_status_controls(self) -> None:
        for rc in (0, 3):
            result = self._dispatch_shell(
                f"shell-valid-removed-{rc}",
                '{"outcome":"removed","reason":"finish_removed",'
                '"branch_action":"deleted"}\n',
                rc)
            self.assertTrue(result["workspace_removed"])
            self.assertEqual(result["branch_action"], "deleted")
            self.assertEqual(result["audit_receipt_failed"], rc == 3)
        refused = self._dispatch_shell(
            "shell-valid-refused",
            '{"outcome":"refused","reason":"workspace_preserved"}\n', 1)
        self.assertFalse(refused["workspace_removed"])
        self.assertNotIn("branch_action", refused)
        contradicted = self._dispatch_shell(
            "shell-removed-wrong-rc",
            '{"outcome":"removed","reason":"finish_removed",'
            '"branch_action":"retained"}\n',
            1)
        self.assertIsNone(contradicted["workspace_removed"])
        self.assertNotIn("branch_action", contradicted)

    def test_rejected_shell_output_can_only_recover_from_bound_valid_journal(self) -> None:
        recovered = self._dispatch_shell(
            "shell-bound-recovery", "{", 0,
            reconciled={
                "outcome": "removed",
                "reason": "finish_removed",
                "branch_action": "retained_local_only",
            })
        self.assertTrue(recovered["workspace_removed"])
        self.assertEqual(recovered["branch_action"], "retained_local_only")


class PublicationOrderedRecoveryTest(FinalHardeningBase):
    def _ready(self, name: str) -> tuple[str, dict]:
        _repo, wt = self.linked(name)
        Path(wt, "draft.txt").write_text("discard\n", encoding="utf-8")
        UX.preview_payload(self.payload(wt, name))
        dialogue = UX.read_dialogue(name)
        return wt, dialogue

    def test_dialogue_cleans_before_output_but_index_cas_waits_for_flush(self) -> None:
        _wt, dialogue = self._ready("index-after-output")
        path = UX.index_path("index-after-output")
        result = UX._removed_dispatch_result(dialogue, {
            "outcome": "removed", "reason": "finish_removed",
            "branch_action": "retained",
        })
        self.assertFalse(UX.dialogue_path("index-after-output").exists())
        self.assertTrue(path.exists())

        class TrackingOutput(io.StringIO):
            saw_anchor_at_flush = False

            def flush(inner_self) -> None:
                inner_self.saw_anchor_at_flush = path.exists()
                super().flush()

        output = TrackingOutput()
        with contextlib.redirect_stdout(output):
            UX._write_dispatch_result(result)
        self.assertTrue(output.saw_anchor_at_flush)
        self.assertFalse(path.exists())
        self.assertTrue(json.loads(output.getvalue())["workspace_removed"])

    def test_output_interruption_keeps_anchor_and_superseding_index_is_untouched(self) -> None:
        _wt, dialogue = self._ready("index-output-interrupt")
        path = UX.index_path("index-output-interrupt")
        result = UX._removed_dispatch_result(dialogue, {
            "outcome": "removed", "reason": "finish_removed",
            "branch_action": "deleted",
        })

        class BrokenOutput(io.StringIO):
            def write(self, _value) -> int:
                raise OSError("output interrupted")

        with mock.patch.object(UX.sys, "stdout", BrokenOutput()), \
                self.assertRaises(OSError):
            UX._write_dispatch_result(result)
        self.assertTrue(path.exists())

        superseding = json.loads(path.read_text(encoding="utf-8"))
        superseding["generation"] += 1
        superseding["nonce"] = "superseding-generation"
        UX._json_write(path, superseding)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            UX._write_dispatch_result(result)
        self.assertTrue(path.exists())
        self.assertEqual(
            json.loads(path.read_text(encoding="utf-8"))["nonce"],
            "superseding-generation")

    def test_recovery_uses_exact_index_and_journal_without_dialogue(self) -> None:
        _wt, dialogue = self._ready("index-journal-only")
        index = json.loads(
            UX.index_path("index-journal-only").read_text(encoding="utf-8"))
        UX.dialogue_path("index-journal-only").unlink()
        operation_id = "b" * 64
        finish_dir = Path(FIN.finish_dir())
        finish_dir.mkdir(parents=True, exist_ok=True)
        Path(finish_dir, f"removal-{operation_id}.json").write_text(
            "{}\n", encoding="utf-8")
        journal = {
            **{key: index[key] for key in (
                "root", "session_id", "conversation_id", "generation",
                "nonce", "fingerprint")},
            **{key: dialogue["target"][key] for key in (
                "git_dir", "common_dir", "branch", "head")},
        }
        # Recovery filters by the caller's session. Bind this synthetic index to
        # its fixture session rather than inheriting the test runner's identity.
        with mock.patch.dict(os.environ, {"DEV_SESSION_ID": index["session_id"]}), \
                mock.patch.object(UX, "_load_finish", return_value=FIN), \
                mock.patch.object(
                FIN, "read_removal_journal", return_value=(journal, "ok")), \
                mock.patch.object(FIN, "reconcile_removal", return_value={
                    "outcome": "removed", "reason": "finish_removed",
                    "branch_action": "retained_local_only",
                }):
            recovered = UX._recover_current_removal()
        self.assertTrue(recovered["workspace_removed"])
        self.assertEqual(recovered["branch_action"], "retained_local_only")
        self.assertTrue(UX.index_path("index-journal-only").exists())
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            UX._write_dispatch_result(recovered)
        self.assertFalse(UX.index_path("index-journal-only").exists())

    def test_uncertain_output_also_releases_anchor_only_after_flush(self) -> None:
        _wt, dialogue = self._ready("index-uncertain-output")
        path = UX.index_path("index-uncertain-output")
        result = UX._uncertain_after_close(dialogue)
        self.assertIsNone(result["workspace_removed"])
        self.assertTrue(path.exists())
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            UX._write_dispatch_result(result)
        self.assertFalse(path.exists())
        self.assertIsNone(json.loads(output.getvalue())["workspace_removed"])

    def test_cli_output_failure_never_appends_workspace_preserved_fallback(self) -> None:
        _wt, dialogue = self._ready("index-cli-output-fault")
        path = UX.index_path("index-cli-output-fault")

        class FailOnce(io.StringIO):
            calls = 0

            def write(inner_self, value) -> int:
                inner_self.calls += 1
                if inner_self.calls == 1:
                    raise OSError("terminal closed")
                return super().write(value)

        sink = FailOnce()
        with mock.patch.object(
                UX, "dispatch_current",
                side_effect=lambda: UX._uncertain_after_close(dialogue)), \
                mock.patch.object(UX.sys, "stdout", sink):
            rc = UX.main(["dispatch", "--current"])
        self.assertEqual(rc, 1)
        self.assertEqual(sink.calls, 1, "must not append a false preserved JSON record")
        self.assertTrue(path.exists())


class JournalDerivedBranchTruthTest(FinalHardeningBase):
    ACTIONS = (
        "retained", "retained_local_only", "deleted", "delete_failed", "delete_error",
    )

    def _record(self) -> dict:
        return {
            "operation_id": "c" * 64,
            "phase": "removed",
            "root": "/removed/worktree",
            "git_dir": "/common/worktrees/removed",
            "common_dir": "/common",
            "branch": "cursor/worktree/branch-truth",
            "head": "d" * 40,
            "conversation_id": "branch-truth",
            "nonce": "nonce",
            "generation": 1,
            "session_id": "session",
            "boot_id": "boot",
            "fingerprint": "e" * 64,
            "branch_disposition": {
                "action": "delete_eligible", "reason": "awa_attested_ephemeral",
            },
            "branch_action": "",
            "discard_count": 1,
            "cleanup_warnings": [],
            "receipt_committed": False,
        }

    def test_durable_journal_precedes_closed_memory_and_no_retained_default_exists(self) -> None:
        base = {
            "outcome": "removed", "reason": "finish_removed",
            "state_cleanup_warnings": ["removal_reconciliation_incomplete"],
        }
        for action in self.ACTIONS:
            with self.subTest(action=action):
                rec = self._record()
                with mock.patch.object(
                        FIN, "_durable_branch_action", return_value=action):
                    result = FIN._removed_fallback_from_branch_truth(
                        rec, base, "retained" if action != "retained" else "deleted")
                self.assertEqual(result["branch_action"], action)
        rec = self._record()
        with mock.patch.object(FIN, "_durable_branch_action", return_value=""):
            memory = FIN._removed_fallback_from_branch_truth(
                rec, base, "delete_error")
            missing = FIN._removed_fallback_from_branch_truth(rec, base, "")
        self.assertEqual(memory["branch_action"], "delete_error")
        self.assertEqual(missing["outcome"], "uncertain")
        self.assertNotIn("branch_action", missing)

    def test_post_branch_cleanup_faults_preserve_each_action_and_reconcile_idempotently(
            self) -> None:
        for action in self.ACTIONS:
            with self.subTest(action=action):
                rec = self._record()
                durable = {"action": ""}
                writes = []

                def write(record):
                    writes.append((record["phase"], record["branch_action"]))
                    durable["action"] = record["branch_action"]

                roots = mock.Mock()
                roots._remove_root_locked.side_effect = OSError("root cleanup")
                roots.remove_current_session_cas.side_effect = OSError("session cleanup")
                with mock.patch.object(
                        FIN, "_operation_removal_state_locked",
                        return_value={"state": "removed", "reason": "removed"}), \
                        mock.patch.object(
                            FIN, "_finalize_branch_locked", return_value=action) as finalized, \
                        mock.patch.object(
                            FIN, "_durable_branch_action",
                            side_effect=lambda _rec: durable["action"]), \
                        mock.patch.object(
                            FIN, "_write_removal_journal", side_effect=write), \
                        mock.patch.object(
                            FIN, "_cleanup_challenge_locked",
                            side_effect=OSError("challenge cleanup")), \
                        mock.patch.object(FIN, "_roots_module", return_value=roots), \
                        mock.patch.object(
                            FIN, "_write_removed_receipt_locked", return_value=True):
                    first = FIN._reconcile_removal_journal_locked(rec)
                    second = FIN._reconcile_removal_journal_locked(rec)
                self.assertEqual(first["outcome"], "removed")
                self.assertEqual(first["branch_action"], action)
                self.assertEqual(second["branch_action"], action)
                finalized.assert_called_once()
                self.assertTrue(writes)
                self.assertIn("challenge_cleanup_failed", first["state_cleanup_warnings"])
                self.assertIn("active_root_cleanup_failed", first["state_cleanup_warnings"])
                self.assertIn("current_session_cleanup_failed", first["state_cleanup_warnings"])

                public = UX._build_public_dispatch(
                    UX.PublicDispatchOutcome.REMOVED,
                    reason=UX.PublicDispatchReason.FINISH_REMOVED,
                    kernel_outcome={"branch_action": action})
                expected = {
                    "retained": "retained",
                    "retained_local_only": "retained_local_only",
                    "deleted": "deleted",
                    "delete_failed": "retained",
                    "delete_error": "retained",
                }[action]
                self.assertEqual(public["branch_action"], expected)


class ClosedArgparseTest(FinalHardeningBase):
    HOSTILE = "/private/parser/value SHOULD-NOT-ESCAPE"

    def _invoke(self, function, argv: list[str]) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            rc = function(argv)
        return rc, stdout.getvalue(), stderr.getvalue()

    def test_consumer_parse_errors_are_fixed_json_empty_stderr_and_exit_two(self) -> None:
        cases = (
            ["--unknown", self.HOSTILE],
            ["commit", "--conversation-id", "c", "--rows", "1", "--message", "m",
             "--timeout", self.HOSTILE],
            ["retain", "--conversation-id", "c", "--rows", self.HOSTILE],
            ["mixed", "--conversation-id", "c", "--commit-rows", "1",
             "--retain-rows", self.HOSTILE, "--message", "m"],
            ["retain"],
            ["retain-list", self.HOSTILE],
        )
        outputs = []
        for argv in cases:
            rc, stdout, stderr = self._invoke(UX.main, argv)
            self.assertEqual(rc, 2)
            self.assertEqual(stderr, "")
            self.assertNotIn(self.HOSTILE, stdout)
            outputs.append(json.loads(stdout))
        self.assertTrue(all(item == outputs[0] for item in outputs))

    def test_kernel_parse_errors_are_fixed_json_empty_stderr_and_exit_two(self) -> None:
        cases = (
            ["--unknown", self.HOSTILE],
            ["flock-fd", "--fd", self.HOSTILE],
            ["resolve-target"],
            ["finish-dir", self.HOSTILE],
        )
        outputs = []
        for argv in cases:
            rc, stdout, stderr = self._invoke(FIN.main, argv)
            self.assertEqual(rc, 2)
            self.assertEqual(stderr, "")
            self.assertNotIn(self.HOSTILE, stdout)
            outputs.append(json.loads(stdout))
        self.assertTrue(all(item == outputs[0] for item in outputs))

    def test_help_remains_normal(self) -> None:
        for function in (UX.main, FIN.main):
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr), \
                    self.assertRaises(SystemExit) as raised:
                function(["--help"])
            self.assertEqual(raised.exception.code, 0)
            self.assertIn("usage:", stdout.getvalue())
            self.assertEqual(stderr.getvalue(), "")

    def test_every_long_option_prefix_is_closed_while_exact_spelling_still_works(self) -> None:
        consumer_prefixes = (
            ["--he"],
            ["warning", "--row", self.HOSTILE],
            ["retain", "--conversation-i", self.HOSTILE, "--rows", "1"],
        )
        kernel_prefixes = (
            ["--he"],
            ["resolve-target", "--roo", self.HOSTILE],
            ["finish-execute", "--common-d", self.HOSTILE],
            ["finish-execute", "--lock-time", self.HOSTILE],
        )
        for function, cases in (
                (UX.main, consumer_prefixes), (FIN.main, kernel_prefixes)):
            outputs = []
            for argv in cases:
                rc, stdout, stderr = self._invoke(function, list(argv))
                self.assertEqual(rc, 2, argv)
                self.assertEqual(stderr, "")
                self.assertNotIn(self.HOSTILE, stdout)
                outputs.append(json.loads(stdout))
            self.assertTrue(all(value == outputs[0] for value in outputs))

        rc, stdout, stderr = self._invoke(
            UX.main, ["warning", "--rows", "exact row"])
        self.assertEqual(rc, 0)
        self.assertIn("exact row", stdout)
        self.assertEqual(stderr, "")
        for function, argv in (
                (UX.main, ["warning", "--help"]),
                (FIN.main, ["finish-execute", "--help"])):
            stdout_io, stderr_io = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout_io), \
                    contextlib.redirect_stderr(stderr_io), \
                    self.assertRaises(SystemExit) as raised:
                function(argv)
            self.assertEqual(raised.exception.code, 0)
            self.assertIn("usage:", stdout_io.getvalue())
            self.assertEqual(stderr_io.getvalue(), "")


class EmptyDirectoryTreeTest(FinalHardeningBase):
    def _inventory(self, wt: str) -> tuple[dict, dict]:
        target = FIN.resolve_target(wt)
        return target, FIN.build_inventory(wt, target["git_dir"])

    def _fingerprint(self, target: dict, inventory: dict) -> str:
        physical = FIN.capture_physical_incarnations(
            target["root"], target["git_dir"])
        return FIN.compute_fingerprint(
            inventory, **target, membership=[],
            root_incarnation=physical[0], git_dir_incarnation=physical[1])

    def test_nested_trees_are_shallow_deduplicated_and_tracked_ancestors_excluded(self) -> None:
        _repo, wt = self.linked("empty-tree-inventory")
        Path(wt, "outer/inner/leaf").mkdir(parents=True)
        Path(wt, "tracked-parent/empty/deep").mkdir(parents=True)
        Path(wt, "tracked-parent/tracked.txt").parent.mkdir(parents=True, exist_ok=True)
        Path(wt, "tracked-parent/tracked.txt").write_text("tracked\n", encoding="utf-8")
        git(wt, "add", "tracked-parent/tracked.txt")
        git(wt, "-c", "user.name=AWA Test", "-c",
            "user.email=awa@example.invalid", "commit", "-qm", "tracked parent")
        _target, inventory = self._inventory(wt)
        trees = [row for row in inventory["entries"] if row["kind"] == "empty_dir_tree"]
        self.assertEqual([row["path"] for row in trees],
                         ["outer", "tracked-parent/empty"])
        self.assertTrue(all(row["commit_eligible"] is False for row in trees))
        self.assertTrue(all(row["retain_eligible"] is True for row in trees))
        outer = trees[0]
        self.assertEqual(
            [bytes.fromhex(item["path_hex"]).decode() for item in outer["tree_members"]],
            ["outer", "outer/inner", "outer/inner/leaf"])
        self.assertNotIn("tracked-parent", [row["path"] for row in trees])
        self.assertNotIn("outer/inner", [row["path"] for row in trees])
        self.assertNotEqual(FIN.render_rows(inventory),
                            "None | No operator work will be deleted.")

    def test_ignored_and_cruft_trees_are_classified_read_only_and_fingerprint_bound(self) -> None:
        _repo, wt = self.linked("empty-tree-ignore")
        target = FIN.resolve_target(wt)
        exclude = Path(target["common_dir"], "info", "exclude")
        with exclude.open("a", encoding="utf-8") as handle:
            handle.write("\nignored-tree/\ncontainer/ignored-deep/\n")
        Path(wt, "ignored-tree/deep").mkdir(parents=True)
        Path(wt, "container/ignored-deep/leaf").mkdir(parents=True)
        Path(wt, "node_modules/cache/empty").mkdir(parents=True)
        target, before = self._inventory(wt)
        by_path = {row["path"]: row for row in before["entries"]
                   if row["kind"] == "empty_dir_tree"}
        self.assertEqual(by_path["ignored-tree"]["class"], "ignored")
        self.assertEqual(by_path["container"]["class"], "untracked")
        self.assertFalse(by_path["ignored-tree"]["hidden"])
        self.assertTrue(by_path["node_modules"]["hidden"])
        self.assertNotIn("container/ignored-deep", by_path)
        self.assertIn("ignored-tree", FIN.render_rows(before))
        self.assertNotIn("node_modules", FIN.render_rows(before))
        first = self._fingerprint(target, before)
        os.chmod(Path(wt, "ignored-tree/deep"), 0o751)
        _target, mode_changed = self._inventory(wt)
        second = self._fingerprint(target, mode_changed)
        self.assertNotEqual(first, second)
        Path(wt, "ignored-tree/deep/new-leaf").mkdir()
        _target, topology_changed = self._inventory(wt)
        third = self._fingerprint(target, topology_changed)
        self.assertNotEqual(second, third)

    def test_retain_restore_proves_exact_empty_topology_and_modes(self) -> None:
        _repo, wt = self.linked("empty-tree-retain")
        Path(wt, "empty/sub/leaf").mkdir(parents=True)
        os.chmod(Path(wt, "empty"), 0o711)
        os.chmod(Path(wt, "empty/sub"), 0o750)
        os.chmod(Path(wt, "empty/sub/leaf"), 0o705)
        UX.preview_payload(self.payload(wt, "empty-tree-retain"))
        UX.dispatch_choice("empty-tree-retain", "Retain")
        dialogue = UX.read_dialogue("empty-tree-retain")
        index = next(
            number for number, row in enumerate(dialogue["visible"], 1)
            if row["path"] == "empty")
        created = UX.create_retain("empty-tree-retain", [index])
        destination = self.data_home / "empty-tree-restore"
        UX.restore_retain(created["artifact_id"], str(destination))
        expected = {
            "empty": 0o711,
            "empty/sub": 0o750,
            "empty/sub/leaf": 0o705,
        }
        actual = {
            str(path.relative_to(destination)): path.stat().st_mode & 0o777
            for path in destination.rglob("*")
            if path.is_dir() and ".git" not in path.parts
        }
        self.assertEqual(actual, expected)

    def test_commit_and_mixed_reject_retain_only_rows_before_any_mutation(self) -> None:
        _repo, wt = self.linked("empty-tree-commit-refusal")
        Path(wt, "empty/deep").mkdir(parents=True)
        UX.preview_payload(self.payload(wt, "empty-tree-commit-refusal"))
        UX.dispatch_choice("empty-tree-commit-refusal", "Commit")
        dialogue = UX.read_dialogue("empty-tree-commit-refusal")
        empty_index = next(
            number for number, row in enumerate(dialogue["visible"], 1)
            if row["path"] == "empty")
        head = git(wt, "rev-parse", "HEAD").stdout.strip()
        status = git(wt, "status", "--porcelain=v1", "-uall").stdout
        with self.assertRaisesRegex(UX.FinishUXError, "retain_only"):
            UX.commit_selected_local(
                "empty-tree-commit-refusal", [empty_index], "must refuse")
        self.assertEqual(git(wt, "rev-parse", "HEAD").stdout.strip(), head)
        self.assertEqual(git(wt, "status", "--porcelain=v1", "-uall").stdout, status)
        self.assertEqual(
            UX.read_dialogue("empty-tree-commit-refusal")["state"],
            "awaiting_commit_selection")

        _repo2, wt2 = self.linked("empty-tree-mixed-refusal")
        Path(wt2, "empty/deep").mkdir(parents=True)
        Path(wt2, "retain.txt").write_text("retain\n", encoding="utf-8")
        UX.preview_payload(self.payload(wt2, "empty-tree-mixed-refusal"))
        UX.dispatch_choice("empty-tree-mixed-refusal", "Mixed")
        mixed = UX.read_dialogue("empty-tree-mixed-refusal")
        by_path = {
            row["path"]: number
            for number, row in enumerate(mixed["visible"], 1)
        }
        retain_root = UX._retain_dir()
        before_artifacts = (
            {item.name for item in retain_root.iterdir()}
            if retain_root.is_dir() else set())
        head2 = git(wt2, "rev-parse", "HEAD").stdout.strip()
        status2 = git(wt2, "status", "--porcelain=v1", "-uall").stdout
        with self.assertRaisesRegex(UX.FinishUXError, "retain_only"):
            UX.complete_mixed(
                "empty-tree-mixed-refusal", [by_path["empty"]],
                [by_path["retain.txt"]], "must refuse")
        self.assertEqual(git(wt2, "rev-parse", "HEAD").stdout.strip(), head2)
        self.assertEqual(git(wt2, "status", "--porcelain=v1", "-uall").stdout, status2)
        self.assertEqual(
            ({item.name for item in retain_root.iterdir()}
             if retain_root.is_dir() else set()),
            before_artifacts)
        self.assertEqual(
            UX.read_dialogue("empty-tree-mixed-refusal")["state"],
            "awaiting_mixed_selection")


class IgnoredRowsRetainOnlyTest(FinalHardeningBase):
    def _ignored_workspace(self, name: str) -> tuple[str, dict]:
        _repo, wt = self.linked(name)
        Path(wt, ".gitignore").write_text(
            "ignored.txt\nignored-dir/\n.env.production\n", encoding="utf-8")
        git(wt, "add", ".gitignore")
        git(wt, "-c", "user.name=AWA Test", "-c",
            "user.email=awa@example.invalid", "commit", "-qm", "ignore fixtures")
        Path(wt, "ignored.txt").write_text("ignored file\n", encoding="utf-8")
        Path(wt, "ignored-dir").mkdir()
        Path(wt, "ignored-dir/child.txt").write_text(
            "ignored child\n", encoding="utf-8")
        Path(wt, ".env.production").write_text(
            "TOKEN=not-a-real-secret\n", encoding="utf-8")
        Path(wt, "ordinary.txt").write_text("ordinary\n", encoding="utf-8")
        target = FIN.resolve_target(wt)
        inventory = FIN.build_inventory(wt, target["git_dir"])
        return wt, inventory

    def test_every_visible_ignored_file_directory_and_secret_is_retain_only(self) -> None:
        _wt, inventory = self._ignored_workspace("ignored-classification")
        ignored = [
            row for row in inventory["entries"]
            if row["class"] == "ignored" and not row["hidden"]
        ]
        self.assertGreaterEqual(len(ignored), 3)
        self.assertTrue(any(row["template_id"] == "secret" for row in ignored))
        self.assertTrue(any(row["kind"] == "dir" for row in ignored))
        for row in ignored:
            self.assertFalse(row["commit_eligible"], row)
            self.assertTrue(row["retain_eligible"], row)

    def test_commit_and_mixed_commit_partition_reject_before_any_mutation(self) -> None:
        wt, _inventory = self._ignored_workspace("ignored-commit-refusal")
        UX.preview_payload(self.payload(wt, "ignored-commit-refusal"))
        UX.dispatch_choice("ignored-commit-refusal", "Commit")
        dialogue = UX.read_dialogue("ignored-commit-refusal")
        ignored_rows = [
            number for number, row in enumerate(dialogue["visible"], 1)
            if row["class"] == "ignored"
        ]
        before_head = git(wt, "rev-parse", "HEAD").stdout.strip()
        before_status = git(
            wt, "status", "--porcelain=v1", "-uall", "--ignored=matching").stdout
        with mock.patch.object(UX, "_claim_action") as claimed, \
                mock.patch.object(UX, "_run_checked") as git_mutation:
            with self.assertRaisesRegex(UX.FinishUXError, "retain_only"):
                UX.commit_selected_local(
                    "ignored-commit-refusal", ignored_rows, "must refuse")
        claimed.assert_not_called()
        git_mutation.assert_not_called()
        self.assertEqual(git(wt, "rev-parse", "HEAD").stdout.strip(), before_head)
        self.assertEqual(
            git(wt, "status", "--porcelain=v1", "-uall",
                "--ignored=matching").stdout,
            before_status)
        self.assertEqual(
            UX.read_dialogue("ignored-commit-refusal")["state"],
            "awaiting_commit_selection")

        wt2, _inventory2 = self._ignored_workspace("ignored-mixed-refusal")
        UX.preview_payload(self.payload(wt2, "ignored-mixed-refusal"))
        UX.dispatch_choice("ignored-mixed-refusal", "Mixed")
        mixed = UX.read_dialogue("ignored-mixed-refusal")
        ignored_index = next(
            number for number, row in enumerate(mixed["visible"], 1)
            if row["class"] == "ignored")
        other = [
            number for number in range(1, len(mixed["visible"]) + 1)
            if number != ignored_index
        ]
        with mock.patch.object(UX, "_claim_action") as claimed, \
                mock.patch.object(UX, "create_retain") as retain, \
                mock.patch.object(UX, "deliver_commit") as delivery:
            with self.assertRaisesRegex(UX.FinishUXError, "retain_only"):
                UX.complete_mixed(
                    "ignored-mixed-refusal", [ignored_index], other,
                    "must refuse before Retain")
        claimed.assert_not_called()
        retain.assert_not_called()
        delivery.assert_not_called()
        self.assertEqual(
            UX.read_dialogue("ignored-mixed-refusal")["state"],
            "awaiting_mixed_selection")

    def test_mixed_retains_ignored_commits_ordinary_and_restore_proves_ignore_intent(
            self) -> None:
        wt, _inventory = self._ignored_workspace("ignored-mixed-success")
        UX.preview_payload(self.payload(wt, "ignored-mixed-success"))
        UX.dispatch_choice("ignored-mixed-success", "Mixed")
        dialogue = UX.read_dialogue("ignored-mixed-success")
        commit_rows = [
            number for number, row in enumerate(dialogue["visible"], 1)
            if row["path"] == "ordinary.txt"
        ]
        retain_rows = [
            number for number, row in enumerate(dialogue["visible"], 1)
            if row["class"] == "ignored"
        ]
        self.assertEqual(len(commit_rows), 1)
        self.assertTrue(any(
            dialogue["visible"][number - 1]["template_id"] == "secret"
            for number in retain_rows))
        before_artifacts = list(UX.list_retained())
        with self.assertRaisesRegex(
                UX.FinishUXError, "explicit_secret_confirmation_required"):
            UX.complete_mixed(
                "ignored-mixed-success", commit_rows, retain_rows,
                "commit ordinary only")
        self.assertEqual(UX.list_retained(), before_artifacts)
        self.assertEqual(
            UX.read_dialogue("ignored-mixed-success")["state"],
            "awaiting_mixed_selection")

        with mock.patch.object(
                UX, "deliver_commit",
                return_value={"ok": True, "proof": {"checks": 0}}):
            result = UX.complete_mixed(
                "ignored-mixed-success", commit_rows, retain_rows,
                "commit ordinary only", allow_secrets=True)
        self.assertTrue(result["action_complete"])
        artifact_id = result["retained"]["artifact_id"]
        changed = git(
            wt, "show", "--pretty=format:", "--name-only", "HEAD").stdout.splitlines()
        self.assertEqual(changed, ["ordinary.txt"])

        manifest = UX._manifest(UX._artifact_path(artifact_id))
        self.assertEqual(
            set(manifest["ignore_intent"]),
            {dialogue["visible"][number - 1]["path"] for number in retain_rows})
        self.assertTrue(manifest["explicit_secrets"])
        destination = self.data_home / "ignored-restore"
        UX.restore_retain(artifact_id, str(destination))
        self.assertEqual(
            (destination / "ignored.txt").read_text(encoding="utf-8"),
            "ignored file\n")
        self.assertEqual(
            (destination / "ignored-dir/child.txt").read_text(encoding="utf-8"),
            "ignored child\n")
        self.assertEqual(
            (destination / ".env.production").read_text(encoding="utf-8"),
            "TOKEN=not-a-real-secret\n")
        for rel in ("ignored.txt", "ignored-dir/child.txt", ".env.production"):
            self.assertEqual(git(str(destination), "check-ignore", "-q", rel).returncode, 0)


if __name__ == "__main__":
    import unittest
    unittest.main()
