"""Regressions for opaque regular-file churn across the multi-turn finish flow."""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
from unittest import mock

from consumer import finish_current as UX
from kernel.lib import awa_finish as FIN
from .helpers import commit_all
from .test_finish_hardening import HardeningBase


class FinishSemanticDriftTest(HardeningBase):
    def linked_fixture(self, name: str) -> tuple[str, str]:
        repo = self.make_repo(name)
        Path(repo, ".gitignore").write_text(
            ".cursor/hooks/state/\nignored-operator/\n", encoding="utf-8")
        Path(repo, ".cursor/hooks").mkdir(parents=True)
        Path(repo, ".cursor/hooks/.gitkeep").write_text("", encoding="utf-8")
        commit_all(repo, "ignore fixture state")
        return repo, self.add_worktree(repo, f"cursor/worktree/{name}")

    def retain_selection(
            self, name: str, *, sentinel_name: str = "UAT-RETAIN-SENTINEL.txt",
            initial_hook_file: bool = True,
            ) -> tuple[str, Path, dict, int]:
        _repo, wt = self.linked_fixture(name)
        hook_state = Path(wt, ".cursor/hooks/state/continual-learning.json")
        hook_state.parent.mkdir(parents=True)
        if initial_hook_file:
            hook_state.write_text('{"turnsSinceLastRun":2}\n', encoding="utf-8")
        sentinel = Path(wt, f"ignored-operator/{sentinel_name}")
        sentinel.parent.mkdir(parents=True)
        sentinel.write_text("retain-me\n", encoding="utf-8")
        self.start(wt, name)
        UX.handle_hook_payload(self.payload(
            wt, "Retain", name, event_id=f"{name}-retain-choice"))
        selection = self.current(wt)
        self.assertEqual(selection["state"], "awaiting_retain_selection")
        dialogue = UX.read_dialogue(name)
        sentinel_row = next(
            number for number, row in enumerate(dialogue["visible"], 1)
            if row["path"] == "ignored-operator")
        return wt, hook_state, dialogue, sentinel_row

    def test_unselected_hook_state_content_drift_allows_retain_refresh_and_close(self) -> None:
        """Bites merged pre-fix main at complete_retain with live_inventory_drift."""
        conversation = "semantic-drift-flow"
        wt, hook_state, dialogue, sentinel_row = self.retain_selection(
            conversation, initial_hook_file=False)
        self.assertFalse(hook_state.exists())
        self.assertTrue(any(
            row["path"] == ".cursor/hooks/state" for row in dialogue["visible"]))

        # Exact Desktop UAT shape: the displayed ignored directory row already exists, then a
        # normal Cursor stop hook creates its state file between the choice and row turn.
        hook_state.write_text('{"turnsSinceLastRun":3}\n', encoding="utf-8")
        retained = UX.complete_retain(conversation, [sentinel_row])
        self.assertTrue(retained["artifact"]["protected"], retained)
        self.assertTrue(retained["artifact"]["restore_proven"], retained)
        self.assertTrue(retained["fresh_preview_required"], retained)

        # The required post-Retain turn publishes a fresh warning before Close can be accepted.
        refresh_payload = self.payload(
            wt, "continue", conversation, event_id="post-retain-refresh")
        refreshed = UX.handle_hook_payload(refresh_payload)
        self.assertFalse(refreshed["continue"], refreshed)
        self.assertTrue(UX.mark_hook_published(refresh_payload))
        self.assertNotIn("ignored-operator", refreshed["user_message"])

        # The same stop hook writes again after the fresh warning. Exact Close must still complete
        # because the warning already authorized deletion of this unchanged path and object shape.
        hook_state.write_text('{"turnsSinceLastRun":4}\n', encoding="utf-8")
        UX.handle_hook_payload(self.payload(
            wt, "Close", conversation, event_id="exact-close"))
        removed = self.current(wt)
        self.assertTrue(removed["workspace_removed"], removed)
        self.assertTrue(removed["agent_stopping"], removed)
        self.assertFalse(Path(wt).exists())

    def test_selected_row_content_drift_still_refuses(self) -> None:
        wt, _hook_state, _dialogue, sentinel_row = self.retain_selection(
            "semantic-selected-drift")
        Path(wt, "ignored-operator/UAT-RETAIN-SENTINEL.txt").write_text(
            "changed-after-selection\n", encoding="utf-8")
        with self.assertRaisesRegex(UX.FinishUXError, "^live_inventory_drift$"):
            UX.complete_retain("semantic-selected-drift", [sentinel_row])
        self.assertEqual(UX.list_retained(), [])

    def test_commit_and_mixed_keep_full_content_drift_refusal(self) -> None:
        for choice in ("Commit", "Mixed"):
            with self.subTest(choice=choice):
                name = f"semantic-strict-{choice.lower()}"
                _repo, wt = self.linked_fixture(name)
                draft = Path(wt, "draft.txt")
                draft.write_text("before\n", encoding="utf-8")
                self.start(wt, name)
                draft.write_text("after\n", encoding="utf-8")
                UX.handle_hook_payload(self.payload(
                    wt, choice, name, event_id=f"{name}-choice"))
                result = self.current(wt)
                self.assertEqual(result["reason"], "live_inventory_drift")
                self.assertEqual(UX.read_dialogue(name)["state"], "awaiting_choice")

    def test_every_unselected_structural_drift_class_refuses(self) -> None:
        def insert(_path: Path, wt: str) -> None:
            Path(wt, "new-visible-row.txt").write_text("{}\n", encoding="utf-8")

        def remove(path: Path, _wt: str) -> None:
            path.unlink()
            path.parent.rmdir()

        def rename(path: Path, _wt: str) -> None:
            path.parent.rename(path.parent.with_name("renamed-state"))

        def change_type(path: Path, _wt: str) -> None:
            path.unlink()
            path.mkdir()

        def change_to_symlink(path: Path, wt: str) -> None:
            path.unlink()
            target = os.path.relpath(
                Path(wt, "ignored-operator/UAT-RETAIN-SENTINEL.txt"), path.parent)
            path.symlink_to(target)

        for label, mutate in (
                ("insert", insert),
                ("remove", remove),
                ("rename", rename),
                ("type", change_type),
                ("symlink", change_to_symlink)):
            with self.subTest(label=label):
                name = f"semantic-structure-{label}"
                wt, hook_state, _dialogue, sentinel_row = self.retain_selection(name)
                mutate(hook_state, wt)
                with self.assertRaisesRegex(
                        UX.FinishUXError, "^live_inventory_drift$"):
                    UX.complete_retain(name, [sentinel_row])
                self.assertEqual(UX.list_retained(), [])

    def test_row_reorder_changes_structure_binding_and_refuses_close(self) -> None:
        _repo, wt = self.linked_fixture("semantic-row-reorder")
        Path(wt, "a.txt").write_text("a\n", encoding="utf-8")
        Path(wt, "z.txt").write_text("z\n", encoding="utf-8")
        target = FIN.resolve_target(root=wt)
        inv = FIN.build_inventory(wt, target["git_dir"])
        self.assertTrue(inv["safe"], inv)
        original = FIN.compute_structure_fingerprint(
            inv, **target, membership=[])
        reordered_inventory = dict(inv)
        reordered_inventory["entries"] = list(reversed(inv["entries"]))
        reordered = FIN.compute_structure_fingerprint(
            reordered_inventory, **target, membership=[])
        self.assertNotEqual(original, reordered)
        authorized, reason = FIN.authorize(
            "Close",
            {"fingerprint": "a" * 64, "structure_fingerprint": original},
            current_fingerprint="b" * 64,
            current_structure_fingerprint=reordered)
        self.assertFalse(authorized)
        self.assertEqual(reason, "fingerprint_mismatch")

    def test_legacy_stale_fingerprint_has_no_structural_fallback(self) -> None:
        authorized, reason = FIN.authorize(
            "Close", {"fingerprint": "a" * 64},
            current_fingerprint="b" * 64,
            current_structure_fingerprint="c" * 64)
        self.assertFalse(authorized)
        self.assertEqual(reason, "fingerprint_mismatch")

    def test_structural_fallback_never_broadens_exact_close_authorization(self) -> None:
        challenge = {
            "fingerprint": "a" * 64,
            "structure_fingerprint": "c" * 64,
        }
        authorized, reason = FIN.authorize(
            "Close", challenge,
            current_fingerprint="b" * 64,
            current_structure_fingerprint="c" * 64)
        self.assertTrue(authorized)
        self.assertEqual(reason, "authorized")
        for answer in ("close", " Close", "Close ", "yes", True):
            with self.subTest(answer=answer):
                authorized, reason = FIN.authorize(
                    answer, challenge,
                    current_fingerprint="b" * 64,
                    current_structure_fingerprint="c" * 64)
                self.assertFalse(authorized)
                self.assertEqual(reason, "not_close")

    def test_failed_remove_compares_execution_bytes_not_stale_warning_bytes(self) -> None:
        name = "semantic-execution-journal"
        _repo, wt = self.linked_fixture(name)
        hook_state = Path(wt, ".cursor/hooks/state/continual-learning.json")
        hook_state.parent.mkdir(parents=True)
        hook_state.write_text('{"turnsSinceLastRun":2}\n', encoding="utf-8")
        target = FIN.resolve_target(root=wt)
        preview = FIN.preview(
            **target, session_id="session", conversation_id=name)
        self.assertTrue(preview["ok"], preview)
        hook_state.write_text('{"turnsSinceLastRun":3}\n', encoding="utf-8")
        real_admin = FIN._run_git_admin

        def intercept(common_dir, *args, **kwargs):
            if len(args) >= 2 and args[0:2] == ("worktree", "remove"):
                return subprocess.CompletedProcess(
                    args, 1, stdout="", stderr="intact failure")
            return real_admin(common_dir, *args, **kwargs)

        with mock.patch.object(FIN, "_run_git_admin", side_effect=intercept):
            result = FIN.finish_execute(
                **target, session_id="session", conversation_id=name, answer="Close")
        self.assertEqual(result["outcome"], "error", result)
        self.assertEqual(result["reason"], "worktree_remove_failed")
        self.assertTrue(Path(wt).exists())
        self.assertEqual(list(Path(FIN.finish_dir()).glob("removal-*.json")), [])

    def test_secret_and_ignored_gates_survive_unselected_content_drift(self) -> None:
        name = "semantic-secret-gate"
        repo = self.make_repo(name)
        Path(repo, ".gitignore").write_text(
            ".cursor/\n.env.production\n", encoding="utf-8")
        commit_all(repo, "ignore secret and hook state")
        wt = self.add_worktree(repo, f"cursor/worktree/{name}")
        hook_state = Path(wt, ".cursor/hooks/state/continual-learning.json")
        hook_state.parent.mkdir(parents=True)
        hook_state.write_text('{"turnsSinceLastRun":2}\n', encoding="utf-8")
        Path(wt, ".env.production").write_text(
            "TOKEN=not-a-real-secret\n", encoding="utf-8")
        self.start(wt, name)
        UX.handle_hook_payload(self.payload(
            wt, "Retain", name, event_id=f"{name}-retain-choice"))
        self.assertEqual(
            self.current(wt)["state"], "awaiting_retain_selection")
        dialogue = UX.read_dialogue(name)
        secret_row = next(
            number for number, row in enumerate(dialogue["visible"], 1)
            if row["path"] == ".env.production")
        selected = dialogue["visible"][secret_row - 1]
        self.assertEqual(selected["class"], "ignored")
        self.assertFalse(selected["commit_eligible"])
        self.assertEqual(selected["template_id"], "secret")
        hook_state.write_text('{"turnsSinceLastRun":3}\n', encoding="utf-8")
        with self.assertRaisesRegex(
                UX.FinishUXError, "^explicit_secret_confirmation_required$"):
            UX.complete_retain(name, [secret_row])
        self.assertEqual(UX.list_retained(), [])
        retained = UX.complete_retain(name, [secret_row], allow_secrets=True)
        self.assertTrue(retained["artifact"]["protected"], retained)
        self.assertTrue(retained["artifact"]["restore_proven"], retained)

    def test_cli_surfaces_live_drift_with_plain_recovery(self) -> None:
        output = io.StringIO()
        with mock.patch.object(
                UX, "complete_retain",
                side_effect=UX.FinishUXError("live_inventory_drift")), \
                contextlib.redirect_stdout(output):
            rc = UX.main([
                "retain", "--conversation-id", "semantic-cli-drift", "--rows", "1",
            ])
        self.assertEqual(rc, 1)
        result = json.loads(output.getvalue())
        self.assertEqual(result["reason"], "live_inventory_drift")
        self.assertEqual(result["recovery"], UX._DRIFT_RECOVERY)
        self.assertNotIn("operation_failed", json.dumps(result))


if __name__ == "__main__":
    import unittest

    unittest.main()
