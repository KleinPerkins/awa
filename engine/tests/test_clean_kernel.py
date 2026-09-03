"""Subprocess tests for the kernel `dev-worktree.sh clean` safety gate."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path

from engine import lifecycle
from .helpers import EngineTestCase, commit_all, git

_IDENT = (
    "-c",
    "user.email=49759187+KleinPerkins@users.noreply.github.com",
    "-c",
    "user.name=KleinPerkins",
)


class CleanKernelTest(EngineTestCase):
    @property
    def repo_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    @property
    def dev_worktree(self) -> str:
        return str(self.repo_root / "kernel" / "bin" / "dev-worktree.sh")

    def run_clean(self, path: str, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        clean_env = os.environ.copy()
        clean_env["AWA_HOME"] = str(self.repo_root)
        if env:
            clean_env.update(env)
        return subprocess.run(
            ["bash", self.dev_worktree, "clean", "--path", path, *args],
            cwd=str(self.repo_root),
            env=clean_env,
            capture_output=True,
            text=True,
        )

    def assert_clean_refused(self, result: subprocess.CompletedProcess) -> None:
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("local-only commits", result.stderr)

    def assert_patch_equivalent(self, result: subprocess.CompletedProcess) -> None:
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("patch-equivalent", result.stdout + result.stderr)

    def git_ident(self, cwd: str, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "-C", cwd, *_IDENT, *args],
            capture_output=True,
            text=True,
            check=True,
        )

    def commit_file(self, cwd: str, relpath: str, content: str, message: str) -> None:
        Path(cwd, relpath).write_text(content, encoding="utf-8")
        commit_all(cwd, message)

    def squash_branch_to_main(self, repo: str, branch: str, message: str = "squash feature") -> None:
        git(repo, "checkout", "-q", "main")
        git(repo, "merge", "--squash", branch)
        commit_all(repo, message)

    def single_commit_squash(self, name: str, branch: str = "feat/squash") -> tuple[str, str]:
        repo = self.make_repo(name)
        wt = self.add_worktree(repo, branch)
        self.commit_file(wt, "feature.txt", "feature\n", "feature")
        self.squash_branch_to_main(repo, branch)
        return repo, wt

    def test_single_commit_squash_main_not_advanced_succeeds(self) -> None:
        _, wt = self.single_commit_squash("single")

        result = self.run_clean(wt)

        self.assert_patch_equivalent(result)

    def test_single_commit_squash_main_advanced_after_squash_succeeds(self) -> None:
        repo, wt = self.single_commit_squash("advanced")
        self.commit_file(repo, "main-after.txt", "after\n", "advance main")

        result = self.run_clean(wt)

        self.assert_patch_equivalent(result)

    def test_genuinely_unshared_branch_refuses(self) -> None:
        repo = self.make_repo("unshared")
        wt = self.add_worktree(repo, "feat/unshared")
        self.commit_file(wt, "feature.txt", "feature\n", "feature")

        result = self.run_clean(wt)

        self.assert_clean_refused(result)

    def test_add_then_remove_tree_equal_branch_refuses_without_patch_equivalent(self) -> None:
        repo = self.make_repo("net-zero")
        wt = self.add_worktree(repo, "feat/net-zero")
        self.commit_file(wt, "temporary.txt", "temporary\n", "add temporary")
        Path(wt, "temporary.txt").unlink()
        commit_all(wt, "remove temporary")

        result = self.run_clean(wt)

        self.assert_clean_refused(result)
        self.assertNotIn("patch-equivalent", result.stdout + result.stderr)

    def test_branch_with_merge_commit_refuses(self) -> None:
        repo = self.make_repo("merge-commit")
        wt = self.add_worktree(repo, "feat/merge")
        self.commit_file(wt, "feature.txt", "feature\n", "feature")
        git(repo, "checkout", "-q", "-b", "side", "main")
        self.commit_file(repo, "side.txt", "side\n", "side")
        git(repo, "checkout", "-q", "main")
        self.git_ident(wt, "merge", "--no-edit", "side")
        self.squash_branch_to_main(repo, "feat/merge")

        result = self.run_clean(wt)

        self.assert_clean_refused(result)

    def test_origin_main_only_patch_equivalent_succeeds(self) -> None:
        repo = self.make_repo("origin-only")
        self.add_bare_remote(repo)
        wt = self.add_worktree(repo, "feat/remote-only")
        self.commit_file(wt, "feature.txt", "feature\n", "feature")
        self.squash_branch_to_main(repo, "feat/remote-only")
        git(repo, "push", "origin", "main")
        git(repo, "update-ref", "-d", "refs/heads/main")
        git(repo, "fetch", "origin", "main:refs/remotes/origin/main")

        result = self.run_clean(wt)

        self.assert_patch_equivalent(result)

    def test_no_local_main_and_no_origin_main_refuses(self) -> None:
        repo = self.make_repo("no-main")
        wt = self.add_worktree(repo, "feat/no-main")
        self.commit_file(wt, "feature.txt", "feature\n", "feature")
        git(repo, "update-ref", "-d", "refs/heads/main")
        git(repo, "update-ref", "-d", "refs/remotes/origin/main", check=False)

        result = self.run_clean(wt)

        self.assert_clean_refused(result)

    def test_multi_commit_squash_refuses(self) -> None:
        repo = self.make_repo("multi")
        wt = self.add_worktree(repo, "feat/multi")
        self.commit_file(wt, "one.txt", "one\n", "one")
        self.commit_file(wt, "two.txt", "two\n", "two")
        self.squash_branch_to_main(repo, "feat/multi")

        result = self.run_clean(wt)

        self.assert_clean_refused(result)

    def test_squash_delete_branch_removes_worktree_and_ref(self) -> None:
        repo, wt = self.single_commit_squash("delete", "feat/delete")

        result = self.run_clean(wt, "--delete-branch")

        self.assert_patch_equivalent(result)
        self.assertFalse(Path(wt).exists())
        ref = git(repo, "show-ref", "--verify", "--quiet", "refs/heads/feat/delete", check=False)
        self.assertNotEqual(ref.returncode, 0)

    def test_adopted_merged_worktree_bundle_clean_owns_only_validated_lease(self) -> None:
        """Regression: adoption's exact lease must not make a fully merged worktree unclean."""
        repo = self.make_repo("adopted")
        Path(repo, ".gitignore").write_text("scratch/\n", encoding="utf-8")
        commit_all(repo, "ignore local scratch")
        wt = self.add_worktree(repo, "feat/adopted")
        self.commit_file(wt, "feature.txt", "feature\n", "feature")
        self.squash_branch_to_main(repo, "feat/adopted")
        lifecycle.adopt(wt)
        scratch = Path(wt, "scratch", "cache.db")
        scratch.parent.mkdir()
        scratch.write_text("preserve me\n", encoding="utf-8")

        result = self.run_clean(wt, "--bundle", "--delete-branch")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(Path(wt).exists())
        ref = git(
            repo,
            "show-ref",
            "--verify",
            "--quiet",
            "refs/heads/feat/adopted",
            check=False,
        )
        self.assertNotEqual(ref.returncode, 0)
        manifests = list((self.state_home / "awa" / "recovery").glob("*.manifest.json"))
        self.assertEqual(len(manifests), 1)
        manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
        self.assertEqual(manifest["included"], ["scratch/"])
        self.assertNotIn(".awa", "\n".join(manifest["included"]))

    def test_adopted_unmerged_worktree_preserves_lease_on_commit_safety_refusal(self) -> None:
        repo = self.make_repo("adopted-unmerged")
        wt = self.add_worktree(repo, "feat/adopted-unmerged")
        self.commit_file(wt, "feature.txt", "feature\n", "feature")
        lifecycle.adopt(wt)

        result = self.run_clean(wt, "--bundle", "--delete-branch")

        self.assert_clean_refused(result)
        self.assertTrue(Path(wt, ".awa", "lease.json").is_file())

    def test_ignored_validated_lease_is_removed_not_recovery_bundled(self) -> None:
        repo = self.make_repo("adopted-ignored")
        Path(repo, ".gitignore").write_text(".awa/\nscratch/\n", encoding="utf-8")
        commit_all(repo, "ignore AWA state and local scratch")
        wt = self.add_worktree(repo, "feat/adopted-ignored")
        self.commit_file(wt, "feature.txt", "feature\n", "feature")
        self.squash_branch_to_main(repo, "feat/adopted-ignored")
        lifecycle.adopt(wt)
        scratch = Path(wt, "scratch", "cache.db")
        scratch.parent.mkdir()
        scratch.write_text("preserve me\n", encoding="utf-8")

        result = self.run_clean(wt, "--bundle", "--delete-branch")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        manifests = list((self.state_home / "awa" / "recovery").glob("*.manifest.json"))
        self.assertEqual(len(manifests), 1)
        manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
        self.assertEqual(manifest["included"], ["scratch/"])

    def test_adopted_worktree_with_extra_awa_content_refuses_and_preserves_all(self) -> None:
        _, wt = self.single_commit_squash("adopted-extra", "feat/adopted-extra")
        lifecycle.adopt(wt)
        extra = Path(wt, ".awa", "operator-note.txt")
        extra.write_text("not AWA-owned\n", encoding="utf-8")

        result = self.run_clean(wt, "--bundle", "--delete-branch")

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("dirty worktree", result.stderr)
        self.assertTrue(Path(wt, ".awa", "lease.json").is_file())
        self.assertEqual(extra.read_text(encoding="utf-8"), "not AWA-owned\n")

    def test_adopted_worktree_with_unrelated_untracked_file_refuses_and_preserves_all(self) -> None:
        _, wt = self.single_commit_squash("adopted-untracked", "feat/adopted-untracked")
        lifecycle.adopt(wt)
        unrelated = Path(wt, "operator-note.txt")
        unrelated.write_text("preserve me\n", encoding="utf-8")

        result = self.run_clean(wt, "--bundle", "--delete-branch")

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("dirty worktree", result.stderr)
        self.assertTrue(Path(wt, ".awa", "lease.json").is_file())
        self.assertEqual(unrelated.read_text(encoding="utf-8"), "preserve me\n")

    def test_malformed_or_identity_mismatched_lease_is_never_owned(self) -> None:
        for case in ("malformed", "branch-mismatch"):
            with self.subTest(case=case):
                _, wt = self.single_commit_squash(
                    f"adopted-{case}",
                    f"feat/adopted-{case}",
                )
                lifecycle.adopt(wt)
                lease_path = Path(wt, ".awa", "lease.json")
                if case == "malformed":
                    lease_path.write_text("{not-json\n", encoding="utf-8")
                else:
                    lease = json.loads(lease_path.read_text(encoding="utf-8"))
                    lease["branch"] = "feat/some-other-branch"
                    lease_path.write_text(json.dumps(lease), encoding="utf-8")
                lease_path.chmod(0o600)

                result = self.run_clean(wt, "--bundle", "--delete-branch")

                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("dirty worktree", result.stderr)
                self.assertTrue(lease_path.is_file())

    def test_symlinked_lease_is_never_owned_or_followed(self) -> None:
        _, wt = self.single_commit_squash("adopted-symlink", "feat/adopted-symlink")
        lifecycle.adopt(wt)
        lease_path = Path(wt, ".awa", "lease.json")
        outside = Path(self._tmp.name, "outside-lease.json")
        lease_path.replace(outside)
        lease_path.symlink_to(outside)
        before = outside.read_bytes()

        result = self.run_clean(wt, "--bundle", "--delete-branch")

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("dirty worktree", result.stderr)
        self.assertTrue(lease_path.is_symlink())
        self.assertEqual(outside.read_bytes(), before)

    def test_atomic_delete_is_bound_to_captured_head(self) -> None:
        repo, wt = self.single_commit_squash("atomic", "feat/atomic")
        captured_head = git(wt, "rev-parse", "HEAD").stdout.strip()
        move_target = git(repo, "rev-parse", "main").stdout.strip()
        common_dir = git(wt, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
        shim_dir = Path(self._tmp.name) / "git-shim"
        shim_dir.mkdir()
        real_git = shutil.which("git")
        self.assertIsNotNone(real_git)
        shim = shim_dir / "git"
        shim.write_text(
            f"""#!/usr/bin/env bash
set -euo pipefail
REAL_GIT={shlex.quote(real_git or "git")}
if [ "${{1:-}}" = "--git-dir=$AWA_TEST_COMMON_DIR" ] &&
   [ "${{2:-}}" = "update-ref" ] &&
   [ "${{3:-}}" = "-d" ] &&
   [ "${{4:-}}" = "refs/heads/$AWA_TEST_BRANCH" ]; then
  "$REAL_GIT" --git-dir="$AWA_TEST_COMMON_DIR" update-ref "refs/heads/$AWA_TEST_BRANCH" "$AWA_TEST_MOVE_REF_TO"
fi
exec "$REAL_GIT" "$@"
""",
            encoding="utf-8",
        )
        shim.chmod(0o755)
        env = {
            "PATH": f"{shim_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            "AWA_TEST_COMMON_DIR": common_dir,
            "AWA_TEST_BRANCH": "feat/atomic",
            "AWA_TEST_MOVE_REF_TO": move_target,
        }

        result = self.run_clean(wt, "--delete-branch", env=env)

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("no longer points at captured HEAD", result.stderr)
        self.assertFalse(Path(wt).exists())
        moved_head = git(repo, "rev-parse", "refs/heads/feat/atomic").stdout.strip()
        self.assertEqual(moved_head, move_target)
        self.assertNotEqual(moved_head, captured_head)
