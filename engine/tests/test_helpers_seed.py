"""Isolation and eligibility proofs for copy-only Git repository seeds."""

from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from . import helpers
from .helpers import EngineTestCase, commit_all, git


class RepoSeedTest(EngineTestCase):
    def test_materializations_have_independent_refs_config_objects_and_hooks(self) -> None:
        left = Path(self.make_seeded_repo("left"))
        right = Path(self.make_seeded_repo("right"))
        initial_head = git(str(left), "rev-parse", "HEAD").stdout.strip()
        self.assertEqual(git(str(right), "rev-parse", "HEAD").stdout.strip(), initial_head)

        git(str(left), "checkout", "-qb", "left-only")
        git(str(left), "config", "awa.test", "left")
        (left / "left-only").write_text("left\n", encoding="utf-8")
        commit_all(str(left), "left")
        hook = left / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        hook.chmod(0o700)

        self.assertNotIn("left-only", git(str(right), "branch").stdout)
        self.assertNotEqual(
            git(str(right), "config", "--get", "awa.test", check=False).returncode,
            0,
        )
        self.assertFalse((right / ".git" / "hooks" / "pre-commit").exists())
        self.assertEqual(git(str(right), "rev-parse", "HEAD").stdout.strip(), initial_head)

        left_common = Path(
            left,
            git(str(left), "rev-parse", "--git-common-dir").stdout.strip(),
        ).resolve()
        right_common = Path(
            right,
            git(str(right), "rev-parse", "--git-common-dir").stdout.strip(),
        ).resolve()
        self.assertNotEqual(left_common, right_common)
        for relative in (Path("HEAD"), Path("config"), Path("index")):
            self.assertNotEqual(
                os.stat(left_common / relative).st_ino,
                os.stat(right_common / relative).st_ino,
            )
        object_rel = Path("objects") / initial_head[:2] / initial_head[2:]
        self.assertTrue((left_common / object_rel).is_file())
        self.assertTrue((right_common / object_rel).is_file())
        self.assertNotEqual(
            os.stat(left_common / object_rel).st_ino,
            os.stat(right_common / object_rel).st_ino,
        )

    def test_materializations_have_no_links_alternates_specials_or_shared_inodes(self) -> None:
        left = Path(self.make_seeded_repo("left-audit"))
        right = Path(self.make_seeded_repo("right-audit"))
        inode_sets = []
        for root in (left, right):
            inodes = set()
            for path in (root, *sorted(root.rglob("*"))):
                metadata = path.lstat()
                self.assertFalse(path.is_symlink(), path)
                self.assertTrue(
                    stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode),
                    path,
                )
                self.assertEqual(metadata.st_mode & 0o077, 0, path)
                if stat.S_ISREG(metadata.st_mode):
                    self.assertEqual(metadata.st_nlink, 1, path)
                    inodes.add((metadata.st_dev, metadata.st_ino))
            self.assertFalse((root / ".git" / "objects" / "info" / "alternates").exists())
            self.assertFalse((root / ".git" / "commondir").exists())
            inode_sets.append(inodes)
        self.assertFalse(inode_sets[0] & inode_sets[1])

    def test_process_seed_is_unchanged_after_copy_and_repository_mutation(self) -> None:
        seed = helpers._process_repo_seed()
        before = seed.sha256
        repo = Path(self.make_seeded_repo("immutable"))
        (repo / "changed").write_text("changed\n", encoding="utf-8")
        commit_all(str(repo), "changed")
        self.make_seeded_repo("immutable-second")
        self.assertEqual(seed.sha256, before)
        self.assertEqual(seed.audit(), before)

    def test_destination_must_be_new_and_beneath_active_test_root(self) -> None:
        seed = helpers._process_repo_seed()
        outside = Path(tempfile.gettempdir()) / "awa-seed-outside"
        with self.assertRaisesRegex(ValueError, "active engine test root"):
            seed.materialize(outside)
        existing = Path(self._tmp.name) / "existing"
        existing.mkdir()
        with self.assertRaisesRegex(ValueError, "must not exist"):
            seed.materialize(existing)

    def test_fresh_escape_and_origin_selection_remain_explicit(self) -> None:
        with mock.patch.object(self, "make_repo", wraps=self.make_repo) as fresh:
            fresh_repo = self.make_seeded_repo("fresh", fresh=True)
        fresh.assert_called_once_with("fresh", origin=True)
        self.assertTrue(Path(fresh_repo, ".git").is_dir())

        without_origin = self.make_seeded_repo("without-origin", origin=False)
        self.assertNotIn("origin", git(without_origin, "remote").stdout.split())
        ordinary = self.make_repo("ordinary")
        self.assertIn("origin", git(ordinary, "remote").stdout.split())

    def test_separate_cases_keep_independent_private_xdg_state(self) -> None:
        roots = []
        for name in ("first", "second"):
            case = EngineTestCase()
            case.setUp()
            try:
                case.make_seeded_repo(name)
                current = tuple(
                    Path(os.environ[key]).resolve()
                    for key in ("XDG_STATE_HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME")
                )
                for path in current:
                    self.assertTrue(path.is_dir())
                    self.assertEqual(path.stat().st_mode & 0o077, 0)
                    self.assertFalse(path.is_symlink())
                    self.assertTrue(path.is_relative_to(Path(case._tmp.name).resolve()))
                roots.append(current)
            finally:
                case.tearDown()
        self.assertTrue(set(roots[0]).isdisjoint(roots[1]))


if __name__ == "__main__":
    unittest.main()
