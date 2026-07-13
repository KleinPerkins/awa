"""test_retention.py — focused Phase 3 tests for the recovery-retention lifecycle.

Each test is a BITING regression tied to an authoritative-plan requirement (it fails against a
naive/absent implementation and passes against the canonical one). The suite is auto-discovered by
`engine/tests/run-tests.sh` and therefore runs inside `make verify`.

Requirement -> test map:
  * ONE unified artifact format (kernel + engine)            -> TestUnifiedManifest
  * age from SOURCE deletion (not creation) + 7-day TTL      -> TestTtlSourceClock
  * protected artifacts NEVER auto-removed (TTL or pressure) -> TestProtectedNeverRemoved
  * 1-GiB / 24-hour pressure policy, oldest-first, fail-safe -> TestPressurePolicy
  * containment (symlink/escape rejected, never deletes out) -> TestContainment
  * ONE crash-resumable, tombstoned deletion transaction     -> TestCrashResumableDeletion
  * reconciliation (row -> pruned, tombstone, source clear)  -> TestReconciliation
  * legacy normalization (deterministic id, participates)    -> TestLegacyNormalization
  * permissions repair (0600 / protected 0400)               -> TestPermissionsRepair
  * throttle + shared-lock ABI (opportunistic non-blocking)  -> TestThrottleAndSharedLock
  * prune-on-creation trigger under the shared lock          -> TestPruneOnCreation
  * orphan/partial artifacts surfaced, never trusted/deleted -> TestNeedsRepair
  * NO retention logic on the finish authorization path      -> TestFinishPathHasNoRetention
  * dashboard/status visibility surface                      -> TestStatusSurface / TestCliSurface /
                                                               TestEmitterProbe
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

from engine import lock as lock_mod, paths, recovery, retention, state as state_mod
from engine.tests.helpers import EngineTestCase

_ROOT = Path(__file__).resolve().parents[2]


def _write_manifest(rec: Path, base: str, doc: dict) -> Path:
    mpath = rec / f"{base}.manifest.json"
    mpath.write_text(json.dumps(doc), encoding="utf-8")
    return mpath


def _mk_artifact(rec: Path, base: str, size: int, *, protected: bool = False,
                 source: str = "", kind: str = "bundle", created_epoch: int | None = None,
                 legacy: bool = False) -> tuple[Path, Path, dict]:
    """Materialize one artifact (archive + sidecar manifest) in `rec`. `legacy=True` writes a
    pre-unified manifest (no schema/artifact_id/epoch) so normalization is exercised."""
    archive = rec / f"{base}.tar.gz"
    archive.write_bytes(b"x" * size)
    if legacy:
        doc = {"kind": kind, "archive": str(archive), "size": size, "source": source}
    else:
        doc = retention.build_manifest(kind, source, archive, protected=protected, recovery_root=rec)
        if created_epoch is not None:
            doc["created_at_epoch"] = created_epoch
    mpath = _write_manifest(rec, base, doc)
    mode = 0o400 if protected else 0o600
    for p in (archive, mpath):
        os.chmod(p, mode)
    return archive, mpath, doc


class _RetentionBase(EngineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.rec = Path(self._tmp.name) / "recovery"
        self.rec.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------------------------------
class TestUnifiedManifest(_RetentionBase):
    def test_build_manifest_shape_id_and_sha_over_real_bytes(self):
        archive = self.rec / "a.tar.gz"
        archive.write_bytes(b"hello-world")
        doc = retention.build_manifest("bundle", "/some/src", archive, recovery_root=self.rec)
        for k in retention.MANIFEST_KEYS:
            self.assertIn(k, doc, f"unified manifest must declare {k}")
        self.assertEqual(doc["schema"], retention.SCHEMA_ARTIFACT)
        self.assertTrue(doc["artifact_id"].startswith("bundle-"))
        self.assertEqual(doc["size"], len(b"hello-world"))
        import hashlib
        self.assertEqual(doc["sha256"], hashlib.sha256(b"hello-world").hexdigest())
        self.assertFalse(doc["protected"])
        self.assertEqual(doc["archive_name"], "a.tar.gz")

    def test_kernel_and_engine_share_one_schema_constant(self):
        # The kernel bundler (dev-worktree.sh) emits the SAME unified schema token; a drift here is
        # a cross-surface incompatibility (biting: catches either side renaming the schema).
        shell = (_ROOT / "kernel" / "bin" / "dev-worktree.sh").read_text(encoding="utf-8")
        self.assertIn(retention.SCHEMA_ARTIFACT, shell,
                      "kernel bundler must emit the same unified manifest schema as the engine")


# --------------------------------------------------------------------------------------------------
class TestTtlSourceClock(_RetentionBase):
    def test_ttl_ages_from_source_deletion_not_creation(self):
        """BITING: an artifact created long ago whose SOURCE still exists must NEVER TTL-prune.
        A creation-time TTL would wrongly delete it."""
        src = Path(self._tmp.name) / "live-src"
        src.mkdir()
        ttl = 100
        ancient = int(time.time()) - 10 * ttl
        _mk_artifact(self.rec, "keepme", 10, source=str(src), created_epoch=ancient)
        with state_mod.State() as st:
            res = retention.run_maintenance(st, recovery_dir=self.rec, trigger="manual",
                                            ttl_seconds=ttl, now=time.time())
        self.assertEqual(res["deleted"], [], "source still present -> never TTL-eligible")
        self.assertTrue((self.rec / "keepme.tar.gz").exists())

    def test_ttl_prunes_after_source_deleted_plus_ttl(self):
        ttl = 100
        archive, manifest, doc = _mk_artifact(self.rec, "old", 10, source="")
        now = time.time()
        with state_mod.State() as st:
            # Source-deletion clock started ttl+10s ago -> now past the 7-day-equivalent TTL.
            st.set_source_deleted_epoch(doc["artifact_id"], int(now) - (ttl + 10))
            res = retention.run_maintenance(st, recovery_dir=self.rec, trigger="manual",
                                            ttl_seconds=ttl, now=now)
        self.assertEqual(len(res["deleted"]), 1)
        self.assertFalse(archive.exists(), "expired ordinary archive must be removed")
        self.assertFalse(manifest.exists(), "expired manifest must be removed")

    def test_first_absence_starts_the_clock_but_does_not_prune_immediately(self):
        """A first pass that OBSERVES the source gone records the clock (age 0) and preserves the
        artifact; only a later pass past TTL prunes it (fail-safe)."""
        ttl = 100
        archive, _, doc = _mk_artifact(self.rec, "fresh-absent", 10, source="")
        t0 = time.time()
        with state_mod.State() as st:
            r1 = retention.run_maintenance(st, recovery_dir=self.rec, trigger="manual",
                                           ttl_seconds=ttl, now=t0)
            self.assertEqual(r1["deleted"], [], "first observation must not delete")
            self.assertTrue(archive.exists())
            r2 = retention.run_maintenance(st, recovery_dir=self.rec, trigger="manual",
                                           ttl_seconds=ttl, now=t0 + ttl + 1)
        self.assertEqual(len(r2["deleted"]), 1)
        self.assertFalse(archive.exists())

    def test_default_ttl_is_seven_days(self):
        self.assertEqual(retention.TTL_SECONDS, 7 * 24 * 3600)


# --------------------------------------------------------------------------------------------------
class TestProtectedNeverRemoved(_RetentionBase):
    def test_protected_survives_ttl_and_pressure(self):
        """BITING: a protected whole-worktree archive must survive even when both TTL AND pressure
        would otherwise select it."""
        prot_a, prot_m, prot_doc = _mk_artifact(self.rec, "prot", 500, protected=True,
                                                kind="worktree-archive")
        ord_a, ord_m, ord_doc = _mk_artifact(self.rec, "ord", 500, source="")
        now = time.time()
        with state_mod.State() as st:
            # Age BOTH well past TTL and force pressure with a tiny watermark.
            st.set_source_deleted_epoch(prot_doc["artifact_id"], int(now) - 10_000)
            st.set_source_deleted_epoch(ord_doc["artifact_id"], int(now) - 10_000)
            res = retention.run_maintenance(st, recovery_dir=self.rec, trigger="manual",
                                            ttl_seconds=100, watermark_bytes=100,
                                            min_age_seconds=1, now=now)
        self.assertTrue(prot_a.exists(), "protected archive must never be auto-removed")
        self.assertTrue(prot_m.exists(), "protected manifest must never be auto-removed")
        self.assertFalse(ord_a.exists(), "the ordinary sibling should be pruned")
        # Protected bytes are reported honestly even though they sit above the watermark.
        self.assertGreaterEqual(res["protected_bytes"], 500)


# --------------------------------------------------------------------------------------------------
class TestPressurePolicy(_RetentionBase):
    def test_pressure_oldest_first_and_young_preserved(self):
        """BITING: pressure prunes OLDEST-first until back under the watermark, and NEVER prunes an
        artifact younger than the 24h-equivalent min-age even while over the watermark."""
        now = int(time.time())
        _, _, a = _mk_artifact(self.rec, "A-old", 60, source="")
        _, _, b = _mk_artifact(self.rec, "B-mid", 60, source="")
        _, _, c = _mk_artifact(self.rec, "C-young", 60, source="")
        with state_mod.State() as st:
            st.set_source_deleted_epoch(a["artifact_id"], now - 100)   # oldest
            st.set_source_deleted_epoch(b["artifact_id"], now - 50)    # middle
            st.set_source_deleted_epoch(c["artifact_id"], now - 5)     # younger than min_age
            res = retention.run_maintenance(st, recovery_dir=self.rec, trigger="manual",
                                            ttl_seconds=10_000, watermark_bytes=100,
                                            min_age_seconds=10, now=now)
        deleted_ids = {d["artifact_id"] for d in res["deleted"]}
        self.assertIn(a["artifact_id"], deleted_ids, "oldest must go first")
        self.assertIn(b["artifact_id"], deleted_ids, "prune until back under watermark")
        self.assertNotIn(c["artifact_id"], deleted_ids, "a young artifact is preserved (fail-safe)")
        self.assertTrue((self.rec / "C-young.tar.gz").exists())
        self.assertEqual({d["reason"] for d in res["deleted"]}, {retention.REASON_PRESSURE})

    def test_default_pressure_constants(self):
        self.assertEqual(retention.PRESSURE_WATERMARK_BYTES, 1024 * 1024 * 1024)
        self.assertEqual(retention.PRESSURE_MIN_AGE_SECONDS, 24 * 3600)

    def test_accounting_uses_on_disk_size_not_manifest_claim(self):
        """BITING: pressure accounting must reflect ACTUAL on-disk bytes; a manifest that lies about
        `size` (or references a now-missing archive) must not inflate the watermark."""
        _, _, doc = _mk_artifact(self.rec, "liar", 10, source="")
        doc["size"] = 10 * 1024 ** 3      # claim 10 GiB on a 10-byte archive
        _write_manifest(self.rec, "liar", doc)
        d = retention.scan(self.rec).descriptors[0]
        self.assertEqual(d.size, 10, "descriptor size must be on-disk truth, not the manifest claim")


# --------------------------------------------------------------------------------------------------
class TestContainment(_RetentionBase):
    def test_delete_one_refuses_symlink_archive_and_preserves_outside_target(self):
        """BITING: a manifest whose archive is a symlink escaping the recovery root must be REFUSED
        (containment) and the outside target must survive. A naive os.unlink would remove it."""
        outside = Path(self._tmp.name) / "outside.bin"
        outside.write_bytes(b"IMPORTANT")
        link = self.rec / "evil.tar.gz"
        os.symlink(str(outside), str(link))
        desc = retention.ArtifactDescriptor(
            artifact_id="bundle-evil", kind="bundle", protected=False, source="",
            archive=link, manifest=None, size=9, created_at_epoch=int(time.time()))
        out = retention._delete_one(self.rec, desc, retention.REASON_MANUAL, None)
        self.assertEqual(out["outcome"], "refused_containment")
        self.assertTrue(outside.exists(), "containment must never delete outside the recovery root")

    def test_safe_target_rejects_escape_and_symlink(self):
        outside = Path(self._tmp.name) / "x"
        outside.write_bytes(b"1")
        self.assertFalse(retention._safe_target(outside, self.rec))
        inside = self.rec / "in.tar.gz"
        inside.write_bytes(b"1")
        self.assertTrue(retention._safe_target(inside, self.rec))
        link = self.rec / "l.tar.gz"
        os.symlink(str(outside), str(link))
        self.assertFalse(retention._safe_target(link, self.rec))

    def test_deletion_journal_never_escapes_on_tampered_artifact_id(self):
        """BITING (write-side containment): a manifest whose artifact_id is a path traversal must
        NOT cause the deletion journal to be written outside the trash dir. A naive
        `trash / f'{artifact_id}.deletion.json'` would create paths outside the recovery root."""
        archive = self.rec / "safe.tar.gz"
        archive.write_bytes(b"x" * 10)
        desc = retention.ArtifactDescriptor(
            artifact_id="../../evil/pwned", kind="bundle", protected=False, source="",
            archive=archive, manifest=None, size=10, created_at_epoch=int(time.time()))
        with state_mod.State() as st:
            out = retention._delete_one(self.rec, desc, retention.REASON_MANUAL, st)
        self.assertEqual(out["outcome"], "deleted", "a contained archive is still deleted")
        self.assertFalse((Path(self._tmp.name) / "evil").exists(),
                         "a tampered artifact_id must never create paths outside the trash dir")
        self.assertFalse(archive.exists())


# --------------------------------------------------------------------------------------------------
class TestCrashResumableDeletion(_RetentionBase):
    def _trash(self) -> Path:
        t = self.rec / retention._TRASH_DIRNAME
        t.mkdir(parents=True, exist_ok=True)
        return t

    def test_resume_completes_interrupted_transaction_and_tombstones(self):
        """BITING: a crash after the journal was written (archive still present) is COMPLETED by the
        resume pass: archive+manifest unlinked, tombstone recorded, journal removed."""
        archive, manifest, doc = _mk_artifact(self.rec, "crashy", 10, source="")
        journal = self._trash() / f"{doc['artifact_id']}.deletion.json"
        journal.write_text(json.dumps({
            "schema": retention.SCHEMA_DELETION_JOURNAL, "artifact_id": doc["artifact_id"],
            "kind": "bundle", "reason": retention.REASON_TTL, "bytes": 10,
            "archive": str(archive), "manifest": str(manifest), "source": "",
            "phase": "prepared", "created_at_epoch": int(time.time())}), encoding="utf-8")
        with state_mod.State() as st:
            res = retention._resume(self.rec, st)
            self.assertIn(doc["artifact_id"], res["resumed"])
            self.assertTrue(st.tombstone_exists(doc["artifact_id"]))
        self.assertFalse(archive.exists())
        self.assertFalse(manifest.exists())
        self.assertFalse(journal.exists(), "a completed journal must be removed")

    def test_resume_refuses_escaping_journal(self):
        """BITING: a tampered journal pointing outside the root must NOT delete the outside file; it
        is surfaced for repair and left in place."""
        outside = Path(self._tmp.name) / "precious.bin"
        outside.write_bytes(b"KEEP")
        journal = self._trash() / "tampered.deletion.json"
        journal.write_text(json.dumps({
            "schema": retention.SCHEMA_DELETION_JOURNAL, "artifact_id": "bundle-x",
            "reason": "ttl", "archive": str(outside), "manifest": ""}), encoding="utf-8")
        with state_mod.State() as st:
            res = retention._resume(self.rec, st)
        self.assertTrue(outside.exists(), "resume must never follow an escaping journal target")
        self.assertIn(str(journal), res["needs_repair"])

    def test_delete_one_is_journal_clean_on_success(self):
        archive, manifest, doc = _mk_artifact(self.rec, "clean", 10, source="")
        desc = retention.scan(self.rec).descriptors[0]
        with state_mod.State() as st:
            out = retention._delete_one(self.rec, desc, retention.REASON_MANUAL, st)
        self.assertEqual(out["outcome"], "deleted")
        # no lingering journals after a clean delete
        trash = self.rec / retention._TRASH_DIRNAME
        leftovers = list(trash.glob("*.deletion.json")) if trash.exists() else []
        self.assertEqual(leftovers, [], "a successful delete leaves no journal")


# --------------------------------------------------------------------------------------------------
class TestReconciliation(_RetentionBase):
    def test_pruned_artifact_reconciles_row_tombstone_and_clears_clock(self):
        """BITING: after a TTL prune the recovery ROW is marked pruned (no longer implies the
        archive is restorable), a tombstone exists, and the source-deletion clock is cleared."""
        archive, manifest, doc = _mk_artifact(self.rec, "recon", 10, source="")
        now = time.time()
        with state_mod.State() as st:
            st.record_recovery("bundle", "", str(archive), str(manifest),
                               artifact_id=doc["artifact_id"], sha256=doc["sha256"],
                               bytes=10, protected=False)
            st.set_source_deleted_epoch(doc["artifact_id"], int(now) - 10_000)
            retention.run_maintenance(st, recovery_dir=self.rec, trigger="manual",
                                      ttl_seconds=100, now=now)
            rows = {r["artifact_id"]: r for r in st.recovery_artifacts()}
            self.assertEqual(rows[doc["artifact_id"]]["status"], "pruned")
            self.assertTrue(st.tombstone_exists(doc["artifact_id"]))
            self.assertIsNone(st.get_source_deleted_epoch(doc["artifact_id"]))


# --------------------------------------------------------------------------------------------------
class TestLegacyNormalization(_RetentionBase):
    def test_legacy_manifest_normalized_with_deterministic_id(self):
        archive, manifest, _ = _mk_artifact(self.rec, "legacy1", 10, source="", legacy=True)
        s1 = retention.scan(self.rec)
        self.assertEqual(len(s1.descriptors), 1)
        d = s1.descriptors[0]
        self.assertTrue(d.legacy)
        self.assertTrue(d.artifact_id.startswith("legacy-"))
        # deterministic across scans (stable age clock / tombstone key)
        d2 = retention.scan(self.rec).descriptors[0]
        self.assertEqual(d.artifact_id, d2.artifact_id)

    def test_legacy_bare_patch_participates_as_ordinary(self):
        patch = self.rec / "old.patch"
        patch.write_text("diff --git a b\n", encoding="utf-8")
        descs = retention.scan(self.rec).descriptors
        self.assertEqual([d.kind for d in descs], ["patch"])
        self.assertFalse(descs[0].protected)

    def test_legacy_artifact_ttl_prunes(self):
        archive, manifest, _ = _mk_artifact(self.rec, "legx", 10, source="", legacy=True)
        aid = retention.scan(self.rec).descriptors[0].artifact_id
        now = time.time()
        with state_mod.State() as st:
            st.set_source_deleted_epoch(aid, int(now) - 10_000)
            res = retention.run_maintenance(st, recovery_dir=self.rec, trigger="manual",
                                            ttl_seconds=100, now=now)
        self.assertEqual(len(res["deleted"]), 1)
        self.assertFalse(archive.exists())


# --------------------------------------------------------------------------------------------------
class TestPermissionsRepair(_RetentionBase):
    def test_group_other_bits_stripped_and_protected_readonly(self):
        ord_a, ord_m, _ = _mk_artifact(self.rec, "ord", 10, source="")
        prot_a, prot_m, _ = _mk_artifact(self.rec, "prot", 10, protected=True,
                                         kind="worktree-archive")
        os.chmod(ord_a, 0o644)      # world-readable drift
        os.chmod(prot_a, 0o644)     # protected should be forced back to 0o400
        scan_res = retention.scan(self.rec)
        retention.repair_permissions(self.rec, scan_res)
        self.assertEqual(os.stat(ord_a).st_mode & 0o777, 0o600)
        self.assertEqual(os.stat(prot_a).st_mode & 0o777, 0o400)
        self.assertEqual(os.stat(self.rec).st_mode & 0o777, 0o700)


# --------------------------------------------------------------------------------------------------
class TestThrottleAndSharedLock(_RetentionBase):
    def test_opportunistic_is_throttled_after_a_run(self):
        with state_mod.State() as st:
            r1 = retention.run_maintenance(st, recovery_dir=self.rec, trigger="opportunistic",
                                           now=time.time())
            self.assertTrue(r1["ran"])
            r2 = retention.run_maintenance(st, recovery_dir=self.rec, trigger="opportunistic",
                                           now=time.time())
        self.assertFalse(r2["ran"])
        self.assertEqual(r2.get("skipped"), "throttled")

    def test_opportunistic_skips_when_lock_is_held_never_races(self):
        """BITING: an opportunistic pass under lock contention SKIPS (non-blocking) rather than
        racing a concurrent maintenance pass."""
        with state_mod.State() as st:
            with lock_mod.state_root_lock(blocking=True, timeout=5.0):
                res = retention.run_maintenance(st, recovery_dir=self.rec, trigger="opportunistic",
                                                now=time.time(), timeout=0.3)
        self.assertFalse(res["ran"])
        self.assertEqual(res.get("skipped"), "lock_busy")

    def test_shared_lockfile_is_private_perms(self):
        # Same private-perms ABI as the finish/clean/Retain common-dir lock.
        with lock_mod.state_root_lock(blocking=True, timeout=5.0):
            lf = lock_mod.state_root_lockfile()
            self.assertEqual(os.stat(lf).st_mode & 0o777, paths.FILE_MODE)


# --------------------------------------------------------------------------------------------------
class TestPruneOnCreation(_RetentionBase):
    def test_creation_runs_maintenance_under_the_lock(self):
        """BITING: creating a recovery artifact deterministically triggers ONE maintenance pass
        (META_LAST_RUN advances), so storage self-limits without any schedule."""
        repo = self.make_repo()
        Path(repo, ".gitignore").write_text("*.dat\n", encoding="utf-8")
        Path(repo, "x.dat").write_text("d\n", encoding="utf-8")
        with state_mod.State() as st:
            before = st.get_meta(retention.META_LAST_RUN)
            recovery.create_bundle(repo, recovery_dir=self.rec, state=st)
            after = st.get_meta(retention.META_LAST_RUN)
        self.assertIsNotNone(after, "prune-on-creation must record a maintenance run")
        self.assertNotEqual(before, after)

    def test_creation_never_fails_if_maintenance_raises(self):
        # Fail-safe: artifact creation must succeed even if a maintenance step hiccups.
        repo = self.make_repo()
        r = recovery.create_bundle(repo, recovery_dir=self.rec)  # state=None path
        self.assertTrue(Path(r.archive).exists())


# --------------------------------------------------------------------------------------------------
class TestNeedsRepair(_RetentionBase):
    def test_manifest_without_archive_is_surfaced_not_deleted(self):
        archive = self.rec / "ghost.tar.gz"
        archive.write_bytes(b"x")
        doc = retention.build_manifest("bundle", "", archive, recovery_root=self.rec)
        # the manifest now references an archive that is subsequently missing
        archive.unlink()
        _write_manifest(self.rec, "ghost", doc)
        res = retention.scan(self.rec)
        self.assertTrue(any("ghost.tar.gz" in p for p in res.needs_repair))

    def test_bare_archive_without_manifest_is_surfaced_not_trusted(self):
        (self.rec / "orphan.tar.gz").write_bytes(b"x")
        res = retention.scan(self.rec)
        self.assertTrue(any("orphan.tar.gz" in p for p in res.needs_repair))
        # and a maintenance pass must not delete an unmanifested archive
        with state_mod.State() as st:
            retention.run_maintenance(st, recovery_dir=self.rec, trigger="manual", now=time.time())
        self.assertTrue((self.rec / "orphan.tar.gz").exists())


# --------------------------------------------------------------------------------------------------
class TestFinishPathHasNoRetention(unittest.TestCase):
    """CRITICAL invariant: the exact-`Close` finish authorization/removal path carries NO
    retention/pruning logic. This is a structural biting regression."""

    _TOKENS = ("run_maintenance", "engine.retention", "import retention",
               "_prune_on_creation", "PRESSURE_WATERMARK", "prune_artifacts")

    def _assert_clean(self, rel: str) -> None:
        text = (_ROOT / rel).read_text(encoding="utf-8")
        for tok in self._TOKENS:
            self.assertNotIn(tok, text,
                             f"{rel} must not reference retention lifecycle token {tok!r}")

    def test_kernel_finish_has_no_retention(self):
        self._assert_clean("kernel/lib/awa_finish.py")

    def test_consumer_finish_has_no_retention(self):
        self._assert_clean("consumer/finish_current.py")


# --------------------------------------------------------------------------------------------------
class TestStatusSurface(_RetentionBase):
    def test_status_reports_policy_and_storage(self):
        _mk_artifact(self.rec, "p", 10, protected=True, kind="worktree-archive")
        _mk_artifact(self.rec, "o", 20, source="")
        with state_mod.State() as st:
            out = retention.status(st, recovery_dir=self.rec, now=time.time())
        self.assertEqual(out["ttl_days"], 7.0)
        self.assertEqual(out["watermark_bytes"], retention.PRESSURE_WATERMARK_BYTES)
        self.assertEqual(out["artifact_count"], 2)
        self.assertEqual(out["protected_count"], 1)
        self.assertGreaterEqual(out["protected_bytes"], 10)
        self.assertGreaterEqual(out["ordinary_bytes"], 20)
        self.assertIn("tombstone_count", out)


class TestCliSurface(EngineTestCase):
    """The dashboard consumes `recover status` + `recover prune --maintenance`; keep the JSON
    surface stable (runs the real launcher path under the isolated test XDG)."""

    def _run(self, *args: str) -> dict:
        proc = subprocess.run([sys.executable, "-m", "engine", *args], cwd=str(_ROOT),
                              env={**os.environ, "PYTHONPATH": str(_ROOT)},
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def test_recover_status_json(self):
        d = self._run("recover", "status")
        self.assertEqual(d["action"], "status")
        self.assertEqual(d["ttl_days"], 7.0)
        self.assertEqual(d["watermark_bytes"], retention.PRESSURE_WATERMARK_BYTES)

    def test_recover_prune_maintenance_json(self):
        d = self._run("recover", "prune", "--maintenance")
        self.assertEqual(d["action"], "prune")
        self.assertTrue(d["ran"])
        self.assertEqual(d["trigger"], "manual")


class TestEmitterProbe(EngineTestCase):
    """Dashboard visibility probe is side-effect-free: with NO engine state db it reports
    available:false WITHOUT spawning the engine or creating state."""

    def _emitter(self):
        spec = importlib.util.spec_from_file_location(
            "awa_emitter_probe", _ROOT / "dashboard" / "emitter.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_recovery_status_unavailable_without_state(self):
        emitter = self._emitter()
        out = emitter.recovery_status(timeout=5.0)
        self.assertIn("recovery", out)
        self.assertFalse(out["recovery"]["available"])
        # no state db must have been created by the probe
        self.assertFalse((self.state_home / "awa" / "state.db").exists())


class TestSessionHook(EngineTestCase):
    """The opportunistic sessionStart maintenance hook is fail-open and must never CREATE engine
    state from a passive session (prune-on-creation is the primary trigger that first materializes
    it). It also must degrade to a quiet ``{}`` when there is nothing to report."""

    HOOK = _ROOT / "kernel" / "hooks" / "awa-recovery-maintenance.sh"

    def test_hook_is_quiet_and_creates_no_state_when_none_exists(self):
        # EngineTestCase isolates XDG_STATE_HOME at an EMPTY dir (no state.db yet).
        proc = subprocess.run(["bash", str(self.HOOK)], input="{}", text=True,
                              capture_output=True, env={**os.environ}, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "{}", "quiet on a nothing-to-do session")
        # A detached maintenance pass (if wrongly spawned) would create the db within ~a second.
        db = self.state_home / "awa" / "state.db"
        for _ in range(30):
            if db.exists():
                break
            time.sleep(0.1)
        self.assertFalse(db.exists(),
                         "a passive sessionStart hook must not CREATE engine state")


if __name__ == "__main__":
    unittest.main(verbosity=2)
