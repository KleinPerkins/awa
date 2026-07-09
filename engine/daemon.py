"""daemon.py — watcher/enforcer with single-instance guarantee (§H6, Phase 4).

The engine is OFF the safety-critical path: the daemon only observes, bookkeeps, and
eases (it never becomes a new safety dependency). Its two jobs:

  * single-instance: bind an exclusive flock over a pidfile in the run dir and REFUSE
    to start a second instance. All state writes go through the daemon OR (daemon off)
    through the local guard holding the same per-common-dir lock — never two concurrent
    writers.
  * bounded loops (event-first, capped iterations so a test/CI run terminates): a
    quarantine-ref cleanup/retention pass that deletes expired `refs/awa/*` refs and
    prunes their state rows.

`SingleInstance` is a context manager; a second acquire raises `AlreadyRunning`.
"""

from __future__ import annotations

import calendar
import errno
import fcntl
import json
import os
import time
from pathlib import Path

from . import gitutil, paths, state as state_mod


class AlreadyRunning(RuntimeError):
    def __init__(self, pid: int | None):
        self.pid = pid
        super().__init__(f"AWA daemon already running (pid={pid})")


class SingleInstance:
    """Exclusive flock over a pidfile — refuses a second concurrent daemon."""

    def __init__(self, pidfile: Path | None = None):
        self.pidfile = Path(pidfile) if pidfile else paths.run_dir() / "daemon.pid"
        self._fd: int | None = None

    def _read_pid(self) -> int | None:
        try:
            txt = self.pidfile.read_text(encoding="ascii").strip()
            return int(txt) if txt else None
        except (OSError, ValueError):
            return None

    def acquire(self) -> "SingleInstance":
        paths.ensure_dir(self.pidfile.parent)
        fd = os.open(str(self.pidfile), os.O_RDWR | os.O_CREAT, paths.FILE_MODE)
        try:
            os.chmod(self.pidfile, paths.FILE_MODE)
        except OSError:
            pass
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            existing = self._read_pid()
            os.close(fd)
            if exc.errno in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES):
                raise AlreadyRunning(existing) from exc
            raise
        os.ftruncate(fd, 0)
        os.write(fd, f"{os.getpid()}\n".encode("ascii"))
        os.fsync(fd)
        self._fd = fd
        return self

    def release(self) -> None:
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            except OSError:
                pass
            os.close(self._fd)
            self._fd = None
            try:
                self.pidfile.unlink()
            except OSError:
                pass

    def status(self) -> dict:
        return {"pidfile": str(self.pidfile), "pid": self._read_pid(),
                "running": self.is_running()}

    def is_running(self) -> bool:
        """True if another live process holds the lock (probe without stealing)."""
        if not self.pidfile.exists():
            return False
        fd = os.open(str(self.pidfile), os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd, fcntl.LOCK_UN)
            return False  # we got it -> nobody holds it.
        except OSError:
            return True
        finally:
            os.close(fd)

    def __enter__(self) -> "SingleInstance":
        return self.acquire()

    def __exit__(self, *exc) -> None:
        self.release()


def cleanup_quarantine_refs(state: state_mod.State, *, now: float | None = None,
                            delete_remote: bool = False, remote: str = "origin") -> list[str]:
    """Delete state rows (and optionally the remote refs) for expired quarantine refs.

    A ref is expired when `retire_after` <= now. Bounded to `refs/awa/*`-marked rows.
    Returns the list of refs cleaned.
    """
    now = now if now is not None else time.time()
    cleaned: list[str] = []
    for row in state.quarantine_refs():
        ra = row.get("retire_after")
        if not ra:
            continue
        try:
            # `retire_after` is always UTC (written via time.gmtime()). `calendar.timegm`
            # interprets the parsed struct_time as UTC; `time.mktime` would wrongly treat
            # it as LOCAL time, skewing expiry by the host's UTC offset on every non-UTC
            # machine (bug: refs lingered/expired hours early depending on timezone sign).
            expiry = calendar.timegm(time.strptime(ra, "%Y-%m-%dT%H:%M:%SZ"))
        except (ValueError, TypeError):
            continue
        if expiry > now:
            continue
        ref = row["ref"]
        if not ref.startswith("refs/awa/"):
            continue  # safety: never touch a non-quarantine ref.
        if delete_remote:
            common = row.get("git_common_dir") or ""
            repo_dir = os.path.dirname(common) if common.endswith("/.git") else common
            gitutil.git(repo_dir or ".", "push", remote, f":{ref}", timeout=60)
        state.delete_quarantine_ref(ref)
        state.record_event("quarantine_cleanup", f"retired quarantine ref {ref}", row.get("lease_id"))
        cleaned.append(ref)
    return cleaned


def ingest_detection_receipts(state: state_mod.State,
                              receipts_path: Path | None = None) -> int:
    """Phase-6 engine-backing: fold the shell-gate's `afterFileEdit` detection receipts
    (JSONL, written by worktree-guard.sh — the safety-critical hook that must NOT depend
    on the engine) into the durable state, resuming from a persisted byte offset.

    This is the engine OBSERVING the kernel's detections after the fact — the hook keeps
    working with the engine off; the engine only enriches/bookkeeps. Returns the count of
    newly-ingested receipts.
    """
    rp = Path(receipts_path) if receipts_path else paths.detections_dir() / "receipts.jsonl"
    if not rp.exists():
        return 0
    offset = int(state.get_meta("detections_offset") or "0")
    size = rp.stat().st_size
    if size < offset:  # file rotated/truncated -> restart from the top.
        offset = 0
    ingested = 0
    with open(rp, encoding="utf-8", errors="replace") as fh:
        fh.seek(offset)
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            state.record_detection(
                repo=rec.get("repo", ""),
                path=rec.get("path", ""),
                kind=rec.get("kind", "primary-file-edit-detected"),
            )
            ingested += 1
        new_offset = fh.tell()
    state._set_meta("detections_offset", str(new_offset))
    if ingested:
        state.record_event("detections_ingested", f"folded {ingested} detection receipt(s)")
    return ingested


def ingest_clean_receipts(state: state_mod.State,
                          receipts_dir: Path | None = None) -> int:
    """K2 observability: fold the kernel's `clean_receipt/v1` records (one JSON file per
    terminal `clean`, written by dev-worktree.sh — the engine-OFF safety path) into the
    durable timeline, idempotently by receipt_id.

    Like `ingest_detection_receipts`, this is the engine OBSERVING the kernel after the fact:
    the receipts are authored with the engine off; the engine only reflects them into its
    queryable state so a terminal clean shows up in the observable history. Returns the count
    of newly-folded receipts. NON-load-bearing — it changes no gate/refusal decision.
    """
    rd = Path(receipts_dir) if receipts_dir else paths.receipts_dir()
    if not rd.is_dir():
        return 0
    ingested = 0
    for f in sorted(rd.glob("clean-*.json")):
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(rec, dict) or rec.get("schema") != "clean_receipt/v1":
            continue
        if state.record_clean_receipt(rec):
            ingested += 1
    if ingested:
        state.record_event("clean_receipts_ingested", f"folded {ingested} clean receipt(s)")
    return ingested


def _removed_attributed_paths(receipts_dir: Path) -> set[str]:
    """Canonical paths of worktrees whose removal IS attributed to an AWA clean receipt
    (disposition `removed`). Read straight from disk so the detector is self-contained
    (independent of whether the receipts were already folded into state)."""
    removed: set[str] = set()
    if not receipts_dir.is_dir():
        return removed
    for f in receipts_dir.glob("clean-*.json"):
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(rec, dict) and rec.get("disposition") == "removed" and rec.get("path"):
            removed.add(os.path.realpath(str(rec["path"])))
    return removed


def detect_missing_unattributed(state: state_mod.State, *,
                                roots_dir: Path | None = None,
                                receipts_dir: Path | None = None) -> list[dict]:
    """K2 observability: detect a Safe Workspace that VANISHED with no attributing record.

    A kernel `active_root/v1` record whose `root_path` no longer exists is a candidate. When an
    AWA `clean` removes a worktree it also drops that heartbeat record, so a lingering record for
    a missing path means the worktree disappeared OUTSIDE the AWA clean path. We cross-check the
    `removed` clean receipts: if one attributes that exact path, it is an attributed removal (the
    record merely lingered) and is NOT flagged. Otherwise it is `worktree_missing_unattributed`.

    Purely observational: records a (deduplicated) detection + event and returns the findings.
    It removes nothing and changes no gate/refusal decision.
    """
    rd = Path(roots_dir) if roots_dir else paths.roots_dir()
    rep = Path(receipts_dir) if receipts_dir else paths.receipts_dir()
    removed = _removed_attributed_paths(rep)
    found: list[dict] = []
    if not rd.is_dir():
        return found
    for f in sorted(rd.glob("*.json")):
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(rec, dict):
            continue
        rpath = rec.get("root_path")
        if not rpath or os.path.exists(rpath):
            continue  # no path recorded, or the worktree is still present.
        if os.path.realpath(str(rpath)) in removed:
            continue  # an AWA clean receipt attributes this removal — not unattributed.
        if not state.detection_exists("worktree_missing_unattributed", str(rpath)):
            state.record_detection(repo=str(rec.get("git_common_dir") or ""),
                                   path=str(rpath), kind="worktree_missing_unattributed")
            state.record_event("worktree_missing_unattributed",
                               f"vanished Safe Workspace with no attributing clean receipt: {rpath}")
        found.append({"path": rpath, "branch": rec.get("branch"),
                      "git_common_dir": rec.get("git_common_dir")})
    return found


def timeline(state: state_mod.State, limit: int = 100) -> list[dict]:
    """The observable engine timeline: detection receipts + folded clean receipts merged and
    sorted newest-first. Read-only view over durable state (call the ingest/detect passes first
    to populate it). Each entry carries a `type` discriminator (`detection` | `clean_receipt`)."""
    entries: list[dict] = []
    for d in state.detections(limit=limit):
        entries.append({"type": "detection", "ts": d.get("ts"), "kind": d.get("kind"),
                        "repo": d.get("repo"), "path": d.get("path")})
    for r in state.clean_receipts(limit=limit):
        entries.append({"type": "clean_receipt", "ts": r.get("ts"),
                        "disposition": r.get("disposition"), "reason_code": r.get("reason_code"),
                        "path": r.get("path"), "branch": r.get("branch"),
                        "archive": r.get("archive"), "root_disposition": r.get("root_disposition")})
    entries.sort(key=lambda e: (e.get("ts") or ""), reverse=True)
    return entries[:limit]


def run_once(state: state_mod.State, *, delete_remote: bool = False) -> dict:
    """One bounded maintenance pass. Returns a summary (bookkeeping only)."""
    cleaned = cleanup_quarantine_refs(state, delete_remote=delete_remote)
    ingested = ingest_detection_receipts(state)
    clean_ingested = ingest_clean_receipts(state)
    missing = detect_missing_unattributed(state)
    return {"quarantine_cleaned": cleaned, "detections_ingested": ingested,
            "clean_receipts_ingested": clean_ingested,
            "missing_unattributed": len(missing),
            "active_leases": len(state.list_leases("active"))}


def run_loop(state: state_mod.State, *, max_iterations: int = 1, interval: float = 0.0,
             delete_remote: bool = False) -> list[dict]:
    """Bounded event-first loop (capped iterations so tests/CI terminate)."""
    results: list[dict] = []
    for _ in range(max(1, max_iterations)):
        results.append(run_once(state, delete_remote=delete_remote))
        if interval > 0:
            time.sleep(interval)
    return results
