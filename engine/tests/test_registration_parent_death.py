"""V7 durable spawn-intent and observation-only reconciliation tests."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from engine import registration_launcher as launcher


BOOT = "a" * 64


def _parent_version(pid: int, boot_id: str = BOOT) -> str:
    return launcher.pidversion(pid, 1, 2, boot_id)


def _child_version(pid: int, boot_id: str = BOOT) -> str:
    return launcher.pidversion(pid, 3, 4, boot_id)


def _intent(
    nonce: str,
    *,
    phase: str,
    parent_pid: int = 100,
    child_pid: int | None = 200,
    boot_id: str = BOOT,
) -> launcher.SpawnIntent:
    return launcher.SpawnIntent.create(
        nonce=nonce,
        route="startup",
        phase=phase,
        boot_id=boot_id,
        parent_pid=parent_pid,
        parent_pidversion=_parent_version(parent_pid, boot_id),
        child_pid=child_pid,
        child_pidversion=(
            _child_version(child_pid, boot_id)
            if child_pid is not None
            else None
        ),
        private_executable_path="/Library/Application Support/AWA/runtime/"
        "versions/" + "1" * 64 + "/Python.app/Contents/MacOS/Python",
        private_executable_sha256="2" * 64,
        runtime_manifest_sha256="1" * 64,
        version_lock_identity="3" * 64,
        mapped_vnode_dev="10" if child_pid is not None else None,
        mapped_vnode_ino="11" if child_pid is not None else None,
        created_wall_ns="1",
        updated_wall_ns=None if phase == "PREPARED" else "2",
    )


class DurableIntentTest(unittest.TestCase):
    def test_filesystem_store_fsyncs_reopens_and_refuses_unknown_residue(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="awa-intents.") as raw:
            root = Path(raw).resolve() / "v1"
            root.mkdir(mode=0o700)
            store = launcher.FilesystemIntentStore(
                root, expected_uid=os.getuid()
            )
            intent = _intent("9" * 64, phase="PREPARED", child_pid=None)
            store.create(intent)
            reopened = launcher.FilesystemIntentStore(
                root, expected_uid=os.getuid(), create=False
            )
            self.assertEqual(reopened[intent.nonce], intent)
            reopened.transition(
                intent.nonce,
                "SPAWNED",
                child_pid=200,
                child_pidversion=_child_version(200),
                mapped_vnode_dev="10",
                mapped_vnode_ino="11",
                published_wall_ns="2",
            )
            self.assertEqual(reopened[intent.nonce].phase, "SPAWNED")
            with self.assertRaises((FileExistsError, launcher.ProtocolRefusal)):
                store.create(intent)
            residue = root / "untrusted"
            residue.write_bytes(b"x")
            residue.chmod(0o600)
            with self.assertRaises(launcher.ProtocolRefusal):
                reopened.values()

    def test_phase_updates_are_durable_and_monotonic(self) -> None:
        store = launcher.InMemoryIntentStore()
        intent = _intent("a" * 64, phase="PREPARED", child_pid=None)
        store.create(intent)
        for phase in (
            "SPAWNED",
            "READY",
            "GO",
            "PRODUCT",
            "TERMINAL",
        ):
            store.transition(
                intent.nonce,
                phase,
                child_pid=200 if phase == "SPAWNED" else None,
                child_pidversion=(
                    launcher.pidversion(200, 1, 2, BOOT)
                    if phase == "SPAWNED"
                    else None
                ),
                mapped_vnode_dev="10" if phase == "SPAWNED" else None,
                mapped_vnode_ino="11" if phase == "SPAWNED" else None,
                terminal_reason=(
                    "NORMAL_EXIT" if phase == "TERMINAL" else None
                ),
            )
        self.assertEqual(store[intent.nonce].phase, "TERMINAL")
        self.assertEqual(
            tuple(store.events),
            (
                "create:PREPARED",
                "sync:file",
                "sync:directory",
                "transition:SPAWNED",
                "sync:file",
                "sync:directory",
                "transition:READY",
                "sync:file",
                "sync:directory",
                "transition:GO",
                "sync:file",
                "sync:directory",
                "transition:PRODUCT",
                "sync:file",
                "sync:directory",
                "transition:TERMINAL",
                "sync:file",
                "sync:directory",
            ),
        )
        with self.assertRaises(ValueError):
            store.transition(intent.nonce, "READY")

    def test_spawn_failure_is_recorded_before_any_cleanup(self) -> None:
        store = launcher.InMemoryIntentStore()
        intent = _intent("b" * 64, phase="PREPARED", child_pid=None)
        store.create(intent)
        store.transition(
            intent.nonce,
            "TERMINAL",
            terminal_reason="SPAWN_FAILED",
        )
        self.assertIn(intent.nonce, store)
        self.assertEqual(store[intent.nonce].phase, "TERMINAL")
        self.assertEqual(
            store[intent.nonce].terminal_reason,
            "SPAWN_FAILED",
        )


class ObservationOnlyReconciliationTest(unittest.TestCase):
    def test_every_live_parent_phase_is_preserved(self) -> None:
        phases = launcher.SPAWN_PHASES
        for phase in phases:
            with self.subTest(phase=phase):
                child = None if phase == "PREPARED" else 200
                intent = _intent("c" * 64, phase=phase, child_pid=child)
                store = launcher.InMemoryIntentStore([intent])
                observer = launcher.FakeProcessObserver(
                    BOOT,
                    live={
                        (100, _parent_version(100)): True,
                        (200, _child_version(200)): child is not None,
                    },
                )
                results = launcher.IntentReconciler(observer).reconcile(store)
                self.assertEqual(results[0].outcome, "HEALTHY_PAIR_PRESERVED")
                self.assertIn(intent.nonce, store)
                self.assertEqual(observer.signals, [])

    def test_parent_exit_during_scan_never_authorizes_cleanup(self) -> None:
        intent = _intent("d" * 64, phase="GO")
        store = launcher.InMemoryIntentStore([intent])
        observer = launcher.FakeProcessObserver(
            BOOT,
            scripted_liveness={
                (100, _parent_version(100)): [True, False],
                (200, _child_version(200)): [True],
            },
        )
        results = launcher.IntentReconciler(observer).reconcile(store)
        self.assertEqual(results[0].outcome, "HEALTHY_PAIR_PRESERVED")
        self.assertIn(intent.nonce, store)
        self.assertEqual(observer.signals, [])

    def test_pre_watchdog_residue_refuses_with_reboot_requirement(self) -> None:
        intent = _intent(
            "e" * 64,
            phase="PREPARED",
            child_pid=None,
        )
        store = launcher.InMemoryIntentStore([intent])
        observer = launcher.FakeProcessObserver(
            BOOT,
            live={(100, _parent_version(100)): False},
        )
        result = launcher.IntentReconciler(observer).reconcile(store)[0]
        self.assertEqual(result.outcome, "RESIDUE_REFUSED")
        self.assertEqual(
            result.operator_message,
            launcher.AMBIGUOUS_RESIDUE_MESSAGE,
        )
        self.assertIn(intent.nonce, store)
        self.assertEqual(observer.signals, [])

    def test_child_is_only_observed_and_may_exit_naturally(self) -> None:
        intent = _intent("f" * 64, phase="GO")
        store = launcher.InMemoryIntentStore([intent])
        observer = launcher.FakeProcessObserver(
            BOOT,
            live={
                (100, _parent_version(100)): False,
                (200, _child_version(200)): True,
            },
            wait_results={(200, _child_version(200)): True},
        )
        result = launcher.IntentReconciler(observer).reconcile(store)[0]
        self.assertEqual(result.outcome, "NATURAL_EXIT_RECONCILED")
        self.assertEqual(store[intent.nonce].phase, "TERMINAL")
        self.assertEqual(
            store[intent.nonce].terminal_reason,
            "NATURAL_EXIT_RECONCILED",
        )
        self.assertEqual(observer.signals, [])

    def test_persistent_child_refuses_without_signalling(self) -> None:
        intent = _intent("0" * 64, phase="PRODUCT")
        store = launcher.InMemoryIntentStore([intent])
        observer = launcher.FakeProcessObserver(
            BOOT,
            live={
                (100, _parent_version(100)): False,
                (200, _child_version(200)): True,
            },
            wait_results={(200, _child_version(200)): False},
        )
        result = launcher.IntentReconciler(observer).reconcile(store)[0]
        self.assertEqual(result.outcome, "RESIDUE_REFUSED")
        self.assertEqual(
            result.operator_message,
            launcher.CONFIRMED_INERT_MESSAGE,
        )
        self.assertIn(intent.nonce, store)
        self.assertEqual(observer.signals, [])

    def test_new_boot_clears_old_boot_record_without_pid_observation(self) -> None:
        intent = _intent("1" * 64, phase="PRODUCT", boot_id="b" * 64)
        store = launcher.InMemoryIntentStore([intent])
        observer = launcher.FakeProcessObserver(BOOT, live={})
        result = launcher.IntentReconciler(observer).reconcile(store)[0]
        self.assertEqual(result.outcome, "REBOOT_CLEARED")
        self.assertNotIn(intent.nonce, store)
        self.assertEqual(
            store.archived[intent.nonce].terminal_reason,
            "REBOOT_CLEARED",
        )
        self.assertEqual(observer.observations, [])
        self.assertEqual(observer.signals, [])

    def test_concurrent_live_parent_is_not_disturbed_by_dead_record(self) -> None:
        live = _intent("2" * 64, phase="READY", parent_pid=101, child_pid=201)
        dead = _intent("3" * 64, phase="PRODUCT", parent_pid=102, child_pid=202)
        store = launcher.InMemoryIntentStore([live, dead])
        observer = launcher.FakeProcessObserver(
            BOOT,
            live={
                (101, _parent_version(101)): True,
                (201, _child_version(201)): True,
                (102, _parent_version(102)): False,
                (202, _child_version(202)): False,
            },
        )
        results = launcher.IntentReconciler(observer).reconcile(store)
        self.assertEqual(
            {result.nonce: result.outcome for result in results},
            {
                live.nonce: "HEALTHY_PAIR_PRESERVED",
                dead.nonce: "RESIDUE_REFUSED",
            },
        )
        self.assertIn(live.nonce, store)
        self.assertIn(dead.nonce, store)
        self.assertEqual(observer.signals, [])


if __name__ == "__main__":
    unittest.main()
