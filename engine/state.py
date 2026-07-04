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
CREATE INDEX IF NOT EXISTS idx_events_lease ON events(lease_id);
CREATE INDEX IF NOT EXISTS idx_leases_common ON leases(git_common_dir);
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
        self._set_meta("schema_version", str(SCHEMA_VERSION))
        self._tighten_perms()

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
                        manifest: str | None = None, lease_id: str | None = None) -> None:
        self.conn.execute(
            "INSERT INTO recovery_artifacts(ts,lease_id,kind,source,archive,manifest) "
            "VALUES(?,?,?,?,?,?)",
            (now_iso(), lease_id, kind, source, archive, manifest),
        )

    def recovery_artifacts(self, limit: int = 100) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM recovery_artifacts ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

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
