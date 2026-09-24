"""Native Cursor sessionStart adoption and evidence acceptance tests."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from engine import (
    identity,
    lease as lease_mod,
    lifecycle,
    lock,
    native_entry,
    state as state_mod,
)
from engine.tests.helpers import EngineTestCase, git
from kernel.lib import awa_handoff, awa_roots


_ROOT = Path(__file__).resolve().parents[2]
_HOOK = _ROOT / "kernel" / "hooks" / "awa-session-handoff.sh"
_CLEAN = _ROOT / "kernel" / "bin" / "dev-worktree.sh"


class TestNativeEntry(EngineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.repo = Path(self.make_seeded_repo("native-entry-source"))
        self.policy = Path(self._tmp.name) / "policy.yml"
        self._write_policy()
        self.saved_policy = os.environ.get("AWA_POLICY")
        self.saved_root = os.environ.get("AWA_GOVERNED_ROOT")
        os.environ["AWA_POLICY"] = str(self.policy)
        os.environ["AWA_GOVERNED_ROOT"] = str(self.repo.parent)

    def tearDown(self) -> None:
        if self.saved_policy is None:
            os.environ.pop("AWA_POLICY", None)
        else:
            os.environ["AWA_POLICY"] = self.saved_policy
        if self.saved_root is None:
            os.environ.pop("AWA_GOVERNED_ROOT", None)
        else:
            os.environ["AWA_GOVERNED_ROOT"] = self.saved_root
        super().tearDown()

    def _write_policy(self, *, exclude: str | None = None) -> None:
        excluded = f"  - {exclude}\n" if exclude is not None else "  - never-match\n"
        self.policy.write_text(
            "version: 1\n"
            f"governed_roots:\n  - {self.repo.parent}\n"
            "default: include\n"
            "default_mode: on\n"
            "include:\n  - '*'\n"
            f"exclude:\n{excluded}"
            "detectors:\n"
            "  governed_markers:\n    - _ops/POLICY.md\n"
            "  foreign_hook_frameworks:\n    - pre-commit\n"
            "  read_only_paths: []\n"
            "overrides:\n  include: []\n  exclude: []\n",
            encoding="utf-8",
        )

    def _worktree(self, branch: str = "feat/native") -> Path:
        return Path(self.add_worktree(str(self.repo), branch, suffix=f".{branch.replace('/', '-')}.wt"))

    @staticmethod
    def _payload(root: Path, session: str = "session-one") -> dict:
        return {
            "hook_event_name": "sessionStart",
            "workspace_roots": [str(root)],
            "session_id": session,
        }

    @staticmethod
    def _context(root: Path) -> tuple[str, str, str]:
        branch = git(str(root), "symbolic-ref", "--short", "HEAD").stdout.strip()
        head = git(str(root), "rev-parse", "HEAD").stdout.strip()
        common = str(
            Path(
                git(
                    str(root),
                    "rev-parse",
                    "--path-format=absolute",
                    "--git-common-dir",
                ).stdout.strip()
            ).resolve()
        )
        return branch, head, common

    def _bind_session(self, root: Path, session: str) -> None:
        branch, _head, common = self._context(root)
        heartbeat = awa_roots.heartbeat(
            str(root),
            branch=branch,
            common_dir=common,
            session_id=session,
        )
        self.assertEqual(heartbeat.get("schema"), awa_roots.SCHEMA_ACTIVE_ROOT)
        bound = awa_roots.bind_current_session(
            str(root),
            session_id=session,
            conversation_id=f"conversation-{session}",
            branch=branch,
            common_dir=common,
            source="sessionStart",
        )
        self.assertTrue(bound["ok"], bound)

    def _active_rows(self, root: Path) -> list[dict]:
        with state_mod.State() as state:
            return [
                row
                for row in state.list_leases("active")
                if Path(row["worktree_path"]).resolve() == root.resolve()
            ]

    def test_eligible_linked_session_adopts_attests_and_writes_private_receipt(self):
        root = self._worktree()
        result = native_entry.register_session_start(self._payload(root))
        self.assertEqual((result.result, result.action), ("success", "adopted"))

        lease = lease_mod.read_lease(str(root))
        self.assertIsNotNone(lease)
        self.assertEqual(lease_mod.validate(lease), [])
        self.assertEqual(len(self._active_rows(root)), 1)
        with state_mod.State() as state:
            events = state.events(lease_id=lease["lease_id"])
        self.assertEqual(
            [event["kind"] for event in events[:2]],
            ["attest", "adopt"],
        )

        receipts = native_entry.read_receipts()
        self.assertEqual(len(receipts), 1)
        receipt = receipts[0]
        branch, head, common = self._context(root)
        self.assertEqual(
            {
                "root": receipt["root"],
                "session_id": receipt["session_id"],
                "branch": receipt["branch"],
                "head": receipt["head"],
                "git_common_dir": receipt["git_common_dir"],
                "result": receipt["result"],
                "action": receipt["action"],
                "lease_id": receipt["lease_id"],
            },
            {
                "root": str(root.resolve()),
                "session_id": "session-one",
                "branch": branch,
                "head": head,
                "git_common_dir": common,
                "result": "success",
                "action": "adopted",
                "lease_id": lease["lease_id"],
            },
        )
        receipt_path = native_entry.receipt_path(str(root), "session-one")
        self.assertEqual(stat.S_IMODE(receipt_path.parent.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(receipt_path.stat().st_mode), 0o600)

    def test_existing_valid_lease_attests_without_duplicate_adoption(self):
        root = self._worktree()
        first = native_entry.register_session_start(self._payload(root, "session-one"))
        second = native_entry.register_session_start(self._payload(root, "session-two"))
        self.assertEqual(first.action, "adopted")
        self.assertEqual((second.result, second.action), ("success", "attested"))
        lease = lease_mod.read_lease(str(root))
        with state_mod.State() as state:
            events = state.events(lease_id=lease["lease_id"], limit=20)
        self.assertEqual(sum(event["kind"] == "adopt" for event in events), 1)
        self.assertGreaterEqual(sum(event["kind"] == "attest" for event in events), 2)
        self.assertEqual(len(native_entry.read_receipts()), 2)

    def test_clean_head_advance_repairs_same_lease_then_attests(self):
        root = self._worktree("feat/head-advance")
        first = native_entry.register_session_start(
            self._payload(root, "head-before")
        )
        self.assertEqual(first.action, "adopted")
        before = lease_mod.read_lease(str(root))
        (root / "advance.txt").write_text("advance\n", encoding="utf-8")
        git(str(root), "add", "advance.txt")
        git(str(root), "commit", "-m", "advance native head")
        new_head = git(str(root), "rev-parse", "HEAD").stdout.strip()

        second = native_entry.register_session_start(
            self._payload(root, "head-after")
        )
        self.assertEqual((second.result, second.action), ("success", "repaired"))
        after = lease_mod.read_lease(str(root))
        self.assertEqual(after["lease_id"], before["lease_id"])
        self.assertEqual(after["head"], new_head)
        rows = self._active_rows(root)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["lease_id"], before["lease_id"])
        self.assertEqual(rows[0]["head"], new_head)
        with state_mod.State() as state:
            events = state.events(lease_id=before["lease_id"], limit=20)
        self.assertEqual(sum(event["kind"] == "adopt" for event in events), 1)
        self.assertTrue(
            any(event["kind"] == "native_entry_repair" for event in events)
        )

    def test_concurrent_sessions_have_one_adoption_and_distinct_receipts(self):
        root = self._worktree()
        barrier = threading.Barrier(2)
        results = []
        errors = []

        def enter(session: str) -> None:
            try:
                barrier.wait(timeout=5)
                results.append(
                    native_entry.register_session_start(
                        self._payload(root, session),
                        lock_timeout=10.0,
                    )
                )
            except BaseException as exc:  # pragma: no cover - assertion reports detail
                errors.append(exc)

        threads = [
            threading.Thread(target=enter, args=(f"session-{index}",))
            for index in range(2)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        self.assertFalse(errors)
        self.assertEqual(sorted(result.action for result in results), ["adopted", "attested"])
        self.assertEqual(len(self._active_rows(root)), 1)
        self.assertEqual(
            {receipt["session_id"] for receipt in native_entry.read_receipts()},
            {"session-0", "session-1"},
        )

    def test_multiple_roots_and_sessions_never_overwrite_receipts(self):
        first = self._worktree("feat/first")
        second = self._worktree("feat/second")
        native_entry.register_session_start(self._payload(first, "shared-session"))
        native_entry.register_session_start(self._payload(second, "shared-session"))
        receipts = native_entry.read_receipts()
        self.assertEqual(len(receipts), 2)
        self.assertEqual({receipt["root"] for receipt in receipts}, {str(first), str(second)})
        self.assertNotEqual(
            native_entry.receipt_path(str(first), "shared-session"),
            native_entry.receipt_path(str(second), "shared-session"),
        )

    def test_pending_ensure_for_other_root_is_unchanged(self):
        ensure_root = self._worktree("feat/ensure")
        native_root = self._worktree("feat/native-other")
        pending = awa_handoff.create_pending(str(ensure_root))
        native_entry.register_session_start(self._payload(native_root, "native-session"))
        self.assertEqual(awa_handoff.read_record(), pending)

    def test_dirty_excluded_primary_detached_and_missing_session_never_adopt(self):
        dirty = self._worktree("feat/dirty")
        (dirty / "dirty.txt").write_text("dirty\n", encoding="utf-8")
        dirty_result = native_entry.register_session_start(self._payload(dirty, "dirty"))
        self.assertEqual(dirty_result.result, "failed")
        self.assertIsNone(lease_mod.read_lease(str(dirty)))

        excluded = self._worktree("feat/excluded")
        self._write_policy(exclude="native-entry-source.feat-excluded.wt")
        excluded_result = native_entry.register_session_start(
            self._payload(excluded, "excluded")
        )
        self.assertEqual(excluded_result.result, "failed")
        self.assertIsNone(lease_mod.read_lease(str(excluded)))
        self._write_policy()

        primary_result = native_entry.register_session_start(
            self._payload(self.repo, "primary")
        )
        self.assertEqual(primary_result.result, "failed")
        self.assertIsNone(lease_mod.read_lease(str(self.repo)))

        detached = self._worktree("feat/detached")
        git(str(detached), "checkout", "--detach", "-q")
        detached_result = native_entry.register_session_start(
            self._payload(detached, "detached")
        )
        self.assertEqual(detached_result.result, "failed")
        self.assertIsNone(lease_mod.read_lease(str(detached)))

        missing_session = native_entry.register_session_start(
            {
                "hook_event_name": "sessionStart",
                "workspace_roots": [str(self._worktree("feat/no-session"))],
            }
        )
        self.assertEqual(missing_session.result, "failed")

    def test_in_progress_git_operation_is_preserved_without_adoption(self):
        root = self._worktree("feat/operation")
        identity_value = lifecycle.observe_identity(str(root))
        marker = Path(identity_value.git_dir) / "MERGE_HEAD"
        marker.write_text(identity_value.head + "\n", encoding="ascii")
        before = marker.read_bytes()
        result = native_entry.register_session_start(
            self._payload(root, "operation")
        )
        self.assertEqual(result.result, "failed")
        self.assertEqual(marker.read_bytes(), before)
        self.assertIsNone(lease_mod.read_lease(str(root)))
        self.assertEqual(self._active_rows(root), [])

    def test_malformed_mismatched_and_symlinked_state_is_preserved(self):
        malformed = self._worktree("feat/malformed")
        awa_dir = malformed / ".awa"
        awa_dir.mkdir(mode=0o700)
        malformed_path = awa_dir / "lease.json"
        malformed_path.write_text('{"schema":', encoding="utf-8")
        malformed_path.chmod(0o600)
        before = malformed_path.read_bytes()
        malformed_result = native_entry.register_session_start(
            self._payload(malformed, "malformed")
        )
        self.assertEqual(malformed_result.result, "conflict")
        self.assertEqual(malformed_path.read_bytes(), before)
        self.assertEqual(self._active_rows(malformed), [])

        symlinked = self._worktree("feat/symlink-state")
        symlink_dir = symlinked / ".awa"
        symlink_dir.mkdir(mode=0o700)
        outside = Path(self._tmp.name) / "outside-lease.json"
        outside.write_text("outside\n", encoding="utf-8")
        (symlink_dir / "lease.json").symlink_to(outside)
        symlink_result = native_entry.register_session_start(
            self._payload(symlinked, "symlink-state")
        )
        self.assertEqual(symlink_result.result, "conflict")
        self.assertEqual(outside.read_text(encoding="utf-8"), "outside\n")
        self.assertTrue((symlink_dir / "lease.json").is_symlink())
        self.assertEqual(self._active_rows(symlinked), [])

        mismatched = self._worktree("feat/db-conflict")
        branch, head, common = self._context(mismatched)
        conflicting = lease_mod.build_lease(
            str(mismatched),
            branch + "-other",
            common,
            head=head,
            boot="conflicting-boot",
        )
        with state_mod.State() as state:
            state.upsert_lease(conflicting)
        mismatch_result = native_entry.register_session_start(
            self._payload(mismatched, "db-conflict")
        )
        self.assertEqual(mismatch_result.result, "conflict")
        self.assertIsNone(lease_mod.read_lease(str(mismatched)))
        self.assertEqual(
            [row["lease_id"] for row in self._active_rows(mismatched)],
            [conflicting["lease_id"]],
        )

    def test_symlinked_root_and_ambiguous_payload_are_rejected_without_receipt(self):
        root = self._worktree("feat/symlink-root")
        alias = Path(self._tmp.name) / "root-alias"
        alias.symlink_to(root, target_is_directory=True)
        result = native_entry.register_session_start(self._payload(alias, "symlink-root"))
        self.assertEqual(result.result, "failed")
        self.assertIsNone(lease_mod.read_lease(str(root)))

        ambiguous = native_entry.register_session_start(
            {
                "hook_event_name": "sessionStart",
                "workspace_roots": [str(root), str(self.repo)],
                "session_id": "ambiguous",
            }
        )
        self.assertEqual(ambiguous.result, "failed")
        self.assertEqual(native_entry.read_receipts(), [])

    def test_symlinked_receipt_state_is_preserved_before_adoption(self):
        root = self._worktree("feat/symlink-receipt")
        receipt = native_entry.receipt_path(str(root), "symlink-receipt")
        receipt.parent.mkdir(parents=True, mode=0o700)
        outside = Path(self._tmp.name) / "outside-receipt.json"
        outside.write_text("outside receipt\n", encoding="utf-8")
        receipt.symlink_to(outside)
        result = native_entry.register_session_start(
            self._payload(root, "symlink-receipt")
        )
        self.assertEqual(result.result, "conflict")
        self.assertEqual(outside.read_text(encoding="utf-8"), "outside receipt\n")
        self.assertTrue(receipt.is_symlink())
        self.assertIsNone(lease_mod.read_lease(str(root)))

    def test_symlinked_state_root_is_preserved_before_adoption(self):
        root = self._worktree("feat/symlink-state-root")
        state_root = self.state_home / "awa"
        outside = Path(self._tmp.name) / "outside-state"
        outside.mkdir(mode=0o700)
        state_root.symlink_to(outside, target_is_directory=True)
        result = native_entry.register_session_start(
            self._payload(root, "symlink-state-root")
        )
        self.assertEqual(result.result, "conflict")
        self.assertTrue(state_root.is_symlink())
        self.assertEqual(list(outside.iterdir()), [])
        self.assertIsNone(lease_mod.read_lease(str(root)))

    def test_disk_and_sqlite_asymmetry_repairs_only_exact_identity(self):
        disk_only = self._worktree("feat/disk-only")
        context = lifecycle.observe_identity(str(disk_only))
        disk_lease = lease_mod.build_lease(
            context.root,
            context.branch,
            context.git_common_dir,
            head=context.head,
            boot="disk-only-boot",
        )
        lease_mod.create_lease(str(disk_only), disk_lease)
        disk_result = native_entry.register_session_start(
            self._payload(disk_only, "disk-only")
        )
        self.assertEqual((disk_result.result, disk_result.action), ("success", "repaired"))
        self.assertEqual(
            [row["lease_id"] for row in self._active_rows(disk_only)],
            [disk_lease["lease_id"]],
        )

        db_only = self._worktree("feat/db-only")
        db_context = lifecycle.observe_identity(str(db_only))
        db_lease = lease_mod.build_lease(
            db_context.root,
            db_context.branch,
            db_context.git_common_dir,
            head=db_context.head,
            boot="db-only-boot",
        )
        with state_mod.State() as state:
            state.upsert_lease(db_lease)
        db_result = native_entry.register_session_start(
            self._payload(db_only, "db-only")
        )
        self.assertEqual((db_result.result, db_result.action), ("success", "repaired"))
        self.assertEqual(lease_mod.read_lease(str(db_only))["lease_id"], db_lease["lease_id"])

    def test_identity_drift_never_writes_success(self):
        for field, value in (
            ("branch", "feat/drifted"),
            ("head", "f" * 40),
            ("git_common_dir", str(Path(self._tmp.name) / "other" / ".git")),
        ):
            with self.subTest(field=field):
                root = self._worktree(f"feat/drift-{field}")
                observed = lifecycle.observe_identity(str(root))
                drifted = replace(observed, **{field: value})
                with mock.patch.object(
                    native_entry,
                    "_observe_identity",
                    side_effect=[observed, drifted],
                ):
                    result = native_entry.register_session_start(
                        self._payload(root, f"drift-{field}")
                    )
                self.assertEqual(result.result, "mismatched")
                self.assertIsNone(lease_mod.read_lease(str(root)))
                self.assertEqual(self._active_rows(root), [])
                self.assertFalse(
                    any(
                        receipt["result"] == "success"
                        and receipt["root"] == str(root.resolve())
                        for receipt in native_entry.read_receipts()
                    )
                )

    def test_lock_contention_and_registration_exception_are_fail_open(self):
        root = self._worktree("feat/lock")
        with mock.patch.object(
            lock,
            "common_dir_lock",
            side_effect=lock.LockBusy("busy"),
        ):
            busy = native_entry.register_session_start(
                self._payload(root, "busy"),
                lock_timeout=0.0,
            )
        self.assertEqual(busy.result, "failed")
        self.assertIsNone(lease_mod.read_lease(str(root)))

        exception_root = self._worktree("feat/exception")
        with mock.patch.object(
            native_entry,
            "_register_under_lock",
            side_effect=RuntimeError("private detail must not escape"),
        ):
            failed = native_entry.register_session_start(
                self._payload(exception_root, "exception")
            )
        self.assertEqual(failed.result, "failed")
        self.assertNotIn("private detail", failed.reason)
        self.assertIsNone(lease_mod.read_lease(str(exception_root)))

        timeout_root = self._worktree("feat/timeout")
        with mock.patch.object(
            native_entry,
            "_git",
            side_effect=subprocess.TimeoutExpired(["git"], 2),
        ):
            timed_out = native_entry.register_session_start(
                self._payload(timeout_root, "timeout")
            )
        self.assertEqual(timed_out.result, "failed")
        self.assertIsNone(lease_mod.read_lease(str(timeout_root)))

    def test_receipt_precedes_lifecycle_commit_and_crash_stays_explicit(self):
        root = self._worktree("feat/receipt-order")
        real_write = native_entry._write_receipt
        calls = 0

        class Crash(BaseException):
            pass

        def crash_after_pending(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                return real_write(*args, **kwargs)
            raise Crash()

        with mock.patch.object(
            native_entry,
            "_write_receipt",
            side_effect=crash_after_pending,
        ):
            result = native_entry.register_session_start(
                self._payload(root, "receipt-order")
            )
        self.assertEqual(result.result, "failed")
        self.assertIsNotNone(lease_mod.read_lease(str(root)))
        self.assertEqual(len(self._active_rows(root)), 1)
        receipt = native_entry.read_receipts()[0]
        self.assertEqual(receipt["result"], "failed")
        self.assertEqual(receipt["reason"], "registration_pending")
        self.assertIsNone(receipt["lease_id"])

        retried = native_entry.register_session_start(
            self._payload(root, "receipt-order")
        )
        self.assertEqual((retried.result, retried.action), ("success", "attested"))
        final = native_entry.read_receipts()[0]
        self.assertEqual(final["result"], "success")
        self.assertGreater(final["generation"], receipt["generation"])

    def test_receipt_evidence_requires_current_exact_root_session_and_git_identity(self):
        root = self._worktree("feat/evidence")
        native_entry.register_session_start(self._payload(root, "evidence"))
        self.assertEqual(native_entry.evidence_state(), "stale")
        self._bind_session(root, "evidence")
        self.assertEqual(native_entry.evidence_state(), "success")
        git(str(root), "checkout", "-q", "-b", "feat/evidence-drift")
        self.assertEqual(native_entry.evidence_state(), "stale")

    def test_receipt_or_lease_never_bypasses_independent_cleanup_gates(self):
        root = self._worktree("feat/cleanup")
        native_entry.register_session_start(self._payload(root, "cleanup"))
        branch, _head, common = self._context(root)
        awa_roots.heartbeat(
            str(root),
            branch=branch,
            common_dir=common,
            session_id="cleanup",
        )
        env = {
            **os.environ,
            "AWA_POLICY": str(self.policy),
            "AWA_ROOTS_LIB": str(_ROOT / "kernel" / "lib" / "awa_roots.py"),
        }
        active = subprocess.run(
            ["bash", str(_CLEAN), "clean", "--path", str(root)],
            cwd=self.repo,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertNotEqual(active.returncode, 0)
        self.assertIn("ACTIVE Safe Workspace", active.stderr)
        self.assertTrue(root.is_dir())

        (root / "dirty.txt").write_text("preserve\n", encoding="utf-8")
        dirty = subprocess.run(
            ["bash", str(_CLEAN), "clean", "--path", str(root)],
            cwd=self.repo,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertNotEqual(dirty.returncode, 0)
        self.assertIn("dirty", dirty.stderr)
        self.assertTrue(root.is_dir())

    def test_shell_dispatcher_is_quiet_and_fail_open_without_engine(self):
        fake_root = Path(self._tmp.name) / "runtime"
        hook = fake_root / "kernel" / "hooks" / _HOOK.name
        hook.parent.mkdir(parents=True)
        hook.write_bytes(_HOOK.read_bytes())
        hook.chmod(0o700)
        result = subprocess.run(
            ["bash", str(hook)],
            input=json.dumps(self._payload(self._worktree("feat/no-engine"), "no-engine")),
            cwd=self.repo,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))


if __name__ == "__main__":
    unittest.main()
