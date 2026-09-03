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

import importlib.util
import json
import os
import re
import subprocess
from pathlib import Path

from .helpers import EngineTestCase, commit_all, git

_IDENT = ("-c", "user.email=49759187+KleinPerkins@users.noreply.github.com",
          "-c", "user.name=KleinPerkins")

_FINISH_PY = Path(__file__).resolve().parents[2] / "kernel" / "lib" / "awa_finish.py"


def _load_finish():
    """Load the stdlib-only finish kernel lib by path (for the shared per-common-dir lock ABI)."""
    spec = importlib.util.spec_from_file_location("awa_finish_for_clean_receipts", _FINISH_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FIN = _load_finish()


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
        return subprocess.run(["bash", self.dev_worktree, "clean", *args], cwd=str(self.repo_root),
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
        repo, wt = self._safe_worktree_with_ignored("ignored")
        r = self.run_clean("--path", wt)  # no --bundle / --force
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

    def test_ignored_scan_failed_refused(self) -> None:
        """unknown-evidence-blocks (the clean-path half): if the git-ignored scan ITSELF fails,
        child state is UNKNOWN, so the destructive remove must REFUSE (never proceed on an
        unclassifiable tree). Fault-injected via a `git` shim that fails only the --ignored scan."""
        import shutil
        _, wt = self.safe_worktree("ignoredscanfail")
        real_git = shutil.which("git")
        self.assertTrue(real_git, "git must be on PATH")
        shim_dir = Path(self._tmp.name) / "gitshim"
        shim_dir.mkdir(parents=True, exist_ok=True)
        shim = shim_dir / "git"
        shim.write_text(
            "#!/usr/bin/env bash\n"
            'for a in "$@"; do case "$a" in --ignored*) exit 128 ;; esac; done\n'
            f'exec "{real_git}" "$@"\n',
            encoding="utf-8")
        shim.chmod(0o755)
        env = {"PATH": f"{shim_dir}:{os.environ.get('PATH', '')}"}
        r = self.run_clean("--path", wt, env=env)
        self.assertNotEqual(r.returncode, 0, "an unknown ignored-scan result MUST refuse")
        rec = self.only_receipt(r)
        self.assertEqual((rec["disposition"], rec["reason_code"]), ("refused", "ignored_scan_failed"))
        self.assertTrue(Path(wt).exists(),
                        "the worktree MUST be preserved when child-state evidence is unknown")

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

    # ---- ordinary clean holds the shared per-common-dir lock (Fix 3) --------
    def test_lock_busy_refuses_and_preserves(self) -> None:
        """Fix 3: the ordinary `clean --path` destructive section runs under the SAME per-common-dir
        advisory lock as kernel finish + engine maintenance. A HELD lock makes the clean refuse
        (clean_lock_busy) fail-safe and preserves the worktree. Held here via a second open of the
        byte-identical lockfile in the test process (a different process from the clean shell)."""
        _, wt = self.safe_worktree("lockbusy")
        wt_real = str(Path(wt).resolve())
        common_dir = git(wt_real, "rev-parse", "--path-format=absolute",
                         "--git-common-dir").stdout.strip()
        # Hold the shared lock, then a concurrent ordinary clean must refuse within the short timeout.
        with FIN.common_dir_lock(common_dir, blocking=True, timeout=5.0):
            r = self.run_clean("--path", wt, env={"AWA_CLEAN_LOCK_TIMEOUT": "1"})
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        rec = self.only_receipt(r)
        self.assertEqual((rec["disposition"], rec["reason_code"]), ("refused", "clean_lock_busy"))
        self.assertTrue(Path(wt).exists(), "a lock-busy refusal MUST preserve the worktree")

    def test_uncontended_clean_still_removes_under_lock(self) -> None:
        """Fix 3 transparency: with NO contender the lock is acquired instantly and the ordinary
        clean removes exactly as before (the lock is write-serialization, not a worktree lock)."""
        _, wt = self.safe_worktree("lockfree")
        r = self.run_clean("--path", wt)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rec = self.only_receipt(r)
        self.assertEqual(rec["disposition"], "removed")
        self.assertFalse(Path(wt).exists())

    def _finish_lock_fault_helper(self, mode: str) -> str:
        helper = self.data_home / f"finish-lock-{mode}.py"
        lock_file = self.data_home / f"finish-lock-{mode}.lock"
        nonregular = self.data_home / f"finish-lock-{mode}.dir"
        nonregular.mkdir(exist_ok=True)
        symlink = self.data_home / f"finish-lock-{mode}.symlink"
        if mode == "symlink":
            lock_file.touch()
            symlink.symlink_to(lock_file)
        helper.write_text(
            "import os, sys\n"
            f"mode={mode!r}\n"
            f"lock={str(lock_file)!r}\n"
            f"nonregular={str(nonregular)!r}\n"
            f"symlink={str(symlink)!r}\n"
            "cmd=sys.argv[1] if len(sys.argv)>1 else ''\n"
            "if cmd == 'lock-ensure':\n"
            "    if mode == 'nonzero': raise SystemExit(23)\n"
            "    if mode == 'empty': raise SystemExit(0)\n"
            "    if mode == 'nonregular': print(nonregular); raise SystemExit(0)\n"
            "    if mode == 'symlink': print(symlink); raise SystemExit(0)\n"
            "    open(lock, 'a').close(); print(lock); raise SystemExit(0)\n"
            "if cmd == 'flock-fd':\n"
            "    raise SystemExit(75 if mode == 'acquire' else 0)\n"
            "raise SystemExit(2)\n",
            encoding="utf-8")
        return str(helper)

    def test_every_lock_setup_failure_refuses_even_with_force(self) -> None:
        bash_env = self.data_home / "fail-lock-exec.bash"
        bash_env.write_text("exec() { return 1; }\n", encoding="utf-8")
        scenarios = {
            "missing": (str(self.data_home / "missing-finish-helper.py"), {}),
            "nonzero": (self._finish_lock_fault_helper("nonzero"), {}),
            "empty": (self._finish_lock_fault_helper("empty"), {}),
            "nonregular": (self._finish_lock_fault_helper("nonregular"), {}),
            "symlink": (self._finish_lock_fault_helper("symlink"), {}),
            "open": (
                self._finish_lock_fault_helper("open"),
                {"BASH_ENV": str(bash_env)}),
            "acquire": (self._finish_lock_fault_helper("acquire"), {}),
        }
        for mode, (helper, extra_env) in scenarios.items():
            with self.subTest(mode=mode):
                _, wt = self.safe_worktree("lock-fault-" + mode)
                before = len(self.receipts())
                result = self.run_clean(
                    "--path", wt, "--force",
                    env={
                        "AWA_FINISH_LIB": helper, "AWA_CLEAN_LOCK_TIMEOUT": "0.01",
                        **extra_env,
                    })
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                receipts = self.receipts()
                self.assertEqual(len(receipts), before + 1)
                matching = [
                    receipt for receipt in receipts
                    if receipt.get("path") == str(Path(wt).resolve())]
                self.assertEqual(len(matching), 1, receipts)
                self.assertEqual(
                    (matching[0]["disposition"], matching[0]["reason_code"]),
                    ("refused", "clean_lock_busy"))
                self.assertTrue(Path(wt).exists(), mode)

    def test_lock_open_failure_has_explicit_fail_closed_branch(self) -> None:
        source = Path(self.dev_worktree).read_text(encoding="utf-8")
        self.assertIn('if ! { exec 9<>"$_lockfile"; } 2>/dev/null; then', source)
        self.assertIn(
            'clean_set_disposition refused clean_lock_busy "cannot open per-common-dir lockfile',
            source)

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
            # fail-CLOSED hardening reason codes (BLOCKER #1 / MAJOR #2 / MINOR #4)
            ("refused", "roots_lib_missing"), ("refused", "disposition_unavailable"),
            ("refused", "reactivated_during_clean"),
            # ordinary `clean --path` per-common-dir lock (Fix 3, additive-within-v1 2026-07-10):
            # the shared write-serialization lock held across the destructive section; on contention
            # the clean refuses fail-safe and preserves the worktree (covered behaviorally below).
            ("refused", "clean_lock_busy"),
            # Root-Bound Worktree Finish (Phase 1) terminal paths — additive-within-v1 (2026-07-10).
            # Each is a receipt-bearing `clean --finish-current` outcome; covered behaviorally in
            # engine/tests/test_finish_kernel.py.
            ("refused", "finish_bad_args"), ("refused", "finish_lib_missing"),
            ("refused", "finish_not_linked"), ("refused", "finish_preview"),
            ("refused", "finish_no_authorization"), ("refused", "finish_not_close"),
            ("refused", "finish_no_challenge"), ("refused", "finish_fingerprint_mismatch"),
            ("refused", "finish_target_mismatch"), ("refused", "finish_session_blocked"),
            ("refused", "finish_recheck_failed"), ("refused", "finish_inventory_unsafe"),
            ("refused", "finish_lock_busy"), ("removed", "finish_removed"),
            ("error", "finish_remove_failed"), ("error", "finish_error"),
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
