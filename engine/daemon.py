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


def run_once(state: state_mod.State, *, delete_remote: bool = False) -> dict:
    """One bounded maintenance pass. Returns a summary (bookkeeping only)."""
    cleaned = cleanup_quarantine_refs(state, delete_remote=delete_remote)
    ingested = ingest_detection_receipts(state)
    return {"quarantine_cleaned": cleaned, "detections_ingested": ingested,
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
