"""Final Phase-2 blockers: durable Retain publication and total public projection."""

from __future__ import annotations

import ast
import contextlib
import hashlib
import inspect
import io
import json
import os
from pathlib import Path
import subprocess
import textwrap
from unittest import mock

from consumer import egress
from consumer import finish_current as UX
from .test_finish_final_hardening import FinalHardeningBase, FIN


class RetainTrustLatchTest(FinalHardeningBase):
    def _retained(self, wt: str, source: Path) -> bool:
        target = FIN.resolve_target(wt)
        rel = str(source.relative_to(wt))
        row = next(
            item for item in FIN.build_inventory(wt, target["git_dir"])["entries"]
            if item["path"] == rel)
        return bool(row.get("retained"))

    def test_committed_marker_binds_exact_true_manifest_and_suppression(self) -> None:
        wt, source, indices = self.retain_ready("retain-committed-marker")
        created = UX.create_retain("retain-committed-marker", indices)
        artifact_id = created["artifact_id"]
        artifact = UX._artifact_path(artifact_id)
        pending, committed, _rollback = UX._publication_paths(artifact_id)
        manifest_data = (artifact / "manifest.json").read_bytes()
        marker = json.loads(committed.read_text(encoding="utf-8"))
        self.assertFalse(pending.exists())
        self.assertEqual(marker, {
            "schema": UX.RETAIN_PUBLICATION_SCHEMA,
            "artifact_id": artifact_id,
            "manifest_sha256": hashlib.sha256(manifest_data).hexdigest(),
        })
        self.assertEqual(marker["manifest_sha256"], hashlib.sha256(manifest_data).hexdigest())
        self.assertEqual(artifact.stat().st_mode & 0o777, 0o700)
        self.assertEqual(committed.stat().st_mode & 0o777, 0o600)
        self.assertTrue(self._retained(wt, source))

    def test_post_manifest_replace_pre_parent_sync_is_never_published(self) -> None:
        wt, source, indices = self.retain_ready("retain-manifest-parent-sync")
        real_replace = os.replace
        real_sync = UX._sync_dir
        true_manifest_replaced = False

        def replace(source_path, destination_path):
            nonlocal true_manifest_replaced
            result = real_replace(source_path, destination_path)
            destination = Path(destination_path)
            if (destination.name == "manifest.json"
                    and destination.parent.name.endswith(".staging")):
                doc = json.loads(destination.read_text(encoding="utf-8"))
                true_manifest_replaced = doc.get("restore_proven") is True
            return result

        def sync(path):
            if true_manifest_replaced and Path(path).name.endswith(".staging"):
                raise OSError("private parent sync fault")
            return real_sync(path)

        with mock.patch.object(os, "replace", side_effect=replace), \
                mock.patch.object(UX, "_sync_dir", side_effect=sync), \
                self.assertRaises(OSError):
            UX.create_retain("retain-manifest-parent-sync", indices)
        self.assertTrue(source.exists())
        self.assertEqual(UX.list_retained(), [])
        self.assertFalse(self._retained(wt, source))

    def test_precommit_failure_preserves_every_durable_candidate(self) -> None:
        wt, source, indices = self.retain_ready("retain-rollback-sync")
        root = UX._retain_dir()
        real_sync = UX._sync_dir

        def sync(path):
            if Path(path) == root:
                names = {item.name for item in root.iterdir()}
                if (any(name.startswith("retain-") for name in names)
                        or any(name.endswith(".publication-tombstone") for name in names)):
                    raise OSError("private rollback sync fault")
            return real_sync(path)

        with mock.patch.object(UX, "_sync_dir", side_effect=sync), \
                self.assertRaises(OSError):
            UX.create_retain("retain-rollback-sync", indices)
        self.assertTrue(source.exists())
        self.assertTrue(any(
            item.name.startswith("retain-") or item.name.endswith(".staging")
            for item in root.iterdir()))
        payload_candidates = [
            item for item in root.iterdir()
            if item.name.startswith("retain-") or item.name.endswith(".staging")
        ]
        warnings = UX._resume_retain_publications()
        self.assertTrue(warnings or UX.list_retained())
        self.assertTrue(all(item.exists() for item in payload_candidates))

    def test_crash_immediately_before_and_after_commit_marker_is_truthful(self) -> None:
        class Crash(BaseException):
            pass

        for point in ("before", "after"):
            with self.subTest(point=point):
                name = "retain-marker-crash-" + point
                wt, source, indices = self.retain_ready(name)
                real_write = UX._private_write

                def write(destination_path, data):
                    destination_value = Path(destination_path)
                    is_commit = destination_value.name.endswith(
                        ".publication.committed.json")
                    if is_commit and point == "before":
                        raise Crash()
                    result = real_write(destination_path, data)
                    if is_commit and point == "after":
                        raise Crash()
                    return result

                with mock.patch.object(UX, "_private_write", side_effect=write), \
                        self.assertRaises(Crash):
                    UX.create_retain(name, indices)
                finals = []
                for item in UX._retain_dir().iterdir():
                    if not item.name.startswith("retain-") or not item.is_dir():
                        continue
                    doc = UX._manifest(
                        item, require_proven=True,
                        expected_artifact_id=item.name, allow_uncommitted=True)
                    if doc.get("source") == os.path.realpath(wt):
                        finals.append(item)
                self.assertEqual(len(finals), 1)
                artifact_id = finals[0].name
                listed = {item["artifact_id"] for item in UX.list_retained()}
                self.assertIn(artifact_id, listed)
                self.assertTrue(self._retained(wt, source))
                UX.delete_retain(artifact_id, artifact_id)

    def test_post_commit_sync_failure_returns_latched_success_with_bounded_warning(self) -> None:
        wt, source, indices = self.retain_ready("retain-post-commit-sync")
        root = UX._retain_dir()
        real_sync = UX._sync_dir

        def sync(path):
            if (Path(path) == root
                    and any(item.name.endswith(".publication.committed.json")
                            for item in root.iterdir())):
                raise OSError("private post-commit sync fault")
            return real_sync(path)

        with mock.patch.object(UX, "_sync_dir", side_effect=sync):
            created = UX.create_retain("retain-post-commit-sync", indices)
        self.assertTrue(created["ok"])
        self.assertEqual(
            created["cleanup_warnings"], ["publication_post_commit_incomplete"])
        self.assertIn(
            created["artifact_id"],
            {item["artifact_id"] for item in UX.list_retained()})
        self.assertTrue(self._retained(wt, source))

    def test_exception_after_commit_marker_write_returns_latched_success(self) -> None:
        wt, source, indices = self.retain_ready("retain-post-marker-rename")
        real_write = UX._private_write

        def write(destination_path, data):
            destination_value = Path(destination_path)
            value = real_write(destination_path, data)
            if destination_value.name.endswith(".publication.committed.json"):
                raise OSError("private post-marker fault")
            return value

        with mock.patch.object(UX, "_private_write", side_effect=write):
            created = UX.create_retain("retain-post-marker-rename", indices)
        self.assertTrue(created["ok"])
        self.assertEqual(
            created["cleanup_warnings"], ["publication_post_commit_incomplete"])
        self.assertIn(
            created["artifact_id"],
            {item["artifact_id"] for item in UX.list_retained()})
        self.assertTrue(self._retained(wt, source))

    def test_digest_mismatch_rejects_list_restore_and_suppression(self) -> None:
        wt, source, indices = self.retain_ready("retain-digest-mismatch")
        created = UX.create_retain("retain-digest-mismatch", indices)
        artifact_id = created["artifact_id"]
        artifact = UX._artifact_path(artifact_id)
        manifest = artifact / "manifest.json"
        UX._private_write(manifest, manifest.read_bytes() + b" ")
        self.assertNotIn(
            artifact_id, {item["artifact_id"] for item in UX.list_retained()})
        with self.assertRaises(UX.FinishUXError):
            UX.restore_retain(
                artifact_id, str(self.data_home / "digest-mismatch-restore"))
        self.assertFalse(self._retained(wt, source))
        self.assertTrue(UX.delete_retain(artifact_id, artifact_id)["ok"])

    def test_markerless_legacy_remains_restorable_and_deletable_but_never_suppresses(self) -> None:
        wt, source, indices = self.retain_ready("retain-legacy-unlatched")
        created = UX.create_retain("retain-legacy-unlatched", indices)
        artifact_id = created["artifact_id"]
        artifact = UX._artifact_path(artifact_id)
        manifest = artifact / "manifest.json"
        doc = json.loads(manifest.read_text(encoding="utf-8"))
        doc.pop("publication_protocol")
        UX._private_write(
            manifest, (json.dumps(doc, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        pending, committed, _rollback = UX._publication_paths(artifact_id)
        pending.unlink(missing_ok=True)
        committed.unlink()
        UX._sync_dir(UX._retain_dir())
        listed = next(
            item for item in UX.list_retained()
            if item["artifact_id"] == artifact_id)
        self.assertEqual(listed["publication_status"], "legacy_unlatched")
        destination = self.data_home / "legacy-unlatched-restore"
        UX.restore_retain(artifact_id, str(destination))
        self.assertEqual((destination / "draft.txt").read_text(), source.read_text())
        self.assertFalse(self._retained(wt, source))
        self.assertTrue(UX.delete_retain(artifact_id, artifact_id)["ok"])


class DispatcherProjectionTest(FinalHardeningBase):
    SECRET_CORPUS = (
        "/private/state/finish.lock",
        "f" * 64,
        "private prompt bytes",
        "hostile child output",
        "hostile child error",
    )

    def _ready(self, name: str) -> str:
        _repo, wt = self.linked(name)
        Path(wt, "draft.txt").write_text("keep\n", encoding="utf-8")
        UX.preview_payload(self.payload(wt, name))
        return wt

    def _assert_no_leak(self, result: dict) -> None:
        rendered = json.dumps(result, sort_keys=True)
        for secret in self.SECRET_CORPUS:
            self.assertNotIn(secret, rendered)
        self.assertEqual(egress.scan_object(result), [])

    def _hostile(self, outcome: str, *, branch_action: object = "deleted") -> dict:
        return {
            "outcome": outcome,
            "reason": self.SECRET_CORPUS[0],
            "message": self.SECRET_CORPUS[2],
            "stdout": self.SECRET_CORPUS[3],
            "stderr": self.SECRET_CORPUS[4],
            "branch_action": branch_action,
            "branch_reason": self.SECRET_CORPUS[0],
            "head_oid": self.SECRET_CORPUS[1],
            "operation_id": self.SECRET_CORPUS[1],
            "state_cleanup_warnings": [
                {"path": self.SECRET_CORPUS[0]}, self.SECRET_CORPUS[2],
            ],
            "extra": {"prompt": self.SECRET_CORPUS[2]},
        }

    def test_dispatch_surfaces_have_no_direct_dictionary_return(self) -> None:
        surfaces = (
            UX._choice_rejection,
            UX._removed_dispatch_result,
            UX.dispatch_choice,
            UX._recover_current_removal,
            UX.dispatch_current,
        )
        for surface in surfaces:
            with self.subTest(surface=surface.__name__):
                tree = ast.parse(textwrap.dedent(inspect.getsource(surface)))
                direct = [
                    node.lineno for node in ast.walk(tree)
                    if isinstance(node, ast.Return)
                    and isinstance(node.value, ast.Dict)
                ]
                self.assertEqual(direct, [], "public dictionaries must come from the builder")

    def test_shell_projection_parser_rejects_extras_invalid_values_and_hostile_bytes(self) -> None:
        self.assertEqual(
            UX._parse_shell_public_projection(
                '{"outcome":"removed","reason":"finish_removed",'
                '"branch_action":"deleted"}'),
            (
                UX.PublicDispatchOutcome.REMOVED,
                UX.PublicDispatchReason.FINISH_REMOVED,
                UX.PublicBranchResult.DELETED,
            ))
        hostile = (
            '{"outcome":"refused","reason":"workspace_preserved",'
            f'"extra":"{self.SECRET_CORPUS[0]}"}}'
        )
        self.assertIsNone(UX._parse_shell_public_projection(hostile))
        self.assertIsNone(UX._parse_shell_public_projection(
            '{"outcome":"removed","reason":"finish_removed",'
            '"branch_action":"delete_error"}'))
        self.assertIsNone(UX._parse_shell_public_projection("\udcff"))

    def test_hostile_removed_refused_uncertain_and_branch_fallback_are_total(self) -> None:
        cases = (
            ("projection-removed", self._hostile("removed"), True, "deleted"),
            ("projection-refused", self._hostile("refused"), False, None),
            ("projection-error", self._hostile("error"), False, None),
            ("projection-uncertain", self._hostile("uncertain"), None, None),
            ("projection-branch-fallback",
             self._hostile("removed", branch_action={"path": "/private/bad"}),
             None, None),
        )
        for name, child, removed, branch_action in cases:
            with self.subTest(name=name):
                self._ready(name)
                result = UX.dispatch_choice(
                    name, "Close", executor=lambda **_kwargs: child)
                self.assertIs(result["workspace_removed"], removed)
                if removed is None or removed is True:
                    self.assertTrue(result["agent_stopping"])
                    self.assertTrue(result["chat_remains_open"])
                if branch_action is not None:
                    self.assertEqual(result["branch_action"], branch_action)
                self._assert_no_leak(result)

    def test_correction_cancel_cleanup_and_selection_faults_use_the_builder(self) -> None:
        correction_name = "projection-correction"
        correction_wt = self._ready(correction_name)
        correction = UX.dispatch_choice(correction_name, " close ")
        self.assertEqual(correction["reason"], "close_must_be_exact")
        self.assertFalse(correction["mutated_repo"])
        self.assertTrue(Path(correction_wt).exists())
        self._assert_no_leak(correction)

        cancel_name = "projection-cancel"
        cancel_wt = self._ready(cancel_name)
        with mock.patch.object(
                UX, "_cleanup_terminal_projections",
                side_effect=RuntimeError(self.SECRET_CORPUS[0])):
            cancelled = UX.dispatch_choice(cancel_name, "Cancel")
        self.assertEqual(cancelled["reason"], "cancel_cleanup_incomplete")
        self.assertTrue(cancelled["authority_inert"])
        self.assertFalse(cancelled["mutated_repo"])
        self.assertTrue(Path(cancel_wt).exists())
        self._assert_no_leak(cancelled)

        selection_name = "projection-selection-fault"
        selection_wt = self._ready(selection_name)
        with mock.patch.object(
                UX, "write_dialogue",
                side_effect=RuntimeError(self.SECRET_CORPUS[0])):
            selection = UX.dispatch_choice(selection_name, "Retain")
        self.assertEqual(selection["reason"], "operation_failed")
        self.assertFalse(selection["workspace_removed"])
        self.assertTrue(Path(selection_wt).exists())
        self._assert_no_leak(selection)

    def test_executor_exception_is_unknown_and_stops_without_exception_text(self) -> None:
        name = "projection-exception"
        self._ready(name)

        def fail(**_kwargs):
            raise RuntimeError(self.SECRET_CORPUS[0])

        result = UX.dispatch_choice(name, "Close", executor=fail)
        self.assertIsNone(result["workspace_removed"])
        self.assertTrue(result["agent_stopping"])
        self._assert_no_leak(result)

    def test_hostile_shell_json_extra_is_unknown_and_never_returned(self) -> None:
        name = "projection-hostile-shell-json"
        wt = self._ready(name)
        real_run = UX.subprocess.run
        seen_machine_mode = False

        def run(command, *args, **kwargs):
            nonlocal seen_machine_mode
            if (isinstance(command, list) and command
                    and str(command[0]).endswith("kernel/bin/dev-worktree.sh")):
                seen_machine_mode = (
                    kwargs.get("env", {}).get("AWA_FINISH_PUBLIC_PROJECTION") == "1")
                return subprocess.CompletedProcess(
                    command, 1,
                    stdout=(
                        '{"outcome":"refused","reason":"workspace_preserved",'
                        f'"extra":"{self.SECRET_CORPUS[0]}"}}\n'
                    ),
                    stderr=self.SECRET_CORPUS[4])
            return real_run(command, *args, **kwargs)

        with mock.patch.object(UX.subprocess, "run", side_effect=run):
            result = UX.dispatch_choice(name, "Close")
        self.assertTrue(seen_machine_mode)
        self.assertIsNone(result["workspace_removed"])
        self.assertTrue(result["agent_stopping"])
        self.assertTrue(Path(wt).exists())
        self._assert_no_leak(result)

    def test_real_shell_projection_reports_removed_and_proven_refusal(self) -> None:
        removed_name = "projection-real-shell-removed"
        removed_wt = self._ready(removed_name)
        removed = UX.dispatch_choice(removed_name, "Close")
        self.assertTrue(removed["workspace_removed"], removed)
        self.assertTrue(removed["agent_stopping"])
        self.assertFalse(Path(removed_wt).exists())
        self._assert_no_leak(removed)

        hook_name = "projection-real-shell-hook-removed"
        _repo, hook_wt = self.linked(hook_name)
        Path(hook_wt, "draft.txt").write_text("keep\n", encoding="utf-8")
        hook_payload = self.payload(hook_wt, hook_name)
        UX.handle_hook_payload(hook_payload)
        self.assertTrue(UX.mark_hook_published(hook_payload))
        UX.handle_hook_payload({
            **hook_payload, "prompt": "Close",
            "event_id": "projection-real-shell-hook-close",
        })
        hook_removed = UX.dispatch_choice(hook_name)
        self.assertTrue(hook_removed["workspace_removed"], hook_removed)
        self.assertTrue(hook_removed["agent_stopping"])
        self.assertFalse(Path(hook_wt).exists())
        self._assert_no_leak(hook_removed)

        refused_name = "projection-real-shell-refused"
        refused_wt = self._ready(refused_name)
        install_id = Path(FIN.awa_state_dir()) / "install-id"
        install_id.write_text("inst-replaced-after-preview\n", encoding="ascii")
        os.chmod(install_id, 0o600)
        refused = UX.dispatch_choice(refused_name, "Close")
        self.assertFalse(refused["workspace_removed"])
        self.assertFalse(refused["ok"])
        self.assertTrue(Path(refused_wt).exists())
        self._assert_no_leak(refused)

    def test_real_lock_contention_is_fixed_and_consumes_one_use_close(self) -> None:
        name = "projection-real-lock"
        _repo, wt = self.linked(name)
        Path(wt, "draft.txt").write_text("keep\n", encoding="utf-8")
        payload = self.payload(wt, name)
        UX.handle_hook_payload(payload)
        self.assertTrue(UX.mark_hook_published(payload))
        UX.handle_hook_payload({
            **payload, "prompt": "Close", "event_id": "projection-real-lock-close",
        })
        dialogue = UX.read_dialogue(name)
        fin = UX._load_finish()

        def execute(**kwargs):
            with fin.common_dir_lock(
                    dialogue["target"]["common_dir"], blocking=True, timeout=1.0):
                return fin.finish_execute(
                    **dialogue["target"], session_id=kwargs["session_id"],
                    conversation_id=kwargs["conversation_id"],
                    answer=kwargs["authorization"],
                    expected_nonce=kwargs["expected_nonce"],
                    expected_generation=kwargs["expected_generation"],
                    lock_timeout=0.01)

        result = UX.dispatch_choice(name, executor=execute)
        self.assertFalse(result["workspace_removed"])
        self.assertEqual(result["outcome"]["reason"], "lock_busy")
        self.assertEqual(
            fin.generation_state_status(
                name, dialogue["nonce"], dialogue["generation"]),
            "consumed")
        self.assertTrue(Path(wt).exists())
        self._assert_no_leak(result)

    def test_cli_json_and_exception_handling_never_echo_private_text(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rc = UX.main([
                "dispatch", "--conversation-id", "missing-public-dialogue",
            ])
        self.assertEqual(rc, 0)
        result = json.loads(output.getvalue())
        self.assertFalse(result["workspace_removed"])
        self._assert_no_leak(result)

        output = io.StringIO()
        with mock.patch.object(
                UX, "dispatch_choice",
                side_effect=UX.FinishUXError(self.SECRET_CORPUS[0])), \
                contextlib.redirect_stdout(output):
            rc = UX.main([
                "dispatch", "--conversation-id", "hostile-public-dialogue",
            ])
        self.assertEqual(rc, 1)
        result = json.loads(output.getvalue())
        self.assertEqual(result["reason"], "operation_failed")
        self._assert_no_leak(result)

    def test_kernel_cli_exception_classes_use_fixed_messages(self) -> None:
        cases = (
            FIN.LockBusy(self.SECRET_CORPUS[0]),
            FIN.FinishError(self.SECRET_CORPUS[0]),
            RuntimeError(self.SECRET_CORPUS[0]),
        )
        for exception in cases:
            with self.subTest(exception=exception.__class__.__name__):
                output = io.StringIO()
                with mock.patch.object(FIN, "resolve_target", side_effect=exception), \
                        contextlib.redirect_stdout(output):
                    rc = FIN.main(["resolve-target", "--root", "/private/hostile-root"])
                self.assertEqual(rc, 1)
                result = json.loads(output.getvalue())
                self.assertNotIn(self.SECRET_CORPUS[0], json.dumps(result))
                self.assertIn(
                    result["message"],
                    {
                        "another local action is in progress",
                        "finish could not be completed safely",
                    })

    def test_post_removal_lockbusy_cannot_reverse_the_removed_latch(self) -> None:
        name = "projection-post-remove-lockbusy"
        wt = self._ready(name)
        dialogue = UX.read_dialogue(name)
        with mock.patch.object(
                FIN, "_reconcile_removal_journal_locked",
                side_effect=FIN.LockBusy(self.SECRET_CORPUS[0])):
            outcome = FIN.finish_execute(
                **dialogue["target"], session_id=dialogue["session_id"],
                conversation_id=name, answer="Close")
        self.assertEqual(outcome["outcome"], "removed")
        self.assertFalse(Path(wt).exists())
        public = UX._build_public_dispatch(
            UX.PublicDispatchOutcome.REMOVED,
            reason=UX.PublicDispatchReason.FINISH_REMOVED,
            kernel_outcome=outcome)
        self.assertTrue(public["workspace_removed"])
        self.assertTrue(public["agent_stopping"])
        self._assert_no_leak(public)


if __name__ == "__main__":
    import unittest
    unittest.main()
