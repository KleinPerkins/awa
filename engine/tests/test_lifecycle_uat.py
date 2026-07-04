"""End-to-end engine-path lifecycle UAT (mandate: exercise the ENGINE path).

Drives the REAL CLI (`awa-engine.sh` -> `python3 -m engine`) through the full
lifecycle in a scratch repo: create (native-window worktree) -> adopt -> work ->
apply-back preview -> recovery (patch + bundle) -> cleanup-refusal/allow -> retire ->
daemon run-once. Asserts the safety guarantees hold at each step. Subprocess inherits
the isolated XDG env set by EngineTestCase, so it never touches the operator's state.
"""

from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path

from engine import guard, gitutil
from engine.tests.helpers import EngineTestCase, commit_all

_CLI = str(Path(__file__).resolve().parents[2] / "bin" / "awa-engine.sh")


class TestLifecycleUAT(EngineTestCase):
    def _cli(self, *args: str) -> dict:
        proc = subprocess.run([_CLI, *args], capture_output=True, text=True, env=os.environ.copy())
        self.assertTrue(proc.stdout.strip(), f"no stdout for {args}: {proc.stderr}")
        return json.loads(proc.stdout)

    def test_full_engine_lifecycle(self):
        # 1) CREATE — a native-window-style linked worktree.
        repo = self.make_repo()
        Path(repo, ".gitignore").write_text("*.localdb\n*.key\n", encoding="utf-8")
        commit_all(repo, "gitignore")
        wt = self.add_worktree(repo, "feat/ship")

        # 2) ADOPT (engine): lease recorded + attested, NO push.
        adopt = self._cli("adopt", "--worktree", wt)
        self.assertTrue(adopt["ok"])
        self.assertTrue(adopt["attested"])
        self.assertTrue(Path(wt, ".awa", "lease.json").exists())

        # lease-read + re-attest via the CLI (engine path).
        lr = self._cli("lease-read", "--worktree", wt)
        self.assertTrue(lr["ok"] and lr["valid"])
        self.assertTrue(self._cli("attest", "--worktree", wt)["ok"])

        # engine doctor is green (WAL + local disk + S4 perms)
        self.assertTrue(self._cli("doctor")["ok"])

        # 3) WORK — a real commit + an uncommitted edit + ignored files (secret + non-secret).
        Path(wt, "feature.txt").write_text("shipped\n", encoding="utf-8")
        commit_all(wt, "feature commit")
        Path(wt, "README.md").write_text("uncommitted\n", encoding="utf-8")
        Path(wt, "local.localdb").write_text("DB\n", encoding="utf-8")
        Path(wt, "secret.key").write_text("PRIVATE\n", encoding="utf-8")

        # guard: mutating in the adopted worktree is ALLOWED (Safe Workspace).
        g = self._cli("guard", "shell", "--cwd", wt, "--command", "git commit -am x")
        self.assertEqual(g["permission"], "allow")

        # 4) APPLY-BACK PREVIEW (engine): SHA-bound, preview-only, recovery-before-mutation.
        ab = self._cli("apply-back", "--worktree", wt)
        self.assertTrue(ab["ok"])
        self.assertTrue(ab["preview"])
        self.assertFalse(ab["mutated"])
        self.assertGreaterEqual(ab["commits_ahead"], 1)
        self.assertTrue(ab["recovery_patch"] and os.path.exists(ab["recovery_patch"]))

        # 5) CLEANUP-REFUSAL — the worktree is dirty + has local-only commits + ignored files.
        #    Assert via BOTH the direct guard and the engine CLI verb (engine-off guarantee).
        ok, why = guard.can_clean(wt)
        self.assertFalse(ok)
        self.assertFalse(self._cli("guard", "can-clean", "--worktree", wt)["can_clean"])

        # 6) RECOVERY — patch round-trip (uncommitted edit) + bundle ignored files.
        patch = self._cli("recover", "patch", "--worktree", wt)
        self.assertTrue(patch["has_changes"] and os.path.exists(patch["patch"]))
        bundle = self._cli("recover", "bundle", "--worktree", wt)
        self.assertIn("local.localdb", bundle["included"])
        self.assertIn("secret.key", bundle["skipped_secrets"])
        # the patch actually restores the uncommitted edit after it is discarded.
        gitutil.git(wt, "checkout", "--", "README.md")
        self.assertTrue(self._cli("recover", "restore-patch", "--worktree", wt, "--patch", patch["patch"])["ok"])
        self.assertEqual(Path(wt, "README.md").read_text(encoding="utf-8"), "uncommitted\n")

        # 7) integrate the branch into main so cleanup becomes safe, then clean uncommitted state.
        gitutil.git(wt, "checkout", "--", "README.md")   # drop the recovered edit again
        Path(wt, "local.localdb").unlink()
        Path(wt, "secret.key").unlink()
        gitutil.git(repo, "merge", "--no-edit", "feat/ship")   # bring the commit into main
        ok, why = guard.can_clean(wt)
        self.assertTrue(ok, why)
        self.assertTrue(self._cli("guard", "can-clean", "--worktree", wt)["can_clean"])

        # 8) RETIRE the lease (while the lease.json still exists on disk).
        self.assertTrue(self._cli("retire", "--worktree", wt)["ok"])

        # 9) SAFE CLEANUP — with the engine's can-clean gate GREEN, remove the worktree.
        gitutil.git(repo, "worktree", "remove", "--force", wt)
        self.assertFalse(Path(wt).exists())

        # 10) a daemon maintenance pass (single-instance) closes out the lifecycle.
        run = self._cli("daemon", "run-once")
        self.assertTrue(run["ok"])

        # audit trail records the whole lifecycle.
        events = self._cli("events")
        kinds = {e["kind"] for e in events["events"]}
        self.assertTrue({"adopt", "attest", "retire"} <= kinds, kinds)

    def test_publish_quarantine_cleanup_and_apply_back_execute(self):
        """ENGINE path: opt-in publish to a quarantine ref on a LOCAL bare remote, the
        daemon quarantine-cleanup loop, and the honest apply-back --execute gating."""
        repo = self.make_repo()
        bare = self.add_bare_remote(repo)
        wt = self.add_worktree(repo, "feat/publish")
        Path(wt, "f.txt").write_text("x\n", encoding="utf-8")
        commit_all(wt, "commit")
        self.assertTrue(self._cli("adopt", "--worktree", wt)["ok"])

        # apply-back --execute WITHOUT --confirm -> adapter preview (no mutation).
        prev = self._cli("apply-back", "--worktree", wt, "--execute")
        self.assertTrue(prev["ok"])
        self.assertFalse(prev["mutated"])

        # apply-back --execute --confirm with NO write token in env -> honest refusal
        # (S3: a write op never falls back to a read token).
        env = os.environ.copy()
        env.pop("AWA_GITHUB_WRITE_TOKEN", None)
        proc = subprocess.run([_CLI, "apply-back", "--worktree", wt, "--execute", "--confirm"],
                              capture_output=True, text=True, env=env)
        exec_res = json.loads(proc.stdout)
        self.assertFalse(exec_res["ok"])
        self.assertTrue(exec_res["error"])

        # OPT-IN publish to a quarantine ref, already expired (retention -1) so the
        # daemon cleanup loop reclaims it deterministically regardless of timezone.
        pub = self._cli("publish", "--worktree", wt, "--retention-days", "-1")
        self.assertTrue(pub["ok"])
        ref = pub["quarantine_ref"]
        self.assertTrue(ref.startswith("refs/awa/"))
        # the ref really landed on the bare remote (not a refs/heads/* branch).
        self.assertIn(ref, gitutil.git(bare, "show-ref")[1])

        # daemon run-once --delete-remote reclaims the expired quarantine ref (remote + state).
        run = self._cli("daemon", "run-once", "--delete-remote")
        self.assertIn(ref, run["summary"]["quarantine_cleaned"])
        self.assertNotIn(ref, gitutil.git(bare, "show-ref")[1])


if __name__ == "__main__":
    unittest.main()
