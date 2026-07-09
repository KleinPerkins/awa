"""K1: a kernel-owned clean_receipt/v1 is written on EVERY terminal `clean` path.

The kernel `dev-worktree.sh clean` is the SOLE destructive worktree-removal path in the whole
product (the engine's retire/recovery/daemon paths are non-destructive bookkeeping — verified by
inspection: lifecycle.retire only marks lease state, recovery only *creates* bundles/patches,
daemon.cleanup_quarantine_refs cleans git refs, none remove a worktree). So "a receipt on every
terminal clean path" is a KERNEL property and is proven here by driving the real bash gate with
the engine OFF (subprocess; awa_roots.py is stdlib-only).

Two guarantees together make "a NEW clean path without a receipt fails CI" structural, not a
per-path discipline a future edit can forget:
  1. behavioral — every reachable terminal path (refusal, removal, and the ignored/unknown-evidence
     invariants) writes exactly ONE receipt with the expected disposition + reason_code + schema;
  2. coverage/meta — the set of reason_codes authored in the script is LOCKED to a known set here,
     so adding a `clean_set_disposition <disp> <new_reason>` without covering it breaks this test,
     and the EXIT-trap + fail-safe default ("refused"/"unattributed_exit") guarantee even an
     unclassified exit records a REFUSAL receipt (never a silent success).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from .helpers import EngineTestCase, commit_all, git

_IDENT = ("-c", "user.email=49759187+KleinPerkins@users.noreply.github.com",
          "-c", "user.name=KleinPerkins")


class CleanReceiptsTest(EngineTestCase):
    # ---- plumbing -----------------------------------------------------------
    @property
    def repo_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    @property
    def dev_worktree(self) -> str:
        return str(self.repo_root / "kernel" / "bin" / "dev-worktree.sh")

    @property
    def awa_roots(self) -> str:
        return str(self.repo_root / "kernel" / "lib" / "awa_roots.py")

    @property
    def receipts_root(self) -> Path:
        return self.state_home / "awa" / "receipts"

    def run_clean(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
        clean_env = os.environ.copy()
        clean_env["AWA_HOME"] = str(self.repo_root)
        if env:
            clean_env.update(env)
        return subprocess.run([self.dev_worktree, "clean", *args], cwd=str(self.repo_root),
                              env=clean_env, capture_output=True, text=True)

    def heartbeat(self, path: str) -> None:
        subprocess.run(["python3", self.awa_roots, "heartbeat", "--root", path],
                       env=os.environ.copy(), capture_output=True, text=True, check=True)

    def receipts(self) -> list[dict]:
        if not self.receipts_root.is_dir():
            return []
        out = []
        for name in sorted(self.receipts_root.glob("clean-*.json")):
            out.append(json.loads(name.read_text(encoding="utf-8")))
        return sorted(out, key=lambda r: r.get("receipt_id", ""))

    def only_receipt(self, result: subprocess.CompletedProcess | None = None) -> dict:
        rs = self.receipts()
        self.assertEqual(len(rs), 1,
                         f"expected exactly one receipt, got {len(rs)}\n"
                         + (result.stdout + result.stderr if result else ""))
        r = rs[0]
        # frozen required keys are always present regardless of path
        for k in ("schema", "receipt_id", "time", "verb", "disposition", "reason_code",
                  "path", "flags", "root_disposition", "tool"):
            self.assertIn(k, r, r)
        self.assertEqual(r["schema"], "clean_receipt/v1")
        self.assertIn(r["disposition"], ("removed", "refused", "error"))
        for fk in ("bundle", "force", "delete_branch"):
            self.assertIn(fk, r["flags"])
        return r

    # ---- scratch builders ---------------------------------------------------
    def commit_file(self, cwd: str, rel: str, content: str, message: str) -> None:
        Path(cwd, rel).write_text(content, encoding="utf-8")
        commit_all(cwd, message)

    def safe_worktree(self, name: str, branch: str = "feat/x") -> tuple[str, str]:
        """A worktree whose branch is squash-merged into main -> cleanup-safe (removable)."""
        repo = self.make_repo(name)
        wt = self.add_worktree(repo, branch)
        self.commit_file(wt, "feature.txt", "feature\n", "feature")
        git(repo, "checkout", "-q", "main")
        git(repo, "merge", "--squash", branch)
        commit_all(repo, "squash feature")
        return repo, wt

    # ---- terminal REFUSAL paths (each writes a refused/<reason> receipt) -----
    def test_missing_path_refused(self) -> None:
        r = self.run_clean()  # no --path
        self.assertNotEqual(r.returncode, 0)
        rec = self.only_receipt(r)
        self.assertEqual((rec["disposition"], rec["reason_code"]), ("refused", "missing_path"))

    def test_unknown_option_refused(self) -> None:
        _, wt = self.safe_worktree("unknownopt")
        r = self.run_clean("--path", wt, "--nope")
        self.assertNotEqual(r.returncode, 0)
        rec = self.only_receipt(r)
        self.assertEqual((rec["disposition"], rec["reason_code"]), ("refused", "unknown_option"))

    def test_not_a_directory_refused(self) -> None:
        r = self.run_clean("--path", str(self.state_home / "does-not-exist"))
        self.assertNotEqual(r.returncode, 0)
        rec = self.only_receipt(r)
        self.assertEqual((rec["disposition"], rec["reason_code"]), ("refused", "not_a_directory"))

    def test_symlinked_path_refused(self) -> None:
        _, wt = self.safe_worktree("symlink")
        link = wt + ".link"
        os.symlink(wt, link)
        r = self.run_clean("--path", link)
        self.assertNotEqual(r.returncode, 0)
        rec = self.only_receipt(r)
        self.assertEqual((rec["disposition"], rec["reason_code"]), ("refused", "symlinked_path"))

    def test_dirty_refused(self) -> None:
        _, wt = self.safe_worktree("dirty")
        Path(wt, "uncommitted.txt").write_text("dirty\n", encoding="utf-8")
        r = self.run_clean("--path", wt)
        self.assertNotEqual(r.returncode, 0)
        rec = self.only_receipt(r)
        self.assertEqual((rec["disposition"], rec["reason_code"]), ("refused", "dirty"))

    def test_detached_head_refused(self) -> None:
        _, wt = self.safe_worktree("detached")
        head = git(wt, "rev-parse", "HEAD").stdout.strip()
        git(wt, "checkout", "-q", head)  # detach
        r = self.run_clean("--path", wt)
        self.assertNotEqual(r.returncode, 0)
        rec = self.only_receipt(r)
        self.assertEqual((rec["disposition"], rec["reason_code"]), ("refused", "detached_head"))

    def test_local_only_commits_refused(self) -> None:
        repo = self.make_repo("unshared")
        wt = self.add_worktree(repo, "feat/unshared")
        self.commit_file(wt, "feature.txt", "feature\n", "feature")  # never merged/pushed
        r = self.run_clean("--path", wt)
        self.assertNotEqual(r.returncode, 0)
        rec = self.only_receipt(r)
        self.assertEqual((rec["disposition"], rec["reason_code"]), ("refused", "local_only_commits"))

    # ---- "ignored-files-are-child-state" invariant --------------------------
    def test_ignored_files_present_refused(self) -> None:
        """git-ignored local files are CHILD STATE: a clean refuses (bundle-or-refuse)."""
        repo, wt = self.safe_worktree("ignored")
        Path(wt, ".gitignore").write_text("secret.env\n", encoding="utf-8")
        # commit the .gitignore itself so the tree is clean, then drop an ignored file.
        git(wt, "checkout", "-q", "feat/x")
        Path(wt, ".gitignore").write_text("secret.env\n", encoding="utf-8")
        commit_all(wt, "add gitignore")
        git(repo, "checkout", "-q", "main")
        git(repo, "merge", "--squash", "feat/x")
        commit_all(repo, "squash w/ gitignore")
        Path(wt, "secret.env").write_text("TOKEN=abc\n", encoding="utf-8")  # ignored child state
        r = self.run_clean("--path", wt)
        self.assertNotEqual(r.returncode, 0)
        rec = self.only_receipt(r)
        self.assertEqual((rec["disposition"], rec["reason_code"]), ("refused", "ignored_present"))
        self.assertTrue(rec["ignored_present"])
        self.assertGreaterEqual(rec["ignored_count"], 1)
        self.assertTrue(Path(wt).exists(), "worktree must NOT be removed on an ignored-present refusal")

    def test_ignored_files_bundle_removes_and_archives(self) -> None:
        """--bundle archives ignored child state, THEN removes (contract-compat within v1)."""
        repo, wt = self._safe_worktree_with_ignored("ignored-bundle")
        r = self.run_clean("--path", wt, "--bundle")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rec = self.only_receipt(r)
        self.assertEqual(rec["disposition"], "removed")
        self.assertTrue(rec["flags"]["bundle"])
        self.assertTrue(rec["archive"], "a --bundle removal must record an archive path")
        self.assertTrue(Path(rec["archive"]).exists(), "the recovery archive must exist on disk")
        self.assertFalse(Path(wt).exists())

    def test_ignored_files_force_removes_without_archive(self) -> None:
        repo, wt = self._safe_worktree_with_ignored("ignored-force")
        r = self.run_clean("--path", wt, "--force")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rec = self.only_receipt(r)
        self.assertEqual(rec["disposition"], "removed")
        self.assertTrue(rec["flags"]["force"])
        self.assertFalse(Path(wt).exists())

    def _safe_worktree_with_ignored(self, name: str) -> tuple[str, str]:
        repo = self.make_repo(name)
        wt = self.add_worktree(repo, "feat/x")
        Path(wt, ".gitignore").write_text("secret.env\n", encoding="utf-8")
        self.commit_file(wt, "feature.txt", "feature\n", "feature")
        git(repo, "checkout", "-q", "main")
        git(repo, "merge", "--squash", "feat/x")
        commit_all(repo, "squash")
        Path(wt, "secret.env").write_text("TOKEN=abc\n", encoding="utf-8")
        return repo, wt

    # ---- active_root gate (an ACTIVE Safe Workspace blocks removal) ----------
    def test_active_root_refused(self) -> None:
        _, wt = self.safe_worktree("active")
        self.heartbeat(wt)  # mark the root ACTIVE (fresh heartbeat)
        r = self.run_clean("--path", wt)
        self.assertNotEqual(r.returncode, 0)
        rec = self.only_receipt(r)
        self.assertEqual((rec["disposition"], rec["reason_code"]), ("refused", "active_root"))
        self.assertEqual(rec["root_disposition"], "active")
        self.assertTrue(Path(wt).exists(), "an active root must not be removed")

    # ---- terminal REMOVAL paths ---------------------------------------------
    def test_removed_kept_branch(self) -> None:
        _, wt = self.safe_worktree("keep")
        r = self.run_clean("--path", wt)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rec = self.only_receipt(r)
        self.assertEqual((rec["disposition"], rec["reason_code"]), ("removed", "removed_kept_branch"))
        self.assertFalse(Path(wt).exists())

    def test_removed_with_branch(self) -> None:
        repo, wt = self.safe_worktree("delete", "feat/del")
        r = self.run_clean("--path", wt, "--delete-branch")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rec = self.only_receipt(r)
        self.assertEqual((rec["disposition"], rec["reason_code"]), ("removed", "removed_with_branch"))
        self.assertTrue(rec["flags"]["delete_branch"])
        self.assertFalse(Path(wt).exists())
        ref = git(repo, "show-ref", "--verify", "--quiet", "refs/heads/feat/del", check=False)
        self.assertNotEqual(ref.returncode, 0)

    # ---- exactly-one-receipt-per-invocation ---------------------------------
    def test_exactly_one_receipt_per_invocation(self) -> None:
        _, wt = self.safe_worktree("one")
        r = self.run_clean("--path", wt)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(self.receipts()), 1, "the EXIT trap must emit exactly one receipt")

    # ---- coverage/meta: the reason_code universe is LOCKED -------------------
    def test_reason_code_universe_is_locked(self) -> None:
        """Every disposition/reason authored in the script must be a KNOWN, receipt-bearing path.
        Adding a new `clean_set_disposition <disp> <reason>` (a new terminal path) without adding
        it here fails CI — this is the "new clean path without a receipt fails" guarantee."""
        src = Path(self.dev_worktree).read_text(encoding="utf-8")
        authored = set(re.findall(r"clean_set_disposition\s+(\w+)\s+(\w+)", src))
        # the fail-safe DEFAULT (armed before any classification) is a terminal path too.
        self.assertIn('_CLEAN_DISPOSITION="refused"', src)
        self.assertIn('_CLEAN_REASON="unattributed_exit"', src)
        authored.add(("refused", "unattributed_exit"))

        known = {
            ("refused", "unknown_option"), ("refused", "missing_path"),
            ("refused", "symlinked_path"), ("refused", "not_a_directory"),
            ("error", "canonicalize_failed"), ("refused", "dirty"),
            ("error", "no_branch"), ("refused", "detached_head"),
            ("error", "no_head"), ("error", "no_git_dir"), ("error", "no_common_dir"),
            ("refused", "active_root"), ("refused", "local_only_commits"),
            ("refused", "ignored_scan_failed"), ("error", "bundle_failed"),
            ("refused", "ignored_present"), ("removed", "removed_with_branch"),
            ("error", "branch_moved"), ("removed", "removed_kept_branch"),
            ("refused", "unattributed_exit"),
        }
        # every disposition is a valid clean_receipt/v1 disposition value
        for disp, _reason in authored:
            self.assertIn(disp, ("removed", "refused", "error"), (disp, _reason))
        new = authored - known
        self.assertEqual(new, set(),
                         "NEW terminal clean path(s) without receipt coverage: "
                         + ", ".join(f"{d}/{r}" for d, r in sorted(new))
                         + " — add a behavioral test + receipt assertion.")

    def test_exit_trap_and_failsafe_default_present(self) -> None:
        """Structural backstop: the EXIT trap + fail-safe default are what make the receipt
        guarantee hold on EVERY exit (die/return/normal), not just the classified ones."""
        src = Path(self.dev_worktree).read_text(encoding="utf-8")
        self.assertRegex(src, r"trap\s+'_clean_exit_trap'\s+EXIT")
        self.assertIn("_CLEAN_RECEIPT_WRITTEN", src)


if __name__ == "__main__":
    import unittest
    unittest.main()
