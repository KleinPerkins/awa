"""state.py — durable SQLite state store (WAL, local disk only) (§H6/S4).

The db + its -wal/-shm sidecars live under ${XDG_STATE_HOME}/awa on LOCAL disk
(WAL corrupts on synced/network paths). The store is opened WAL-mode with a
busy_timeout; the per-common-dir advisory lock (lock.py) is the real write
serialization boundary — WAL just makes concurrent readers non-blocking.

All state files are created 700/600 (S4). The store records leases, lifecycle
events (append-only audit, redacted via redact.py), detections, quarantine refs,
and recovery artifacts. It is bookkeeping, NOT on the safety-critical path: the
kernel guarantee holds even if the db is absent/corrupt (the guard degrades to the
policy snapshot + .awa/lease.json).
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

from . import paths

# Audit redaction lives in the engine package (engine/redact.py). Import defensively:
# redaction is defense-in-depth and must NEVER be fatal if the module is unavailable.
try:
    from . import redact  # type: ignore
except Exception:  # noqa: BLE001 — redaction is defense-in-depth; never fatal.
    class _NoRedact:
        @staticmethod
        def redact(text: str) -> str:
            return text
    redact = _NoRedact()  # type: ignore


SCHEMA_VERSION = 1

_DDL = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS leases (
    lease_id TEXT PRIMARY KEY,
    worktree_path TEXT NOT NULL,
    branch TEXT NOT NULL,
    git_common_dir TEXT NOT NULL,
    boot_id TEXT NOT NULL,
    base_ref TEXT,
    head TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    attested_at TEXT,
    pid INTEGER
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    lease_id TEXT,
    kind TEXT NOT NULL,
    detail TEXT
);
CREATE TABLE IF NOT EXISTS detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    repo TEXT NOT NULL,
    path TEXT NOT NULL,
    kind TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS quarantine_refs (
    ref TEXT PRIMARY KEY,
    lease_id TEXT,
    git_common_dir TEXT NOT NULL,
    created_at TEXT NOT NULL,
    retire_after TEXT
);
CREATE TABLE IF NOT EXISTS recovery_artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    lease_id TEXT,
    kind TEXT NOT NULL,
    source TEXT NOT NULL,
    archive TEXT NOT NULL,
    manifest TEXT
);
-- Phase 3 recovery-retention: the age clock starts when the SOURCE work is deleted, not when
-- the archive is created. Manifests are read-only, so first-observed source-deletion time is
-- recorded here, keyed by the collision-resistant artifact_id (works for legacy artifacts too).
CREATE TABLE IF NOT EXISTS recovery_source_deleted (
    artifact_id TEXT PRIMARY KEY,
    epoch INTEGER NOT NULL,
    iso TEXT NOT NULL
);
-- Phase 3 recovery-retention: an explicit prune tombstone (artifact_id, time, reason, bytes) so
-- a recovery row/receipt no longer implies an expired archive is restorable. Append-only, keyed
-- by artifact_id (idempotent under crash-resume via INSERT OR IGNORE).
CREATE TABLE IF NOT EXISTS recovery_tombstones (
    artifact_id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    ts_epoch INTEGER NOT NULL,
    reason TEXT NOT NULL,
    bytes INTEGER NOT NULL DEFAULT 0,
    kind TEXT,
    archive TEXT,
    manifest TEXT,
    source TEXT
);
CREATE TABLE IF NOT EXISTS clean_receipts (
    receipt_id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    disposition TEXT NOT NULL,
    reason_code TEXT,
    path TEXT,
    branch TEXT,
    archive TEXT,
    root_disposition TEXT,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_lease ON events(lease_id);
CREATE INDEX IF NOT EXISTS idx_leases_common ON leases(git_common_dir);
CREATE INDEX IF NOT EXISTS idx_detections_kind_path ON detections(kind, path);
"""


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class State:
    def __init__(self, db_path: Path | None = None, *, assert_local: bool = True):
        self.db_path = Path(db_path) if db_path else paths.state_db_path()
        paths.ensure_dir(self.db_path.parent)
        if assert_local:
            paths.assert_local_disk(self.db_path.parent)
        # Restrictive umask so the db + sidecars are created 600, not world-readable.
        old_umask = os.umask(0o077)
        try:
            self.conn = sqlite3.connect(str(self.db_path), timeout=30.0, isolation_level=None)
        finally:
            os.umask(old_umask)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA busy_timeout=30000")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(_DDL)
        self._migrate()
        self._set_meta("schema_version", str(SCHEMA_VERSION))
        self._tighten_perms()

    def _migrate(self) -> None:
        """Additive-within-v1 column migration for `recovery_artifacts` (Phase 3 retention).

        `_DDL` uses CREATE TABLE IF NOT EXISTS, which will NOT add columns to a table an older
        install already created. Add each Phase-3 column idempotently (ALTER TABLE ADD COLUMN,
        guarded by PRAGMA table_info) so a pre-existing db upgrades in place with no data loss.
        """
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(recovery_artifacts)")}
        additions = (
            ("artifact_id", "TEXT"),
            ("sha256", "TEXT"),
            ("bytes", "INTEGER"),
            ("protected", "INTEGER NOT NULL DEFAULT 0"),
            ("status", "TEXT NOT NULL DEFAULT 'active'"),
        )
        for name, decl in additions:
            if name not in cols:
                self.conn.execute(f"ALTER TABLE recovery_artifacts ADD COLUMN {name} {decl}")

    def _tighten_perms(self) -> None:
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(self.db_path) + suffix)
            if p.exists():
                try:
                    os.chmod(p, paths.FILE_MODE)
                except OSError:
                    pass

    def _set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def wal_mode(self) -> str:
        return str(self.conn.execute("PRAGMA journal_mode").fetchone()[0])

    # ---- events (append-only, redacted audit) --------------------------------
    def record_event(self, kind: str, detail: str = "", lease_id: str | None = None) -> None:
        self.conn.execute(
            "INSERT INTO events(ts,lease_id,kind,detail) VALUES(?,?,?,?)",
            (now_iso(), lease_id, kind, redact.redact(detail or "")),
        )

    def events(self, lease_id: str | None = None, limit: int = 100) -> list[dict]:
        if lease_id:
            rows = self.conn.execute(
                "SELECT * FROM events WHERE lease_id=? ORDER BY id DESC LIMIT ?",
                (lease_id, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ---- leases --------------------------------------------------------------
    def upsert_lease(self, lease: dict) -> None:
        ts = now_iso()
        existing = self.get_lease(lease["lease_id"])
        created = existing["created_at"] if existing else lease.get("created_at", ts)
        self.conn.execute(
            """INSERT INTO leases(lease_id,worktree_path,branch,git_common_dir,boot_id,
                    base_ref,head,status,created_at,updated_at,attested_at,pid)
               VALUES(:lease_id,:worktree_path,:branch,:git_common_dir,:boot_id,
                    :base_ref,:head,:status,:created_at,:updated_at,:attested_at,:pid)
               ON CONFLICT(lease_id) DO UPDATE SET
                    worktree_path=excluded.worktree_path, branch=excluded.branch,
                    git_common_dir=excluded.git_common_dir, boot_id=excluded.boot_id,
                    base_ref=excluded.base_ref, head=excluded.head, status=excluded.status,
                    updated_at=excluded.updated_at, attested_at=excluded.attested_at,
                    pid=excluded.pid""",
            {
                "lease_id": lease["lease_id"],
                "worktree_path": lease["worktree_path"],
                "branch": lease["branch"],
                "git_common_dir": lease["git_common_dir"],
                "boot_id": lease["boot_id"],
                "base_ref": lease.get("base_ref"),
                "head": lease.get("head"),
                "status": lease.get("status", "active"),
                "created_at": created,
                "updated_at": ts,
                "attested_at": lease.get("attested_at"),
                "pid": lease.get("pid"),
            },
        )

    def get_lease(self, lease_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM leases WHERE lease_id=?", (lease_id,)).fetchone()
        return dict(row) if row else None

    def list_leases(self, status: str | None = None) -> list[dict]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM leases WHERE status=? ORDER BY created_at", (status,)
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM leases ORDER BY created_at").fetchall()
        return [dict(r) for r in rows]

    def set_lease_status(self, lease_id: str, status: str) -> None:
        self.conn.execute(
            "UPDATE leases SET status=?, updated_at=? WHERE lease_id=?",
            (status, now_iso(), lease_id),
        )

    def attest_lease(self, lease_id: str) -> None:
        self.conn.execute(
            "UPDATE leases SET attested_at=?, updated_at=? WHERE lease_id=?",
            (now_iso(), now_iso(), lease_id),
        )

    # ---- detections ----------------------------------------------------------
    def record_detection(self, repo: str, path: str, kind: str = "primary-file-edit-detected") -> None:
        self.conn.execute(
            "INSERT INTO detections(ts,repo,path,kind) VALUES(?,?,?,?)",
            (now_iso(), repo, path, kind),
        )

    def detections(self, limit: int = 100) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM detections ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def detection_exists(self, kind: str, path: str) -> bool:
        """True if a detection with this (kind, path) is already recorded — lets an observer
        (e.g. the vanished-worktree detector) stay idempotent across repeated passes."""
        row = self.conn.execute(
            "SELECT 1 FROM detections WHERE kind=? AND path=? LIMIT 1", (kind, path)
        ).fetchone()
        return row is not None

    # ---- clean receipts (folded from the kernel's clean_receipt/v1 records) ---
    def record_clean_receipt(self, receipt: dict) -> bool:
        """Fold ONE kernel clean_receipt/v1 into the durable timeline. Idempotent by
        receipt_id (INSERT OR IGNORE) so repeated ingests never double-count. Returns True
        only when a NEW receipt row was inserted. Detail is redacted (defense-in-depth)."""
        receipt_id = str(receipt.get("receipt_id") or "").strip()
        if not receipt_id:
            return False
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO clean_receipts"
            "(receipt_id,ts,disposition,reason_code,path,branch,archive,root_disposition,detail) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (
                receipt_id,
                str(receipt.get("time") or now_iso()),
                str(receipt.get("disposition") or ""),
                str(receipt.get("reason_code") or ""),
                str(receipt.get("path") or ""),
                str(receipt.get("branch") or ""),
                str(receipt.get("archive") or ""),
                str(receipt.get("root_disposition") or ""),
                redact.redact(str(receipt.get("message") or "")),
            ),
        )
        return cur.rowcount > 0

    def clean_receipts(self, limit: int = 100) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM clean_receipts ORDER BY ts DESC, receipt_id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ---- quarantine refs -----------------------------------------------------
    def record_quarantine_ref(self, ref: str, git_common_dir: str,
                              lease_id: str | None = None, retire_after: str | None = None) -> None:
        self.conn.execute(
            """INSERT INTO quarantine_refs(ref,lease_id,git_common_dir,created_at,retire_after)
               VALUES(?,?,?,?,?)
               ON CONFLICT(ref) DO UPDATE SET retire_after=excluded.retire_after""",
            (ref, lease_id, git_common_dir, now_iso(), retire_after),
        )

    def quarantine_refs(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM quarantine_refs ORDER BY created_at").fetchall()
        return [dict(r) for r in rows]

    def delete_quarantine_ref(self, ref: str) -> None:
        self.conn.execute("DELETE FROM quarantine_refs WHERE ref=?", (ref,))

    # ---- recovery artifacts --------------------------------------------------
    def record_recovery(self, kind: str, source: str, archive: str,
                        manifest: str | None = None, lease_id: str | None = None,
                        *, artifact_id: str | None = None, sha256: str | None = None,
                        bytes: int | None = None, protected: bool = False) -> None:
        self.conn.execute(
            "INSERT INTO recovery_artifacts"
            "(ts,lease_id,kind,source,archive,manifest,artifact_id,sha256,bytes,protected,status) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,'active')",
            (now_iso(), lease_id, kind, source, archive, manifest,
             artifact_id, sha256, bytes, 1 if protected else 0),
        )

    def recovery_artifacts(self, limit: int = 100) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM recovery_artifacts ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_recovery_pruned(self, artifact_id: str, archive: str | None = None) -> None:
        """Reconcile recovery rows once an artifact is pruned so a row no longer implies the
        archive is restorable. Matches by artifact_id (new rows) OR archive path (legacy rows)."""
        self.conn.execute(
            "UPDATE recovery_artifacts SET status='pruned' "
            "WHERE artifact_id=? OR (archive=? AND ?<>'')",
            (artifact_id, archive or "", archive or ""),
        )

    # ---- recovery source-deletion age clock (Phase 3) ------------------------
    def get_source_deleted_epoch(self, artifact_id: str) -> int | None:
        row = self.conn.execute(
            "SELECT epoch FROM recovery_source_deleted WHERE artifact_id=?", (artifact_id,)
        ).fetchone()
        return int(row["epoch"]) if row else None

    def set_source_deleted_epoch(self, artifact_id: str, epoch: int) -> None:
        """Record the FIRST-observed source-deletion time for an artifact (idempotent — a later
        observation never moves the clock forward or back)."""
        self.conn.execute(
            "INSERT OR IGNORE INTO recovery_source_deleted(artifact_id,epoch,iso) VALUES(?,?,?)",
            (artifact_id, int(epoch),
             time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(epoch)))),
        )

    def clear_source_deleted(self, artifact_id: str) -> None:
        """Source reappeared (path reused) — stop aging it (fail-safe: keep the artifact)."""
        self.conn.execute("DELETE FROM recovery_source_deleted WHERE artifact_id=?", (artifact_id,))

    # ---- recovery prune tombstones (Phase 3) ---------------------------------
    def record_recovery_tombstone(self, artifact_id: str, *, reason: str, bytes: int = 0,
                                  kind: str | None = None, archive: str | None = None,
                                  manifest: str | None = None, source: str | None = None) -> bool:
        """Append ONE prune tombstone (idempotent by artifact_id). Returns True on a new row."""
        epoch = int(time.time())
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO recovery_tombstones"
            "(artifact_id,ts,ts_epoch,reason,bytes,kind,archive,manifest,source) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (artifact_id, now_iso(), epoch, reason, int(bytes or 0), kind, archive, manifest,
             source),
        )
        return cur.rowcount > 0

    def recovery_tombstones(self, limit: int = 100) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM recovery_tombstones ORDER BY ts_epoch DESC, artifact_id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def tombstone_exists(self, artifact_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM recovery_tombstones WHERE artifact_id=? LIMIT 1", (artifact_id,)
        ).fetchone()
        return row is not None

    def close(self) -> None:
        try:
            self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.Error:
            pass
        self.conn.close()

    def __enter__(self) -> "State":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def perms_report(db_path: Path | None = None) -> dict:
    """S4: report octal modes of the state dir + db files (doctor asserts 700/600)."""
    db_path = Path(db_path) if db_path else paths.state_db_path()
    out: dict[str, str] = {}
    d = db_path.parent
    if d.exists():
        out[str(d)] = oct(os.stat(d).st_mode & 0o777)
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(db_path) + suffix)
        if p.exists():
            out[str(p)] = oct(os.stat(p).st_mode & 0o777)
    return out
