"""AWA integrity evaluator and status-last private store.

The integrity subsystem is observational and engine-side.  Its status file is a
single atomic commit point: generation-tagged derived artifacts are durable
before ``status.json`` references them.  Nothing here participates in the
kernel guard's decision path.
"""

from __future__ import annotations

import contextlib
import copy
import fcntl
import hashlib
import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from urllib.parse import quote

from . import __version__, paths


SCHEMA = "awa-integrity-status/v1"
HISTORY_MAX = 50

_PROFILES = frozenset({"fast", "deep"})
_TRIGGERS = ("cli", "beforeShell", "stop", "launchd")
_SEVERITIES = frozenset({"green", "degraded", "red"})
_ARTIFACTS = (
    ("history", "json"),
    ("public", "json"),
    ("console", "html"),
    ("outbox", "json"),
)


class StaleGenerationError(RuntimeError):
    """The caller tried to commit a generation older than the current status."""


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("utf-8")


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    written = 0
    while written < len(view):
        count = os.write(fd, view[written:])
        if count <= 0:
            raise OSError("short write made no progress")
        written += count


def _fsync_dir(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    fd = os.open(str(path), flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _ensure_artifact_dir(root: Path, name: str) -> Path:
    child = root / name
    created = not child.exists()
    paths.ensure_dir(child)
    if created:
        _fsync_dir(root)
    return child


def _atomic_replace_bytes(target: Path, data: bytes) -> None:
    """Durably replace one file, then fsync its immediate parent directory."""
    tmp = target.parent / f".{target.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    fd = os.open(
        str(tmp),
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        paths.FILE_MODE,
    )
    try:
        _write_all(fd, data)
        os.fchmod(fd, paths.FILE_MODE)
        os.fsync(fd)
    except BaseException:
        os.close(fd)
        try:
            os.unlink(str(tmp))
        except OSError:
            pass
        raise
    else:
        os.close(fd)

    try:
        os.replace(str(tmp), str(target))
        _fsync_dir(target.parent)
    except BaseException:
        try:
            os.unlink(str(tmp))
        except OSError:
            pass
        raise


@contextlib.contextmanager
def _integrity_lock():
    """Exclusive dedicated lock.  Only ``_commit`` calls this helper."""
    root = paths.ensure_dir(paths.integrity_dir())
    lock_path = root / ".lock"
    fd = os.open(
        str(lock_path),
        os.O_RDWR | os.O_CREAT,
        paths.FILE_MODE,
    )
    try:
        os.fchmod(fd, paths.FILE_MODE)
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _default_trigger() -> dict:
    return {
        "last_attempt": None,
        "last_success": None,
        "last_error": None,
        "generation": 0,
    }


def _prepare_status(
    status: dict,
    previous: dict | None,
    generation: int,
    *,
    profile: str,
    trigger: str,
) -> dict:
    if profile not in _PROFILES:
        raise ValueError(f"invalid integrity profile: {profile}")
    if trigger not in _TRIGGERS:
        raise ValueError(f"invalid integrity trigger: {trigger}")

    overall = status.get("overall")
    if overall not in _SEVERITIES:
        raise ValueError(f"invalid integrity overall severity: {overall}")

    current = copy.deepcopy(status)
    current.pop("artifacts", None)
    current["schema"] = SCHEMA
    current["generation"] = generation
    current["profile"] = profile
    current["trigger"] = trigger
    generated_at = current.get("generated_at")
    if not isinstance(generated_at, str) or not generated_at:
        generated_at = _now_iso()
    current["generated_at"] = generated_at

    release = current.get("release")
    if not isinstance(release, dict):
        release = {}
    current["release"] = {
        "version": str(release.get("version") or __version__),
        "commit": str(
            release.get("commit")
            or os.environ.get("AWA_RELEASE_COMMIT")
            or "unknown"
        ),
    }

    merged_triggers: dict[str, dict] = {}
    previous_triggers = (
        previous.get("triggers", {}) if isinstance(previous, dict) else {}
    )
    supplied_triggers = current.get("triggers", {})
    if not isinstance(previous_triggers, dict):
        previous_triggers = {}
    if not isinstance(supplied_triggers, dict):
        supplied_triggers = {}
    for name in _TRIGGERS:
        entry = _default_trigger()
        old = previous_triggers.get(name)
        supplied = supplied_triggers.get(name)
        if isinstance(old, dict):
            entry.update(old)
        if isinstance(supplied, dict):
            entry.update(supplied)
        merged_triggers[name] = entry

    active = merged_triggers[trigger]
    active["last_attempt"] = active.get("last_attempt") or generated_at
    if active.get("last_error") is None:
        active["last_success"] = active.get("last_success") or generated_at
    active["generation"] = generation
    current["triggers"] = merged_triggers

    previous_overall = previous.get("overall") if isinstance(previous, dict) else None
    if previous_overall != overall:
        transition_id = (
            f"{previous_overall or 'unknown'}->{overall}@{generated_at}#{generation}"
        )
    else:
        transition_id = (
            previous.get("transition_id") if isinstance(previous, dict) else None
        )
    current["transition_id"] = transition_id

    if not isinstance(current.get("invariants"), list):
        current["invariants"] = []
    if not isinstance(current.get("orphans"), dict):
        current["orphans"] = {}
    if not isinstance(current.get("recovery"), dict):
        current["recovery"] = {}
    if not isinstance(current.get("alert"), dict):
        current["alert"] = {}
    return current


def _artifact_payloads(status: dict) -> dict[str, bytes]:
    generation = status["generation"]
    public = {
        "schema": "awa-integrity-public/v1",
        "generation": generation,
        "generated_at": status["generated_at"],
        "overall": status["overall"],
        "invariants": [
            {
                "id": item.get("id"),
                "severity": item.get("severity"),
            }
            for item in status.get("invariants", [])
            if isinstance(item, dict)
        ],
        "orphans": status.get("orphans", {}),
        "recovery": status.get("recovery", {}),
        "fresh_until": status.get("fresh_until"),
    }
    console = (
        "<!doctype html><meta charset=\"utf-8\">"
        "<title>AWA integrity</title>"
        f"<p data-generation=\"{generation}\">{status['overall']}</p>\n"
    ).encode("utf-8")
    outbox = {
        "schema": "awa-integrity-outbox/v1",
        "generation": generation,
        "transition_id": status.get("transition_id"),
        "pending": False,
    }
    return {
        "history": _json_bytes(status),
        "public": _json_bytes(public),
        "console": console,
        "outbox": _json_bytes(outbox),
    }


def _prune_superseded(root: Path, generation: int) -> None:
    if HISTORY_MAX < 1:
        return
    cutoff = generation - HISTORY_MAX
    if cutoff < 1:
        return
    for name, extension in _ARTIFACTS:
        child = root / name
        for candidate in child.glob(f"*.{extension}"):
            try:
                candidate_generation = int(candidate.stem)
            except ValueError:
                continue
            if candidate_generation > cutoff:
                continue
            try:
                os.unlink(str(candidate))
            except FileNotFoundError:
                continue
            _fsync_dir(child)


def _commit(status: dict, *, profile: str, trigger: str) -> int:
    """Publish one evaluation through the status-last commit protocol."""
    if not isinstance(status, dict):
        raise TypeError("integrity status must be a dict")

    root = paths.ensure_dir(paths.integrity_dir())
    with _integrity_lock():
        previous = read_status()
        previous_generation = (
            previous.get("generation", 0) if isinstance(previous, dict) else 0
        )
        if type(previous_generation) is not int or previous_generation < 0:
            previous_generation = 0

        requested_generation = status.get("generation")
        if (
            type(requested_generation) is int
            and requested_generation <= previous_generation
        ):
            raise StaleGenerationError(
                f"generation {requested_generation} is not newer than "
                f"{previous_generation}"
            )

        generation = previous_generation + 1
        current = _prepare_status(
            status,
            previous,
            generation,
            profile=profile,
            trigger=trigger,
        )

        children = {
            name: _ensure_artifact_dir(root, name) for name, _ in _ARTIFACTS
        }
        payloads = _artifact_payloads(current)
        references: dict[str, dict] = {}
        for name, extension in _ARTIFACTS:
            data = payloads[name]
            target = children[name] / f"{generation}.{extension}"
            _atomic_replace_bytes(target, data)
            references[name] = {
                "gen": generation,
                "path": f"{name}/{generation}.{extension}",
                "sha256": hashlib.sha256(data).hexdigest(),
            }

        current["artifacts"] = references
        _atomic_replace_bytes(paths.integrity_status_path(), _json_bytes(current))
        _prune_superseded(root, generation)
        return generation


def _valid_artifact_ref(root: Path, ref: object) -> bool:
    if not isinstance(ref, dict):
        return False
    generation = ref.get("gen")
    relative = ref.get("path")
    expected_hash = ref.get("sha256")
    if type(generation) is not int or generation < 1:
        return False
    if not isinstance(relative, str) or not relative:
        return False
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        return False
    relpath = Path(relative)
    if relpath.is_absolute() or ".." in relpath.parts or len(relpath.parts) != 2:
        return False
    if relpath.parts[0] not in {name for name, _ in _ARTIFACTS}:
        return False
    artifact = root / relpath
    if artifact.is_symlink() or not artifact.is_file():
        return False
    try:
        actual_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
    except OSError:
        return False
    return actual_hash == expected_hash


def read_status() -> dict | None:
    """Read the single authority, rejecting malformed or broken references."""
    status_path = paths.integrity_status_path()
    try:
        raw = status_path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        return None
    generation = value.get("generation")
    if type(generation) is not int or generation < 1:
        return None
    if value.get("overall") not in _SEVERITIES:
        return None
    artifacts = value.get("artifacts")
    if not isinstance(artifacts, dict):
        return None
    expected_names = {name for name, _ in _ARTIFACTS}
    if set(artifacts) != expected_names:
        return None
    root = paths.integrity_dir()
    if not all(_valid_artifact_ref(root, ref) for ref in artifacts.values()):
        return None
    return value


def _ro_conn() -> sqlite3.Connection:
    """Open the live SQLite database read-only, including committed WAL rows."""
    db_path = paths.state_db_path().resolve()
    uri = f"file:{quote(str(db_path), safe='/')}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, isolation_level=None)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        return conn
    except BaseException:
        conn.close()
        raise
