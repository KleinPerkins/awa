"""Final Phase-2 hardening: hostile Git environments, removal truth, durable Retain."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path
from unittest import mock

from consumer import finish_current as UX
from . import test_finish_kernel as kernel_tests
from .helpers import EngineTestCase, commit_all, git


FIN = kernel_tests.FIN


class FinalHardeningBase(EngineTestCase):
    def linked(self, name: str, *, object_format: str = "sha1") -> tuple[str, str]:
        if object_format == "sha1":
            repo = self.make_seeded_repo(name)
        else:
            repo = str(Path(self._tmp.name) / name)
            Path(repo).mkdir()
            initialized = subprocess.run(
                ["git", "-C", repo, "init", "-q", "--object-format=sha256", "."],
                capture_output=True, text=True)
            if initialized.returncode != 0:
                self.skipTest("installed Git does not support SHA-256 repositories")
            Path(repo, "README.md").write_text("# sha256\n", encoding="utf-8")
            commit_all(repo, "init")
            git(repo, "branch", "-M", "main")
        return repo, self.add_worktree(repo, f"cursor/worktree/{name}")

    def payload(self, wt: str, conversation: str) -> dict:
        target = UX.resolve_linked_root({"cwd": wt})
        UX._load_finish()._roots_module().write_current_session(
            wt, session_id=conversation, conversation_id=conversation,
            branch=target["branch"], common_dir=target["common_dir"])
        return {
            "hook_event_name": "beforeSubmitPrompt",
            "prompt": "I'm done",
            "conversation_id": conversation,
            "session_id": conversation,
            "cwd": wt,
            "workspace_roots": [wt],
        }

    def retain_ready(self, name: str, *, nested: bool = False,
                     object_format: str = "sha1") -> tuple[str, Path, list[int]]:
        _repo, wt = self.linked(name, object_format=object_format)
        rel = "nested/deeper/draft.txt" if nested else "draft.txt"
        source = Path(wt, rel)
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("preserve exactly\n", encoding="utf-8")
        UX.preview_payload(self.payload(wt, name))
        UX.dispatch_choice(name, "Retain")
        dialogue = UX.read_dialogue(name)
        return wt, source, list(range(1, len(dialogue["visible"]) + 1))


class DeterministicGitEnvironmentTest(FinalHardeningBase):
    POISON = {
        "GIT_DIR": "/definitely/wrong/git-dir",
        "GIT_COMMON_DIR": "/definitely/wrong/common-dir",
        "GIT_WORK_TREE": "/definitely/wrong/work-tree",
        "GIT_INDEX_FILE": "/definitely/wrong/index",
        "GIT_OBJECT_DIRECTORY": "/definitely/wrong/objects",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES": "/definitely/wrong/alternate",
        "GIT_NAMESPACE": "hostile",
        "GIT_PREFIX": "hostile/",
        "GIT_CEILING_DIRECTORIES": "/",
        "GIT_DISCOVERY_ACROSS_FILESYSTEM": "false",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_SYSTEM": "/definitely/wrong/system-config",
        "GIT_CONFIG_GLOBAL": "/definitely/wrong/global-config",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "core.bare",
        "GIT_CONFIG_VALUE_0": "true",
        "GIT_FUTURE_UNKNOWN": "hostile",
    }

    def test_profile_strips_every_ambient_git_variable_and_preserves_host_context(self) -> None:
        with mock.patch.dict(os.environ, {
                **self.POISON, "AWA_NON_GIT_SENTINEL": "preserved"}, clear=False):
            env = FIN.sanitized_git_env()
            self.assertEqual(env["AWA_NON_GIT_SENTINEL"], "preserved")
            self.assertEqual(
                {key for key in env if key.startswith("GIT_")},
                {"GIT_OPTIONAL_LOCKS", "GIT_NO_LAZY_FETCH", "GIT_TERMINAL_PROMPT"})
            self.assertEqual(
                {key: env[key] for key in (
                    "GIT_OPTIONAL_LOCKS", "GIT_NO_LAZY_FETCH",
                    "GIT_TERMINAL_PROMPT", "LC_ALL", "LANG", "LANGUAGE")},
                {
                    "GIT_OPTIONAL_LOCKS": "0", "GIT_NO_LAZY_FETCH": "1",
                    "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C",
                    "LANG": "C", "LANGUAGE": "C",
                })

    def test_all_finish_kernel_and_root_recheck_git_children_receive_only_safe_profile(self) -> None:
        _repo, wt = self.linked("git-env-spy")
        Path(wt, "draft.txt").write_text("staged only\n", encoding="utf-8")
        git(wt, "add", "draft.txt")
        real_run = subprocess.run
        observed: list[dict] = []

        def spy(command, *args, **kwargs):
            if isinstance(command, (list, tuple)) and command and command[0] == "git":
                observed.append(dict(kwargs.get("env") or {}))
            return real_run(command, *args, **kwargs)

        with mock.patch.dict(os.environ, self.POISON, clear=False), \
                mock.patch.object(subprocess, "run", side_effect=spy):
            target = FIN.resolve_target(wt)
            inventory = FIN.build_inventory(wt, target["git_dir"])
            roots = FIN._roots_module()
            ok, _reason = roots._heartbeat_target_recheck(
                wt, branch=target["branch"], common_dir=target["common_dir"],
                require_linked=True)
        self.assertTrue(inventory["safe"], inventory)
        self.assertTrue(ok)
        self.assertTrue(observed)
        allowed = {
            "GIT_OPTIONAL_LOCKS", "GIT_NO_LAZY_FETCH",
            "GIT_TERMINAL_PROMPT", "GIT_INDEX_FILE",
        }
        for env in observed:
            self.assertFalse((set(self.POISON) - {"GIT_INDEX_FILE"}) & set(env))
            self.assertNotEqual(env.get("GIT_INDEX_FILE"), self.POISON["GIT_INDEX_FILE"])
            self.assertLessEqual(
                {key for key in env if key.startswith("GIT_")}, allowed)
            self.assertEqual(env["LC_ALL"], "C")

    def test_poisoned_alternate_index_cannot_hide_staged_state_sha1_or_sha256(self) -> None:
        for object_format in ("sha1", "sha256"):
            with self.subTest(object_format=object_format):
                _repo, wt = self.linked(
                    "alt-index-" + object_format, object_format=object_format)
                tracked = Path(wt, "README.md")
                tracked.write_text("staged-only replacement\n", encoding="utf-8")
                git(wt, "add", "README.md")
                target = FIN.resolve_target(wt)
                expected = FIN.build_inventory(wt, target["git_dir"])
                self.assertTrue(expected["safe"], expected)
                self.assertTrue(any(
                    entry["class"] == "staged" for entry in expected["entries"]))
                alternate = self.data_home / f"{object_format}.alternate-index"
                git(wt, "read-tree", f"--index-output={alternate}", "HEAD")
                poison = dict(self.POISON)
                poison["GIT_INDEX_FILE"] = str(alternate)
                with mock.patch.dict(os.environ, poison, clear=False):
                    actual = FIN.build_inventory(wt, target["git_dir"])
                self.assertEqual(actual, expected)

    def test_each_selector_config_and_object_variable_preserves_inventory_parity(self) -> None:
        _repo, wt = self.linked("individual-git-poison")
        Path(wt, "README.md").write_text("staged parity\n", encoding="utf-8")
        git(wt, "add", "README.md")
        Path(wt, "untracked.txt").write_text("untracked parity\n", encoding="utf-8")
        target = FIN.resolve_target(wt)
        expected = FIN.build_inventory(wt, target["git_dir"])
        for key, value in self.POISON.items():
            with self.subTest(variable=key), \
                    mock.patch.dict(os.environ, {key: value}, clear=False):
                self.assertEqual(
                    FIN.build_inventory(wt, target["git_dir"]), expected)

    def test_preflight_never_invokes_configured_fsmonitor_or_filter_process(self) -> None:
        _repo, wt = self.linked("no-hook-preflight")
        marker = self.data_home / "hook-ran"
        hook = self.data_home / "hook.sh"
        hook.write_text(
            "#!/bin/sh\nprintf ran >> \"$AWA_TEST_HOOK_MARKER\"\ncat\n",
            encoding="utf-8")
        hook.chmod(0o700)
        os.environ["AWA_TEST_HOOK_MARKER"] = str(marker)
        try:
            git(wt, "config", "filter.awa-hardening.clean", str(hook))
            git(wt, "config", "filter.awa-hardening.smudge", "cat")
            Path(wt, ".gitattributes").write_text(
                "*.filtered filter=awa-hardening\n", encoding="utf-8")
            Path(wt, "value.filtered").write_text("base\n", encoding="utf-8")
            commit_all(wt, "filtered baseline")
            marker.unlink(missing_ok=True)
            target = FIN.resolve_target(wt)
            FIN._index_visibility_preflight(wt, target["git_dir"])
            self.assertFalse(marker.exists())
            git(wt, "config", "core.fsmonitor", str(hook))
            inventory = FIN.build_inventory(wt, target["git_dir"])
            self.assertFalse(inventory["safe"])
            self.assertEqual(inventory["refuse_reason"], FIN.INDEX_VISIBILITY_REFUSAL)
            self.assertFalse(marker.exists())
            self.assertEqual(
                git(wt, "config", "filter.awa-hardening.clean").stdout.strip(),
                str(hook))
        finally:
            os.environ.pop("AWA_TEST_HOOK_MARKER", None)

    def test_shell_finish_preview_is_parity_safe_under_combined_poison(self) -> None:
        _repo, wt = self.linked("shell-env-parity")
        Path(wt, "draft.txt").write_text("visible\n", encoding="utf-8")
        env = os.environ.copy()
        env.update(self.POISON)
        env.update({
            "AWA_HOME": str(Path(__file__).resolve().parents[2]),
            "XDG_STATE_HOME": str(self.state_home),
            "DEV_SESSION_ID": "shell-env-parity",
        })
        result = subprocess.run(
            [str(Path(__file__).resolve().parents[2] / "kernel" / "bin"
                 / "dev-worktree.sh"),
             "clean", "--finish-current", "--preview",
             "--conversation-id", "shell-env-parity"],
            cwd=wt, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("AWA finish preview", result.stdout)
        self.assertIn("draft.txt", result.stdout)

    def test_retain_and_commit_consumers_never_forward_ambient_git_variables(self) -> None:
        wt, _source, indices = self.retain_ready("consumer-env-retain")
        real_run = subprocess.run
        observed: list[tuple[list[str], dict]] = []

        def spy(command, *args, **kwargs):
            if isinstance(command, (list, tuple)) and command and command[0] == "git":
                observed.append((list(command), dict(kwargs.get("env") or {})))
            return real_run(command, *args, **kwargs)

        with mock.patch.dict(os.environ, self.POISON, clear=False), \
                mock.patch.object(subprocess, "run", side_effect=spy):
            UX.create_retain("consumer-env-retain", indices)

        _repo, commit_wt = self.linked("consumer-env-commit")
        Path(commit_wt, "selected.txt").write_text("selected\n", encoding="utf-8")
        UX.preview_payload(self.payload(commit_wt, "consumer-env-commit"))
        UX.dispatch_choice("consumer-env-commit", "Commit")
        with mock.patch.dict(os.environ, self.POISON, clear=False):
            UX.commit_selected_local(
                "consumer-env-commit", [1], "selected environment",
                runner=spy)
        self.assertTrue(observed)
        allowed = {
            "GIT_OPTIONAL_LOCKS", "GIT_NO_LAZY_FETCH",
            "GIT_TERMINAL_PROMPT", "GIT_INDEX_FILE",
        }
        for _command, env in observed:
            self.assertFalse((set(self.POISON) - {"GIT_INDEX_FILE"}) & set(env))
            self.assertNotEqual(env.get("GIT_INDEX_FILE"), self.POISON["GIT_INDEX_FILE"])
            self.assertLessEqual(
                {key for key in env if key.startswith("GIT_")}, allowed)


class HonestRemovalClassificationTest(FinalHardeningBase):
    def target(self, wt: str) -> dict:
        return FIN.resolve_target(wt)

    def prepare_only(self, wt: str, conversation: str) -> tuple[dict, dict]:
        target = self.target(wt)
        preview = FIN.preview(
            **target, session_id="sess", conversation_id=conversation)
        self.assertTrue(preview["ok"], preview)
        challenge, status = FIN._read_challenge_raw(conversation)
        self.assertEqual(status, "ok")
        inventory = FIN.build_inventory(wt, target["git_dir"])
        identity = FIN._operation_identity_payload(
            root=wt, git_dir=target["git_dir"],
            common_dir=target["common_dir"], branch=target["branch"],
            head=target["head"], conversation_id=conversation,
            nonce=challenge["nonce"], generation=challenge["generation"],
            session_id="sess",
            session_key_value=FIN._roots_module().session_key("sess"),
            boot_id_value=challenge["boot_id"],
            install_id_value=challenge["install_id"],
            root_incarnation_value=challenge["root_incarnation"],
            git_dir_incarnation_value=challenge["git_dir_incarnation"],
            fingerprint=challenge["fingerprint"], claim="direct",
            branch_disposition_value=FIN.branch_disposition(
                wt, target["branch"], target["head"], target["common_dir"]),
            discard_count=len(inventory["entries"]))
        with FIN.common_dir_lock(target["common_dir"]):
            journal = FIN._prepare_removal_journal_locked(identity=identity)
        return target, journal

    def reconcile(self, wt: str, target: dict, conversation: str) -> dict:
        return FIN.reconcile_removal(
            **target, conversation_id=conversation, session_id="sess")

    def test_every_partial_content_class_with_same_root_inode_is_uncertain_and_preserved(self) -> None:
        cases = ("tracked", "index", "untracked", "ignored", "symlink", "directory")
        for kind in cases:
            with self.subTest(kind=kind):
                repo, wt = self.linked("partial-" + kind)
                nested = Path(wt, "nested")
                nested.mkdir()
                Path(wt, ".gitignore").write_text("nested/ignored.bin\n", encoding="utf-8")
                Path(nested, "tracked.txt").write_text("base\n", encoding="utf-8")
                Path(nested, "index.txt").write_text("base\n", encoding="utf-8")
                Path(nested, "target-a").write_text("a\n", encoding="utf-8")
                Path(nested, "target-b").write_text("b\n", encoding="utf-8")
                commit_all(wt, "partial baseline")
                Path(nested, "tracked.txt").write_text("before\n", encoding="utf-8")
                Path(nested, "index.txt").write_text("staged-before\n", encoding="utf-8")
                git(wt, "add", "nested/index.txt")
                Path(nested, "untracked.txt").write_text("before\n", encoding="utf-8")
                Path(nested, "ignored.bin").write_text("before\n", encoding="utf-8")
                os.symlink("target-a", nested / "link")
                Path(nested, "tree", "child").mkdir(parents=True)
                Path(nested, "tree", "child", "value").write_text(
                    "before\n", encoding="utf-8")
                target, journal = self.prepare_only(wt, "partial-" + kind)
                root_inode = os.lstat(wt).st_ino
                if kind == "tracked":
                    Path(nested, "tracked.txt").write_text("after\n", encoding="utf-8")
                    secret = "tracked.txt"
                elif kind == "index":
                    Path(nested, "index.txt").write_text("staged-after\n", encoding="utf-8")
                    git(wt, "add", "nested/index.txt")
                    secret = "index.txt"
                elif kind == "untracked":
                    Path(nested, "untracked.txt").unlink()
                    secret = "untracked.txt"
                elif kind == "ignored":
                    Path(nested, "ignored.bin").write_text("after\n", encoding="utf-8")
                    secret = "ignored.bin"
                elif kind == "symlink":
                    (nested / "link").unlink()
                    os.symlink("target-b", nested / "link")
                    secret = "target-b"
                else:
                    shutil.rmtree(nested / "tree" / "child")
                    secret = "child"
                self.assertEqual(os.lstat(wt).st_ino, root_inode)
                result = self.reconcile(wt, target, "partial-" + kind)
                self.assertEqual(result["outcome"], "uncertain", result)
                self.assertTrue(
                    Path(FIN.removal_journal_path(journal["operation_id"])).exists())
                self.assertEqual(git(repo, "show-ref", "--verify",
                                     f"refs/heads/{target['branch']}").returncode, 0)
                self.assertIsNotNone(FIN.read_challenge("partial-" + kind)[0])
                self.assertNotIn(secret, json.dumps(result))
                self.assertEqual(kernel_tests.AR.list_receipts(), [])

    def _execute_with_remove(self, name: str, behavior) -> tuple[str, dict, dict]:
        repo, wt = self.linked(name)
        Path(wt, "nested").mkdir()
        Path(wt, "nested", "draft").write_text("discard\n", encoding="utf-8")
        target = self.target(wt)
        preview = FIN.preview(
            **target, session_id="sess", conversation_id=name)
        self.assertTrue(preview["ok"], preview)
        real_admin = FIN._run_git_admin

        def intercept(common_dir, *args, **kwargs):
            if len(args) >= 2 and args[0:2] == ("worktree", "remove"):
                return behavior(real_admin, common_dir, args, kwargs, wt)
            return real_admin(common_dir, *args, **kwargs)

        with mock.patch.object(FIN, "_run_git_admin", side_effect=intercept):
            result = FIN.finish_execute(
                **target, session_id="sess", conversation_id=name, answer="Close")
        return repo, target, result

    def test_intact_failure_clears_prepared_journal_but_complete_nonzero_finalizes(self) -> None:
        def intact(_real, _common, args, _kwargs, _wt):
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="intact failure")

        repo, target, result = self._execute_with_remove("remove-intact", intact)
        self.assertEqual(result["outcome"], "error", result)
        self.assertEqual(result["reason"], "worktree_remove_failed")
        self.assertTrue(Path(target["root"]).exists())
        self.assertFalse(list(Path(FIN.finish_dir()).glob("removal-*.json")))
        self.assertEqual(git(repo, "show-ref", "--verify",
                             f"refs/heads/{target['branch']}").returncode, 0)

        def complete(real, common, args, kwargs, _wt):
            removed = real(common, *args, **kwargs)
            self.assertEqual(removed.returncode, 0, removed.stderr)
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="late failure")

        _repo, target, result = self._execute_with_remove("remove-complete", complete)
        self.assertEqual(result["outcome"], "removed", result)
        self.assertFalse(Path(target["root"]).exists())
        receipts = kernel_tests.AR.list_receipts()
        self.assertEqual(receipts[-1]["disposition"], "removed")

    def test_partial_delete_and_inspection_failure_never_cleanup_branch_or_narrate_removed(self) -> None:
        def partial(_real, _common, args, _kwargs, wt):
            Path(wt, "nested", "draft").unlink()
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

        repo, target, result = self._execute_with_remove("remove-partial", partial)
        self.assertEqual(result["outcome"], "uncertain", result)
        self.assertEqual(result["message"], "workspace removal could not be classified safely")
        self.assertTrue(Path(target["root"]).exists())
        self.assertEqual(git(repo, "show-ref", "--verify",
                             f"refs/heads/{target['branch']}").returncode, 0)
        self.assertFalse(any(
            item["disposition"] == "removed" for item in kernel_tests.AR.list_receipts()))

        def intact(_real, _common, args, _kwargs, _wt):
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="inspection")

        real_registration = FIN._worktree_registration
        calls = 0

        def unavailable(common_dir, root):
            nonlocal calls
            calls += 1
            if calls >= 1:
                return False, 0
            return real_registration(common_dir, root)

        with mock.patch.object(FIN, "_worktree_registration", side_effect=unavailable):
            repo, target, result = self._execute_with_remove(
                "remove-inspection", intact)
        self.assertEqual(result["outcome"], "uncertain", result)
        self.assertTrue(Path(target["root"]).exists())
        self.assertEqual(git(repo, "show-ref", "--verify",
                             f"refs/heads/{target['branch']}").returncode, 0)


class DurableRetainPublicationTest(FinalHardeningBase):
    def _assert_unsuppressed(self, wt: str, source: Path) -> None:
        target = UX._load_finish().resolve_target(wt)
        inventory = UX._load_finish().build_inventory(wt, target["git_dir"])
        rel = str(source.relative_to(wt))
        row = next(item for item in inventory["entries"] if item["path"] == rel)
        self.assertFalse(row.get("retained"))

    def _assert_suppressed(self, wt: str, source: Path) -> None:
        target = UX._load_finish().resolve_target(wt)
        inventory = UX._load_finish().build_inventory(wt, target["git_dir"])
        rel = str(source.relative_to(wt))
        row = next(item for item in inventory["entries"] if item["path"] == rel)
        self.assertTrue(row.get("retained"))

    def test_short_writes_loop_and_nested_directory_sync_order_is_exact(self) -> None:
        destination = self.data_home / "durable" / "value"
        real_write = os.write

        def short_write(fd, data):
            return real_write(fd, bytes(data[:3]))

        with mock.patch.object(os, "write", side_effect=short_write):
            UX._private_write(destination, b"0123456789abcdef")
        self.assertEqual(destination.read_bytes(), b"0123456789abcdef")
        self.assertEqual(destination.stat().st_mode & 0o777, 0o600)

        tree = self.data_home / "sync-tree"
        (tree / "a" / "b").mkdir(parents=True)
        (tree / "c").mkdir()
        observed: list[Path] = []
        with mock.patch.object(UX, "_sync_dir", side_effect=lambda path: observed.append(Path(path))):
            UX._sync_tree_directories_bottom_up(tree)
        expected = sorted(
            [tree, tree / "a", tree / "a" / "b", tree / "c"],
            key=lambda value: (len(value.parts), os.fsencode(str(value))),
            reverse=True)
        self.assertEqual(observed, expected)

    def test_each_publication_boundary_failure_preserves_every_candidate(self) -> None:
        boundaries = (
            "payload_write", "tree_sync", "proof", "staging_rename",
            "post_rename_sync", "proven_manifest",
        )
        for boundary in boundaries:
            with self.subTest(boundary=boundary):
                wt, source, indices = self.retain_ready(
                    "retain-fault-" + boundary, nested=True)
                root = UX._retain_dir()
                patches = []
                if boundary == "payload_write":
                    patches.append(mock.patch.object(
                        UX, "_copy_regular_durable",
                        side_effect=OSError("injected payload write fault")))
                elif boundary == "tree_sync":
                    patches.append(mock.patch.object(
                        UX, "_sync_tree_directories_bottom_up",
                        side_effect=OSError("injected tree sync fault")))
                elif boundary == "proof":
                    patches.append(mock.patch.object(
                        UX, "_verify_restored",
                        side_effect=OSError("injected proof fault")))
                elif boundary == "staging_rename":
                    real_replace = os.replace

                    def fail_staging(source_path, destination_path):
                        if str(source_path).endswith(".staging"):
                            raise OSError("injected staging rename fault")
                        return real_replace(source_path, destination_path)

                    patches.append(mock.patch.object(os, "replace", side_effect=fail_staging))
                elif boundary == "post_rename_sync":
                    real_sync = UX._sync_dir

                    def fail_after_rename(path):
                        finals = [
                            item for item in root.iterdir()
                            if item.name.startswith("retain-") and item.is_dir()]
                        if Path(path) == root and finals:
                            raise OSError("injected post-rename sync fault")
                        return real_sync(path)

                    patches.append(mock.patch.object(
                        UX, "_sync_dir", side_effect=fail_after_rename))
                else:
                    real_private_write = UX._private_write

                    def fail_publish(path, data):
                        if (Path(path).name == "manifest.json"
                                and b'"restore_proven": true' in data):
                            raise OSError("injected proven manifest fault")
                        return real_private_write(path, data)

                    patches.append(mock.patch.object(
                        UX, "_private_write", side_effect=fail_publish))
                for patch in patches:
                    patch.start()
                try:
                    with self.assertRaises(Exception):
                        UX.create_retain(
                            "retain-fault-" + boundary, indices)
                finally:
                    for patch in reversed(patches):
                        patch.stop()
                self.assertTrue(source.exists())
                listed = [
                    item for item in UX.list_retained()
                    if item.get("source") == os.path.realpath(wt)
                ]
                if boundary == "post_rename_sync":
                    self.assertEqual(len(listed), 1)
                    self._assert_suppressed(wt, source)
                else:
                    self.assertEqual(listed, [])
                    self._assert_unsuppressed(wt, source)
                for candidate in root.iterdir():
                    if candidate.name.startswith("retain-"):
                        try:
                            doc = UX._manifest(candidate, require_proven=False)
                        except UX.FinishUXError:
                            continue
                        if doc.get("source") == os.path.realpath(wt):
                            self.assertEqual(
                                doc["restore_proven"],
                                boundary == "post_rename_sync")
                            UX.delete_retain(doc["artifact_id"], doc["artifact_id"])

    def test_crash_before_and_after_rename_and_after_publication_have_truthful_visibility(self) -> None:
        class Crash(BaseException):
            pass

        for point in ("before_rename", "after_rename", "after_publication"):
            with self.subTest(point=point):
                name = "retain-crash-" + point
                wt, source, indices = self.retain_ready(name)
                root = UX._retain_dir()
                real_replace = os.replace
                real_private_write = UX._private_write

                def crash_replace(source_path, destination_path):
                    source_name = Path(source_path).name
                    destination_name = Path(destination_path).name
                    if source_name.endswith(".staging"):
                        if point == "before_rename":
                            raise Crash()
                        value = real_replace(source_path, destination_path)
                        if point == "after_rename":
                            raise Crash()
                        return value
                    return real_replace(source_path, destination_path)

                def crash_publish(path, data):
                    value = real_private_write(path, data)
                    if (point == "after_publication"
                            and Path(path).name.endswith(
                                ".publication.committed.json")):
                        raise Crash()
                    return value

                with mock.patch.object(os, "replace", side_effect=crash_replace), \
                        mock.patch.object(UX, "_private_write", side_effect=crash_publish), \
                        self.assertRaises(Crash):
                    UX.create_retain(name, indices)
                artifacts = []
                artifact_errors = {}
                for candidate in root.iterdir():
                    try:
                        doc = UX._manifest(
                            candidate, require_proven=False,
                            allow_uncommitted=True)
                    except UX.FinishUXError as exc:
                        artifact_errors[candidate.name] = str(exc)
                        continue
                    if doc.get("source") == os.path.realpath(wt):
                        artifacts.append((candidate, doc))
                self.assertEqual(
                    len(artifacts), 1,
                    {"children": sorted(item.name for item in root.iterdir()),
                     "errors": artifact_errors})
                _candidate, doc = artifacts[0]
                visible = {item["artifact_id"] for item in UX.list_retained()}
                self.assertTrue(doc["restore_proven"])
                if point in {"after_rename", "after_publication"}:
                    self.assertIn(doc["artifact_id"], visible)
                else:
                    self.assertNotIn(doc["artifact_id"], visible)
                    self._assert_unsuppressed(wt, source)
                UX.delete_retain(doc["artifact_id"], doc["artifact_id"])

    def test_delete_tombstone_resume_and_legacy_manifest_compatibility(self) -> None:
        wt, _source, indices = self.retain_ready("retain-delete-resume")
        created = UX.create_retain("retain-delete-resume", indices)
        artifact_id = created["artifact_id"]
        artifact = UX._artifact_path(artifact_id)
        doc = UX._manifest(artifact)
        doc.pop("object_format")
        doc.pop("publication_protocol")
        UX._private_write(
            artifact / "manifest.json",
            (json.dumps(doc, indent=2, sort_keys=True) + "\n").encode())
        _pending, committed, _rollback = UX._publication_paths(artifact_id)
        committed.unlink()
        UX._sync_dir(UX._retain_dir())
        listed = {
            item["artifact_id"]: item for item in UX.list_retained()}
        self.assertIn(artifact_id, listed)
        self.assertEqual(
            listed[artifact_id]["publication_status"], "legacy_unlatched")
        restored = self.data_home / "legacy-restored"
        UX.restore_retain(artifact_id, str(restored))
        self.assertEqual(
            git(str(restored), "rev-parse", "--show-object-format").stdout.strip(),
            "sha1")
        real_rmtree = shutil.rmtree
        tombstone = UX._retain_dir() / ("." + artifact_id + ".tombstone")
        failed = False

        def fail_once(path, *args, **kwargs):
            nonlocal failed
            candidate = Path(path)
            if not failed and tombstone in (candidate, *candidate.parents):
                failed = True
                raise OSError("injected recursive delete interruption")
            return real_rmtree(path, *args, **kwargs)

        with mock.patch.object(shutil, "rmtree", side_effect=fail_once):
            with self.assertRaises(OSError):
                UX.delete_retain(artifact_id, artifact_id)
        self.assertTrue(tombstone.exists())
        resumed = UX.delete_retain(artifact_id, artifact_id)
        self.assertFalse(resumed["already_absent"])
        self.assertFalse(tombstone.exists())

    def test_delete_crash_boundaries_are_idempotently_resumable(self) -> None:
        class Crash(BaseException):
            pass

        for point in (
                "artifact_renamed", "owner_published",
                "tombstone_removed", "owner_removed"):
            with self.subTest(point=point):
                name = "retain-delete-crash-" + point
                _wt, _source, indices = self.retain_ready(name)
                created = UX.create_retain(name, indices)
                artifact_id = created["artifact_id"]
                artifact = UX._artifact_path(artifact_id)
                root = UX._retain_dir()
                tombstone = root / ("." + artifact_id + ".tombstone")
                owner = root / ("." + artifact_id + ".tombstone-owner.json")
                real_replace = os.replace
                real_rmdir = Path.rmdir
                real_unlink = Path.unlink

                def crash_replace(source, destination):
                    value = real_replace(source, destination)
                    if ((point == "artifact_renamed" and Path(destination) == tombstone)
                            or (point == "owner_published" and Path(destination) == owner)):
                        raise Crash()
                    return value

                def crash_rmdir(path, *args, **kwargs):
                    value = real_rmdir(path, *args, **kwargs)
                    if point == "tombstone_removed" and path == tombstone:
                        raise Crash()
                    return value

                def crash_unlink(path, *args, **kwargs):
                    value = real_unlink(path, *args, **kwargs)
                    if point == "owner_removed" and path == owner:
                        raise Crash()
                    return value

                with mock.patch.object(os, "replace", side_effect=crash_replace), \
                        mock.patch.object(Path, "rmdir", new=crash_rmdir), \
                        mock.patch.object(Path, "unlink", new=crash_unlink), \
                        self.assertRaises(Crash):
                    UX.delete_retain(artifact_id, artifact_id)
                self.assertNotIn(
                    artifact_id, {item["artifact_id"] for item in UX.list_retained()})
                resumed = UX.delete_retain(artifact_id, artifact_id)
                self.assertTrue(resumed["ok"])
                self.assertFalse(os.path.lexists(artifact))
                self.assertFalse(os.path.lexists(tombstone))
                self.assertFalse(os.path.lexists(owner))

    def test_sha1_and_sha256_retain_proof_use_source_format_and_raw_blobs(self) -> None:
        for object_format in ("sha1", "sha256"):
            with self.subTest(object_format=object_format):
                name = "retain-format-" + object_format
                _repo, wt = self.linked(name, object_format=object_format)
                filter_script = self.data_home / f"{object_format}-filter.sh"
                filter_script.write_text(
                    "#!/bin/sh\ntr '[:lower:]' '[:upper:]'\n", encoding="utf-8")
                filter_script.chmod(0o700)
                git(wt, "config", "filter.hostile.clean", str(filter_script))
                git(wt, "config", "filter.hostile.smudge", "cat")
                Path(wt, ".gitattributes").write_text(
                    "*.raw filter=hostile\n", encoding="utf-8")
                Path(wt, "value.raw").write_text("worktree bytes\n", encoding="utf-8")
                commit_all(wt, "filtered baseline")
                Path(wt, "value.raw").write_text("staged worktree bytes\n", encoding="utf-8")
                git(wt, "add", "value.raw")
                UX.preview_payload(self.payload(wt, name))
                UX.dispatch_choice(name, "Retain")
                dialogue = UX.read_dialogue(name)
                created = UX.create_retain(
                    name, list(range(1, len(dialogue["visible"]) + 1)))
                artifact = UX._artifact_path(created["artifact_id"])
                doc = UX._manifest(artifact)
                self.assertEqual(doc["object_format"], object_format)
                destination = self.data_home / f"{object_format}-restore"
                UX.restore_retain(created["artifact_id"], str(destination))
                self.assertEqual(
                    git(str(destination), "rev-parse",
                        "--show-object-format").stdout.strip(),
                    object_format)
                for blob in doc["git_blobs"]:
                    raw = (artifact / "git-blobs" / blob["oid"]).read_bytes()
                    written = subprocess.run(
                        ["git", f"--git-dir={destination / '.git'}",
                         "hash-object", "--no-filters", "--stdin"],
                        input=raw, capture_output=True)
                    self.assertEqual(
                        written.stdout.decode().strip(), blob["oid"])

    def test_retain_index_restore_is_nul_safe_for_newline_and_tab_paths(self) -> None:
        _repo, wt = self.linked("retain-odd-paths")
        odd_paths = ("line\nbreak.txt", "tab\tname.txt")
        for rel in odd_paths:
            Path(wt, rel).write_text(rel, encoding="utf-8")
            git(wt, "add", rel)
        UX.preview_payload(self.payload(wt, "retain-odd-paths"))
        UX.dispatch_choice("retain-odd-paths", "Retain")
        dialogue = UX.read_dialogue("retain-odd-paths")
        created = UX.create_retain(
            "retain-odd-paths",
            list(range(1, len(dialogue["visible"]) + 1)))
        destination = self.data_home / "odd-path-restore"
        UX.restore_retain(created["artifact_id"], str(destination))
        for rel in odd_paths:
            self.assertEqual(
                Path(destination, rel).read_text(encoding="utf-8"), rel)


if __name__ == "__main__":
    import unittest
    unittest.main()
