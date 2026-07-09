"""Phase 3: recovery manager — patch round-trip, bundle S1/S2, restore."""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from engine import gitutil, recovery, state as state_mod
from engine.tests.helpers import EngineTestCase, commit_all


class TestPatchRoundTrip(EngineTestCase):
    def test_patch_create_and_restore(self):
        repo = self.make_repo()
        Path(repo, "f.txt").write_text("v1\n", encoding="utf-8")
        commit_all(repo, "add f")
        # uncommitted edit (tracked)
        Path(repo, "f.txt").write_text("v2-uncommitted\n", encoding="utf-8")
        with state_mod.State() as st:
            res = recovery.create_patch(repo, state=st)
        self.assertTrue(res.has_changes)
        # reset the working tree
        gitutil.git(repo, "checkout", "--", "f.txt")
        self.assertEqual(Path(repo, "f.txt").read_text(), "v1\n")
        # restore the patch -> uncommitted content reproduced exactly
        recovery.restore_patch(res.patch, repo)
        self.assertEqual(Path(repo, "f.txt").read_text(), "v2-uncommitted\n")

    def test_empty_patch_is_noop(self):
        repo = self.make_repo()
        res = recovery.create_patch(repo)
        self.assertFalse(res.has_changes)
        recovery.restore_patch(res.patch, repo)  # must not raise


class TestBundle(EngineTestCase):
    def _repo_with_ignored(self) -> str:
        repo = self.make_repo()
        Path(repo, ".gitignore").write_text("*.key\n*.env\n*.dat\n*.localdb\n", encoding="utf-8")
        commit_all(repo, "gitignore")
        return repo

    def test_bundle_skips_secrets_keeps_nonsecret(self):
        repo = self._repo_with_ignored()
        Path(repo, "secret.key").write_text("PRIVATE\n", encoding="utf-8")
        Path(repo, "app.env").write_text("A=1\n", encoding="utf-8")
        Path(repo, "data.localdb").write_text("DB\n", encoding="utf-8")
        with state_mod.State() as st:
            r = recovery.create_bundle(repo, state=st)
        self.assertIn("data.localdb", r.included)
        self.assertIn("secret.key", r.skipped_secrets)
        self.assertIn("app.env", r.skipped_secrets)
        # archive name never starts with a dot
        self.assertFalse(os.path.basename(r.archive).startswith("."))

    def test_bundle_allow_secrets_override(self):
        repo = self._repo_with_ignored()
        Path(repo, "secret.key").write_text("PRIVATE\n", encoding="utf-8")
        r = recovery.create_bundle(repo, allow_secrets=True)
        self.assertIn("secret.key", r.included)
        self.assertEqual(r.skipped_secrets, [])

    def test_bundle_drops_symlink_escaping_root(self):
        repo = self._repo_with_ignored()
        outside = Path(self._tmp.name) / "outside"
        outside.mkdir()
        (outside / "leak.dat").write_text("SECRETOUT\n", encoding="utf-8")
        os.symlink(str(outside / "leak.dat"), str(Path(repo, "escape.dat")))
        Path(repo, "inside.dat").write_text("INSIDE\n", encoding="utf-8")
        r = recovery.create_bundle(repo)
        self.assertIn("escape.dat", r.skipped_symlink_escape)
        self.assertIn("inside.dat", r.included)

    def test_bundle_restore_round_trip(self):
        repo = self._repo_with_ignored()
        Path(repo, "data.localdb").write_text("DBDATA\n", encoding="utf-8")
        r = recovery.create_bundle(repo)
        dest = Path(self._tmp.name) / "restore-dest"
        restored = recovery.restore_bundle(r.archive, str(dest))
        self.assertIn("data.localdb", restored)
        self.assertEqual((dest / "data.localdb").read_text(), "DBDATA\n")

    def test_list_artifacts(self):
        repo = self._repo_with_ignored()
        Path(repo, "data.localdb").write_text("DB\n", encoding="utf-8")
        recovery.create_bundle(repo)
        recovery.create_patch(repo)
        arts = recovery.list_artifacts()
        kinds = {a.get("kind") for a in arts}
        self.assertIn("bundle", kinds)
        self.assertIn("patch", kinds)


class TestWorktreeArchive(EngineTestCase):
    """D2: protected whole-worktree archive + archive-only hardening + cleanup refusal."""

    def _repo(self) -> str:
        repo = self.make_repo()
        Path(repo, ".gitignore").write_text("*.db\n*.env\n", encoding="utf-8")
        commit_all(repo, "gitignore")
        Path(repo, "notes.txt").write_text("untracked notes\n", encoding="utf-8")   # untracked
        Path(repo, "data.db").write_text("LOCALDB\n", encoding="utf-8")             # ignored
        Path(repo, "app.env").write_text("SECRET=1\n", encoding="utf-8")            # ignored+secret
        return repo

    def test_archive_captures_whole_tree_protected_and_readonly(self):
        repo = self._repo()
        with state_mod.State() as st:
            r = recovery.create_worktree_archive(repo, state=st)
        # whole tree: tracked (README.md, .gitignore) + untracked + ignored are all included.
        for rel in ("README.md", ".gitignore", "notes.txt", "data.db"):
            self.assertIn(rel, r.included, rel)
        # S1: the secret-pattern file is excluded (recorded as skipped), not archived.
        self.assertIn("app.env", r.skipped_secrets)
        # .git metadata is never archived.
        self.assertFalse(any(e == ".git" or e.startswith(".git/") for e in r.included))
        # manifest declares kind + protected.
        doc = json.loads(Path(r.manifest).read_text(encoding="utf-8"))
        self.assertEqual(doc["kind"], recovery.WORKTREE_ARCHIVE_KIND)
        self.assertTrue(doc["protected"])
        self.assertTrue(r.protected)
        # archive-only hardening: archive + manifest are READ-ONLY (0o400), NO OS immutable flag.
        self.assertEqual(oct(os.stat(r.archive).st_mode & 0o777), "0o400")
        self.assertEqual(oct(os.stat(r.manifest).st_mode & 0o777), "0o400")

    def test_archive_restore_round_trip(self):
        repo = self._repo()
        r = recovery.create_worktree_archive(repo)
        dest = Path(self._tmp.name) / "wt-restore"
        restored = recovery.restore_bundle(r.archive, str(dest))
        self.assertIn("data.db", restored)
        self.assertEqual((dest / "data.db").read_text(), "LOCALDB\n")

    def test_archive_drops_symlink_escaping_root(self):
        repo = self._repo()
        outside = Path(self._tmp.name) / "outside"
        outside.mkdir(exist_ok=True)
        (outside / "leak.txt").write_text("LEAK\n", encoding="utf-8")
        os.symlink(str(outside / "leak.txt"), str(Path(repo, "escape.txt")))
        r = recovery.create_worktree_archive(repo)
        self.assertIn("escape.txt", r.skipped_symlink_escape)
        self.assertNotIn("escape.txt", r.included)

    def test_prune_refuses_protected_even_with_force(self):
        repo = self._repo()
        arch = recovery.create_worktree_archive(repo)           # protected
        bundle = recovery.create_bundle(repo)                   # non-protected
        res = recovery.prune_artifacts(force=True)              # force delete everything eligible
        self.assertIn(arch.archive, res["refused_protected"])
        self.assertIn(bundle.archive, res["deleted"])
        # the protected archive + its manifest survive; the bundle is gone.
        self.assertTrue(Path(arch.archive).exists(), "a protected archive must survive cleanup")
        self.assertTrue(Path(arch.manifest).exists())
        self.assertFalse(Path(bundle.archive).exists())

    def test_prune_default_is_noop(self):
        repo = self._repo()
        bundle = recovery.create_bundle(repo)
        res = recovery.prune_artifacts()  # no force, no age threshold -> deletes nothing.
        self.assertEqual(res["deleted"], [])
        self.assertIn(bundle.archive, res["kept"])
        self.assertTrue(Path(bundle.archive).exists())


if __name__ == "__main__":
    unittest.main()
