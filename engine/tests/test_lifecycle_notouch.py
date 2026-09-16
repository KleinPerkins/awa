"""M2.4 generic lifecycle no-touch policy and repair-boundary tests."""

from __future__ import annotations

import copy
import os
import unittest
from pathlib import Path
from unittest import mock

from engine import integrity_repair, lifecycle_reconcile, policy
from engine.tests.helpers import EngineTestCase


def _candidate(path: str) -> lifecycle_reconcile._Observation:
    return lifecycle_reconcile._Observation(
        path=path,
        lease={
            "lease_id": "awa1-no-touch",
            "worktree_path": path,
            "branch": "feat/no-touch",
            "git_common_dir": str(Path(path).parent / "repo" / ".git"),
            "boot_id": "old",
            "base_ref": "main",
            "head": "1" * 40,
            "status": "active",
            "created_at": "2000-01-01T00:00:00Z",
            "updated_at": "2000-01-01T00:00:00Z",
            "attested_at": "2000-01-01T00:00:00Z",
            "pid": 999999,
        },
        registration=None,
        registration_known=True,
        root_exists=False,
        lease_on_disk=False,
        disposition="dead",
        live_session=False,
        journal_or_recovery_ambiguous=False,
    )


class TestLifecycleNoTouch(EngineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.home = Path(self._tmp.name) / "home"
        self.home.mkdir()
        self.policy_path = Path(self._tmp.name) / "policy.yml"
        self.target = self.home / "managed" / "protected" / "worktree"

    def _write_policy(self, values: list[str] | str) -> policy.PolicyConfig:
        if isinstance(values, list):
            rendered = (
                "lifecycle_no_touch: []\n"
                if not values
                else "lifecycle_no_touch:\n"
                + "".join(f"  - {value}\n" for value in values)
            )
        else:
            rendered = f"lifecycle_no_touch: {values}\n"
        self.policy_path.write_text("version: 1\n" + rendered, encoding="utf-8")
        return policy.PolicyConfig.load(self.policy_path)

    def test_exact_glob_tilde_alias_and_boundary_matching(self):
        cfg = self._write_policy(
            [
                "~/managed/protected",
                "~/managed/glob-*",
                str(self.home / "managed" / "tree" / "**"),
            ]
        )
        with mock.patch.dict(os.environ, {"HOME": str(self.home)}, clear=False):
            self.assertTrue(
                lifecycle_reconcile.is_no_touch(
                    self.home / "managed" / "protected", cfg
                )
            )
            self.assertTrue(
                lifecycle_reconcile.is_no_touch(
                    self.home / "managed" / "glob-one", cfg
                )
            )
            self.assertTrue(
                lifecycle_reconcile.is_no_touch(
                    self.home / "managed" / "tree" / "child", cfg
                )
            )
            self.assertFalse(
                lifecycle_reconcile.is_no_touch(
                    self.home / "managed" / "protected-suffix", cfg
                )
            )

            physical = self.home / "physical"
            physical.mkdir()
            alias = self.home / "alias"
            alias.symlink_to(physical, target_is_directory=True)
            alias_cfg = self._write_policy([str(physical / "**")])
            self.assertTrue(
                lifecycle_reconcile.is_no_touch(alias / "child", alias_cfg)
            )

    def test_malformed_or_unreadable_policy_fails_preserve(self):
        malformed_values = ["scalar", ["relative/path"], [""], ["~other/path"], ["[broken"]]
        for value in malformed_values:
            with self.subTest(value=value):
                cfg = self._write_policy(value)
                self.assertFalse(cfg.lifecycle_no_touch_valid)
                self.assertTrue(lifecycle_reconcile.is_no_touch(self.target, cfg))

        self.policy_path.unlink()
        self.policy_path.mkdir()
        cfg = policy.load_lifecycle_policy(self.policy_path)
        self.assertFalse(cfg.lifecycle_no_touch_valid)
        self.assertTrue(lifecycle_reconcile.is_no_touch(self.target, cfg))

    def test_configured_paths_are_preserved_and_omitted_from_plan(self):
        cfg = self._write_policy([str(self.target)])
        observation = _candidate(str(self.target))
        with mock.patch.object(
            lifecycle_reconcile, "_observations", return_value=[observation]
        ), mock.patch.object(
            lifecycle_reconcile, "_lifecycle_policy", return_value=cfg
        ):
            rows = lifecycle_reconcile.classify()
            plan = integrity_repair.build_plan()
        self.assertEqual(rows[0].classification, "preserve")
        self.assertEqual(plan["actions"], [])

    def test_ordinary_paths_unchanged(self):
        cfg = self._write_policy([str(self.home / "other" / "**")])
        observation = _candidate(str(self.target))
        with mock.patch.object(
            lifecycle_reconcile, "_observations", return_value=[observation]
        ), mock.patch.object(
            lifecycle_reconcile, "_lifecycle_policy", return_value=cfg
        ):
            self.assertEqual(
                lifecycle_reconcile.classify()[0].classification,
                "retire_candidate",
            )
            self.assertEqual(
                integrity_repair.build_plan()["actions"][0]["kind"],
                "retire-bookkeeping",
            )

    def test_policy_change_changes_digest_and_removes_authorization(self):
        ordinary = self._write_policy([])
        protected = copy.deepcopy(ordinary)
        protected.lifecycle_no_touch = [str(self.target)]
        observation = _candidate(str(self.target))
        with mock.patch.object(
            lifecycle_reconcile, "_observations", return_value=[observation]
        ), mock.patch.object(
            lifecycle_reconcile,
            "_lifecycle_policy",
            side_effect=[ordinary, protected],
        ):
            preview = integrity_repair.build_plan()
            current = integrity_repair.build_plan()
        self.assertEqual(len(preview["actions"]), 1)
        self.assertEqual(current["actions"], [])
        self.assertNotEqual(preview["plan_digest"], current["plan_digest"])

    def test_product_has_no_hardcoded_host_instance(self):
        source_files = [
            Path(policy.__file__),
            Path(lifecycle_reconcile.__file__),
            Path(integrity_repair.__file__),
        ]
        forbidden = "chaos" + "-scheduler"
        self.assertTrue(all(forbidden not in path.read_text(encoding="utf-8") for path in source_files))


if __name__ == "__main__":
    unittest.main()
