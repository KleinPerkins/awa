"""M2.2: digest-bound, row-authorized integrity repair actions."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from engine import (
    integrity_repair,
    lifecycle,
    lifecycle_reconcile,
    lock,
    paths,
    recovery,
    state as state_mod,
)
from engine.tests.helpers import EngineTestCase


def _observation(
    path: str,
    lease: dict | None,
    *,
    root_exists: bool = False,
    registered: bool = False,
    disposition: str = "dead",
    live_session: bool = False,
    lease_on_disk: bool = False,
    ambiguity: bool = False,
) -> lifecycle_reconcile._Observation:
    registration = None
    if registered:
        registration = lifecycle_reconcile.GitRegistration(
            path=path,
            git_common_dir=str((Path(path).parent / "repo" / ".git").resolve()),
            linked=True,
            dirty=False,
            cached_remote=True,
        )
    return lifecycle_reconcile._Observation(
        path=path,
        lease=copy.deepcopy(lease),
        registration=registration,
        registration_known=True,
        root_exists=root_exists,
        lease_on_disk=lease_on_disk,
        disposition=disposition,
        live_session=live_session,
        journal_or_recovery_ambiguous=ambiguity,
    )


class TestIntegrityRepair(EngineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.target = str((Path(self._tmp.name) / "absent-worktree").resolve())
        self.common_dir = str((Path(self._tmp.name) / "repo" / ".git").resolve())
        Path(self.common_dir).mkdir(parents=True)
        with state_mod.State() as state:
            state.upsert_lease(
                {
                    "lease_id": "awa1-repair",
                    "worktree_path": self.target,
                    "branch": "feat/retire",
                    "git_common_dir": self.common_dir,
                    "boot_id": "old-boot",
                    "base_ref": "main",
                    "head": "1" * 40,
                    "status": "active",
                    "created_at": "2000-01-01T00:00:00Z",
                    "attested_at": "2000-01-01T00:00:00Z",
                    "pid": 999999,
                }
            )
            self.lease = state.get_lease("awa1-repair")
        self.retire_observation = _observation(self.target, self.lease)

    def _plan(self, *observations) -> dict:
        selected = observations or (self.retire_observation,)
        with mock.patch.object(
            lifecycle_reconcile,
            "_observations",
            return_value=list(selected),
        ):
            return integrity_repair.build_plan()

    def _apply_retire(self, plan: dict, *, fault=None):
        action = plan["actions"][0]
        with mock.patch.object(
            lifecycle_reconcile,
            "_observations",
            return_value=[self.retire_observation],
        ):
            return integrity_repair.apply(
                plan["plan_digest"],
                action["kind"],
                action["authorization"],
                fault=fault,
            )

    def _valid_capture(self, path: str, **_kwargs) -> integrity_repair.Capture:
        result = recovery.create_worktree_archive(
            path,
            recovery_dir=paths.recovery_dir(),
        )
        return integrity_repair.Capture(
            archive=result.archive,
            manifest=result.manifest,
            protected=result.protected,
            skipped_secrets=tuple(result.skipped_secrets),
            skipped_symlink_escape=tuple(result.skipped_symlink_escape),
        )

    def test_plan_is_read_only(self):
        db = Path(self.state_home) / "awa" / "state.db"
        before_db = hashlib.sha256(db.read_bytes()).hexdigest()
        before_tree = sorted(
            str(path.relative_to(self.state_home))
            for path in self.state_home.rglob("*")
        )

        first = self._plan()
        second = self._plan()

        self.assertEqual(first, second)
        self.assertEqual(first["schema"], integrity_repair.PLAN_SCHEMA)
        self.assertEqual(len(first["actions"]), 1)
        self.assertEqual(
            hashlib.sha256(db.read_bytes()).hexdigest(),
            before_db,
        )
        self.assertEqual(
            sorted(
                str(path.relative_to(self.state_home))
                for path in self.state_home.rglob("*")
            ),
            before_tree,
        )

    def test_apply_refuses_without_matching_digest_or_row_authorization(self):
        second_lease = dict(self.lease)
        second_lease.update(
            lease_id="awa1-repair-2",
            worktree_path=str((Path(self._tmp.name) / "absent-two").resolve()),
        )
        with state_mod.State() as state:
            state.upsert_lease(second_lease)
            second_lease = state.get_lease("awa1-repair-2")
        second = _observation(second_lease["worktree_path"], second_lease)
        plan = self._plan(self.retire_observation, second)
        self.assertEqual(len(plan["actions"]), 2)
        self.assertEqual(
            {action["kind"] for action in plan["actions"]},
            {"retire-bookkeeping"},
        )
        self.assertEqual(
            len({action["authorization"] for action in plan["actions"]}),
            2,
        )

        with mock.patch.object(
            lifecycle_reconcile,
            "_observations",
            return_value=[self.retire_observation, second],
        ):
            for digest, authorization in (
                ("0" * 64, plan["actions"][0]["authorization"]),
                (plan["plan_digest"], ""),
                (plan["plan_digest"], "wrong-row"),
            ):
                with self.subTest(digest=digest, authorization=authorization):
                    with self.assertRaises(integrity_repair.RepairRefused):
                        integrity_repair.apply(
                            digest,
                            "retire-bookkeeping",
                            authorization,
                        )
        with state_mod.State() as state:
            self.assertEqual(state.get_lease("awa1-repair")["status"], "active")
            self.assertEqual(state.get_lease("awa1-repair-2")["status"], "active")

    def test_digest_binds_every_safety_relevant_input(self):
        action = self._plan()["actions"][0]
        core = {
            key: copy.deepcopy(value)
            for key, value in action.items()
            if key not in {"authorization", "authorization_sha256"}
        }
        baseline = integrity_repair._plan_from_actions([core])["plan_digest"]
        variants = (
            ("kind", "remove-worktree"),
            ("target", self.target + "-changed"),
            ("lease_id", "awa1-other"),
            ("stored_row.head", "2" * 40),
            ("classification.topology", "unknown"),
            ("evidence.path_exists", True),
            ("evidence.git_registered", True),
            ("evidence.lease_on_disk", True),
            ("evidence.live_session", True),
            ("evidence.journal_or_recovery_ambiguous", True),
            ("evidence.disposition", "active"),
            ("live_git.head", "3" * 40),
        )
        for dotted, value in variants:
            changed = copy.deepcopy(core)
            parent = changed
            parts = dotted.split(".")
            for part in parts[:-1]:
                if parent.get(part) is None:
                    parent[part] = {}
                parent = parent[part]
            parent[parts[-1]] = value
            with self.subTest(field=dotted):
                self.assertNotEqual(
                    integrity_repair._plan_from_actions([changed])["plan_digest"],
                    baseline,
                )

    def test_apply_refuses_unknown_action_kind(self):
        plan = self._plan()
        with self.assertRaises(integrity_repair.RepairRefused):
            integrity_repair.apply(
                plan["plan_digest"],
                "future-action",
                plan["actions"][0]["authorization"],
            )

    def test_retire_bookkeeping_updates_sqlite_only_no_path_or_ref(self):
        marker = Path(self.common_dir) / "refs-marker"
        marker.write_text("untouched", encoding="utf-8")
        plan = self._plan()
        result = self._apply_retire(plan)

        self.assertEqual(result["result"], "retired")
        self.assertFalse(os.path.lexists(self.target))
        self.assertEqual(marker.read_text(encoding="utf-8"), "untouched")
        with state_mod.State() as state:
            row = state.get_lease("awa1-repair")
            self.assertEqual(row["status"], "retired")
            events = state.events("awa1-repair")
        self.assertEqual(events[0]["kind"], "integrity_repair_retire_bookkeeping")
        detail = json.loads(events[0]["detail"])
        self.assertEqual(detail["rollback"]["prior_status"], "active")
        self.assertEqual(detail["plan_digest"], plan["plan_digest"])
        self.assertNotIn(plan["actions"][0]["authorization"], events[0]["detail"])
        self.assertEqual(
            detail["authorization_sha256"],
            hashlib.sha256(
                plan["actions"][0]["authorization"].encode("utf-8")
            ).hexdigest(),
        )
        with self.assertRaises(integrity_repair.RepairRefused):
            self._apply_retire(plan)

    def test_retire_bookkeeping_holds_stored_git_common_dir_lock(self):
        plan = self._plan()
        real_lock = lock.common_dir_lock
        observed = []

        def recording(common_dir, **kwargs):
            observed.append(common_dir)
            return real_lock(common_dir, **kwargs)

        with mock.patch.object(lock, "common_dir_lock", side_effect=recording):
            self._apply_retire(plan)
        self.assertEqual(observed, [self.lease["git_common_dir"]])

    def test_retire_bookkeeping_does_not_call_lifecycle_retire(self):
        plan = self._plan()
        with mock.patch.object(
            lifecycle,
            "retire",
            side_effect=AssertionError("lifecycle.retire must not be called"),
        ) as retire:
            self._apply_retire(plan)
        retire.assert_not_called()

    def test_retire_bookkeeping_refuses_if_evidence_incomplete(self):
        variants = {
            "root": {"root_exists": True},
            "registered": {"registered": True},
            "active": {"disposition": "active"},
            "session": {"live_session": True},
            "lease": {"lease_on_disk": True},
            "ambiguity": {"ambiguity": True},
        }
        for name, overrides in variants.items():
            with self.subTest(name=name):
                incomplete = _observation(
                    self.target,
                    self.lease,
                    **overrides,
                )
                plan = self._plan(incomplete)
                self.assertEqual(plan["actions"], [])

    def test_remove_worktree_routes_through_clean_path_gate(self):
        action, observation = self._remove_action()
        plan = self._plan(observation)
        self.assertEqual(plan["actions"][0]["kind"], "remove-worktree")
        calls = []

        def capture(path, **_kwargs):
            calls.append(("capture", path))
            return self._valid_capture(path)

        def clean_runner(argv):
            calls.append(("clean", tuple(argv)))
            return integrity_repair.CleanResult(
                returncode=0,
                stdout="",
                stderr="",
                receipt={
                    "schema": "clean_receipt/v1",
                    "receipt_id": "receipt-1",
                    "disposition": "removed",
                    "path": action["target"],
                    "branch": action["live_git"]["branch"],
                    "head": action["live_git"]["head"],
                    "git_common_dir": action["live_git"]["git_common_dir"],
                    "flags": {
                        "bundle": True,
                        "force": False,
                        "delete_branch": False,
                    },
                },
            )

        with mock.patch.object(
            lifecycle_reconcile,
            "_observations",
            return_value=[observation],
        ):
            result = integrity_repair.apply(
                plan["plan_digest"],
                "remove-worktree",
                plan["actions"][0]["authorization"],
                capture=capture,
                clean_runner=clean_runner,
            )
        self.assertEqual(result["result"], "removed")
        self.assertEqual(calls[0], ("capture", action["target"]))
        clean_argv = calls[1][1]
        self.assertEqual(clean_argv[-4:], ("clean", "--path", action["target"], "--bundle"))
        self.assertNotIn("--force", clean_argv)
        self.assertNotIn("--delete-branch", clean_argv)

    def test_remove_worktree_default_clean_fixture_end_to_end(self):
        action, observation = self._remove_action()
        plan = self._plan(observation)
        with mock.patch.object(
            lifecycle_reconcile,
            "_observations",
            return_value=[observation],
        ):
            result = integrity_repair.apply(
                plan["plan_digest"],
                "remove-worktree",
                plan["actions"][0]["authorization"],
            )

        self.assertEqual(result["result"], "removed")
        self.assertFalse(os.path.lexists(action["target"]))
        manifests = list(paths.recovery_dir().glob("*.worktree.manifest.json"))
        self.assertEqual(len(manifests), 1)
        capture = json.loads(manifests[0].read_text(encoding="utf-8"))
        self.assertIs(capture["protected"], True)
        self.assertEqual(capture["skipped_secrets"], [])
        self.assertEqual(capture["skipped_symlink_escape"], [])
        receipts = list(paths.receipts_dir().glob("clean-*.json"))
        self.assertEqual(len(receipts), 1)
        receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
        self.assertEqual(receipt["disposition"], "removed")
        self.assertEqual(receipt["path"], action["target"])
        self.assertEqual(
            receipt["flags"],
            {"bundle": True, "force": False, "delete_branch": False},
        )

    def test_remove_worktree_refuses_active_root(self):
        _action, observation = self._remove_action()
        plan = self._plan(observation)
        active = replace(
            observation,
            disposition="active",
            live_session=True,
        )
        capture = mock.Mock(side_effect=self._valid_capture)
        clean_runner = mock.Mock()
        with mock.patch.object(
            lifecycle_reconcile,
            "_observations",
            side_effect=[[observation], [active]],
        ):
            with self.assertRaises(integrity_repair.RepairRefused):
                integrity_repair.apply(
                    plan["plan_digest"],
                    "remove-worktree",
                    plan["actions"][0]["authorization"],
                    capture=capture,
                    clean_runner=clean_runner,
                )
        capture.assert_called_once()
        clean_runner.assert_not_called()

    def test_remove_worktree_is_reversible_and_refuses_incomplete_capture(self):
        _action, observation = self._remove_action()
        plan = self._plan(observation)
        clean_runner = mock.Mock()
        for field in ("skipped_secrets", "skipped_symlink_escape"):
            capture = mock.Mock(
                return_value=integrity_repair.Capture(
                    archive="/capture",
                    manifest="/manifest",
                    protected=True,
                    skipped_secrets=("blocked",) if field == "skipped_secrets" else (),
                    skipped_symlink_escape=(
                        ("escape",) if field == "skipped_symlink_escape" else ()
                    ),
                )
            )
            with self.subTest(field=field), mock.patch.object(
                lifecycle_reconcile,
                "_observations",
                return_value=[observation],
            ):
                with self.assertRaises(integrity_repair.RepairRefused):
                    integrity_repair.apply(
                        plan["plan_digest"],
                        "remove-worktree",
                        plan["actions"][0]["authorization"],
                        capture=capture,
                        clean_runner=clean_runner,
                    )
        clean_runner.assert_not_called()

    def test_apply_rolls_back_on_fault_and_preserves_clean_path_authority(self):
        plan = self._plan()

        def fault(point):
            if point == "retire-after-update":
                raise RuntimeError("injected")

        with self.assertRaises(RuntimeError):
            self._apply_retire(plan, fault=fault)
        with state_mod.State() as state:
            self.assertEqual(state.get_lease("awa1-repair")["status"], "active")
            self.assertFalse(
                any(
                    event["kind"] == "integrity_repair_retire_bookkeeping"
                    for event in state.events("awa1-repair")
                )
            )

        _action, observation = self._remove_action()
        removal = self._plan(observation)
        with mock.patch.object(
            lock,
            "common_dir_lock",
            side_effect=AssertionError("remove-worktree must not take an outer lock"),
        ), mock.patch.object(
            lifecycle_reconcile,
            "_observations",
            return_value=[observation],
        ):
            with self.assertRaises(integrity_repair.RepairRefused):
                integrity_repair.apply(
                    removal["plan_digest"],
                    "remove-worktree",
                    removal["actions"][0]["authorization"],
                    capture=lambda *_args, **_kwargs: integrity_repair.Capture(
                        archive="/capture",
                        manifest="/manifest",
                        protected=True,
                        skipped_secrets=(),
                        skipped_symlink_escape=(),
                    ),
                    clean_runner=lambda _argv: integrity_repair.CleanResult(
                        returncode=1,
                        stdout="",
                        stderr="clean refused",
                        receipt={
                            "schema": "clean_receipt/v1",
                            "receipt_id": "receipt-refused",
                            "disposition": "refused",
                            "path": removal["actions"][0]["target"],
                        },
                    ),
                )

    def _remove_action(self):
        repo = self.make_seeded_repo("remove-repo")
        worktree = self.add_worktree(repo, "feat/remove")
        common_dir = subprocess.run(
            [
                "git",
                "-C",
                worktree,
                "rev-parse",
                "--path-format=absolute",
                "--git-common-dir",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        registration = lifecycle_reconcile.GitRegistration(
            path=str(Path(worktree).resolve()),
            git_common_dir=common_dir,
            linked=True,
            dirty=False,
            cached_remote=True,
        )
        observation = lifecycle_reconcile._Observation(
            path=str(Path(worktree).resolve()),
            lease=None,
            registration=registration,
            registration_known=True,
            root_exists=True,
            lease_on_disk=False,
            disposition="untracked",
            live_session=False,
            journal_or_recovery_ambiguous=False,
        )
        action = integrity_repair._action_for_observation(observation)
        self.assertIsNotNone(action)
        return action, observation


if __name__ == "__main__":
    unittest.main()
