"""Fail-open payload-bound registration for native Cursor worktrees.

``sessionStart`` remains the eager opportunity and ``beforeSubmitPrompt`` is
the first-prompt recovery opportunity. Both paths derive identity only from a
closed hook payload, bind the exact current session, and adopt or attest under
the existing per-common-dir lifecycle lock. Private native-entry receipts are
evidence only; they never authorize cleanup or removal.
"""

from __future__ import annotations

import contextlib
import concurrent.futures
import datetime
import fcntl
import hashlib
import json
import os
import re
import secrets
import sqlite3
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator
from urllib.parse import quote

from . import (
    lease as lease_mod,
    lifecycle,
    lock,
    paths,
    policy as policy_mod,
    state as state_mod,
)


SCHEMA_V1 = "awa-native-entry/v1"
SCHEMA_V2 = "awa-native-entry/v2"
SCHEMA = SCHEMA_V2
RESULTS_V1 = frozenset(
    {"success", "stale", "mismatched", "conflict", "failed"}
)
RESULTS_V2 = frozenset(
    {"pending", "success", "stale", "mismatched", "conflict", "failed"}
)
_ACTIONS_V1 = frozenset({"adopted", "attested", "repaired"})
_ACTIONS_V2 = _ACTIONS_V1 | frozenset({"recovered"})
SOURCE_EVENTS = frozenset({"sessionStart", "beforeSubmitPrompt"})
_MAX_PAYLOAD_BYTES = 64 * 1024
_MAX_RECEIPT_BYTES = 64 * 1024
_MAX_RECEIPTS = 512
_DEFAULT_REGISTRATION_SECONDS = 30.0
_EAGER_REGISTRATION_SECONDS = 4.5
_OBJECT_ID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_SESSION_ID = re.compile(r"[^\x00-\x20\x7f]{1,512}\Z")
_RECEIPT_NAME = re.compile(r"entry-[0-9a-f]{24}-[0-9a-f]{24}\.json\Z")
RECEIPT_V1_KEYS = frozenset(
    {
        "schema",
        "root",
        "session_id",
        "branch",
        "head",
        "git_dir",
        "git_common_dir",
        "generation",
        "timestamp",
        "result",
        "action",
        "lease_id",
        "reason",
    }
)
RECEIPT_V2_KEYS = RECEIPT_V1_KEYS | frozenset(
    {
        "source_event",
        "conversation_id",
        "source_generation_id",
    }
)
_V2_REASONS = frozenset(
    {
        "registration_pending",
        "registered",
        "recovered",
        "already_registered",
        "policy_ineligible",
        "identity_changed",
        "policy_changed",
        "worktree_dirty",
        "worktree_ignored_state",
        "index_hidden_state",
        "git_operation_unknown",
        "git_operation_active",
        "registration_conflict",
        "attestation_failed",
        "current_session_invalid",
        "lock_busy",
        "deadline_exceeded",
        "registration_failed",
    }
)
_V2_TERMINAL_FAILURE_REASONS = _V2_REASONS - frozenset(
    {
        "registration_pending",
        "registered",
        "recovered",
        "already_registered",
    }
)
_ATTEMPT_KEYS = (
    "source_event",
    "root",
    "session_id",
    "conversation_id",
    "source_generation_id",
    "branch",
    "head",
    "git_dir",
    "git_common_dir",
)


class EntryUnavailable(RuntimeError):
    """Expected local uncertainty; the hook remains quiet and fail-open."""

    def __init__(self, reason: str, *, result: str = "failed") -> None:
        super().__init__(reason)
        self.reason = reason
        self.result = result


@dataclass(frozen=True)
class EntryPayload:
    root: str
    session_id: str
    conversation_id: str
    source_generation_id: str
    source_event: str


@dataclass(frozen=True)
class EntryResult:
    result: str
    action: str | None
    reason: str
    receipt: dict | None = None


def native_entry_dir() -> Path:
    return paths.awa_state_dir() / "native-entry"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def receipt_path(root: str, session_id: str) -> Path:
    canonical = os.path.realpath(os.path.abspath(os.path.expanduser(root)))
    return native_entry_dir() / (
        f"entry-{_digest(canonical)}-{_digest(session_id)}.json"
    )


def _valid_branch(value: object) -> bool:
    if not isinstance(value, str) or not value or value == "HEAD":
        return False
    if (
        value.startswith(("-", ".", "/"))
        or value.endswith((".", "/"))
        or ".." in value
        or "@{" in value
        or "//" in value
        or any(
            character.isspace() or character in "~^:?*[\\\\"
            for character in value
        )
    ):
        return False
    return all(part and not part.endswith(".lock") for part in value.split("/"))


def _valid_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _canonical_existing_directory(value: object) -> str | None:
    if not isinstance(value, str) or not value or "\0" in value:
        return None
    if not os.path.isabs(value) or value != os.path.abspath(value):
        return None
    try:
        metadata = os.lstat(value)
    except OSError:
        return None
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        return None
    canonical = os.path.realpath(value)
    return canonical if canonical == value else None


def _payload_sources(value: object) -> list[dict]:
    if not isinstance(value, dict):
        raise EntryUnavailable("invalid_payload")
    sources = [value]
    nested = value.get("tool_input")
    if nested is not None:
        if not isinstance(nested, dict):
            raise EntryUnavailable("invalid_payload")
        sources.append(nested)
    return sources


def _one_payload_string(
    sources: list[dict],
    keys: tuple[str, ...],
    *,
    required_key: str | None = None,
) -> str:
    if required_key is not None and not any(
        required_key in source for source in sources
    ):
        raise EntryUnavailable("invalid_payload")
    supplied = [
        source[key]
        for source in sources
        for key in keys
        if key in source
    ]
    if not supplied or any(
        not isinstance(value, str)
        or not value
        or value != value.strip()
        for value in supplied
    ):
        raise EntryUnavailable("invalid_payload")
    exact = set(supplied)
    if len(exact) != 1:
        raise EntryUnavailable("invalid_payload")
    value = next(iter(exact))
    if _SESSION_ID.fullmatch(value) is None:
        raise EntryUnavailable("invalid_payload")
    return value


def parse_entry_payload(value: object) -> EntryPayload:
    """Normalize one supported event using payload identity only."""
    sources = _payload_sources(value)
    event = _one_payload_string(
        sources,
        ("hook_event_name", "event"),
        required_key="hook_event_name",
    )
    if event not in SOURCE_EVENTS:
        raise EntryUnavailable("invalid_event")

    roots: list[str] = []
    documented_roots = 0
    for source in sources:
        for key in (
            "cwd",
            "workspaceRoot",
            "workspace_path",
            "root",
            "projectRoot",
        ):
            candidate = source.get(key)
            if candidate is None:
                continue
            if (
                not isinstance(candidate, str)
                or not candidate
                or candidate != candidate.strip()
            ):
                raise EntryUnavailable("ambiguous_root")
            roots.append(candidate)
        listed = source.get("workspace_roots")
        if listed is None:
            continue
        if (
            not isinstance(listed, list)
            or not listed
            or any(
                not isinstance(item, str)
                or not item
                or item != item.strip()
                for item in listed
            )
        ):
            raise EntryUnavailable("ambiguous_root")
        documented_roots += len(listed)
        roots.extend(listed)
    canonical_roots = {_canonical_existing_directory(item) for item in roots}
    if (
        documented_roots < 1
        or not roots
        or None in canonical_roots
        or len(canonical_roots) != 1
    ):
        raise EntryUnavailable("ambiguous_root")

    conversation = _one_payload_string(
        sources,
        ("conversation_id", "conversationId"),
        required_key="conversation_id",
    )
    generation = _one_payload_string(
        sources,
        ("generation_id", "generationId"),
        required_key="generation_id",
    )
    explicit_sessions = [
        source[key]
        for source in sources
        for key in ("session_id", "sessionId")
        if key in source
    ]
    if event == "sessionStart" and not explicit_sessions:
        raise EntryUnavailable("ambiguous_session")
    if explicit_sessions:
        if any(
            not isinstance(session, str)
            or not session
            or session != session.strip()
            for session in explicit_sessions
        ):
            raise EntryUnavailable("ambiguous_session")
        sessions = set(explicit_sessions)
        if (
            len(sessions) != 1
            or _SESSION_ID.fullmatch(next(iter(sessions))) is None
            or next(iter(sessions)) != conversation
        ):
            raise EntryUnavailable("ambiguous_session")
    return EntryPayload(
        root=next(iter(canonical_roots)),
        session_id=conversation,
        conversation_id=conversation,
        source_generation_id=generation,
        source_event=event,
    )


def parse_session_start(value: object) -> EntryPayload:
    """Compatibility parser for the eager registration opportunity."""
    payload = parse_entry_payload(value)
    if payload.source_event != "sessionStart":
        raise EntryUnavailable("invalid_event")
    return payload


def _git_env() -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_")
    }
    env.update(
        {
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "LC_ALL": "C",
            "LANG": "C",
            "LANGUAGE": "C",
        }
    )
    return env


_GIT_READS = {
    (
        "rev-parse",
        "--show-toplevel",
        "--path-format=absolute",
        "--git-dir",
        "--git-common-dir",
    ),
    (
        "status",
        "--porcelain=v2",
        "--branch",
        "-z",
        "--untracked-files=all",
    ),
    (
        "status",
        "--porcelain=v2",
        "--branch",
        "-z",
        "--ignored=matching",
        "--untracked-files=all",
    ),
    ("worktree", "list", "--porcelain", "-z"),
    (
        "config",
        "--get-regexp",
        r"^(remote\.origin\.url|core\.hookspath)$",
    ),
    ("ls-files", "-v", "-z"),
}


def _remaining(deadline: float | None, *, cap: float | None = None) -> float:
    if deadline is None:
        remaining = 2.0 if cap is None else cap
    else:
        remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise EntryUnavailable("deadline_exceeded")
    if cap is not None:
        remaining = min(remaining, cap)
    return max(0.001, remaining)


def _git(
    root: str,
    *args: str,
    deadline: float | None = None,
) -> subprocess.CompletedProcess:
    normalized = tuple(str(arg) for arg in args)
    if normalized not in _GIT_READS:
        raise ValueError("native entry permits only closed local Git reads")
    return subprocess.run(
        [
            "git",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.untrackedCache=false",
            "-C",
            root,
            *normalized,
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=_remaining(deadline, cap=2.0),
        check=False,
        env=_git_env(),
    )


def _parse_worktrees(raw: str) -> list[dict]:
    records: list[dict] = []
    current: dict[str, object] = {}
    for token in raw.split("\0"):
        if not token:
            if current:
                records.append(current)
                current = {}
            continue
        key, separator, text = token.partition(" ")
        if key == "worktree" and "worktree" in current:
            records.append(current)
            current = {}
        current[key] = text if separator else True
    if current:
        records.append(current)
    return records


def _observe_identity(
    root: str,
    *,
    deadline: float | None = None,
) -> lifecycle.WorktreeIdentity:
    canonical_root = _canonical_existing_directory(root)
    if canonical_root is None or canonical_root != root:
        raise EntryUnavailable("root_not_canonical")
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        identity_future = executor.submit(
            _git,
            root,
            "rev-parse",
            "--show-toplevel",
            "--path-format=absolute",
            "--git-dir",
            "--git-common-dir",
            deadline=deadline,
        )
        status_future = executor.submit(
            _git,
            root,
            "status",
            "--porcelain=v2",
            "--branch",
            "-z",
            "--untracked-files=all",
            deadline=deadline,
        )
        worktrees_future = executor.submit(
            _git,
            root,
            "worktree",
            "list",
            "--porcelain",
            "-z",
            deadline=deadline,
        )
        identity_result = identity_future.result()
        status_result = status_future.result()
        worktrees_result = worktrees_future.result()
    if any(
        result.returncode != 0
        for result in (identity_result, status_result, worktrees_result)
    ):
        raise EntryUnavailable("git_identity_unavailable")
    identity_lines = identity_result.stdout.splitlines()
    if len(identity_lines) != 3:
        raise EntryUnavailable("git_identity_unavailable")
    top = _canonical_existing_directory(identity_lines[0])
    git_dir = _canonical_existing_directory(identity_lines[1])
    common = _canonical_existing_directory(identity_lines[2])
    status_headers: dict[str, str] = {}
    for token in status_result.stdout.split("\0"):
        if token.startswith("# ") and " " in token[2:]:
            key, value = token[2:].split(" ", 1)
            if key in status_headers:
                raise EntryUnavailable("git_identity_unavailable")
            status_headers[key] = value
    branch = status_headers.get("branch.head", "")
    head = status_headers.get("branch.oid", "")
    if (
        top != root
        or git_dir is None
        or common is None
        or git_dir == common
        or not _valid_branch(branch)
        or _OBJECT_ID.fullmatch(head) is None
    ):
        raise EntryUnavailable("not_eligible_linked_worktree")

    registrations = _parse_worktrees(worktrees_result.stdout)
    matches = []
    for record in registrations:
        registered = record.get("worktree")
        canonical = _canonical_existing_directory(registered)
        if canonical == root:
            matches.append(record)
    if len(matches) != 1:
        raise EntryUnavailable("git_registration_ambiguous")
    registration = matches[0]
    if (
        registration.get("bare") is True
        or registration.get("detached") is True
        or registration.get("prunable") is not None
        or registration.get("HEAD") != head
        or registration.get("branch") != f"refs/heads/{branch}"
    ):
        raise EntryUnavailable("git_registration_mismatch")
    return lifecycle.WorktreeIdentity(
        root=root,
        git_dir=git_dir,
        git_common_dir=common,
        branch=branch,
        head=head,
    )


def _load_policy() -> policy_mod.PolicyConfig:
    configured = os.environ.get("AWA_POLICY", "").strip()
    policy_path = (
        Path(configured).expanduser()
        if configured
        else Path(__file__).resolve().parents[1]
        / "kernel"
        / "policy"
        / "default-worktree-policy.yml"
    )
    try:
        text = policy_mod._read_regular_text(policy_path)  # noqa: SLF001
        data = policy_mod._parse_mini_yaml(text)  # noqa: SLF001
        return policy_mod.PolicyConfig._from_data(data, policy_path)  # noqa: SLF001
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        raise EntryUnavailable("policy_unavailable") from exc


def _policy_repository(
    identity_value: lifecycle.WorktreeIdentity,
) -> str:
    """Derive the canonical primary repository from the proven common Git dir."""
    common = Path(identity_value.git_common_dir)
    if common.name != ".git":
        raise EntryUnavailable("policy_repository_unavailable")
    primary = _canonical_existing_directory(str(common.parent))
    if primary is None:
        raise EntryUnavailable("policy_repository_unavailable")
    return primary


def _policy_decision(
    identity_value: lifecycle.WorktreeIdentity,
    *,
    has_origin: bool,
    hooks_path: str,
) -> bool:
    cfg = _load_policy()
    repository = _policy_repository(identity_value)
    candidates = []
    env_root = os.environ.get("AWA_GOVERNED_ROOT", "").strip()
    if env_root:
        candidates.append(env_root)
    candidates.extend(cfg.governed_roots)
    governed = ""
    for candidate in candidates:
        canonical = os.path.realpath(os.path.abspath(os.path.expanduser(candidate)))
        if repository == canonical or repository.startswith(canonical + os.sep):
            governed = canonical
            break
    if governed:
        rel = "." if repository == governed else repository[len(governed) + 1 :]
    else:
        rel = os.path.basename(repository.rstrip(os.sep))
    decision = policy_mod.classify(
        rel,
        repository,
        cfg,
        hooks_path=hooks_path,
        has_origin=has_origin,
        is_root=(rel == "."),
        is_standalone=not governed,
    )
    return decision.classification == policy_mod.INCLUDE


def _validated_registration_identity(
    root: str,
    *,
    deadline: float,
    policy_reason: str,
    policy_result: str,
) -> lifecycle.WorktreeIdentity:
    """Collect one complete registration snapshot with concurrent closed reads."""
    canonical_root = _canonical_existing_directory(root)
    if canonical_root is None or canonical_root != root:
        raise EntryUnavailable("root_not_canonical")
    commands = {
        "identity": (
            "rev-parse",
            "--show-toplevel",
            "--path-format=absolute",
            "--git-dir",
            "--git-common-dir",
        ),
        "status": (
            "status",
            "--porcelain=v2",
            "--branch",
            "-z",
            "--ignored=matching",
            "--untracked-files=all",
        ),
        "worktrees": ("worktree", "list", "--porcelain", "-z"),
        "flags": ("ls-files", "-v", "-z"),
        "config": (
            "config",
            "--get-regexp",
            r"^(remote\.origin\.url|core\.hookspath)$",
        ),
    }
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(commands)) as executor:
        futures = {
            name: executor.submit(
                _git,
                root,
                *arguments,
                deadline=deadline,
            )
            for name, arguments in commands.items()
        }
        results = {name: future.result() for name, future in futures.items()}
    if any(
        result.returncode != 0
        for name, result in results.items()
        if name != "config"
    ) or results["config"].returncode not in {0, 1}:
        raise EntryUnavailable("git_identity_unavailable")

    identity_lines = results["identity"].stdout.splitlines()
    if len(identity_lines) != 3:
        raise EntryUnavailable("git_identity_unavailable")
    top = _canonical_existing_directory(identity_lines[0])
    git_dir = _canonical_existing_directory(identity_lines[1])
    common = _canonical_existing_directory(identity_lines[2])

    headers: dict[str, str] = {}
    ordinary_status: list[str] = []
    ignored_paths: list[str] = []
    for token in results["status"].stdout.split("\0"):
        if not token:
            continue
        if token.startswith("# ") and " " in token[2:]:
            key, value = token[2:].split(" ", 1)
            if key in headers:
                raise EntryUnavailable("git_identity_unavailable")
            headers[key] = value
        elif token.startswith("! "):
            ignored_paths.append(token[2:])
        else:
            ordinary_status.append(token)
    branch = headers.get("branch.head", "")
    head = headers.get("branch.oid", "")
    if (
        top != root
        or git_dir is None
        or common is None
        or git_dir == common
        or not _valid_branch(branch)
        or _OBJECT_ID.fullmatch(head) is None
    ):
        raise EntryUnavailable("not_eligible_linked_worktree")
    registrations = _parse_worktrees(results["worktrees"].stdout)
    matches = []
    for record in registrations:
        registered = record.get("worktree")
        if _canonical_existing_directory(registered) == root:
            matches.append(record)
    if len(matches) != 1:
        raise EntryUnavailable("git_registration_ambiguous")
    registration = matches[0]
    if (
        registration.get("bare") is True
        or registration.get("detached") is True
        or registration.get("prunable") is not None
        or registration.get("HEAD") != head
        or registration.get("branch") != f"refs/heads/{branch}"
    ):
        raise EntryUnavailable("git_registration_mismatch")
    identity_value = lifecycle.WorktreeIdentity(
        root=root,
        git_dir=git_dir,
        git_common_dir=common,
        branch=branch,
        head=head,
    )

    if any(token != "? .awa/lease.json" for token in ordinary_status):
        raise EntryUnavailable("worktree_dirty")
    if any(path not in {".awa/", ".awa/lease.json"} for path in ignored_paths):
        raise EntryUnavailable("worktree_ignored_state")
    for record in results["flags"].stdout.split("\0"):
        if record and (record[0] == "S" or record[0].islower()):
            raise EntryUnavailable("index_hidden_state")
    git_directory = Path(identity_value.git_dir)
    for name in (
        "MERGE_HEAD",
        "CHERRY_PICK_HEAD",
        "REVERT_HEAD",
        "BISECT_LOG",
        "rebase-merge",
        "rebase-apply",
        "sequencer",
        "index.lock",
        "HEAD.lock",
    ):
        marker = git_directory / name
        try:
            marker.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise EntryUnavailable("git_operation_unknown") from exc
        raise EntryUnavailable("git_operation_active")

    origin_values: list[str] = []
    hooks_values: list[str] = []
    for line in results["config"].stdout.splitlines():
        key, separator, value = line.partition(" ")
        if not separator or not value:
            raise EntryUnavailable("policy_unavailable")
        if key == "remote.origin.url":
            origin_values.append(value)
        elif key == "core.hookspath":
            hooks_values.append(value)
        else:
            raise EntryUnavailable("policy_unavailable")
    if len(set(hooks_values)) > 1:
        raise EntryUnavailable("policy_unavailable")
    if not _policy_decision(
        identity_value,
        has_origin=bool(origin_values),
        hooks_path=hooks_values[0] if hooks_values else "",
    ):
        raise EntryUnavailable(policy_reason, result=policy_result)
    return identity_value


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        + "\n"
    ).encode("utf-8")


def _closed_json_object(pairs: list[tuple[str, object]]) -> dict:
    value: dict = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _write_all(fd: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        written = os.write(fd, data[offset:])
        if written <= 0:
            raise OSError("short native-entry write")
        offset += written


def _private_receipt_dir(*, create: bool) -> tuple[Path, int] | None:
    directory = native_entry_dir()
    if create:
        state_home = paths.state_home()
        state_home.mkdir(parents=True, exist_ok=True, mode=paths.DIR_MODE)
        state_home_meta = state_home.lstat()
        if (
            state_home.is_symlink()
            or not stat.S_ISDIR(state_home_meta.st_mode)
            or state_home_meta.st_uid != os.getuid()
        ):
            raise EntryUnavailable(
                "native_entry_directory_conflict",
                result="conflict",
            )
        state_root = paths.awa_state_dir()
        try:
            state_root.mkdir(mode=paths.DIR_MODE)
        except FileExistsError:
            pass
        state_root_meta = state_root.lstat()
        if (
            state_root.is_symlink()
            or not stat.S_ISDIR(state_root_meta.st_mode)
            or stat.S_IMODE(state_root_meta.st_mode) != paths.DIR_MODE
            or state_root_meta.st_uid != os.getuid()
        ):
            raise EntryUnavailable(
                "native_entry_directory_conflict",
                result="conflict",
            )
        try:
            directory.mkdir(mode=paths.DIR_MODE)
        except FileExistsError:
            pass
    try:
        metadata = directory.lstat()
    except FileNotFoundError:
        return None
    if (
        directory.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != paths.DIR_MODE
        or metadata.st_uid != os.getuid()
    ):
        raise EntryUnavailable("native_entry_directory_conflict", result="conflict")
    flags = os.O_RDONLY
    flags |= getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(str(directory), flags)
    opened = os.fstat(fd)
    if (
        not stat.S_ISDIR(opened.st_mode)
        or (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino)
    ):
        os.close(fd)
        raise EntryUnavailable("native_entry_directory_conflict", result="conflict")
    return directory, fd


@contextlib.contextmanager
def _receipt_lock(
    *,
    deadline: float | None = None,
) -> Iterator[tuple[Path, int]]:
    opened = _private_receipt_dir(create=True)
    if opened is None:  # pragma: no cover - create=True guarantees a result.
        raise EntryUnavailable("native_entry_directory_unavailable")
    directory, directory_fd = opened
    flags = os.O_RDWR | os.O_CREAT
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    lock_fd = os.open(".lock", flags, paths.FILE_MODE, dir_fd=directory_fd)
    try:
        metadata = os.fstat(lock_fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
        ):
            raise EntryUnavailable(
                "native_entry_lock_conflict",
                result="conflict",
            )
        os.fchmod(lock_fd, paths.FILE_MODE)
        while True:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                _remaining(deadline)
                time.sleep(min(0.01, _remaining(deadline)))
        yield directory, directory_fd
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
        os.close(directory_fd)


def _read_fd_json(directory_fd: int, name: str) -> dict | None:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(name, flags, dir_fd=directory_fd)
    except FileNotFoundError:
        return None
    try:
        metadata = os.fstat(fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != paths.FILE_MODE
            or metadata.st_uid != os.getuid()
        ):
            raise EntryUnavailable("native_entry_receipt_conflict", result="conflict")
        raw = os.read(fd, _MAX_RECEIPT_BYTES + 1)
        if len(raw) > _MAX_RECEIPT_BYTES:
            raise EntryUnavailable("native_entry_receipt_conflict", result="conflict")
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_closed_json_object,
        )
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise EntryUnavailable("native_entry_receipt_conflict", result="conflict") from exc
    finally:
        os.close(fd)
    return value if isinstance(value, dict) else None


def _valid_receipt(value: object, *, name: str | None = None) -> dict | None:
    if not isinstance(value, dict):
        return None
    schema = value.get("schema")
    if schema == SCHEMA_V1:
        if set(value) != RECEIPT_V1_KEYS:
            return None
        results = RESULTS_V1
        actions = _ACTIONS_V1
    elif schema == SCHEMA_V2:
        if set(value) != RECEIPT_V2_KEYS:
            return None
        results = RESULTS_V2
        actions = _ACTIONS_V2
    else:
        return None
    root = value.get("root")
    session = value.get("session_id")
    git_dir = value.get("git_dir")
    common = value.get("git_common_dir")
    result = value.get("result")
    action = value.get("action")
    lease_id = value.get("lease_id")
    if (
        not isinstance(root, str)
        or not os.path.isabs(root)
        or root != os.path.realpath(os.path.abspath(root))
        or not isinstance(session, str)
        or _SESSION_ID.fullmatch(session) is None
        or not _valid_branch(value.get("branch"))
        or not isinstance(value.get("head"), str)
        or _OBJECT_ID.fullmatch(value["head"]) is None
        or not isinstance(git_dir, str)
        or not os.path.isabs(git_dir)
        or git_dir != os.path.realpath(os.path.abspath(git_dir))
        or not isinstance(common, str)
        or not os.path.isabs(common)
        or common != os.path.realpath(os.path.abspath(common))
        or type(value.get("generation")) is not int
        or value["generation"] < 1
        or not _valid_timestamp(value.get("timestamp"))
        or result not in results
        or not isinstance(value.get("reason"), str)
        or not value["reason"]
    ):
        return None
    if schema == SCHEMA_V2 and (
        value.get("source_event") not in SOURCE_EVENTS
        or value.get("conversation_id") != session
        or not isinstance(value.get("source_generation_id"), str)
        or _SESSION_ID.fullmatch(value["source_generation_id"]) is None
        or value["reason"] not in _V2_REASONS
    ):
        return None
    if result == "success":
        if action not in actions or not isinstance(lease_id, str) or not lease_id:
            return None
    elif action is not None or lease_id is not None:
        return None
    if schema == SCHEMA_V2:
        reason = value["reason"]
        if result == "pending" and reason != "registration_pending":
            return None
        if result == "success" and (
            (action == "recovered" and reason != "recovered")
            or (action != "recovered" and reason != "registered")
        ):
            return None
        if (
            result not in {"pending", "success"}
            and reason not in _V2_TERMINAL_FAILURE_REASONS
        ):
            return None
    if name is not None and name != receipt_path(root, session).name:
        return None
    return dict(value)


def _read_existing_locked(
    directory_fd: int,
    name: str,
) -> dict | None:
    value = _read_fd_json(directory_fd, name)
    if value is None:
        try:
            os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            return None
        raise EntryUnavailable(
            "native_entry_receipt_conflict",
            result="conflict",
        )
    validated = _valid_receipt(value, name=name)
    if validated is None:
        raise EntryUnavailable(
            "native_entry_receipt_conflict",
            result="conflict",
        )
    return validated


def _preflight_receipt(
    root: str,
    session_id: str,
    *,
    deadline: float | None = None,
) -> dict | None:
    with _receipt_lock(deadline=deadline) as (_directory, directory_fd):
        name = receipt_path(root, session_id).name
        try:
            return _read_existing_locked(directory_fd, name)
        except OSError as exc:
            raise EntryUnavailable(
                "native_entry_receipt_conflict",
                result="conflict",
            ) from exc


def _build_receipt(
    payload: EntryPayload,
    identity_value: lifecycle.WorktreeIdentity,
    *,
    generation: int,
    result: str,
    action: str | None,
    lease_id: str | None,
    reason: str,
) -> dict:
    if result not in RESULTS_V2 or reason not in _V2_REASONS:
        raise ValueError("invalid native-entry result")
    receipt = {
        "schema": SCHEMA_V2,
        "source_event": payload.source_event,
        "root": identity_value.root,
        "session_id": payload.session_id,
        "conversation_id": payload.conversation_id,
        "source_generation_id": payload.source_generation_id,
        "branch": identity_value.branch,
        "head": identity_value.head,
        "git_dir": identity_value.git_dir,
        "git_common_dir": identity_value.git_common_dir,
        "generation": generation,
        "timestamp": _now(),
        "result": result,
        "action": action,
        "lease_id": lease_id,
        "reason": reason,
    }
    name = receipt_path(payload.root, payload.session_id).name
    if _valid_receipt(receipt, name=name) is None:
        raise ValueError("invalid native-entry receipt")
    return receipt


def _write_receipt_locked(
    directory_fd: int,
    name: str,
    receipt: dict,
    *,
    replacing: bool,
) -> None:
    temp_name = f".{name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    temp_fd = os.open(
        temp_name,
        flags,
        paths.FILE_MODE,
        dir_fd=directory_fd,
    )
    try:
        os.fchmod(temp_fd, paths.FILE_MODE)
        _write_all(temp_fd, _json_bytes(receipt))
        os.fsync(temp_fd)
    finally:
        os.close(temp_fd)
    try:
        if replacing:
            os.replace(
                temp_name,
                name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
            )
        else:
            os.link(
                temp_name,
                name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
            os.fsync(directory_fd)
            os.unlink(temp_name, dir_fd=directory_fd)
        os.fsync(directory_fd)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temp_name, dir_fd=directory_fd)
        raise


def _write_receipt(
    payload: EntryPayload,
    identity_value: lifecycle.WorktreeIdentity,
    *,
    result: str,
    action: str | None,
    lease_id: str | None,
    reason: str,
    deadline: float | None = None,
) -> dict:
    """Write one monotonic v2 record; production terminal writes use CAS below."""
    with _receipt_lock(deadline=deadline) as (_directory, directory_fd):
        name = receipt_path(payload.root, payload.session_id).name
        existing = _read_existing_locked(directory_fd, name)
        generation = int(existing["generation"]) + 1 if existing else 1
        receipt = _build_receipt(
            payload,
            identity_value,
            generation=generation,
            result=result,
            action=action,
            lease_id=lease_id,
            reason=reason,
        )
        _write_receipt_locked(
            directory_fd,
            name,
            receipt,
            replacing=existing is not None,
        )
        return receipt


def _attempt_matches(receipt: dict, pending: dict) -> bool:
    return (
        receipt.get("schema") == SCHEMA_V2
        and pending.get("schema") == SCHEMA_V2
        and receipt.get("generation") == pending.get("generation")
        and receipt.get("result") == "pending"
        and all(receipt.get(key) == pending.get(key) for key in _ATTEMPT_KEYS)
    )


def _publish_pending(
    payload: EntryPayload,
    identity_value: lifecycle.WorktreeIdentity,
    *,
    deadline: float | None = None,
) -> dict:
    with _receipt_lock(deadline=deadline) as (_directory, directory_fd):
        name = receipt_path(payload.root, payload.session_id).name
        existing = _read_existing_locked(directory_fd, name)
        generation = int(existing["generation"]) + 1 if existing else 1
        pending = _build_receipt(
            payload,
            identity_value,
            generation=generation,
            result="pending",
            action=None,
            lease_id=None,
            reason="registration_pending",
        )
        _write_receipt_locked(
            directory_fd,
            name,
            pending,
            replacing=existing is not None,
        )
        return pending


def _publish_success(
    pending: dict,
    *,
    action: str,
    lease_id: str,
    reason: str,
    deadline: float | None = None,
) -> dict | None:
    with _receipt_lock(deadline=deadline) as (_directory, directory_fd):
        name = receipt_path(pending["root"], pending["session_id"]).name
        current = _read_existing_locked(directory_fd, name)
        if current is None or not _attempt_matches(current, pending):
            return None
        success = dict(current)
        success.update(
            {
                "generation": int(current["generation"]) + 1,
                "timestamp": _now(),
                "result": "success",
                "action": action,
                "lease_id": lease_id,
                "reason": reason,
            }
        )
        if _valid_receipt(success, name=name) is None:
            raise ValueError("invalid native-entry success receipt")
        _write_receipt_locked(
            directory_fd,
            name,
            success,
            replacing=True,
        )
        return success


def _publish_terminal_failure(
    pending: dict,
    *,
    result: str,
    reason: str,
    deadline: float | None = None,
) -> dict | None:
    if result not in {"stale", "mismatched", "conflict", "failed"}:
        raise ValueError("invalid terminal native-entry failure")
    if reason not in _V2_REASONS:
        reason = "registration_failed"
    with _receipt_lock(deadline=deadline) as (_directory, directory_fd):
        name = receipt_path(pending["root"], pending["session_id"]).name
        current = _read_existing_locked(directory_fd, name)
        if current is None or not _attempt_matches(current, pending):
            return None
        terminal = dict(current)
        terminal.update(
            {
                "generation": int(current["generation"]) + 1,
                "timestamp": _now(),
                "result": result,
                "action": None,
                "lease_id": None,
                "reason": reason,
            }
        )
        if _valid_receipt(terminal, name=name) is None:
            raise ValueError("invalid native-entry failure receipt")
        _write_receipt_locked(
            directory_fd,
            name,
            terminal,
            replacing=True,
        )
        return terminal


def _read_disk_lease(
    identity_value: lifecycle.WorktreeIdentity,
) -> tuple[str, dict | None]:
    directory = Path(identity_value.root) / ".awa"
    try:
        metadata = directory.lstat()
    except FileNotFoundError:
        return "absent", None
    except OSError:
        return "conflict", None
    if (
        directory.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != paths.DIR_MODE
        or metadata.st_uid != os.getuid()
    ):
        return "conflict", None
    directory_flags = os.O_RDONLY
    directory_flags |= getattr(os, "O_DIRECTORY", 0)
    directory_flags |= getattr(os, "O_CLOEXEC", 0)
    directory_flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        directory_fd = os.open(str(directory), directory_flags)
    except OSError:
        return "conflict", None
    try:
        opened_directory = os.fstat(directory_fd)
        if (
            not stat.S_ISDIR(opened_directory.st_mode)
            or (opened_directory.st_dev, opened_directory.st_ino)
            != (metadata.st_dev, metadata.st_ino)
        ):
            return "conflict", None
        names = sorted(entry.name for entry in os.scandir(directory_fd))
        if not names:
            return "absent", None
        if names != ["lease.json"]:
            return "conflict", None
        flags = os.O_RDONLY
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NONBLOCK", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open("lease.json", flags, dir_fd=directory_fd)
        except OSError:
            return "conflict", None
        try:
            lease_meta = os.fstat(fd)
            if (
                not stat.S_ISREG(lease_meta.st_mode)
                or stat.S_IMODE(lease_meta.st_mode) != paths.FILE_MODE
                or lease_meta.st_uid != os.getuid()
            ):
                return "conflict", None
            raw = os.read(fd, _MAX_RECEIPT_BYTES + 1)
        finally:
            os.close(fd)
    finally:
        os.close(directory_fd)
    if len(raw) > _MAX_RECEIPT_BYTES:
        return "conflict", None
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return "conflict", None
    if not isinstance(value, dict) or lease_mod.validate(value):
        return "conflict", None
    if (
        os.path.realpath(os.path.abspath(str(value.get("worktree_path") or "")))
        != identity_value.root
        or value.get("branch") != identity_value.branch
        or os.path.realpath(os.path.abspath(str(value.get("git_common_dir") or "")))
        != identity_value.git_common_dir
        or value.get("status", "active") != "active"
    ):
        return "conflict", value
    head = value.get("head")
    if not isinstance(head, str) or _OBJECT_ID.fullmatch(head) is None:
        return "conflict", value
    if head != identity_value.head:
        return "stale_head", value
    return "valid", value


def _matching_rows(
    state: state_mod.State,
    identity_value: lifecycle.WorktreeIdentity,
) -> list[dict]:
    rows = []
    for row in state.list_leases("active"):
        try:
            candidate = os.path.realpath(
                os.path.abspath(str(row.get("worktree_path") or ""))
            )
        except (OSError, TypeError, ValueError):
            continue
        if candidate == identity_value.root:
            rows.append(row)
    return rows


def _row_identity_matches(
    row: dict,
    identity_value: lifecycle.WorktreeIdentity,
    *,
    lease_id: str | None = None,
) -> bool:
    return bool(
        row.get("status") == "active"
        and os.path.realpath(os.path.abspath(str(row.get("worktree_path") or "")))
        == identity_value.root
        and row.get("branch") == identity_value.branch
        and os.path.realpath(os.path.abspath(str(row.get("git_common_dir") or "")))
        == identity_value.git_common_dir
        and (lease_id is None or row.get("lease_id") == lease_id)
    )


def _row_matches(
    row: dict,
    identity_value: lifecycle.WorktreeIdentity,
    *,
    lease_id: str | None = None,
) -> bool:
    return bool(
        _row_identity_matches(
            row,
            identity_value,
            lease_id=lease_id,
        )
        and row.get("head") == identity_value.head
    )


def _lease_from_row(row: dict) -> dict:
    return {
        key: row.get(key)
        for key in (
            "lease_id",
            "worktree_path",
            "branch",
            "git_common_dir",
            "boot_id",
            "base_ref",
            "head",
            "status",
            "created_at",
            "pid",
        )
    } | {"schema": lease_mod.SCHEMA}


def _require_current_session(
    payload: EntryPayload,
    identity_value: lifecycle.WorktreeIdentity,
    *,
    expected_boot_id: str,
) -> dict:
    try:
        from kernel.lib import awa_roots

        current, status_value = awa_roots._read_current_session(  # noqa: SLF001
            payload.root,
            expected_boot_id=expected_boot_id,
        )
        record, corrupt = awa_roots.read_record(payload.root)
    except Exception as exc:
        raise EntryUnavailable("current_session_invalid") from exc
    if (
        status_value != "ok"
        or not isinstance(current, dict)
        or corrupt
        or not isinstance(record, dict)
    ):
        raise EntryUnavailable("current_session_invalid")
    expected = {
        "root": payload.root,
        "session_id": payload.session_id,
        "conversation_id": payload.conversation_id,
        "session_key": awa_roots.session_key(payload.session_id),
        "branch": identity_value.branch,
        "common_dir": identity_value.git_common_dir,
        "boot_id": expected_boot_id,
    }
    if any(current.get(key) != value for key, value in expected.items()):
        raise EntryUnavailable("current_session_invalid")
    sessions = record.get("sessions") if isinstance(record, dict) else None
    member = (
        sessions.get(expected["session_key"])
        if isinstance(sessions, dict)
        else None
    )
    if not isinstance(member, dict):
        raise EntryUnavailable("current_session_invalid")
    member_expected = {
        "session_id": payload.session_id,
        "branch": identity_value.branch,
        "git_common_dir": identity_value.git_common_dir,
        "boot_id": expected_boot_id,
    }
    if any(member.get(key) != value for key, value in member_expected.items()):
        raise EntryUnavailable("current_session_invalid")
    heartbeat_epoch = member.get("last_heartbeat_epoch")
    age = int(time.time()) - heartbeat_epoch if type(heartbeat_epoch) is int else -1
    if (
        type(heartbeat_epoch) is not int
        or heartbeat_epoch <= 0
        or age < 0
        or age >= awa_roots._ttl_seconds()  # noqa: SLF001
        or member.get("pid") is not None
    ):
        raise EntryUnavailable("current_session_invalid")
    return current


def _bind_payload_session(
    payload: EntryPayload,
    identity_value: lifecycle.WorktreeIdentity,
    *,
    deadline: float,
) -> str:
    try:
        from kernel.lib import awa_roots

        while True:
            bound = awa_roots.heartbeat_and_bind_current_session(
                payload.root,
                session_id=payload.session_id,
                conversation_id=payload.conversation_id,
                branch=identity_value.branch,
                common_dir=identity_value.git_common_dir,
                source=payload.source_event,
                lock_timeout=_remaining(deadline),
                deadline=deadline,
            )
            if bound.get("ok"):
                break
            if (
                payload.source_event != "beforeSubmitPrompt"
                or bound.get("reason") != "current_session_session_mismatch"
                or _remaining(deadline) <= 0.03
            ):
                raise EntryUnavailable("current_session_invalid")
            time.sleep(min(0.025, _remaining(deadline)))
    except EntryUnavailable:
        raise
    except Exception as exc:
        raise EntryUnavailable("current_session_invalid") from exc
    bound_current = bound.get("current_session")
    expected_boot = (
        bound_current.get("boot_id")
        if isinstance(bound_current, dict)
        else None
    )
    if not isinstance(expected_boot, str) or not expected_boot:
        raise EntryUnavailable("current_session_invalid")
    _require_current_session(
        payload,
        identity_value,
        expected_boot_id=expected_boot,
    )
    return expected_boot


def _receipt_identity_matches(
    receipt: dict,
    payload: EntryPayload,
    identity_value: lifecycle.WorktreeIdentity,
) -> bool:
    if (
        receipt.get("root") != payload.root
        or receipt.get("session_id") != payload.session_id
        or receipt.get("schema") != SCHEMA_V2
        or receipt.get("conversation_id") != payload.conversation_id
    ):
        return False
    return all(
        receipt.get(key) == getattr(identity_value, attribute)
        for key, attribute in (
            ("root", "root"),
            ("branch", "branch"),
            ("head", "head"),
            ("git_dir", "git_dir"),
            ("git_common_dir", "git_common_dir"),
        )
    )


def _attested_lifecycle_snapshot(
    identity_value: lifecycle.WorktreeIdentity,
    *,
    lease_id: str | None = None,
    deadline: float | None = None,
) -> str | None:
    disk_state, disk = _read_disk_lease(identity_value)
    if disk_state != "valid" or disk is None:
        return None
    observed_lease = disk.get("lease_id")
    if (
        not isinstance(observed_lease, str)
        or not observed_lease
        or (lease_id is not None and observed_lease != lease_id)
    ):
        return None
    try:
        connection = _ro_connection(deadline=deadline)
        try:
            rows = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM leases "
                    "WHERE status='active' AND worktree_path=?",
                    (identity_value.root,),
                ).fetchall()
            ]
        finally:
            connection.close()
    except (OSError, sqlite3.Error):
        return None
    if (
        len(rows) != 1
        or not _row_matches(
            rows[0],
            identity_value,
            lease_id=observed_lease,
        )
        or not isinstance(rows[0].get("attested_at"), str)
        or not rows[0]["attested_at"]
    ):
        return None
    return observed_lease


def _register_under_lock(
    expected: lifecycle.WorktreeIdentity,
    state: state_mod.State,
    *,
    deadline: float | None = None,
) -> tuple[str, str]:
    # The caller has just repeated the complete Git/policy/content/session
    # validation while holding the lifecycle lock. ``lifecycle.adopt`` and
    # ``lifecycle.attest`` additionally re-read their write identity.
    observed = expected
    lifecycle_git_env = _git_env()
    disk_state, disk = _read_disk_lease(observed)
    rows = _matching_rows(state, observed)
    if disk_state == "conflict" or len(rows) > 1:
        raise EntryUnavailable("registration_conflict", result="conflict")

    if disk_state == "absent" and not rows:
        adopted = lifecycle.adopt(
            observed.root,
            state=state,
            expected_identity=observed,
            lock_held=True,
            exclusive_lease=True,
            deadline=deadline,
            git_env=lifecycle_git_env,
        )
        if not adopted.attested:
            raise EntryUnavailable("attestation_failed")
        action = "adopted"
        lease_id = adopted.lease_id
    elif disk_state in {"valid", "stale_head"} and len(rows) == 1:
        if (
            disk is None
            or not _row_identity_matches(
                rows[0],
                observed,
                lease_id=disk["lease_id"],
            )
        ):
            raise EntryUnavailable("registration_conflict", result="conflict")
        repaired_head = (
            disk_state == "stale_head"
            or rows[0].get("head") != observed.head
        )
        if repaired_head:
            updated = dict(disk)
            updated["head"] = observed.head
            if disk_state == "stale_head":
                lease_mod.replace_lease(
                    observed.root,
                    updated,
                    expected_lease_id=disk["lease_id"],
                )
            state.upsert_lease(updated)
            state.record_event(
                "native_entry_repair",
                "repaired exact lease HEAD projection",
                updated["lease_id"],
            )
            disk = updated
        attested, _reason = lifecycle.attest(
            observed.root,
            state=state,
            expected_identity=observed,
            lock_held=True,
            allow_rekey=False,
            deadline=deadline,
            git_env=lifecycle_git_env,
        )
        if not attested:
            raise EntryUnavailable("attestation_failed")
        action = "repaired" if repaired_head else "attested"
        lease_id = disk["lease_id"]
    elif disk_state in {"valid", "stale_head"} and not rows:
        if disk is None:
            raise EntryUnavailable("registration_conflict", result="conflict")
        if disk_state == "stale_head":
            updated = dict(disk)
            updated["head"] = observed.head
            lease_mod.replace_lease(
                observed.root,
                updated,
                expected_lease_id=disk["lease_id"],
            )
            disk = updated
        state.upsert_lease(disk)
        state.record_event(
            "native_entry_repair",
            "repaired exact disk-only lease projection",
            disk["lease_id"],
        )
        attested, _reason = lifecycle.attest(
            observed.root,
            state=state,
            expected_identity=observed,
            lock_held=True,
            allow_rekey=False,
            deadline=deadline,
            git_env=lifecycle_git_env,
        )
        if not attested:
            raise EntryUnavailable("attestation_failed")
        action = "repaired"
        lease_id = disk["lease_id"]
    elif disk_state == "absent" and len(rows) == 1:
        row = rows[0]
        if not _row_identity_matches(row, observed):
            raise EntryUnavailable("registration_conflict", result="conflict")
        restored = _lease_from_row(row)
        restored["head"] = observed.head
        if lease_mod.validate(restored):
            raise EntryUnavailable("registration_conflict", result="conflict")
        lease_mod.create_lease(observed.root, restored)
        state.upsert_lease(restored)
        state.record_event(
            "native_entry_repair",
            "repaired exact SQLite-only lease projection",
            restored["lease_id"],
        )
        attested, _reason = lifecycle.attest(
            observed.root,
            state=state,
            expected_identity=observed,
            lock_held=True,
            allow_rekey=False,
            deadline=deadline,
            git_env=lifecycle_git_env,
        )
        if not attested:
            raise EntryUnavailable("attestation_failed")
        action = "repaired"
        lease_id = restored["lease_id"]
    else:  # Defensive closed world.
        raise EntryUnavailable("registration_conflict", result="conflict")

    final_disk_state, final_disk = _read_disk_lease(observed)
    final_rows = _matching_rows(state, observed)
    if (
        final_disk_state != "valid"
        or final_disk is None
        or final_disk.get("lease_id") != lease_id
        or len(final_rows) != 1
        or not _row_matches(final_rows[0], observed, lease_id=lease_id)
        or not isinstance(final_rows[0].get("attested_at"), str)
        or not final_rows[0]["attested_at"]
    ):
        raise EntryUnavailable("registration_conflict", result="conflict")
    return action, lease_id


def _register_payload(
    payload: EntryPayload,
    *,
    lock_timeout: float,
    deadline: float,
) -> EntryResult:
    identity_value: lifecycle.WorktreeIdentity | None = None
    pending: dict | None = None
    lifecycle_complete = False
    try:
        identity_value = _validated_registration_identity(
            payload.root,
            deadline=deadline,
            policy_reason="policy_ineligible",
            policy_result="failed",
        )
        _preflight_receipt(
            payload.root,
            payload.session_id,
            deadline=deadline,
        )
        current_boot = _bind_payload_session(
            payload,
            identity_value,
            deadline=deadline,
        )

        common_timeout = min(
            max(0.0, lock_timeout),
            _remaining(deadline),
        )
        with lock.common_dir_lock(
            identity_value.git_common_dir,
            timeout=common_timeout,
        ):
            observed = _validated_registration_identity(
                payload.root,
                deadline=deadline,
                policy_reason="policy_changed",
                policy_result="mismatched",
            )
            if observed != identity_value:
                raise EntryUnavailable(
                    "identity_changed",
                    result="mismatched",
                )
            _require_current_session(
                payload,
                observed,
                expected_boot_id=current_boot,
            )

            existing = _preflight_receipt(
                payload.root,
                payload.session_id,
                deadline=deadline,
            )
            exact_success = (
                existing is not None
                and existing.get("schema") == SCHEMA_V2
                and existing.get("result") == "success"
                and _receipt_identity_matches(existing, payload, observed)
            )
            if exact_success:
                success_lease = str(existing.get("lease_id") or "")
                exact_success = (
                    _attested_lifecycle_snapshot(
                        observed,
                        lease_id=success_lease,
                        deadline=deadline,
                    )
                    == success_lease
                )
            if exact_success:
                final_identity = _validated_registration_identity(
                    payload.root,
                    deadline=deadline,
                    policy_reason="policy_changed",
                    policy_result="mismatched",
                )
                _require_current_session(
                    payload,
                    final_identity,
                    expected_boot_id=current_boot,
                )
                if (
                    final_identity == observed
                    and _attested_lifecycle_snapshot(
                        final_identity,
                        lease_id=success_lease,
                        deadline=deadline,
                    )
                    == success_lease
                ):
                    return EntryResult(
                        "success",
                        None,
                        "already_registered",
                        existing,
                    )
                # Live drift defeats the no-op. Continue through a fresh
                # monotonic pending attempt bound to the newly observed state.
                observed = final_identity

            if (
                existing is not None
                and existing.get("schema") == SCHEMA_V2
                and existing.get("result") == "pending"
                and _receipt_identity_matches(existing, payload, observed)
            ):
                recovered_lease = _attested_lifecycle_snapshot(
                    observed,
                    deadline=deadline,
                )
                if recovered_lease is not None:
                    final_identity = _validated_registration_identity(
                        payload.root,
                        deadline=deadline,
                        policy_reason="policy_changed",
                        policy_result="mismatched",
                    )
                    if final_identity != observed:
                        raise EntryUnavailable(
                            "identity_changed",
                            result="mismatched",
                        )
                    _require_current_session(
                        payload,
                        final_identity,
                        expected_boot_id=current_boot,
                    )
                    if (
                        _attested_lifecycle_snapshot(
                            final_identity,
                            lease_id=recovered_lease,
                            deadline=deadline,
                        )
                        != recovered_lease
                    ):
                        raise EntryUnavailable(
                            "registration_conflict",
                            result="conflict",
                        )
                    receipt = _publish_success(
                        existing,
                        action="recovered",
                        lease_id=recovered_lease,
                        reason="recovered",
                        deadline=deadline,
                    )
                    if receipt is None:
                        raise EntryUnavailable("registration_conflict", result="conflict")
                    return EntryResult(
                        "success",
                        "recovered",
                        "recovered",
                        receipt,
                    )

            # Fixed nesting: the common-directory lifecycle lock is already
            # held before the receipt lock is acquired. No receipt-locked path
            # below acquires the common-directory lock.
            pending = _publish_pending(
                payload,
                observed,
                deadline=deadline,
            )
            with state_mod.State(
                timeout_seconds=_remaining(deadline),
            ) as state:
                with contextlib.suppress(sqlite3.Error):
                    state.conn.execute(
                        f"PRAGMA busy_timeout={max(1, int(_remaining(deadline) * 1000))}"
                    )
                action, lease_id = _register_under_lock(
                    observed,
                    state,
                    deadline=deadline,
                )
                lifecycle_complete = True

            final_identity = _validated_registration_identity(
                payload.root,
                deadline=deadline,
                policy_reason="policy_changed",
                policy_result="mismatched",
            )
            if final_identity != observed:
                raise EntryUnavailable(
                    "identity_changed",
                    result="mismatched",
                )
            _require_current_session(
                payload,
                final_identity,
                expected_boot_id=current_boot,
            )
            if (
                _attested_lifecycle_snapshot(
                    final_identity,
                    lease_id=lease_id,
                    deadline=deadline,
                )
                != lease_id
            ):
                raise EntryUnavailable(
                    "registration_conflict",
                    result="conflict",
                )
            receipt = _publish_success(
                pending,
                action=action,
                lease_id=lease_id,
                reason="registered",
                deadline=deadline,
            )
            if receipt is None:
                raise EntryUnavailable(
                    "registration_conflict",
                    result="conflict",
                )
        return EntryResult("success", action, "registered", receipt)
    except lock.LockBusy:
        result, reason = "failed", "lock_busy"
    except EntryUnavailable as exc:
        result = (
            exc.result
            if exc.result in {"stale", "mismatched", "conflict", "failed"}
            else "failed"
        )
        reason = (
            exc.reason
            if exc.reason in _V2_REASONS
            else "registration_failed"
        )
    except (
        FileExistsError,
        OSError,
        sqlite3.Error,
        subprocess.SubprocessError,
        ValueError,
        RuntimeError,
    ):
        result, reason = "failed", "registration_failed"
    except BaseException:
        # This models abrupt hook/worker loss. If lifecycle finished, retaining
        # pending evidence makes the next exact attempt recoverable without
        # emitting another lifecycle event.
        return EntryResult("failed", None, "registration_failed", pending)

    receipt = None
    if pending is not None and not lifecycle_complete:
        try:
            receipt = _publish_terminal_failure(
                pending,
                result=result,
                reason=reason,
                deadline=deadline,
            )
        except BaseException:
            receipt = None
    return EntryResult(result, None, reason, receipt)


def register_event(
    payload_value: object,
    *,
    lock_timeout: float = 1.0,
    deadline: float | None = None,
) -> EntryResult:
    """Register one supported event; expected failures remain contained."""
    try:
        payload = parse_entry_payload(payload_value)
    except EntryUnavailable as exc:
        return EntryResult(exc.result, None, exc.reason)
    absolute_deadline = (
        deadline
        if deadline is not None
        else time.monotonic() + _DEFAULT_REGISTRATION_SECONDS
    )
    return _register_payload(
        payload,
        lock_timeout=lock_timeout,
        deadline=absolute_deadline,
    )


def register_session_start(
    payload_value: object,
    *,
    lock_timeout: float = 1.0,
    deadline: float | None = None,
) -> EntryResult:
    """Compatibility entry point restricted to an exact ``sessionStart``."""
    try:
        payload = parse_session_start(payload_value)
    except EntryUnavailable as exc:
        return EntryResult(exc.result, None, exc.reason)
    absolute_deadline = (
        deadline
        if deadline is not None
        else time.monotonic() + _DEFAULT_REGISTRATION_SECONDS
    )
    return _register_payload(
        payload,
        lock_timeout=lock_timeout,
        deadline=absolute_deadline,
    )


def _read_receipts_with_state() -> tuple[list[dict], bool]:
    try:
        opened = _private_receipt_dir(create=False)
    except (EntryUnavailable, OSError):
        return [], True
    if opened is None:
        return [], False
    _directory, directory_fd = opened
    records = []
    invalid = False
    try:
        candidates = []
        for entry in os.scandir(directory_fd):
            name = entry.name
            if name == ".lock" or name.startswith("."):
                continue
            if _RECEIPT_NAME.fullmatch(name) is None:
                invalid = True
                continue
            try:
                metadata = entry.stat(follow_symlinks=False)
            except OSError:
                invalid = True
                continue
            candidates.append((metadata.st_mtime_ns, name))
        # Bounded newest-first processing keeps current session evidence
        # available without treating ordinary historical overflow as corruption.
        names = [
            name
            for _mtime, name in sorted(candidates, reverse=True)[:_MAX_RECEIPTS]
        ]
        for name in names:
            try:
                value = _read_fd_json(directory_fd, name)
            except (EntryUnavailable, OSError):
                invalid = True
                continue
            receipt = _valid_receipt(value, name=name)
            if receipt is None:
                invalid = True
                continue
            records.append(receipt)
    except OSError:
        return [], True
    finally:
        os.close(directory_fd)
    return records, invalid


def read_receipts() -> list[dict]:
    """Return bounded strict receipt records; malformed entries are never followed."""
    records, _invalid = _read_receipts_with_state()
    return records


def candidate_common_dirs() -> list[str]:
    """Read-only repository discovery seeds from strict native-entry receipts."""
    records, _invalid = _read_receipts_with_state()
    return sorted(
        {
            str(record["git_common_dir"])
            for record in records
            if isinstance(record.get("git_common_dir"), str)
            and os.path.isabs(record["git_common_dir"])
        }
    )


def inspect_lease_state(root: str) -> str:
    """Return absent|valid|conflict|unknown without changing lease state."""
    try:
        identity_value = _observe_identity(
            os.path.realpath(os.path.abspath(os.path.expanduser(root)))
        )
        state, _record = _read_disk_lease(identity_value)
    except Exception:
        return "unknown"
    return state if state in {"absent", "valid", "conflict"} else "unknown"


def _ro_connection(
    *,
    deadline: float | None = None,
) -> sqlite3.Connection:
    db = paths.state_db_path().resolve()
    connection = sqlite3.connect(
        f"file:{quote(str(db), safe='/')}?mode=ro",
        uri=True,
        isolation_level=None,
        timeout=_remaining(deadline, cap=5.0),
    )
    connection.row_factory = sqlite3.Row
    connection.execute(
        f"PRAGMA busy_timeout={max(1, int(_remaining(deadline, cap=5.0) * 1000))}"
    )
    connection.execute("PRAGMA query_only=ON")
    connection.execute("BEGIN")
    return connection


def _receipt_targets_current_session(
    receipt: dict,
) -> lifecycle.WorktreeIdentity | None:
    try:
        from kernel.lib import awa_roots

        current, status_value = awa_roots.read_current_session(receipt["root"])
        if status_value != "ok" or not isinstance(current, dict):
            return None
        disposition = awa_roots.disposition(receipt["root"])
    except Exception:
        return None
    if (
        disposition.get("disposition") != "active"
        or current.get("root") != receipt.get("root")
        or current.get("session_id") != receipt.get("session_id")
        or (
            receipt.get("schema") == SCHEMA_V2
            and current.get("conversation_id")
            != receipt.get("conversation_id")
        )
        or current.get("branch") != receipt.get("branch")
        or os.path.realpath(
            os.path.abspath(str(current.get("common_dir") or ""))
        )
        != receipt.get("git_common_dir")
    ):
        return None
    record = disposition.get("record")
    sessions = record.get("sessions") if isinstance(record, dict) else None
    session_key = awa_roots.session_key(receipt.get("session_id"))
    member = sessions.get(session_key) if isinstance(sessions, dict) else None
    if not (
        isinstance(member, dict)
        and member.get("session_id") == receipt.get("session_id")
        and member.get("boot_id") == current.get("boot_id")
        and member.get("branch") == receipt.get("branch")
        and os.path.realpath(
            os.path.abspath(str(member.get("git_common_dir") or ""))
        )
        == receipt.get("git_common_dir")
    ):
        return None
    try:
        observed = _observe_identity(receipt["root"])
    except (EntryUnavailable, OSError, subprocess.SubprocessError):
        return None
    if any(
        receipt[key] != getattr(observed, attribute)
        for key, attribute in (
            ("root", "root"),
            ("branch", "branch"),
            ("head", "head"),
            ("git_dir", "git_dir"),
            ("git_common_dir", "git_common_dir"),
        )
    ):
        return None
    return observed


def _receipt_is_current(receipt: dict) -> bool:
    if receipt.get("result") != "success":
        return False
    observed = _receipt_targets_current_session(receipt)
    if observed is None:
        return False
    disk_state, disk = _read_disk_lease(observed)
    if (
        disk_state != "valid"
        or disk is None
        or disk.get("lease_id") != receipt.get("lease_id")
    ):
        return False
    try:
        connection = _ro_connection()
        try:
            rows = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM leases WHERE status='active' AND worktree_path=?",
                    (observed.root,),
                ).fetchall()
            ]
        finally:
            connection.close()
    except (OSError, sqlite3.Error):
        return False
    if (
        len(rows) != 1
        or not _row_matches(
            rows[0],
            observed,
            lease_id=str(receipt["lease_id"]),
        )
        or not isinstance(rows[0].get("attested_at"), str)
        or not rows[0]["attested_at"]
    ):
        return False
    return True


def evidence_state() -> str:
    """Aggregate current native-entry evidence using a closed honest vocabulary."""
    records, invalid = _read_receipts_with_state()
    if invalid:
        return "conflict"
    if not records:
        return "absent"
    current = [
        record
        for record in records
        if _receipt_targets_current_session(record) is not None
    ]
    current_states = {str(record.get("result")) for record in current}
    if "conflict" in current_states:
        return "conflict"
    if "mismatched" in current_states:
        return "mismatched"
    if "failed" in current_states:
        return "failed"
    if "pending" in current_states:
        return "pending"
    current_successes = [
        record for record in current if _receipt_is_current(record)
    ]
    success_kinds = {
        (
            "legacy"
            if record.get("schema") == SCHEMA_V1
            else (
                "eager"
                if record.get("source_event") == "sessionStart"
                else "recovered"
            )
        )
        for record in current_successes
    }
    if len(success_kinds) == 1:
        return next(iter(success_kinds))
    if success_kinds:
        return "success"
    return "stale"


def main(argv: list[str] | None = None) -> int:
    arguments = list(argv if argv is not None else sys.argv[1:])
    deadline = time.monotonic() + _EAGER_REGISTRATION_SECONDS
    if arguments:
        if len(arguments) != 2 or arguments[0] != "--deadline-monotonic":
            return 0
        try:
            supplied = float(arguments[1])
        except (TypeError, ValueError):
            return 0
        if not (time.monotonic() < supplied <= time.monotonic() + 5.0):
            return 0
        deadline = supplied
    try:
        raw = sys.stdin.buffer.read(_MAX_PAYLOAD_BYTES + 1)
        if len(raw) > _MAX_PAYLOAD_BYTES:
            return 0
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_closed_json_object,
        )
        register_event(payload, deadline=deadline)
    except BaseException:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
