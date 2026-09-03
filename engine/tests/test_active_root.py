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
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

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

    def test_dual_timestamp_writer_samples_epoch_once(self) -> None:
        root = self.a_dir("single-clock")
        epoch = 1_700_000_000
        with mock.patch.object(AR, "_now_epoch", side_effect=[epoch]) as clock:
            rec = AR.heartbeat(root)
        self.assertEqual(clock.call_count, 1)
        self.assertEqual(rec["last_heartbeat_epoch"], epoch)
        self.assertEqual(rec["last_heartbeat"], AR._iso_from_epoch(epoch))
        member = rec["sessions"]["unattributed"]
        self.assertEqual(member["last_heartbeat_epoch"], epoch)
        self.assertEqual(member["last_heartbeat"], AR._iso_from_epoch(epoch))

    def test_heartbeat_normalizes_only_one_second_legacy_skew(self) -> None:
        root = self.a_dir("legacy-skew")
        AR.heartbeat(root, session_id="one", boot=AR.boot_id())
        AR.heartbeat(root, session_id="two", boot=AR.boot_id())
        path = Path(AR.record_path(root))
        rec = json.loads(path.read_text(encoding="utf-8"))
        one = rec["sessions"][AR.session_key("one")]
        one["last_heartbeat"] = AR._iso_from_epoch(one["last_heartbeat_epoch"] + 1)
        path.write_text(json.dumps(rec), encoding="utf-8")
        refreshed = AR.heartbeat(root, session_id="two", boot=AR.boot_id())
        normalized = refreshed["sessions"][AR.session_key("one")]
        self.assertEqual(
            normalized["last_heartbeat"],
            AR._iso_from_epoch(normalized["last_heartbeat_epoch"]))

        raw = path.read_bytes()
        malformed = json.loads(raw)
        member = malformed["sessions"][AR.session_key("one")]
        member["last_heartbeat"] = AR._iso_from_epoch(member["last_heartbeat_epoch"] + 2)
        path.write_text(json.dumps(malformed), encoding="utf-8")
        before = path.read_bytes()
        refused = AR.heartbeat(root, session_id="two", boot=AR.boot_id())
        self.assertFalse(refused["ok"])
        self.assertEqual(path.read_bytes(), before)

    # ---- session-aware branch-mismatch guard (fix: mid-session branch switch) ----------
    def test_heartbeat_same_session_branch_switch_now_succeeds(self) -> None:
        """BITING: before the fix, a SAME session's heartbeat on a real linked worktree, after
        an ordinary mid-session `git checkout` to a new branch, was refused with
        heartbeat_existing_branch_mismatch purely because the persisted top-level `branch` was
        stale -- even though _heartbeat_target_recheck had JUST, freshly, independently
        re-verified the new branch against live git ground truth under the same lock."""
        repo = self.make_repo("samesession")
        wt = self.add_worktree(repo, "fix/one")
        common = git(wt, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
        first = AR.heartbeat(wt, branch="fix/one", common_dir=common, session_id="agent-session")
        self.assertTrue(first.get("ok", True), first)
        self.assertEqual(first["branch"], "fix/one")

        git(wt, "checkout", "-q", "-b", "docs/two")
        second = AR.heartbeat(wt, branch="docs/two", common_dir=common, session_id="agent-session")
        self.assertTrue(second.get("ok", True), second)
        self.assertEqual(second["branch"], "docs/two")
        self.assertEqual(
            second["sessions"][AR.session_key("agent-session")]["branch"], "docs/two")
        self.assertEqual(AR.disposition(wt)["disposition"], "active")

    def test_heartbeat_different_session_branch_disagreement_still_refused(self) -> None:
        """BITING: protection preserved. A DIFFERENT, still-tracked session's own recorded
        branch claim disagreeing with a fresh heartbeat's branch must still refuse -- this is a
        genuine concurrent-use signal, not a stale same-session artifact."""
        repo = self.make_repo("diffsession")
        wt = self.add_worktree(repo, "feat/alpha")
        common = git(wt, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
        seeded = AR.heartbeat(wt, branch="feat/alpha", common_dir=common, session_id="session-a")
        self.assertTrue(seeded.get("ok", True), seeded)

        git(wt, "checkout", "-q", "-b", "feat/beta")
        before = Path(AR.record_path(wt)).read_bytes()
        refused = AR.heartbeat(wt, branch="feat/beta", common_dir=common, session_id="session-b")
        self.assertFalse(refused.get("ok", True), refused)
        self.assertEqual(refused["reason"], "heartbeat_existing_branch_mismatch")
        self.assertEqual(Path(AR.record_path(wt)).read_bytes(), before,
                         "a refused heartbeat must not mutate the persisted record")

    def test_heartbeat_common_dir_mismatch_still_refused_regardless_of_session(self) -> None:
        """BITING: the common_dir half of the guard is UNCHANGED -- still a hard, unconditional
        block regardless of session identity (a worktree's git_common_dir must never remap
        without the filesystem being torn down/rebuilt)."""
        root = self.a_dir("commondir")
        seeded = AR.heartbeat(root, common_dir="/tmp/awa-common-a", session_id="same-session")
        self.assertTrue(seeded.get("ok", True), seeded)
        before = Path(AR.record_path(root)).read_bytes()
        refused = AR.heartbeat(root, common_dir="/tmp/awa-common-b", session_id="same-session")
        self.assertFalse(refused.get("ok", True), refused)
        self.assertEqual(refused["reason"], "heartbeat_existing_common_dir_mismatch")
        self.assertEqual(Path(AR.record_path(root)).read_bytes(), before)

    def test_heartbeat_branch_conflict_check_is_per_session_not_last_writer(self) -> None:
        """Robustness: the conflict check must consult EVERY other currently-tracked session's
        OWN recorded claim, not merely whichever session's heartbeat most recently wrote the
        shared top-level fields. Session Z claims branch W; session A also agrees on W and (by
        coincidence) becomes the top-level's most recent writer; a real branch switch to X must
        still block A's OWN update, because Z -- a separate, still-tracked session -- has not
        (yet) agreed to X. A naive comparison that only checks whichever session wrote the
        top-level fields last would wrongly let this through, since A -- the confirming session
        -- also happens to be that last writer."""
        repo = self.make_repo("multisession")
        wt = self.add_worktree(repo, "shared/w")
        common = git(wt, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
        z1 = AR.heartbeat(wt, branch="shared/w", common_dir=common, session_id="session-z")
        self.assertTrue(z1.get("ok", True), z1)
        a1 = AR.heartbeat(wt, branch="shared/w", common_dir=common, session_id="session-a")
        self.assertTrue(a1.get("ok", True), a1)
        self.assertEqual(a1["session_id"], "session-a", "A is now the top-level last writer")

        git(wt, "checkout", "-q", "-b", "shared/x")
        blocked = AR.heartbeat(wt, branch="shared/x", common_dir=common, session_id="session-a")
        self.assertFalse(blocked.get("ok", True), blocked)
        self.assertEqual(
            blocked["reason"], "heartbeat_existing_branch_mismatch",
            "Z's own still-tracked claim of the OLD branch must still block A's update, even "
            "though A (not Z) wrote the top-level fields last")
        # The block is symmetric (a genuine two-session disagreement, not a one-sided bug): Z
        # moving alone is equally blocked by A's own still-tracked (and, since `blocked` above
        # never persisted, still stale) claim. This mutual-refusal-until-reconciled behavior
        # PRE-DATES this fix (the old top-level-only check could wedge on ANY mismatch, from any
        # cause); this fix only narrows which mismatches can trigger it -- resolving a genuine
        # multi-session disagreement automatically is out of scope here. The file's existing
        # `forget`/remove_root escape hatch (K2 TODO, above) is the documented recovery path.
        z_blocked = AR.heartbeat(wt, branch="shared/x", common_dir=common, session_id="session-z")
        self.assertFalse(z_blocked.get("ok", True), z_blocked)
        self.assertTrue(AR.remove_root(wt, common_dir=common))
        recovered = AR.heartbeat(wt, branch="shared/x", common_dir=common, session_id="session-a")
        self.assertTrue(recovered.get("ok", True), recovered)

    def _age_session_member(self, root: str, session_id: str, seconds_ago: int) -> None:
        """Rewrite ONE session member's last-heartbeat timestamps in place (other members are
        left untouched), so a test can make a specific tracked session look stale without
        disturbing the rest of the record. If this session is currently the record's top-level
        writer, the top-level projection fields are aged in lockstep -- the record's own
        member-projection invariant (top-level fields == that session's member fields) requires
        this; it is not itself part of what this test is exercising."""
        path = Path(AR.record_path(root))
        rec = json.loads(path.read_text(encoding="utf-8"))
        epoch = AR._now_epoch() - seconds_ago
        timestamp = AR._iso_from_epoch(epoch)
        member = rec["sessions"][AR.session_key(session_id)]
        member["last_heartbeat_epoch"] = epoch
        member["last_heartbeat"] = timestamp
        if member.get("first_seen"):
            first_epoch = AR._iso_to_epoch(member["first_seen"])
            if first_epoch is not None and first_epoch > epoch:
                member["first_seen"] = timestamp
        if rec.get("session_id") == session_id:
            rec["last_heartbeat_epoch"] = epoch
            rec["last_heartbeat"] = timestamp
            if rec.get("first_seen"):
                top_first_epoch = AR._iso_to_epoch(rec["first_seen"])
                if top_first_epoch is not None and top_first_epoch > epoch:
                    rec["first_seen"] = timestamp
        path.write_text(json.dumps(rec), encoding="utf-8")

    def test_heartbeat_stale_different_session_branch_disagreement_no_longer_vetoes(
            self) -> None:
        """BITING (fix, round 2): PR #82 made `other_session_disagrees` session-aware but not
        STALENESS-aware -- ANY other session EVER recorded against this root, however old,
        vetoed a heartbeat forever once its frozen `branch` disagreed with a fresh, live
        target-recheck. Reproduces the real field defect: two long-idle Cursor sessions
        (session-a on the ORIGINAL branch) left in `sessions`, then an ordinary later branch
        switch by session-b must not be vetoed by session-a's now-stale claim."""
        repo = self.make_repo("stalebranch")
        wt = self.add_worktree(repo, "shared/orig")
        common = git(wt, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
        seeded = AR.heartbeat(wt, branch="shared/orig", common_dir=common, session_id="session-a")
        self.assertTrue(seeded.get("ok", True), seeded)
        # Age session-a's OWN entry well past BRANCH_DISAGREEMENT_STALE_SECONDS (30 min) --
        # exactly like the real poisoned worktree's two ~11.6h-old entries, just clamped to
        # comfortably past this dedicated (shorter) threshold rather than the coarse 12h TTL.
        self._age_session_member(
            wt, "session-a", AR.BRANCH_DISAGREEMENT_STALE_SECONDS + 60)

        git(wt, "checkout", "-q", "-b", "shared/new")
        refreshed = AR.heartbeat(wt, branch="shared/new", common_dir=common, session_id="session-b")
        self.assertTrue(refreshed.get("ok", True), refreshed)
        self.assertEqual(refreshed["branch"], "shared/new")
        self.assertEqual(
            refreshed["sessions"][AR.session_key("session-b")]["branch"], "shared/new")
        # session-a's own stale entry is left as-is (minimal-risk: non-voting, not pruned) --
        # matching finish_session_gate's own established "stale neither blocks nor waives" style.
        self.assertEqual(
            refreshed["sessions"][AR.session_key("session-a")]["branch"], "shared/orig")
        self.assertEqual(AR.disposition(wt)["disposition"], "active")

    def test_heartbeat_branch_disagreement_freshness_boundary_is_exact(self) -> None:
        """Robustness: the freshness cutoff is the exact BRANCH_DISAGREEMENT_STALE_SECONDS
        boundary, not some other accidental threshold (e.g. the coarse 12h DEFAULT_TTL_SECONDS,
        which would NOT have cleared the real poisoned worktree -- its two entries were ~11.6h
        old, still 'fresh' by that measure)."""
        repo = self.make_repo("boundarybranch")
        wt = self.add_worktree(repo, "shared/orig")
        common = git(wt, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
        AR.heartbeat(wt, branch="shared/orig", common_dir=common, session_id="session-a")
        git(wt, "checkout", "-q", "-b", "shared/new")

        # Just UNDER the threshold -> still fresh -> still vetoes.
        self._age_session_member(
            wt, "session-a", AR.BRANCH_DISAGREEMENT_STALE_SECONDS - 5)
        still_blocked = AR.heartbeat(
            wt, branch="shared/new", common_dir=common, session_id="session-b")
        self.assertFalse(still_blocked.get("ok", True), still_blocked)
        self.assertEqual(still_blocked["reason"], "heartbeat_existing_branch_mismatch")

        # Just OVER the threshold -> stale -> no longer vetoes.
        self._age_session_member(
            wt, "session-a", AR.BRANCH_DISAGREEMENT_STALE_SECONDS + 5)
        now_allowed = AR.heartbeat(
            wt, branch="shared/new", common_dir=common, session_id="session-b")
        self.assertTrue(now_allowed.get("ok", True), now_allowed)

    # ---- bind_current_session has the SAME defect one level up (fix, cont.) -----------
    def test_bind_current_session_same_session_branch_switch_now_succeeds(self) -> None:
        """BITING: bind_current_session's OWN `same_target` check compares `prior.branch` to
        the freshly live-reverified incoming branch UNCONDITIONALLY, one level above heartbeat().
        Fixing heartbeat() alone left this reproducing the identical original symptom (fail-open
        on an ordinary mid-session branch switch) through _bind_hook_current_session, just under
        a different reason string (current_session_target_mismatch instead of
        heartbeat_existing_branch_mismatch) -- proven directly below and end-to-end in
        test_finish_conversation.HookAndDispatcherTest."""
        repo = self.make_repo("bindsamesession")
        wt = self.add_worktree(repo, "fix/one")
        common = git(wt, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
        first = AR.bind_current_session(
            wt, session_id="agent-session", conversation_id="conv-1", branch="fix/one",
            common_dir=common, source="beforeSubmitPrompt")
        self.assertTrue(first.get("ok"), first)

        git(wt, "checkout", "-q", "-b", "docs/two")
        second = AR.bind_current_session(
            wt, session_id="agent-session", conversation_id="conv-1", branch="docs/two",
            common_dir=common, source="beforeSubmitPrompt")
        self.assertTrue(second.get("ok"), second)
        self.assertEqual(second["current_session"]["branch"], "docs/two")

    def test_bind_current_session_different_session_branch_disagreement_still_refused(
            self) -> None:
        """BITING: protection preserved -- a DIFFERENT session's own prior current-session claim
        disagreeing about the branch must still refuse bind_current_session, exactly mirroring
        heartbeat()'s unchanged cross-session protection."""
        repo = self.make_repo("binddiffsession")
        wt = self.add_worktree(repo, "feat/alpha")
        common = git(wt, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
        seeded = AR.bind_current_session(
            wt, session_id="session-a", conversation_id="conv-a", branch="feat/alpha",
            common_dir=common, source="beforeSubmitPrompt")
        self.assertTrue(seeded.get("ok"), seeded)

        git(wt, "checkout", "-q", "-b", "feat/beta")
        refused = AR.bind_current_session(
            wt, session_id="session-b", conversation_id="conv-b", branch="feat/beta",
            common_dir=common, source="beforeSubmitPrompt")
        self.assertFalse(refused.get("ok"), refused)
        self.assertEqual(refused["reason"], "current_session_target_mismatch")

    def test_bind_current_session_stale_prior_self_heals_via_session_start(self) -> None:
        """Investigation finding (NOT a bug -- proven here so it never silently regresses):
        unlike heartbeat()'s accumulating `sessions` dict, `current_session` is a SINGLE
        CAS-replaceable record, and `sessionStart` may replace a DIFFERENT session's prior claim
        UNCONDITIONALLY (identity-independent), regardless of how stale that prior claim is --
        there is no time-based veto to go unbounded in the first place. An arbitrarily old prior
        claim from a long-dead session is superseded the moment the new session's sessionStart
        hook runs, exactly as for a claim written a second ago. beforeSubmitPrompt alone (no
        sessionStart) legitimately still refuses (current_session_session_mismatch) -- that race
        is already bounded by _bind_hook_current_session's own short retry-with-deadline loop,
        not by staleness."""
        repo = self.make_repo("bindstaleheals")
        wt = self.add_worktree(repo, "feat/alpha")
        common = git(wt, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
        seeded = AR.bind_current_session(
            wt, session_id="session-a", conversation_id="conv-a", branch="feat/alpha",
            common_dir=common, source="beforeSubmitPrompt")
        self.assertTrue(seeded.get("ok"), seeded)
        # Age the (single) current_session record WAY past any staleness window this file uses
        # anywhere (12h default TTL) -- if this were the same unbounded-veto defect class, this
        # would still block a different session's beforeSubmitPrompt bind forever.
        path = Path(AR.current_session_path(wt))
        rec = json.loads(path.read_text(encoding="utf-8"))
        rec["updated_at_epoch"] = AR._now_epoch() - (AR.DEFAULT_TTL_SECONDS * 10)
        path.write_text(json.dumps(rec), encoding="utf-8")

        still_refused = AR.bind_current_session(
            wt, session_id="session-b", conversation_id="conv-b", branch="feat/alpha",
            common_dir=common, source="beforeSubmitPrompt")
        self.assertFalse(still_refused.get("ok"), still_refused)
        self.assertEqual(still_refused["reason"], "current_session_session_mismatch")

        healed = AR.bind_current_session(
            wt, session_id="session-b", conversation_id="conv-b", branch="feat/alpha",
            common_dir=common, source="sessionStart")
        self.assertTrue(healed.get("ok"), healed)
        current, status = AR.read_current_session(wt)
        self.assertEqual(status, "ok")
        self.assertEqual(current["session_id"], "session-b")

    # ---- finish_session_evidence has the SAME defect one level further downstream ----
    def test_finish_session_evidence_stale_disagreeing_session_no_longer_malformed(
            self) -> None:
        """BITING (fix, round 3): fixing heartbeat() alone left the real end-to-end repro dying
        one layer further downstream, in finish_session_gate's OWN evidence-validation helper
        (_finish_session_evidence_locked). ANY session member's frozen `branch` disagreeing with
        the CURRENT live branch made the whole evidence set `session_malformed`, regardless of
        that member's staleness -- even though finish_session_gate's OWN freshness loop, right
        below this helper in the same file, already correctly treats a stale member as neither
        blocking nor waiving. This is the exact reason the real poisoned worktree's repro still
        failed (reason=session_malformed) immediately after fixing heartbeat() alone."""
        repo = self.make_repo("evidencestale")
        wt = self.add_worktree(repo, "shared/orig")
        common = git(wt, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
        AR.heartbeat(wt, branch="shared/orig", common_dir=common, session_id="session-a")
        self._age_session_member(
            wt, "session-a", AR.BRANCH_DISAGREEMENT_STALE_SECONDS + 60)
        git(wt, "checkout", "-q", "-b", "shared/new")
        confirmed = AR.heartbeat(
            wt, branch="shared/new", common_dir=common, session_id="session-b")
        self.assertTrue(confirmed.get("ok", True), confirmed)

        evidence = AR.finish_session_evidence(
            wt, confirming_session_key=AR.session_key("session-b"),
            branch="shared/new", common_dir=common)
        self.assertTrue(evidence.get("ok"), evidence)
        self.assertIn(AR.session_key("session-a"), evidence["membership"])

        # A FRESH disagreement must still be treated as malformed/blocking evidence -- defense in
        # depth parity with heartbeat()'s own guard, which in the ordinary flow already refuses
        # first for a fresh disagreement (so this shape cannot normally arise via the public API;
        # construct it directly, matching this file's existing convention for edge cases, e.g.
        # test_reboot_heartbeat_prunes_valid_old_members_and_preserves_mixed_projection above).
        path = Path(AR.record_path(wt))
        rec = json.loads(path.read_text(encoding="utf-8"))
        fresh_epoch = AR._now_epoch()
        rec["sessions"][AR.session_key("session-a")] = {
            "session_id": "session-a", "pid": None, "boot_id": AR.boot_id(),
            "branch": "shared/other", "git_common_dir": common,
            "first_seen": AR._iso_from_epoch(fresh_epoch),
            "last_heartbeat": AR._iso_from_epoch(fresh_epoch),
            "last_heartbeat_epoch": fresh_epoch,
        }
        path.write_text(json.dumps(rec), encoding="utf-8")
        fresh_disagreement = AR.finish_session_evidence(
            wt, confirming_session_key=AR.session_key("session-b"),
            branch="shared/new", common_dir=common)
        self.assertFalse(fresh_disagreement.get("ok"), fresh_disagreement)
        self.assertEqual(fresh_disagreement["reason"], "session_malformed")
        self.assertEqual(fresh_disagreement["detail"], "session_target_or_timestamp_invalid")

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
        # ...but AGE the record far past the (default) TTL so the canonical disposition is STALE.
        # We age the record rather than exporting AWA_HEARTBEAT_TTL_SECONDS=0, because that env
        # value is now CLAMPED (MINOR #6) — a stray `0` must never be able to disable protection.
        rp = Path(AR.record_path(wt))
        rec = json.loads(rp.read_text(encoding="utf-8"))
        rec["last_heartbeat_epoch"] = int(time.time()) - 100000
        rec["last_heartbeat"] = "2000-01-01T00:00:00Z"
        rec.pop("pid", None)  # no live pid -> falls to the (expired) TTL branch
        rp.write_text(json.dumps(rec), encoding="utf-8")
        self.assertEqual(AR.disposition(wt)["disposition"], "stale")
        env = os.environ.copy()
        env["AWA_HOME"] = str(_REPO_ROOT)
        r = subprocess.run(["bash", self.dev_worktree, "clean", "--path", wt, "--delete-branch"],
                           cwd=str(_REPO_ROOT), env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(Path(wt).exists())

    # ---- sessionStart hook: heartbeat refresh + dead-root guidance ----------
    def _run_session_hook(
        self,
        cwd: str,
        *,
        home: Path | None = None,
        cache_home: Path | None = None,
    ) -> dict:
        payload = json.dumps({
            "workspace_roots": [cwd],
            "conversation_id": "conversation-realistic",
            "session_id": "session-realistic",
        })
        env = os.environ.copy()
        env["AWA_HOME"] = str(_REPO_ROOT)
        home_path = home if home is not None else self.data_home / "home"
        if home is None:
            home_path.mkdir(mode=0o700, exist_ok=True)
        env["HOME"] = str(home_path)
        cache_path = (
            cache_home if cache_home is not None else self.data_home / "cache"
        )
        if cache_home is None:
            cache_path.mkdir(mode=0o700, exist_ok=True)
        env["XDG_CACHE_HOME"] = str(cache_path)
        r = subprocess.run(["bash", self.session_hook], input=payload, cwd=cwd,
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
        rec, status = AR.read_current_session(wt)
        self.assertEqual(status, "ok")
        self.assertEqual(rec["session_id"], "session-realistic")
        target_branch = git(wt, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        target_common = git(
            wt, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
        self.assertEqual(rec["branch"], target_branch)
        self.assertEqual(rec["common_dir"], target_common)
        active, corrupt = AR.read_record(wt)
        self.assertFalse(corrupt)
        member = active["sessions"][AR.session_key("session-realistic")]
        contract = json.loads(
            (_REPO_ROOT / "contracts" / "awa-contract.v1.json").read_text(encoding="utf-8"))
        self.assertEqual(set(member), set(contract["active_root"]["sessions_field"][
            "member_declared_keys"]))
        self.assertNotIn("unattributed", active["sessions"])

    def test_guard_payload_or_current_identity_never_mints_unattributed(self) -> None:
        repo = self.make_repo("guardidentity")
        wt = self.add_worktree(repo, "feat/identity")
        target_branch = git(wt, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        target_common = git(
            wt, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
        AR.write_current_session(
            wt, session_id="real-session", conversation_id="real-conversation",
            branch=target_branch, common_dir=target_common)
        payload = json.dumps({"command": "ls", "workspace_roots": [wt]})
        env = os.environ.copy()
        env.pop("DEV_SESSION_ID", None)
        env["AWA_HEARTBEAT_REFRESH_THROTTLE"] = "0"
        result = subprocess.run(
            ["bash", self.guard_hook], input=payload, cwd=wt, env=env,
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        record, corrupt = AR.read_record(wt)
        self.assertFalse(corrupt)
        self.assertIn(AR.session_key("real-session"), record["sessions"])
        self.assertNotIn("unattributed", record["sessions"])

    def test_delayed_current_binding_after_removal_creates_no_phantom_state(self) -> None:
        repo = self.make_repo("bindingbarrier")
        wt = self.add_worktree(repo, "feat/barrier")
        branch = git(wt, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        common = git(
            wt, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
        entered = threading.Event()
        proceed = threading.Event()
        result: dict = {}
        real_lock = AR._common_dir_lock

        @contextmanager
        def delayed_lock(*args, **kwargs):
            entered.set()
            self.assertTrue(proceed.wait(5))
            with real_lock(*args, **kwargs):
                yield

        def bind() -> None:
            result.update(AR.bind_current_session(
                wt, session_id="late", conversation_id="late-conversation",
                branch=branch, common_dir=common, source="sessionStart"))

        with mock.patch.object(AR, "_common_dir_lock", delayed_lock):
            worker = threading.Thread(target=bind)
            worker.start()
            self.assertTrue(entered.wait(5))
            git(repo, "worktree", "remove", "--force", wt)
            proceed.set()
            worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertFalse(result["ok"], result)
        self.assertIn("root_absent", result["reason"])
        self.assertEqual(AR.read_current_session(wt)[1], "absent")
        self.assertFalse(Path(AR.record_path(wt)).exists())

    def test_prior_boot_current_session_replaced_but_malformed_bytes_preserved(self) -> None:
        repo = self.make_repo("currentreboot")
        wt = self.add_worktree(repo, "feat/reboot")
        branch = git(wt, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        common = git(
            wt, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
        old = AR.write_current_session(
            wt, session_id="old", conversation_id="old-conversation",
            branch=branch, common_dir=common)
        path = Path(AR.current_session_path(wt))
        old["boot_id"] = "prior-boot"
        path.write_text(json.dumps(old), encoding="utf-8")
        replaced = AR.bind_current_session(
            wt, session_id="new", conversation_id="new-conversation",
            branch=branch, common_dir=common, source="sessionStart")
        self.assertTrue(replaced["ok"], replaced)
        self.assertTrue(replaced["replaced_prior_boot"])
        current, status = AR.read_current_session(wt)
        self.assertEqual(status, "ok")
        self.assertEqual(current["session_id"], "new")

        malformed = dict(current)
        malformed["boot_id"] = "another-prior-boot"
        malformed["updated_at_epoch"] = "bad"
        path.write_text(json.dumps(malformed), encoding="utf-8")
        before = path.read_bytes()
        refused = AR.bind_current_session(
            wt, session_id="third", conversation_id="third-conversation",
            branch=branch, common_dir=common, source="sessionStart")
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["reason"], "current_session_malformed")
        self.assertEqual(path.read_bytes(), before)

        partial = dict(current)
        partial["session_id"] = "partial-old"
        partial["session_key"] = AR.session_key("partial-old")
        partial["conversation_id"] = ""
        partial["boot_id"] = "partial-prior-boot"
        path.write_text(json.dumps(partial), encoding="utf-8")
        partial_replaced = AR.bind_current_session(
            wt, session_id="third", conversation_id="third-conversation",
            branch=branch, common_dir=common, source="beforeSubmitPrompt")
        self.assertTrue(partial_replaced["ok"], partial_replaced)
        self.assertTrue(partial_replaced["replaced_prior_boot"])
        cleanup = AR.remove_current_session_cas(
            wt, session_id=current["session_id"],
            conversation_id=current["conversation_id"], branch=branch,
            common_dir=common, expected_boot_id=current["boot_id"])
        self.assertTrue(cleanup["ok"])
        self.assertEqual(cleanup["reason"], "superseded")
        surviving, surviving_status = AR.read_current_session(wt)
        self.assertEqual(surviving_status, "ok")
        self.assertEqual(surviving["session_id"], "third")

    def test_reboot_heartbeat_prunes_valid_old_members_and_preserves_mixed_projection(self) -> None:
        root = self.a_dir("heartbeat-reboot")
        current_boot = AR.boot_id()
        AR.heartbeat(root, session_id="old-member", boot=current_boot)
        AR.heartbeat(root, session_id="current-member", boot=current_boot)
        path = Path(AR.record_path(root))
        rec = json.loads(path.read_text(encoding="utf-8"))
        rec["sessions"][AR.session_key("old-member")]["boot_id"] = "prior-boot"
        path.write_text(json.dumps(rec), encoding="utf-8")
        pruned = AR.heartbeat(root, session_id="current-member", boot=current_boot)
        self.assertEqual(pruned["schema"], "active_root/v1")
        self.assertEqual(set(pruned["sessions"]), {AR.session_key("current-member")})

        mixed = json.loads(path.read_text(encoding="utf-8"))
        mixed["sessions"][AR.session_key("prior-top")] = dict(
            mixed["sessions"][AR.session_key("current-member")],
            session_id="prior-top", boot_id="prior-boot")
        top = mixed["sessions"][AR.session_key("prior-top")]
        for key in (
                "session_id", "pid", "boot_id", "branch", "git_common_dir",
                "first_seen", "last_heartbeat", "last_heartbeat_epoch"):
            mixed[key] = top[key]
        path.write_text(json.dumps(mixed), encoding="utf-8")
        before = path.read_bytes()
        refused = AR.heartbeat(root, session_id="current-member", boot=current_boot)
        self.assertFalse(refused["ok"], refused)
        self.assertEqual(refused["reason"], "heartbeat_mixed_boot_projection")
        self.assertEqual(path.read_bytes(), before)

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
        home = self.data_home / "home-is-a-file"
        cache_home = self.data_home / "cache-is-a-file"
        home.write_text("not a directory", encoding="utf-8")
        cache_home.write_text("not a directory", encoding="utf-8")
        out = self._run_session_hook(
            str(self.data_home),
            home=home,
            cache_home=cache_home,
        )
        self.assertIn("additional_context", out)

    # ---- MAJOR #3: the guard hot-path keeps an actively-used session alive past the raw TTL ----
    @property
    def guard_hook(self) -> str:
        return str(_REPO_ROOT / "kernel" / "hooks" / "worktree-guard.sh")

    def _run_guard(self, cwd: str, command: str = "ls") -> subprocess.CompletedProcess:
        payload = json.dumps({"command": command, "workspace_roots": [cwd]})
        env = os.environ.copy()
        env["AWA_HOME"] = str(_REPO_ROOT)
        env["DEV_SESSION_ID"] = "guard-refresh-test"
        env["AWA_HEARTBEAT_REFRESH_THROTTLE"] = "0"  # deterministic: never throttle in-test
        # ensure no ambient cloud signal degrades the guard to a no-op allow
        for k in ("CURSOR_BACKGROUND_AGENT", "CURSOR_CLOUD_AGENT", "IS_BACKGROUND_AGENT",
                  "AWA_FORCE_CLOUD"):
            env.pop(k, None)
        return subprocess.run(["bash", self.guard_hook], input=payload, cwd=cwd, env=env,
                              capture_output=True, text=True)

    def _age_heartbeat(self, root: str, seconds_ago: int = 100000) -> None:
        rp = Path(AR.record_path(root))
        rec = json.loads(rp.read_text(encoding="utf-8"))
        epoch = int(time.time()) - seconds_ago
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))
        rec["first_seen"] = timestamp
        rec["last_heartbeat_epoch"] = epoch
        rec["last_heartbeat"] = timestamp
        rec.pop("pid", None)
        for member in (rec.get("sessions") or {}).values():
            member["first_seen"] = timestamp
            member["last_heartbeat_epoch"] = epoch
            member["last_heartbeat"] = timestamp
            member["pid"] = None
        rp.write_text(json.dumps(rec), encoding="utf-8")

    def test_guard_hotpath_refresh_keeps_active_session_alive_past_ttl(self) -> None:
        """A genuinely-active session older than the raw TTL (or one where sessionStart never
        fired) would otherwise go STALE -> freely removable. Running ANY command in the worktree
        must refresh the heartbeat so wall-clock alone cannot downgrade an active session."""
        repo = self.make_repo("guardrefresh")
        wt = self.add_worktree(repo, "feat/g")
        AR.heartbeat(wt)
        self._age_heartbeat(wt)  # older than the TTL -> stale WITHOUT a refresh
        self.assertEqual(AR.disposition(wt)["disposition"], "stale",
                         "precondition: an un-refreshed old heartbeat is stale")
        r = self._run_guard(wt, "ls")  # activity -> guard refreshes
        self.assertIn('"permission": "allow"', r.stdout, r.stdout + r.stderr)
        self.assertEqual(AR.disposition(wt)["disposition"], "active",
                         "an actively-used session must NOT be stale past the raw TTL")

    def test_guard_hotpath_creates_heartbeat_when_sessionstart_missed(self) -> None:
        """Even if sessionStart never fired (no record at all), the first command in a linked
        worktree creates the heartbeat -> the Safe Workspace becomes protected."""
        repo = self.make_repo("guardcreate")
        wt = self.add_worktree(repo, "feat/gc")
        self.assertEqual(AR.disposition(wt)["disposition"], "untracked")  # no record yet
        self._run_guard(wt, "ls")
        self.assertEqual(AR.disposition(wt)["disposition"], "active")

    def test_guard_hotpath_does_not_heartbeat_primary_checkout(self) -> None:
        """The primary checkout is never a removal target and must not acquire a blocking
        heartbeat (git-dir == git-common-dir)."""
        repo = self.make_repo("guardprimary")
        self._run_guard(repo, "ls")
        self.assertIn(AR.disposition(repo)["disposition"], ("untracked", "absent"),
                      "the primary checkout must not be heart-beaten")

    # ---- MINOR #6: TTL env clamp (a stray 0 / negative / garbage cannot disable protection) ----
    def test_ttl_env_is_clamped(self) -> None:
        saved = os.environ.get("AWA_HEARTBEAT_TTL_SECONDS")
        try:
            for raw, expect in (("0", AR.DEFAULT_TTL_SECONDS),
                                ("-5", AR.DEFAULT_TTL_SECONDS),
                                ("not-an-int", AR.DEFAULT_TTL_SECONDS),
                                ("10", AR.MIN_TTL_SECONDS),      # below floor -> clamped up
                                ("600", 600)):                    # above floor -> honored
                os.environ["AWA_HEARTBEAT_TTL_SECONDS"] = raw
                self.assertEqual(AR._ttl_seconds(), expect, f"TTL env {raw!r}")
        finally:
            if saved is None:
                os.environ.pop("AWA_HEARTBEAT_TTL_SECONDS", None)
            else:
                os.environ["AWA_HEARTBEAT_TTL_SECONDS"] = saved

    def test_ttl_env_zero_does_not_make_fresh_heartbeat_removable(self) -> None:
        """The safety proof: with AWA_HEARTBEAT_TTL_SECONDS=0 a FRESH active heartbeat is STILL
        active (env 0 is clamped to the default), so a stray export cannot flip every pid-less
        active workspace to removable."""
        root = self.a_dir("ttlzero")
        AR.heartbeat(root)
        saved = os.environ.get("AWA_HEARTBEAT_TTL_SECONDS")
        try:
            os.environ["AWA_HEARTBEAT_TTL_SECONDS"] = "0"
            d = AR.disposition(root)
            self.assertEqual(d["disposition"], "active")
            self.assertTrue(d["blocks_removal"])
        finally:
            if saved is None:
                os.environ.pop("AWA_HEARTBEAT_TTL_SECONDS", None)
            else:
                os.environ["AWA_HEARTBEAT_TTL_SECONDS"] = saved


if __name__ == "__main__":
    import unittest
    unittest.main()
