"""Real Git-operation inventory and protected-state certification regressions."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest import mock

from consumer import finish_current as UX
from .helpers import commit_all, git
from .test_finish_kernel import FIN, FinishBase


class GitOperationInventoryTest(FinishBase):
    def operation_repo(
            self, name: str, *, object_format: str = "sha1",
            ref_format: str | None = None) -> tuple[str, str, str]:
        repo = str(Path(self._tmp.name) / name)
        Path(repo).mkdir()
        command = ["git", "-C", repo, "init", "-q", "-b", "main"]
        if object_format != "sha1":
            command.append("--object-format=" + object_format)
        if ref_format is not None:
            command.append("--ref-format=" + ref_format)
        initialized = subprocess.run(command, capture_output=True, text=True)
        if initialized.returncode != 0:
            self.skipTest(
                f"Git does not support {object_format}/{ref_format or 'files'}")
        git(
            repo,
            "config",
            "user.email",
            "49759187+KleinPerkins@users.noreply.github.com",
        )
        git(repo, "config", "user.name", "KleinPerkins")
        Path(repo, "file.txt").write_text("base\n", encoding="utf-8")
        commit_all(repo, "base")
        wt = repo + ".wt"
        branch = "cursor/worktree/" + name
        git(repo, "worktree", "add", "-q", "-b", branch, wt, "main")
        return repo, wt, branch

    def merge_conflict(
            self, name: str, *, object_format: str = "sha1",
            ref_format: str | None = None) -> tuple[str, str, dict]:
        repo, wt, branch = self.operation_repo(
            name, object_format=object_format, ref_format=ref_format)
        git(repo, "checkout", "-q", "-b", name + "-side", "main")
        Path(repo, "file.txt").write_text("side\n", encoding="utf-8")
        commit_all(repo, "side")
        git(repo, "checkout", "-q", "main")
        Path(wt, "file.txt").write_text("work\n", encoding="utf-8")
        commit_all(wt, "work")
        merged = git(wt, "merge", name + "-side", check=False)
        self.assertNotEqual(merged.returncode, 0)
        target = self.targets(wt)
        self.assertEqual(target["branch"], branch)
        return repo, wt, target

    def inventory(self, wt: str, target: dict) -> dict:
        inventory = FIN.build_inventory(wt, target["git_dir"])
        self.assertTrue(inventory["safe"], inventory)
        return inventory

    def retain_operation(self, wt: str, conversation_id: str) -> dict:
        target = UX.resolve_linked_root({"cwd": wt})
        FIN._roots_module().write_current_session(
            wt, session_id=conversation_id, conversation_id=conversation_id,
            branch=target["branch"], common_dir=target["common_dir"])
        payload = {
            "hook_event_name": "beforeSubmitPrompt",
            "prompt": "I'm done",
            "conversation_id": conversation_id,
            "session_id": conversation_id,
            "cwd": wt,
            "workspace_roots": [wt],
        }
        preview = UX.preview_payload(payload)
        self.assertFalse(preview["continue"], preview)
        UX.dispatch_choice(conversation_id, "Retain")
        dialogue = UX.read_dialogue(conversation_id)
        operation_rows = [
            index for index, entry in enumerate(dialogue["visible"], 1)
            if entry["class"] == "operation"
        ]
        self.assertEqual(len(operation_rows), 1)
        result = UX.create_retain(conversation_id, operation_rows)
        manifest = UX._manifest(UX._artifact_path(result["artifact_id"]))
        self.assertTrue(manifest["restore_proven"])
        self.assertTrue(manifest["operation_abort_proven"])
        return manifest

    def test_restore_git_anchors_porcelain_at_restored_worktree(self) -> None:
        destination = Path(self._tmp.name) / "restored"
        (destination / ".git").mkdir(parents=True)
        completed = subprocess.CompletedProcess(["git"], 0, b"", b"")
        with mock.patch.object(UX.subprocess, "run", return_value=completed) as run:
            UX._restore_git(destination, "status")
        self.assertEqual(run.call_args.kwargs["cwd"], destination)

    def test_merge_manifest_binds_admin_content_raw_index_and_safe_row(self) -> None:
        _repo, wt, target = self.merge_conflict("operation-merge")
        first = self.inventory(wt, target)
        operation = first["operation_manifest"]
        self.assertEqual(operation["groups"], ["merge"])
        self.assertTrue(operation["admin_records"])
        self.assertTrue(operation["refs"])
        self.assertTrue(operation["index_entries"])
        self.assertTrue(operation["object_closure"])
        row = next(item for item in first["entries"] if item["class"] == "operation")
        self.assertFalse(row["commit_eligible"])
        self.assertTrue(row["retain_eligible"])
        rendered = FIN.render_rows({"entries": [row]})
        self.assertNotIn(operation["head_oid"], rendered)
        self.assertNotIn("MERGE_", rendered)

        merge_message = Path(target["git_dir"], "MERGE_MSG")
        original_message = merge_message.read_bytes()
        merge_message.write_bytes(original_message + b"\ncontent-only drift\n")
        second = self.inventory(wt, target)
        self.assertNotEqual(
            operation["digest"], second["operation_manifest"]["digest"])
        merge_message.write_bytes(original_message)

        before_index = self.inventory(wt, target)["operation_manifest"]
        git(wt, "update-index", "--index-version=4")
        after_index = self.inventory(wt, target)["operation_manifest"]
        self.assertEqual(
            before_index["index_entries"], after_index["index_entries"])
        self.assertNotEqual(before_index["raw_index"], after_index["raw_index"])
        self.assertNotEqual(before_index["digest"], after_index["digest"])

    def test_multi_cherry_pick_and_revert_are_real_sequence_state(self) -> None:
        for kind in ("cherry-pick", "revert"):
            with self.subTest(kind=kind):
                repo, wt, _branch = self.operation_repo("operation-" + kind)
                if kind == "cherry-pick":
                    git(repo, "checkout", "-q", "-b", "topic", "main")
                    Path(repo, "file.txt").write_text("topic\n", encoding="utf-8")
                    commit_all(repo, "topic conflict")
                    first = git(repo, "rev-parse", "HEAD").stdout.strip()
                    Path(repo, "second.txt").write_text("second\n", encoding="utf-8")
                    commit_all(repo, "topic second")
                    second = git(repo, "rev-parse", "HEAD").stdout.strip()
                    Path(wt, "file.txt").write_text("work\n", encoding="utf-8")
                    commit_all(wt, "work conflict")
                    result = git(wt, "cherry-pick", first, second, check=False)
                else:
                    Path(wt, "file.txt").write_text("one\n", encoding="utf-8")
                    commit_all(wt, "one")
                    first = git(wt, "rev-parse", "HEAD").stdout.strip()
                    Path(wt, "second.txt").write_text("two\n", encoding="utf-8")
                    commit_all(wt, "two")
                    second = git(wt, "rev-parse", "HEAD").stdout.strip()
                    Path(wt, "file.txt").write_text("later\n", encoding="utf-8")
                    commit_all(wt, "later conflict")
                    result = git(wt, "revert", first, second, check=False)
                self.assertNotEqual(result.returncode, 0)
                operation = self.inventory(
                    wt, self.targets(wt))["operation_manifest"]
                self.assertEqual(operation["groups"], ["sequence"])
                self.assertTrue(any(
                    bytes.fromhex(item["path_hex"]).startswith(b"sequencer/")
                    for item in operation["admin_records"]))

    def test_rebase_merge_apply_and_am_backends(self) -> None:
        for backend in ("merge", "apply", "am"):
            with self.subTest(backend=backend):
                repo, wt, _branch = self.operation_repo("operation-" + backend)
                git(repo, "checkout", "-q", "-b", backend + "-upstream", "main")
                Path(repo, "file.txt").write_text("upstream\n", encoding="utf-8")
                commit_all(repo, "upstream")
                Path(wt, "file.txt").write_text("local\n", encoding="utf-8")
                commit_all(wt, "local")
                if backend == "am":
                    patch = subprocess.run(
                        ["git", "-C", repo, "format-patch", "-1", "--stdout"],
                        capture_output=True, check=True).stdout
                    patch_path = Path(self._tmp.name, "operation.patch")
                    patch_path.write_bytes(patch)
                    result = git(wt, "am", str(patch_path), check=False)
                    expected = "am"
                else:
                    result = git(
                        wt, "rebase", "--" + backend, backend + "-upstream",
                        check=False)
                    expected = "rebase-" + backend
                self.assertNotEqual(result.returncode, 0)
                operation = self.inventory(
                    wt, self.targets(wt))["operation_manifest"]
                self.assertEqual(operation["groups"], [expected])
                self.assertTrue(operation["original_ref"].startswith("refs/heads/"))
                self.assertEqual(
                    FIN.resolve_target(wt)["branch"],
                    operation["original_ref"][len("refs/heads/"):])

    def test_bisect_checkout_and_no_checkout_use_logical_refs(self) -> None:
        for no_checkout in (False, True):
            with self.subTest(no_checkout=no_checkout):
                _repo, wt, branch = self.operation_repo(
                    "operation-bisect-" + ("no" if no_checkout else "yes"))
                good = git(wt, "rev-parse", "HEAD").stdout.strip()
                for value in ("one", "two", "three"):
                    Path(wt, "file.txt").write_text(value + "\n", encoding="utf-8")
                    commit_all(wt, value)
                bad = git(wt, "rev-parse", "HEAD").stdout.strip()
                args = ["bisect", "start"]
                if no_checkout:
                    args.append("--no-checkout")
                git(wt, *args, bad, good)
                operation = self.inventory(
                    wt, self.targets(wt))["operation_manifest"]
                self.assertEqual(operation["groups"], ["bisect"])
                self.assertTrue(any(
                    bytes.fromhex(item["name_hex"]).startswith(b"refs/bisect/")
                    for item in operation["refs"]))
                self.assertEqual(operation["original_ref"], "refs/heads/" + branch)
                self.assertEqual(FIN.resolve_target(wt)["branch"], branch)

    def test_notes_merge_conflict_is_canonical_operation(self) -> None:
        _repo, wt, _branch = self.operation_repo("operation-notes")
        target_oid = git(wt, "rev-parse", "HEAD").stdout.strip()
        git(wt, "notes", "--ref=left", "add", "-m", "base", target_oid)
        left = git(wt, "rev-parse", "refs/notes/left").stdout.strip()
        git(wt, "update-ref", "refs/notes/right", left)
        git(wt, "notes", "--ref=left", "add", "-f", "-m", "left", target_oid)
        git(wt, "notes", "--ref=right", "add", "-f", "-m", "right", target_oid)
        merged = git(wt, "notes", "--ref=left", "merge", "refs/notes/right", check=False)
        self.assertNotEqual(merged.returncode, 0)
        operation = self.inventory(wt, self.targets(wt))["operation_manifest"]
        self.assertEqual(operation["groups"], ["notes-merge"])
        self.assertTrue(any(
            item.get("kind") == "notes-target" for item in operation["refs"]))
        git(wt, "notes", "merge", "--abort")
        after_abort = self.inventory(wt, self.targets(wt))["operation_manifest"]
        self.assertFalse(after_abort["active"])

    def test_operation_admin_links_specials_mounts_and_drift_refuse(self) -> None:
        _repo, wt, target = self.merge_conflict("operation-admin-refusal")
        merge_message = Path(target["git_dir"], "MERGE_MSG")
        original = merge_message.read_bytes()
        merge_message.unlink()
        merge_message.symlink_to("MERGE_HEAD")
        linked = FIN.build_inventory(wt, target["git_dir"])
        self.assertFalse(linked["safe"])
        self.assertEqual(linked["refuse_reason"], "operation_admin_link")
        merge_message.unlink()
        merge_message.write_bytes(original)

        with mock.patch.object(
                FIN.os.path, "ismount",
                side_effect=lambda value: os.fsdecode(value).endswith("MERGE_MSG")):
            mounted = FIN.build_inventory(wt, target["git_dir"])
        self.assertFalse(mounted["safe"])
        self.assertEqual(mounted["refuse_reason"], "operation_mount_boundary")

        real_scan = FIN._scan_operation_admin
        changed = {"done": False}

        def drift(*args, **kwargs):
            result = real_scan(*args, **kwargs)
            if not changed["done"]:
                changed["done"] = True
                merge_message.write_bytes(original + b"\ndrift\n")
            return result

        with mock.patch.object(FIN, "_scan_operation_admin", side_effect=drift):
            drifted = FIN.build_inventory(wt, target["git_dir"])
        self.assertFalse(drifted["safe"])
        self.assertEqual(drifted["refuse_reason"], "operation_state_drift")

        _repo2, wt2, _branch2 = self.operation_repo("operation-admin-fifo")
        git(_repo2, "checkout", "-q", "-b", "fifo-topic", "main")
        Path(_repo2, "file.txt").write_text("topic\n", encoding="utf-8")
        commit_all(_repo2, "topic")
        topic = git(_repo2, "rev-parse", "HEAD").stdout.strip()
        Path(wt2, "file.txt").write_text("work\n", encoding="utf-8")
        commit_all(wt2, "work")
        git(wt2, "cherry-pick", topic, check=False)
        fifo_target = self.targets(wt2)
        sequencer = Path(fifo_target["git_dir"], "sequencer")
        sequencer.mkdir(exist_ok=True)
        os.mkfifo(sequencer / "unsafe")
        special = FIN.build_inventory(wt2, fifo_target["git_dir"])
        self.assertFalse(special["safe"])
        self.assertEqual(special["refuse_reason"], "operation_admin_special")

    def test_sha1_sha256_and_reftable_operation_manifests(self) -> None:
        for object_format in ("sha1", "sha256"):
            with self.subTest(object_format=object_format):
                _repo, wt, target = self.merge_conflict(
                    "operation-format-" + object_format,
                    object_format=object_format)
                operation = self.inventory(wt, target)["operation_manifest"]
                self.assertEqual(operation["object_format"], object_format)
                expected_length = 40 if object_format == "sha1" else 64
                self.assertTrue(all(
                    len(item["oid"]) == expected_length
                    for item in operation["object_closure"]))

        _repo, wt, target = self.merge_conflict(
            "operation-reftable", ref_format="reftable")
        operation = self.inventory(wt, target)["operation_manifest"]
        self.assertEqual(operation["groups"], ["merge"])
        self.assertTrue(operation["refs"])

    def test_each_operation_group_retain_restores_and_aborts_in_isolation(self) -> None:
        for group in (
                "sequence", "rebase-merge", "rebase-apply", "am",
                "bisect", "notes-merge"):
            with self.subTest(group=group):
                name = "retain-" + group
                repo, wt, _branch = self.operation_repo(name)
                if group == "sequence":
                    git(repo, "checkout", "-q", "-b", name + "-topic", "main")
                    Path(repo, "file.txt").write_text("topic\n", encoding="utf-8")
                    commit_all(repo, "topic")
                    topic = git(repo, "rev-parse", "HEAD").stdout.strip()
                    Path(wt, "file.txt").write_text("work\n", encoding="utf-8")
                    commit_all(wt, "work")
                    self.assertNotEqual(
                        git(wt, "cherry-pick", topic, check=False).returncode, 0)
                elif group.startswith("rebase-") or group == "am":
                    git(repo, "checkout", "-q", "-b", name + "-upstream", "main")
                    Path(repo, "file.txt").write_text("upstream\n", encoding="utf-8")
                    commit_all(repo, "upstream")
                    Path(wt, "file.txt").write_text("local\n", encoding="utf-8")
                    commit_all(wt, "local")
                    if group == "am":
                        patch = subprocess.run(
                            ["git", "-C", repo, "format-patch", "-1", "--stdout"],
                            capture_output=True, check=True).stdout
                        patch_path = Path(self._tmp.name, name + ".patch")
                        patch_path.write_bytes(patch)
                        result = git(wt, "am", str(patch_path), check=False)
                    else:
                        result = git(
                            wt, "rebase", "--" + group.removeprefix("rebase-"),
                            name + "-upstream", check=False)
                    self.assertNotEqual(result.returncode, 0)
                elif group == "bisect":
                    good = git(wt, "rev-parse", "HEAD").stdout.strip()
                    for value in ("one", "two", "three"):
                        Path(wt, "file.txt").write_text(value + "\n", encoding="utf-8")
                        commit_all(wt, value)
                    bad = git(wt, "rev-parse", "HEAD").stdout.strip()
                    git(wt, "bisect", "start", "--no-checkout", bad, good)
                else:
                    target_oid = git(wt, "rev-parse", "HEAD").stdout.strip()
                    git(wt, "notes", "--ref=left", "add", "-m", "base", target_oid)
                    left = git(wt, "rev-parse", "refs/notes/left").stdout.strip()
                    git(wt, "update-ref", "refs/notes/right", left)
                    git(wt, "notes", "--ref=left", "add", "-f", "-m", "left", target_oid)
                    git(wt, "notes", "--ref=right", "add", "-f", "-m", "right", target_oid)
                    self.assertNotEqual(
                        git(wt, "notes", "--ref=left", "merge",
                            "refs/notes/right", check=False).returncode, 0)
                proof_home = Path(self._tmp.name) / ("home-" + group)
                proof_home.mkdir()
                with mock.patch.dict(os.environ, {"HOME": str(proof_home)}):
                    manifest = self.retain_operation(wt, "retain-proof-" + group)
                self.assertEqual(
                    manifest["operation_state"]["selected_groups"], [group])

    def test_operation_discard_count_requires_exact_close(self) -> None:
        _repo, wt, target = self.merge_conflict("operation-close")
        inventory = self.inventory(wt, target)
        preview = self.preview(wt, conv="operation-close")
        self.assertEqual(
            preview["discard_count"], len(inventory["entries"]))
        self.assertEqual(
            len([entry for entry in inventory["entries"]
                 if entry["class"] == "operation"]), 1)
        self.assertEqual(
            len([entry for entry in preview["visible"]
                 if entry["class"] == "operation"]), 1)

        rejected, rejected_proc = self.execute(
            wt, "close", conv="operation-close")
        self.assertNotEqual(rejected_proc.returncode, 0)
        self.assertEqual(rejected["outcome"], "refused")
        self.assertTrue(Path(wt).is_dir())

        removed, removed_proc = self.execute(
            wt, "Close", conv="operation-close")
        self.assertEqual(removed_proc.returncode, 0, removed_proc.stderr)
        self.assertEqual(removed["outcome"], "removed", removed)
        self.assertFalse(Path(wt).exists())

    def test_foreign_top_level_lock_ignored_but_genuine_git_lock_still_blocks(self) -> None:
        # Live-Desktop-UAT regression. A Cursor Agent-window worktree under ~/dev governance
        # carries a FOREIGN host session lock (``cursor-session.lock``, written by the ~/dev
        # one-writer ``session-lock`` hook) in its per-worktree git_dir for the whole session.
        # It shares the ``.lock`` suffix but is a PID marker, not a git artifact. Before the fix
        # ``_operation_top_presence`` flagged ANY top-level ``*.lock`` as a live git operation, so
        # with no git operation in progress the finish hook failed open (no warning rendered) and a
        # genuine Close was refused (``operation_live_lock`` -> inventory ``safe=False``). Foreign
        # non-git locks must be IGNORED; genuine top-level git locks must STILL block.
        _repo, wt, _branch = self.operation_repo("operation-foreign-lock")
        git_dir = os.path.abspath(self.targets(wt)["git_dir"])

        foreign = [Path(git_dir, "cursor-session.lock"), Path(git_dir, "zzz-foreign.lock")]
        # Mirror the real host marker content (token=pid:.. / pid=.. / tool=); the stem matches no
        # git top-level lockable and no top-level object named ``cursor-session`` exists.
        foreign[0].write_text(
            "token=pid:4242\npid=4242\ntty=?\nts=0\nhost=x\ntool=\n", encoding="utf-8")
        foreign[1].write_text("arbitrary non-git lock\n", encoding="utf-8")

        # Direction A — foreign locks alone: MUST NOT raise, MUST leave the inventory safe.
        presence = FIN._operation_top_presence(git_dir)  # returns normally (no raise)
        self.assertIsInstance(presence, dict)
        clean = FIN.build_inventory(wt, git_dir)
        self.assertTrue(clean["safe"], clean)
        self.assertEqual(clean["refuse_reason"], "")
        self.assertEqual(
            [entry for entry in clean["entries"] if entry["class"] == "operation"], [])

        # Direction B — each genuine top-level git lock STILL blocks, even while the foreign locks
        # remain present (index.lock/HEAD.lock also exercise the "locks an existing object" path;
        # packed-refs.lock exercises the git-lockable-stem allow-list path with no matching file).
        for stem in ("index", "HEAD", "packed-refs"):
            with self.subTest(stem=stem):
                lock = Path(git_dir, stem + ".lock")
                lock.write_bytes(b"")
                try:
                    with self.assertRaises(FIN.FinishError) as caught:
                        FIN._operation_top_presence(git_dir)
                    self.assertEqual(str(caught.exception), "operation_live_lock")
                    blocked = FIN.build_inventory(wt, git_dir)
                    self.assertFalse(blocked["safe"], blocked)
                    self.assertEqual(blocked["refuse_reason"], "operation_live_lock")
                finally:
                    lock.unlink()

        # With the genuine locks gone the still-present foreign locks keep the tree safe — proving
        # the block came from the real git lock, not the coexisting foreign session marker.
        restored = FIN.build_inventory(wt, git_dir)
        self.assertTrue(restored["safe"], restored)
        for path in foreign:
            self.assertTrue(path.exists(), path)


if __name__ == "__main__":
    import unittest
    unittest.main()
