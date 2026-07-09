"""K1: per-root active_root/v1 heartbeat + canonical disposition + removal refusal.

Canonical disposition (awa_roots.disposition) is the SINGLE source of truth consulted by BOTH
the kernel clean gate and the sessionStart hook. This module proves the state machine
(active | stale | dead | untracked | absent), the removal rule (active BLOCKS, stale ALLOWS,
dead GUIDES), the unknown-evidence-blocks fail-safe, the symlink-prefix agreement that keeps the
heartbeat writer and the clean gate on the SAME record, and the sessionStart hook behavior.

Kernel-only: awa_roots.py is stdlib-only and imported directly; the hook + gate are driven as
subprocesses so the guarantee is proven with the Python engine OFF.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import time
from pathlib import Path

from .helpers import EngineTestCase, commit_all, git

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROOTS_PY = _REPO_ROOT / "kernel" / "lib" / "awa_roots.py"


def _load_awa_roots():
    spec = importlib.util.spec_from_file_location("awa_roots_under_test", _ROOTS_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


AR = _load_awa_roots()


class ActiveRootTest(EngineTestCase):
    @property
    def dev_worktree(self) -> str:
        return str(_REPO_ROOT / "kernel" / "bin" / "dev-worktree.sh")

    @property
    def session_hook(self) -> str:
        return str(_REPO_ROOT / "kernel" / "hooks" / "worktree-session.sh")

    def a_dir(self, name: str = "root") -> str:
        d = self.data_home / name
        d.mkdir(parents=True, exist_ok=True)
        return str(d)

    # ---- record shape + fresh heartbeat is ACTIVE ---------------------------
    def test_fresh_heartbeat_is_active_and_blocks(self) -> None:
        root = self.a_dir("fresh")
        rec = AR.heartbeat(root)
        for k in ("schema", "root_path", "git_common_dir", "boot_id", "first_seen",
                  "last_heartbeat", "last_heartbeat_epoch"):
            self.assertIn(k, rec, rec)
        self.assertEqual(rec["schema"], "active_root/v1")
        d = AR.disposition(root)
        self.assertEqual(d["disposition"], "active")
        self.assertTrue(d["blocks_removal"])

    def test_first_seen_preserved_across_refresh(self) -> None:
        root = self.a_dir("firstseen")
        r1 = AR.heartbeat(root)
        time.sleep(1)
        r2 = AR.heartbeat(root)
        self.assertEqual(r1["first_seen"], r2["first_seen"])
        self.assertGreaterEqual(r2["last_heartbeat_epoch"], r1["last_heartbeat_epoch"])

    # ---- STALE (TTL) allows -------------------------------------------------
    def test_ttl_expired_is_stale_and_allows(self) -> None:
        root = self.a_dir("stale")
        AR.heartbeat(root)
        d = AR.disposition(root, ttl=0)  # TTL=0 -> any age >= 0 is expired
        self.assertEqual(d["disposition"], "stale")
        self.assertFalse(d["blocks_removal"])

    # ---- DEAD (path gone) guides --------------------------------------------
    def test_removed_path_is_dead(self) -> None:
        root = self.a_dir("dead")
        AR.heartbeat(root)
        os.rmdir(root)
        d = AR.disposition(root)
        self.assertEqual(d["disposition"], "dead")
        self.assertFalse(d["blocks_removal"])
        # records are keyed by the CANONICAL (realpath) root path
        self.assertIn(AR.canon(root), [r["root_path"] for r in AR.dead_roots()])

    # ---- UNTRACKED / ABSENT -------------------------------------------------
    def test_untracked_and_absent(self) -> None:
        root = self.a_dir("untracked")
        self.assertEqual(AR.disposition(root)["disposition"], "untracked")
        missing = str(self.data_home / "never-existed")
        self.assertEqual(AR.disposition(missing)["disposition"], "absent")

    # ---- unknown-evidence-blocks (corrupt record / unparseable time) --------
    def test_corrupt_record_is_active_failsafe(self) -> None:
        root = self.a_dir("corrupt")
        AR.heartbeat(root)
        Path(AR.record_path(root)).write_text("{ not json", encoding="utf-8")
        d = AR.disposition(root)
        self.assertEqual(d["disposition"], "active", "corrupt record must fail-safe ACTIVE")
        self.assertTrue(d["blocks_removal"])

    def test_unparseable_heartbeat_time_is_active_failsafe(self) -> None:
        root = self.a_dir("notime")
        rec = AR.heartbeat(root)
        rec["last_heartbeat_epoch"] = "not-a-number"
        rec["last_heartbeat"] = "not-a-time"
        Path(AR.record_path(root)).write_text(json.dumps(rec), encoding="utf-8")
        d = AR.disposition(root)
        self.assertEqual(d["disposition"], "active")
        self.assertTrue(d["blocks_removal"])

    # ---- pid liveness (strong signal on the same boot) ----------------------
    def test_live_pid_same_boot_is_active(self) -> None:
        root = self.a_dir("livepid")
        AR.heartbeat(root, pid=os.getpid(), boot=AR.boot_id())
        self.assertEqual(AR.disposition(root)["disposition"], "active")

    def test_dead_pid_same_boot_is_stale(self) -> None:
        root = self.a_dir("deadpid")
        proc = subprocess.Popen(["python3", "-c", "pass"])
        proc.wait()  # reaped -> pid no longer alive
        AR.heartbeat(root, pid=proc.pid, boot=AR.boot_id())
        d = AR.disposition(root)
        self.assertEqual(d["disposition"], "stale")
        self.assertFalse(d["blocks_removal"])

    # ---- canonical: symlinked prefix agrees (macOS /tmp -> /private/tmp) -----
    def test_symlink_prefix_resolves_to_same_record(self) -> None:
        real = self.a_dir("realroot")
        link = str(self.data_home / "linkroot")
        os.symlink(real, link)
        AR.heartbeat(link)            # write keyed via the symlinked path
        d = AR.disposition(real)      # look up via the real path
        self.assertEqual(d["disposition"], "active",
                         "heartbeat writer and clean gate must key the SAME record regardless of symlink")

    # ---- remove_root clears the record (no phantom dead) --------------------
    def test_remove_root_is_idempotent_and_clears(self) -> None:
        root = self.a_dir("removeroot")
        AR.heartbeat(root)
        self.assertTrue(AR.remove_root(root))
        self.assertEqual(AR.disposition(root)["disposition"], "untracked")
        self.assertFalse(AR.remove_root(root), "second remove is a no-op")

    # ---- gate integration: stale ALLOWS a real clean -----------------------
    def test_stale_heartbeat_allows_clean(self) -> None:
        repo = self.make_repo("staleclean")
        wt = self.add_worktree(repo, "feat/s")
        Path(wt, "feature.txt").write_text("f\n", encoding="utf-8")
        commit_all(wt, "feature")
        git(repo, "checkout", "-q", "main")
        git(repo, "merge", "--squash", "feat/s")
        commit_all(repo, "squash")
        AR.heartbeat(wt)  # active...
        env = os.environ.copy()
        env["AWA_HOME"] = str(_REPO_ROOT)
        env["AWA_HEARTBEAT_TTL_SECONDS"] = "0"  # ...but TTL=0 -> stale -> allows removal
        r = subprocess.run([self.dev_worktree, "clean", "--path", wt, "--delete-branch"],
                           cwd=str(_REPO_ROOT), env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(Path(wt).exists())

    # ---- sessionStart hook: heartbeat refresh + dead-root guidance ----------
    def _run_session_hook(self, cwd: str) -> dict:
        payload = json.dumps({"workspace_roots": [cwd]})
        env = os.environ.copy()
        env["AWA_HOME"] = str(_REPO_ROOT)
        r = subprocess.run([self.session_hook], input=payload, cwd=cwd,
                           env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def test_session_hook_refreshes_heartbeat_in_worktree(self) -> None:
        repo = self.make_repo("sess")
        wt = self.add_worktree(repo, "feat/sess")
        out = self._run_session_hook(wt)
        self.assertIn("additional_context", out)
        self.assertEqual(AR.disposition(wt)["disposition"], "active",
                         "sessionStart in a linked worktree must refresh its heartbeat")

    def test_session_hook_surfaces_dead_root_guidance(self) -> None:
        repo = self.make_repo("deadsess")
        wt = self.add_worktree(repo, "feat/dead")
        AR.heartbeat(wt)
        # Out-of-band deletion (NOT via clean) -> a DEAD recorded root.
        git(repo, "worktree", "remove", "--force", wt)
        out = self._run_session_hook(repo)
        self.assertIn("no longer exists on disk", out["additional_context"])
        self.assertIn(str(Path(wt).resolve()), out["additional_context"])

    def test_session_hook_is_failsafe_json_even_outside_worktree(self) -> None:
        out = self._run_session_hook(str(self.data_home))
        self.assertIn("additional_context", out)


if __name__ == "__main__":
    import unittest
    unittest.main()
