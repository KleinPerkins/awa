"""Release-blocking finish preflight coverage for hidden Git index state."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
from pathlib import Path
from unittest import mock

from consumer import finish_current as UX
from .helpers import commit_all, git
from .test_finish_kernel import FIN, FinishBase


GENERIC_REASON = "index_visibility_flags"


class FinishIndexVisibilityTest(FinishBase):
    def _flagged(self, name: str, flag: str, *, modified: bool) -> tuple[str, dict]:
        _, wt, _ = self.ephemeral_wt(name)
        tracked = Path(wt, "README.md")
        git(wt, "update-index", flag, "README.md")
        if modified:
            tracked.write_text("private modified bytes\n", encoding="utf-8")
        return wt, self.targets(wt)

    def _assert_generic_refusal(self, wt: str, target: dict) -> dict:
        inventory = FIN.build_inventory(wt, target["git_dir"])
        self.assertFalse(inventory["safe"], inventory)
        self.assertEqual(inventory["refuse_reason"], GENERIC_REASON)
        self.assertEqual(inventory["entries"], [])
        self.assertEqual(inventory["objects"], [])
        self.assertEqual(inventory["status_hex"], "")
        self.assertEqual(inventory["index_hex"], "")
        return inventory

    def _script(self, name: str, body: str) -> Path:
        script = self.data_home / name
        script.write_text("#!/bin/sh\nset -eu\n" + body, encoding="utf-8")
        script.chmod(0o755)
        return script

    def _format_worktree(self, name: str, object_format: str) -> tuple[str, dict]:
        repo = str(Path(self._tmp.name) / (name + "-repo"))
        created = subprocess.run(
            ["git", "init", "-q", f"--object-format={object_format}", repo],
            capture_output=True, text=True)
        if created.returncode != 0:
            if object_format == "sha256":
                self.skipTest("installed Git does not support SHA-256 repositories")
            self.fail(created.stderr)
        Path(repo, "README.md").write_text("# base\n", encoding="utf-8")
        commit_all(repo, "init")
        git(repo, "branch", "-M", "main")
        wt = self.add_worktree(repo, f"cursor/worktree/{name}")
        return wt, self.targets(wt)

    def test_modified_and_unchanged_assume_unchanged_refuse(self) -> None:
        for modified in (False, True):
            with self.subTest(modified=modified):
                wt, target = self._flagged(
                    "assume-" + str(modified).lower(),
                    "--assume-unchanged", modified=modified)
                self._assert_generic_refusal(wt, target)
                self.assertTrue(Path(wt).exists())

    def test_modified_and_unchanged_skip_worktree_refuse(self) -> None:
        for modified in (False, True):
            with self.subTest(modified=modified):
                wt, target = self._flagged(
                    "skip-" + str(modified).lower(),
                    "--skip-worktree", modified=modified)
                self._assert_generic_refusal(wt, target)
                self.assertTrue(Path(wt).exists())

    def test_clean_materialized_sparse_checkout_refuses(self) -> None:
        _, wt, _ = self.ephemeral_wt("materialized-sparse")
        git(wt, "sparse-checkout", "init", "--cone")
        git(wt, "sparse-checkout", "set", "--cone", ".")
        tags = git(wt, "-c", "core.fsmonitor=false", "ls-files", "-t", "-z").stdout
        self.assertTrue(tags.startswith("H "), tags)
        self.assertNotIn("\0S ", "\0" + tags)
        self.assertTrue(Path(wt, "README.md").exists())
        self._assert_generic_refusal(wt, self.targets(wt))

    def test_effective_fsmonitor_config_refuses_without_invoking_hook(self) -> None:
        _, wt, _ = self.ephemeral_wt("fsmonitor-config")
        marker = self.data_home / "fsmonitor-config-invoked"
        hook = self._script(
            "fake-fsmonitor-config",
            f"printf invoked >> {shlex.quote(str(marker))}\nprintf 'token\\n'\n")
        git(wt, "config", "core.fsmonitor", str(hook))
        target = self.targets(wt)
        inventory = self._assert_generic_refusal(wt, target)
        self.assertFalse(marker.exists())
        self.assertNotIn(str(hook), json.dumps(inventory, sort_keys=True))

    def test_fsmonitor_valid_extension_refuses_after_config_disabled(self) -> None:
        _, wt, _ = self.ephemeral_wt("fsmonitor-extension")
        marker = self.data_home / "fsmonitor-extension-invoked"
        hook = self._script(
            "fake-fsmonitor-extension",
            f"printf invoked >> {shlex.quote(str(marker))}\nprintf 'token\\n'\n")
        git(wt, "config", "core.fsmonitor", str(hook))
        git(wt, "status", "--porcelain=v1")
        git(wt, "update-index", "--fsmonitor-valid", "README.md")
        index_path = Path(self.targets(wt)["git_dir"], "index")
        self.assertIn(b"FSMN", index_path.read_bytes())
        git(wt, "config", "core.fsmonitor", "false")
        marker.unlink(missing_ok=True)

        self._assert_generic_refusal(wt, self.targets(wt))
        self.assertFalse(marker.exists())

    def test_preflight_never_invokes_clean_or_smudge_filters(self) -> None:
        _, wt, _ = self.ephemeral_wt("filter-hook")
        marker = self.data_home / "filter-invoked"
        driver = self._script(
            "fake-filter",
            f"printf invoked >> {shlex.quote(str(marker))}\ncat\n")
        command = f"{shlex.quote(str(driver))}"
        git(wt, "config", "filter.tripwire.clean", command)
        git(wt, "config", "filter.tripwire.smudge", command)
        Path(wt, ".gitattributes").write_text(
            "README.md filter=tripwire\n", encoding="utf-8")
        commit_all(wt, "configure filter")
        marker.unlink(missing_ok=True)

        FIN._index_visibility_preflight(wt, self.targets(wt)["git_dir"])
        self.assertFalse(marker.exists())

    def test_preflight_git_reads_disable_writes_fsmonitor_and_lazy_fetch(self) -> None:
        _, wt, _ = self.ephemeral_wt("readonly-environment")
        target = self.targets(wt)
        real_run = FIN.subprocess.run
        observed = []

        def capture(command, *args, **kwargs):
            if isinstance(command, list) and command and command[0] == "git":
                observed.append((list(command), dict(kwargs.get("env") or {})))
            return real_run(command, *args, **kwargs)

        with mock.patch.object(FIN.subprocess, "run", side_effect=capture):
            FIN._index_visibility_preflight(wt, target["git_dir"])
        self.assertTrue(observed)
        for command, env in observed:
            self.assertEqual(env.get("GIT_OPTIONAL_LOCKS"), "0")
            self.assertEqual(env.get("GIT_NO_LAZY_FETCH"), "1")
            self.assertNotIn("status", command)
            if "ls-files" in command:
                self.assertIn("core.fsmonitor=false", command)

    def test_malformed_and_failed_flag_inspection_refuse_generically(self) -> None:
        for mode in ("malformed", "ambiguous", "failed"):
            with self.subTest(mode=mode):
                _, wt, _ = self.ephemeral_wt("inspection-" + mode)
                target = self.targets(wt)
                real = FIN._git_bytes

                def fault(root: str, *args: str):
                    if "ls-files" in args and "-v" in args:
                        if mode == "malformed":
                            return subprocess.CompletedProcess(
                                args, 0, stdout=b"H secret-path-without-nul",
                                stderr=b"")
                        if mode == "ambiguous":
                            return subprocess.CompletedProcess(
                                args, 0, stdout=b"H different-private-path\x00",
                                stderr=b"")
                        return subprocess.CompletedProcess(
                            args, 1, stdout=b"", stderr=b"private inspection failure")
                    return real(root, *args)

                with mock.patch.object(FIN, "_git_bytes", side_effect=fault):
                    inventory = self._assert_generic_refusal(wt, target)
                encoded = json.dumps(inventory, sort_keys=True)
                self.assertNotIn("secret-path", encoded)
                self.assertNotIn("private inspection failure", encoded)

    def test_sha1_and_sha256_normal_indexes_remain_supported(self) -> None:
        for object_format in ("sha1", "sha256"):
            with self.subTest(object_format=object_format):
                wt, target = self._format_worktree(
                    "format-" + object_format, object_format)
                Path(wt, "README.md").write_text(
                    f"# changed {object_format}\n", encoding="utf-8")
                Path(wt, "new.txt").write_text("visible\n", encoding="utf-8")
                inventory = FIN.build_inventory(wt, target["git_dir"])
                self.assertTrue(inventory["safe"], inventory)
                self.assertEqual(
                    {(entry["code"], entry["path"]) for entry in inventory["entries"]},
                    {(" M", "README.md"), ("??", "new.txt")})

    def test_index_v4_normal_rows_remain_supported(self) -> None:
        wt, target = self._format_worktree("index-v4", "sha1")
        converted = git(
            wt, "update-index", "--index-version=4", check=False)
        if converted.returncode != 0:
            self.skipTest("installed Git does not support index version 4")
        self.assertEqual(
            int.from_bytes(Path(target["git_dir"], "index").read_bytes()[4:8], "big"),
            4)
        Path(wt, "README.md").write_text("# v4 modified\n", encoding="utf-8")
        Path(wt, "new.txt").write_text("new\n", encoding="utf-8")
        inventory = FIN.build_inventory(wt, target["git_dir"])
        self.assertTrue(inventory["safe"], inventory)
        self.assertEqual(
            {(entry["code"], entry["path"]) for entry in inventory["entries"]},
            {(" M", "README.md"), ("??", "new.txt")})

    def test_preview_does_not_change_index_digest(self) -> None:
        _, wt, _ = self.ephemeral_wt("digest-stable")
        target = self.targets(wt)
        tracked = Path(wt, "README.md")
        before_stat = tracked.stat()
        os.utime(
            tracked,
            ns=(before_stat.st_atime_ns, before_stat.st_mtime_ns + 2_000_000_000))
        index_path = Path(target["git_dir"], "index")
        before = hashlib.sha256(index_path.read_bytes()).digest()

        preview = FIN.preview(
            root=wt, **target, session_id="digest-session",
            conversation_id="digest-conversation")
        self.assertTrue(preview["ok"], preview)
        after = hashlib.sha256(index_path.read_bytes()).digest()
        self.assertEqual(after, before)

    def test_refusal_mints_no_challenge_or_dialogue_and_preserves_root(self) -> None:
        wt, target = self._flagged(
            "no-dialogue", "--assume-unchanged", modified=False)
        conversation = "index-visibility-refusal"
        payload = {
            "hook_event_name": "beforeSubmitPrompt",
            "prompt": "finish",
            "conversation_id": conversation,
            "session_id": conversation,
            "cwd": wt,
            "workspace_roots": [wt],
        }
        output = UX.handle_hook_payload(payload)
        self.assertEqual(output, {"continue": True})
        self.assertEqual(FIN._read_challenge_raw(conversation)[1], "absent")
        self.assertIsNone(UX.read_dialogue(conversation))
        self.assertFalse(UX.index_path(conversation).exists())
        self.assertTrue(Path(wt).exists())
        self.assertTrue(Path(wt, "README.md").exists())

        direct = FIN.preview(
            root=wt, **target, session_id="direct",
            conversation_id="direct-index-visibility-refusal")
        self.assertFalse(direct["ok"], direct)
        self.assertEqual(
            direct["reason"], "inventory_" + GENERIC_REASON)
        self.assertEqual(
            FIN._read_challenge_raw("direct-index-visibility-refusal")[1],
            "absent")
        self.assertTrue(Path(wt).exists())

    def test_shell_preview_refuses_generically_without_challenge(self) -> None:
        wt, target = self._flagged(
            "shell-refusal", "--skip-worktree", modified=True)
        conversation = "shell-index-visibility-refusal"
        result = self.run_dev_finish(
            "--preview", "--conversation-id", conversation, cwd=wt)
        self.assertNotEqual(result.returncode, 0)
        rendered = result.stdout + result.stderr
        self.assertIn("inventory unsafe or unreadable", rendered)
        for secret in (
                "README.md", "private modified bytes", target["head"],
                target["git_dir"], target["common_dir"]):
            self.assertNotIn(secret, rendered)
        self.assertEqual(FIN._read_challenge_raw(conversation)[1], "absent")
        self.assertTrue(Path(wt).exists())
        self.assertEqual(
            Path(wt, "README.md").read_text(encoding="utf-8"),
            "private modified bytes\n")

    def test_generic_refusal_leaks_no_path_oid_hash_config_or_content(self) -> None:
        private_name = "private-index-path-do-not-render.txt"
        private_content = "private-content-do-not-render"
        _, wt, _ = self.ephemeral_wt("content-safe-refusal")
        private = Path(wt, private_name)
        private.write_text(private_content, encoding="utf-8")
        commit_all(wt, "private fixture")
        git(wt, "update-index", "--assume-unchanged", private_name)
        target = self.targets(wt)
        head = target["head"]
        result = FIN.preview(
            root=wt, **target, session_id="safe-output",
            conversation_id="safe-output")
        rendered = json.dumps(result, sort_keys=True)
        self.assertFalse(result["ok"], result)
        self.assertEqual(result["reason"], "inventory_" + GENERIC_REASON)
        for secret in (
                private_name, private_content, head,
                hashlib.sha256(private_content.encode()).hexdigest(),
                target["git_dir"], target["common_dir"]):
            self.assertNotIn(secret, rendered)

    def test_ordinary_visible_tracked_and_untracked_rows_are_unchanged(self) -> None:
        _, wt, _ = self.ephemeral_wt("ordinary-visible")
        Path(wt, "README.md").write_text("# modified\n", encoding="utf-8")
        Path(wt, "new file.txt").write_text("new\n", encoding="utf-8")
        inventory = FIN.build_inventory(wt, self.targets(wt)["git_dir"])
        self.assertTrue(inventory["safe"], inventory)
        self.assertEqual(
            [
                (entry["code"], entry["class"], entry["path"], entry["sentence"])
                for entry in inventory["entries"]
            ],
            [
                (" M", "modified", "README.md",
                 "A tracked file you have modified but not committed."),
                ("??", "untracked", "new file.txt",
                 "A new file that is not tracked by version control."),
            ],
        )
        self.assertEqual(
            FIN.render_rows(inventory),
            "1. README.md | A tracked file you have modified but not committed.\n"
            "2. new file.txt | A new file that is not tracked by version control.")


if __name__ == "__main__":
    import unittest
    unittest.main()
