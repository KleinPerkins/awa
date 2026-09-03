#!/usr/bin/env python3
"""Deterministic conversational surface for root-bound worktree finish.

This module adds recall and operator ergonomics only. The kernel's pending challenge,
literal ``Close`` check, fingerprint recheck, session gate, and removal lock remain the
sole removal authority.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unicodedata
import uuid
from enum import Enum
from pathlib import Path
from typing import Any, Callable


RECOGNIZER_VERSION = "finish-current-intent/v1"
DIALOGUE_SCHEMA = "awa_finish_dialogue/v1"
RETAIN_SCHEMA = "awa_protected_retain/v1"
RETAIN_PUBLICATION_SCHEMA = "awa_retain_publication/v1"
RETAIN_PUBLICATION_PROTOCOL = "committed-marker-v1"
RETAIN_PUBLICATION_KEYS = frozenset({
    "schema", "artifact_id", "manifest_sha256",
})
RETAIN_MANIFEST_KEYS = frozenset({
    "schema", "artifact_id", "kind", "protected", "source", "git_common_dir",
    "head", "object_format", "selected_rows", "selected_status", "entries",
    "status_snapshot_hex", "index_snapshot_hex", "index_entries", "base_entries",
    "git_blobs", "selected_paths", "selected_snapshot", "ignore_intent",
    "explicit_secrets", "explicit_ignored_dependencies", "operation_state",
    "operation_abort_proven", "created_at_epoch", "publication_protocol",
    "restore_proven", "restore_proven_at_epoch",
})
RETAIN_OPERATION_STATE_KEYS = frozenset({
    "schema", "operation_digest", "selected_groups", "operation_manifest",
    "raw_index", "admin_root", "object_pack",
})
FINISH_PUBLIC_PROJECTION_ENV = "AWA_FINISH_PUBLIC_PROJECTION"
CURRENT_INDEX_SCHEMA = "awa_finish_current_index/v1"
CHOICE_ENVELOPE_SCHEMA = "awa_finish_choice_envelope/v1"
DIALOGUE_KEYS = frozenset({
    "schema", "recognizer_version", "conversation_id", "session_id", "state",
    "target", "fingerprint", "structure_fingerprint", "nonce", "generation",
    "hook_mode", "visible",
    "rows", "created_at_epoch", "action_kind", "action_commit_complete",
    "action_retain_complete", "action_artifact_id",
})
PRE_STRUCTURE_DIALOGUE_KEYS = DIALOGUE_KEYS - {"structure_fingerprint"}
LEGACY_DIALOGUE_KEYS = PRE_STRUCTURE_DIALOGUE_KEYS - {
    "action_kind", "action_commit_complete", "action_retain_complete",
    "action_artifact_id",
}
CURRENT_INDEX_KEYS = frozenset({
    "schema", "root", "session_id", "conversation_id", "generation", "nonce",
    "fingerprint", "created_at_epoch",
})
CHOICE_ENVELOPE_KEYS = frozenset({
    "schema", "root", "session_id", "conversation_id", "generation", "nonce",
    "exact_text", "canonical_choice", "attachments_present", "event_id",
    "created_at_epoch",
})
_STATE_KEYSETS = {
    DIALOGUE_SCHEMA: DIALOGUE_KEYS,
    CURRENT_INDEX_SCHEMA: CURRENT_INDEX_KEYS,
    CHOICE_ENVELOPE_SCHEMA: CHOICE_ENVELOPE_KEYS,
}
CHOICES = ("Commit", "Retain", "Mixed", "Cancel", "Close")
NON_DESTRUCTIVE_CHOICES = ("Commit", "Retain", "Mixed", "Cancel")
CLOSE_CORRECTION = "For safety, reply exactly: Close"
HOOK_OBSERVATION_SCHEMA = "awa_finish_hook_observation/v1"
HOOK_OBSERVATION_LIMIT = 100
HOOK_PUBLICATION_TICKET_SCHEMA = "awa_finish_hook_publication_ticket/v1"
HOOK_PUBLICATION_INVOCATION_ENV = "AWA_FINISH_HOOK_PUBLICATION_INVOCATION"
HOOK_PUBLICATION_TICKET_LIMIT = 100
HOOK_PUBLICATION_TICKET_KEYS = frozenset({
    "schema", "invocation_id", "conversation_id", "session_id", "root",
    "generation", "nonce", "warning_sha256", "created_at_epoch",
})

WARNING_STATIC = """WARNING: Finish workspace requested

Removing this temporary workspace permanently deletes work you have not committed: the uncommitted changes and untracked or ignored files listed below. Commit or retain them first if you want to keep them. Anything already committed is preserved -- if the branch has commits that are not shared yet, the branch is kept -- so committed work is never lost.

How do you want to proceed? Reply with exactly one of: Commit, Retain, Mixed, Cancel, or Close.

Commit --> Choose which items below to deliver; the agent commits and pushes or merges them.

Retain --> Choose which items below to keep; the agent saves them on your computer, outside the workspace, so removal cannot delete them.

Mixed  --> Choose Commit or Retain for each item; the agent does both.

Cancel --> Do nothing and continue what you were doing.

Close  --> Remove the temporary workspace now. Everything listed below is permanently deleted, the agent stops, and this chat stays open.

To remove the workspace, reply with exactly: Close

Permanently deleted on Close:"""

_DIRECT = frozenset({
    "i'm done", "im done", "i am done", "we're done", "were done", "all done",
    "remove worktree", "remove the worktree", "remove this worktree",
    "remove workspace", "remove the workspace", "remove this workspace",
    "can we close", "can we close this", "can we close this workspace",
    "end session", "end the session", "end this session",
    "finish", "finish up", "finish this", "finish this workspace",
    "finalize", "finalize this", "finalize this workspace",
    "wrap up", "wrap this up", "let's wrap up", "lets wrap up",
    "close workspace", "close the workspace", "close this workspace",
    "let's close", "lets close", "clean up this workspace",
    "please finish", "please finish this", "please close this",
    "please close this workspace", "i'm done please close this",
    "im done please close this", "i am done please close this",
})
_DIRECT_GRAMMAR = re.compile(
    r"^(?:(?:i(?:'m| am)|im)\s+done(?:\s*[-—,:;]\s*)?)?"
    r"(?:please\s+)?(?:finish|finalize|close|remove|end|wrap(?:\s+up)?)"
    r"(?:\s+(?:this|the))?(?:\s+(?:workspace|worktree|session))?$",
    re.IGNORECASE,
)
_NEGATED = re.compile(
    r"\b(?:don['’]?t|do\s+not|not|never|won['’]?t|can['’]?t|cannot|isn['’]?t|aren['’]?t)\b",
    re.IGNORECASE,
)
_META = re.compile(
    r"(?:`|\"|“|”|‘|’.*(?:said|quote)|\b(?:how|what)\s+(?:does|is)\b|"
    r"\b(?:document|documentation|docs|example|code|command|feature|workflow|"
    r"phrase|word|metalinguistic|discussion|discuss|explain|test)\b|"
    r"\b(?:the|a|this)\s+user\s+said\b|\bsomeone\s+said\b|"
    r"\bif\b|\bhypothetical(?:ly)?\b|\bwere\s+i\s+done\b|\bwould\b)",
    re.IGNORECASE,
)


class FinishUXError(RuntimeError):
    pass


class ClosedArgumentError(RuntimeError):
    """An argparse refusal whose private parser detail must not cross the CLI boundary."""


class ClosedArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # Every parser in the tree, including argparse-created subparsers, rejects prefixes.
        # A private value supplied after ``--conversation-i`` must never be accepted as though
        # the caller had provided the exact ``--conversation-id`` grammar.
        kwargs["allow_abbrev"] = False
        super().__init__(*args, **kwargs)

    def error(self, _message: str) -> None:
        raise ClosedArgumentError("invalid_arguments")


def _finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise argparse.ArgumentTypeError("finite number required")
    return parsed


def _row_indices_arg(value: str) -> list[int]:
    parts = value.split(",")
    if (not parts or any(re.fullmatch(r"[0-9]+", part) is None for part in parts)):
        raise argparse.ArgumentTypeError("row numbers required")
    return [int(part) for part in parts]


class PublicDispatchOutcome(str, Enum):
    SELECTION = "selection"
    CORRECTION = "correction"
    CANCELLED = "cancelled"
    CANCEL_INCOMPLETE = "cancel_incomplete"
    REMOVED = "removed"
    REFUSED = "refused"
    UNCERTAIN = "uncertain"


class PublicDispatchReason(str, Enum):
    NO_PENDING_DIALOGUE = "no_pending_dialogue"
    WRONG_DIALOGUE_STATE = "wrong_dialogue_state"
    CURRENT_ROOT_INVALID = "current_root_not_worktree_toplevel"
    CURRENT_DIALOGUE_ABSENT = "current_dialogue_absent"
    CURRENT_DIALOGUE_AMBIGUOUS = "current_dialogue_ambiguous"
    CURRENT_DIALOGUE_MISSING = "current_dialogue_missing"
    CURRENT_DIALOGUE_GENERATION_MISMATCH = "current_dialogue_generation_mismatch"
    CHALLENGE_ABSENT = "challenge_absent"
    CHALLENGE_MALFORMED = "challenge_malformed"
    CHALLENGE_STALE = "challenge_stale"
    CHALLENGE_CONSUMED = "challenge_consumed"
    CHALLENGE_DIALOGUE_MISMATCH = "challenge_dialogue_mismatch"
    CHALLENGE_GENERATION_REQUIRED = "challenge_generation_required"
    CHALLENGE_GENERATION_MISMATCH = "challenge_generation_mismatch"
    CHALLENGE_UNACTIVATED = "challenge_unactivated"
    LIVE_INVENTORY_UNSAFE = "live_inventory_unsafe"
    LIVE_INVENTORY_DRIFT = "live_inventory_drift"
    LIVE_PHYSICAL_DRIFT = "live_physical_incarnation_drift"
    ATTACHMENTS_PRESENT = "attachments_present"
    BOOLEAN_NOT_ALLOWED = "boolean_not_allowed"
    CHOICE_NOT_STRING = "choice_not_string"
    CHOICE_EMPTY = "choice_empty"
    CLOSE_MUST_BE_EXACT = "close_must_be_exact"
    CHOICE_NOT_STANDALONE = "choice_not_standalone"
    CHOICE_ENVELOPE_ABSENT = "choice_envelope_absent"
    CHOICE_ENVELOPE_AMBIGUOUS = "choice_envelope_ambiguous"
    CHOICE_ENVELOPE_MISMATCH = "choice_envelope_mismatch"
    CHOICE_ENVELOPE_CONSUME_FAILED = "choice_envelope_consume_failed"
    CHOICE_ENVELOPE_CANONICAL_MISMATCH = "choice_envelope_canonical_mismatch"
    LOCK_BUSY = "lock_busy"
    FINGERPRINT_MISMATCH = "fingerprint_mismatch"
    CANCEL_CLEANUP_INCOMPLETE = "cancel_cleanup_incomplete"
    CURRENT_REMOVAL_AMBIGUOUS = "current_removal_ambiguous"
    FINISH_REMOVED = "finish_removed"
    WORKSPACE_PRESERVED = "workspace_preserved"
    REMOVAL_UNCERTAIN = "removal_uncertain"
    REQUEST_REFUSED = "request_refused"
    OPERATION_FAILED = "operation_failed"


class PublicBranchResult(str, Enum):
    RETAINED = "retained"
    RETAINED_LOCAL_ONLY = "retained_local_only"
    DELETED = "deleted"


class PublicSelectionState(str, Enum):
    COMMIT = "awaiting_commit_selection"
    RETAIN = "awaiting_retain_selection"
    MIXED = "awaiting_mixed_selection"


_FIXED_PUBLIC_MESSAGES = {
    PublicDispatchOutcome.REMOVED: (
        "The temporary workspace was removed. The agent is stopping; this chat remains open."
    ),
    PublicDispatchOutcome.REFUSED: "The temporary workspace was not removed.",
    PublicDispatchOutcome.UNCERTAIN: (
        "Removal could not be confirmed. The agent is stopping; this chat remains open."
    ),
}
_DRIFT_RECOVERY = (
    "Something in this workspace changed since the warning. Start finish again to see a fresh "
    "warning. For Commit, Retain, or Mixed, use only the row numbers that warning displays."
)

# Process-local handoff: the dispatcher selects one exact recovery anchor; the CLI deletes it only
# after the complete closed public result has been written and flushed.
_POST_OUTPUT_INDEX_CAS: dict | None = None
_DURABILITY = None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_durability():
    global _DURABILITY
    if _DURABILITY is not None:
        return _DURABILITY
    path = Path(os.environ.get("AWA_DURABILITY_LIB", "") or
                (_repo_root() / "kernel" / "lib" / "awa_durability.py"))
    spec = importlib.util.spec_from_file_location(
        "awa_durability_for_finish_consumer", path)
    if spec is None or spec.loader is None:
        raise FinishUXError(f"durability kernel unavailable: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _DURABILITY = mod
    return mod


def _load_finish():
    path = Path(os.environ.get("AWA_FINISH_LIB", "") or
                (_repo_root() / "kernel" / "lib" / "awa_finish.py"))
    spec = importlib.util.spec_from_file_location("awa_finish_for_consumer", path)
    if spec is None or spec.loader is None:
        raise FinishUXError(f"finish kernel unavailable: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _normalize_prompt(prompt: str) -> str:
    text = unicodedata.normalize("NFKC", prompt or "")
    text = text.replace("’", "'")
    text = re.sub(r"\s+", " ", text).strip().lower()
    text = re.sub(r"(?:\u2026|[.!?])+$", "", text).strip()
    text = re.sub(r"\s*[-—,:;]\s*", " ", text)
    return text


def recognize_finish(prompt: Any) -> bool:
    """Pure high-signal recall matcher; it never authorizes or removes anything."""
    if not isinstance(prompt, str) or not prompt.strip():
        return False
    normalized = _normalize_prompt(prompt)
    if _NEGATED.search(normalized) or _META.search(normalized):
        return False
    return normalized in _DIRECT or bool(_DIRECT_GRAMMAR.fullmatch(normalized))


def render_warning(rows: str) -> str:
    """Render immutable approved copy plus Phase-1 escaped rows, without truncation."""
    if not isinstance(rows, str) or not rows:
        rows = "None | No operator work will be deleted."
    return WARNING_STATIC + "\n" + rows


def canonicalize_choice(answer: Any, attachments: Any = None) -> tuple[str | None, str]:
    """Canonicalize safe choices while preserving literal-Close authorization."""
    if attachments:
        return None, "attachments_present"
    if isinstance(answer, bool):
        return None, "boolean_not_allowed"
    if not isinstance(answer, str):
        return None, "choice_not_string"
    if answer == "Close":
        return "Close", "ok"
    trimmed = answer.strip()
    if not trimmed:
        return None, "choice_empty"
    folded = trimmed.casefold()
    for choice in NON_DESTRUCTIVE_CHOICES:
        if folded == choice.casefold():
            return choice, "ok"
    if folded == "close":
        return None, "close_must_be_exact"
    return None, "choice_not_standalone"


def is_exact_choice(answer: Any, attachments: Any = None) -> bool:
    """Compatibility predicate for accepted finish choices."""
    canonical, _reason = canonicalize_choice(answer, attachments)
    return canonical is not None


def _state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME", "").strip()
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".local", "state")
    return Path(base) / "awa"


def _dialogue_dir() -> Path:
    return _state_dir() / "finish-dialogue"


def _retain_dir() -> Path:
    return _state_dir() / "protected-retain"


def _index_dir() -> Path:
    return _state_dir() / "finish-current-index"


def _envelope_dir() -> Path:
    return _state_dir() / "finish-choice-envelope"


def _hook_observation_dir() -> Path:
    return _state_dir() / "finish-hook-observations"


def _hook_publication_dir() -> Path:
    return _state_dir() / "finish-hook-publications"


def _private_dir(path: Path) -> None:
    path = Path(path)
    missing = []
    cursor = path
    while not cursor.exists():
        missing.append(cursor)
        parent = cursor.parent
        if parent == cursor:
            break
        cursor = parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)
        directory.chmod(0o700)
        _sync_dir(directory)
        _sync_dir(directory.parent)
    if not path.is_dir() or path.is_symlink():
        raise FinishUXError("private_directory_invalid")
    path.chmod(0o700)


def _sync_fd(fd: int) -> None:
    """Use the kernel's one file-and-directory physical-durability primitive."""
    _load_durability()._sync_fd(fd)


def _sync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        _sync_fd(fd)
    finally:
        os.close(fd)


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError("short durable write")
        view = view[written:]


def _private_write(path: Path, data: bytes) -> None:
    _private_dir(path.parent)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}.{uuid.uuid4().hex}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.fchmod(fd, 0o600)
        _write_all(fd, data)
        _sync_fd(fd)
    finally:
        os.close(fd)
    try:
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        _sync_dir(path.parent)
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def _copy_regular_durable(source: Path, destination: Path) -> tuple[int, str]:
    _private_dir(destination.parent)
    source_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        source_flags |= os.O_NOFOLLOW
    source_fd = os.open(source, source_flags)
    destination_fd = os.open(
        destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    digest = hashlib.sha256()
    try:
        before = os.fstat(source_fd)
        if not stat.S_ISREG(before.st_mode):
            raise FinishUXError("retain_source_not_regular")
        os.fchmod(destination_fd, 0o600)
        total = 0
        while True:
            chunk = os.read(source_fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            _write_all(destination_fd, chunk)
            total += len(chunk)
        after = os.fstat(source_fd)
        identity = lambda value: (
            value.st_dev, value.st_ino, value.st_mode, value.st_size,
            getattr(value, "st_mtime_ns", int(value.st_mtime * 1_000_000_000)),
            getattr(value, "st_ctime_ns", int(value.st_ctime * 1_000_000_000)),
        )
        if identity(before) != identity(after) or total != before.st_size:
            raise FinishUXError("retain_source_changed")
        _sync_fd(destination_fd)
    finally:
        os.close(destination_fd)
        os.close(source_fd)
    return total, digest.hexdigest()


def _sync_tree_directories_bottom_up(root: Path) -> None:
    directories = [root]
    for dirpath, dirnames, _filenames in os.walk(root, topdown=True, followlinks=False):
        dirnames.sort()
        for name in dirnames:
            child = Path(dirpath) / name
            if child.is_symlink():
                raise FinishUXError("retain_directory_link")
            directories.append(child)
    for directory in sorted(
            directories, key=lambda value: (len(value.parts), os.fsencode(str(value))),
            reverse=True):
        _sync_dir(directory)


def _conversation_key(conversation_id: str) -> str:
    return hashlib.sha256(conversation_id.encode("utf-8")).hexdigest()[:24]


def dialogue_path(conversation_id: str) -> Path:
    return _dialogue_dir() / f"dialogue-{_conversation_key(conversation_id)}.json"


def index_path(conversation_id: str) -> Path:
    return _index_dir() / f"index-{_conversation_key(conversation_id)}.json"


def envelope_path(conversation_id: str, generation: int, event_id: str) -> Path:
    return _envelope_dir() / (
        f"envelope-{_conversation_key(conversation_id)}-{int(generation)}-{event_id}.json")


def _json_write(path: Path, record: dict) -> None:
    _private_write(path, (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def _json_read(path: Path, schema: str) -> dict | None:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    keys = _STATE_KEYSETS.get(schema)
    actual = set(doc) if isinstance(doc, dict) else set()
    keyset_ok = keys is None or actual == keys
    if schema == DIALOGUE_SCHEMA and keys is not None:
        keyset_ok = actual in (
            keys, PRE_STRUCTURE_DIALOGUE_KEYS, LEGACY_DIALOGUE_KEYS)
    # canonical_choice was added within v1; accept its one pre-addition envelope shape while every
    # current writer and contract regression exact-pin the full emitted keyset.
    if schema == CHOICE_ENVELOPE_SCHEMA and keys is not None:
        keyset_ok = actual in (keys, keys - {"canonical_choice"})
    valid = (
        isinstance(doc, dict)
        and doc.get("schema") == schema
        and keyset_ok
    )
    if not valid:
        return None
    if schema == DIALOGUE_SCHEMA and "structure_fingerprint" not in doc:
        doc = dict(doc)
        doc["structure_fingerprint"] = ""
    if schema == DIALOGUE_SCHEMA and actual == LEGACY_DIALOGUE_KEYS:
        doc = dict(doc)
        doc.update({
            "action_kind": "",
            "action_commit_complete": False,
            "action_retain_complete": False,
            "action_artifact_id": "",
        })
    return doc


def _hook_publication_invocation() -> str:
    value = os.environ.get(HOOK_PUBLICATION_INVOCATION_ENV, "").strip()
    return value if re.fullmatch(r"[0-9a-f]{32,64}", value) is not None else ""


def _hook_publication_ticket_path(invocation_id: str) -> Path:
    if re.fullmatch(r"[0-9a-f]{32,64}", invocation_id or "") is None:
        raise FinishUXError("hook_publication_invocation_invalid")
    return _hook_publication_dir() / f"ticket-{invocation_id}.json"


def _write_hook_publication_ticket(dialogue: dict, warning: str) -> bool:
    """Bind the shell's post-output transition to the exact generation it emitted.

    Direct/library callers retain their existing publication API when no invocation id is set.
    The installed hook always supplies one; no generation/nonce has to cross the public JSON.
    """
    invocation_id = _hook_publication_invocation()
    if not invocation_id:
        return False
    record = {
        "schema": HOOK_PUBLICATION_TICKET_SCHEMA,
        "invocation_id": invocation_id,
        "conversation_id": dialogue["conversation_id"],
        "session_id": dialogue["session_id"],
        "root": dialogue["target"]["root"],
        "generation": dialogue["generation"],
        "nonce": dialogue["nonce"],
        "warning_sha256": hashlib.sha256(warning.encode("utf-8")).hexdigest(),
        "created_at_epoch": int(time.time()),
    }
    path = _hook_publication_ticket_path(invocation_id)
    _json_write(path, record)
    # Tickets are post-output handoffs, not authority. Bound their orphan footprint without ever
    # deleting the ticket for the invocation currently being emitted.
    try:
        files = sorted(
            _hook_publication_dir().glob("ticket-*.json"),
            key=lambda item: (item.stat().st_mtime_ns, item.name))
        for stale in files[:-HOOK_PUBLICATION_TICKET_LIMIT]:
            if stale != path:
                stale.unlink()
    except OSError:
        pass
    return True


def _read_hook_publication_ticket(invocation_id: str) -> dict | None:
    try:
        path = _hook_publication_ticket_path(invocation_id)
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (FinishUXError, OSError, json.JSONDecodeError):
        return None
    if (not isinstance(doc, dict) or set(doc) != HOOK_PUBLICATION_TICKET_KEYS
            or doc.get("schema") != HOOK_PUBLICATION_TICKET_SCHEMA
            or doc.get("invocation_id") != invocation_id
            or not isinstance(doc.get("conversation_id"), str)
            or not isinstance(doc.get("session_id"), str)
            or not isinstance(doc.get("root"), str)
            or type(doc.get("generation")) is not int or doc["generation"] < 1
            or not isinstance(doc.get("nonce"), str) or not doc["nonce"]
            or re.fullmatch(r"[0-9a-f]{64}", str(doc.get("warning_sha256") or "")) is None
            or type(doc.get("created_at_epoch")) is not int
            or doc["created_at_epoch"] < 1):
        return None
    return doc


def _clear_hook_publication_ticket(invocation_id: str) -> None:
    try:
        path = _hook_publication_ticket_path(invocation_id)
        path.unlink()
        _sync_dir(path.parent)
    except (FinishUXError, OSError):
        pass


def _safe_outcome(value: Any, fallback: str = "unknown") -> str:
    text = str(value or "")
    return text if re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", text) else fallback


def _observe_hook(payload: dict, output: dict, *, decision: str,
                  identity_outcome: str = "not_evaluated",
                  root_outcome: str = "not_evaluated",
                  reason: str = "") -> None:
    """Write bounded metadata-only hook diagnostics; never influence hook authorization."""
    try:
        canonical = json.dumps(output, sort_keys=True, separators=(",", ":"))
        prompt_keys = [
            key for key in ("prompt", "user_prompt", "message", "text")
            if key in payload
        ]
        identity_keys = [
            key for key in (
                "conversation_id", "conversationId", "chat_id", "chatId",
                "session_id", "sessionId")
            if key in payload
        ]
        roots = _payload_roots(payload)
        record = {
            "schema": HOOK_OBSERVATION_SCHEMA,
            "recorded_at_epoch": int(time.time()),
            "event_type": _safe_outcome(
                payload.get("hook_event_name"), "unknown_event"),
            "payload_keys": sorted(
                key for key in payload if isinstance(key, str)),
            "prompt_keys_present": prompt_keys,
            "attachments_present": _attachments_present(payload),
            "identity_keys_present": identity_keys,
            "identity_outcome": _safe_outcome(identity_outcome),
            "root_candidate_count": len(roots),
            "root_outcome": _safe_outcome(root_outcome),
            "decision": _safe_outcome(decision),
            "reason": _safe_outcome(reason, "redacted"),
            "continue": output.get("continue") if isinstance(
                output.get("continue"), bool) else None,
            "output_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        }
        directory = _hook_observation_dir()
        _private_dir(directory)
        name = f"hook-{time.time_ns()}-{os.getpid()}-{uuid.uuid4().hex[:8]}.json"
        _json_write(directory / name, record)
        files = sorted(directory.glob("hook-*.json"),
                       key=lambda item: (item.stat().st_mtime_ns, item.name))
        for stale in files[:-HOOK_OBSERVATION_LIMIT]:
            try:
                stale.unlink()
            except OSError:
                pass
    except Exception:
        pass


def _hook_output(payload: dict, output: dict, *, decision: str,
                 identity_outcome: str = "not_evaluated",
                 root_outcome: str = "not_evaluated",
                 reason: str = "") -> dict:
    _observe_hook(
        payload, output, decision=decision, identity_outcome=identity_outcome,
        root_outcome=root_outcome, reason=reason)
    return output


def write_dialogue(record: dict) -> None:
    _json_write(dialogue_path(record["conversation_id"]), record)


def _read_dialogue_raw(conversation_id: str) -> dict | None:
    doc = _json_read(dialogue_path(conversation_id), DIALOGUE_SCHEMA)
    if doc is None:
        return None
    if doc.get("conversation_id") != conversation_id:
        return None
    return doc


def read_dialogue(conversation_id: str) -> dict | None:
    """Resolve only a live dialogue; claimed/cancelled projections are permanently inert."""
    doc = _read_dialogue_raw(conversation_id)
    if doc is None:
        return None
    try:
        status = _load_finish().generation_state_status(
            conversation_id, doc.get("nonce"), doc.get("generation"))
    except Exception:
        return None
    return doc if status == "live" else None


def delete_dialogue(conversation_id: str) -> bool:
    try:
        dialogue_path(conversation_id).unlink()
        return True
    except OSError:
        return False


def write_current_index(dialogue: dict) -> None:
    _json_write(index_path(dialogue["conversation_id"]), {
        "schema": CURRENT_INDEX_SCHEMA,
        "root": dialogue["target"]["root"],
        "session_id": dialogue["session_id"],
        "conversation_id": dialogue["conversation_id"],
        "generation": dialogue["generation"],
        "nonce": dialogue["nonce"],
        "fingerprint": dialogue["fingerprint"],
        "created_at_epoch": dialogue["created_at_epoch"],
    })


def _delete_if_cas(path: Path, *, generation: int, nonce: str, schema: str) -> bool:
    doc = _json_read(path, schema)
    if doc is None or doc.get("generation") != generation or doc.get("nonce") != nonce:
        return False
    try:
        path.unlink()
    except OSError:
        return False
    return not path.exists()


def _clear_projection(path: Path, *, generation: int, nonce: str,
                      schema: str) -> tuple[bool, str]:
    """Idempotently clear only the selected projection; never unlink a replacement generation."""
    if not os.path.lexists(path):
        return True, "absent"
    doc = _json_read(path, schema)
    if doc is None:
        return False, "malformed"
    if doc.get("generation") != generation or doc.get("nonce") != nonce:
        return True, "superseded"
    try:
        path.unlink()
    except OSError:
        return False, "unlink_failed"
    return (True, "cleared") if not os.path.lexists(path) else (False, "still_present")


def _cleanup_terminal_projections(dialogue: dict, *,
                                  include_challenge: bool,
                                  include_index: bool = True) -> list[str]:
    """Recoverable bounded cleanup after the kernel made a generation terminal."""
    conversation_id = dialogue["conversation_id"]
    generation = dialogue["generation"]
    nonce = dialogue["nonce"]
    warnings: list[str] = []
    if include_challenge:
        fin = _load_finish()
        challenge, status = fin._read_challenge_raw(conversation_id)
        if (status == "ok" and challenge is not None
                and challenge.get("generation") == generation
                and challenge.get("nonce") == nonce):
            try:
                fin.delete_challenge(
                    conversation_id, expected_generation=generation,
                    expected_nonce=nonce)
            except Exception:
                pass
            challenge, status = fin._read_challenge_raw(conversation_id)
            if (status == "ok" and challenge is not None
                    and challenge.get("generation") == generation
                    and challenge.get("nonce") == nonce):
                warnings.append("challenge_cleanup_failed")
        elif status == "malformed":
            warnings.append("challenge_cleanup_malformed")

    if include_index:
        ok, reason = _clear_projection(
            index_path(conversation_id), generation=generation, nonce=nonce,
            schema=CURRENT_INDEX_SCHEMA)
        if not ok:
            warnings.append("current_index_cleanup_" + reason)

    pattern = (f"envelope-{_conversation_key(conversation_id)}-"
               f"{generation}-*.json")
    for path in sorted(_envelope_dir().glob(pattern)):
        doc = _json_read(path, CHOICE_ENVELOPE_SCHEMA)
        if doc is None:
            warnings.append("choice_envelope_cleanup_malformed")
            continue
        if doc.get("generation") != generation or doc.get("nonce") != nonce:
            continue
        ok, reason = _clear_projection(
            path, generation=generation, nonce=nonce,
            schema=CHOICE_ENVELOPE_SCHEMA)
        if not ok:
            warnings.append("choice_envelope_cleanup_" + reason)

    ok, reason = _clear_projection(
        dialogue_path(conversation_id), generation=generation, nonce=nonce,
        schema=DIALOGUE_SCHEMA)
    if not ok:
        warnings.append("dialogue_cleanup_" + reason)
    return sorted(set(warnings))


def _defer_terminal_index_cleanup(value: dict) -> None:
    global _POST_OUTPUT_INDEX_CAS
    conversation_id = value.get("conversation_id")
    generation = value.get("generation")
    nonce = value.get("nonce")
    if (isinstance(conversation_id, str) and conversation_id
            and type(generation) is int and generation > 0
            and isinstance(nonce, str) and nonce):
        _POST_OUTPUT_INDEX_CAS = {
            "conversation_id": conversation_id,
            "generation": generation,
            "nonce": nonce,
        }


def _finalize_terminal_index_after_output() -> None:
    """Best-effort exact CAS; failure intentionally leaves a duplicate-recovery anchor."""
    global _POST_OUTPUT_INDEX_CAS
    anchor = _POST_OUTPUT_INDEX_CAS
    _POST_OUTPUT_INDEX_CAS = None
    if anchor is None:
        return
    _clear_projection(
        index_path(anchor["conversation_id"]),
        generation=anchor["generation"], nonce=anchor["nonce"],
        schema=CURRENT_INDEX_SCHEMA)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _affirmative_context_handle(value: Any) -> bool:
    """Cloud/background fields can be opaque handles, not just booleans.

    Desktop commonly sends explicit false values; only those and genuinely empty values are
    negative. Every other non-empty value is an unsupported isolated-agent signal.
    """
    if value is None or value is False or value == 0:
        return False
    if isinstance(value, (list, dict)) and not value:
        return False
    text = str(value).strip()
    return bool(text) and text.lower() not in {"false", "0", "no", "off"}


def _payload_prompt(payload: dict) -> str:
    for key in ("prompt", "user_prompt", "message", "text"):
        if isinstance(payload.get(key), str):
            return payload[key]
    return ""


def _payload_conversation(payload: dict) -> str:
    values = {
        payload[key].strip()
        for key in ("conversation_id", "conversationId", "chat_id", "chatId")
        if isinstance(payload.get(key), str) and payload[key].strip()
    }
    if len(values) == 1:
        return next(iter(values))
    if len(values) > 1:
        return ""
    return os.environ.get("AWA_FINISH_CONVERSATION_ID", "").strip()


def _payload_session(payload: dict, conversation_id: str) -> str:
    values = {
        payload[key].strip()
        for key in ("session_id", "sessionId")
        if isinstance(payload.get(key), str) and payload[key].strip()
    }
    if len(values) == 1:
        return next(iter(values))
    if len(values) > 1:
        return ""
    return os.environ.get("DEV_SESSION_ID", "").strip() or conversation_id


def _current_session(root: str) -> dict:
    fin = _load_finish()
    rec, status = fin._roots_module().read_current_session(root)
    if status != "ok" or rec is None:
        raise FinishUXError(f"current_session_{status}")
    return rec


def _bind_hook_current_session(target: dict, session_id: str,
                               conversation_id: str) -> dict:
    """Bind first-prompt identity despite fire-and-forget sessionStart ordering."""
    roots = _load_finish()._roots_module()
    try:
        wait_seconds = float(os.environ.get(
            "AWA_FINISH_SESSION_BIND_WAIT_SECONDS", "3"))
    except ValueError:
        wait_seconds = 3.0
    deadline = time.monotonic() + min(5.0, max(0.0, wait_seconds))
    while True:
        heartbeat = roots.heartbeat(
            target["root"], branch=target["branch"],
            common_dir=target["common_dir"], session_id=session_id,
            lock_timeout=min(1.0, max(0.1, deadline - time.monotonic())))
        if not heartbeat.get("ok", True):
            raise FinishUXError(str(
                heartbeat.get("reason") or "current_session_heartbeat_failed"))
        result = roots.bind_current_session(
            target["root"], session_id=session_id,
            conversation_id=conversation_id, branch=target["branch"],
            common_dir=target["common_dir"], source="beforeSubmitPrompt",
            lock_timeout=min(1.0, max(0.1, deadline - time.monotonic())))
        if result.get("ok"):
            return result
        reason = str(result.get("reason") or "current_session_bind_failed")
        if (reason != "current_session_session_mismatch"
                or time.monotonic() >= deadline):
            raise FinishUXError(reason)
        # sessionStart is documented fire-and-forget and can still be replacing the prior
        # conversation's root binding while the first prompt hook is already running.
        time.sleep(0.05)


def _resolve_current_index(root: str | None = None) -> tuple[dict, dict]:
    candidate = os.path.realpath(root or os.getcwd())
    try:
        resolved = _load_finish().resolve_target(candidate)
    except Exception as exc:
        raise FinishUXError(str(exc) or "current_root_not_worktree_toplevel") from exc
    if resolved["root"] != candidate:
        raise FinishUXError("current_root_not_worktree_toplevel")
    identity = _current_session(candidate)
    fin = _load_finish()
    records = []
    if _index_dir().is_dir():
        for path in sorted(_index_dir().glob("index-*.json")):
            doc = _json_read(path, CURRENT_INDEX_SCHEMA)
            if (doc is not None
                    and fin.generation_state_status(
                        doc.get("conversation_id"), doc.get("nonce"),
                        doc.get("generation")) == "live"
                    and doc.get("root") == candidate
                    and doc.get("session_id") == identity["session_id"]
                    and doc.get("conversation_id") == identity["conversation_id"]):
                records.append(doc)
    if len(records) != 1:
        raise FinishUXError("current_dialogue_absent" if not records
                            else "current_dialogue_ambiguous")
    dialogue = read_dialogue(records[0]["conversation_id"])
    if dialogue is None:
        raise FinishUXError("current_dialogue_missing")
    if (records[0].get("generation") != dialogue.get("generation")
            or records[0].get("nonce") != dialogue.get("nonce")
            or records[0].get("fingerprint") != dialogue.get("fingerprint")):
        raise FinishUXError("current_dialogue_generation_mismatch")
    return dialogue, identity


def _payload_roots(payload: dict) -> list[str]:
    raw: list[str] = []
    nested = payload.get("tool_input")
    sources = (payload, nested if isinstance(nested, dict) else {})
    for source in sources:
        for key in ("cwd", "workspaceRoot", "workspace_path", "root", "projectRoot"):
            if isinstance(source.get(key), str) and source[key].strip():
                raw.append(source[key])
        if isinstance(source.get("workspace_roots"), list):
            raw.extend(x for x in source["workspace_roots"]
                       if isinstance(x, str) and x.strip())
    roots = sorted({os.path.realpath(os.path.abspath(os.path.expanduser(x))) for x in raw})
    return roots


def _unsupported(payload: dict) -> bool:
    nested = payload.get("tool_input")
    for source in (payload, nested if isinstance(nested, dict) else {}):
        for key in ("is_background_agent", "cloud_agent_identity_broker"):
            if _affirmative_context_handle(source.get(key)):
                return True
    for name in (
            "CURSOR_BACKGROUND_AGENT", "CURSOR_CLOUD_AGENT", "IS_BACKGROUND_AGENT",
            "is_background_agent", "AWA_FORCE_CLOUD", "cloud_agent_identity_broker",
            "CURSOR_AGENT_IDENTITY_BROKER"):
        if _affirmative_context_handle(os.environ.get(name)):
            return True
    return any(p == "/workspace" or p.startswith("/workspace/") for p in _payload_roots(payload))


def _finish_git_env(*, index_file: str | None = None) -> dict:
    return _load_finish().sanitized_git_env(index_file=index_file)


def _git(root: str, *args: str, env: dict | None = None,
         timeout: float = 30.0) -> subprocess.CompletedProcess:
    binding = _load_finish().validated_git_binding(root)
    command = [
        "git", "--git-dir=" + binding["git_dir"],
        "--work-tree=" + binding["root"], *args,
    ]
    child_env = _sanitized_supplied_env(
        env, index_file=binding["index_file"])
    return subprocess.run(
        command, capture_output=True, text=True,
        env=child_env, timeout=timeout)


def _git_bytes(root: str, *args: str, env: dict | None = None,
               timeout: float = 30.0) -> subprocess.CompletedProcess:
    binding = _load_finish().validated_git_binding(root)
    command = [
        "git", "--git-dir=" + binding["git_dir"],
        "--work-tree=" + binding["root"], *args,
    ]
    child_env = _sanitized_supplied_env(
        env, index_file=binding["index_file"])
    return subprocess.run(
        command, capture_output=True,
        env=child_env, timeout=timeout)


def _git_bytes_input(root: str, *args: str, input_data: bytes,
                     timeout: float = 120.0) -> subprocess.CompletedProcess:
    binding = _load_finish().validated_git_binding(root)
    command = [
        "git", "--git-dir=" + binding["git_dir"],
        "--work-tree=" + binding["root"], *args,
    ]
    return subprocess.run(
        command, input=input_data, capture_output=True,
        env=_sanitized_supplied_env(None, index_file=binding["index_file"]),
        timeout=timeout)


def resolve_linked_root(payload: dict) -> dict:
    if _unsupported(payload):
        raise FinishUXError("unsupported_context")
    roots = _payload_roots(payload)
    if len(roots) != 1:
        raise FinishUXError("absent_or_multi_root")
    candidate = roots[0]
    try:
        return _load_finish().resolve_target(candidate)
    except Exception as exc:
        reason = str(exc) or "git_identity_unavailable"
        aliases = {
            "git_identity_unavailable": "not_git",
            "current_root_not_worktree_toplevel": "not_worktree_toplevel",
        }
        raise FinishUXError(aliases.get(reason, reason)) from exc


def cleanup_pending(conversation_id: str, *, generation: int | None = None,
                    nonce: str | None = None) -> bool:
    """CAS cleanup only; it can never delete a newer generation."""
    if not conversation_id or generation is None or not nonce:
        return False
    dialogue = _read_dialogue_raw(conversation_id)
    if (dialogue is None or dialogue.get("generation") != generation
            or dialogue.get("nonce") != nonce):
        return False
    target = dialogue.get("target") or {}
    fin = _load_finish()
    try:
        with fin.common_dir_lock(target["common_dir"], blocking=True, timeout=5.0):
            ch, status = fin.read_challenge(conversation_id, lock_held=True)
            if (status == "ok" and ch is not None
                    and ch.get("generation") == generation and ch.get("nonce") == nonce):
                fin.delete_challenge(
                    conversation_id, expected_generation=generation, expected_nonce=nonce,
                    lock_held=True)
            _delete_if_cas(index_path(conversation_id), generation=generation,
                           nonce=nonce, schema=CURRENT_INDEX_SCHEMA)
            for path in _envelope_dir().glob(
                    f"envelope-{_conversation_key(conversation_id)}-{generation}-*.json"):
                _delete_if_cas(path, generation=generation, nonce=nonce,
                               schema=CHOICE_ENVELOPE_SCHEMA)
            return _delete_if_cas(dialogue_path(conversation_id), generation=generation,
                                  nonce=nonce, schema=DIALOGUE_SCHEMA)
    except Exception:
        return False


def preview_payload(payload: dict, *, hook_mode: bool = False,
                    _completed_action: dict | None = None) -> dict:
    """Run bounded local Phase-1 preview and persist dispatcher state."""
    conversation_id = _payload_conversation(payload)
    if not conversation_id:
        raise FinishUXError("missing_stable_conversation_id")
    session_id = _payload_session(payload, conversation_id)
    if not session_id:
        raise FinishUXError("missing_stable_session_id")
    target = resolve_linked_root(payload)
    binding: dict | None = None
    if hook_mode:
        binding = _bind_hook_current_session(target, session_id, conversation_id)
        current = _current_session(target["root"])
        if (current.get("session_id") != session_id
                or current.get("conversation_id") != conversation_id
                or current.get("branch") != target["branch"]
                or os.path.abspath(current.get("common_dir", ""))
                != os.path.abspath(target["common_dir"])):
            if binding.get("created"):
                created = binding.get("current_session") or {}
                _load_finish()._roots_module().remove_current_session_cas(
                    target["root"], session_id=session_id,
                    conversation_id=conversation_id, branch=target["branch"],
                    common_dir=target["common_dir"],
                    expected_boot_id=created.get("boot_id"))
            raise FinishUXError("current_session_identity_mismatch")
    fin = _load_finish()
    try:
        result = fin.preview(**target, session_id=session_id,
                             conversation_id=conversation_id, hook_mode=hook_mode)
        if not result.get("ok"):
            raise FinishUXError(str(result.get("reason") or "preview_failed"))
        inventory = fin.build_inventory(target["root"], target["git_dir"])
        if not inventory.get("safe"):
            raise FinishUXError("inventory_unsafe")
        challenge, challenge_status = fin.read_challenge(conversation_id)
        if (challenge_status != "ok" or challenge is None
                or challenge.get("nonce") != result.get("nonce")
                or challenge.get("generation") != result.get("generation")):
            raise FinishUXError("preview_challenge_mismatch")
        physical = fin.capture_physical_incarnations(
            target["root"], target["git_dir"])
        if physical != (
                challenge.get("root_incarnation"),
                challenge.get("git_dir_incarnation")):
            raise FinishUXError("live_physical_incarnation_drift")
        captured_fingerprint = fin.compute_fingerprint(
            inventory, root=target["root"], git_dir=target["git_dir"],
            common_dir=target["common_dir"], branch=target["branch"],
            head=target["head"], membership=challenge["heartbeat_membership"],
            root_incarnation=physical[0], git_dir_incarnation=physical[1])
        captured_structure = fin.compute_structure_fingerprint(
            inventory, root=target["root"], git_dir=target["git_dir"],
            common_dir=target["common_dir"], branch=target["branch"],
            head=target["head"], membership=challenge["heartbeat_membership"],
            root_incarnation=physical[0], git_dir_incarnation=physical[1])
        if (captured_fingerprint != result.get("fingerprint")
                or captured_structure != result.get("structure_fingerprint")):
            raise FinishUXError("live_inventory_drift")
        row_fingerprints = fin.compute_row_fingerprints(inventory)
        if len(row_fingerprints) != len(inventory["entries"]):
            raise FinishUXError("live_inventory_drift")
        for entry, row_fingerprint in zip(
                inventory["entries"], row_fingerprints, strict=True):
            entry["snapshot_fingerprint"] = row_fingerprint
        visible = [entry for entry in inventory["entries"]
                   if not entry["hidden"] and not entry.get("retained")]
        dialogue = {
            "schema": DIALOGUE_SCHEMA,
            "recognizer_version": RECOGNIZER_VERSION,
            "conversation_id": conversation_id,
            "session_id": session_id,
            "state": "awaiting_choice",
            "target": target,
            "fingerprint": result["fingerprint"],
            "structure_fingerprint": result["structure_fingerprint"],
            "nonce": result["nonce"],
            "generation": result["generation"],
            "hook_mode": bool(hook_mode),
            "visible": visible,
            "rows": result["rows"],
            "created_at_epoch": int(time.time()),
            "action_kind": "",
            "action_commit_complete": False,
            "action_retain_complete": False,
            "action_artifact_id": "",
        }
        if _completed_action is not None:
            # Post-action hook refresh must never expose an awaiting_choice replacement between
            # challenge creation and latch persistence. The first dialogue write for this new
            # generation therefore already carries the completed-action latch.
            dialogue.update({
                "state": "action_complete_refresh_pending",
                "action_kind": _completed_action["action_kind"],
                "action_commit_complete": _completed_action["action_commit_complete"],
                "action_retain_complete": _completed_action["action_retain_complete"],
                "action_artifact_id": _completed_action["action_artifact_id"],
            })
        write_dialogue(dialogue)
        write_current_index(dialogue)
        return {
            "ok": True,
            "continue": False,
            "user_message": render_warning(result["rows"]),
            "conversation_id": conversation_id,
        }
    except Exception:
        if "dialogue" in locals():
            cleanup_pending(conversation_id, generation=dialogue.get("generation"),
                            nonce=dialogue.get("nonce"))
        elif "result" in locals() and isinstance(result, dict):
            nonce = result.get("nonce")
            generation = result.get("generation")
            if isinstance(nonce, str) and type(generation) is int:
                try:
                    fin.delete_challenge(
                        conversation_id, expected_nonce=nonce,
                        expected_generation=generation)
                except Exception:
                    pass
        if hook_mode and binding is not None and binding.get("created"):
            created = binding.get("current_session") or {}
            try:
                fin = _load_finish()
                fin._roots_module().remove_current_session_cas(
                    target["root"], session_id=session_id,
                    conversation_id=conversation_id, branch=target["branch"],
                    common_dir=target["common_dir"],
                    expected_boot_id=created.get("boot_id"))
            except Exception:
                pass
        raise


def _attachments_present(payload: dict) -> bool:
    for key in ("attachments", "files", "images"):
        value = payload.get(key)
        if value not in (None, False, [], {}, ""):
            return True
    return False


def _persist_choice_envelope(payload: dict, prompt: str) -> bool:
    conversation_id = _payload_conversation(payload)
    session_id = _payload_session(payload, conversation_id)
    roots = _payload_roots(payload)
    if not conversation_id or not session_id or len(roots) != 1:
        return False
    dialogue = read_dialogue(conversation_id)
    if dialogue is None or dialogue.get("state") != "awaiting_choice":
        return False
    if (dialogue["target"]["root"] != roots[0]
            or dialogue.get("session_id") != session_id):
        return False
    ch, status = _load_finish().read_challenge(conversation_id)
    if (status != "ok" or ch is None
            or ch.get("nonce") != dialogue.get("nonce")
            or ch.get("generation") != dialogue.get("generation")
            or ch.get("hook_mode") is not True
            or ch.get("hook_warning_published") is not True):
        return False
    event_value = ""
    for key in ("event_id", "eventId", "hook_event_id", "hookEventId", "request_id"):
        if isinstance(payload.get(key), str) and payload[key].strip():
            event_value = payload[key].strip()
            break
    event_material = event_value or uuid.uuid4().hex
    event_id = hashlib.sha256(event_material.encode("utf-8")).hexdigest()[:16]
    canonical_choice, _reason = canonicalize_choice(
        prompt, _attachments_present(payload))
    envelope = {
        "schema": CHOICE_ENVELOPE_SCHEMA,
        "root": dialogue["target"]["root"],
        "session_id": session_id,
        "conversation_id": conversation_id,
        "generation": dialogue["generation"],
        "nonce": dialogue["nonce"],
        "exact_text": prompt,
        "canonical_choice": canonical_choice,
        "attachments_present": _attachments_present(payload),
        "event_id": event_value,
        "created_at_epoch": int(time.time()),
    }
    _json_write(envelope_path(
        conversation_id, dialogue["generation"], event_id), envelope)
    return True


def mark_hook_published(payload: dict) -> bool:
    """Publish only the generation emitted by this exact hook invocation.

    The installed shell supplies a private invocation id shared by its pre-output and post-output
    children. Library callers with no id retain the original current-dialogue compatibility path.
    """
    conversation_id = _payload_conversation(payload)
    invocation_supplied = bool(
        os.environ.get(HOOK_PUBLICATION_INVOCATION_ENV, "").strip())
    invocation_id = _hook_publication_invocation()
    ticket = _read_hook_publication_ticket(invocation_id) if invocation_id else None
    try:
        if invocation_supplied and not invocation_id:
            return False
        if invocation_id and ticket is None:
            return False
        dialogue = _read_dialogue_raw(conversation_id)
        if dialogue is None or dialogue.get("hook_mode") is not True:
            return False
        if ticket is not None:
            roots = _payload_roots(payload)
            session_id = _payload_session(payload, conversation_id)
            if (ticket.get("conversation_id") != conversation_id
                    or ticket.get("session_id") != session_id
                    or len(roots) != 1 or ticket.get("root") != roots[0]
                    or ticket.get("generation") != dialogue.get("generation")
                    or ticket.get("nonce") != dialogue.get("nonce")
                    or ticket.get("warning_sha256") != hashlib.sha256(
                        render_warning(str(dialogue.get("rows") or "")).encode(
                            "utf-8")).hexdigest()):
                return False
        fin = _load_finish()
        challenge, status = fin._read_challenge_raw(conversation_id)
        if (status not in {"ok", "legacy_skew"} or challenge is None
                or challenge.get("nonce") != dialogue.get("nonce")
                or challenge.get("generation") != dialogue.get("generation")):
            return False
        was_unpublished = challenge.get("hook_warning_published") is False
        result = fin.publish_hook_challenge(
            conversation_id=conversation_id,
            common_dir=dialogue["target"]["common_dir"],
            root=dialogue["target"]["root"], session_id=dialogue["session_id"],
            nonce=dialogue["nonce"], generation=dialogue["generation"])
        if not result.get("ok"):
            return False
        # For post-action refresh, the completed-action latch remains present through output and
        # kernel publication. Only this exact post-output CAS turns the new generation into a
        # choice-accepting dialogue. A crash first causes the next prompt to republish, never act.
        if (was_unpublished
                and dialogue.get("state") == "action_complete_refresh_pending"):
            try:
                with fin.common_dir_lock(
                        dialogue["target"]["common_dir"], blocking=True, timeout=5.0):
                    current = _read_dialogue_raw(conversation_id)
                    current_challenge, current_status = fin.read_challenge(
                        conversation_id, lock_held=True)
                    if (current is None
                            or current.get("state") != "action_complete_refresh_pending"
                            or current.get("generation") != dialogue.get("generation")
                            or current.get("nonce") != dialogue.get("nonce")
                            or current_status != "ok" or current_challenge is None
                            or current_challenge.get("generation") != dialogue.get("generation")
                            or current_challenge.get("nonce") != dialogue.get("nonce")
                            or current_challenge.get("hook_warning_published") is not True):
                        return False
                    current.update({
                        "state": "awaiting_choice",
                        "action_kind": "",
                        "action_commit_complete": False,
                        "action_retain_complete": False,
                        "action_artifact_id": "",
                    })
                    write_dialogue(current)
                    write_current_index(current)
            except Exception:
                return False
        return True
    except Exception:
        return False
    finally:
        if invocation_id:
            _clear_hook_publication_ticket(invocation_id)


def _refresh_hook_completed_action(payload: dict, dialogue: dict) -> dict:
    """Create a fresh hook warning while retaining completed-action state until publication."""
    conversation_id = _payload_conversation(payload)
    roots = _payload_roots(payload)
    if (dialogue.get("state") != "action_complete_refresh_pending"
            or dialogue.get("hook_mode") is not True
            or dialogue.get("conversation_id") != conversation_id
            or dialogue.get("session_id") != _payload_session(payload, conversation_id)
            or len(roots) != 1 or roots[0] != dialogue.get("target", {}).get("root")):
        raise FinishUXError("action_refresh_identity_mismatch")
    # Validate all completed-action facts before replacing any challenge generation.
    _refresh_completed_action(dialogue)
    original = dict(dialogue)
    replacement: dict | None = None
    try:
        result = preview_payload(
            payload, hook_mode=True, _completed_action=original)
        replacement = _read_dialogue_raw(conversation_id)
        if (replacement is None
                or replacement.get("generation") == original.get("generation")
                or replacement.get("nonce") == original.get("nonce")
                or replacement.get("state") != "action_complete_refresh_pending"
                or replacement.get("action_kind") != original.get("action_kind")):
            raise FinishUXError("action_refresh_generation_missing")
        if os.environ.get(HOOK_PUBLICATION_INVOCATION_ENV, "").strip():
            if not _write_hook_publication_ticket(
                    replacement, str(result.get("user_message") or "")):
                raise FinishUXError("hook_publication_ticket_unavailable")
        return result
    except Exception:
        current = _read_dialogue_raw(conversation_id)
        if (current is not None
                and (current.get("generation"), current.get("nonce"))
                != (original.get("generation"), original.get("nonce"))):
            cleanup_pending(
                conversation_id, generation=current.get("generation"),
                nonce=current.get("nonce"))
        write_dialogue(original)
        write_current_index(original)
        raise


def _match_choice_envelope(dialogue: dict) -> tuple[Path | None, dict | None, str]:
    """Locate the single choice envelope bound to this generation WITHOUT consuming it."""
    pattern = (f"envelope-{_conversation_key(dialogue['conversation_id'])}-"
               f"{dialogue['generation']}-*.json")
    matches = []
    for path in sorted(_envelope_dir().glob(pattern)):
        doc = _json_read(path, CHOICE_ENVELOPE_SCHEMA)
        if doc is not None:
            matches.append((path, doc))
    if len(matches) != 1:
        return None, None, (
            "choice_envelope_absent" if not matches else "choice_envelope_ambiguous")
    path, doc = matches[0]
    if (doc.get("root") != dialogue["target"]["root"]
            or doc.get("session_id") != dialogue["session_id"]
            or doc.get("conversation_id") != dialogue["conversation_id"]
            or doc.get("generation") != dialogue["generation"]
            or doc.get("nonce") != dialogue["nonce"]):
        return None, None, "choice_envelope_mismatch"
    return path, doc, "ok"


def _consume_choice_envelope(dialogue: dict) -> tuple[dict | None, str]:
    path, doc, reason = _match_choice_envelope(dialogue)
    if path is None or doc is None:
        return None, reason
    try:
        path.unlink()
    except OSError:
        return None, "choice_envelope_consume_failed"
    return doc, "ok"


def _pending_choice_drift_mode(dialogue: dict, challenge: dict, answer: Any,
                               attachments: Any) -> str:
    """Classify the read-only live-proof policy for the pending canonical choice."""
    try:
        if challenge.get("hook_mode"):
            _path, doc, _reason = _match_choice_envelope(dialogue)
            if doc is None:
                return "strict"
            choice, _ = canonicalize_choice(
                doc.get("exact_text"), doc.get("attachments_present"))
            if "canonical_choice" in doc and doc.get("canonical_choice") != choice:
                return "strict"
        else:
            choice, _ = canonicalize_choice(answer, attachments)
        if choice == "Cancel":
            return "cancel"
        if choice in {"Retain", "Close"}:
            return "content"
        return "strict"
    except Exception:
        return "strict"


def handle_hook_payload(payload: dict) -> dict:
    """Fail-open prompt-hook adapter. Choice candidates pass to the dispatcher."""
    try:
        conversation_id = _payload_conversation(payload)
    except FinishUXError:
        return _hook_output(
            payload, {"continue": True}, decision="fail_open",
            identity_outcome="not_confirmable", reason="conversation_identity_unavailable")
    # A completed hook-mode action cannot publish its own replacement challenge. The next prompt
    # is discarded before recognition/choice parsing and used only to emit a fresh warning.
    pending_action = _read_dialogue_raw(conversation_id)
    if (pending_action is not None
            and pending_action.get("state") == "action_complete_refresh_pending"
            and pending_action.get("hook_mode") is True):
        try:
            result = _refresh_hook_completed_action(payload, pending_action)
            return _hook_output(
                payload, {"continue": False, "user_message": result["user_message"]},
                decision="block_warning", identity_outcome="matched",
                root_outcome="matched", reason="completed_action_refresh")
        except Exception as exc:
            return _hook_output(
                payload, {"continue": True}, decision="fail_open",
                identity_outcome="not_confirmable", root_outcome="not_evaluated",
                reason=_safe_outcome(str(exc), exc.__class__.__name__))
    prompt = _payload_prompt(payload)
    text_choice, text_reason = canonicalize_choice(prompt)
    if text_choice is not None or text_reason == "close_must_be_exact":
        persisted = _persist_choice_envelope(payload, prompt)
        canonical_choice, reason = canonicalize_choice(
            prompt, _attachments_present(payload))
        return _hook_output(
            payload, {"continue": True},
            decision="allow_choice_envelope" if persisted else "allow_choice_inert",
            identity_outcome="matched" if persisted else "not_confirmable",
            root_outcome="matched" if persisted else "not_evaluated",
            reason=("canonical_" + canonical_choice.lower()
                    if canonical_choice is not None else reason))
    if not recognize_finish(prompt):
        return _hook_output(
            payload, {"continue": True}, decision="allow_unrecognized")
    try:
        result = preview_payload(payload, hook_mode=True)
        dialogue = _read_dialogue_raw(conversation_id)
        if dialogue is None:
            raise FinishUXError("hook_preview_dialogue_missing")
        if os.environ.get(HOOK_PUBLICATION_INVOCATION_ENV, "").strip():
            if not _write_hook_publication_ticket(
                    dialogue, str(result.get("user_message") or "")):
                raise FinishUXError("hook_publication_ticket_unavailable")
        return _hook_output(
            payload, {"continue": False, "user_message": result["user_message"]},
            decision="block_warning", identity_outcome="matched", root_outcome="matched")
    except Exception as exc:
        dialogue = read_dialogue(conversation_id)
        if dialogue is not None:
            cleanup_pending(conversation_id, generation=dialogue.get("generation"),
                            nonce=dialogue.get("nonce"))
        reason = _safe_outcome(str(exc), exc.__class__.__name__)
        identity_outcome = (
            reason if reason.startswith(("missing_stable_", "current_session_"))
            else "not_evaluated")
        root_outcome = (
            reason if reason in {
                "unsupported_context", "absent_or_multi_root", "not_git",
                "not_worktree_toplevel", "git_identity_unavailable", "primary_checkout",
            } else "not_evaluated")
        return _hook_output(
            payload, {"continue": True}, decision="fail_open",
            identity_outcome=identity_outcome, root_outcome=root_outcome,
            reason=reason)


def _selected(dialogue: dict, indices: list[int]) -> list[dict]:
    if not isinstance(indices, list) or not indices:
        raise FinishUXError("at_least_one_row_required")
    if any(not isinstance(i, int) for i in indices):
        raise FinishUXError("row_indices_must_be_integers")
    if len(indices) != len(set(indices)):
        raise FinishUXError("duplicate_row")
    visible = dialogue.get("visible") or []
    if any(i < 1 or i > len(visible) for i in indices):
        raise FinishUXError("row_out_of_range")
    return [visible[i - 1] for i in indices]


def _claim_action(conversation_id: str, expected_state: str, executing_state: str,
                  lock_timeout: float = 30.0, *,
                  allow_content_drift: bool = False,
                  selected_indices: list[int] | None = None) -> dict:
    dialogue = read_dialogue(conversation_id)
    if dialogue is None:
        raise FinishUXError("no_pending_dialogue")
    if dialogue.get("state") != expected_state:
        raise FinishUXError("wrong_dialogue_state")
    fin = _load_finish()
    with fin.common_dir_lock(
            dialogue["target"]["common_dir"], blocking=True, timeout=lock_timeout):
        current = read_dialogue(conversation_id)
        if (current is None or current.get("generation") != dialogue.get("generation")
                or current.get("nonce") != dialogue.get("nonce")
                or current.get("state") != expected_state):
            raise FinishUXError("dialogue_transition_cas_mismatch")
        fin, challenge = _bind_dialogue_challenge(
            current, expected_state=expected_state, lock_held=True)
        _assert_live_inventory(
            fin, current, challenge, lock_held=True,
            allow_content_drift=allow_content_drift,
            selected_indices=selected_indices)
        current["state"] = executing_state
        write_dialogue(current)
        return current


def _latch_action_complete(conversation_id: str, action_kind: str, *,
                           commit_complete: bool, retain_complete: bool,
                           artifact_id: str = "", lock_timeout: float = 30.0) -> dict:
    """Persist the generation-bound point of no return before any fresh preview.

    A retry may refresh this exact generation, but it may never execute the completed action again.
    """
    expected_states = {
        "Commit": "committing",
        "Retain": "retaining",
        "Mixed": "executing_mixed",
    }
    expected = expected_states.get(action_kind)
    if expected is None:
        raise FinishUXError("action_kind_invalid")
    if type(commit_complete) is not bool or type(retain_complete) is not bool:
        raise FinishUXError("action_completion_invalid")
    completion_shape = {
        "Commit": (True, False, False),
        "Retain": (False, True, True),
        "Mixed": (True, True, True),
    }[action_kind]
    if ((commit_complete, retain_complete, bool(artifact_id))
            != completion_shape):
        raise FinishUXError("action_completion_invalid")
    if artifact_id and re.fullmatch(r"retain-[0-9a-f]{32}", artifact_id) is None:
        raise FinishUXError("action_artifact_invalid")
    dialogue = _read_dialogue_raw(conversation_id)
    if dialogue is None:
        raise FinishUXError("no_pending_dialogue")
    fin = _load_finish()
    with fin.common_dir_lock(
            dialogue["target"]["common_dir"], blocking=True, timeout=lock_timeout):
        current = _read_dialogue_raw(conversation_id)
        if (current is None
                or current.get("generation") != dialogue.get("generation")
                or current.get("nonce") != dialogue.get("nonce")):
            raise FinishUXError("dialogue_transition_cas_mismatch")
        if current.get("state") == "action_complete_refresh_pending":
            if (
                    current.get("action_kind") == action_kind
                    and current.get("action_commit_complete") is commit_complete
                    and current.get("action_retain_complete") is retain_complete
                    and current.get("action_artifact_id") == artifact_id):
                return current
            raise FinishUXError("action_completion_mismatch")
        if current.get("state") != expected:
            raise FinishUXError("wrong_dialogue_state")
        current.update({
            "state": "action_complete_refresh_pending",
            "action_kind": action_kind,
            "action_commit_complete": commit_complete,
            "action_retain_complete": retain_complete,
            "action_artifact_id": artifact_id,
        })
        write_dialogue(current)
        return current


def _bind_dialogue_challenge(dialogue: dict, *, expected_state: str,
                             lock_held: bool = False) -> tuple[Any, dict]:
    """Identity binding ONLY: resolve the challenge that this dialogue names, WITHOUT the live
    inventory/fingerprint drift gate. Every identity failure still refuses -- a Cancel may only
    discard the exact challenge its dialogue is bound to. Callers that also require phase-specific
    live proof pair this with `_assert_live_inventory` (see `_validate_dialogue_live`)."""
    if dialogue.get("state") != expected_state:
        raise FinishUXError(
            f"wrong_dialogue_state:{dialogue.get('state')}:{expected_state}")
    target = dialogue.get("target")
    if not isinstance(target, dict):
        raise FinishUXError("dialogue_target_invalid")
    fin = _load_finish()
    ch, status = fin.read_challenge(
        dialogue["conversation_id"], lock_held=lock_held)
    if status != "ok" or ch is None:
        raise FinishUXError(f"challenge_{status}")
    if (ch.get("nonce") != dialogue.get("nonce")
            or ch.get("generation") != dialogue.get("generation")
            or ch.get("fingerprint") != dialogue.get("fingerprint")
            or ch.get("structure_fingerprint", "")
            != dialogue.get("structure_fingerprint", "")
            or ch.get("root") != target.get("root")
            or ch.get("session_key") != fin._roots_module().session_key(
                dialogue.get("session_id"))):
        raise FinishUXError("challenge_dialogue_mismatch")
    return fin, ch


def _assert_live_inventory(
        fin: Any, dialogue: dict, ch: dict, *, lock_held: bool = False,
        allow_content_drift: bool = False,
        selected_indices: list[int] | None = None) -> None:
    """Enforce the phase-appropriate live proof and physical-incarnation gates.

    Strict callers require the full fingerprint. Retain/Close callers may admit opaque regular-file
    churn below an unchanged displayed directory after exact structural equality; Retain
    additionally requires exact selected-row snapshots. Cancel intentionally skips this gate.
    """
    target = dialogue["target"]
    inv = fin.build_inventory(target["root"], target["git_dir"])
    if not inv.get("safe"):
        raise FinishUXError("live_inventory_unsafe")
    membership = fin.heartbeat_membership(
        target["root"], fin._roots_module().session_key(dialogue["session_id"]),
        branch=target["branch"], common_dir=target["common_dir"],
        lock_held=lock_held)
    physical = fin.capture_physical_incarnations(
        target["root"], target["git_dir"])
    fingerprint = fin.compute_fingerprint(
        inv, root=target["root"], git_dir=target["git_dir"],
        common_dir=target["common_dir"], branch=target["branch"],
        head=target["head"], membership=membership,
        root_incarnation=physical[0], git_dir_incarnation=physical[1])
    if fingerprint != dialogue.get("fingerprint"):
        expected_structure = dialogue.get("structure_fingerprint")
        if not allow_content_drift or not expected_structure:
            raise FinishUXError("live_inventory_drift")
        structure_fingerprint = fin.compute_structure_fingerprint(
            inv, root=target["root"], git_dir=target["git_dir"],
            common_dir=target["common_dir"], branch=target["branch"],
            head=target["head"], membership=membership,
            root_incarnation=physical[0], git_dir_incarnation=physical[1])
        if structure_fingerprint != expected_structure:
            raise FinishUXError("live_inventory_drift")
        if selected_indices is not None:
            selected = _selected(dialogue, selected_indices)
            live_rows = [
                row_fingerprint
                for entry, row_fingerprint in zip(
                    inv["entries"], fin.compute_row_fingerprints(inv), strict=True)
                if not entry.get("hidden") and not entry.get("retained")
            ]
            if len(live_rows) != len(dialogue.get("visible") or []):
                raise FinishUXError("live_inventory_drift")
            for index, baseline in zip(selected_indices, selected, strict=True):
                expected = baseline.get("snapshot_fingerprint")
                if (not isinstance(expected, str)
                        or re.fullmatch(r"[0-9a-f]{64}", expected) is None
                        or live_rows[index - 1] != expected):
                    raise FinishUXError("live_inventory_drift")
    if physical != (ch.get("root_incarnation"), ch.get("git_dir_incarnation")):
        raise FinishUXError("live_physical_incarnation_drift")


def _validate_dialogue_live(dialogue: dict, *, expected_state: str,
                            lock_held: bool = False,
                            allow_content_drift: bool = False,
                            selected_indices: list[int] | None = None) -> tuple[Any, dict]:
    fin, ch = _bind_dialogue_challenge(
        dialogue, expected_state=expected_state, lock_held=lock_held)
    _assert_live_inventory(
        fin, dialogue, ch, lock_held=lock_held,
        allow_content_drift=allow_content_drift,
        selected_indices=selected_indices)
    return fin, ch


def _activate_envelope(fin: Any, dialogue: dict, envelope: dict,
                       canonical_choice: str) -> tuple[bool, str]:
    canonical = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    activated = fin.activate_hook_challenge(
        conversation_id=dialogue["conversation_id"],
        common_dir=dialogue["target"]["common_dir"],
        root=dialogue["target"]["root"], session_id=dialogue["session_id"],
        nonce=dialogue["nonce"], generation=dialogue["generation"],
        choice=canonical_choice, envelope_digest=digest)
    return bool(activated.get("ok")), str(activated.get("reason") or "activation_failed")


def _public_reason(value: Any, fallback: PublicDispatchReason) -> PublicDispatchReason:
    text = value if isinstance(value, str) else ""
    if text.startswith("wrong_dialogue_state:"):
        return PublicDispatchReason.WRONG_DIALOGUE_STATE
    exact = {item.value: item for item in PublicDispatchReason}
    return exact.get(text, fallback)


def _public_branch(value: Any) -> PublicBranchResult | None:
    # A failed/raised conditional deletion leaves the saved name in place by kernel contract.
    mapping = {
        "retained": PublicBranchResult.RETAINED,
        "retained_local_only": PublicBranchResult.RETAINED_LOCAL_ONLY,
        "deleted": PublicBranchResult.DELETED,
        "delete_failed": PublicBranchResult.RETAINED,
        "delete_error": PublicBranchResult.RETAINED,
    }
    return mapping.get(value) if isinstance(value, str) else None


def _public_cleanup_warnings(values: Any) -> list[str]:
    allowed = {
        "active_root_cleanup_failed",
        "challenge_cleanup_failed",
        "challenge_cleanup_malformed",
        "choice_envelope_cleanup_malformed",
        "choice_envelope_cleanup_unlink_failed",
        "current_index_cleanup_malformed",
        "current_index_cleanup_unlink_failed",
        "dialogue_cleanup_malformed",
        "dialogue_cleanup_unlink_failed",
        "finalized_state_write_failed",
        "kernel_state_cleanup_incomplete",
        "local_cleanup_incomplete",
        "receipt_write_failed",
        "removal_reconciliation_failed",
        "removal_reconciliation_incomplete",
        "removed_state_write_failed",
    }
    out = []
    for value in values if isinstance(values, (list, tuple, set)) else []:
        if isinstance(value, str) and value in allowed:
            out.append(value)
        elif isinstance(value, str) and value.startswith("current_session_"):
            out.append("current_session_cleanup_failed")
        elif value:
            out.append("local_cleanup_incomplete")
    return sorted(set(out))


def _parse_shell_public_projection(
        value: Any) -> tuple[PublicDispatchOutcome, PublicDispatchReason,
                             PublicBranchResult | None] | None:
    """Accept only the shell's exact closed machine projection; ignore every extra byte."""
    if not isinstance(value, str):
        return None
    try:
        if len(value.encode("utf-8")) > 4096:
            return None
    except UnicodeError:
        return None
    try:
        def closed_object(pairs):
            doc = {}
            for key, item in pairs:
                if key in doc:
                    raise ValueError("duplicate projection field")
                doc[key] = item
            return doc

        doc = json.loads(value, object_pairs_hook=closed_object)
    except (TypeError, ValueError):
        return None
    if not isinstance(doc, dict):
        return None
    if set(doc) == {"outcome", "reason", "branch_action"}:
        if (doc.get("outcome") != PublicDispatchOutcome.REMOVED.value
                or doc.get("reason") != PublicDispatchReason.FINISH_REMOVED.value):
            return None
        try:
            branch = PublicBranchResult(doc.get("branch_action"))
        except (TypeError, ValueError):
            return None
        return (
            PublicDispatchOutcome.REMOVED,
            PublicDispatchReason.FINISH_REMOVED,
            branch,
        )
    if set(doc) != {"outcome", "reason"}:
        return None
    if (doc.get("outcome") == PublicDispatchOutcome.REFUSED.value
            and doc.get("reason") == PublicDispatchReason.WORKSPACE_PRESERVED.value):
        return (
            PublicDispatchOutcome.REFUSED,
            PublicDispatchReason.WORKSPACE_PRESERVED,
            None,
        )
    if (doc.get("outcome") == PublicDispatchOutcome.UNCERTAIN.value
            and doc.get("reason") == PublicDispatchReason.REMOVAL_UNCERTAIN.value):
        return (
            PublicDispatchOutcome.UNCERTAIN,
            PublicDispatchReason.REMOVAL_UNCERTAIN,
            None,
        )
    return None


def _build_public_dispatch(
        outcome: PublicDispatchOutcome, *,
        reason: PublicDispatchReason = PublicDispatchReason.REQUEST_REFUSED,
        selection_state: PublicSelectionState | None = None,
        kernel_outcome: dict | None = None,
        cleanup_warnings: list[str] | None = None,
        audit_failed: bool = False,
        fresh_preview_required: bool | None = None) -> dict:
    """The sole public dispatcher projection.

    Inputs are closed enums plus booleans. Child text and extra JSON fields are never copied.
    """
    if not isinstance(outcome, PublicDispatchOutcome):
        raise TypeError("public dispatch outcome must be typed")
    if not isinstance(reason, PublicDispatchReason):
        raise TypeError("public dispatch reason must be typed")
    raw = kernel_outcome if isinstance(kernel_outcome, dict) else {}
    if outcome == PublicDispatchOutcome.SELECTION:
        if not isinstance(selection_state, PublicSelectionState):
            raise TypeError("public selection state must be typed")
        return {
            "ok": True,
            "state": selection_state.value,
            "instruction": "Select displayed row numbers only.",
        }
    if outcome == PublicDispatchOutcome.CORRECTION:
        result = {
            "ok": False,
            "state": "awaiting_choice",
            "reason": reason.value,
            "mutated_repo": False,
        }
        if reason == PublicDispatchReason.CLOSE_MUST_BE_EXACT:
            result["user_message"] = CLOSE_CORRECTION
        return result
    if outcome == PublicDispatchOutcome.CANCELLED:
        return {"ok": True, "state": "cancelled", "mutated_repo": False}
    if outcome == PublicDispatchOutcome.CANCEL_INCOMPLETE:
        return {
            "ok": False,
            "state": "cancelled_cleanup_incomplete",
            "reason": PublicDispatchReason.CANCEL_CLEANUP_INCOMPLETE.value,
            "cleanup_warnings": _public_cleanup_warnings(cleanup_warnings),
            "authority_inert": True,
            "mutated_repo": False,
        }
    if outcome == PublicDispatchOutcome.REMOVED:
        branch = _public_branch(raw.get("branch_action"))
        if branch is None:
            return _build_public_dispatch(
                PublicDispatchOutcome.UNCERTAIN,
                reason=PublicDispatchReason.REMOVAL_UNCERTAIN)
        raw_warnings = raw.get("state_cleanup_warnings")
        raw_warnings = raw_warnings if isinstance(raw_warnings, list) else []
        warnings = _public_cleanup_warnings(
            raw_warnings
            + list(cleanup_warnings or []))
        message = _FIXED_PUBLIC_MESSAGES[outcome]
        return {
            "ok": True,
            "state": "removed",
            "workspace_removed": True,
            "agent_stopping": True,
            "chat_remains_open": True,
            "audit_receipt_failed": bool(audit_failed),
            "branch_action": branch.value,
            "message": message,
            "outcome": {
                "outcome": "removed",
                "reason": PublicDispatchReason.FINISH_REMOVED.value,
                "message": message,
                "branch_action": branch.value,
            },
            "state_cleanup_failed": bool(warnings),
            "state_cleanup_warnings": warnings,
        }
    if outcome == PublicDispatchOutcome.UNCERTAIN:
        message = _FIXED_PUBLIC_MESSAGES[outcome]
        return {
            "ok": False,
            "state": "reconciliation_uncertain",
            "reason": reason.value,
            "workspace_removed": None,
            "agent_stopping": True,
            "chat_remains_open": True,
            "message": message,
            "outcome": {
                "outcome": "uncertain",
                "reason": reason.value,
                "message": message,
            },
        }
    message = _FIXED_PUBLIC_MESSAGES[PublicDispatchOutcome.REFUSED]
    result = {
        "ok": False,
        "state": "refused",
        "reason": reason.value,
        "workspace_removed": False,
        "message": message,
    }
    if fresh_preview_required is not None:
        result["fresh_preview_required"] = bool(fresh_preview_required)
    if reason in {
            PublicDispatchReason.LIVE_INVENTORY_UNSAFE,
            PublicDispatchReason.LIVE_INVENTORY_DRIFT,
            PublicDispatchReason.LIVE_PHYSICAL_DRIFT,
            PublicDispatchReason.FINGERPRINT_MISMATCH}:
        result["recovery"] = _DRIFT_RECOVERY
    if kernel_outcome is not None:
        result["outcome"] = {
            "outcome": "refused",
            "reason": reason.value,
            "message": message,
        }
    return result


def _choice_rejection(reason: str) -> dict:
    return _build_public_dispatch(
        PublicDispatchOutcome.CORRECTION,
        reason=_public_reason(reason, PublicDispatchReason.REQUEST_REFUSED))


def _removed_dispatch_result(dialogue: dict, outcome: dict, *,
                             audit_failed: bool = False) -> dict:
    # Dialogue and envelopes are no longer needed after the kernel's terminal decision. The
    # current index remains as the exact journal-bound recovery anchor until public output flushes.
    try:
        warnings = _cleanup_terminal_projections(
            dialogue, include_challenge=False, include_index=False)
    except Exception:
        warnings = ["local_cleanup_incomplete"]
    _defer_terminal_index_cleanup(dialogue)
    return _build_public_dispatch(
        PublicDispatchOutcome.REMOVED,
        reason=PublicDispatchReason.FINISH_REMOVED,
        kernel_outcome=outcome, cleanup_warnings=warnings,
        audit_failed=audit_failed)


def _uncertain_after_close(dialogue: dict, outcome: dict | None = None) -> dict:
    _defer_terminal_index_cleanup(dialogue)
    return _build_public_dispatch(
        PublicDispatchOutcome.UNCERTAIN,
        reason=PublicDispatchReason.REMOVAL_UNCERTAIN,
        kernel_outcome=outcome)


def dispatch_choice(conversation_id: str, answer: Any = None, *, attachments: Any = None,
                    executor: Callable[..., dict] | None = None) -> dict:
    """Resolve one generation. Hook challenges trust only a consumed choice envelope."""
    dialogue = read_dialogue(conversation_id)
    if dialogue is None:
        return _build_public_dispatch(
            PublicDispatchOutcome.REFUSED,
            reason=PublicDispatchReason.NO_PENDING_DIALOGUE)
    try:
        fin, challenge = _bind_dialogue_challenge(
            dialogue, expected_state="awaiting_choice")
    except Exception as exc:
        return _build_public_dispatch(
            PublicDispatchOutcome.REFUSED,
            reason=_public_reason(
                str(exc) if isinstance(exc, FinishUXError) else "",
                PublicDispatchReason.REQUEST_REFUSED))
    # Cancel is unconditional and mutates no repository state. Retain and Close admit only
    # structurally identical content drift; Retain's selected rows and Close's final proof are
    # checked again in their phase-specific locked paths. Commit and Mixed remain fully strict.
    drift_mode = _pending_choice_drift_mode(
        dialogue, challenge, answer, attachments)
    if drift_mode != "cancel":
        try:
            _assert_live_inventory(
                fin, dialogue, challenge,
                allow_content_drift=drift_mode == "content")
        except Exception as exc:
            return _build_public_dispatch(
                PublicDispatchOutcome.REFUSED,
                reason=_public_reason(
                    str(exc) if isinstance(exc, FinishUXError) else "",
                    PublicDispatchReason.REQUEST_REFUSED))

    if challenge.get("hook_mode"):
        try:
            envelope, reason = _consume_choice_envelope(dialogue)
        except Exception:
            return _build_public_dispatch(
                PublicDispatchOutcome.REFUSED,
                reason=PublicDispatchReason.OPERATION_FAILED)
        if envelope is None:
            return _choice_rejection(reason)
        answer = envelope.get("exact_text")
        attachments = envelope.get("attachments_present")
        try:
            canonical_choice, reason = canonicalize_choice(answer, attachments)
        except Exception:
            return _choice_rejection("choice_not_string")
        if ("canonical_choice" in envelope
                and envelope.get("canonical_choice") != canonical_choice):
            return _choice_rejection("choice_envelope_canonical_mismatch")
        if canonical_choice is None:
            return _choice_rejection(reason)
        try:
            activated, reason = _activate_envelope(
                fin, dialogue, envelope, canonical_choice)
        except Exception:
            activated, reason = False, "request_refused"
        if not activated:
            return _build_public_dispatch(
                PublicDispatchOutcome.REFUSED,
                reason=_public_reason(
                    reason, PublicDispatchReason.REQUEST_REFUSED))
    else:
        try:
            canonical_choice, reason = canonicalize_choice(answer, attachments)
        except Exception:
            return _choice_rejection("choice_not_string")
        if canonical_choice is None:
            return _choice_rejection(reason)

    answer = canonical_choice
    if answer == "Cancel":
        try:
            result = fin.cancel_challenge(
                conversation_id=conversation_id,
                common_dir=dialogue["target"]["common_dir"],
                root=dialogue["target"]["root"], session_id=dialogue["session_id"],
                nonce=dialogue["nonce"], generation=dialogue["generation"])
        except Exception:
            return _build_public_dispatch(
                PublicDispatchOutcome.CANCEL_INCOMPLETE,
                reason=PublicDispatchReason.CANCEL_CLEANUP_INCOMPLETE,
                cleanup_warnings=["local_cleanup_incomplete"])
        if not result.get("inert"):
            return _build_public_dispatch(
                PublicDispatchOutcome.REFUSED,
                reason=PublicDispatchReason.REQUEST_REFUSED)
        try:
            warnings = _cleanup_terminal_projections(
                dialogue, include_challenge=True)
        except Exception:
            warnings = ["local_cleanup_incomplete"]
        transition_reason = str(result.get("reason") or "cancel_transition_failed")
        recoverable = {
            "cancelled", "cancelled_superseded", "lock_busy",
            "challenge_cleanup_failed", "already_cancelled",
        }
        if not result.get("ok") and transition_reason not in recoverable:
            warnings.append("cancel_state_" + transition_reason)
        warnings = sorted(set(warnings))
        if warnings:
            return _build_public_dispatch(
                PublicDispatchOutcome.CANCEL_INCOMPLETE,
                reason=PublicDispatchReason.CANCEL_CLEANUP_INCOMPLETE,
                cleanup_warnings=warnings)
        return _build_public_dispatch(
            PublicDispatchOutcome.CANCELLED,
            reason=PublicDispatchReason.REQUEST_REFUSED)
    if answer in ("Commit", "Retain", "Mixed"):
        dialogue["state"] = {
            "Commit": "awaiting_commit_selection",
            "Retain": "awaiting_retain_selection",
            "Mixed": "awaiting_mixed_selection",
        }[answer]
        try:
            write_dialogue(dialogue)
        except Exception:
            return _build_public_dispatch(
                PublicDispatchOutcome.REFUSED,
                reason=PublicDispatchReason.OPERATION_FAILED)
        return _build_public_dispatch(
            PublicDispatchOutcome.SELECTION,
            selection_state={
                "Commit": PublicSelectionState.COMMIT,
                "Retain": PublicSelectionState.RETAIN,
                "Mixed": PublicSelectionState.MIXED,
            }[answer])

    try:
        target = dialogue["target"]
    except Exception:
        return _build_public_dispatch(
            PublicDispatchOutcome.REFUSED,
            reason=PublicDispatchReason.OPERATION_FAILED)
    shell_invoked = executor is None
    trusted_shell_result = False
    shell_projection = None
    try:
        if executor is None:
            tool = _repo_root() / "kernel" / "bin" / "dev-worktree.sh"
            env = _finish_git_env()
            env["DEV_SESSION_ID"] = dialogue["session_id"]
            env[FINISH_PUBLIC_PROJECTION_ENV] = "1"
            command = [
                "bash", str(tool), "clean", "--finish-current", "--authorization", "Close",
                "--conversation-id", conversation_id,
            ]
            if dialogue.get("hook_mode") is True:
                command.extend([
                    "--expected-nonce", dialogue["nonce"],
                    "--expected-generation", str(dialogue["generation"]),
                ])
            proc = subprocess.run(
                command,
                cwd=target["root"], env=env, capture_output=True, text=True,
            )
            shell_projection = _parse_shell_public_projection(proc.stdout)
            outcome = {"returncode": proc.returncode}
            if shell_projection is not None:
                projected_outcome, projected_reason, projected_branch = shell_projection
                removed_exit = proc.returncode in {0, 3}
                projection_removed = projected_outcome == PublicDispatchOutcome.REMOVED
                projection_nonremoved = projected_outcome in {
                    PublicDispatchOutcome.REFUSED,
                    PublicDispatchOutcome.UNCERTAIN,
                }
                trusted_shell_result = (
                    (projection_removed and removed_exit)
                    or (projection_nonremoved and not removed_exit)
                )
                if trusted_shell_result:
                    outcome.update({
                        "outcome": projected_outcome.value,
                        "reason": projected_reason.value,
                    })
                    if projected_branch is not None:
                        outcome["branch_action"] = projected_branch.value
                else:
                    shell_projection = None
        else:
            outcome = executor(
                target=target, authorization="Close", conversation_id=conversation_id,
                session_id=dialogue["session_id"],
                expected_nonce=dialogue["nonce"],
                expected_generation=dialogue["generation"])
    except Exception:
        return _uncertain_after_close(dialogue)
    if not isinstance(outcome, dict):
        return _uncertain_after_close(dialogue)
    if shell_invoked and not trusted_shell_result:
        try:
            reconciled = fin.reconcile_removal(
                **target, conversation_id=conversation_id,
                session_id=dialogue["session_id"],
                expected_nonce=dialogue["nonce"],
                expected_generation=dialogue["generation"])
        except Exception:
            reconciled = None
        if (isinstance(reconciled, dict)
                and reconciled.get("outcome") == "removed"
                and _public_branch(reconciled.get("branch_action")) is not None):
            return _removed_dispatch_result(dialogue, reconciled)
        if (isinstance(reconciled, dict)
                and reconciled.get("outcome") == "not_removed"):
            return _build_public_dispatch(
                PublicDispatchOutcome.REFUSED,
                reason=PublicDispatchReason.WORKSPACE_PRESERVED,
                kernel_outcome=reconciled,
                fresh_preview_required=True)
        return _uncertain_after_close(dialogue, reconciled)
    removed = (
        outcome.get("outcome") == "removed"
        and _public_branch(outcome.get("branch_action")) is not None
    )
    audit_failed = bool(
        shell_invoked and trusted_shell_result and outcome.get("returncode") == 3)
    if removed:
        return _removed_dispatch_result(
            dialogue, outcome, audit_failed=audit_failed)
    if outcome.get("outcome") == "removed":
        return _uncertain_after_close(dialogue, outcome)
    if outcome.get("outcome") == "uncertain":
        return _uncertain_after_close(dialogue, outcome)
    if outcome.get("outcome") not in {"refused", "error", "not_removed", "absent"}:
        return _uncertain_after_close(dialogue, outcome)
    try:
        terminal = fin.generation_state_status(
            conversation_id, dialogue["nonce"], dialogue["generation"])
    except Exception:
        terminal = "unknown"
    return _build_public_dispatch(
        PublicDispatchOutcome.REFUSED,
        reason=_public_reason(
            outcome.get("reason"), PublicDispatchReason.WORKSPACE_PRESERVED),
        fresh_preview_required=terminal != "live",
        kernel_outcome=outcome)


def _recover_current_removal() -> dict | None:
    """Recover one exact index+journal pair without requiring the deleted dialogue/root."""
    fin = _load_finish()
    candidates: list[tuple[dict, dict]] = []
    unresolved_anchors: list[dict] = []
    expected_session = os.environ.get("DEV_SESSION_ID", "").strip()
    if not _index_dir().is_dir():
        return None
    journal_dir = Path(fin.finish_dir())
    journal_paths = (
        sorted(journal_dir.glob("removal-*.json"))
        if journal_dir.is_dir() else [])
    for path in sorted(_index_dir().glob("index-*.json")):
        index = _json_read(path, CURRENT_INDEX_SCHEMA)
        if index is None or (expected_session and index.get("session_id") != expected_session):
            continue
        exact_journals = []
        for journal_path in journal_paths:
            match = re.fullmatch(r"removal-([0-9a-f]{64})\.json", journal_path.name)
            if match is None:
                continue
            journal, status = fin.read_removal_journal(match.group(1))
            if status != "ok" or journal is None:
                continue
            if all(journal.get(key) == index.get(key) for key in (
                    "root", "session_id", "conversation_id", "generation",
                    "nonce", "fingerprint")):
                exact_journals.append(journal)
        if len(exact_journals) == 1:
            journal = exact_journals[0]
            candidates.append((index, {
                key: journal[key]
                for key in ("root", "git_dir", "common_dir", "branch", "head")
            }))
        elif len(exact_journals) > 1:
            # Multiple independently validated journals for one anchor is impossible under the
            # operation-id binding; report uncertainty rather than selecting by directory order.
            unresolved_anchors.append(index)
        elif not os.path.lexists(str(index.get("root") or "")):
            # A surviving exact current index for an absent root is never projected as preserved.
            unresolved_anchors.append(index)
    if not candidates:
        if len(unresolved_anchors) == 1:
            _defer_terminal_index_cleanup(unresolved_anchors[0])
            return _build_public_dispatch(
                PublicDispatchOutcome.UNCERTAIN,
                reason=PublicDispatchReason.REMOVAL_UNCERTAIN)
        if unresolved_anchors:
            return _build_public_dispatch(
                PublicDispatchOutcome.UNCERTAIN,
                reason=PublicDispatchReason.CURRENT_REMOVAL_AMBIGUOUS)
        return None
    if len(candidates) != 1 or unresolved_anchors:
        return _build_public_dispatch(
            PublicDispatchOutcome.UNCERTAIN,
            reason=PublicDispatchReason.CURRENT_REMOVAL_AMBIGUOUS)
    index, target = candidates[0]
    dialogue = {
        **index,
        "target": target,
    }
    _defer_terminal_index_cleanup(index)
    outcome = fin.reconcile_removal(
        **target, conversation_id=index["conversation_id"],
        session_id=index["session_id"], expected_nonce=index["nonce"],
        expected_generation=index["generation"])
    if (outcome.get("outcome") == "removed"
            and _public_branch(outcome.get("branch_action")) is not None):
        return _removed_dispatch_result(dialogue, outcome)
    if outcome.get("outcome") == "removed":
        return _uncertain_after_close(dialogue, outcome)
    if outcome.get("outcome") == "uncertain":
        return _uncertain_after_close(dialogue, outcome)
    if not os.path.lexists(target["root"]):
        return _uncertain_after_close(dialogue, outcome)
    # The root is provably still present; leave the exact anchor for ordinary live dispatch.
    global _POST_OUTPUT_INDEX_CAS
    _POST_OUTPUT_INDEX_CAS = None
    return None


def dispatch_current(*, executor: Callable[..., dict] | None = None) -> dict:
    if executor is None:
        try:
            recovered = _recover_current_removal()
        except Exception:
            return _build_public_dispatch(
                PublicDispatchOutcome.UNCERTAIN,
                reason=PublicDispatchReason.REMOVAL_UNCERTAIN)
        if recovered is not None:
            return recovered
    try:
        dialogue, _identity = _resolve_current_index()
    except Exception as exc:
        return _build_public_dispatch(
            PublicDispatchOutcome.REFUSED,
            reason=_public_reason(
                str(exc) if isinstance(exc, FinishUXError) else "",
                PublicDispatchReason.REQUEST_REFUSED))
    return dispatch_choice(dialogue["conversation_id"], executor=executor)


def _safe_rel_from_hex(value: str) -> str:
    raw = bytes.fromhex(value)
    rel = os.fsdecode(raw)
    if not rel or os.path.isabs(rel):
        raise FinishUXError("unsafe_artifact_path")
    norm = os.path.normpath(rel)
    if norm == ".." or norm.startswith(".." + os.sep):
        raise FinishUXError("unsafe_artifact_path")
    return norm


def _under(base: Path, path: Path) -> bool:
    base_real = os.path.realpath(base)
    path_real = os.path.realpath(path)
    return path_real == base_real or path_real.startswith(base_real + os.sep)


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_index(data: bytes) -> list[dict]:
    out = []
    for record in filter(None, data.split(b"\x00")):
        meta, sep, path = record.partition(b"\t")
        fields = meta.split()
        if not sep or len(fields) != 3:
            raise FinishUXError("retain_index_parse_failed")
        mode, oid, stage = (field.decode("ascii") for field in fields)
        out.append({"mode": mode, "oid": oid, "stage": int(stage),
                    "path_hex": path.hex()})
    return out


def _parse_tree(data: bytes) -> list[dict]:
    out = []
    for record in filter(None, data.split(b"\x00")):
        meta, sep, path = record.partition(b"\t")
        fields = meta.split()
        if not sep or len(fields) != 3:
            raise FinishUXError("retain_tree_parse_failed")
        mode, typ, oid = (field.decode("ascii") for field in fields)
        out.append({"mode": mode, "type": typ, "oid": oid, "path_hex": path.hex()})
    return out


def _restore_blob_entry(destination: Path, entry: dict, blob: Path) -> None:
    rel = _safe_rel_from_hex(entry["path_hex"])
    out = destination / rel
    _private_dir(out.parent)
    mode = entry["mode"]
    if mode == "120000":
        os.symlink(blob.read_bytes().decode("utf-8", "surrogateescape"), out)
    elif mode in {"100644", "100755"}:
        shutil.copyfile(blob, out)
        out.chmod(0o755 if mode == "100755" else 0o600)
    else:
        raise FinishUXError("unsupported_git_tree_type")


def _capture_path(source: Path, rel: str, payload: Path, records: list[dict]) -> None:
    full = source / rel
    try:
        st = os.lstat(full)
    except FileNotFoundError:
        records.append({"path": rel, "type": "absent"})
        return
    if stat.S_ISLNK(st.st_mode):
        target = os.readlink(full)
        record = {"path": rel, "type": "symlink", "target": target,
                  "mode": stat.S_IMODE(st.st_mode)}
        if os.path.isabs(target):
            resolved = os.path.realpath(full)
            if not _under(source, Path(resolved)):
                raise FinishUXError("symlink_escape")
            record["target_kind"] = "internal_absolute"
            record["target_root_relative"] = os.path.relpath(resolved, source)
        else:
            record["target_kind"] = "relative"
        records.append(record)
        return
    if stat.S_ISREG(st.st_mode):
        dest = payload / rel
        size, digest = _copy_regular_durable(full, dest)
        if size != st.st_size:
            raise FinishUXError("retain_source_changed")
        records.append({"path": rel, "type": "file", "mode": stat.S_IMODE(st.st_mode),
                        "size": size, "sha256": digest})
        return
    if stat.S_ISDIR(st.st_mode):
        records.append({"path": rel, "type": "dir", "mode": stat.S_IMODE(st.st_mode)})
        for dirpath, dirnames, filenames in os.walk(full, topdown=True, followlinks=False):
            dirnames.sort()
            filenames.sort()
            base_rel = os.path.relpath(dirpath, source)
            for name in list(dirnames) + list(filenames):
                child = os.path.normpath(os.path.join(base_rel, name))
                _capture_path(source, child, payload, records)
            dirnames[:] = []
        return
    raise FinishUXError("unsupported_artifact_file_type")


def _snapshot_records(records: list[dict]) -> list[dict]:
    """Normalize captured payload metadata to the kernel selected-snapshot shape."""
    normalized = []
    for item in records:
        value = dict(item)
        if value.get("type") == "symlink" and value.get("target_kind") == "internal_absolute":
            value.pop("target", None)
        normalized.append(value)
    normalized.sort(key=lambda item: (os.fsencode(item["path"]), item["type"]))
    return normalized


def _artifact_path(artifact_id: str) -> Path:
    if not re.fullmatch(r"retain-[0-9a-f]{32}", artifact_id or ""):
        raise FinishUXError("invalid_artifact_id")
    root = _retain_dir()
    path = root / artifact_id
    if not _under(root, path):
        raise FinishUXError("artifact_escape")
    return path


def _publication_paths(artifact_id: str) -> tuple[Path, Path, Path]:
    if not re.fullmatch(r"retain-[0-9a-f]{32}", artifact_id or ""):
        raise FinishUXError("invalid_artifact_id")
    root = _retain_dir()
    return (
        root / f".{artifact_id}.publication.pending.json",
        root / f".{artifact_id}.publication.committed.json",
        root / f".{artifact_id}.publication-tombstone",
    )


def _read_regular_bytes(path: Path, *, limit: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        before_path = os.lstat(path)
        fd = os.open(path, flags)
    except OSError as exc:
        raise FinishUXError("artifact_metadata_invalid") from exc
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before_path.st_mode)
                or before.st_dev != before_path.st_dev or before.st_ino != before_path.st_ino
                or before.st_size < 0 or before.st_size > limit):
            raise FinishUXError("artifact_metadata_invalid")
        chunks = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(fd, min(64 * 1024, remaining))
            if not chunk:
                raise FinishUXError("artifact_metadata_invalid")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(fd, 1):
            raise FinishUXError("artifact_metadata_invalid")
        after = os.fstat(fd)
    finally:
        os.close(fd)
    try:
        after_path = os.lstat(path)
    except OSError as exc:
        raise FinishUXError("artifact_metadata_invalid") from exc
    identity = lambda value: (
        value.st_dev, value.st_ino, stat.S_IFMT(value.st_mode), value.st_size,
        getattr(value, "st_mtime_ns", int(value.st_mtime * 1_000_000_000)),
        getattr(value, "st_ctime_ns", int(value.st_ctime * 1_000_000_000)),
    )
    if identity(before) != identity(after) or identity(before) != identity(after_path):
        raise FinishUXError("artifact_metadata_changed")
    return b"".join(chunks)


def _manifest_document(manifest: Path, *, require_proven: bool,
                       expected_artifact_id: str | None) -> tuple[dict, bytes]:
    try:
        data = _read_regular_bytes(manifest, limit=64 * 1024 * 1024)
        doc = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError, FinishUXError) as exc:
        raise FinishUXError("artifact_manifest_invalid") from exc
    if (not isinstance(doc, dict) or doc.get("schema") != RETAIN_SCHEMA
            or doc.get("protected") is not True):
        raise FinishUXError("artifact_not_protected")
    if (expected_artifact_id is not None
            and doc.get("artifact_id") != expected_artifact_id):
        raise FinishUXError("artifact_identity_mismatch")
    if require_proven and doc.get("restore_proven") is not True:
        raise FinishUXError("artifact_not_restore_proven")
    return doc, data


def _manifest_file(manifest: Path, *, require_proven: bool,
                   expected_artifact_id: str | None) -> dict:
    return _manifest_document(
        manifest, require_proven=require_proven,
        expected_artifact_id=expected_artifact_id)[0]


def _publication_marker_bytes(artifact_id: str, manifest_digest: str) -> bytes:
    marker = {
        "schema": RETAIN_PUBLICATION_SCHEMA,
        "artifact_id": artifact_id,
        "manifest_sha256": manifest_digest,
    }
    return (json.dumps(marker, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _valid_publication_marker(path: Path, artifact_id: str,
                              manifest_digest: str) -> bool:
    try:
        data = _read_regular_bytes(path, limit=64 * 1024)
        marker = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError, FinishUXError):
        return False
    return (
        isinstance(marker, dict)
        and set(marker) == RETAIN_PUBLICATION_KEYS
        and marker.get("schema") == RETAIN_PUBLICATION_SCHEMA
        and marker.get("artifact_id") == artifact_id
        and marker.get("manifest_sha256") == manifest_digest
        and re.fullmatch(r"[0-9a-f]{64}", manifest_digest) is not None
    )


def _publication_status(path: Path, doc: dict, manifest_data: bytes) -> str:
    protocol = doc.get("publication_protocol")
    if protocol is None:
        return "legacy_unlatched"
    if protocol != RETAIN_PUBLICATION_PROTOCOL:
        return "invalid"
    artifact_id = doc.get("artifact_id")
    if (not isinstance(artifact_id, str)
            or re.fullmatch(r"retain-[0-9a-f]{32}", artifact_id) is None
            or doc.get("restore_proven") is not True):
        return "uncommitted"
    _pending, committed, _rollback = _publication_paths(artifact_id)
    digest = hashlib.sha256(manifest_data).hexdigest()
    return (
        "committed"
        if _valid_publication_marker(committed, artifact_id, digest)
        else "uncommitted"
    )


def _manifest(path: Path, *, require_proven: bool = True,
              expected_artifact_id: str | None = None,
              allow_uncommitted: bool = False) -> dict:
    try:
        path_st = os.lstat(path)
    except OSError as exc:
        raise FinishUXError("artifact_manifest_invalid") from exc
    if not stat.S_ISDIR(path_st.st_mode) or stat.S_ISLNK(path_st.st_mode):
        raise FinishUXError("artifact_manifest_invalid")
    doc, data = _manifest_document(
        path / "manifest.json", require_proven=require_proven,
        expected_artifact_id=expected_artifact_id)
    status = _publication_status(path, doc, data)
    if not allow_uncommitted and status not in {"committed", "legacy_unlatched"}:
        raise FinishUXError("artifact_publication_uncommitted")
    return doc


def _object_format(doc: dict) -> str:
    explicit = doc.get("object_format")
    if explicit is not None:
        if explicit not in {"sha1", "sha256"}:
            raise FinishUXError("artifact_object_format_invalid")
        return explicit
    # Legacy v1 artifacts predate the additive field. Infer from their source OIDs.
    oids = [
        str(item.get("oid") or "")
        for key in ("git_blobs", "index_entries", "base_entries")
        for item in (doc.get(key) or []) if isinstance(item, dict)
    ]
    lengths = {len(oid) for oid in oids if re.fullmatch(r"[0-9a-f]+", oid)}
    if not lengths:
        head = str(doc.get("head") or "")
        lengths = {len(head)} if re.fullmatch(r"[0-9a-f]+", head) else set()
    if lengths == {40}:
        return "sha1"
    if lengths == {64}:
        return "sha256"
    raise FinishUXError("artifact_object_format_invalid")


def _restore_git(destination: Path, *args: str, input_data: bytes | str | None = None,
                 text: bool = False, check: bool = False) -> subprocess.CompletedProcess:
    git_dir = destination / ".git"
    try:
        st = os.lstat(git_dir)
    except OSError as exc:
        raise FinishUXError("restore_git_binding_invalid") from exc
    if not stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode):
        raise FinishUXError("restore_git_binding_invalid")
    index_file = git_dir / "index"
    command = [
        "git", "--git-dir=" + str(git_dir),
        "--work-tree=" + str(destination), *args,
    ]
    return subprocess.run(
        command, input=input_data, capture_output=True, text=text, check=check,
        env=_finish_git_env(index_file=str(index_file)))


def _install_raw_git_blobs(doc: dict, destination: Path, blobs: Path) -> None:
    for blob in doc.get("git_blobs") or []:
        blob_path = blobs / blob["oid"]
        if (not blob_path.is_file() or blob_path.is_symlink()
                or blob_path.stat().st_size != blob["size"]
                or _sha_file(blob_path) != blob["sha256"]):
            raise FinishUXError("artifact_git_blob_mismatch")
        written = _restore_git(
            destination, "hash-object", "-w", "--no-filters", "--stdin",
            input_data=blob_path.read_bytes())
        if written.returncode != 0 or written.stdout.decode("ascii", "strict").strip() != blob["oid"]:
            raise FinishUXError("restore_git_blob_write_failed")


def _index_info(entries: list[dict], *, staged: bool) -> bytes:
    lines = []
    for entry in entries:
        _safe_rel_from_hex(entry["path_hex"])
        path = bytes.fromhex(entry["path_hex"])
        if staged:
            prefix = f"{entry['mode']} {entry['oid']} {entry['stage']}\t".encode("ascii")
        else:
            prefix = f"{entry['mode']} {entry['oid']}\t".encode("ascii")
        lines.append(prefix + path + b"\x00")
    return b"".join(lines)


def _operation_artifact_state(doc: dict, artifact: Path) -> dict | None:
    state = doc.get("operation_state")
    if state is None:
        return None
    if (not isinstance(state, dict)
            or set(state) != RETAIN_OPERATION_STATE_KEYS
            or state.get("schema") != "awa-retain-operation-state/v1"
            or state.get("admin_root") != "git-state/admin"):
        raise FinishUXError("artifact_operation_state_invalid")
    operation = state.get("operation_manifest")
    selected_groups = state.get("selected_groups")
    if (not isinstance(operation, dict) or operation.get("active") is not True
            or operation.get("digest") != state.get("operation_digest")
            or operation.get("digest") != _load_finish()._operation_manifest_digest(operation)
            or not isinstance(selected_groups, list) or not selected_groups
            or len(selected_groups) != len(set(selected_groups))
            or any(group not in (operation.get("groups") or [])
                   for group in selected_groups)):
        raise FinishUXError("artifact_operation_state_invalid")
    metadata = (
        (state.get("raw_index"), "git-state/index"),
        (state.get("object_pack"), "git-state/objects.pack"),
    )
    for item, expected_path in metadata:
        if (not isinstance(item, dict)
                or set(item) != {"path", "size", "sha256"}
                or item.get("path") != expected_path
                or type(item.get("size")) is not int or item["size"] < 0
                or re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256") or "")) is None):
            raise FinishUXError("artifact_operation_state_invalid")
        data = _read_regular_bytes(
            artifact / expected_path, limit=max(1, item["size"] + 1))
        if len(data) != item["size"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise FinishUXError("artifact_operation_payload_mismatch")
    return state


def _restore_operation_ref_state(destination: Path, operation: dict) -> None:
    refs: dict[str, str] = {}
    for item in operation.get("refs") or []:
        if not isinstance(item, dict) or item.get("kind") == "pseudo":
            continue
        try:
            name = os.fsdecode(bytes.fromhex(item["name_hex"]))
        except (KeyError, TypeError, ValueError):
            raise FinishUXError("artifact_operation_ref_invalid")
        oid = item.get("oid")
        if (not name.startswith("refs/")
                or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", str(oid or "")) is None
                or (name in refs and refs[name] != oid)):
            raise FinishUXError("artifact_operation_ref_invalid")
        refs[name] = oid
    for name in sorted(refs, key=os.fsencode):
        check = _restore_git(destination, "check-ref-format", name)
        if check.returncode != 0 or check.stdout or check.stderr:
            raise FinishUXError("artifact_operation_ref_invalid")
        if _restore_git(destination, "update-ref", name, refs[name]).returncode != 0:
            raise FinishUXError("restore_operation_ref_failed")
    symbolic = operation.get("head_symbolic_ref")
    head_oid = operation.get("head_oid")
    if symbolic:
        if symbolic not in refs:
            raise FinishUXError("artifact_operation_head_invalid")
        if _restore_git(destination, "symbolic-ref", "HEAD", symbolic).returncode != 0:
            raise FinishUXError("restore_operation_head_failed")
    else:
        if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", str(head_oid or "")) is None:
            raise FinishUXError("artifact_operation_head_invalid")
        if _restore_git(
                destination, "update-ref", "--no-deref", "HEAD", head_oid).returncode != 0:
            raise FinishUXError("restore_operation_head_failed")


def _restore_operation_stage_zero(destination: Path, operation: dict) -> None:
    entries = operation.get("index_entries")
    if entries is None:
        # Operation manifest v1 derives these from the index listing; artifacts persist the parsed
        # records additively so restore never needs to infer stages from a mutable source.
        entries = []
    for entry in entries:
        if entry.get("stage") != 0:
            continue
        rel = _safe_rel_from_hex(entry["path_hex"])
        out = destination / rel
        if not _under(destination, out):
            raise FinishUXError("restore_operation_path_escape")
        blob = _restore_git(destination, "cat-file", "blob", entry["oid"])
        if blob.returncode != 0:
            raise FinishUXError("restore_operation_blob_missing")
        _private_dir(out.parent)
        mode = entry.get("mode")
        if mode == "120000":
            os.symlink(blob.stdout.decode("utf-8", "surrogateescape"), out)
        elif mode in {"100644", "100755"}:
            _private_write(out, blob.stdout)
            out.chmod(0o755 if mode == "100755" else 0o600)
        elif mode == "160000":
            # Nested repositories are refused by inventory, so an operation artifact cannot safely
            # manufacture a submodule working tree.
            raise FinishUXError("restore_operation_gitlink_unsupported")
        else:
            raise FinishUXError("restore_operation_mode_invalid")


def _restore_operation_admin(
        artifact: Path, destination: Path, state: dict) -> None:
    operation = state["operation_manifest"]
    admin_source = artifact / state["admin_root"]
    admin_destination = destination / ".git"
    records = operation.get("admin_records")
    if not isinstance(records, list):
        raise FinishUXError("artifact_operation_admin_invalid")
    directories = [item for item in records if item.get("type") == "dir"]
    files = [item for item in records if item.get("type") == "file"]
    if len(directories) + len(files) != len(records):
        raise FinishUXError("artifact_operation_admin_invalid")
    for item in sorted(directories, key=lambda value: len(bytes.fromhex(value["path_hex"]))):
        rel = _safe_rel_from_hex(item["path_hex"])
        out = admin_destination / rel
        if not _under(admin_destination, out):
            raise FinishUXError("restore_operation_admin_escape")
        _private_dir(out)
    for item in sorted(files, key=lambda value: bytes.fromhex(value["path_hex"])):
        rel = _safe_rel_from_hex(item["path_hex"])
        source = admin_source / rel
        out = admin_destination / rel
        if not _under(admin_source, source) or not _under(admin_destination, out):
            raise FinishUXError("restore_operation_admin_escape")
        size, digest = _copy_regular_durable(source, out)
        if size != item.get("size") or digest != item.get("sha256"):
            raise FinishUXError("artifact_operation_admin_mismatch")
        out.chmod(int(item.get("mode", 0o600)) & 0o777)
    for item in sorted(
            directories, key=lambda value: len(bytes.fromhex(value["path_hex"])),
            reverse=True):
        rel = _safe_rel_from_hex(item["path_hex"])
        (admin_destination / rel).chmod(int(item.get("mode", 0o700)) & 0o777)


def _restore_retain_path(artifact: Path, artifact_id: str, destination: str, *,
                         require_proven: bool) -> dict:
    doc = _manifest(
        artifact, require_proven=require_proven,
        expected_artifact_id=artifact_id,
        allow_uncommitted=not require_proven)
    dest = Path(os.path.abspath(destination))
    if dest.exists() and any(dest.iterdir()):
        raise FinishUXError("restore_destination_not_empty")
    _private_dir(dest)
    payload = artifact / "payload"
    blobs = artifact / "git-blobs"
    operation_state = _operation_artifact_state(doc, artifact)
    if (require_proven and operation_state is not None
            and doc.get("operation_abort_proven") is not True):
        raise FinishUXError("artifact_operation_not_abort_proven")
    if doc.get("base_entries") is not None or operation_state is not None:
        object_format = _object_format(doc)
        init = subprocess.run(
            ["git", "init", "-q", f"--object-format={object_format}", str(dest)],
            capture_output=True, text=True, env=_finish_git_env())
        if init.returncode != 0:
            raise FinishUXError("restore_git_init_failed")
    if operation_state is not None:
        pack_meta = operation_state["object_pack"]
        pack_data = _read_regular_bytes(
            artifact / pack_meta["path"], limit=max(1, pack_meta["size"] + 1))
        installed = _restore_git(
            dest, "index-pack", "--stdin", input_data=pack_data)
        if installed.returncode != 0:
            raise FinishUXError("restore_operation_pack_failed")
        operation = operation_state["operation_manifest"]
        _restore_operation_ref_state(dest, operation)
        _restore_operation_stage_zero(dest, operation)
    elif doc.get("base_entries") is not None:
        _install_raw_git_blobs(doc, dest, blobs)
        if _restore_git(dest, "read-tree", "--empty").returncode != 0:
            raise FinishUXError("restore_git_index_failed")
        base_info = _index_info(doc["base_entries"], staged=False)
        if base_info:
            updated = _restore_git(
                dest, "update-index", "-z", "--index-info", input_data=base_info)
            if updated.returncode != 0:
                raise FinishUXError("restore_git_index_failed")
        tree = _restore_git(dest, "write-tree", text=True)
        if tree.returncode != 0:
            raise FinishUXError("restore_git_tree_failed")
        commit = _restore_git(
            dest, "-c", "user.name=AWA Retain Restore",
            "-c", "user.email=awa-retain@example.invalid",
            "commit-tree", tree.stdout.strip(), "-m", "AWA retained baseline",
            text=True)
        if commit.returncode != 0:
            raise FinishUXError("restore_git_commit_failed")
        ref = "refs/heads/awa-retain-baseline"
        if _restore_git(dest, "update-ref", ref, commit.stdout.strip()).returncode != 0:
            raise FinishUXError("restore_git_ref_failed")
        if _restore_git(dest, "symbolic-ref", "HEAD", ref).returncode != 0:
            raise FinishUXError("restore_git_ref_failed")
    for item in sorted(doc["entries"], key=lambda x: (x["path"].count(os.sep), x["path"])):
        out = dest / item["path"]
        if not _under(dest, out):
            raise FinishUXError("restore_path_escape")
        typ = item["type"]
        if typ == "absent":
            if out.exists() or out.is_symlink():
                if out.is_dir() and not out.is_symlink():
                    shutil.rmtree(out)
                else:
                    out.unlink()
        elif typ == "dir":
            if out.is_symlink() or (out.exists() and not out.is_dir()):
                out.unlink()
            _private_dir(out)
            out.chmod(int(item.get("mode", 0o700)) & 0o777)
        elif typ == "file":
            _private_dir(out.parent)
            if out.is_symlink() or (out.exists() and not out.is_file()):
                if out.is_dir() and not out.is_symlink():
                    shutil.rmtree(out)
                else:
                    out.unlink()
            shutil.copyfile(payload / item["path"], out, follow_symlinks=False)
            out.chmod(int(item.get("mode", 0o600)) & 0o777)
        elif typ == "symlink":
            _private_dir(out.parent)
            if out.exists() or out.is_symlink():
                if out.is_dir() and not out.is_symlink():
                    shutil.rmtree(out)
                else:
                    out.unlink()
            target = item["target"]
            if item.get("target_kind") == "internal_absolute":
                target = str(dest / item["target_root_relative"])
            os.symlink(target, out)
        else:
            raise FinishUXError("unknown_artifact_entry_type")
    # Child restoration uses private parent creation; reapply captured directory modes last.
    for item in sorted(
            (entry for entry in doc["entries"] if entry.get("type") == "dir"),
            key=lambda entry: entry["path"].count(os.sep), reverse=True):
        (dest / item["path"]).chmod(int(item.get("mode", 0o700)) & 0o777)
    if operation_state is not None:
        raw_meta = operation_state["raw_index"]
        raw_index = _read_regular_bytes(
            artifact / raw_meta["path"], limit=max(1, raw_meta["size"] + 1))
        _private_write(dest / ".git" / "index", raw_index)
        _restore_operation_admin(artifact, dest, operation_state)
    elif doc.get("index_entries") is not None:
        selected_paths = doc.get("selected_paths") or []
        _restore_git(
            dest, "-c", "core.fsmonitor=false", "rm", "-r", "--cached",
            "--ignore-unmatch", "--", *selected_paths)
        lines = _index_info(doc["index_entries"], staged=True)
        if lines:
            updated = _restore_git(
                dest, "update-index", "-z", "--index-info", input_data=lines)
            if updated.returncode != 0:
                raise FinishUXError("restore_git_index_failed")
    ignored = doc.get("ignore_intent") or []
    if ignored:
        exclude = dest / ".git" / "info" / "exclude"
        if exclude.parent.is_dir():
            with exclude.open("a", encoding="utf-8") as fh:
                fh.write("\n# Restored by AWA protected Retain\n")
                fh.write("\n".join(ignored) + "\n")
        else:
            _private_write(dest / ".awa-retain-ignore",
                           ("\n".join(ignored) + "\n").encode("utf-8"))
    return {"artifact_id": artifact_id, "destination": str(dest),
            "restored_entries": len(doc["entries"]), "ignore_intent_applied": bool(ignored)}


def restore_retain(artifact_id: str, destination: str) -> dict:
    _resume_retain_publications()
    return _restore_retain_path(
        _artifact_path(artifact_id), artifact_id, destination,
        require_proven=True)


def _verify_restored(doc: dict, destination: Path) -> None:
    for item in doc["entries"]:
        out = destination / item["path"]
        typ = item["type"]
        if typ == "absent":
            if out.exists() or out.is_symlink():
                raise FinishUXError("restore_proof_absence_mismatch")
        elif typ == "dir":
            if (not out.is_dir() or out.is_symlink()
                    or (out.stat().st_mode & 0o777)
                    != (int(item.get("mode", 0o700)) & 0o777)):
                raise FinishUXError("restore_proof_type_mismatch")
        elif typ == "file":
            if (not out.is_file() or out.is_symlink() or _sha_file(out) != item["sha256"]
                    or (out.stat().st_mode & 0o777) != (int(item.get("mode", 0o600)) & 0o777)):
                raise FinishUXError("restore_proof_content_mismatch")
        elif typ == "symlink":
            expected = item["target"]
            if item.get("target_kind") == "internal_absolute":
                expected = str(destination / item["target_root_relative"])
            if not out.is_symlink() or os.readlink(out) != expected:
                raise FinishUXError("restore_proof_link_mismatch")
    # Prove exact child topology for every captured directory. This detects an omitted or added
    # empty descendant without treating the restore repository's own .git metadata as payload.
    entries_by_path = {
        item["path"]: item for item in doc["entries"]
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }
    for item in doc["entries"]:
        if item.get("type") != "dir":
            continue
        expected_children = sorted(
            os.path.basename(path)
            for path in entries_by_path
            if os.path.dirname(path) == item["path"])
        try:
            actual_children = sorted(
                child.name for child in os.scandir(destination / item["path"]))
        except OSError as exc:
            raise FinishUXError("restore_proof_topology_mismatch") from exc
        if actual_children != expected_children:
            raise FinishUXError("restore_proof_topology_mismatch")
    operation_state = doc.get("operation_state")
    if operation_state is not None:
        operation = operation_state.get("operation_manifest")
        if not isinstance(operation, dict):
            raise FinishUXError("restore_proof_operation_missing")
        raw_index_path = destination / ".git" / "index"
        raw_meta = operation_state.get("raw_index") or {}
        raw_index = _read_regular_bytes(
            raw_index_path, limit=max(1, int(raw_meta.get("size", -1)) + 1))
        if (len(raw_index) != raw_meta.get("size")
                or hashlib.sha256(raw_index).hexdigest() != raw_meta.get("sha256")):
            raise FinishUXError("restore_proof_raw_index_mismatch")
        fin = _load_finish()
        binding = fin.validated_git_binding(str(destination), allow_primary=True)
        status = _restore_git(
            destination, "-c", "core.quotepath=false",
            "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
            "status", "--porcelain=v1", "-z", "--untracked-files=all",
            "--ignored=matching")
        index = _restore_git(
            destination, "-c", "core.fsmonitor=false",
            "-c", "core.untrackedCache=false",
            "ls-files", "--stage", "-z")
        if status.returncode != 0 or index.returncode != 0:
            raise FinishUXError("restore_proof_operation_status_failed")
        restored_operation = fin._capture_operation_manifest(
            binding, status_bytes=status.stdout, index_listing=index.stdout,
            raw_index=raw_index)
        if restored_operation != operation:
            raise FinishUXError("restore_proof_operation_mismatch")
        closure = operation.get("object_closure")
        if not isinstance(closure, list) or not closure:
            raise FinishUXError("restore_proof_object_closure_missing")
        query = "".join(item["oid"] + "\n" for item in closure).encode("ascii")
        checked = _restore_git(
            destination, "cat-file",
            "--batch-check=%(objectname) %(objecttype) %(objectsize)",
            input_data=query)
        expected = [
            f"{item['oid']} {item['type']} {item['size']}"
            for item in closure
        ]
        if (checked.returncode != 0
                or checked.stdout.decode("ascii", "strict").splitlines() != expected):
            raise FinishUXError("restore_proof_object_closure_mismatch")
        _verify_operation_abort(operation, destination)
        return
    snapshot = doc.get("selected_snapshot")
    selected_paths = doc.get("selected_paths") or []
    if (not isinstance(snapshot, dict)
            or snapshot.get("selected_paths") != selected_paths):
        raise FinishUXError("restore_proof_snapshot_missing")
    # Prove the exact raw Git state without invoking a configured clean/smudge/filter process.
    # Filesystem records above prove worktree bytes; these two plumbing reads prove the selected
    # real-index stages and baseline tree. Raw blob OIDs were independently re-hashed with
    # --no-filters while installing them.
    actual_index = _restore_git(
        destination, "-c", "core.fsmonitor=false",
        "-c", "core.untrackedCache=false",
        "ls-files", "--stage", "-z", "--", *selected_paths)
    if (actual_index.returncode != 0
            or actual_index.stdout.hex() != doc.get("index_snapshot_hex")):
        raise FinishUXError("restore_proof_index_mismatch")
    actual_tree = _restore_git(
        destination, "ls-tree", "-rz", "HEAD", "--", *selected_paths)
    if (actual_tree.returncode != 0
            or _parse_tree(actual_tree.stdout) != (doc.get("base_entries") or [])):
        raise FinishUXError("restore_proof_tree_mismatch")
    actual_format = _restore_git(
        destination, "rev-parse", "--show-object-format", text=True)
    if (actual_format.returncode != 0
            or actual_format.stdout.strip() != _object_format(doc)):
        raise FinishUXError("restore_proof_object_format_mismatch")


def _verify_operation_abort(operation: dict, destination: Path) -> None:
    groups = operation.get("groups")
    if not isinstance(groups, list) or len(groups) != 1:
        raise FinishUXError("restore_proof_operation_ambiguous")
    command = {
        "merge": ("merge", "--abort"),
        "sequence": ("cherry-pick", "--abort"),
        "rebase-merge": ("rebase", "--abort"),
        "rebase-apply": ("rebase", "--abort"),
        "am": ("am", "--abort"),
        "bisect": ("bisect", "reset"),
        "notes-merge": ("notes", "merge", "--abort"),
    }.get(groups[0])
    if command is None:
        raise FinishUXError("restore_proof_operation_unsupported")
    abort_copy = destination.parent / (
        "." + destination.name + ".abort." + uuid.uuid4().hex)
    try:
        shutil.copytree(destination, abort_copy, symlinks=True)
        hooks = abort_copy / ".git" / "awa-proof-empty-hooks"
        _private_dir(hooks)
        result = _restore_git(
            abort_copy,
            "-c", "core.hooksPath=" + str(hooks),
            "-c", "core.fsmonitor=false",
            "-c", "core.untrackedCache=false",
            "-c", "merge.renormalize=false",
            *command)
        if result.returncode != 0:
            raise FinishUXError("restore_proof_operation_abort_failed")
        fin = _load_finish()
        binding = fin.validated_git_binding(str(abort_copy), allow_primary=True)
        status = _restore_git(
            abort_copy, "-c", "core.fsmonitor=false",
            "-c", "core.untrackedCache=false",
            "status", "--porcelain=v1", "-z", "--untracked-files=all",
            "--ignored=matching")
        index = _restore_git(
            abort_copy, "-c", "core.fsmonitor=false",
            "-c", "core.untrackedCache=false",
            "ls-files", "--stage", "-z")
        raw_index = _read_regular_bytes(
            Path(binding["index_file"]), limit=1024 * 1024 * 1024)
        if status.returncode != 0 or index.returncode != 0:
            raise FinishUXError("restore_proof_operation_abort_failed")
        after = fin._capture_operation_manifest(
            binding, status_bytes=status.stdout, index_listing=index.stdout,
            raw_index=raw_index)
        if after.get("active") is not False:
            raise FinishUXError("restore_proof_operation_abort_incomplete")
    finally:
        if abort_copy.exists():
            shutil.rmtree(abort_copy)


def _owned_uncommitted_artifact(path: Path, artifact_id: str) -> tuple[dict, bytes]:
    doc, data = _manifest_document(
        path / "manifest.json", require_proven=False,
        expected_artifact_id=artifact_id)
    if doc.get("publication_protocol") != RETAIN_PUBLICATION_PROTOCOL:
        raise FinishUXError("artifact_publication_not_owned")
    common_dir = doc.get("git_common_dir")
    if not isinstance(common_dir, str) or not os.path.isabs(common_dir):
        raise FinishUXError("artifact_publication_not_owned")
    return doc, data


def _resume_retain_publications() -> list[str]:
    """Promote a sole final+pending artifact without ever deleting payload candidates.

    Pending is a durable witness, not disposable rollback metadata. Staging/rollback, mismatches,
    and multiple payload candidates stay byte-for-byte preserved for explicit repair.
    """
    root = _retain_dir()
    if not root.is_dir() or root.is_symlink():
        return []
    artifact_ids = set()
    patterns = (
        re.compile(r"^(retain-[0-9a-f]{32})$"),
        re.compile(r"^\.(retain-[0-9a-f]{32})\.staging$"),
        re.compile(r"^\.(retain-[0-9a-f]{32})\.publication-tombstone$"),
        re.compile(r"^\.(retain-[0-9a-f]{32})\.publication\.pending\.json$"),
        re.compile(r"^\.(retain-[0-9a-f]{32})\.publication\.committed\.json$"),
    )
    try:
        children = list(root.iterdir())
    except OSError:
        return ["publication_cleanup_incomplete"]
    for child in children:
        for pattern in patterns:
            match = pattern.fullmatch(child.name)
            if match:
                artifact_ids.add(match.group(1))
                break
    warnings: list[str] = []
    fin = _load_finish()
    for artifact_id in sorted(artifact_ids):
        final = _artifact_path(artifact_id)
        staging = root / ("." + artifact_id + ".staging")
        pending, committed, rollback = _publication_paths(artifact_id)
        try:
            candidates = [
                candidate for candidate in (rollback, final, staging)
                if os.path.lexists(candidate)
            ]
            if not candidates:
                if os.path.lexists(pending) or os.path.lexists(committed):
                    warnings.append("publication_repair_required")
                continue
            if len(candidates) != 1:
                warnings.append("publication_repair_required")
                continue
            selected = candidates[0]
            selected_st = os.lstat(selected)
            if not stat.S_ISDIR(selected_st.st_mode) or stat.S_ISLNK(selected_st.st_mode):
                warnings.append("publication_repair_required")
                continue
            doc, manifest_data = _manifest_document(
                selected / "manifest.json", require_proven=False,
                expected_artifact_id=artifact_id)
            if doc.get("publication_protocol") is None:
                # Markerless legacy artifacts remain reader-compatible and need no promotion.
                continue
            if (doc.get("publication_protocol") != RETAIN_PUBLICATION_PROTOCOL
                    or doc.get("restore_proven") is not True):
                warnings.append("publication_repair_required")
                continue
            digest = hashlib.sha256(manifest_data).hexdigest()
            pending_valid = _valid_publication_marker(
                pending, artifact_id, digest)
            committed_valid = _valid_publication_marker(
                committed, artifact_id, digest)
            pending_present = os.path.lexists(pending)
            committed_present = os.path.lexists(committed)
            if ((pending_present and not pending_valid)
                    or (committed_present and not committed_valid)):
                warnings.append("publication_repair_required")
                continue
            # Staging/rollback is intentionally hidden and untrusted even with a valid pending
            # witness. Recovery never moves or removes it automatically.
            if selected != final:
                warnings.append("publication_repair_required")
                continue
            if not committed_valid and not pending_valid:
                warnings.append("publication_repair_required")
                continue
            with fin.common_dir_lock(
                    doc["git_common_dir"], blocking=False, timeout=0.0):
                current_candidates = [
                    candidate for candidate in (rollback, final, staging)
                    if os.path.lexists(candidate)
                ]
                if len(current_candidates) != 1 or current_candidates[0] != final:
                    warnings.append("publication_repair_required")
                    continue
                current_doc, current_data = _manifest_document(
                    final / "manifest.json", require_proven=True,
                    expected_artifact_id=artifact_id)
                current_digest = hashlib.sha256(current_data).hexdigest()
                if (current_doc.get("publication_protocol") != RETAIN_PUBLICATION_PROTOCOL
                        or current_digest != digest):
                    warnings.append("publication_repair_required")
                    continue
                current_pending_valid = _valid_publication_marker(
                    pending, artifact_id, digest)
                current_committed_valid = _valid_publication_marker(
                    committed, artifact_id, digest)
                if (os.path.lexists(committed) and not current_committed_valid):
                    warnings.append("publication_repair_required")
                    continue
                if not current_committed_valid:
                    if not current_pending_valid:
                        warnings.append("publication_repair_required")
                        continue
                    # Copy, never rename, the pending witness. _private_write fsyncs the marker and
                    # its parent before committed trust exists; pending remains through that point.
                    marker_data = _read_regular_bytes(pending, limit=64 * 1024)
                    _private_write(committed, marker_data)
                    if not _valid_publication_marker(
                            committed, artifact_id, digest):
                        warnings.append("publication_recovery_incomplete")
                        continue
                # Pending cleanup is optional and strictly post-commit. Any failure leaves a valid
                # committed artifact and is surfaced without touching payload bytes.
                if current_pending_valid and os.path.lexists(pending):
                    try:
                        pending.unlink()
                        _sync_dir(root)
                    except OSError:
                        warnings.append("publication_pending_cleanup_incomplete")
        except Exception:
            warnings.append("publication_recovery_incomplete")
    return sorted(set(warnings))


def _selected_operation(selected: list[dict], inventory: dict) -> tuple[dict | None, list[str]]:
    operation_rows = [entry for entry in selected if entry.get("template_id") == "operation"]
    if not operation_rows:
        return None, []
    operation = inventory.get("operation_manifest")
    if (not isinstance(operation, dict) or operation.get("active") is not True
            or not isinstance(operation.get("digest"), str)):
        raise FinishUXError("retain_operation_state_missing")
    selected_groups = []
    active_groups = operation.get("groups")
    if not isinstance(active_groups, list):
        raise FinishUXError("retain_operation_state_invalid")
    for row in operation_rows:
        group = row.get("operation_group")
        if (not isinstance(group, str) or group not in active_groups
                or row.get("operation_digest") != operation["digest"]
                or row.get("operation_manifest") != operation):
            raise FinishUXError("retain_operation_state_changed")
        if group not in selected_groups:
            selected_groups.append(group)
    return operation, sorted(selected_groups)


def _capture_operation_payload(tmp: Path, target: dict, operation: dict,
                               selected_groups: list[str]) -> dict:
    fin = _load_finish()
    if operation.get("digest") != fin._operation_manifest_digest(operation):
        raise FinishUXError("retain_operation_digest_invalid")
    state_root = tmp / "git-state"
    admin_root = state_root / "admin"
    _private_dir(admin_root)
    git_dir = Path(target["git_dir"])
    raw_index_path = state_root / "index"
    index_size, index_digest = _copy_regular_durable(
        Path(fin.validated_git_binding(target["root"])["index_file"]), raw_index_path)
    raw_index = operation.get("raw_index")
    if (not isinstance(raw_index, dict)
            or set(raw_index) != {"size", "sha256"}):
        raise FinishUXError("retain_operation_index_invalid")
    if (index_size != raw_index.get("size") or index_digest != raw_index.get("sha256")
            or len(_read_regular_bytes(
                raw_index_path, limit=max(1, index_size + 1))) != index_size):
        raise FinishUXError("retain_operation_index_changed")

    admin_records = operation.get("admin_records")
    if not isinstance(admin_records, list):
        raise FinishUXError("retain_operation_admin_invalid")
    directories = [item for item in admin_records if item.get("type") == "dir"]
    files = [item for item in admin_records if item.get("type") == "file"]
    if len(directories) + len(files) != len(admin_records):
        raise FinishUXError("retain_operation_admin_invalid")
    for item in sorted(directories, key=lambda value: len(bytes.fromhex(value["path_hex"]))):
        rel = _safe_rel_from_hex(item["path_hex"])
        destination = admin_root / rel
        if not _under(admin_root, destination):
            raise FinishUXError("retain_operation_admin_escape")
        _private_dir(destination)
    for item in sorted(files, key=lambda value: bytes.fromhex(value["path_hex"])):
        rel = _safe_rel_from_hex(item["path_hex"])
        source = git_dir / rel
        destination = admin_root / rel
        if not _under(git_dir, source) or not _under(admin_root, destination):
            raise FinishUXError("retain_operation_admin_escape")
        size, digest = _copy_regular_durable(source, destination)
        if size != item.get("size") or digest != item.get("sha256"):
            raise FinishUXError("retain_operation_admin_changed")

    closure = operation.get("object_closure")
    if (not isinstance(closure, list) or not closure
            or any(not isinstance(item, dict)
                   or re.fullmatch(
                       r"[0-9a-f]{40}|[0-9a-f]{64}",
                       str(item.get("oid") or "")) is None
                   for item in closure)):
        raise FinishUXError("retain_operation_objects_invalid")
    closure_oids = [item["oid"] for item in closure]
    pack = _git_bytes_input(
        target["root"], "pack-objects", "--stdout", "--delta-base-offset",
        input_data=("".join(oid + "\n" for oid in closure_oids)).encode("ascii"))
    if pack.returncode != 0 or not pack.stdout:
        raise FinishUXError("retain_operation_pack_failed")
    pack_path = state_root / "objects.pack"
    _private_write(pack_path, pack.stdout)
    return {
        "schema": "awa-retain-operation-state/v1",
        "operation_digest": operation["digest"],
        "selected_groups": selected_groups,
        "operation_manifest": operation,
        "raw_index": {
            "path": "git-state/index",
            "size": index_size,
            "sha256": index_digest,
        },
        "admin_root": "git-state/admin",
        "object_pack": {
            "path": "git-state/objects.pack",
            "size": len(pack.stdout),
            "sha256": hashlib.sha256(pack.stdout).hexdigest(),
        },
    }


def create_retain(conversation_id: str, indices: list[int], *,
                  allow_secrets: bool = False,
                  allow_ignored_dependencies: bool = False,
                  lock_timeout: float = 30.0,
                  _claimed: bool = False) -> dict:
    dialogue = read_dialogue(conversation_id)
    if dialogue is None or (_claimed and dialogue.get("state") != "executing_mixed"):
        raise FinishUXError("wrong_dialogue_state")
    selected = _selected(dialogue, indices)
    if (any(e.get("template_id") == "secret"
            or e.get("contains_secret_dependencies") is True for e in selected)
            and not allow_secrets):
        raise FinishUXError("explicit_secret_confirmation_required")
    if (any(e.get("contains_ignored_dependencies") is True for e in selected)
            and not allow_ignored_dependencies):
        raise FinishUXError("explicit_ignored_confirmation_required")
    if not _claimed:
        dialogue = _claim_action(
            conversation_id, "awaiting_retain_selection", "retaining",
            lock_timeout=lock_timeout, allow_content_drift=True,
            selected_indices=indices)
        selected = _selected(dialogue, indices)
    target = dialogue["target"]
    fin = _load_finish()
    artifact_id = "retain-" + uuid.uuid4().hex
    root = _retain_dir()
    _private_dir(root)
    cleanup_warnings = _resume_retain_publications()
    final = _artifact_path(artifact_id)
    tmp = root / ("." + artifact_id + ".staging")
    pending, committed, rollback = _publication_paths(artifact_id)
    records: list[dict] = []
    rels: list[str] = []
    for entry in selected:
        for raw_hex in entry.get("paths_hex") or []:
            rel = _safe_rel_from_hex(raw_hex)
            if rel not in rels:
                rels.append(rel)
    rels.sort()
    publication_committed = False
    try:
        with fin.common_dir_lock(target["common_dir"], blocking=True, timeout=lock_timeout):
            _validate_dialogue_live(
                dialogue,
                expected_state="executing_mixed" if _claimed else "retaining",
                lock_held=True,
                allow_content_drift=not _claimed,
                selected_indices=None if _claimed else indices)
            live_inventory = fin.build_inventory(target["root"], target["git_dir"])
            if not live_inventory.get("safe"):
                raise FinishUXError("retain_operation_inventory_unsafe")
            operation, selected_operation_groups = _selected_operation(
                selected, live_inventory)
            if operation is not None:
                for raw_hex in operation.get("dependencies_hex") or []:
                    rel = _safe_rel_from_hex(raw_hex)
                    if rel not in rels:
                        rels.append(rel)
                rels.sort()
            if any(os.path.lexists(path) for path in (
                    final, tmp, pending, committed, rollback)):
                raise FinishUXError("retain_publication_collision")
            _private_dir(tmp)
            payload = tmp / "payload"
            _private_dir(payload)
            for rel in rels:
                _capture_path(Path(target["root"]), rel, payload, records)
            records.sort(key=lambda x: (x["path"], x["type"]))
            status = _git_bytes(
                target["root"], "-c", "core.quotepath=false",
                "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
                "status", "--porcelain=v1", "-z", "--untracked-files=all",
                "--ignored=matching", "--", *rels)
            index = _git_bytes(
                target["root"], "-c", "core.fsmonitor=false",
                "-c", "core.untrackedCache=false",
                "ls-files", "--stage", "-z", "--", *rels)
            tree = _git_bytes(target["root"], "ls-tree", "-rz", "HEAD", "--", *rels)
            object_format_result = _git(
                target["root"], "rev-parse", "--show-object-format")
            if status.returncode != 0 or index.returncode != 0:
                raise FinishUXError("retain_status_capture_failed")
            if tree.returncode != 0:
                raise FinishUXError("retain_tree_capture_failed")
            object_format = object_format_result.stdout.strip()
            if object_format_result.returncode != 0 or object_format not in {"sha1", "sha256"}:
                raise FinishUXError("retain_object_format_failed")
            selected_snapshot = fin.selected_snapshot(target["root"], rels)
            if (selected_snapshot.get("status_hex") != status.stdout.hex()
                    or selected_snapshot.get("index_hex") != index.stdout.hex()
                    or selected_snapshot.get("entries") != _snapshot_records(records)):
                raise FinishUXError("retain_source_changed")
            index_entries = _parse_index(index.stdout)
            base_entries = _parse_tree(tree.stdout)
            blob_oids = sorted({item["oid"] for item in index_entries + base_entries})
            blobs = tmp / "git-blobs"
            _private_dir(blobs)
            blob_manifest = []
            for oid in blob_oids:
                blob = _git_bytes(target["root"], "cat-file", "blob", oid)
                if blob.returncode != 0:
                    raise FinishUXError("retain_blob_capture_failed")
                blob_path = blobs / oid
                _private_write(blob_path, blob.stdout)
                blob_manifest.append({
                    "oid": oid, "sha256": hashlib.sha256(blob.stdout).hexdigest(),
                    "size": len(blob.stdout),
                })
            operation_state = (
                _capture_operation_payload(
                    tmp, target, operation, selected_operation_groups)
                if operation is not None else None)
            doc = {
                "schema": RETAIN_SCHEMA,
                "artifact_id": artifact_id,
                "kind": "protected-retain",
                "protected": True,
                "source": target["root"],
                "git_common_dir": target["common_dir"],
                "head": target["head"],
                "object_format": object_format,
                "selected_rows": indices,
                "selected_status": [
                    {"code": e["code"], "class": e["class"], "paths_hex": e["paths_hex"]}
                    for e in selected
                ],
                "entries": records,
                "status_snapshot_hex": status.stdout.hex(),
                "index_snapshot_hex": index.stdout.hex(),
                "index_entries": index_entries,
                "base_entries": base_entries,
                "git_blobs": blob_manifest,
                "selected_paths": rels,
                "selected_snapshot": selected_snapshot,
                "ignore_intent": sorted({
                    _safe_rel_from_hex(h)
                    for e in selected if e.get("class") == "ignored"
                    for h in e.get("paths_hex") or []
                }),
                "explicit_secrets": bool(
                    any(e.get("template_id") == "secret"
                        or e.get("contains_secret_dependencies") is True
                        for e in selected)),
                "explicit_ignored_dependencies": bool(
                    operation is not None
                    and operation.get("contains_ignored_dependencies") is True),
                "operation_state": operation_state,
                "operation_abort_proven": False if operation_state is not None else None,
                "created_at_epoch": int(time.time()),
                "publication_protocol": RETAIN_PUBLICATION_PROTOCOL,
                "restore_proven": False,
            }
            _private_write(tmp / "manifest.json",
                           (json.dumps(doc, indent=2, sort_keys=True) + "\n").encode("utf-8"))
            # Every payload/blob/preliminary-manifest file is durable before directory entries are
            # synced bottom-up. Restore proof deliberately reads the still-unpublished
            # restore_proven=false staging artifact.
            _sync_tree_directories_bottom_up(tmp)
            proof = root / ("." + artifact_id + ".proof")
            try:
                _restore_retain_path(
                    tmp, artifact_id, str(proof), require_proven=False)
                _verify_restored(doc, proof)
            finally:
                if proof.exists():
                    shutil.rmtree(proof)
                    _sync_dir(root)
            if fin.selected_snapshot(target["root"], rels) != selected_snapshot:
                raise FinishUXError("retain_source_changed")
            # The final true manifest is written and every staging directory is synced while the
            # artifact remains hidden. Readers still reject it because no committed marker exists.
            doc["restore_proven"] = True
            if operation_state is not None:
                doc["operation_abort_proven"] = True
            doc["restore_proven_at_epoch"] = int(time.time())
            final_manifest = (
                json.dumps(doc, indent=2, sort_keys=True) + "\n").encode("utf-8")
            _private_write(tmp / "manifest.json", final_manifest)
            _sync_tree_directories_bottom_up(tmp)
            manifest_digest = hashlib.sha256(final_manifest).hexdigest()
            marker_data = _publication_marker_bytes(artifact_id, manifest_digest)
            _private_write(pending, marker_data)
            os.replace(tmp, final)
            _sync_dir(root)
            # Pending remains a durable witness while committed is independently created, synced,
            # and validated. Never rename/consume the sole witness to manufacture trust.
            _private_write(committed, marker_data)
            publication_committed = True
            try:
                if os.path.lexists(pending):
                    pending.unlink()
                    _sync_dir(root)
            except OSError:
                cleanup_warnings.append("publication_pending_cleanup_incomplete")
    except Exception:
        # Re-read the final committed marker rather than trusting a local flag because a fault may
        # be raised after the durable write completed. Pending is deliberately left in place when
        # commit creation/sync is uncertain, so reboot recovery can promote the exact manifest.
        try:
            trusted = (
                final.is_dir() and not final.is_symlink()
                and _publication_status(
                    final,
                    *_manifest_document(
                        final / "manifest.json", require_proven=True,
                        expected_artifact_id=artifact_id)) == "committed"
            )
        except Exception:
            trusted = False
        if publication_committed or trusted:
            cleanup_warnings.append("publication_post_commit_incomplete")
        else:
            # Every staging/final/rollback candidate may be the sole durable copy after a crash.
            # Readers keep it hidden/untrusted unless marker validation safely recovers it.
            raise
    result = {
        "ok": True, "artifact_id": artifact_id, "protected": True,
        "restore_proven": True, "selected_rows": indices,
    }
    bounded = sorted(set(
        warning for warning in cleanup_warnings
        if warning in {
            "publication_cleanup_incomplete",
            "publication_pending_cleanup_incomplete",
            "publication_post_commit_incomplete",
            "publication_recovery_incomplete",
            "publication_repair_required",
            "publication_root_sync_incomplete",
        }))
    if bounded:
        result["cleanup_warnings"] = bounded
    return result


def _trusted_retained() -> list[dict]:
    root = _retain_dir()
    if not root.is_dir():
        return []
    out = []
    for path in sorted(root.iterdir()):
        if (not re.fullmatch(r"retain-[0-9a-f]{32}", path.name)
                or not path.is_dir() or path.is_symlink()):
            continue
        try:
            doc = _manifest(path, expected_artifact_id=path.name)
            _checked, data = _manifest_document(
                path / "manifest.json", require_proven=True,
                expected_artifact_id=path.name)
            publication_status = _publication_status(path, doc, data)
        except FinishUXError:
            continue
        item = {k: doc.get(k) for k in (
            "artifact_id", "kind", "protected", "source", "created_at_epoch",
            "restore_proven", "selected_rows")}
        item["publication_status"] = publication_status
        out.append(item)
    return out


def list_retained() -> list[dict]:
    _resume_retain_publications()
    return _trusted_retained()


def delete_retain(artifact_id: str, confirmation: str) -> dict:
    if confirmation != artifact_id:
        raise FinishUXError("explicit_artifact_id_confirmation_required")
    path = _artifact_path(artifact_id)
    root = _retain_dir()
    staging = root / ("." + artifact_id + ".staging")
    pending, committed, publication_rollback = _publication_paths(artifact_id)
    tombstone = root / ("." + artifact_id + ".tombstone")
    owner = root / ("." + artifact_id + ".tombstone-owner.json")
    exists = lambda candidate: os.path.lexists(candidate)
    live = [
        candidate for candidate in (path, staging, publication_rollback)
        if exists(candidate)
    ]
    if len(live) > 1 or (live and (exists(tombstone) or exists(owner))):
        raise FinishUXError("artifact_delete_state_ambiguous")
    if not live and not exists(tombstone) and not exists(owner):
        for marker in (pending, committed):
            if exists(marker):
                marker_st = os.lstat(marker)
                if stat.S_ISDIR(marker_st.st_mode) and not stat.S_ISLNK(marker_st.st_mode):
                    raise FinishUXError("artifact_delete_state_ambiguous")
                marker.unlink()
        if root.is_dir():
            _sync_dir(root)
        return {"ok": True, "deleted": artifact_id, "already_absent": True}
    if exists(owner):
        doc = _manifest_file(
            owner, require_proven=False, expected_artifact_id=artifact_id)
    else:
        selected = live[0] if live else tombstone
        doc = _manifest(
            selected, require_proven=False, expected_artifact_id=artifact_id,
            allow_uncommitted=True)
    fin = _load_finish()
    with fin.common_dir_lock(doc["git_common_dir"], blocking=True, timeout=30.0):
        live = [
            candidate for candidate in (path, staging, publication_rollback)
            if exists(candidate)
        ]
        if len(live) > 1 or (live and (exists(tombstone) or exists(owner))):
            raise FinishUXError("artifact_delete_state_ambiguous")
        if live:
            selected = live[0]
            current = _manifest(
                selected, require_proven=False, expected_artifact_id=artifact_id,
                allow_uncommitted=True)
            if current.get("git_common_dir") != doc.get("git_common_dir"):
                raise FinishUXError("artifact_delete_identity_changed")
            os.replace(selected, tombstone)
            _sync_dir(root)
        if not exists(tombstone) and not exists(owner):
            raise FinishUXError("artifact_delete_state_changed")
        current = (
            _manifest_file(
                owner, require_proven=False, expected_artifact_id=artifact_id)
            if exists(owner)
            else _manifest(
                tombstone, require_proven=False, expected_artifact_id=artifact_id,
                allow_uncommitted=True)
        )
        if current.get("git_common_dir") != doc.get("git_common_dir"):
            raise FinishUXError("artifact_delete_identity_changed")
        if not exists(owner):
            # Preserve the identifying manifest until every payload child is gone. A failed or
            # interrupted recursive removal therefore always remains safely resumable.
            for child in sorted(tombstone.iterdir(), key=lambda item: os.fsencode(item.name)):
                if child.name == "manifest.json":
                    continue
                child_st = os.lstat(child)
                if stat.S_ISDIR(child_st.st_mode) and not stat.S_ISLNK(child_st.st_mode):
                    shutil.rmtree(child)
                else:
                    child.unlink()
            manifest = tombstone / "manifest.json"
            os.replace(manifest, owner)
            _sync_dir(tombstone)
            _sync_dir(root)
        if exists(tombstone):
            if any(tombstone.iterdir()):
                raise FinishUXError("artifact_delete_state_ambiguous")
            tombstone.rmdir()
            _sync_dir(root)
        if not exists(owner):
            raise FinishUXError("artifact_delete_state_changed")
        for marker in (pending, committed):
            if not exists(marker):
                continue
            marker_st = os.lstat(marker)
            if stat.S_ISDIR(marker_st.st_mode) and not stat.S_ISLNK(marker_st.st_mode):
                raise FinishUXError("artifact_delete_state_ambiguous")
            marker.unlink()
        _sync_dir(root)
        owner.unlink()
        _sync_dir(root)
    return {"ok": True, "deleted": artifact_id, "already_absent": False}


_PASS_CHECKS = frozenset({"SUCCESS", "NEUTRAL", "SKIPPED"})


def verify_delivery_evidence(*, github_repositories: list[str], preserved_head_oid: str,
                             merged_prs: list[dict], compare: dict,
                             checks: list[dict], checks_complete: bool | None = None,
                             checks_observations: list[list[dict]] | None = None,
                             zero_check_stable: bool = False,
                             merge_commit_enabled: bool = True) -> dict:
    """Pure strict delivery-proof evaluator used by the Commit-only network adapter."""
    repos = sorted(set(github_repositories))
    if len(repos) != 1:
        return {"ok": False, "reason": "ambiguous_github_remote"}
    if merge_commit_enabled is not True:
        return {"ok": False, "reason": "merge_commit_required_unsupported"}
    if not re.fullmatch(r"[0-9a-fA-F]{40,64}", preserved_head_oid or ""):
        return {"ok": False, "reason": "malformed_head_oid"}
    exact = [p for p in merged_prs
             if p.get("state") == "MERGED" and p.get("headRefOid") == preserved_head_oid]
    if len(exact) != 1:
        return {"ok": False, "reason": "merged_pr_not_exact"}
    if compare.get("status") not in {"ahead", "identical"}:
        return {"ok": False, "reason": "head_not_in_default_branch"}
    states = [
        str(check.get("state") or check.get("conclusion") or "").upper()
        for check in checks if isinstance(check, dict)
    ]
    derived_complete = bool(checks) and len(states) == len(checks) and all(
        state in _PASS_CHECKS for state in states)
    if not checks:
        observations = checks_observations or []
        derived_complete = bool(
            zero_check_stable and len(observations) >= 2
            and all(isinstance(item, list) and not item for item in observations[-2:]))
    if checks_complete is False or not derived_complete:
        return {"ok": False, "reason": "checks_incomplete"}
    for check in checks:
        state = str(check.get("state") or check.get("conclusion") or "").upper()
        if state not in _PASS_CHECKS:
            return {"ok": False, "reason": "check_not_passing", "state": state or "UNKNOWN"}
    return {"ok": True, "repository": repos[0], "pr": exact[0].get("number"),
            "checks": len(checks)}


def _github_repo(url: str) -> str | None:
    match = re.search(r"(?:github\.com[/:])([^/\s]+)/([^/\s]+?)(?:\.git)?$", url.strip())
    return f"{match.group(1)}/{match.group(2)}" if match else None


def verify_delivery_network(root: str, branch: str, preserved_head_oid: str,
                            runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
                            sleep: Callable[[float], None] = time.sleep) -> dict:
    """Commit-only network boundary: all gh/API calls are structurally contained here."""
    try:
        rem = _git(root, "remote", "-v")
        repos = [_github_repo(line.split()[1]) for line in rem.stdout.splitlines()
                 if len(line.split()) >= 2]
        repos = [repo for repo in repos if repo]
        if len(set(repos)) != 1:
            return {"ok": False, "reason": "ambiguous_github_remote"}
        repo = repos[0]

        def gh(*args: str) -> Any:
            proc = runner(
                ["gh", *args], capture_output=True, text=True, timeout=30,
                env=_finish_git_env())
            if proc.returncode != 0:
                raise FinishUXError("gh_failed")
            return json.loads(proc.stdout)

        prs = gh("pr", "list", "--repo", repo, "--state", "merged", "--head", branch,
                 "--json", "number,state,headRefOid,mergedAt,url")
        default = gh("repo", "view", repo, "--json",
                     "defaultBranchRef,mergeCommitAllowed")
        if default.get("mergeCommitAllowed") is not True:
            return {"ok": False, "reason": "merge_commit_required_unsupported"}
        default_name = default["defaultBranchRef"]["name"]
        compare = gh("api", f"repos/{repo}/compare/{preserved_head_oid}...{default_name}")
        exact = [p for p in prs if p.get("headRefOid") == preserved_head_oid]
        checks: list[dict] = []
        observations: list[list[dict]] = []
        if len(exact) == 1:
            for observation in range(2):
                checks = gh("pr", "checks", str(exact[0]["number"]), "--repo", repo,
                            "--json", "name,state,bucket,completedAt")
                if not isinstance(checks, list):
                    raise FinishUXError("checks_malformed")
                observations.append(checks)
                if checks:
                    break
                if observation == 0:
                    sleep(1.0)
        return verify_delivery_evidence(
            github_repositories=repos, preserved_head_oid=preserved_head_oid,
            merged_prs=prs, compare=compare, checks=checks,
            checks_observations=observations,
            zero_check_stable=len(observations) >= 2,
            merge_commit_enabled=default.get("mergeCommitAllowed") is True)
    except (OSError, subprocess.SubprocessError, KeyError, TypeError, ValueError,
            json.JSONDecodeError, FinishUXError):
        return {"ok": False, "reason": "delivery_evidence_unavailable"}


def _selected_paths(dialogue: dict, indices: list[int]) -> list[str]:
    paths: list[str] = []
    selected = _selected(dialogue, indices)
    if any(entry.get("commit_eligible", True) is not True for entry in selected):
        raise FinishUXError("retain_only_row_cannot_be_committed")
    for entry in selected:
        for value in entry.get("paths_hex") or []:
            rel = _safe_rel_from_hex(value)
            if rel not in paths:
                paths.append(rel)
    return sorted(paths)


def _sanitized_supplied_env(env: dict | None = None, *,
                            index_file: str | None = None) -> dict:
    source = os.environ if env is None else env
    clean = {key: value for key, value in source.items() if not key.startswith("GIT_")}
    profile = _finish_git_env(index_file=index_file)
    clean.update({
        key: value for key, value in profile.items()
        if key.startswith("GIT_") or key in {"LC_ALL", "LANG", "LANGUAGE"}
    })
    return clean


def _run_checked(command: list[str], *, cwd: str, env: dict | None = None,
                 runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
                 timeout: float = 60.0) -> subprocess.CompletedProcess:
    proc = runner(
        command, cwd=cwd, env=_sanitized_supplied_env(
            env, index_file=env.get("GIT_INDEX_FILE") if env is not None else None),
        capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise FinishUXError(f"command_failed:{command[0]}:{proc.returncode}")
    return proc


def _unique_github_remote(root: str) -> tuple[str, str]:
    remotes = _git(root, "remote", "-v")
    if remotes.returncode != 0:
        raise FinishUXError("remote_list_failed")
    pairs = []
    for line in remotes.stdout.splitlines():
        cols = line.split()
        if len(cols) < 2:
            continue
        repo = _github_repo(cols[1])
        if repo:
            pairs.append((cols[0], repo))
    repositories = {repo for _, repo in pairs}
    names = {name for name, _ in pairs}
    if len(repositories) != 1 or len(names) != 1:
        raise FinishUXError("ambiguous_github_remote")
    return next(iter(names)), next(iter(repositories))


def commit_selected_local(conversation_id: str, indices: list[int], message: str, *,
                          runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
                          _claimed: bool = False) -> dict:
    """Create one exact selected-path commit without including unrelated staged rows."""
    dialogue = read_dialogue(conversation_id)
    if dialogue is None or (_claimed and dialogue.get("state") != "executing_mixed"):
        raise FinishUXError("wrong_dialogue_state")
    if not message.strip():
        raise FinishUXError("commit_message_required")
    paths = _selected_paths(dialogue, indices)
    if not _claimed:
        dialogue = _claim_action(
            conversation_id, "awaiting_commit_selection", "committing")
        paths = _selected_paths(dialogue, indices)
    target = dialogue["target"]
    fin = _load_finish()
    root = target["root"]
    branch = target["branch"]
    resolved = fin.resolve_target(root)
    if any(resolved.get(key) != target.get(key)
           for key in ("root", "git_dir", "common_dir", "branch", "head")):
        raise FinishUXError("commit_target_identity_changed")
    git_command = [
        "git", "--git-dir=" + resolved["git_dir"],
        "--work-tree=" + resolved["root"],
    ]
    resolved_binding = fin.validated_git_binding(
        root, git_dir=resolved["git_dir"], common_dir=resolved["common_dir"])
    index_dir = _dialogue_dir() / "commit-index"
    _private_dir(index_dir)
    temp_index = index_dir / f"{_conversation_key(conversation_id)}-{uuid.uuid4().hex}.index"
    if os.path.dirname(os.path.realpath(temp_index)) != os.path.realpath(index_dir):
        raise FinishUXError("commit_index_binding_invalid")
    env = _finish_git_env(index_file=str(temp_index))
    try:
        with fin.common_dir_lock(target["common_dir"], blocking=True, timeout=30.0):
            old_head = _run_checked(
                git_command + ["rev-parse", "HEAD"], cwd=root,
                env=env, runner=runner).stdout.strip()
            _run_checked(git_command + ["read-tree", old_head], cwd=root,
                         env=env, runner=runner)
            if (not temp_index.is_file() or temp_index.is_symlink()
                    or os.path.dirname(os.path.realpath(temp_index))
                    != os.path.realpath(index_dir)):
                raise FinishUXError("commit_index_binding_invalid")
            _run_checked(git_command + ["add", "-A", "--", *paths], cwd=root,
                         env=env, runner=runner)
            changed = runner(
                git_command + ["diff", "--cached", "--quiet"], cwd=root,
                env=_sanitized_supplied_env(
                    env, index_file=env["GIT_INDEX_FILE"]),
                capture_output=True, text=True, timeout=30)
            if changed.returncode == 0:
                raise FinishUXError("selected_rows_have_no_commit_change")
            if changed.returncode != 1:
                raise FinishUXError("selected_diff_failed")
            _run_checked(git_command + ["commit", "-m", message], cwd=root,
                         env=env, runner=runner, timeout=120)
            commit = _run_checked(
                git_command + ["rev-parse", "HEAD"], cwd=root,
                env=env, runner=runner).stdout.strip()
            changed_paths = _run_checked(
                git_command + [
                    "diff-tree", "--no-commit-id", "--name-only", "-r",
                    "-z", old_head, commit],
                cwd=root, env=env, runner=runner).stdout.split("\x00")
            unexpected = sorted(set(filter(None, changed_paths)) - set(paths))
            if unexpected:
                _run_checked(
                    git_command + [
                        "update-ref", f"refs/heads/{branch}", old_head, commit],
                    cwd=root, env=_finish_git_env(
                        index_file=resolved_binding["index_file"]), runner=runner)
                raise FinishUXError("commit_included_unselected_paths")
            _run_checked(
                git_command + ["reset", "-q", "HEAD", "--", *paths],
                cwd=root, env=_finish_git_env(
                    index_file=resolved_binding["index_file"]),
                runner=runner)
            return {"ok": True, "head_oid": commit, "previous_head_oid": old_head,
                    "branch": branch, "selected_rows": indices, "paths": paths}
    finally:
        try:
            temp_index.unlink()
        except OSError:
            pass


def deliver_commit(root: str, branch: str, head_oid: str, *,
                   runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
                   timeout_seconds: float = 300.0,
                   sleep: Callable[[float], None] = time.sleep) -> dict:
    """Commit/Mixed-only push, PR merge, and strict delivery proof."""
    remote, repository = _unique_github_remote(root)
    binding = _load_finish().validated_git_binding(root)
    git_command = [
        "git", "--git-dir=" + binding["git_dir"],
        "--work-tree=" + binding["root"],
    ]
    try:
        settings = json.loads(_run_checked(
            ["gh", "repo", "view", repository, "--json", "mergeCommitAllowed"],
            cwd=root, runner=runner).stdout)
        if settings.get("mergeCommitAllowed") is not True:
            return {"ok": False, "reason": "merge_commit_required_unsupported",
                    "head_oid": head_oid}
        _run_checked(
            git_command + ["push", "-u", remote, branch], cwd=root,
            env=_finish_git_env(index_file=binding["index_file"]),
            runner=runner, timeout=120)
        listed = _run_checked(
            ["gh", "pr", "list", "--repo", repository, "--state", "open", "--head", branch,
             "--json", "number,url,headRefOid"], cwd=root, runner=runner).stdout
        prs = json.loads(listed)
        exact = [pr for pr in prs if pr.get("headRefOid") == head_oid]
        if len(exact) == 0:
            created = _run_checked(
                ["gh", "pr", "create", "--repo", repository, "--head", branch, "--fill"],
                cwd=root, runner=runner).stdout.strip()
            pr_ref = created
        elif len(exact) == 1:
            pr_ref = str(exact[0].get("url") or exact[0]["number"])
        else:
            raise FinishUXError("ambiguous_open_pr")
        _run_checked(
            ["gh", "pr", "merge", pr_ref, "--repo", repository, "--auto", "--merge"],
            cwd=root, runner=runner)
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        while True:
            proof = verify_delivery_network(root, branch, head_oid, runner=runner, sleep=sleep)
            if proof.get("ok"):
                return {"ok": True, "proof": proof, "head_oid": head_oid}
            if time.monotonic() >= deadline:
                return {"ok": False, "reason": "delivery_proof_timeout", "last_proof": proof,
                        "head_oid": head_oid}
            sleep(min(5.0, max(0.0, deadline - time.monotonic())))
    except (FinishUXError, OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "reason": "delivery_failed", "detail": str(exc),
                "head_oid": head_oid}


def complete_commit(conversation_id: str, indices: list[int], message: str, *,
                    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
                    timeout_seconds: float = 300.0,
                    sleep: Callable[[float], None] = time.sleep,
                    _claimed: bool = False,
                    _defer_completion: bool = False) -> dict:
    dialogue = read_dialogue(conversation_id)
    if dialogue is None:
        raise FinishUXError("no_pending_dialogue")
    if dialogue.get("state") == "action_complete_refresh_pending":
        if dialogue.get("action_kind") != "Commit" or _claimed:
            raise FinishUXError("wrong_dialogue_state")
        return _refresh_completed_action(dialogue)
    local = commit_selected_local(
        conversation_id, indices, message, runner=runner, _claimed=_claimed)
    delivery = deliver_commit(
        dialogue["target"]["root"], local["branch"], local["head_oid"],
        runner=runner, timeout_seconds=timeout_seconds, sleep=sleep)
    if not delivery.get("ok"):
        result = {"ok": False, "local_commit_preserved": True, "local": local,
                  "delivery": delivery, "action_complete": False,
                  "fresh_preview_required": True, "refresh_ok": False,
                  "close_still_required": True}
        try:
            result["fresh_preview"] = refresh_after_action(conversation_id)
            result["refresh_ok"] = True
            result["fresh_preview_required"] = False
        except Exception:
            pass
        return result
    completed = {"ok": True, "local": local, "delivery": delivery}
    if _defer_completion:
        return completed
    latched = _latch_action_complete(
        conversation_id, "Commit", commit_complete=True,
        retain_complete=False)
    return _refresh_completed_action(latched, extra=completed)


def complete_mixed(conversation_id: str, commit_indices: list[int],
                   retain_indices: list[int], message: str, *,
                   allow_secrets: bool = False,
                   allow_ignored_dependencies: bool = False,
                   runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
                   timeout_seconds: float = 300.0,
                   sleep: Callable[[float], None] = time.sleep) -> dict:
    dialogue = read_dialogue(conversation_id)
    if dialogue is None:
        raise FinishUXError("no_pending_dialogue")
    if dialogue.get("state") == "action_complete_refresh_pending":
        if dialogue.get("action_kind") != "Mixed":
            raise FinishUXError("wrong_dialogue_state")
        return _refresh_completed_action(dialogue)
    _validate_dialogue_live(dialogue, expected_state="awaiting_mixed_selection")
    all_indices = commit_indices + retain_indices
    _selected(dialogue, all_indices)
    if set(commit_indices) & set(retain_indices):
        raise FinishUXError("mixed_rows_overlap")
    if not commit_indices or not retain_indices:
        raise FinishUXError("mixed_requires_both_dispositions")
    visible_indices = set(range(1, len(dialogue.get("visible") or []) + 1))
    if set(all_indices) != visible_indices:
        raise FinishUXError("mixed_partition_incomplete")
    # Validate the Commit partition before Retain publishes anything or the dialogue is claimed.
    _selected_paths(dialogue, commit_indices)
    retain_selected = _selected(dialogue, retain_indices)
    if (any(entry.get("template_id") == "secret"
            or entry.get("contains_secret_dependencies") is True
            for entry in retain_selected)
            and not allow_secrets):
        raise FinishUXError("explicit_secret_confirmation_required")
    if (any(entry.get("contains_ignored_dependencies") is True
            for entry in retain_selected)
            and not allow_ignored_dependencies):
        raise FinishUXError("explicit_ignored_confirmation_required")
    dialogue = _claim_action(
        conversation_id, "awaiting_mixed_selection", "executing_mixed")
    retained = create_retain(
        conversation_id, retain_indices, allow_secrets=allow_secrets,
        allow_ignored_dependencies=allow_ignored_dependencies, _claimed=True)
    try:
        committed = complete_commit(
            conversation_id, commit_indices, message, runner=runner,
            timeout_seconds=timeout_seconds, sleep=sleep, _claimed=True,
            _defer_completion=True)
    except Exception as exc:
        result = {"ok": False, "retained": retained, "commit": {"ok": False,
                  "reason": "commit_exception"},
                  "partial": True, "protected_artifact_preserved": True,
                  "unresolved_rows": commit_indices, "fresh_preview_required": True}
        try:
            result["fresh_preview"] = refresh_after_action(conversation_id)
        except Exception:
            pass
        return result
    if not committed.get("ok"):
        return {"ok": False, "retained": retained, "commit": committed,
                "partial": True, "protected_artifact_preserved": True,
                "local_commit_preserved": bool(committed.get("local_commit_preserved")),
                "unresolved_rows": commit_indices, "fresh_preview_required": True}
    latched = _latch_action_complete(
        conversation_id, "Mixed", commit_complete=True,
        retain_complete=True, artifact_id=retained["artifact_id"])
    return _refresh_completed_action(
        latched, extra={"retained": retained, "commit": committed})


def refresh_after_action(conversation_id: str) -> dict:
    dialogue = _read_dialogue_raw(conversation_id)
    if dialogue is None:
        raise FinishUXError("no_pending_dialogue")
    payload = {
        "prompt": "finish",
        "conversation_id": conversation_id,
        "session_id": dialogue["session_id"],
        "cwd": dialogue["target"]["root"],
    }
    try:
        return preview_payload(payload, hook_mode=bool(dialogue.get("hook_mode")))
    except Exception:
        # A partial refresh must not erase the point-of-no-return latch. Remove only a replacement
        # challenge generation when it can be exact-CAS identified, then restore the old projection.
        current = _read_dialogue_raw(conversation_id)
        if (current is not None
                and (current.get("generation"), current.get("nonce"))
                != (dialogue.get("generation"), dialogue.get("nonce"))):
            try:
                _load_finish().delete_challenge(
                    conversation_id,
                    expected_generation=current.get("generation"),
                    expected_nonce=current.get("nonce"))
            except Exception:
                pass
        write_dialogue(dialogue)
        write_current_index(dialogue)
        raise


def _refresh_completed_action(dialogue: dict, *, extra: dict | None = None) -> dict:
    if (dialogue.get("state") != "action_complete_refresh_pending"
            or dialogue.get("action_kind") not in {"Commit", "Retain", "Mixed"}):
        raise FinishUXError("action_completion_invalid")
    expected = {
        "Commit": (True, False, False),
        "Retain": (False, True, True),
        "Mixed": (True, True, True),
    }[dialogue["action_kind"]]
    artifact_id = dialogue.get("action_artifact_id")
    if (
            dialogue.get("action_commit_complete") is not expected[0]
            or dialogue.get("action_retain_complete") is not expected[1]
            or bool(artifact_id) is not expected[2]
            or (artifact_id
                and re.fullmatch(r"retain-[0-9a-f]{32}", artifact_id) is None)):
        raise FinishUXError("action_completion_invalid")
    result = dict(extra or {})
    result.update({
        "ok": True,
        "action": dialogue["action_kind"],
        "action_complete": True,
        "refresh_ok": False,
        "fresh_preview_required": True,
        "close_still_required": True,
    })
    if artifact_id and "artifact" not in result and "retained" not in result:
        result["artifact"] = {
            "ok": True,
            "artifact_id": artifact_id,
            "protected": True,
            "restore_proven": True,
        }
    if dialogue.get("hook_mode") is True:
        # The action CLI owns only the durable completion latch. Hook warning publication belongs
        # to the next beforeSubmitPrompt invocation and its post-output publication transition.
        return result
    try:
        result["fresh_preview"] = refresh_after_action(
            dialogue["conversation_id"])
    except Exception:
        return result
    result["refresh_ok"] = True
    result["fresh_preview_required"] = False
    return result


def complete_retain(conversation_id: str, indices: list[int], *,
                    allow_secrets: bool = False,
                    allow_ignored_dependencies: bool = False) -> dict:
    dialogue = read_dialogue(conversation_id)
    if dialogue is None:
        raise FinishUXError("no_pending_dialogue")
    if dialogue.get("state") == "action_complete_refresh_pending":
        if dialogue.get("action_kind") != "Retain":
            raise FinishUXError("wrong_dialogue_state")
        return _refresh_completed_action(dialogue)
    artifact = create_retain(
        conversation_id, indices, allow_secrets=allow_secrets,
        allow_ignored_dependencies=allow_ignored_dependencies)
    latched = _latch_action_complete(
        conversation_id, "Retain", commit_complete=False,
        retain_complete=True, artifact_id=artifact["artifact_id"])
    return _refresh_completed_action(latched, extra={"artifact": artifact})


def _read_stdin_json() -> dict:
    try:
        value = json.load(sys.stdin)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _write_dispatch_result(result: dict) -> None:
    """Write and flush the complete public record before releasing its recovery anchor."""
    data = json.dumps(result, indent=2, sort_keys=True) + "\n"
    sys.stdout.write(data)
    sys.stdout.flush()
    _finalize_terminal_index_after_output()


def main(argv: list[str] | None = None) -> int:
    parser = ClosedArgumentParser(prog="awa-finish-current")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("hook")
    sub.add_parser("hook-published")
    sub.add_parser("hook-cleanup")
    rec = sub.add_parser("recognize")
    rec.add_argument("prompt")
    warn = sub.add_parser("warning")
    warn.add_argument("--rows", default="None | No operator work will be deleted.")
    dsp = sub.add_parser("dispatch")
    dsp.add_argument("--current", action="store_true")
    dsp.add_argument("--conversation-id")
    dsp.add_argument("--answer")
    ret = sub.add_parser("retain")
    ret.add_argument("--conversation-id", required=True)
    ret.add_argument(
        "--rows", required=True, type=_row_indices_arg,
        help="comma-separated 1-based row numbers")
    ret.add_argument("--allow-secrets", action="store_true")
    ret.add_argument("--allow-ignored-dependencies", action="store_true")
    com = sub.add_parser("commit")
    com.add_argument("--conversation-id", required=True)
    com.add_argument(
        "--rows", required=True, type=_row_indices_arg,
        help="comma-separated 1-based row numbers")
    com.add_argument("--message", required=True)
    com.add_argument("--timeout", type=_finite_float, default=300.0)
    mix = sub.add_parser("mixed")
    mix.add_argument("--conversation-id", required=True)
    mix.add_argument("--commit-rows", required=True, type=_row_indices_arg)
    mix.add_argument("--retain-rows", required=True, type=_row_indices_arg)
    mix.add_argument("--message", required=True)
    mix.add_argument("--allow-secrets", action="store_true")
    mix.add_argument("--allow-ignored-dependencies", action="store_true")
    mix.add_argument("--timeout", type=_finite_float, default=300.0)
    sub.add_parser("retain-list")
    rst = sub.add_parser("retain-restore")
    rst.add_argument("--artifact-id", required=True)
    rst.add_argument("--destination", required=True)
    dele = sub.add_parser("retain-delete")
    dele.add_argument("--artifact-id", required=True)
    dele.add_argument("--confirm", required=True)
    try:
        args = parser.parse_args(argv)
    except ClosedArgumentError:
        print(json.dumps(_build_public_dispatch(
            PublicDispatchOutcome.REFUSED,
            reason=PublicDispatchReason.OPERATION_FAILED), sort_keys=True))
        return 2
    terminal_dispatch_output = False
    try:
        if args.cmd == "hook":
            deadline = max(1, int(os.environ.get("AWA_FINISH_HOOK_DEADLINE_SECONDS", "15")))
            signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(
                TimeoutError("hook_deadline")))
            signal.alarm(deadline)
            try:
                print(json.dumps(handle_hook_payload(_read_stdin_json())))
            finally:
                signal.alarm(0)
        elif args.cmd == "hook-published":
            published = mark_hook_published(_read_stdin_json())
            print(json.dumps({"published": published}))
            if not published:
                return 1
        elif args.cmd == "hook-cleanup":
            payload = _read_stdin_json()
            conversation_id = _payload_conversation(payload)
            dialogue = read_dialogue(conversation_id)
            if dialogue is not None:
                cleanup_pending(
                    conversation_id, generation=dialogue.get("generation"),
                    nonce=dialogue.get("nonce"))
            print(json.dumps({"continue": True}))
        elif args.cmd == "recognize":
            print(json.dumps({"version": RECOGNIZER_VERSION,
                              "finish_current": recognize_finish(args.prompt)}))
        elif args.cmd == "warning":
            print(render_warning(args.rows))
        elif args.cmd == "dispatch":
            global _POST_OUTPUT_INDEX_CAS
            _POST_OUTPUT_INDEX_CAS = None
            if args.current:
                result = dispatch_current()
            elif args.conversation_id:
                result = dispatch_choice(args.conversation_id, args.answer)
            else:
                raise FinishUXError("dispatch_requires_current_or_conversation")
            terminal_dispatch_output = (
                result.get("workspace_removed") in {True, None}
                and result.get("agent_stopping") is True)
            _write_dispatch_result(result)
        elif args.cmd == "retain":
            print(json.dumps(complete_retain(args.conversation_id, args.rows,
                                             allow_secrets=args.allow_secrets,
                                             allow_ignored_dependencies=(
                                                 args.allow_ignored_dependencies)),
                             indent=2, sort_keys=True))
        elif args.cmd == "commit":
            print(json.dumps(complete_commit(
                args.conversation_id, args.rows, args.message,
                timeout_seconds=args.timeout),
                indent=2, sort_keys=True))
        elif args.cmd == "mixed":
            print(json.dumps(complete_mixed(
                args.conversation_id, args.commit_rows, args.retain_rows, args.message,
                allow_secrets=args.allow_secrets,
                allow_ignored_dependencies=args.allow_ignored_dependencies,
                timeout_seconds=args.timeout),
                indent=2, sort_keys=True))
        elif args.cmd == "retain-list":
            warnings = _resume_retain_publications()
            print(json.dumps({
                "artifacts": _trusted_retained(),
                "publication_warnings": warnings,
            }, indent=2, sort_keys=True))
        elif args.cmd == "retain-restore":
            print(json.dumps(restore_retain(args.artifact_id, args.destination),
                             indent=2, sort_keys=True))
        elif args.cmd == "retain-delete":
            print(json.dumps(delete_retain(args.artifact_id, args.confirm),
                             indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        # Never append a contradictory workspace-preserved record after terminal dispatch output
        # was interrupted. The exact index remains for a later removed/uncertain recovery.
        if (args.cmd == "dispatch"
                and (terminal_dispatch_output or _POST_OUTPUT_INDEX_CAS is not None)):
            return 1
        print(json.dumps(_build_public_dispatch(
            PublicDispatchOutcome.REFUSED,
            reason=_public_reason(
                str(exc) if isinstance(exc, FinishUXError) else "",
                PublicDispatchReason.OPERATION_FAILED)), sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
