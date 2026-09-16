"""M2.3: digest-bound recovery quarantine and explicit legacy migration."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from engine import integrity, paths, recovery, retention, state as state_mod
from engine.tests.helpers import EngineTestCase


_ROOT = Path(__file__).resolve().parents[2]


class QuarantineBase(EngineTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.rec = paths.recovery_dir()
        self.rec.mkdir(parents=True, mode=0o700)
        self.archive = self.rec / "legacy.tar.gz"
        self.archive.write_bytes(b"legacy recovery bytes")
        self.archive.chmod(0o644)

    def preview(self, path: Path | None = None) -> dict:
        return recovery.preview_quarantine(
            str(path or self.archive), recovery_dir=self.rec
        )

    def apply(self, preview: dict | None = None, **kwargs) -> dict:
        preview = preview or self.preview()
        return recovery.apply_quarantine(
            str(self.archive),
            preview["token"],
            recovery_dir=self.rec,
            **kwargs,
        )

    def add_manifest(self, *, protected: bool = False) -> Path:
        name = self.archive.name
        self.assertTrue(name.endswith(".tar.gz"))
        manifest = self.archive.with_name(
            name[: -len(".tar.gz")] + ".manifest.json"
        )
        document = retention.build_manifest(
            "bundle",
            "/fixture/source",
            self.archive,
            protected=protected,
            recovery_root=self.rec,
        )
        manifest.write_text(json.dumps(document) + "\n", encoding="utf-8")
        manifest.chmod(0o400 if protected else 0o600)
        return manifest


class TestPreviewAndEligibility(QuarantineBase):
    def test_preview_is_deterministic_and_read_only(self):
        before = {
            p.relative_to(self.rec).as_posix(): (
                p.lstat().st_mode,
                p.lstat().st_size,
                p.lstat().st_mtime_ns,
                hashlib.sha256(p.read_bytes()).hexdigest(),
            )
            for p in self.rec.rglob("*")
            if p.is_file() and not p.is_symlink()
        }
        first = self.preview()
        second = self.preview()
        self.assertEqual(first, second)
        self.assertEqual(first["outcome"], "previewed")
        self.assertFalse(first["mutated"])
        self.assertFalse(first["applied"])
        self.assertEqual(
            before,
            {
                p.relative_to(self.rec).as_posix(): (
                    p.lstat().st_mode,
                    p.lstat().st_size,
                    p.lstat().st_mtime_ns,
                    hashlib.sha256(p.read_bytes()).hexdigest(),
                )
                for p in self.rec.rglob("*")
                if p.is_file() and not p.is_symlink()
            },
        )
        self.assertFalse((self.rec / "quarantine").exists())

    def test_symlink_escape_and_nonregular_are_rejected(self):
        outside = Path(self._tmp.name) / "outside.tar.gz"
        outside.write_bytes(b"outside")
        link = self.rec / "link.tar.gz"
        link.symlink_to(outside)
        directory = self.rec / "directory.tar.gz"
        directory.mkdir()
        for candidate in (link, outside, directory):
            with self.subTest(candidate=candidate):
                with self.assertRaises(recovery.QuarantineRefused):
                    self.preview(candidate)
        self.assertEqual(outside.read_bytes(), b"outside")

    def test_digest_binds_path_hash_size_mtime_and_physical_identity(self):
        original = self.preview()
        original_stat = self.archive.stat()
        mutations = ("hash", "size", "mtime", "inode")
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.archive.write_bytes(b"legacy recovery bytes")
                os.utime(
                    self.archive,
                    ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
                )
                if mutation == "hash":
                    self.archive.write_bytes(b"LEGACY recovery bytes")
                    os.utime(
                        self.archive,
                        ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
                    )
                elif mutation == "size":
                    self.archive.write_bytes(b"different size")
                elif mutation == "mtime":
                    os.utime(
                        self.archive,
                        ns=(
                            original_stat.st_atime_ns,
                            original_stat.st_mtime_ns + 1_000_000_000,
                        ),
                    )
                elif mutation == "inode":
                    replacement = self.rec / "replacement"
                    replacement.write_bytes(b"legacy recovery bytes")
                    os.utime(
                        replacement,
                        ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
                    )
                    os.replace(replacement, self.archive)
                with self.assertRaises(recovery.QuarantineRefused):
                    self.apply(original)

    def test_destination_collision_never_overwrites(self):
        preview = self.preview()
        destination = Path(preview["destination"])
        destination.parent.mkdir(parents=True, mode=0o700)
        destination.write_bytes(b"collision")
        with self.assertRaises(recovery.QuarantineRefused):
            self.apply(preview)
        self.assertEqual(destination.read_bytes(), b"collision")
        self.assertTrue(self.archive.exists())

    def test_token_is_bound_to_the_canonical_source_path(self):
        preview = self.preview()
        renamed = self.rec / "renamed.tar.gz"
        self.archive.rename(renamed)
        with self.assertRaises(recovery.QuarantineRefused):
            recovery.apply_quarantine(
                str(renamed), preview["token"], recovery_dir=self.rec
            )
        self.assertTrue(renamed.exists())

    def test_existing_quarantine_artifact_cannot_be_quarantined_again(self):
        applied = self.apply()
        with self.assertRaises(recovery.QuarantineRefused):
            self.preview(Path(applied["quarantined_path"]))


class TestApplyResumeAndReverse(QuarantineBase):
    def test_legacy_trash_migration_is_byte_identical_and_private(self):
        trash = self.rec / ".trash"
        trash.mkdir(mode=0o700)
        self.archive = trash / "legacy-20260714075000.tar.gz"
        payload = b"fixture only: never the live archive"
        self.archive.write_bytes(payload)
        preview = self.preview()
        result = self.apply(preview)
        destination = Path(result["quarantined_path"])
        self.assertEqual(result["outcome"], "quarantined")
        self.assertTrue(result["mutated"])
        self.assertTrue(result["applied"])
        self.assertFalse(self.archive.exists())
        self.assertEqual(destination.read_bytes(), payload)
        self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
        self.assertEqual(destination.parent.stat().st_mode & 0o777, 0o700)
        metadata = Path(result["metadata_path"])
        self.assertEqual(metadata.stat().st_mode & 0o777, 0o600)
        for directory in (
            destination.parents[1],
            destination.parent,
            metadata.parent,
            metadata.parents[0].parent / "journals",
            metadata.parents[0].parent / "reversals",
        ):
            self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
        doc = json.loads(metadata.read_text(encoding="utf-8"))
        self.assertEqual(doc["state"], "committed")
        self.assertNotIn("token", json.dumps(doc).lower())
        self.assertNotIn(payload.decode(), json.dumps(doc))
        self.assertEqual(doc["fingerprint"]["sha256"], hashlib.sha256(payload).hexdigest())

    def test_replay_refuses_a_reappeared_original_path(self):
        preview = self.preview()
        self.apply(preview)
        self.archive.write_bytes(b"new unrelated bytes")
        with self.assertRaises(recovery.QuarantineRefused):
            self.apply(preview)

    def test_every_crash_cut_resumes_idempotently(self):
        for point in recovery.QUARANTINE_CRASH_POINTS:
            with self.subTest(point=point):
                with self.subTest(cleanup="isolated"):
                    other = self.rec / f"{point}.tar.gz"
                    other.write_bytes(point.encode())
                    preview = self.preview(other)

                    def fault(observed: str) -> None:
                        if observed == point:
                            raise recovery.QuarantineInjectedCrash(point)

                    with self.assertRaises(recovery.QuarantineInjectedCrash):
                        recovery.apply_quarantine(
                            str(other),
                            preview["token"],
                            recovery_dir=self.rec,
                            fault=fault,
                        )
                    resumed = recovery.apply_quarantine(
                        str(other),
                        preview["token"],
                        recovery_dir=self.rec,
                    )
                    self.assertIn(
                        resumed["outcome"],
                        {"quarantined", "already_quarantined"},
                    )
                    replay = recovery.apply_quarantine(
                        str(other),
                        preview["token"],
                        recovery_dir=self.rec,
                    )
                    self.assertEqual(replay["outcome"], "already_quarantined")
                    self.assertTrue(replay["applied"])
                    self.assertEqual(
                        Path(replay["quarantined_path"]).read_bytes(),
                        point.encode(),
                    )

    def test_post_move_bookkeeping_failure_reports_applied_truthfully(self):
        preview = self.preview()
        with mock.patch.object(
            recovery,
            "_commit_quarantine_metadata",
            side_effect=OSError("injected bookkeeping failure"),
        ):
            with self.assertRaises(recovery.QuarantineAppliedIncomplete) as caught:
                self.apply(preview)
        self.assertTrue(caught.exception.applied)
        self.assertTrue(caught.exception.mutated)
        self.assertFalse(self.archive.exists())
        self.assertTrue(Path(caught.exception.quarantined_path).exists())

    def test_committed_metadata_replay_finalizes_stale_prepared_journal(self):
        preview = self.preview()

        def fault(point: str) -> None:
            if point == "metadata_committed":
                raise recovery.QuarantineInjectedCrash(point)

        with self.assertRaises(recovery.QuarantineInjectedCrash):
            self.apply(preview, fault=fault)
        journals = list(
            (self.rec / "quarantine" / "journals").glob("*.json")
        )
        self.assertEqual(len(journals), 1)
        replay = self.apply(preview)
        self.assertEqual(replay["outcome"], "already_quarantined")
        self.assertFalse(journals[0].exists())

    def test_guarded_reverse_restores_and_is_idempotent(self):
        applied = self.apply()
        metadata = Path(applied["metadata_path"])
        reversed_once = recovery._reverse_quarantine(
            metadata, recovery_dir=self.rec
        )
        self.assertEqual(reversed_once["outcome"], "restored")
        self.assertEqual(self.archive.read_bytes(), b"legacy recovery bytes")
        self.assertFalse(Path(applied["quarantined_path"]).exists())
        reversed_twice = recovery._reverse_quarantine(
            metadata, recovery_dir=self.rec
        )
        self.assertEqual(reversed_twice["outcome"], "already_restored")

    def test_reverse_resumes_after_bytes_move_before_final_metadata(self):
        applied = self.apply()
        metadata = Path(applied["metadata_path"])
        real_write = recovery._atomic_private_write

        def fail_final(path: Path, document: dict) -> None:
            if (
                path.parent.name == "reversals"
                and path.name.endswith(".json")
                and not path.name.endswith(".pending.json")
            ):
                raise OSError("injected reversal bookkeeping failure")
            real_write(path, document)

        with mock.patch.object(
            recovery, "_atomic_private_write", side_effect=fail_final
        ):
            with self.assertRaises(recovery.QuarantineAppliedIncomplete):
                recovery._reverse_quarantine(metadata, recovery_dir=self.rec)
        resumed = recovery._reverse_quarantine(metadata, recovery_dir=self.rec)
        self.assertEqual(resumed["outcome"], "already_restored")
        self.assertEqual(self.archive.read_bytes(), b"legacy recovery bytes")

    def test_reverse_refuses_original_collision_or_quarantine_drift(self):
        applied = self.apply()
        metadata = Path(applied["metadata_path"])
        self.archive.write_bytes(b"collision")
        with self.assertRaises(recovery.QuarantineRefused):
            recovery._reverse_quarantine(metadata, recovery_dir=self.rec)
        self.archive.unlink()
        Path(applied["quarantined_path"]).write_bytes(b"drift")
        with self.assertRaises(recovery.QuarantineRefused):
            recovery._reverse_quarantine(metadata, recovery_dir=self.rec)

    def test_quarantine_and_maintenance_share_the_existing_lock(self):
        entered = threading.Event()
        release = threading.Event()
        preview = self.preview()

        def fault(point: str) -> None:
            if point == "journal_durable":
                entered.set()
                release.wait(5)

        worker = threading.Thread(
            target=recovery.apply_quarantine,
            args=(str(self.archive), preview["token"]),
            kwargs={"recovery_dir": self.rec, "fault": fault},
        )
        worker.start()
        self.assertTrue(entered.wait(5))
        with state_mod.State() as st:
            result = retention.run_maintenance(
                st,
                recovery_dir=self.rec,
                trigger="opportunistic",
                timeout=0.1,
            )
        self.assertEqual(result.get("skipped"), "lock_busy")
        release.set()
        worker.join(5)
        self.assertFalse(worker.is_alive())


class TestMaintenanceInstallAndCount(QuarantineBase):
    def test_quarantine_survives_force_ttl_pressure_and_journal_resume(self):
        applied = self.apply()
        quarantined = Path(applied["quarantined_path"])
        expected = hashlib.sha256(quarantined.read_bytes()).hexdigest()
        recovery.prune_artifacts(recovery_dir=self.rec, force=True)
        with state_mod.State() as st:
            retention.run_maintenance(
                st,
                recovery_dir=self.rec,
                trigger="manual",
                ttl_seconds=0,
                watermark_bytes=0,
                min_age_seconds=0,
            )
            trash = self.rec / ".trash"
            trash.mkdir(exist_ok=True)
            journal = trash / "hostile.deletion.json"
            journal.write_text(
                json.dumps(
                    {
                        "schema": retention.SCHEMA_DELETION_JOURNAL,
                        "artifact_id": "hostile",
                        "reason": "ttl",
                        "archive": str(quarantined),
                        "manifest": "",
                    }
                ),
                encoding="utf-8",
            )
            resumed = retention._resume(self.rec, st)
        self.assertIn(str(journal), resumed["needs_repair"])
        self.assertTrue(quarantined.exists())
        self.assertEqual(hashlib.sha256(quarantined.read_bytes()).hexdigest(), expected)
        summary = retention.status(recovery_dir=self.rec)
        self.assertEqual(summary["ordinary_bytes"], 0)
        self.assertEqual(summary["protected_bytes"], 0)

    def test_normal_uninstall_preserves_whole_quarantine_subtree(self):
        home = Path(self._tmp.name) / "install-home"
        env = {
            **os.environ,
            "HOME": str(home),
            "XDG_DATA_HOME": str(home / ".local" / "share"),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_STATE_HOME": str(home / ".local" / "state"),
        }
        installed = subprocess.run(
            ["bash", str(_ROOT / "install.sh")],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
        quarantine = Path(env["XDG_STATE_HOME"]) / "awa" / "recovery" / "quarantine"
        (quarantine / "artifacts").mkdir(parents=True, mode=0o700)
        (quarantine / "metadata").mkdir(mode=0o700)
        (quarantine / "journals").mkdir(mode=0o700)
        (quarantine / "artifacts" / "fixture").write_bytes(b"preserve")
        (quarantine / "metadata" / "fixture.json").write_bytes(b'{"state":"committed"}\n')
        (quarantine / "journals" / "fixture.json").write_bytes(b"partial")
        before = {
            p.relative_to(quarantine).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in quarantine.rglob("*")
            if p.is_file()
        }
        removed = subprocess.run(
            ["bash", str(_ROOT / "install.sh"), "--uninstall"],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(removed.returncode, 0, removed.stdout + removed.stderr)
        after = {
            p.relative_to(quarantine).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in quarantine.rglob("*")
            if p.is_file()
        }
        self.assertEqual(after, before)

    def test_count_uses_only_committed_valid_on_disk_records(self):
        applied = self.apply()
        root = self.rec / "quarantine"
        (root / "metadata" / "corrupt.json").write_text("{", encoding="utf-8")
        (root / "metadata" / "partial.json").write_text(
            json.dumps({"schema": recovery.QUARANTINE_SCHEMA, "state": "prepared"}),
            encoding="utf-8",
        )
        (root / "journals" / "partial.json").write_text("{}", encoding="utf-8")
        (root / "metadata" / ".temp").write_text("{}", encoding="utf-8")
        self.assertEqual(recovery.quarantine_count(self.rec), 1)
        self.assertTrue(Path(applied["metadata_path"]).exists())

    def test_integrity_evaluation_derives_current_count_not_previous_value(self):
        self.apply()
        safe = integrity.Facts(
            guard_primary_deny=True,
            guard_cd_bypass_deny=True,
            guard_linked_allow=True,
            parity_ok=True,
            hook_rows_present=True,
            hook_fail_open=True,
            mcp_matches=True,
            release_matches=True,
            recovery_last_status="ok",
            needs_repair=0,
            leases_unreconciled=0,
            sessions_dangling=0,
            husks=0,
            disposition_map={},
            handoff_state="closed",
            launchd_last_success_age_s=0,
            delivered={"native": "accepted", "slack": "opted_out"},
        )
        with mock.patch.object(integrity, "read_status", return_value={
            "recovery": {"quarantine_count": 999},
            "invariants": [],
            "triggers": {},
            "orphans": {},
        }):
            evaluated = integrity.evaluate("deep", trigger="cli", facts=safe)
        self.assertEqual(evaluated["recovery"]["quarantine_count"], 1)

    def test_maintenance_and_integrity_never_apply_quarantine_automatically(self):
        with mock.patch.object(
            recovery,
            "apply_quarantine",
            side_effect=AssertionError("automatic quarantine"),
        ):
            with state_mod.State() as st:
                retention.run_maintenance(
                    st, recovery_dir=self.rec, trigger="manual"
                )
            integrity._recovery_facts()


class TestRetentionSidecarQuarantine(QuarantineBase):
    def test_valid_sidecar_moves_without_retention_orphan_and_survives_maintenance(self):
        manifest = self.add_manifest(protected=True)
        archive_bytes = self.archive.read_bytes()
        manifest_bytes = manifest.read_bytes()
        preview = self.preview()
        self.assertTrue(preview["sidecar"]["present"])
        applied = self.apply(preview)
        quarantined_manifest = Path(applied["sidecar"]["quarantined_path"])
        self.assertFalse(manifest.exists())
        self.assertEqual(quarantined_manifest.read_bytes(), manifest_bytes)
        self.assertEqual(Path(applied["quarantined_path"]).read_bytes(), archive_bytes)
        scan = retention.scan(self.rec)
        self.assertEqual(scan.descriptors, [])
        self.assertEqual(scan.needs_repair, [])
        with state_mod.State() as st:
            maintained = retention.run_maintenance(
                st,
                recovery_dir=self.rec,
                trigger="manual",
                ttl_seconds=0,
                watermark_bytes=0,
                min_age_seconds=0,
            )
            trash = self.rec / ".trash"
            trash.mkdir(exist_ok=True)
            hostile = trash / "sidecar.deletion.json"
            hostile.write_text(
                json.dumps(
                    {
                        "schema": retention.SCHEMA_DELETION_JOURNAL,
                        "artifact_id": "sidecar-hostile",
                        "reason": "ttl",
                        "archive": "",
                        "manifest": str(quarantined_manifest),
                    }
                ),
                encoding="utf-8",
            )
            resumed = retention._resume(self.rec, st)
        recovery.prune_artifacts(recovery_dir=self.rec, force=True)
        self.assertEqual(maintained["needs_repair"], [])
        self.assertIn(str(hostile), resumed["needs_repair"])
        self.assertTrue(quarantined_manifest.exists())
        self.assertEqual(recovery.quarantine_count(self.rec), 1)

    def test_digest_binds_sidecar_presence_and_absence(self):
        absent = self.preview()
        self.assertFalse(absent["sidecar"]["present"])
        manifest = self.add_manifest()
        present = self.preview()
        self.assertTrue(present["sidecar"]["present"])
        self.assertNotEqual(absent["token"], present["token"])
        with self.assertRaises(recovery.QuarantineRefused):
            self.apply(absent)
        self.assertTrue(self.archive.exists())
        self.assertTrue(manifest.exists())

    def test_sidecar_drift_swap_or_disappearance_refuses_pre_effect(self):
        mutations = ("content", "mtime", "inode", "missing")
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                archive = self.rec / f"{mutation}.tar.gz"
                archive.write_bytes(b"archive")
                self.archive = archive
                manifest = self.add_manifest()
                preview = self.preview()
                original_stat = manifest.stat()
                if mutation == "content":
                    manifest.write_bytes(b"changed manifest")
                    os.utime(
                        manifest,
                        ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
                    )
                elif mutation == "mtime":
                    os.utime(
                        manifest,
                        ns=(
                            original_stat.st_atime_ns,
                            original_stat.st_mtime_ns + 1_000_000_000,
                        ),
                    )
                elif mutation == "inode":
                    replacement = manifest.with_suffix(".replacement")
                    replacement.write_bytes(manifest.read_bytes())
                    os.utime(
                        replacement,
                        ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
                    )
                    os.replace(replacement, manifest)
                else:
                    manifest.unlink()
                with self.assertRaises(recovery.QuarantineRefused):
                    self.apply(preview)
                self.assertTrue(archive.exists())

    def test_sidecar_symlink_escape_and_destination_collision_refuse(self):
        candidate = self.archive.with_name("legacy.manifest.json")
        outside = Path(self._tmp.name) / "outside.manifest.json"
        outside.write_text("{}\n", encoding="utf-8")
        candidate.symlink_to(outside)
        with self.assertRaises(recovery.QuarantineRefused):
            self.preview()
        candidate.unlink()
        document = retention.build_manifest(
            "bundle", "", self.archive, recovery_root=self.rec
        )
        document["archive"] = str(Path(self._tmp.name) / "outside.tar.gz")
        candidate.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaises(recovery.QuarantineRefused):
            self.preview()
        candidate.unlink()
        self.add_manifest()
        preview = self.preview()
        collision = Path(preview["sidecar"]["destination"])
        collision.parent.mkdir(parents=True, exist_ok=True)
        collision.write_bytes(b"collision")
        with self.assertRaises(recovery.QuarantineRefused):
            self.apply(preview)
        self.assertEqual(collision.read_bytes(), b"collision")
        self.assertTrue(self.archive.exists())

    def test_sidecar_component_crash_points_resume_without_orphan(self):
        self.archive.unlink()
        for point in recovery.QUARANTINE_SIDECAR_CRASH_POINTS:
            with self.subTest(point=point):
                archive = self.rec / f"{point}.tar.gz"
                archive.write_bytes(point.encode())
                self.archive = archive
                manifest = self.add_manifest()
                archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
                manifest_hash = hashlib.sha256(manifest.read_bytes()).hexdigest()
                preview = self.preview()

                def fault(observed: str) -> None:
                    if observed == point:
                        raise recovery.QuarantineInjectedCrash(point)

                with self.assertRaises(recovery.QuarantineInjectedCrash):
                    self.apply(preview, fault=fault)
                resumed = self.apply(preview)
                self.assertEqual(
                    hashlib.sha256(
                        Path(resumed["quarantined_path"]).read_bytes()
                    ).hexdigest(),
                    archive_hash,
                )
                self.assertEqual(
                    hashlib.sha256(
                        Path(resumed["sidecar"]["quarantined_path"]).read_bytes()
                    ).hexdigest(),
                    manifest_hash,
                )
                self.assertEqual(retention.scan(self.rec).needs_repair, [])

    def test_partial_sidecar_first_move_survives_maintenance_before_resume(self):
        manifest = self.add_manifest()
        preview = self.preview()

        def fault(point: str) -> None:
            if point == "sidecar_phase_durable":
                raise recovery.QuarantineInjectedCrash(point)

        with self.assertRaises(recovery.QuarantineInjectedCrash):
            self.apply(preview, fault=fault)
        self.assertTrue(self.archive.exists())
        self.assertFalse(manifest.exists())
        quarantined_sidecar = Path(preview["sidecar"]["destination"])
        self.assertTrue(quarantined_sidecar.exists())
        with state_mod.State() as st:
            retention.run_maintenance(
                st,
                recovery_dir=self.rec,
                trigger="manual",
                ttl_seconds=0,
                watermark_bytes=0,
                min_age_seconds=0,
            )
        self.assertTrue(self.archive.exists())
        self.assertTrue(quarantined_sidecar.exists())
        resumed = self.apply(preview)
        self.assertTrue(Path(resumed["quarantined_path"]).exists())
        self.assertTrue(Path(resumed["sidecar"]["quarantined_path"]).exists())

    def test_post_sidecar_pre_archive_failure_reports_applied_truthfully(self):
        self.add_manifest()
        preview = self.preview()

        def fault(point: str) -> None:
            if point == "sidecar_phase_durable":
                self.archive.write_bytes(b"archive drift after sidecar move")

        with self.assertRaises(recovery.QuarantineAppliedIncomplete) as caught:
            self.apply(preview, fault=fault)
        self.assertTrue(caught.exception.applied)
        self.assertTrue(caught.exception.mutated)
        self.assertTrue(Path(caught.exception.quarantined_path).exists())
        self.assertTrue(self.archive.exists())

    def test_guarded_reversal_restores_both_files_and_resumes_crashes(self):
        for point in recovery.QUARANTINE_REVERSAL_SIDECAR_CRASH_POINTS:
            with self.subTest(point=point):
                archive = self.rec / f"reverse-{point}.tar.gz"
                archive.write_bytes(point.encode())
                self.archive = archive
                manifest = self.add_manifest()
                archive_bytes = archive.read_bytes()
                manifest_bytes = manifest.read_bytes()
                applied = self.apply()
                metadata = Path(applied["metadata_path"])

                def fault(observed: str) -> None:
                    if observed == point:
                        raise recovery.QuarantineInjectedCrash(point)

                with self.assertRaises(recovery.QuarantineInjectedCrash):
                    recovery._reverse_quarantine(
                        metadata,
                        recovery_dir=self.rec,
                        fault=fault,
                    )
                resumed = recovery._reverse_quarantine(
                    metadata, recovery_dir=self.rec
                )
                self.assertIn(
                    resumed["outcome"], {"restored", "already_restored"}
                )
                self.assertEqual(archive.read_bytes(), archive_bytes)
                self.assertEqual(manifest.read_bytes(), manifest_bytes)
                self.assertFalse(
                    Path(applied["quarantined_path"]).exists()
                )
                self.assertFalse(
                    Path(applied["sidecar"]["quarantined_path"]).exists()
                )


class TestQuarantineCli(QuarantineBase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "engine", *args],
            cwd=str(_ROOT),
            env={**os.environ, "PYTHONPATH": str(_ROOT)},
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_preview_apply_and_replay_json_exit_semantics(self):
        preview_proc = self.run_cli(
            "recover", "quarantine", "--archive", str(self.archive), "--preview"
        )
        self.assertEqual(preview_proc.returncode, 0, preview_proc.stderr)
        preview = json.loads(preview_proc.stdout)
        self.assertEqual(preview["outcome"], "previewed")
        applied_proc = self.run_cli(
            "recover",
            "quarantine",
            "--archive",
            str(self.archive),
            "--apply",
            "--token",
            preview["token"],
        )
        self.assertEqual(applied_proc.returncode, 0, applied_proc.stderr)
        applied = json.loads(applied_proc.stdout)
        self.assertEqual(applied["outcome"], "quarantined")
        replay_proc = self.run_cli(
            "recover",
            "quarantine",
            "--archive",
            str(self.archive),
            "--apply",
            "--token",
            preview["token"],
        )
        self.assertEqual(replay_proc.returncode, 0, replay_proc.stderr)
        self.assertEqual(
            json.loads(replay_proc.stdout)["outcome"], "already_quarantined"
        )

    def test_malformed_or_missing_flags_exit_two(self):
        cases = (
            ("recover", "quarantine", "--archive", str(self.archive)),
            (
                "recover",
                "quarantine",
                "--archive",
                str(self.archive),
                "--preview",
                "--apply",
            ),
            (
                "recover",
                "quarantine",
                "--archive",
                str(self.archive),
                "--apply",
            ),
            (
                "recover",
                "quarantine",
                "--archive",
                str(self.archive),
                "--preview",
                "--token",
                "x",
            ),
        )
        for argv in cases:
            with self.subTest(argv=argv):
                self.assertEqual(self.run_cli(*argv).returncode, 2)
        self.assertEqual(
            self.run_cli("recover", "list", "--preview").returncode,
            2,
        )

    def test_refusal_is_closed_json(self):
        preview = self.preview()
        self.archive.write_bytes(b"drift")
        proc = self.run_cli(
            "recover",
            "quarantine",
            "--archive",
            str(self.archive),
            "--apply",
            "--token",
            preview["token"],
        )
        self.assertEqual(proc.returncode, 1)
        result = json.loads(proc.stdout)
        self.assertEqual(result["outcome"], "refused")
        self.assertFalse(result["applied"])
        self.assertFalse(result["mutated"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
