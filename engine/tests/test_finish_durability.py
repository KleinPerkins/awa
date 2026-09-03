"""Physical-durability primitive and destructive-ordering regressions."""

from __future__ import annotations

import errno
import importlib.util
import os
import subprocess
from pathlib import Path
from unittest import mock

from .helpers import commit_all, git
from .test_finish_kernel import FIN, FinishBase


_DURABILITY_PATH = Path(__file__).resolve().parents[2] / "kernel" / "lib" / "awa_durability.py"
_SPEC = importlib.util.spec_from_file_location("awa_durability_under_test", _DURABILITY_PATH)
DUR = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(DUR)


class DurabilityPrimitiveTest(FinishBase):
    def test_darwin_requires_fsync_then_fullfsync_and_retries_eintr(self) -> None:
        fsync_calls = []
        full_calls = []

        def fsync(fd):
            fsync_calls.append(fd)
            if len(fsync_calls) == 1:
                raise OSError(errno.EINTR, "retry")

        def full(fd, command):
            full_calls.append((fd, command))
            if len(full_calls) == 1:
                raise OSError(errno.EINTR, "retry")
            return 0

        with mock.patch.object(DUR.sys, "platform", "darwin"), \
                mock.patch.object(DUR.os, "fsync", side_effect=fsync), \
                mock.patch.object(DUR.fcntl, "F_FULLFSYNC", 51, create=True), \
                mock.patch.object(DUR.fcntl, "fcntl", side_effect=full):
            DUR._sync_fd(7)
        self.assertEqual(fsync_calls, [7, 7])
        self.assertEqual(full_calls, [(7, 51), (7, 51)])

    def test_darwin_missing_or_failed_fullfsync_never_downgrades(self) -> None:
        with mock.patch.object(DUR.sys, "platform", "darwin"), \
                mock.patch.object(DUR.os, "fsync") as fsync, \
                mock.patch.object(DUR.fcntl, "F_FULLFSYNC", None, create=True), \
                self.assertRaises(OSError):
            DUR._sync_fd(8)
        fsync.assert_called_once_with(8)

        with mock.patch.object(DUR.sys, "platform", "darwin"), \
                mock.patch.object(DUR.os, "fsync"), \
                mock.patch.object(DUR.fcntl, "F_FULLFSYNC", 51, create=True), \
                mock.patch.object(
                    DUR.fcntl, "fcntl",
                    side_effect=OSError(errno.EIO, "full sync failed")), \
                self.assertRaises(OSError):
            DUR._sync_fd(9)

    def test_linux_uses_fsync_without_fullfsync(self) -> None:
        with mock.patch.object(DUR.sys, "platform", "linux"), \
                mock.patch.object(DUR.os, "fsync") as fsync, \
                mock.patch.object(DUR.fcntl, "fcntl") as full:
            DUR._sync_fd(10)
        fsync.assert_called_once_with(10)
        full.assert_not_called()

    def test_nested_private_creation_replace_visibility_adoption_and_unlink(self) -> None:
        nested = Path(self._tmp.name, "durable", "one", "two")
        DUR.ensure_private_directory(str(nested))
        self.assertTrue(nested.is_dir())
        self.assertEqual(nested.stat().st_mode & 0o777, 0o700)

        target = nested / "state.json"
        target.write_bytes(b"old")
        real_sync = DUR.sync_directory
        real_replace = DUR.os.replace
        state = {"replaced": False, "failed": False}

        def fail_replace_parent(path):
            if state["replaced"] and not state["failed"]:
                state["failed"] = True
                raise OSError(errno.EIO, "parent sync failed")
            real_sync(path)

        def mark_replace(source, destination):
            value = real_replace(source, destination)
            state["replaced"] = True
            return value

        with mock.patch.object(DUR.os, "replace", side_effect=mark_replace), \
                mock.patch.object(DUR, "sync_directory", side_effect=fail_replace_parent), \
                self.assertRaises(OSError):
            DUR.atomic_private_replace(str(target), b"new")
        self.assertEqual(target.read_bytes(), b"new")
        DUR.adopt_visible(str(target))

        with mock.patch.object(
                DUR, "sync_parent", side_effect=OSError(errno.EIO, "unlink parent")), \
                self.assertRaises(OSError):
            DUR.durable_unlink(str(target), missing_ok=False)
        self.assertFalse(target.exists())
        DUR.sync_directory(str(target.parent))

    def test_private_directory_refuses_untrusted_link_component(self) -> None:
        outside = Path(self._tmp.name, "outside")
        outside.mkdir()
        state = Path(self._tmp.name, "link-state")
        state.mkdir()
        os.symlink(outside, state / "redirect")
        with self.assertRaises(OSError) as raised:
            DUR.ensure_private_directory(str(state / "redirect" / "nested"))
        self.assertEqual(raised.exception.errno, errno.ELOOP)
        self.assertFalse((outside / "nested").exists())

    def test_generation_visible_after_sync_fault_is_inert_and_not_trusted(self) -> None:
        real = FIN._durability_module().create_private_exclusive

        def visible_then_fail(path, data, **kwargs):
            real(path, data, **kwargs)
            raise OSError(errno.EIO, "post-publication sync uncertainty")

        with mock.patch.object(
                FIN._durability_module(), "create_private_exclusive",
                side_effect=visible_then_fail):
            first = FIN._transition_generation(
                transition="cancelled", conversation_id="durable-generation",
                nonce="nonce", generation=1, root="/tmp/root",
                common_dir="/tmp/common", session_key_value="session")
        self.assertFalse(first["ok"])
        self.assertTrue(first["inert"])
        self.assertTrue(first["created"])
        durability = FIN._durability_module()
        with mock.patch.object(
                durability, "adopt_visible",
                wraps=durability.adopt_visible) as adopted:
            second = FIN._transition_generation(
                transition="cancelled", conversation_id="durable-generation",
                nonce="nonce", generation=1, root="/tmp/root",
                common_dir="/tmp/common", session_key_value="session")
        self.assertTrue(second["ok"])
        self.assertFalse(second["created"])
        self.assertTrue(second["inert"])
        adopted.assert_called()


class DestructiveDurabilityOrderingTest(FinishBase):
    def _prepared_close(self, name: str) -> tuple[str, dict]:
        _repo, wt, _branch = self.ephemeral_wt(name, {"draft.txt": "discard"})
        target = self.targets(wt)
        preview = FIN.preview(
            root=wt, git_dir=target["git_dir"], common_dir=target["common_dir"],
            branch=target["branch"], head=target["head"], session_id="sess",
            conversation_id=name)
        self.assertTrue(preview["ok"], preview)
        return wt, target

    def _finish(self, name: str, wt: str, target: dict) -> dict:
        return FIN.finish_execute(
            root=wt, git_dir=target["git_dir"], common_dir=target["common_dir"],
            branch=target["branch"], head=target["head"], session_id="sess",
            conversation_id=name, answer="Close")

    def _journal_for(self, target: dict, name: str) -> dict:
        matches = FIN._journal_candidates(
            root=target["root"] if "root" in target else "",
            git_dir=target["git_dir"], common_dir=target["common_dir"],
            branch=target["branch"], head=target["head"],
            conversation_id=name, session_id="sess")
        self.assertEqual(len(matches), 1)
        return matches[0]

    def test_worktree_namespace_sync_failure_stops_before_branch_then_recovers(self) -> None:
        name = "durable-remove-parent"
        wt, target = self._prepared_close(name)
        with mock.patch.object(
                FIN, "_sync_removed_worktree_namespaces",
                side_effect=OSError(errno.EIO, "namespace sync failed")):
            result = self._finish(name, wt, target)
        self.assertEqual(result["outcome"], "uncertain", result)
        self.assertFalse(Path(wt).exists())
        self.assertEqual(
            git(target["common_dir"], "show-ref", "--verify",
                "refs/heads/" + target["branch"]).returncode, 0)
        journals, malformed = FIN._journal_scan(
            root=wt, git_dir=target["git_dir"], common_dir=target["common_dir"],
            branch=target["branch"], head=target["head"],
            conversation_id=name, session_id="sess")
        self.assertEqual(malformed, [])
        self.assertEqual(len(journals), 1)
        self.assertEqual(journals[0]["phase"], "prepared")
        self.assertEqual(journals[0]["branch_action"], "")
        self.assertEqual(self.receipts(), [])

        repaired = FIN.reconcile_removal(
            root=wt, git_dir=target["git_dir"], common_dir=target["common_dir"],
            branch=target["branch"], head=target["head"],
            conversation_id=name, session_id="sess")
        self.assertEqual(repaired["outcome"], "removed", repaired)
        self.assertEqual(repaired["branch_action"], "deleted")
        again = FIN.reconcile_removal(
            root=wt, git_dir=target["git_dir"], common_dir=target["common_dir"],
            branch=target["branch"], head=target["head"],
            conversation_id=name, session_id="sess")
        self.assertEqual(again["outcome"], "removed", again)

    def test_branch_backend_sync_failure_leaves_removed_journal_unfinalized(self) -> None:
        name = "durable-branch-backend"
        wt, target = self._prepared_close(name)
        with mock.patch.object(
                FIN, "_sync_git_ref_namespaces",
                side_effect=OSError(errno.EIO, "ref namespace sync failed")):
            result = self._finish(name, wt, target)
        self.assertEqual(result["outcome"], "uncertain", result)
        self.assertFalse(Path(wt).exists())
        journals, malformed = FIN._journal_scan(
            root=wt, git_dir=target["git_dir"], common_dir=target["common_dir"],
            branch=target["branch"], head=target["head"],
            conversation_id=name, session_id="sess")
        self.assertEqual(malformed, [])
        self.assertEqual(len(journals), 1)
        self.assertEqual(journals[0]["phase"], "removed")
        self.assertEqual(journals[0]["branch_action"], "")
        self.assertFalse(journals[0]["receipt_committed"])
        self.assertEqual(self.receipts(), [])

        repaired = FIN.reconcile_removal(
            root=wt, git_dir=target["git_dir"], common_dir=target["common_dir"],
            branch=target["branch"], head=target["head"],
            conversation_id=name, session_id="sess")
        self.assertEqual(repaired["outcome"], "removed", repaired)
        self.assertEqual(repaired["branch_action"], "deleted")
        self.assertTrue(repaired["receipt_committed"])

    def test_namespace_sync_precedes_branch_update_and_journal_receipt(self) -> None:
        name = "durable-order"
        wt, target = self._prepared_close(name)
        events = []
        real_remove_sync = FIN._sync_removed_worktree_namespaces
        real_branch = FIN._finalize_branch_locked
        real_receipt = FIN._write_removed_receipt_locked

        def remove_sync(record):
            events.append("remove_namespace")
            return real_remove_sync(record)

        def branch(record):
            events.append("branch")
            return real_branch(record)

        def receipt(record):
            events.append("receipt")
            return real_receipt(record)

        with mock.patch.object(
                FIN, "_sync_removed_worktree_namespaces", side_effect=remove_sync), \
                mock.patch.object(FIN, "_finalize_branch_locked", side_effect=branch), \
                mock.patch.object(FIN, "_write_removed_receipt_locked", side_effect=receipt):
            result = self._finish(name, wt, target)
        self.assertEqual(result["outcome"], "removed", result)
        self.assertLess(events.index("remove_namespace"), events.index("branch"))
        self.assertLess(events.index("branch"), events.index("receipt"))

    def test_files_and_reftable_backend_namespaces_can_be_certified(self) -> None:
        for ref_format in ("files", "reftable"):
            with self.subTest(ref_format=ref_format):
                repo = Path(self._tmp.name, "refs-" + ref_format)
                repo.mkdir()
                command = ["git", "-C", str(repo), "init", "-q", "-b", "main"]
                if ref_format != "files":
                    command.append("--ref-format=" + ref_format)
                initialized = subprocess.run(
                    command,
                    capture_output=True, text=True)
                if initialized.returncode != 0:
                    if ref_format == "reftable":
                        continue
                    self.fail(initialized.stderr)
                Path(repo, "tracked").write_text("x", encoding="utf-8")
                commit_all(str(repo), "tracked")
                FIN._sync_git_ref_namespaces(
                    str(repo / ".git"), "main")


if __name__ == "__main__":
    import unittest
    unittest.main()
