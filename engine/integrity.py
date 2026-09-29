"""AWA integrity evaluator and status-last private store.

The integrity subsystem is observational and engine-side.  Its status file is a
single atomic commit point: generation-tagged derived artifacts are durable
before ``status.json`` references them.  Nothing here participates in the
kernel guard's decision path.
"""

from __future__ import annotations

import contextlib
import copy
import datetime
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import shlex
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import quote

from . import __version__, paths


SCHEMA = "awa-integrity-status/v1"
PUBLIC_SCHEMA = "awa-integrity-public/v1"
OUTBOX_SCHEMA = "awa-integrity-outbox/v1"
RECEIPT_SCHEMA = "awa-integrity-alert-receipt/v1"
HISTORY_MAX = 50
DEEP_BOUND_SECONDS = 24 * 60 * 60

_PROFILES = frozenset({"fast", "deep"})
_TRIGGERS = ("cli", "beforeShell", "stop", "launchd")
_SEVERITIES = frozenset({"green", "degraded", "red"})
_PUBLIC_SEVERITIES = frozenset({"green", "degraded", "red", "unknown"})
_INVARIANT_IDS = frozenset(
    {
        "guard_safety",
        "entry_handshake",
        "recovery",
        "lifecycle",
        "parity",
        "hooks",
        "mcp_engine_parity",
        "release_identity",
        "surveillance_freshness",
        "alert_delivery",
    }
)
_ARTIFACTS = (
    ("history", "json"),
    ("public", "json"),
    ("console", "html"),
    ("outbox", "json"),
)
_ALL_ARTIFACTS = (*_ARTIFACTS, ("receipt", "json"))


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
    """Dedicated lock used only by evaluation and typed receipt commits."""
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


@contextlib.contextmanager
def _alert_dispatch_lock():
    """Serialize current-outbox validation, native dispatch, and receipt CAS."""
    root = paths.ensure_dir(paths.integrity_dir())
    lock_path = root / ".alert-dispatch.lock"
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
    if not isinstance(current.get("worktrees"), dict):
        current["worktrees"] = {}
    if not isinstance(current.get("recovery"), dict):
        current["recovery"] = {}
    if not isinstance(current.get("alert"), dict):
        current["alert"] = {}
    return current


def _safe_count(value: object) -> int:
    return value if type(value) is int and value >= 0 else 0


def _optional_count(value: object) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _safe_timestamp(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    if re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
        value,
    ) is None:
        return None
    return value


def _history_entry(status: dict) -> dict:
    return {
        "generation": _safe_count(status.get("generation")),
        "overall": (
            status.get("overall")
            if status.get("overall") in _SEVERITIES
            else "red"
        ),
        "generated_at": _safe_timestamp(status.get("generated_at")),
    }


def public_projection(status: dict) -> dict:
    """Return the closed, path/secret/raw-evidence-free console projection."""
    if not isinstance(status, dict):
        raise TypeError("integrity status must be a dict")

    invariants = []
    for item in status.get("invariants", []):
        if not isinstance(item, dict):
            continue
        invariant_id = item.get("id")
        severity = item.get("severity")
        if (
            invariant_id not in _INVARIANT_IDS
            or severity not in _PUBLIC_SEVERITIES
        ):
            continue
        invariants.append(
            {
                "id": invariant_id,
                "severity": severity,
                "redacted_reason": f"{invariant_id} is {severity}",
            }
        )

    orphans = status.get("orphans")
    if not isinstance(orphans, dict):
        orphans = {}
    worktrees = status.get("worktrees")
    if not isinstance(worktrees, dict):
        worktrees = {}
    worktree_projection = {
        "checked": False,
        "discovered_linked": _optional_count(
            worktrees.get("discovered_linked")
        ),
        "managed": _optional_count(worktrees.get("managed")),
        "active": _optional_count(worktrees.get("active")),
        "unleased": _optional_count(worktrees.get("unleased")),
        "conflicts": _optional_count(worktrees.get("conflicts")),
        "problems": _optional_count(worktrees.get("problems")),
    }
    worktrees_checked = bool(
        worktrees.get("checked") is True
        and all(
            value is not None
            for key, value in worktree_projection.items()
            if key != "checked"
        )
    )
    worktree_projection["checked"] = worktrees_checked
    if not worktrees_checked:
        # Legacy and fast-only artifacts did not compute this population. Keep
        # every field explicitly unknown rather than turning absence into zero.
        for key in set(worktree_projection) - {"checked"}:
            worktree_projection[key] = None
    recovery = status.get("recovery")
    if not isinstance(recovery, dict):
        recovery = {}
    recovery_status = recovery.get("last_status")
    if recovery_status not in {"ok", "errors", "unknown"}:
        recovery_status = "unknown"

    raw_history = status.get("_recent_history")
    if not isinstance(raw_history, list):
        raw_history = [_history_entry(status)]
    recent_history = []
    seen_generations = set()
    for item in raw_history[-HISTORY_MAX:]:
        if not isinstance(item, dict):
            continue
        generation = _safe_count(item.get("generation"))
        overall = item.get("overall")
        generated_at = _safe_timestamp(item.get("generated_at"))
        if overall not in _SEVERITIES or generation in seen_generations:
            continue
        seen_generations.add(generation)
        recent_history.append(
            {
                "generation": generation,
                "overall": overall,
                "generated_at": generated_at,
            }
        )

    return {
        "schema": PUBLIC_SCHEMA,
        "generation": _safe_count(status.get("generation")),
        "generated_at": _safe_timestamp(status.get("generated_at")),
        "overall": (
            status.get("overall")
            if status.get("overall") in _SEVERITIES
            else "red"
        ),
        "invariants": invariants,
        "orphans": {
            "worktrees": _optional_count(orphans.get("worktrees")),
            "leases_unreconciled": _optional_count(
                orphans.get("leases_unreconciled")
            ),
            "sessions_dangling": _optional_count(
                orphans.get("sessions_dangling")
            ),
            "husks": _optional_count(orphans.get("husks")),
        },
        "worktrees": worktree_projection,
        "recovery": {
            "last_status": recovery_status,
            "needs_repair": _safe_count(recovery.get("needs_repair")),
            "quarantine_count": _safe_count(
                recovery.get("quarantine_count")
            ),
        },
        "recent_history": recent_history,
        "last_checked_age_s": 0,
        "fresh_until": _safe_timestamp(status.get("fresh_until")),
    }


def _previous_public_history(previous: dict | None) -> list[dict]:
    if not isinstance(previous, dict):
        return []
    artifacts = previous.get("artifacts")
    ref = artifacts.get("public") if isinstance(artifacts, dict) else None
    if not _valid_artifact_ref(paths.integrity_dir(), "public", ref):
        return []
    try:
        payload = json.loads(
            (paths.integrity_dir() / ref["path"]).read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    history = payload.get("recent_history") if isinstance(payload, dict) else None
    return copy.deepcopy(history) if isinstance(history, list) else []


def _projection_with_history(
    status: dict,
    previous: dict | None,
) -> dict:
    projectable = copy.deepcopy(status)
    history = _previous_public_history(previous)
    history.append(_history_entry(status))
    projectable["_recent_history"] = history[-HISTORY_MAX:]
    return public_projection(projectable)


def _console_bytes(projection: dict) -> bytes:
    try:
        from . import integrity_console
    except ImportError:
        return (
            "<!doctype html><meta charset=\"utf-8\">"
            "<title>AWA integrity</title>"
            f"<p data-generation=\"{projection['generation']}\">"
            f"{projection['overall']}</p>\n"
        ).encode("utf-8")
    return integrity_console.render(projection).encode("utf-8")


def _worsened(previous: dict | None, current: dict) -> bool:
    rank = {"green": 0, "degraded": 1, "red": 2}
    current_rank = rank.get(current.get("overall"))
    if current_rank is None:
        return False
    previous_rank = (
        rank.get(previous.get("overall"))
        if isinstance(previous, dict)
        else None
    )
    if previous_rank is None:
        return current_rank > 0
    return current_rank > previous_rank


def _referenced_outbox(status: object) -> dict | None:
    if not isinstance(status, dict):
        return None
    artifacts = status.get("artifacts")
    ref = artifacts.get("outbox") if isinstance(artifacts, dict) else None
    root = paths.integrity_dir()
    if not _valid_artifact_ref(root, "outbox", ref):
        return None
    try:
        outbox = json.loads((root / ref["path"]).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if (
        not isinstance(outbox, dict)
        or outbox.get("schema") != OUTBOX_SCHEMA
        or outbox.get("generation") != ref.get("gen")
        or type(outbox.get("pending")) is not bool
        or not isinstance(outbox.get("transition_id"), str)
        or outbox.get("transition_id") != status.get("transition_id")
        or outbox.get("previous_overall")
        not in {*_SEVERITIES, "unknown"}
        or outbox.get("current_overall") not in _SEVERITIES
    ):
        return None
    return outbox


def _referenced_receipt(status: object) -> dict | None:
    if not isinstance(status, dict):
        return None
    artifacts = status.get("artifacts")
    ref = artifacts.get("receipt") if isinstance(artifacts, dict) else None
    root = paths.integrity_dir()
    if not _valid_artifact_ref(root, "receipt", ref):
        return None
    try:
        receipt = json.loads((root / ref["path"]).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    outcomes = receipt.get("outcomes") if isinstance(receipt, dict) else None
    if (
        not isinstance(receipt, dict)
        or receipt.get("schema") != RECEIPT_SCHEMA
        or receipt.get("generation") != ref.get("gen")
        or receipt.get("transition_id") != status.get("transition_id")
        or not isinstance(outcomes, dict)
        or outcomes.get("native") not in {"accepted", "failed"}
        or outcomes.get("slack") not in {
            "accepted",
            "failed",
            "opted_out",
        }
    ):
        return None
    return receipt


def _transition_delivery(status: object, transition_id: str) -> dict | None:
    if not isinstance(status, dict):
        return None
    alert = status.get("alert")
    delivered = alert.get("delivered") if isinstance(alert, dict) else None
    receipt = _referenced_receipt(status)
    if (
        not isinstance(alert, dict)
        or alert.get("last_transition") != transition_id
        or not isinstance(delivered, dict)
        or not isinstance(receipt, dict)
        or receipt.get("transition_id") != transition_id
        or receipt.get("outcomes") != delivered
        or delivered.get("native") not in {"accepted", "failed"}
        or delivered.get("slack") not in {
            "accepted",
            "failed",
            "opted_out",
        }
    ):
        return None
    return {
        "native": delivered["native"],
        "slack": delivered["slack"],
    }


def _pending_outbox(status: object) -> dict | None:
    outbox = _referenced_outbox(status)
    if not isinstance(outbox, dict) or outbox.get("pending") is not True:
        return None
    delivered = _transition_delivery(status, outbox["transition_id"])
    if isinstance(delivered, dict) and any(
        delivered.get(channel) == "accepted"
        for channel in ("native", "slack")
    ):
        return None
    return outbox


def _artifact_payloads(
    status: dict,
    *,
    previous: dict | None,
) -> dict[str, bytes]:
    generation = status["generation"]
    public = _projection_with_history(status, previous)
    prior_pending = _pending_outbox(previous)
    carry_pending = bool(
        isinstance(prior_pending, dict)
        and prior_pending.get("transition_id") == status.get("transition_id")
    )
    pending = _worsened(previous, status) or carry_pending
    previous_overall = (
        prior_pending.get("previous_overall")
        if carry_pending
        else (
            previous.get("overall")
            if isinstance(previous, dict)
            else "unknown"
        )
    )
    current_overall = (
        prior_pending.get("current_overall")
        if carry_pending
        else status.get("overall")
    )
    outbox = {
        "schema": OUTBOX_SCHEMA,
        "generation": generation,
        "transition_id": status.get("transition_id"),
        "previous_overall": previous_overall,
        "current_overall": current_overall,
        "pending": pending,
    }
    return {
        "history": _json_bytes(status),
        "public": _json_bytes(public),
        "console": _console_bytes(public),
        "outbox": _json_bytes(outbox),
    }


def _prune_superseded(
    root: Path,
    generation: int,
    artifacts: dict | None = None,
) -> None:
    if HISTORY_MAX < 1:
        return
    cutoff = generation - HISTORY_MAX
    if cutoff < 1:
        return
    referenced_paths = (
        {
            ref.get("path")
            for ref in artifacts.values()
            if isinstance(ref, dict)
            and isinstance(ref.get("path"), str)
        }
        if isinstance(artifacts, dict)
        else set()
    )
    for name, extension in _ALL_ARTIFACTS:
        child = root / name
        for candidate in child.glob(f"*.{extension}"):
            if f"{name}/{candidate.name}" in referenced_paths:
                continue
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

    dispatch_enabled = status.get("schema") == SCHEMA
    root = paths.ensure_dir(paths.integrity_dir())
    dispatch_context = (
        _alert_dispatch_lock()
        if dispatch_enabled
        else contextlib.nullcontext()
    )
    with dispatch_context:
        with _integrity_lock():
            previous = read_status()
            previous_pending = _pending_outbox(previous)
            previous_generation = (
                previous.get("generation", 0)
                if isinstance(previous, dict)
                else 0
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
            prior_delivery = _transition_delivery(
                previous,
                current.get("transition_id"),
            )
            if isinstance(prior_delivery, dict):
                current_alert = current.get("alert")
                if not isinstance(current_alert, dict):
                    current_alert = {}
                    current["alert"] = current_alert
                previous_alert = previous.get("alert")
                current_alert["last_transition"] = current["transition_id"]
                current_alert["delivered"] = prior_delivery
                current_alert["attempted"] = copy.deepcopy(
                    previous_alert.get("attempted", [])
                    if isinstance(previous_alert, dict)
                    else []
                )

            children = {
                name: _ensure_artifact_dir(root, name)
                for name, _ in _ARTIFACTS
            }
            payloads = _artifact_payloads(current, previous=previous)
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
            if isinstance(prior_delivery, dict):
                previous_artifacts = previous.get("artifacts")
                previous_receipt = (
                    previous_artifacts.get("receipt")
                    if isinstance(previous_artifacts, dict)
                    else None
                )
                if _valid_artifact_ref(
                    root,
                    "receipt",
                    previous_receipt,
                ):
                    references["receipt"] = copy.deepcopy(previous_receipt)

            current["artifacts"] = references
            _atomic_replace_bytes(
                paths.integrity_status_path(),
                _json_bytes(current),
            )
            _prune_superseded(root, generation, current["artifacts"])

        if dispatch_enabled:
            if (
                isinstance(previous_pending, dict)
                and previous_pending.get("transition_id")
                != current.get("transition_id")
            ):
                _audit_stale_dispatch(
                    root,
                    previous_generation,
                    previous_pending["transition_id"],
                    current,
                )
            from . import integrity_alert

            _drain_pending_alert_locked(
                generation,
                current.get("transition_id"),
                native=integrity_alert._native,
            )
    return generation


def _valid_artifact_ref(root: Path, name: str, ref: object) -> bool:
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
    extensions = dict(_ALL_ARTIFACTS)
    if name not in extensions or relpath.parts[0] != name:
        return False
    if relpath.name != f"{generation}.{extensions[name]}":
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
    allowed_names = {name for name, _ in _ALL_ARTIFACTS}
    if not expected_names.issubset(artifacts) or not set(artifacts).issubset(
        allowed_names
    ):
        return None
    root = paths.integrity_dir()
    if not all(
        _valid_artifact_ref(root, name, ref)
        for name, ref in artifacts.items()
    ):
        return None
    return value


def _normalize_alert_outcomes(outcomes: object) -> dict[str, str]:
    if not isinstance(outcomes, dict):
        raise TypeError("alert outcomes must be a dict")
    native = outcomes.get("native")
    slack = outcomes.get("slack")
    if native not in {"accepted", "failed"}:
        raise ValueError("native outcome must be accepted or failed")
    if slack not in {"accepted", "failed", "opted_out"}:
        raise ValueError(
            "slack outcome must be accepted, failed, or opted_out"
        )
    return {"native": native, "slack": slack}


def _receipt_already_committed(
    current: dict,
    expected_generation: int,
    transition_id: str,
    outcomes: dict[str, str],
) -> bool:
    if current.get("transition_id") != transition_id:
        return False
    generation = current.get("generation")
    if type(generation) is not int or generation <= expected_generation:
        return False
    return _transition_delivery(current, transition_id) == outcomes


def _audit_stale_receipt(
    root: Path,
    expected_generation: int,
    transition_id: str,
    outcomes: dict[str, str],
    current: dict | None,
) -> None:
    receipt_dir = _ensure_artifact_dir(root, "receipt")
    transition_hash = hashlib.sha256(
        transition_id.encode("utf-8")
    ).hexdigest()
    target = (
        receipt_dir
        / f"stale-{expected_generation}-{transition_hash[:16]}.json"
    )
    payload = _json_bytes(
        {
            "schema": "awa-integrity-alert-receipt-audit/v1",
            "result": "stale",
            "expected_generation": expected_generation,
            "current_generation": (
                current.get("generation")
                if isinstance(current, dict)
                else None
            ),
            "transition_sha256": transition_hash,
            "outcomes": outcomes,
        }
    )
    if target.exists():
        try:
            if target.read_bytes() == payload:
                return
        except OSError:
            pass
        raise RuntimeError("stale receipt audit collision")
    _atomic_replace_bytes(target, payload)


def _audit_stale_dispatch(
    root: Path,
    expected_generation: int,
    transition_id: str,
    current: dict | None,
) -> None:
    receipt_dir = _ensure_artifact_dir(root, "receipt")
    transition_hash = hashlib.sha256(
        transition_id.encode("utf-8")
    ).hexdigest()
    current_generation = (
        current.get("generation")
        if isinstance(current, dict)
        and type(current.get("generation")) is int
        else 0
    )
    target = (
        receipt_dir
        / (
            f"stale-dispatch-{expected_generation}-{current_generation}-"
            f"{transition_hash[:16]}.json"
        )
    )
    payload = _json_bytes(
        {
            "schema": "awa-integrity-alert-dispatch-audit/v1",
            "result": "stale",
            "expected_generation": expected_generation,
            "current_generation": current_generation or None,
            "transition_sha256": transition_hash,
        }
    )
    if target.exists():
        try:
            if target.read_bytes() == payload:
                return
        except OSError:
            pass
        raise RuntimeError("stale dispatch audit collision")
    _atomic_replace_bytes(target, payload)


def _drain_pending_alert_locked(
    expected_generation: int,
    transition_id: str | None,
    *,
    native,
) -> int | None:
    """Drain only the authoritative current transition while dispatch-locked."""
    root = paths.ensure_dir(paths.integrity_dir())
    current = read_status()
    if (
        not isinstance(current, dict)
        or current.get("generation") != expected_generation
        or current.get("transition_id") != transition_id
    ):
        if isinstance(transition_id, str) and transition_id:
            _audit_stale_dispatch(
                root,
                expected_generation,
                transition_id,
                current,
            )
        return None

    outbox = _pending_outbox(current)
    if (
        not isinstance(outbox, dict)
        or outbox.get("transition_id") != transition_id
    ):
        return None

    from . import integrity_alert

    previous = {"overall": outbox.get("previous_overall") or "unknown"}
    dispatch_status = copy.deepcopy(current)
    if outbox.get("current_overall") in _SEVERITIES:
        dispatch_status["overall"] = outbox["current_overall"]
    try:
        outcomes = integrity_alert.dispatch(
            previous,
            dispatch_status,
            native=native,
            slack=None,
            pending=True,
        )
    except Exception:  # Ordinary notifier faults remain retryable and visible.
        outcomes = {"native": "failed", "slack": "opted_out"}
    if outcomes is None:
        return None
    return commit_alert_receipt(
        expected_generation,
        transition_id,
        outcomes,
    )


def drain_pending_alert(
    expected_generation: int,
    transition_id: str,
    *,
    native=None,
) -> int | None:
    """Serialize and retry one current pending transition, never a stale one."""
    if type(expected_generation) is not int or expected_generation < 1:
        raise ValueError("expected generation must be a positive integer")
    if not isinstance(transition_id, str) or not transition_id:
        raise ValueError("transition id is required")
    if native is None:
        from . import integrity_alert

        native = integrity_alert._native
    with _alert_dispatch_lock():
        return _drain_pending_alert_locked(
            expected_generation,
            transition_id,
            native=native,
        )


def _remove_unreferenced_generation_target(
    root: Path,
    current: dict,
    name: str,
    generation: int,
) -> None:
    extension = dict(_ALL_ARTIFACTS)[name]
    relative = f"{name}/{generation}.{extension}"
    artifacts = current.get("artifacts")
    if isinstance(artifacts, dict) and any(
        isinstance(ref, dict) and ref.get("path") == relative
        for ref in artifacts.values()
    ):
        raise RuntimeError("refusing to replace a referenced integrity artifact")
    target = root / relative
    try:
        os.unlink(str(target))
    except FileNotFoundError:
        return
    _fsync_dir(target.parent)


def _receipt_attempt(
    alert: dict,
    transition_id: str,
    outcomes: dict[str, str],
) -> None:
    attempted = alert.get("attempted")
    if not isinstance(attempted, list):
        attempted = []
        alert["attempted"] = attempted
    if not any(
        item == transition_id
        or (
            isinstance(item, dict)
            and item.get("transition_id") == transition_id
        )
        for item in attempted
    ):
        attempted.append(
            {
                "transition_id": transition_id,
                "channels": [
                    name
                    for name, result in outcomes.items()
                    if result != "opted_out"
                ],
            }
        )


def _apply_alert_delivery_severity(
    status: dict,
    outcomes: dict[str, str],
) -> None:
    configured = [outcomes["native"]]
    if outcomes["slack"] != "opted_out":
        configured.append(outcomes["slack"])
    failed = all(result == "failed" for result in configured)
    severity = "red" if failed else "green"
    evidence = (
        "all configured alert paths failed"
        if failed
        else "at least one configured alert path accepted"
    )
    if failed and status.get("overall") != "green":
        status["overall"] = "red"
    elif not failed:
        outbox = _referenced_outbox(status)
        if (
            isinstance(outbox, dict)
            and outbox.get("current_overall") in _SEVERITIES
        ):
            status["overall"] = outbox["current_overall"]
    invariants = status.get("invariants")
    if not isinstance(invariants, list):
        invariants = []
        status["invariants"] = invariants
    for item in invariants:
        if isinstance(item, dict) and item.get("id") == "alert_delivery":
            item["severity"] = severity
            item["evidence"] = evidence
            return
    invariants.append(
        {
            "id": "alert_delivery",
            "severity": severity,
            "evidence": evidence,
            "checked_at": status.get("generated_at"),
            "profile": status.get("profile"),
        }
    )


def commit_alert_receipt(
    expected_generation: int,
    transition_id: str,
    outcomes: dict,
) -> int | None:
    """CAS-persist alert delivery without re-evaluation or another outbox."""
    if type(expected_generation) is not int or expected_generation < 1:
        raise ValueError("expected generation must be a positive integer")
    if not isinstance(transition_id, str) or not transition_id:
        raise ValueError("transition id is required")
    normalized = _normalize_alert_outcomes(outcomes)
    root = paths.ensure_dir(paths.integrity_dir())

    with _integrity_lock():
        current = read_status()
        if isinstance(current, dict) and _receipt_already_committed(
            current,
            expected_generation,
            transition_id,
            normalized,
        ):
            return None
        if (
            not isinstance(current, dict)
            or current.get("generation") != expected_generation
            or current.get("transition_id") != transition_id
        ):
            _audit_stale_receipt(
                root,
                expected_generation,
                transition_id,
                normalized,
                current,
            )
            return None

        generation = expected_generation + 1
        updated = copy.deepcopy(current)
        updated["generation"] = generation
        updated["generated_at"] = _now_iso()
        updated["transition_id"] = transition_id
        alert = updated.get("alert")
        if not isinstance(alert, dict):
            alert = {}
            updated["alert"] = alert
        _receipt_attempt(alert, transition_id, normalized)
        alert["last_transition"] = transition_id
        alert["delivered"] = normalized
        _apply_alert_delivery_severity(updated, normalized)

        for name in ("receipt", "public", "console"):
            _remove_unreferenced_generation_target(
                root,
                current,
                name,
                generation,
            )

        public = _projection_with_history(updated, current)
        payloads = {
            "receipt": _json_bytes(
                {
                    "schema": RECEIPT_SCHEMA,
                    "generation": generation,
                    "expected_generation": expected_generation,
                    "transition_id": transition_id,
                    "outcomes": normalized,
                }
            ),
            "public": _json_bytes(public),
            "console": _console_bytes(public),
        }
        references = copy.deepcopy(current["artifacts"])
        for name in ("receipt", "public", "console"):
            extension = dict(_ALL_ARTIFACTS)[name]
            child = _ensure_artifact_dir(root, name)
            data = payloads[name]
            target = child / f"{generation}.{extension}"
            _atomic_replace_bytes(target, data)
            references[name] = {
                "gen": generation,
                "path": f"{name}/{generation}.{extension}",
                "sha256": hashlib.sha256(data).hexdigest(),
            }

        updated["artifacts"] = references
        _atomic_replace_bytes(
            paths.integrity_status_path(),
            _json_bytes(updated),
        )
        _prune_superseded(root, generation, updated["artifacts"])
        return generation


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


@dataclass(frozen=True)
class Facts:
    """Complete, injectable observation bundle for the ten invariant checks."""

    guard_primary_deny: bool | None
    guard_cd_bypass_deny: bool | None
    guard_linked_allow: bool | None
    parity_ok: bool | None
    hook_rows_present: bool | None
    hook_fail_open: bool | None
    mcp_matches: bool | None
    release_matches: bool | None
    recovery_last_status: str | None
    needs_repair: int | None
    leases_unreconciled: int | None
    sessions_dangling: int | None
    husks: int | None
    disposition_map: dict[str, str] | None
    handoff_state: str | None
    launchd_last_success_age_s: float | None
    delivered: dict[str, str] | None
    native_entry_state: str | None = "absent"
    worktree_counts: dict[str, int] | None = None


def _check_guard(facts: Facts) -> tuple[str, str]:
    values = (
        facts.guard_primary_deny,
        facts.guard_cd_bypass_deny,
        facts.guard_linked_allow,
    )
    if any(value is None for value in values):
        return "unknown", "guard probe incomplete"
    if all(value is True for value in values):
        return "green", "primary denies and linked workspace allows"
    return "red", "guard safety probe disagreed"


def _check_parity(facts: Facts) -> tuple[str, str]:
    if facts.parity_ok is None:
        return "unknown", "kernel parity unavailable"
    if facts.parity_ok:
        return "green", "kernel and engine classifications agree"
    return "red", "kernel and engine classifications disagree"


def _check_hooks(facts: Facts) -> tuple[str, str]:
    if facts.hook_rows_present is None or facts.hook_fail_open is None:
        return "unknown", "hook configuration unavailable"
    if facts.hook_rows_present and facts.hook_fail_open:
        return "green", "required hook rows are present and fail open"
    if not facts.hook_rows_present:
        return "degraded", "required hook row missing"
    return "degraded", "blocking hook is fail closed"


def _check_mcp(facts: Facts) -> tuple[str, str]:
    if facts.mcp_matches is None:
        return "unknown", "MCP adapter comparison unavailable"
    if facts.mcp_matches:
        return "green", "MCP and engine guard decisions agree"
    return "red", "MCP and engine guard decisions disagree"


def _check_release(facts: Facts) -> tuple[str, str]:
    if facts.release_matches is None:
        return "unknown", "release identity unavailable"
    if facts.release_matches:
        return "green", "release pointer and source identity agree"
    return "degraded", "release pointer and source identity differ"


def _check_recovery(facts: Facts) -> tuple[str, str]:
    if (
        not isinstance(facts.recovery_last_status, str)
        or type(facts.needs_repair) is not int
        or facts.needs_repair < 0
    ):
        return "unknown", "recovery status unavailable"
    if facts.recovery_last_status == "ok" and facts.needs_repair == 0:
        return "green", "recovery scan is clean"
    return "degraded", "recovery scan needs attention"


def _check_lifecycle(facts: Facts) -> tuple[str, str]:
    worktree_counts = facts.worktree_counts
    if worktree_counts is not None:
        required_counts = (
            "discovered_linked",
            "managed",
            "active",
            "unleased",
            "conflicts",
            "problems",
        )
        if (
            not isinstance(worktree_counts, dict)
            or any(
                type(worktree_counts.get(key)) is not int
                or worktree_counts[key] < 0
                for key in required_counts
            )
        ):
            return "unknown", "worktree populations unavailable"
        if (
            worktree_counts["unleased"] > 0
            or worktree_counts["conflicts"] > 0
            or worktree_counts["problems"] > 0
        ):
            return "degraded", (
                "worktree lifecycle needs attention "
                f"(unleased={worktree_counts['unleased']}, "
                f"conflicts={worktree_counts['conflicts']}, "
                f"problems={worktree_counts['problems']})"
            )
    counts = (
        facts.leases_unreconciled,
        facts.sessions_dangling,
        facts.husks,
    )
    if (
        any(type(value) is not int or value < 0 for value in counts)
        or not isinstance(facts.disposition_map, dict)
    ):
        return "unknown", "lifecycle topology unavailable"
    problematic = any(
        value not in {"active"} for value in facts.disposition_map.values()
    )
    if any(value > 0 for value in counts) or problematic:
        return "degraded", (
            "lifecycle counts require reconciliation "
            f"(leases={facts.leases_unreconciled}, "
            f"sessions={facts.sessions_dangling}, husks={facts.husks})"
        )
    return "green", "lifecycle topology is reconciled"


def _check_entry(facts: Facts) -> tuple[str, str]:
    if facts.native_entry_state == "eager":
        return "green", "eager session-start entry evidence validated"
    if facts.native_entry_state == "recovered":
        return "green", "first-prompt recovery evidence validated"
    if facts.native_entry_state == "legacy":
        return "green", "legacy v1 entry evidence validated; source unknown"
    if facts.native_entry_state == "success":
        return "green", "native entry evidence validated"
    if facts.handoff_state == "closed":
        return "green", "ensure handoff evidence validated"
    if facts.native_entry_state == "conflict":
        return "degraded", "native entry evidence conflict"
    if facts.native_entry_state == "mismatched":
        return "degraded", "native entry evidence mismatched"
    if facts.native_entry_state == "failed":
        return "degraded", "native entry registration failed"
    if facts.native_entry_state == "pending":
        return "degraded", "native entry registration pending"
    if facts.native_entry_state == "stale":
        return "degraded", "native entry evidence stale"
    if facts.handoff_state == "pending":
        return "degraded", "ensure handoff evidence pending"
    if facts.handoff_state in {"stale", "mismatched"}:
        return "degraded", "ensure handoff evidence stale"
    if facts.handoff_state == "conflict":
        return "degraded", "ensure handoff evidence conflict"
    if facts.handoff_state == "unknown" or facts.native_entry_state == "unknown":
        return "unknown", "entry evidence unknown"
    return "unknown", "entry evidence absent"


def _check_freshness(facts: Facts) -> tuple[str, str]:
    age = facts.launchd_last_success_age_s
    if not isinstance(age, (int, float)) or isinstance(age, bool) or age < 0:
        return "red", "required deep sweep is missing"
    if age > DEEP_BOUND_SECONDS:
        return "red", "required deep sweep is stale"
    return "green", "required deep sweep is fresh"


def _check_alert(facts: Facts, *, non_green: bool = True) -> tuple[str, str]:
    if not non_green:
        return "green", "no non-green status requires alert delivery"
    delivered = facts.delivered
    if not isinstance(delivered, dict):
        return "unknown", "alert delivery result unavailable"
    native = delivered.get("native")
    slack = delivered.get("slack")
    # The status schema requires explicit ``opted_out``; absence is malformed.
    configured = [native]
    if slack != "opted_out":
        configured.append(slack)
    if not configured or any(
        value not in {"accepted", "failed"} for value in configured
    ):
        return "unknown", "alert delivery result incomplete"
    if all(value == "failed" for value in configured):
        return "red", "all configured alert paths failed"
    return "green", "at least one configured alert path accepted"


REGISTRY = {
    "guard_safety": (
        _check_guard,
        True,
        True,
        frozenset({"fast", "deep"}),
    ),
    "entry_handshake": (
        _check_entry,
        True,
        False,
        frozenset({"fast", "deep"}),
    ),
    "recovery": (
        _check_recovery,
        True,
        False,
        frozenset({"deep"}),
    ),
    "lifecycle": (
        _check_lifecycle,
        True,
        False,
        frozenset({"deep"}),
    ),
    "parity": (
        _check_parity,
        True,
        True,
        frozenset({"deep"}),
    ),
    "hooks": (
        _check_hooks,
        True,
        False,
        frozenset({"fast", "deep"}),
    ),
    "mcp_engine_parity": (
        _check_mcp,
        True,
        False,
        frozenset({"deep"}),
    ),
    "release_identity": (
        _check_release,
        True,
        False,
        frozenset({"deep"}),
    ),
    "surveillance_freshness": (
        _check_freshness,
        True,
        False,
        frozenset({"fast", "deep"}),
    ),
    "alert_delivery": (
        _check_alert,
        True,
        False,
        frozenset({"fast", "deep"}),
    ),
}


def _parse_iso(value: object) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=datetime.timezone.utc)
        return parsed.timestamp()
    except (ValueError, OverflowError):
        return None


def _iso_at(epoch: float) -> str:
    return datetime.datetime.fromtimestamp(
        epoch, tz=datetime.timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%SZ")


def _launchd_is_fresh(triggers: object, *, now: float | None = None) -> bool:
    if not isinstance(triggers, dict):
        return False
    launchd = triggers.get("launchd")
    if not isinstance(launchd, dict):
        return False
    last_success = _parse_iso(launchd.get("last_success"))
    if last_success is None:
        return False
    now_epoch = time.time() if now is None else now
    age = now_epoch - last_success
    return 0 <= age <= DEEP_BOUND_SECONDS


def _reduce_required_invariants(
    invariants: list[dict],
) -> tuple[str, str | None]:
    by_id = {
        item.get("id"): item
        for item in invariants
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    degraded_driver = None
    for invariant_id, (_, required, safety_critical, _) in REGISTRY.items():
        if not required:
            continue
        item = by_id.get(invariant_id)
        severity = item.get("severity") if isinstance(item, dict) else "unknown"
        if severity == "red":
            return "red", invariant_id
        if safety_critical and severity == "unknown":
            return "red", invariant_id
        if severity != "green" and degraded_driver is None:
            degraded_driver = invariant_id
    if degraded_driver is not None:
        return "degraded", degraded_driver
    return "green", None


def reduction_driver(invariants: list[dict], overall: str) -> str | None:
    """Return the visible invariant that deterministically drove overall."""
    required_ids = {
        invariant_id
        for invariant_id, (_, required, _safety, _profiles)
        in REGISTRY.items()
        if required
    }
    visible_ids = {
        item.get("id")
        for item in invariants
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    if not required_ids.issubset(visible_ids):
        return None
    invariant_overall, driver = _reduce_required_invariants(invariants)
    return driver if invariant_overall == overall else None


def reduce(invariants: list[dict], triggers: dict) -> str:
    """Reduce required invariant severities and deep-trigger freshness."""
    invariant_overall, _driver = _reduce_required_invariants(invariants)
    if invariant_overall == "red":
        return "red"
    if not _launchd_is_fresh(triggers):
        return "red"
    return invariant_overall


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _release_pointer() -> dict | None:
    pointer = paths.data_home() / "awa" / "release-pointer.json"
    try:
        value = json.loads(pointer.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _source_root() -> Path:
    pointer = _release_pointer()
    if pointer is not None:
        for key in ("runtime", "source"):
            value = pointer.get(key)
            if isinstance(value, str) and value:
                candidate = Path(value).expanduser()
                if candidate.is_dir():
                    return candidate.resolve()
    return _repo_root()


def _policy_path(source: Path) -> Path:
    configured = os.environ.get("AWA_POLICY", "").strip()
    if configured:
        return Path(configured).expanduser()
    return source / "kernel" / "policy" / "default-worktree-policy.yml"


def _worktree_paths(source: Path) -> list[Path]:
    env = os.environ.copy()
    env["GIT_OPTIONAL_LOCKS"] = "0"
    env["GIT_NO_LAZY_FETCH"] = "1"
    try:
        proc = subprocess.run(
            ["git", "-C", str(source), "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []
    result = []
    for line in proc.stdout.splitlines():
        if line.startswith("worktree "):
            candidate = Path(line[len("worktree ") :])
            if candidate.exists():
                result.append(candidate.resolve())
    return result


def _probe_worktree_paths(source: Path) -> list[Path]:
    """Resolve Git topology separately from the installed runtime code root.

    Installed releases intentionally execute from a non-Git runtime directory,
    while the release ``source`` checkout may be detached or have only one
    worktree. External hosts can therefore name one stable, policy-governed
    repository whose primary/linked topology is safe to probe. An explicit
    invalid or single-worktree target stays unavailable rather than silently
    falling back and fabricating coverage.
    """
    configured = os.environ.get("AWA_INTEGRITY_PROBE_REPO", "").strip()
    if configured:
        return _worktree_paths(Path(configured).expanduser())
    return _worktree_paths(source)


def _guard_probes(
    source: Path,
) -> tuple[bool | None, bool | None, bool | None, list[tuple[Path, str]]]:
    from . import guard

    worktrees = _probe_worktree_paths(source)
    if not worktrees:
        return None, None, None, []
    primary = worktrees[0]
    linked = next((path for path in worktrees[1:] if path != primary), None)
    policy = _policy_path(source)
    if linked is None or not policy.is_file():
        return None, None, None, []
    probes = [
        (primary, "git commit -am integrity-probe"),
        (
            primary,
            f"cd {shlex.quote(str(linked))} && git commit -am integrity-probe",
        ),
        (linked, "git commit -am integrity-probe"),
    ]
    try:
        decisions = [
            guard.decide_shell(str(cwd), command, str(policy))
            for cwd, command in probes
        ]
    except Exception:  # noqa: BLE001 — an unavailable probe is UNKNOWN.
        return None, None, None, probes
    return (
        decisions[0].permission == "deny",
        decisions[1].permission == "deny",
        decisions[2].permission == "allow",
        probes,
    )


def _kernel_parity(source: Path, probes: list[tuple[Path, str]]) -> bool | None:
    if not probes:
        return None
    from . import guard

    hook = source / "kernel" / "hooks" / "worktree-guard.sh"
    policy = _policy_path(source)
    if not hook.is_file() or not policy.is_file():
        return None
    try:
        with tempfile.TemporaryDirectory(prefix="awa-integrity-parity.") as tmp:
            env = os.environ.copy()
            env["AWA_POLICY"] = str(policy)
            env["XDG_STATE_HOME"] = str(Path(tmp) / "state")
            for name in (
                "CURSOR_BACKGROUND_AGENT",
                "CURSOR_CLOUD_AGENT",
                "IS_BACKGROUND_AGENT",
                "is_background_agent",
                "AWA_FORCE_CLOUD",
                "cloud_agent_identity_broker",
                "CURSOR_AGENT_IDENTITY_BROKER",
            ):
                env.pop(name, None)
            for cwd, command in probes:
                direct = guard.decide_shell(str(cwd), command, str(policy))
                proc = subprocess.run(
                    ["bash", str(hook)],
                    input=json.dumps({"cwd": str(cwd), "command": command}),
                    capture_output=True,
                    text=True,
                    timeout=20,
                    env=env,
                )
                if proc.returncode != 0:
                    return False
                mirrored = json.loads(proc.stdout)
                if mirrored.get("permission") != direct.permission:
                    return False
        return True
    except (
        OSError,
        subprocess.SubprocessError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):
        return None


def _mcp_parity(source: Path, probes: list[tuple[Path, str]]) -> bool | None:
    if not probes:
        return None
    from . import guard, mcp_server

    policy = _policy_path(source)
    if not policy.is_file():
        return None
    previous_policy = os.environ.get("AWA_POLICY")
    os.environ["AWA_POLICY"] = str(policy)
    try:
        for cwd, command in probes:
            direct = guard.decide_shell(str(cwd), command, str(policy))
            adapted = mcp_server._tool_guard_shell(  # noqa: SLF001 — product adapter.
                {"cwd": str(cwd), "command": command}
            )
            if (
                adapted.get("permission") != direct.permission
                or adapted.get("classification") != direct.classification
            ):
                return False
        return True
    except Exception:  # noqa: BLE001 — an unavailable adapter is UNKNOWN.
        return None
    finally:
        if previous_policy is None:
            os.environ.pop("AWA_POLICY", None)
        else:
            os.environ["AWA_POLICY"] = previous_policy


_V1_HOOK_LAYOUT = (
    (
        "worktree.session-context",
        "sessionStart",
        "kernel/hooks/worktree-session.sh",
        "host-policy-delegator",
        {"type": "command", "timeout": 5, "failClosed": False},
        None,
    ),
    (
        "worktree.shell-guard",
        "beforeShellExecution",
        "kernel/hooks/worktree-guard.sh",
        "host-policy-delegator",
        {"type": "command", "timeout": 20, "failClosed": False},
        None,
    ),
    (
        "worktree.file-observer",
        "afterFileEdit",
        "kernel/hooks/worktree-guard.sh",
        "host-policy-delegator",
        {"type": "command", "timeout": 20},
        None,
    ),
    (
        "recovery.maintenance",
        "sessionStart",
        "kernel/hooks/awa-recovery-maintenance.sh",
        "installed-awa",
        {"type": "command", "timeout": 5, "failClosed": False},
        None,
    ),
    (
        "finish.prompt-recall",
        "beforeSubmitPrompt",
        "kernel/hooks/before-submit-prompt.sh",
        "installed-awa",
        {
            "type": "command",
            "matcher": "UserPromptSubmit",
            "timeout": 20,
            "failClosed": False,
        },
        None,
    ),
)
_V2_HOOK_LAYOUT = (
    (
        "worktree.shell-guard-composite",
        "beforeShellExecution",
        "kernel/hooks/worktree-guard-with-integrity.sh",
        "host-policy-delegator",
        {"type": "command", "timeout": 20, "failClosed": False},
        None,
    ),
    (
        "worktree.stop-observer",
        "stop",
        "kernel/hooks/awa-integrity-observer.sh",
        "host-policy-delegator",
        {"type": "command", "timeout": 5, "failClosed": False},
        None,
    ),
    (
        "worktree.session-handoff",
        "sessionStart",
        "kernel/hooks/awa-session-handoff.sh",
        "host-policy-delegator",
        {"type": "command", "timeout": 5, "failClosed": False},
        "M2.4",
    ),
)
_V3_HOOK_LAYOUT = (
    (
        "finish.prompt-recall-with-entry",
        "beforeSubmitPrompt",
        "kernel/hooks/before-submit-prompt-with-entry.sh",
        "host-policy-delegator",
        {
            "type": "command",
            "matcher": "UserPromptSubmit",
            "timeout": 20,
            "failClosed": False,
        },
        None,
    ),
)
_V4_HOOK_LAYOUT = (
    (
        "registration.tool-admission",
        "preToolUse",
        "kernel/hooks/awa-registration-admission.sh",
        "host-policy-delegator",
        {
            "type": "command",
            "matcher": "*",
            "timeout": 20,
            "failClosed": False,
        },
        None,
    ),
    (
        "registration.subagent-admission",
        "subagentStart",
        "kernel/hooks/awa-registration-admission.sh",
        "host-policy-delegator",
        {
            "type": "command",
            "matcher": "*",
            "timeout": 20,
            "failClosed": False,
        },
        None,
    ),
    (
        "registration.startup-reconcile",
        "sessionStart",
        "kernel/hooks/awa-registration-startup.sh",
        "host-policy-delegator",
        {"type": "command", "timeout": 5, "failClosed": False},
        None,
    ),
)


def _roles_match_layout(roles: object, layout: tuple) -> bool:
    if not isinstance(roles, list) or len(roles) != len(layout):
        return False
    for role, expected in zip(roles, layout):
        if not isinstance(role, dict):
            return False
        observed = (
            role.get("id"),
            role.get("event"),
            role.get("direct_command_role"),
            role.get("external_command_path_class"),
            role.get("entry"),
            role.get("dormant_until_milestone"),
        )
        if observed != expected:
            return False
    return True


def _valid_hook_entry(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    if entry.get("type") != "command":
        return False
    if type(entry.get("timeout")) is not int or entry["timeout"] <= 0:
        return False
    if "failClosed" in entry and type(entry["failClosed"]) is not bool:
        return False
    return "command" not in entry


def _valid_hook_role(
    source: Path,
    role: object,
    *,
    allow_dormant: bool,
) -> bool:
    if not isinstance(role, dict):
        return False
    required = {
        "id",
        "event",
        "direct_command_role",
        "external_command_path_class",
        "entry",
    }
    allowed = required | ({"dormant_until_milestone"} if allow_dormant else set())
    if set(role) - allowed or not required.issubset(role):
        return False
    if not all(
        isinstance(role[key], str) and role[key]
        for key in (
            "id",
            "event",
            "direct_command_role",
            "external_command_path_class",
        )
    ):
        return False
    if role["external_command_path_class"] not in {
        "host-policy-delegator",
        "installed-awa",
    }:
        return False
    relative = Path(role["direct_command_role"])
    if relative.is_absolute() or ".." in relative.parts:
        return False
    command = (source / relative).resolve()
    try:
        command.relative_to(source.resolve())
    except ValueError:
        return False
    try:
        command_mode = command.lstat().st_mode
    except OSError:
        return False
    if (
        not stat.S_ISREG(command_mode)
        or command_mode & 0o111 == 0
        or not os.access(command, os.R_OK)
    ):
        return False
    return _valid_hook_entry(role["entry"])


def _valid_v2_hook_contract(source: Path, v2: object) -> bool:
    if not isinstance(v2, dict):
        return False
    roles = v2.get("roles")
    return (
        v2.get("schema") == "awa-hook-owner/v2"
        and v2.get("version") == 2
        and v2.get("successor_of") == "awa-hook-owner/v1"
        and v2.get("v1_contract")
        == "contracts/awa-contract.v1.json#hook_ownership"
        and v2.get("modes") == ["direct", "external"]
        and v2.get("default_mode") == "direct"
        and v2.get("selection_env") == "AWA_HOOK_OWNER"
        and v2.get("selection_schema") == "awa-hook-owner-selection/v1"
        and v2.get("external_real_hook_file_writes") is False
        and v2.get("supersedes_roles") == ["worktree.shell-guard"]
        and isinstance(v2.get("composition_rule"), str)
        and bool(v2["composition_rule"])
        and isinstance(v2.get("external_rule"), str)
        and bool(v2["external_rule"])
        and _roles_match_layout(roles, _V2_HOOK_LAYOUT)
        and all(
            _valid_hook_role(source, role, allow_dormant=True)
            for role in roles or []
        )
        and all(
            role["external_command_path_class"] == "host-policy-delegator"
            and role["entry"].get("failClosed") is False
            for role in roles or []
        )
    )


def _valid_v3_hook_contract(source: Path, v3: object) -> bool:
    if not isinstance(v3, dict):
        return False
    roles = v3.get("roles")
    return (
        v3.get("schema") == "awa-hook-owner/v3"
        and v3.get("version") == 3
        and v3.get("successor_of") == "awa-hook-owner/v2"
        and v3.get("v2_contract") == "contracts/awa-hook-owner.v2.json"
        and v3.get("modes") == ["direct", "external"]
        and v3.get("default_mode") == "direct"
        and v3.get("selection_env") == "AWA_HOOK_OWNER"
        and v3.get("selection_schema") == "awa-hook-owner-selection/v1"
        and v3.get("external_real_hook_file_writes") is False
        and v3.get("supersedes_roles") == ["finish.prompt-recall"]
        and isinstance(v3.get("composition_rule"), str)
        and bool(v3["composition_rule"])
        and isinstance(v3.get("external_rule"), str)
        and bool(v3["external_rule"])
        and _roles_match_layout(roles, _V3_HOOK_LAYOUT)
        and all(
            _valid_hook_role(source, role, allow_dormant=False)
            for role in roles or []
        )
        and all(
            role["external_command_path_class"] == "host-policy-delegator"
            and role["entry"].get("failClosed") is False
            for role in roles or []
        )
    )


def _valid_v4_hook_contract(source: Path, v4: object) -> bool:
    if not isinstance(v4, dict):
        return False
    roles = v4.get("roles")
    return (
        v4.get("schema") == "awa-hook-owner/v4"
        and v4.get("version") == 4
        and v4.get("successor_of") == "awa-hook-owner/v3"
        and v4.get("v3_contract") == "contracts/awa-hook-owner.v3.json"
        and v4.get("modes") == ["direct", "external"]
        and v4.get("default_mode") == "direct"
        and v4.get("selection_env") == "AWA_HOOK_OWNER"
        and v4.get("selection_schema") == "awa-hook-owner-selection/v1"
        and v4.get("external_real_hook_file_writes") is False
        and v4.get("supersedes_roles") == []
        and v4.get("matcher_modes") == ["CATCH_ALL", "ENUMERATED"]
        and isinstance(v4.get("composition_rule"), str)
        and bool(v4["composition_rule"])
        and isinstance(v4.get("activation_rule"), str)
        and bool(v4["activation_rule"])
        and isinstance(v4.get("external_rule"), str)
        and bool(v4["external_rule"])
        and _roles_match_layout(roles, _V4_HOOK_LAYOUT)
        and all(
            _valid_hook_role(source, role, allow_dormant=False)
            for role in roles or []
        )
        and all(
            role["external_command_path_class"] == "host-policy-delegator"
            and role["entry"].get("failClosed") is False
            for role in roles or []
        )
    )


def _effective_hook_roles(source: Path) -> list[dict] | None:
    v1_path = source / "contracts" / "awa-contract.v1.json"
    try:
        v1 = json.loads(v1_path.read_text(encoding="utf-8"))["hook_ownership"]
    except (
        OSError,
        KeyError,
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):
        return None
    if (
        not isinstance(v1, dict)
        or v1.get("schema") != "awa-hook-owner/v1"
        or v1.get("modes") != ["direct", "external"]
        or v1.get("default_mode") != "direct"
        or v1.get("selection_env") != "AWA_HOOK_OWNER"
        or v1.get("selection_schema") != "awa-hook-owner-selection/v1"
        or v1.get("external_real_hook_file_writes") is not False
        or not _roles_match_layout(v1.get("roles"), _V1_HOOK_LAYOUT)
        or not all(
            _valid_hook_role(source, role, allow_dormant=False)
            for role in v1.get("roles", [])
        )
    ):
        return None

    v1_roles = v1["roles"]
    v2_path = source / "contracts" / "awa-hook-owner.v2.json"
    v3_path = source / "contracts" / "awa-hook-owner.v3.json"
    v4_path = source / "contracts" / "awa-hook-owner.v4.json"
    if not v2_path.exists():
        if v3_path.exists() or v4_path.exists():
            return None
        return list(v1_roles)
    try:
        v2 = json.loads(v2_path.read_text(encoding="utf-8"))
    except (
        OSError,
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):
        return None
    if not _valid_v2_hook_contract(source, v2):
        return None
    superseded = set(v2["supersedes_roles"])
    effective = [
        role for role in v1_roles if role["id"] not in superseded
    ] + list(v2["roles"])
    if not v3_path.exists():
        if v4_path.exists():
            return None
        return effective
    try:
        v3 = json.loads(v3_path.read_text(encoding="utf-8"))
    except (
        OSError,
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):
        return None
    if not _valid_v3_hook_contract(source, v3):
        return None
    superseded = set(v3["supersedes_roles"])
    effective = [
        role for role in effective if role["id"] not in superseded
    ] + list(v3["roles"])
    if not v4_path.exists():
        return effective
    try:
        v4 = json.loads(v4_path.read_text(encoding="utf-8"))
    except (
        OSError,
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):
        return None
    if not _valid_v4_hook_contract(source, v4):
        return None
    superseded = set(v4["supersedes_roles"])
    return [
        role for role in effective if role["id"] not in superseded
    ] + list(v4["roles"])


def _bounded_json_object(path: Path) -> dict | None:
    try:
        with path.open("rb") as handle:
            raw = handle.read(65_537)
        if len(raw) > 65_536:
            return None
        value = json.loads(raw.decode("utf-8"))
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
    ):
        return None
    return value if type(value) is dict else None


def _hook_owner_mode() -> str | None:
    """Resolve direct/external with the installer's closed precedence."""
    if "AWA_HOOK_OWNER" in os.environ:
        explicit = os.environ["AWA_HOOK_OWNER"]
        return explicit if explicit in {"direct", "external"} else None

    selection_path = paths.config_home() / "awa" / "hook-owner.json"
    if os.path.lexists(selection_path):
        selection = _bounded_json_object(selection_path)
        if (
            selection is None
            or set(selection) != {"schema", "contract", "mode"}
            or selection.get("schema") != "awa-hook-owner-selection/v1"
            or selection.get("contract") != "awa-hook-owner/v1"
            or type(selection.get("mode")) is not str
            or selection["mode"] not in {"direct", "external"}
        ):
            return None
        return selection["mode"]

    pointer_path = paths.data_home() / "awa" / "release-pointer.json"
    if not os.path.lexists(pointer_path):
        return "direct"
    pointer = _bounded_json_object(pointer_path)
    legacy_keys = {
        "schema",
        "version",
        "source",
        "commit",
        "runtime",
        "policy",
        "installed_at",
    }
    if (
        pointer is None
        or pointer.get("schema") != "awa-release-pointer/v1"
        or not legacy_keys.issubset(pointer)
        or any(
            type(pointer.get(key)) is not str or not pointer.get(key)
            for key in legacy_keys
        )
    ):
        return None
    owner_keys = {
        "hook_owner_contract",
        "hook_owner_mode",
        "hook_owner_contract_sha256",
    }
    present = owner_keys.intersection(pointer)
    if not present:
        return "direct"
    if present != owner_keys:
        return None
    mode = pointer.get("hook_owner_mode")
    digest = pointer.get("hook_owner_contract_sha256")
    if (
        pointer.get("hook_owner_contract") != "awa-hook-owner/v1"
        or type(mode) is not str
        or mode not in {"direct", "external"}
        or type(digest) is not str
        or re.fullmatch(r"[0-9a-f]{64}", digest) is None
    ):
        return None
    return mode


def _hook_command_path(command: object) -> Path | None:
    if not isinstance(command, str) or not command:
        return None
    try:
        argv = shlex.split(command)
        if not argv:
            return None
        candidate = argv[0]
        if Path(candidate).name in {"bash", "sh"}:
            if len(argv) < 2 or argv[1].startswith("-"):
                return None
            candidate = argv[1]
        return Path(candidate).expanduser()
    except (OSError, RuntimeError, ValueError):
        return None


def _hook_row_shape_matches(row: object, role: dict) -> bool:
    if not isinstance(row, dict):
        return False
    expected = role["entry"]
    expected_without_fail = dict(expected)
    expected_without_fail.pop("failClosed", None)
    observed_without_fail = {
        key: value
        for key, value in row.items()
        if key != "failClosed" or "failClosed" not in expected
    }
    observed_without_fail.pop("command", None)
    return observed_without_fail == expected_without_fail


def _safe_external_hook_command(row: object) -> Path | None:
    if not isinstance(row, dict):
        return None
    command = row.get("command")
    if not isinstance(command, str) or not command:
        return None
    try:
        candidate = Path(command).expanduser()
    except (OSError, RuntimeError, ValueError):
        return None
    if not candidate.is_absolute():
        return None
    try:
        info = candidate.lstat()
        if (
            not stat.S_ISREG(info.st_mode)
            or candidate.is_symlink()
            or info.st_uid != os.getuid()
            or info.st_mode & 0o022
            or not os.access(candidate, os.X_OK)
        ):
            return None
        resolved = candidate.resolve(strict=True)
        if candidate != resolved:
            return None
        parent = resolved.parent.stat()
        if parent.st_uid != os.getuid() or parent.st_mode & 0o022:
            return None
    except (OSError, RuntimeError, ValueError):
        return None
    return resolved


def _direct_hook_projection_facts(
    source: Path,
    hooks_doc: object,
    roles: list[dict],
) -> tuple[bool | None, bool | None]:
    """Preserve the direct-owner evaluator semantics byte-for-byte in behavior."""
    if (
        not isinstance(hooks_doc, dict)
        or hooks_doc.get("version") != 1
        or not isinstance(hooks_doc.get("hooks"), dict)
    ):
        return False, None
    hooks = hooks_doc["hooks"]
    rows_present = True
    fail_open = True
    for role in roles:
        event_rows = hooks.get(role["event"], [])
        if not isinstance(event_rows, list):
            return None, None
        expected_without_fail = dict(role["entry"])
        expected_fail_closed = expected_without_fail.pop("failClosed", None)
        expected_without_fail["command"] = str(
            (source / role["direct_command_role"]).resolve()
        )
        matching = [
            row
            for row in event_rows
            if isinstance(row, dict)
            and (
                {
                    key: value
                    for key, value in row.items()
                    if key != "failClosed" or "failClosed" not in role["entry"]
                }
                == expected_without_fail
            )
        ]
        if len(matching) != 1:
            rows_present = False
            continue
        if (
            expected_fail_closed is False
            and matching[0].get("failClosed") is not False
        ):
            fail_open = False
    return rows_present, fail_open


def _hook_projection_facts(
    source: Path,
    hooks_doc: object,
    roles: list[dict],
    owner_mode: str,
) -> tuple[bool | None, bool | None]:
    if owner_mode == "direct":
        return _direct_hook_projection_facts(source, hooks_doc, roles)
    if (
        not isinstance(hooks_doc, dict)
        or type(hooks_doc.get("version")) is not int
        or hooks_doc.get("version") != 1
        or not isinstance(hooks_doc.get("hooks"), dict)
        or owner_mode != "external"
    ):
        return False, None
    hooks = hooks_doc["hooks"]
    if any(
        not isinstance(event, str)
        or not isinstance(rows, list)
        or any(not isinstance(row, dict) for row in rows)
        for event, rows in hooks.items()
    ):
        return False, None

    direct_targets = {
        role["id"]: (source / role["direct_command_role"]).resolve()
        for role in roles
    }
    basenames = {
        Path(role["direct_command_role"]).name
        for role in roles
    }

    def classify(row: object, role: dict) -> tuple[str, Path | None] | None:
        if not _hook_row_shape_matches(row, role):
            return None
        command = row.get("command") if isinstance(row, dict) else None
        if not isinstance(command, str):
            return "invalid", None
        lexical = _hook_command_path(command)
        if (
            lexical is None
            or lexical.name != Path(role["direct_command_role"]).name
        ):
            return None
        target = _safe_external_hook_command(row)
        if target is None:
            return "invalid", None
        if target == direct_targets[role["id"]]:
            return "direct", target
        return "external", target

    external_owner_dirs: set[Path] = set()
    if owner_mode == "external":
        for role in roles:
            if role["external_command_path_class"] != "host-policy-delegator":
                continue
            for row in hooks.get(role["event"], []):
                candidate = classify(row, role)
                if candidate is not None and candidate[0] == "external":
                    assert candidate[1] is not None
                    external_owner_dirs.add(candidate[1].parent)

    rows_present = True
    if owner_mode == "external" and len(external_owner_dirs) != 1:
        rows_present = False
    external_owner_dir = (
        next(iter(external_owner_dirs))
        if len(external_owner_dirs) == 1
        else None
    )

    fail_open = True
    accepted_rows: set[int] = set()
    for role in roles:
        candidates = []
        for row in hooks.get(role["event"], []):
            candidate = classify(row, role)
            if candidate is not None:
                candidates.append((row, *candidate))

        expected_kind = "direct"
        expected_target = direct_targets[role["id"]]
        if (
            owner_mode == "external"
            and role["external_command_path_class"] == "host-policy-delegator"
        ):
            expected_kind = "external"
            expected_target = (
                external_owner_dir / Path(role["direct_command_role"]).name
                if external_owner_dir is not None
                else None
            )
        matching = [
            item
            for item in candidates
            if item[1] == expected_kind and item[2] == expected_target
        ]
        if len(candidates) != 1 or len(matching) != 1:
            rows_present = False
            continue
        row = matching[0][0]
        accepted_rows.add(id(row))
        if (
            role["entry"].get("failClosed") is False
            and row.get("failClosed") is not False
        ):
            fail_open = False

    # Reject stale, wrong-event, mixed-owner, and superseded AWA-looking rows.
    # Unrelated hooks remain allowed, but a canonical role basename is reserved.
    for rows in hooks.values():
        for row in rows:
            if id(row) in accepted_rows:
                continue
            command = row.get("command")
            command_path = _hook_command_path(command)
            if command_path is not None and command_path.name in basenames:
                rows_present = False

    return rows_present, fail_open


def _hook_facts(source: Path) -> tuple[bool | None, bool | None]:
    hook_path = Path(
        os.environ.get("AWA_HOOKS_JSON")
        or (Path.home() / ".cursor" / "hooks.json")
    ).expanduser()
    roles = _effective_hook_roles(source)
    if roles is None:
        return False, None
    owner_mode = _hook_owner_mode()
    if owner_mode is None:
        return False, None
    try:
        hooks_doc = json.loads(hook_path.read_text(encoding="utf-8"))
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):
        return False, None
    return _hook_projection_facts(source, hooks_doc, roles, owner_mode)


def _release_matches(source: Path) -> bool | None:
    from . import mcp_server

    try:
        pyproject = (source / "pyproject.toml").read_text(encoding="utf-8")
        match = re.search(r'(?m)^version = "([^"]+)"$', pyproject)
        if match is None:
            return None
        source_matches = (
            match.group(1) == __version__
            and mcp_server.SERVER_INFO.get("version") == __version__
        )
        pointer = _release_pointer()
        if pointer is None:
            return None
        pointer_version = pointer.get("version")
        runtime = pointer.get("runtime")
        source_path = pointer.get("source")
        path_matches = any(
            isinstance(value, str)
            and value
            and Path(value).expanduser().resolve() == source.resolve()
            for value in (runtime, source_path)
        )
        return bool(
            source_matches
            and pointer.get("schema") == "awa-release-pointer/v1"
            and pointer_version == __version__
            and path_matches
        )
    except (OSError, RuntimeError):
        return None


def _recovery_facts() -> tuple[str | None, int | None]:
    from . import recovery, retention

    try:
        recovery.list_artifacts()
        scan = retention.scan(paths.recovery_dir())
    except Exception:  # noqa: BLE001 — malformed live recovery state is UNKNOWN.
        return None, None
    needs_repair = len(scan.needs_repair)
    last_status = "errors" if needs_repair else "ok"
    try:
        conn = _ro_conn()
        try:
            row = conn.execute(
                "SELECT value FROM meta WHERE key=?",
                (retention.META_LAST_STATUS,),
            ).fetchone()
            if row and isinstance(row[0], str) and row[0]:
                last_status = row[0]
        finally:
            conn.close()
    except sqlite3.Error:
        pass
    return last_status, needs_repair


def _quarantine_count() -> int:
    """Derive the current committed on-disk quarantine count every evaluation."""
    from . import recovery

    try:
        return recovery.quarantine_count(paths.recovery_dir())
    except Exception:  # noqa: BLE001 — corrupt/partial state never inflates the count.
        return 0


_ROOTS_MODULES: dict[Path, object] = {}
_HANDOFF_MODULES: dict[Path, object] = {}


def _roots_module(source: Path):
    resolved = source.resolve()
    cached = _ROOTS_MODULES.get(resolved)
    if cached is not None:
        return cached
    module_path = resolved / "kernel" / "lib" / "awa_roots.py"
    module_name = (
        "awa_roots_for_integrity_"
        + hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:12]
    )
    spec = importlib.util.spec_from_file_location(
        module_name,
        module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("canonical disposition module unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _ROOTS_MODULES[resolved] = module
    return module


def _handoff_state(source: Path) -> str:
    """Validate the singleton ensure handoff against its current Git identity."""
    resolved = source.resolve()
    module = _HANDOFF_MODULES.get(resolved)
    if module is None:
        module_path = resolved / "kernel" / "lib" / "awa_handoff.py"
        module_name = (
            "awa_handoff_for_integrity_"
            + hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:12]
        )
        try:
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            if spec is None or spec.loader is None:
                return "unknown"
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
        except Exception:
            return "unknown"
        _HANDOFF_MODULES[resolved] = module
    try:
        record = module.read_record()
        state = module.read_state()
    except Exception:
        return "unknown"
    if state in {"absent", "unknown"}:
        return state
    if not isinstance(record, dict):
        return "unknown"
    if state == "pending":
        return "pending"
    try:
        observed = module.identity(record["root"])
    except Exception:
        return "stale"
    return (
        "closed"
        if all(record.get(key) == observed.get(key) for key in observed)
        else "mismatched"
    )


def _native_entry_state() -> str:
    """Read and exactly revalidate bounded private native-entry receipts."""
    try:
        from . import native_entry

        state = native_entry.evidence_state()
    except Exception:
        return "unknown"
    return (
        state
        if state
        in {
            "absent",
            "success",
            "eager",
            "recovered",
            "legacy",
            "stale",
            "mismatched",
            "conflict",
            "failed",
            "pending",
            "unknown",
        }
        else "unknown"
    )


def _lifecycle_facts(source: Path) -> tuple[
    int | None,
    int | None,
    int | None,
    dict[str, str] | None,
    dict[str, int] | None,
]:
    rows = None
    try:
        conn = _ro_conn()
        try:
            rows = conn.execute(
                "SELECT worktree_path FROM leases WHERE status='active'"
            ).fetchall()
        finally:
            conn.close()
    except (sqlite3.Error, OSError):
        rows = None
    try:
        roots = _roots_module(source)
    except (OSError, RuntimeError):
        roots = None

    if rows is None or roots is None:
        leases_unreconciled = None
        sessions_dangling = None
        husks = None
        dispositions = None
    else:
        leases_unreconciled = 0
        sessions_dangling = 0
        husks = 0
        dispositions = {}
        for row in rows:
            worktree = str(row[0])
            key = hashlib.sha256(worktree.encode("utf-8")).hexdigest()[:12]
            try:
                result = roots.disposition(worktree)
                disposition = str(result.get("disposition") or "active")
            except Exception:  # noqa: BLE001 — canonical UNKNOWN fails safe as active.
                disposition = "active"
                result = {}
            dispositions[key] = disposition
            exists = os.path.exists(worktree)
            if not exists or disposition != "active":
                leases_unreconciled += 1
            record = result.get("record")
            sessions = record.get("sessions") if isinstance(record, dict) else None
            if not exists and isinstance(sessions, dict):
                sessions_dangling += len(sessions)
            if exists:
                try:
                    probe = subprocess.run(
                        [
                            "git",
                            "-C",
                            worktree,
                            "rev-parse",
                            "--is-inside-work-tree",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        env={
                            **os.environ,
                            "GIT_OPTIONAL_LOCKS": "0",
                            "GIT_NO_LAZY_FETCH": "1",
                        },
                    )
                    if probe.returncode != 0:
                        husks += 1
                except (OSError, subprocess.SubprocessError):
                    husks += 1
    worktree_counts = None
    try:
        from . import lifecycle_reconcile

        lifecycle_rows = lifecycle_reconcile.classify()
        worktree_counts = lifecycle_reconcile.summarize(lifecycle_rows)
    except Exception:
        worktree_counts = None
    return (
        leases_unreconciled,
        sessions_dangling,
        husks,
        dispositions,
        worktree_counts,
    )


def _launchd_age(previous: dict | None, now: float) -> float | None:
    if not isinstance(previous, dict):
        return None
    triggers = previous.get("triggers")
    if not isinstance(triggers, dict):
        return None
    launchd = triggers.get("launchd")
    if not isinstance(launchd, dict):
        return None
    last_success = _parse_iso(launchd.get("last_success"))
    if last_success is None:
        return None
    age = now - last_success
    return max(0.0, age)


def _delivered(previous: dict | None) -> dict[str, str] | None:
    if not isinstance(previous, dict):
        return None
    pending = _pending_outbox(previous)
    if isinstance(pending, dict):
        delivered = _transition_delivery(
            previous,
            pending["transition_id"],
        )
        if delivered is None:
            return None
        return delivered
    alert = previous.get("alert")
    value = alert.get("delivered") if isinstance(alert, dict) else None
    if not isinstance(value, dict):
        return None
    return {
        key: str(result)
        for key, result in value.items()
        if key in {"native", "slack"}
    }


def _test_facts_from_env() -> Facts | None:
    raw = os.environ.get("AWA_INTEGRITY_TEST_FACTS_JSON")
    if not raw:
        return None
    if os.environ.get("AWA_ENGINE_TEST_ACTIVE") != "1":
        raise RuntimeError("test integrity facts require AWA_ENGINE_TEST_ACTIVE=1")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("test integrity facts must be a JSON object")
    return Facts(**value)


def _collect_facts(
    previous: dict | None,
    *,
    profile: str,
    now: float,
) -> Facts:
    source = _source_root()
    primary_deny, cd_deny, linked_allow, probes = _guard_probes(source)
    hook_rows, hook_fail_open = _hook_facts(source)
    if profile == "deep":
        recovery_status, needs_repair = _recovery_facts()
        (
            leases_unreconciled,
            sessions_dangling,
            husks,
            disposition_map,
            worktree_counts,
        ) = _lifecycle_facts(source)
        parity_ok = _kernel_parity(source, probes)
        mcp_matches = _mcp_parity(source, probes)
    else:
        recovery_status = None
        needs_repair = None
        leases_unreconciled = None
        sessions_dangling = None
        husks = None
        disposition_map = None
        worktree_counts = None
        parity_ok = None
        mcp_matches = None
    return Facts(
        guard_primary_deny=primary_deny,
        guard_cd_bypass_deny=cd_deny,
        guard_linked_allow=linked_allow,
        parity_ok=parity_ok,
        hook_rows_present=hook_rows,
        hook_fail_open=hook_fail_open,
        mcp_matches=mcp_matches,
        release_matches=_release_matches(source),
        recovery_last_status=recovery_status,
        needs_repair=needs_repair,
        leases_unreconciled=leases_unreconciled,
        sessions_dangling=sessions_dangling,
        husks=husks,
        disposition_map=disposition_map,
        handoff_state=_handoff_state(source),
        launchd_last_success_age_s=_launchd_age(previous, now),
        delivered=_delivered(previous),
        native_entry_state=_native_entry_state(),
        worktree_counts=worktree_counts,
    )


def _evaluation_triggers(
    previous: dict | None,
    facts: Facts,
    *,
    trigger: str,
    now: float,
) -> dict[str, dict]:
    previous_triggers = (
        previous.get("triggers", {}) if isinstance(previous, dict) else {}
    )
    if not isinstance(previous_triggers, dict):
        previous_triggers = {}
    triggers: dict[str, dict] = {}
    for name in _TRIGGERS:
        entry = _default_trigger()
        old = previous_triggers.get(name)
        if isinstance(old, dict):
            entry.update(old)
        triggers[name] = entry

    age = facts.launchd_last_success_age_s
    if isinstance(age, (int, float)) and not isinstance(age, bool) and age >= 0:
        observed = _iso_at(now - float(age))
        triggers["launchd"]["last_attempt"] = observed
        triggers["launchd"]["last_success"] = observed
        triggers["launchd"]["last_error"] = None

    now_iso = _iso_at(now)
    active = triggers[trigger]
    active["last_attempt"] = now_iso
    active["last_success"] = now_iso
    active["last_error"] = None
    return triggers


def evaluate(
    profile: str,
    *,
    trigger: str,
    facts: Facts | None = None,
) -> dict:
    """Evaluate the registered checks once without committing or acquiring a lock."""
    if profile not in _PROFILES:
        raise ValueError(f"invalid integrity profile: {profile}")
    if trigger not in _TRIGGERS:
        raise ValueError(f"invalid integrity trigger: {trigger}")
    if trigger == "launchd" and profile != "deep":
        raise ValueError("launchd trigger requires deep profile")

    now = time.time()
    generated_at = _iso_at(now)
    previous = read_status()
    if facts is None:
        facts = _test_facts_from_env() or _collect_facts(
            previous,
            profile=profile,
            now=now,
        )
    if trigger == "launchd":
        facts = replace(facts, launchd_last_success_age_s=0.0)

    previous_invariants = {}
    if isinstance(previous, dict) and isinstance(previous.get("invariants"), list):
        previous_invariants = {
            item.get("id"): item
            for item in previous["invariants"]
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }

    invariants = []
    for invariant_id, (check, _required, _safety, profiles) in REGISTRY.items():
        if invariant_id == "alert_delivery":
            continue
        if profile in profiles:
            severity, evidence = check(facts)
            item = {
                "id": invariant_id,
                "severity": severity,
                "evidence": evidence,
                "checked_at": generated_at,
                "profile": profile,
            }
        else:
            prior = previous_invariants.get(invariant_id)
            if isinstance(prior, dict) and prior.get("severity") in {
                "green",
                "degraded",
                "red",
                "unknown",
            }:
                item = copy.deepcopy(prior)
            else:
                item = {
                    "id": invariant_id,
                    "severity": "unknown",
                    "evidence": "deep check not yet available",
                    "checked_at": generated_at,
                    "profile": "deep",
                }
        invariants.append(item)

    triggers = _evaluation_triggers(
        previous,
        facts,
        trigger=trigger,
        now=now,
    )
    non_alert_overall = reduce(
        [
            *invariants,
            {
                "id": "alert_delivery",
                "severity": "green",
            },
        ],
        triggers,
    )
    alert_severity, alert_evidence = _check_alert(
        facts,
        non_green=non_alert_overall != "green",
    )
    invariants.append(
        {
            "id": "alert_delivery",
            "severity": alert_severity,
            "evidence": alert_evidence,
            "checked_at": generated_at,
            "profile": profile,
        }
    )
    overall = reduce(invariants, triggers)
    launchd_success = _parse_iso(triggers["launchd"].get("last_success"))
    fresh_until = (
        _iso_at(launchd_success + DEEP_BOUND_SECONDS)
        if launchd_success is not None
        else None
    )
    previous_orphans = (
        previous.get("orphans", {}) if isinstance(previous, dict) else {}
    )
    if not isinstance(previous_orphans, dict):
        previous_orphans = {}
    previous_worktrees = (
        previous.get("worktrees", {}) if isinstance(previous, dict) else {}
    )
    if not isinstance(previous_worktrees, dict):
        previous_worktrees = {}
    count_keys = (
        "discovered_linked",
        "managed",
        "active",
        "unleased",
        "conflicts",
        "problems",
    )
    supplied_counts = facts.worktree_counts
    worktree_counts_valid = bool(
        isinstance(supplied_counts, dict)
        and all(
            type(supplied_counts.get(key)) is int
            and supplied_counts[key] >= 0
            for key in count_keys
        )
    )
    worktree_status = {
        "checked": worktree_counts_valid,
        **{
            key: (
                supplied_counts[key]
                if worktree_counts_valid
                else _optional_count(previous_worktrees.get(key))
            )
            for key in count_keys
        },
    }

    def observed_or_previous(value: object, key: str) -> int | None:
        observed = _optional_count(value)
        return (
            observed
            if observed is not None
            else _optional_count(previous_orphans.get(key))
        )

    return {
        "schema": SCHEMA,
        "generated_at": generated_at,
        "profile": profile,
        "trigger": trigger,
        "release": {
            "version": __version__,
            "commit": os.environ.get("AWA_RELEASE_COMMIT") or "unknown",
        },
        "overall": overall,
        "invariants": invariants,
        "triggers": triggers,
        "orphans": {
            # Legacy field retained, but now means the explicitly defined
            # unleased linked-worktree population instead of an uncomputed total.
            "worktrees": (
                worktree_status["unleased"]
                if worktree_counts_valid
                else _optional_count(previous_orphans.get("worktrees"))
            ),
            "leases_unreconciled": observed_or_previous(
                facts.leases_unreconciled,
                "leases_unreconciled",
            ),
            "sessions_dangling": observed_or_previous(
                facts.sessions_dangling,
                "sessions_dangling",
            ),
            "husks": observed_or_previous(facts.husks, "husks"),
        },
        "worktrees": worktree_status,
        "recovery": {
            "last_status": facts.recovery_last_status or "unknown",
            "needs_repair": facts.needs_repair or 0,
            "quarantine_count": _quarantine_count(),
        },
        "alert": {
            "last_transition": (
                previous.get("transition_id") if isinstance(previous, dict) else None
            ),
            "attempted": [],
            "delivered": facts.delivered or {},
        },
        "fresh_until": fresh_until,
    }
