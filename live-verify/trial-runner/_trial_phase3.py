"""_trial_phase3.py — Phase 3 recovery-retention lifecycle transitions.

Driven through the REAL engine retention API (the SAME public surface ``engine/tests/test_retention.py``
asserts) plus the ``python3 -m engine recover|daemon`` CLI, the dashboard emitter probe, and the
``awa-recovery-maintenance.sh`` sessionStart hook. Every row cites the oracle class it mirrors.
Everything is confined to the sandbox: a per-transition ``recovery_dir`` under the temp sandbox and
the sandbox ``XDG_STATE_HOME`` state db; the real recovery store is never touched.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from _trial_lib import (REPO, INSTALL_SH, HOOK_RECOVERY, Row, Sandbox, check, check_eq,
                        stat_mode, transition)

# The engine public API — imported once; every function reads XDG_STATE_HOME live per call, exactly
# as the oracle relies on (unittest drives all these in one process with changing XDG dirs).
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from engine import lock as lock_mod, paths, recovery, retention, state as state_mod  # noqa: E402


def _rec(sb: Sandbox) -> Path:
    r = sb.tmp / "recovery"
    r.mkdir(parents=True, exist_ok=True)
    return r


def _mk_artifact(rec: Path, base: str, size: int, *, protected: bool = False, source: str = "",
                 kind: str = "bundle", created_epoch: int | None = None,
                 legacy: bool = False) -> tuple[Path, Path, dict]:
    """Port of the oracle's _mk_artifact: materialize an archive + sidecar manifest in `rec`."""
    archive = rec / f"{base}.tar.gz"
    archive.write_bytes(b"x" * size)
    if legacy:
        doc = {"kind": kind, "archive": str(archive), "size": size, "source": source}
    else:
        doc = retention.build_manifest(kind, source, archive, protected=protected, recovery_root=rec)
        if created_epoch is not None:
            doc["created_at_epoch"] = created_epoch
    mpath = rec / f"{base}.manifest.json"
    mpath.write_text(json.dumps(doc), encoding="utf-8")
    mode = 0o400 if protected else 0o600
    for p in (archive, mpath):
        os.chmod(p, mode)
    return archive, mpath, doc


# =====================================================================================
# (a) ONE unified artifact format (kernel bundle + engine artifact)
# =====================================================================================
@transition(Row(
    id="P3-MANIFEST-UNIFIED", phase="P3", title="Unified awa_recovery_artifact/v1 (kernel + engine share it)",
    precondition="a fresh archive",
    inp="build_manifest + scan of the kernel bundler for the shared schema token",
    expected="declares MANIFEST_KEYS; schema/id/size/sha over real bytes; dev-worktree.sh emits the same schema",
    oracle="test_retention::TestUnifiedManifest"))
def manifest_unified(sb: Sandbox) -> str:
    rec = _rec(sb)
    archive = rec / "a.tar.gz"
    archive.write_bytes(b"hello-world")
    doc = retention.build_manifest("bundle", "/some/src", archive, recovery_root=rec)
    for k in retention.MANIFEST_KEYS:
        check(k in doc, f"unified manifest must declare {k}")
    check_eq(doc["schema"], retention.SCHEMA_ARTIFACT, "schema")
    check(doc["artifact_id"].startswith("bundle-"), "artifact id prefix")
    check_eq(doc["size"], len(b"hello-world"), "size")
    check_eq(doc["sha256"], hashlib.sha256(b"hello-world").hexdigest(), "sha over real bytes")
    shell = (REPO / "kernel" / "bin" / "dev-worktree.sh").read_text(encoding="utf-8")
    check(retention.SCHEMA_ARTIFACT in shell, "kernel bundler emits the same unified schema")
    return f"schema={retention.SCHEMA_ARTIFACT}; keys+sha ok; kernel bundler shares the schema"


# =====================================================================================
# (b) TTL from SOURCE deletion (7-day source clock)
# =====================================================================================
@transition(Row(
    id="P3-TTL-SOURCE-CLOCK", phase="P3", title="TTL ages from source deletion (7-day source clock)",
    precondition="artifacts with live vs deleted sources",
    inp="run_maintenance: live source; source-deleted+TTL; first-absence starts clock; default TTL",
    expected="live source never prunes; expired prunes; first absence preserves then prunes; TTL=7d",
    oracle="test_retention::TestTtlSourceClock"))
def ttl_source_clock(sb: Sandbox) -> str:
    check_eq(retention.TTL_SECONDS, 7 * 24 * 3600, "default TTL is 7 days")
    ttl = 100
    # (1) live source -> never TTL-eligible even if created long ago
    rec1 = _rec(sb)
    src = sb.tmp / "live-src"
    src.mkdir()
    _mk_artifact(rec1, "keepme", 10, source=str(src), created_epoch=int(time.time()) - 10 * ttl)
    with state_mod.State() as st:
        res = retention.run_maintenance(st, recovery_dir=rec1, trigger="manual",
                                        ttl_seconds=ttl, now=time.time())
    check_eq(res["deleted"], [], "live source never TTL-eligible")
    check((rec1 / "keepme.tar.gz").exists(), "live-source artifact preserved")
    # (2) source deleted + past TTL -> pruned
    rec2 = sb.tmp / "recovery2"
    rec2.mkdir(parents=True, exist_ok=True)
    archive, manifest, doc = _mk_artifact(rec2, "old", 10, source="")
    now = time.time()
    with state_mod.State() as st:
        st.set_source_deleted_epoch(doc["artifact_id"], int(now) - (ttl + 10))
        res = retention.run_maintenance(st, recovery_dir=rec2, trigger="manual",
                                        ttl_seconds=ttl, now=now)
    check_eq(len(res["deleted"]), 1, "expired artifact pruned")
    check(not archive.exists() and not manifest.exists(), "expired archive+manifest removed")
    # (3) first absence records the clock (preserve), only a later pass prunes
    rec3 = sb.tmp / "recovery3"
    rec3.mkdir(parents=True, exist_ok=True)
    arch3, _, _ = _mk_artifact(rec3, "fresh-absent", 10, source="")
    t0 = time.time()
    with state_mod.State() as st:
        r1 = retention.run_maintenance(st, recovery_dir=rec3, trigger="manual", ttl_seconds=ttl, now=t0)
        check_eq(r1["deleted"], [], "first observation must not delete")
        r2 = retention.run_maintenance(st, recovery_dir=rec3, trigger="manual",
                                       ttl_seconds=ttl, now=t0 + ttl + 1)
    check_eq(len(r2["deleted"]), 1, "later pass prunes")
    check(not arch3.exists(), "fresh-absent pruned on the later pass")
    return "TTL=7d source-clock: live preserved; expired pruned; first-absence fail-safe then prune"


# =====================================================================================
# (c) protected artifacts NEVER auto-removed
# =====================================================================================
@transition(Row(
    id="P3-PROTECTED-NEVER", phase="P3", title="Protected (whole-worktree/Retain) artifacts never auto-removed",
    precondition="a protected archive + an ordinary sibling both aged past TTL, tiny watermark",
    inp="run_maintenance with TTL + pressure both selecting them",
    expected="protected archive+manifest survive; ordinary pruned; protected_bytes reported honestly",
    oracle="test_retention::TestProtectedNeverRemoved"))
def protected_never(sb: Sandbox) -> str:
    rec = _rec(sb)
    prot_a, prot_m, prot_doc = _mk_artifact(rec, "prot", 500, protected=True, kind="worktree-archive")
    ord_a, ord_m, ord_doc = _mk_artifact(rec, "ord", 500, source="")
    now = time.time()
    with state_mod.State() as st:
        st.set_source_deleted_epoch(prot_doc["artifact_id"], int(now) - 10_000)
        st.set_source_deleted_epoch(ord_doc["artifact_id"], int(now) - 10_000)
        res = retention.run_maintenance(st, recovery_dir=rec, trigger="manual", ttl_seconds=100,
                                        watermark_bytes=100, min_age_seconds=1, now=now)
    check(prot_a.exists() and prot_m.exists(), "protected artifact must never be auto-removed")
    check(not ord_a.exists(), "ordinary sibling pruned")
    check(res["protected_bytes"] >= 500, "protected bytes reported honestly")
    return "protected survives TTL+pressure; ordinary pruned; protected_bytes honest"


# =====================================================================================
# (d) 1 GiB / 24h pressure policy, oldest-first, fail-safe
# =====================================================================================
@transition(Row(
    id="P3-PRESSURE", phase="P3", title="Pressure prunes oldest-first, preserves young, on-disk accounting",
    precondition="three aged ordinary artifacts + a size-lying manifest",
    inp="run_maintenance under a tiny watermark + default-constant + accounting checks",
    expected="oldest-first until under watermark; young preserved; reason=pressure; 1GiB/24h defaults; size=on-disk",
    oracle="test_retention::TestPressurePolicy"))
def pressure(sb: Sandbox) -> str:
    check_eq(retention.PRESSURE_WATERMARK_BYTES, 1024 * 1024 * 1024, "1 GiB watermark")
    check_eq(retention.PRESSURE_MIN_AGE_SECONDS, 24 * 3600, "24h min-age")
    rec = _rec(sb)
    now = int(time.time())
    _, _, a = _mk_artifact(rec, "A-old", 60, source="")
    _, _, b = _mk_artifact(rec, "B-mid", 60, source="")
    _, _, c = _mk_artifact(rec, "C-young", 60, source="")
    with state_mod.State() as st:
        st.set_source_deleted_epoch(a["artifact_id"], now - 100)
        st.set_source_deleted_epoch(b["artifact_id"], now - 50)
        st.set_source_deleted_epoch(c["artifact_id"], now - 5)
        res = retention.run_maintenance(st, recovery_dir=rec, trigger="manual", ttl_seconds=10_000,
                                        watermark_bytes=100, min_age_seconds=10, now=now)
    deleted_ids = {d["artifact_id"] for d in res["deleted"]}
    check(a["artifact_id"] in deleted_ids, "oldest goes first")
    check(b["artifact_id"] in deleted_ids, "prune until under watermark")
    check(c["artifact_id"] not in deleted_ids, "young artifact preserved (fail-safe)")
    check_eq({d["reason"] for d in res["deleted"]}, {retention.REASON_PRESSURE}, "reason=pressure")
    # on-disk accounting, not the manifest claim
    rec2 = sb.tmp / "recovery-liar"
    rec2.mkdir(parents=True, exist_ok=True)
    _, _, doc = _mk_artifact(rec2, "liar", 10, source="")
    doc["size"] = 10 * 1024 ** 3
    (rec2 / "liar.manifest.json").write_text(json.dumps(doc), encoding="utf-8")
    check_eq(retention.scan(rec2).descriptors[0].size, 10, "descriptor size is on-disk truth")
    return "oldest-first under watermark; young preserved; 1GiB/24h defaults; on-disk accounting"


# =====================================================================================
# (e) containment (SHA-256 / symlink escape / path-traversal write-side)
# =====================================================================================
@transition(Row(
    id="P3-CONTAINMENT", phase="P3", title="Containment: symlink/escape refused; journal never escapes",
    precondition="a symlink archive escaping the root + a path-traversal artifact_id",
    inp="_delete_one on a symlink; _safe_target checks; _delete_one with ../.. id",
    expected="refused_containment (outside survives); _safe_target rejects escape/symlink; journal stays inside trash",
    oracle="test_retention::TestContainment"))
def containment(sb: Sandbox) -> str:
    rec = _rec(sb)
    outside = sb.tmp / "outside.bin"
    outside.write_bytes(b"IMPORTANT")
    link = rec / "evil.tar.gz"
    os.symlink(str(outside), str(link))
    desc = retention.ArtifactDescriptor(
        artifact_id="bundle-evil", kind="bundle", protected=False, source="",
        archive=link, manifest=None, size=9, created_at_epoch=int(time.time()))
    out = retention._delete_one(rec, desc, retention.REASON_MANUAL, None)
    check_eq(out["outcome"], "refused_containment", "symlink archive refused")
    check(outside.exists(), "containment must never delete outside the root")
    check(not retention._safe_target(outside, rec), "_safe_target rejects outside")
    inside = rec / "in.tar.gz"
    inside.write_bytes(b"1")
    check(retention._safe_target(inside, rec), "_safe_target accepts inside")
    link2 = rec / "l.tar.gz"
    os.symlink(str(outside), str(link2))
    check(not retention._safe_target(link2, rec), "_safe_target rejects a symlink")
    # write-side containment: a traversal artifact_id must not escape the trash dir
    rec2 = sb.tmp / "recovery-trav"
    rec2.mkdir(parents=True, exist_ok=True)
    archive = rec2 / "safe.tar.gz"
    archive.write_bytes(b"x" * 10)
    desc2 = retention.ArtifactDescriptor(
        artifact_id="../../evil/pwned", kind="bundle", protected=False, source="",
        archive=archive, manifest=None, size=10, created_at_epoch=int(time.time()))
    with state_mod.State() as st:
        out2 = retention._delete_one(rec2, desc2, retention.REASON_MANUAL, st)
    check_eq(out2["outcome"], "deleted", "a contained archive is still deleted")
    check(not (sb.tmp / "evil").exists(), "tampered id must not create paths outside the trash dir")
    return "symlink refused (outside survives); _safe_target strict; traversal id contained"


# =====================================================================================
# (f) ONE crash-resumable, tombstoned deletion transaction
# =====================================================================================
@transition(Row(
    id="P3-CRASH-RESUME", phase="P3", title="Crash-resumable tombstoned deletion (resume after crash)",
    precondition="a prepared deletion journal (simulated crash) + an escaping journal",
    inp="_resume completes the prepared txn; refuses the escaping journal; _delete_one leaves no journal",
    expected="resume unlinks+tombstones+removes journal; escaping journal surfaced (outside survives); clean delete leaves no journal",
    oracle="test_retention::TestCrashResumableDeletion"))
def crash_resume(sb: Sandbox) -> str:
    rec = _rec(sb)
    trash = rec / retention._TRASH_DIRNAME
    trash.mkdir(parents=True, exist_ok=True)
    archive, manifest, doc = _mk_artifact(rec, "crashy", 10, source="")
    journal = trash / f"{doc['artifact_id']}.deletion.json"
    journal.write_text(json.dumps({
        "schema": retention.SCHEMA_DELETION_JOURNAL, "artifact_id": doc["artifact_id"],
        "kind": "bundle", "reason": retention.REASON_TTL, "bytes": 10,
        "archive": str(archive), "manifest": str(manifest), "source": "",
        "phase": "prepared", "created_at_epoch": int(time.time())}), encoding="utf-8")
    with state_mod.State() as st:
        res = retention._resume(rec, st)
        check(doc["artifact_id"] in res["resumed"], "prepared txn resumed")
        check(st.tombstone_exists(doc["artifact_id"]), "tombstone recorded")
    check(not archive.exists() and not manifest.exists(), "archive+manifest unlinked on resume")
    check(not journal.exists(), "completed journal removed")
    # escaping journal: outside target must survive + be surfaced
    rec2 = sb.tmp / "recovery-escape"
    (rec2 / retention._TRASH_DIRNAME).mkdir(parents=True, exist_ok=True)
    outside = sb.tmp / "precious.bin"
    outside.write_bytes(b"KEEP")
    j2 = rec2 / retention._TRASH_DIRNAME / "tampered.deletion.json"
    j2.write_text(json.dumps({
        "schema": retention.SCHEMA_DELETION_JOURNAL, "artifact_id": "bundle-x",
        "reason": "ttl", "archive": str(outside), "manifest": ""}), encoding="utf-8")
    with state_mod.State() as st:
        res2 = retention._resume(rec2, st)
    check(outside.exists(), "resume must never follow an escaping journal")
    check(str(j2) in res2["needs_repair"], "escaping journal surfaced for repair")
    # clean delete leaves no journal
    rec3 = sb.tmp / "recovery-clean"
    rec3.mkdir(parents=True, exist_ok=True)
    _mk_artifact(rec3, "clean", 10, source="")
    desc = retention.scan(rec3).descriptors[0]
    with state_mod.State() as st:
        out = retention._delete_one(rec3, desc, retention.REASON_MANUAL, st)
    check_eq(out["outcome"], "deleted", "clean delete")
    leftovers = list((rec3 / retention._TRASH_DIRNAME).glob("*.deletion.json")) \
        if (rec3 / retention._TRASH_DIRNAME).exists() else []
    check_eq(leftovers, [], "a successful delete leaves no journal")
    return "resume completes+tombstones; escaping journal surfaced; clean delete journal-free"


# =====================================================================================
# (g) reconciliation (row -> pruned, tombstone, clock cleared)
# =====================================================================================
@transition(Row(
    id="P3-RECONCILE", phase="P3", title="Prune reconciles the row, tombstone, and source clock",
    precondition="a recorded recovery row aged past TTL",
    inp="run_maintenance then inspect the row/tombstone/clock",
    expected="row status=pruned; tombstone exists; source-deletion clock cleared",
    oracle="test_retention::TestReconciliation"))
def reconcile(sb: Sandbox) -> str:
    rec = _rec(sb)
    archive, manifest, doc = _mk_artifact(rec, "recon", 10, source="")
    now = time.time()
    with state_mod.State() as st:
        st.record_recovery("bundle", "", str(archive), str(manifest), artifact_id=doc["artifact_id"],
                           sha256=doc["sha256"], bytes=10, protected=False)
        st.set_source_deleted_epoch(doc["artifact_id"], int(now) - 10_000)
        retention.run_maintenance(st, recovery_dir=rec, trigger="manual", ttl_seconds=100, now=now)
        rows = {r["artifact_id"]: r for r in st.recovery_artifacts()}
        check_eq(rows[doc["artifact_id"]]["status"], "pruned", "row marked pruned")
        check(st.tombstone_exists(doc["artifact_id"]), "tombstone exists")
        check(st.get_source_deleted_epoch(doc["artifact_id"]) is None, "source clock cleared")
    return "row=pruned; tombstone present; source clock cleared"


# =====================================================================================
# (h) legacy normalization
# =====================================================================================
@transition(Row(
    id="P3-LEGACY", phase="P3", title="Legacy artifacts normalized with a deterministic id + participate",
    precondition="a pre-unified manifest + a bare .patch",
    inp="scan (deterministic id) + bare-patch classification + legacy TTL prune",
    expected="legacy id stable+prefixed; bare patch participates as ordinary; legacy artifact TTL-prunes",
    oracle="test_retention::TestLegacyNormalization"))
def legacy(sb: Sandbox) -> str:
    rec = _rec(sb)
    _mk_artifact(rec, "legacy1", 10, source="", legacy=True)
    d = retention.scan(rec).descriptors[0]
    check(d.legacy and d.artifact_id.startswith("legacy-"), "legacy normalized with prefix")
    check_eq(retention.scan(rec).descriptors[0].artifact_id, d.artifact_id, "deterministic id")
    # bare patch participates as ordinary
    rec2 = sb.tmp / "recovery-patch"
    rec2.mkdir(parents=True, exist_ok=True)
    (rec2 / "old.patch").write_text("diff --git a b\n", encoding="utf-8")
    pdescs = retention.scan(rec2).descriptors
    check_eq([x.kind for x in pdescs], ["patch"], "bare patch classified")
    check(not pdescs[0].protected, "bare patch is ordinary")
    # legacy artifact TTL-prunes
    rec3 = sb.tmp / "recovery-legttl"
    rec3.mkdir(parents=True, exist_ok=True)
    arch3, _, _ = _mk_artifact(rec3, "legx", 10, source="", legacy=True)
    aid = retention.scan(rec3).descriptors[0].artifact_id
    now = time.time()
    with state_mod.State() as st:
        st.set_source_deleted_epoch(aid, int(now) - 10_000)
        res = retention.run_maintenance(st, recovery_dir=rec3, trigger="manual", ttl_seconds=100, now=now)
    check_eq(len(res["deleted"]), 1, "legacy artifact TTL-prunes")
    check(not arch3.exists(), "legacy archive removed")
    return "legacy id stable+prefixed; bare patch ordinary; legacy TTL-prunes"


# =====================================================================================
# (i) permissions repair (0600 ordinary / 0400 protected / 0700 dir)
# =====================================================================================
@transition(Row(
    id="P3-PERMISSIONS", phase="P3", title="Permissions repair strips group/other, protects read-only",
    precondition="world-readable drift on ordinary + protected archives",
    inp="repair_permissions over a scan",
    expected="ordinary->0600; protected->0400; recovery dir->0700",
    oracle="test_retention::TestPermissionsRepair"))
def permissions(sb: Sandbox) -> str:
    rec = _rec(sb)
    ord_a, _, _ = _mk_artifact(rec, "ord", 10, source="")
    prot_a, _, _ = _mk_artifact(rec, "prot", 10, protected=True, kind="worktree-archive")
    os.chmod(ord_a, 0o644)
    os.chmod(prot_a, 0o644)
    retention.repair_permissions(rec, retention.scan(rec))
    check_eq(stat_mode(ord_a), 0o600, "ordinary -> 0600")
    check_eq(stat_mode(prot_a), 0o400, "protected -> 0400")
    check_eq(stat_mode(rec), 0o700, "recovery dir -> 0700")
    return "ordinary 0600; protected 0400; dir 0700"


# =====================================================================================
# (j) throttle + shared-lock ABI (opportunistic, non-blocking)
# =====================================================================================
@transition(Row(
    id="P3-THROTTLE-LOCK", phase="P3", title="Opportunistic maintenance is throttled + non-blocking under lock",
    precondition="an opportunistic run, then a second; then a held state-root lock",
    inp="run_maintenance(opportunistic) x2 + under a held lock; lockfile perms",
    expected="second run throttled; under lock skips lock_busy (never races); lockfile is private-perms",
    oracle="test_retention::TestThrottleAndSharedLock"))
def throttle_lock(sb: Sandbox) -> str:
    with state_mod.State() as st:
        r1 = retention.run_maintenance(st, recovery_dir=_rec(sb), trigger="opportunistic", now=time.time())
        check(r1["ran"], "first opportunistic run executes")
        r2 = retention.run_maintenance(st, recovery_dir=_rec(sb), trigger="opportunistic", now=time.time())
    check(not r2["ran"], "second opportunistic run is throttled")
    check_eq(r2.get("skipped"), "throttled", "throttled reason")
    with state_mod.State() as st:
        with lock_mod.state_root_lock(blocking=True, timeout=5.0):
            res = retention.run_maintenance(st, recovery_dir=_rec(sb), trigger="opportunistic",
                                            now=time.time(), timeout=0.3)
    check(not res["ran"] and res.get("skipped") == "lock_busy", "skips under lock contention")
    with lock_mod.state_root_lock(blocking=True, timeout=5.0):
        check_eq(stat_mode(lock_mod.state_root_lockfile()), paths.FILE_MODE, "lockfile private perms")
    return "second run throttled; lock-busy skip (no race); lockfile private-perms"


# =====================================================================================
# (k) prune-on-creation under the shared lock
# =====================================================================================
@transition(Row(
    id="P3-PRUNE-ON-CREATION", phase="P3", title="Creating an artifact triggers ONE maintenance pass (self-limiting)",
    precondition="a scratch repo with an ignored file",
    inp="recovery.create_bundle (with state, and state=None)",
    expected="META_LAST_RUN advances (one pass ran under the lock); creation never fails if maintenance raises",
    oracle="test_retention::TestPruneOnCreation"))
def prune_on_creation(sb: Sandbox) -> str:
    repo = sb.make_repo("prune-create")
    Path(repo, ".gitignore").write_text("*.dat\n", encoding="utf-8")
    Path(repo, "x.dat").write_text("d\n", encoding="utf-8")
    rec = _rec(sb)
    with state_mod.State() as st:
        before = st.get_meta(retention.META_LAST_RUN)
        recovery.create_bundle(repo, recovery_dir=rec, state=st)
        after = st.get_meta(retention.META_LAST_RUN)
    check(after is not None and after != before, "prune-on-creation recorded a maintenance run")
    # fail-safe: creation succeeds even on the state=None path
    repo2 = sb.make_repo("prune-create2")
    r = recovery.create_bundle(repo2, recovery_dir=sb.tmp / "recovery-nostate")
    check(Path(r.archive).exists(), "artifact creation succeeds (fail-safe)")
    return "create_bundle ran ONE maintenance pass (META_LAST_RUN advanced); creation fail-safe"


# =====================================================================================
# (l) orphan/partial artifacts surfaced, never trusted/deleted
# =====================================================================================
@transition(Row(
    id="P3-NEEDS-REPAIR", phase="P3", title="Orphan/partial artifacts are surfaced, never trusted or deleted",
    precondition="a manifest whose archive is missing + a bare archive with no manifest",
    inp="scan + a maintenance pass",
    expected="both surfaced in needs_repair; the unmanifested archive is never auto-deleted",
    oracle="test_retention::TestNeedsRepair"))
def needs_repair(sb: Sandbox) -> str:
    rec = _rec(sb)
    ghost = rec / "ghost.tar.gz"
    ghost.write_bytes(b"x")
    doc = retention.build_manifest("bundle", "", ghost, recovery_root=rec)
    ghost.unlink()
    (rec / "ghost.manifest.json").write_text(json.dumps(doc), encoding="utf-8")
    check(any("ghost.tar.gz" in p for p in retention.scan(rec).needs_repair), "missing archive surfaced")
    (rec / "orphan.tar.gz").write_bytes(b"x")
    check(any("orphan.tar.gz" in p for p in retention.scan(rec).needs_repair), "bare archive surfaced")
    with state_mod.State() as st:
        retention.run_maintenance(st, recovery_dir=rec, trigger="manual", now=time.time())
    check((rec / "orphan.tar.gz").exists(), "unmanifested archive never auto-deleted")
    return "missing-archive + bare-archive surfaced; unmanifested archive preserved"


# =====================================================================================
# (m) CRITICAL: NO retention logic on the finish authorization/removal path
# =====================================================================================
@transition(Row(
    id="P3-FINISH-NO-RETENTION", phase="P3", title="The exact-Close finish path carries NO retention logic",
    precondition="none (structural scan of the finish sources)",
    inp="scan kernel/lib/awa_finish.py + consumer/finish_current.py for retention tokens",
    expected="neither references run_maintenance/engine.retention/prune_* (removal is retention-free)",
    oracle="test_retention::TestFinishPathHasNoRetention"))
def finish_no_retention(sb: Sandbox) -> str:
    tokens = ("run_maintenance", "engine.retention", "import retention", "_prune_on_creation",
              "PRESSURE_WATERMARK", "prune_artifacts")
    for rel in ("kernel/lib/awa_finish.py", "consumer/finish_current.py"):
        text = (REPO / rel).read_text(encoding="utf-8")
        for tok in tokens:
            check(tok not in text, f"{rel} must not reference retention token {tok!r}")
    return "kernel + consumer finish paths are retention-free (removal never prunes)"


# =====================================================================================
# (n) dashboard / status / session visibility
# =====================================================================================
@transition(Row(
    id="P3-STATUS-SURFACE", phase="P3", title="Retention status reports policy + storage honestly",
    precondition="one protected + one ordinary artifact",
    inp="retention.status",
    expected="ttl_days=7; watermark=1GiB; counts + protected/ordinary bytes + tombstone_count",
    oracle="test_retention::TestStatusSurface"))
def status_surface(sb: Sandbox) -> str:
    rec = _rec(sb)
    _mk_artifact(rec, "p", 10, protected=True, kind="worktree-archive")
    _mk_artifact(rec, "o", 20, source="")
    with state_mod.State() as st:
        out = retention.status(st, recovery_dir=rec, now=time.time())
    check_eq(out["ttl_days"], 7.0, "ttl_days")
    check_eq(out["watermark_bytes"], retention.PRESSURE_WATERMARK_BYTES, "watermark")
    check_eq(out["artifact_count"], 2, "artifact_count")
    check_eq(out["protected_count"], 1, "protected_count")
    check("tombstone_count" in out, "tombstone_count present")
    return "status: ttl_days=7; watermark=1GiB; counts + bytes + tombstone_count"


@transition(Row(
    id="P3-CLI-RECOVER", phase="P3", title="Production `recover status` + `recover prune --maintenance` JSON",
    precondition="isolated sandbox XDG state",
    inp="python3 -m engine recover status; recover prune --maintenance",
    expected="status: ttl_days=7, watermark=1GiB; prune: ran=true, trigger=manual (dashboard-stable JSON)",
    oracle="test_retention::TestCliSurface"))
def cli_recover(sb: Sandbox) -> str:
    status = json.loads(sb.run_engine("recover", "status").stdout)
    check_eq(status["action"], "status", "status action")
    check_eq(status["ttl_days"], 7.0, "ttl_days")
    check_eq(status["watermark_bytes"], retention.PRESSURE_WATERMARK_BYTES, "watermark")
    prune = json.loads(sb.run_engine("recover", "prune", "--maintenance").stdout)
    check_eq(prune["action"], "prune", "prune action")
    check(prune["ran"], "prune ran")
    check_eq(prune["trigger"], "manual", "prune trigger")
    return "recover status (ttl=7,1GiB) + prune --maintenance (ran,trigger=manual)"


@transition(Row(
    id="P3-DAEMON-RUNONCE", phase="P3", title="Production `daemon run-once` runs a bounded offline maintenance pass",
    precondition="isolated sandbox XDG state",
    inp="python3 -m engine daemon run-once",
    expected="ok=true; action=run-once (quarantine cleanup + opportunistic maintenance, zero network)",
    oracle="engine/cli.py cmd_daemon + engine/daemon.py run_once (delete_remote=False -> offline)"))
def daemon_runonce(sb: Sandbox) -> str:
    out = json.loads(sb.run_engine("daemon", "run-once").stdout)
    check_eq(out.get("action"), "run-once", "action")
    check(out.get("ok"), f"run-once ok ({out})")
    return "daemon run-once: ok=true (bounded offline maintenance pass)"


@transition(Row(
    id="P3-EMITTER-PROBE", phase="P3", title="Dashboard emitter probe is side-effect-free without state",
    precondition="no engine state db",
    inp="dashboard/emitter.py recovery_status",
    expected="recovery.available=false; NO state.db created by the probe",
    oracle="test_retention::TestEmitterProbe"))
def emitter_probe(sb: Sandbox) -> str:
    spec = importlib.util.spec_from_file_location("awa_emitter_probe", REPO / "dashboard" / "emitter.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = mod.recovery_status(timeout=5.0)
    check("recovery" in out, "recovery key present")
    check(not out["recovery"]["available"], "available=false without state")
    check(not (sb.state / "awa" / "state.db").exists(), "probe must not create state db")
    return "emitter recovery.available=false; no state.db created (side-effect-free)"


@transition(Row(
    id="P3-SESSION-HOOK", phase="P3", title="Opportunistic sessionStart maintenance hook is fail-open + quiet",
    precondition="empty sandbox XDG state (no state.db)",
    inp="echo '{}' | awa-recovery-maintenance.sh",
    expected="rc=0; stdout=={}; creates no engine state from a passive session",
    oracle="test_retention::TestSessionHook"))
def session_hook(sb: Sandbox) -> str:
    proc = subprocess.run(["bash", str(HOOK_RECOVERY)], input="{}", text=True,
                          capture_output=True, env={**os.environ}, timeout=30)
    check_eq(proc.returncode, 0, f"hook rc ({proc.stderr})")
    check_eq(proc.stdout.strip(), "{}", "quiet on a nothing-to-do session")
    db = sb.state / "awa" / "state.db"
    for _ in range(20):
        if db.exists():
            break
        time.sleep(0.1)
    check(not db.exists(), "a passive sessionStart hook must not create engine state")
    return "sessionStart hook: rc=0, quiet {}, creates no state (fail-open)"


# =====================================================================================
# (o) uninstall survival (protected Retain artifacts survive a normal uninstall)
# =====================================================================================
@transition(Row(
    id="P3-UNINSTALL-SURVIVAL", phase="P3", title="A normal uninstall preserves protected Retain artifacts",
    precondition="install.sh into a sandbox HOME; a protected-retain dir + an ordinary state file",
    inp="install.sh then install.sh --uninstall (HOME + XDG redirected into the sandbox)",
    expected="protected-retain manifest survives uninstall; the ordinary state file is removed",
    oracle="test_finish_conversation::HookAndDispatcherTest::test_normal_uninstall_preserves_protected_retain"))
def uninstall_survival(sb: Sandbox) -> str:
    home = sb.data / "install-home"
    env = {**os.environ, "HOME": str(home),
           "XDG_DATA_HOME": str(home / ".local" / "share"),
           "XDG_CONFIG_HOME": str(home / ".config"),
           "XDG_STATE_HOME": str(home / ".local" / "state")}
    first = sb.run_raw(["bash", str(INSTALL_SH)], env=env)
    check_eq(first.returncode, 0, f"install rc ({first.stdout}{first.stderr})")
    retained = Path(env["XDG_STATE_HOME"]) / "awa" / "protected-retain" / ("retain-" + "a" * 32)
    retained.mkdir(parents=True)
    (retained / "manifest.json").write_text('{"protected":true}\n', encoding="utf-8")
    ordinary = Path(env["XDG_STATE_HOME"]) / "awa" / "ordinary"
    ordinary.write_text("remove", encoding="utf-8")
    removed = sb.run_raw(["bash", str(INSTALL_SH), "--uninstall"], env=env)
    check_eq(removed.returncode, 0, f"uninstall rc ({removed.stdout}{removed.stderr})")
    check((retained / "manifest.json").exists(), "protected retain survives uninstall")
    check(not ordinary.exists(), "ordinary state removed on uninstall")
    return "protected-retain survives uninstall; ordinary state removed"
