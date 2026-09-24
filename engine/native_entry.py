"""Fail-open post-sessionStart registration for native Cursor worktrees.

The hook path is deliberately engine-side and non-authorizing. It exactly
revalidates one local linked worktree, then adopts or attests it under the
existing per-common-dir lifecycle lock. Private native-entry receipts prove
only post-start registration; they never authorize cleanup or removal.
"""

from __future__ import annotations

import contextlib
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


SCHEMA = "awa-native-entry/v1"
RESULTS = frozenset({"success", "stale", "mismatched", "conflict", "failed"})
ACTIONS = frozenset({"adopted", "attested", "repaired"})
_MAX_PAYLOAD_BYTES = 64 * 1024
_MAX_RECEIPT_BYTES = 64 * 1024
_MAX_RECEIPTS = 512
_OBJECT_ID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_SESSION_ID = re.compile(r"[^\x00-\x20\x7f]{1,512}\Z")
_RECEIPT_NAME = re.compile(r"entry-[0-9a-f]{24}-[0-9a-f]{24}\.json\Z")
_RECEIPT_KEYS = frozenset(
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
    expanded = os.path.expanduser(value)
    if not os.path.isabs(expanded):
        return None
    absolute = os.path.abspath(expanded)
    try:
        metadata = os.lstat(absolute)
    except OSError:
        return None
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        return None
    canonical = os.path.realpath(absolute)
    return canonical if canonical == absolute else None


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


def parse_session_start(value: object) -> EntryPayload:
    """Accept one explicit sessionStart root and one unambiguous session id."""
    sources = _payload_sources(value)
    events = {
        source[key].strip()
        for source in sources
        for key in ("hook_event_name", "event")
        if isinstance(source.get(key), str) and source[key].strip()
    }
    if events != {"sessionStart"}:
        raise EntryUnavailable("invalid_event")

    roots: list[str] = []
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
            if not isinstance(candidate, str) or not candidate.strip():
                raise EntryUnavailable("ambiguous_root")
            roots.append(candidate.strip())
        listed = source.get("workspace_roots")
        if listed is None:
            continue
        if (
            not isinstance(listed, list)
            or not listed
            or any(
                not isinstance(item, str) or not item.strip()
                for item in listed
            )
        ):
            raise EntryUnavailable("ambiguous_root")
        roots.extend(item.strip() for item in listed)
    canonical_roots = {_canonical_existing_directory(item) for item in roots}
    if not roots or None in canonical_roots or len(canonical_roots) != 1:
        raise EntryUnavailable("ambiguous_root")

    sessions = {
        source[key].strip()
        for source in sources
        for key in ("session_id", "sessionId")
        if isinstance(source.get(key), str) and source[key].strip()
    }
    if (
        len(sessions) != 1
        or _SESSION_ID.fullmatch(next(iter(sessions), "")) is None
    ):
        raise EntryUnavailable("ambiguous_session")
    return EntryPayload(
        root=next(iter(canonical_roots)),
        session_id=next(iter(sessions)),
    )


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
    ("rev-parse", "--show-toplevel"),
    ("rev-parse", "--path-format=absolute", "--git-dir"),
    ("rev-parse", "--path-format=absolute", "--git-common-dir"),
    ("symbolic-ref", "--quiet", "--short", "HEAD"),
    ("rev-parse", "HEAD"),
    ("status", "--porcelain=v2", "--untracked-files=all"),
    ("status", "--porcelain=v1", "--ignored=matching", "--untracked-files=all"),
    ("worktree", "list", "--porcelain", "-z"),
    ("config", "--get", "remote.origin.url"),
    ("config", "--get", "core.hooksPath"),
    ("ls-files", "-v", "-z"),
}


def _git(root: str, *args: str) -> subprocess.CompletedProcess:
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
        timeout=2,
        check=False,
        env=_git_env(),
    )


def _git_text(root: str, *args: str, allow_missing: bool = False) -> str:
    result = _git(root, *args)
    if result.returncode != 0:
        if allow_missing:
            return ""
        raise EntryUnavailable("git_identity_unavailable")
    return result.stdout.strip()


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


def _observe_identity(root: str) -> lifecycle.WorktreeIdentity:
    canonical_root = _canonical_existing_directory(root)
    if canonical_root is None or canonical_root != root:
        raise EntryUnavailable("root_not_canonical")
    top = _canonical_existing_directory(
        _git_text(root, "rev-parse", "--show-toplevel")
    )
    git_dir = _canonical_existing_directory(
        _git_text(
            root,
            "rev-parse",
            "--path-format=absolute",
            "--git-dir",
        )
    )
    common = _canonical_existing_directory(
        _git_text(
            root,
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
        )
    )
    branch = _git_text(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    head = _git_text(root, "rev-parse", "HEAD")
    if (
        top != root
        or git_dir is None
        or common is None
        or git_dir == common
        or not _valid_branch(branch)
        or _OBJECT_ID.fullmatch(head) is None
    ):
        raise EntryUnavailable("not_eligible_linked_worktree")

    registrations = _parse_worktrees(
        _git_text(root, "worktree", "list", "--porcelain", "-z")
    )
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


def _assert_clean(identity_value: lifecycle.WorktreeIdentity) -> None:
    status = _git_text(
        identity_value.root,
        "status",
        "--porcelain=v2",
        "--untracked-files=all",
    )
    status_rows = [line for line in status.splitlines() if line]
    if any(line != "? .awa/lease.json" for line in status_rows):
        raise EntryUnavailable("worktree_dirty")
    ignored = _git_text(
        identity_value.root,
        "status",
        "--porcelain=v1",
        "--ignored=matching",
        "--untracked-files=all",
    )
    ignored_rows = [
        line[3:]
        for line in ignored.splitlines()
        if line.startswith("!! ")
    ]
    if any(path not in {".awa/", ".awa/lease.json"} for path in ignored_rows):
        raise EntryUnavailable("worktree_ignored_state")
    flags = _git_text(identity_value.root, "ls-files", "-v", "-z")
    for record in flags.split("\0"):
        if not record:
            continue
        tag = record[0]
        if tag == "S" or tag.islower():
            raise EntryUnavailable("index_hidden_state")
    git_dir = Path(identity_value.git_dir)
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
        marker = git_dir / name
        try:
            marker.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise EntryUnavailable("git_operation_unknown") from exc
        raise EntryUnavailable("git_operation_active")


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


def _policy_repository(identity_value: lifecycle.WorktreeIdentity) -> str:
    """Resolve and prove the primary repository represented by a linked root."""
    common = Path(identity_value.git_common_dir)
    if common.name != ".git":
        raise EntryUnavailable("policy_repository_unavailable")
    primary = _canonical_existing_directory(str(common.parent))
    if primary is None:
        raise EntryUnavailable("policy_repository_unavailable")
    primary_top = _canonical_existing_directory(
        _git_text(primary, "rev-parse", "--show-toplevel")
    )
    primary_common = _canonical_existing_directory(
        _git_text(
            primary,
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
        )
    )
    if primary_top != primary or primary_common != identity_value.git_common_dir:
        raise EntryUnavailable("policy_repository_mismatch")
    return primary


def _policy_eligible(identity_value: lifecycle.WorktreeIdentity) -> bool:
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
        if (
            repository == canonical
            or repository.startswith(canonical + os.sep)
        ):
            governed = canonical
            break
    if governed:
        rel = (
            "."
            if repository == governed
            else repository[len(governed) + 1 :]
        )
    else:
        rel = os.path.basename(repository.rstrip(os.sep))
    origin = _git_text(
        repository,
        "config",
        "--get",
        "remote.origin.url",
        allow_missing=True,
    )
    hooks_path = _git_text(
        repository,
        "config",
        "--get",
        "core.hooksPath",
        allow_missing=True,
    )
    decision = policy_mod.classify(
        rel,
        repository,
        cfg,
        hooks_path=hooks_path,
        has_origin=bool(origin),
        is_root=(rel == "."),
        is_standalone=not governed,
    )
    return decision.classification == policy_mod.INCLUDE


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
def _receipt_lock() -> Iterator[tuple[Path, int]]:
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
        if not stat.S_ISREG(metadata.st_mode):
            raise EntryUnavailable(
                "native_entry_lock_conflict",
                result="conflict",
            )
        os.fchmod(lock_fd, paths.FILE_MODE)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
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
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise EntryUnavailable("native_entry_receipt_conflict", result="conflict") from exc
    finally:
        os.close(fd)
    return value if isinstance(value, dict) else None


def _valid_receipt(value: object, *, name: str | None = None) -> dict | None:
    if not isinstance(value, dict) or set(value) != _RECEIPT_KEYS:
        return None
    root = value.get("root")
    session = value.get("session_id")
    git_dir = value.get("git_dir")
    common = value.get("git_common_dir")
    result = value.get("result")
    action = value.get("action")
    lease_id = value.get("lease_id")
    if (
        value.get("schema") != SCHEMA
        or not isinstance(root, str)
        or not os.path.isabs(root)
        or root != os.path.realpath(os.path.abspath(root))
        or not isinstance(session, str)
        or _SESSION_ID.fullmatch(session) is None
        or not _valid_branch(value.get("branch"))
        or not isinstance(value.get("head"), str)
        or _OBJECT_ID.fullmatch(value["head"]) is None
        or not isinstance(git_dir, str)
        or not os.path.isabs(git_dir)
        or not isinstance(common, str)
        or not os.path.isabs(common)
        or type(value.get("generation")) is not int
        or value["generation"] < 1
        or not _valid_timestamp(value.get("timestamp"))
        or result not in RESULTS
        or not isinstance(value.get("reason"), str)
        or not value["reason"]
    ):
        return None
    if result == "success":
        if action not in ACTIONS or not isinstance(lease_id, str) or not lease_id:
            return None
    elif action is not None or lease_id is not None:
        return None
    if name is not None and name != receipt_path(root, session).name:
        return None
    return dict(value)


def _preflight_receipt(root: str, session_id: str) -> dict | None:
    with _receipt_lock() as (_directory, directory_fd):
        name = receipt_path(root, session_id).name
        try:
            value = _read_fd_json(directory_fd, name)
        except OSError as exc:
            raise EntryUnavailable(
                "native_entry_receipt_conflict",
                result="conflict",
            ) from exc
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


def _write_receipt(
    payload: EntryPayload,
    identity_value: lifecycle.WorktreeIdentity,
    *,
    result: str,
    action: str | None,
    lease_id: str | None,
    reason: str,
) -> dict:
    if result not in RESULTS:
        raise ValueError("invalid native-entry result")
    with _receipt_lock() as (_directory, directory_fd):
        name = receipt_path(payload.root, payload.session_id).name
        existing = _read_fd_json(directory_fd, name)
        validated = _valid_receipt(existing, name=name) if existing is not None else None
        if existing is not None and validated is None:
            raise EntryUnavailable(
                "native_entry_receipt_conflict",
                result="conflict",
            )
        generation = int(validated["generation"]) + 1 if validated is not None else 1
        receipt = {
            "schema": SCHEMA,
            "root": identity_value.root,
            "session_id": payload.session_id,
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
        if _valid_receipt(receipt, name=name) is None:
            raise ValueError("invalid native-entry receipt")
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
            if existing is None:
                os.link(
                    temp_name,
                    name,
                    src_dir_fd=directory_fd,
                    dst_dir_fd=directory_fd,
                    follow_symlinks=False,
                )
                os.fsync(directory_fd)
                os.unlink(temp_name, dir_fd=directory_fd)
            else:
                # The target was a validated owned regular file under this
                # namespace lock; replace is same-directory and never follows it.
                os.replace(
                    temp_name,
                    name,
                    src_dir_fd=directory_fd,
                    dst_dir_fd=directory_fd,
                )
            os.fsync(directory_fd)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(temp_name, dir_fd=directory_fd)
            raise
        return receipt


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


def _register_under_lock(
    expected: lifecycle.WorktreeIdentity,
    state: state_mod.State,
) -> tuple[str, str]:
    observed = _observe_identity(expected.root)
    if observed != expected:
        raise EntryUnavailable("identity_changed", result="mismatched")
    if not _policy_eligible(observed):
        raise EntryUnavailable("policy_changed", result="mismatched")
    _assert_clean(observed)
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
        )
        if not attested:
            raise EntryUnavailable("attestation_failed")
        action = "repaired"
        lease_id = restored["lease_id"]
    else:  # Defensive closed world.
        raise EntryUnavailable("registration_conflict", result="conflict")

    final_identity = _observe_identity(expected.root)
    if final_identity != expected:
        raise EntryUnavailable("identity_changed", result="mismatched")
    final_disk_state, final_disk = _read_disk_lease(final_identity)
    final_rows = _matching_rows(state, final_identity)
    if (
        final_disk_state != "valid"
        or final_disk is None
        or final_disk.get("lease_id") != lease_id
        or len(final_rows) != 1
        or not _row_matches(final_rows[0], final_identity, lease_id=lease_id)
    ):
        raise EntryUnavailable("registration_conflict", result="conflict")
    return action, lease_id


def register_session_start(
    payload_value: object,
    *,
    lock_timeout: float = 1.0,
) -> EntryResult:
    """Fail-open native entry registration. No expected failure escapes the hook."""
    try:
        payload = parse_session_start(payload_value)
    except EntryUnavailable as exc:
        return EntryResult(exc.result, None, exc.reason)

    identity_value: lifecycle.WorktreeIdentity | None = None
    try:
        identity_value = _observe_identity(payload.root)
        if not _policy_eligible(identity_value):
            return EntryResult("failed", None, "policy_ineligible")
        _preflight_receipt(payload.root, payload.session_id)
        _assert_clean(identity_value)
        # Publish explicit degraded evidence before any lease/SQLite mutation.
        # Success replaces this record only after adoption/attestation and final
        # identity validation. A process exit in between is therefore visible
        # as incomplete registration instead of silent managed state.
        _write_receipt(
            payload,
            identity_value,
            result="failed",
            action=None,
            lease_id=None,
            reason="registration_pending",
        )
        with lock.common_dir_lock(
            identity_value.git_common_dir,
            timeout=max(0.0, lock_timeout),
        ):
            with state_mod.State() as state:
                action, lease_id = _register_under_lock(identity_value, state)
            receipt = _write_receipt(
                payload,
                identity_value,
                result="success",
                action=action,
                lease_id=lease_id,
                reason="registered",
            )
        return EntryResult("success", action, "registered", receipt)
    except lock.LockBusy:
        result, reason = "failed", "lock_busy"
    except EntryUnavailable as exc:
        result, reason = exc.result, exc.reason
    except (
        FileExistsError,
        OSError,
        sqlite3.Error,
        subprocess.SubprocessError,
        ValueError,
        RuntimeError,
    ):
        result, reason = "failed", "registration_failed"
    except BaseException:  # Hook containment: unexpected failures remain fail-open.
        result, reason = "failed", "registration_failed"

    receipt = None
    if identity_value is not None:
        try:
            receipt = _write_receipt(
                payload,
                identity_value,
                result=result,
                action=None,
                lease_id=None,
                reason=reason,
            )
        except BaseException:
            receipt = None
    return EntryResult(result, None, reason, receipt)


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


def _ro_connection() -> sqlite3.Connection:
    db = paths.state_db_path().resolve()
    connection = sqlite3.connect(
        f"file:{quote(str(db), safe='/')}?mode=ro",
        uri=True,
        isolation_level=None,
    )
    connection.row_factory = sqlite3.Row
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
    if any(_receipt_is_current(record) for record in current):
        return "success"
    return "stale"


def main(argv: list[str] | None = None) -> int:
    del argv
    try:
        raw = sys.stdin.buffer.read(_MAX_PAYLOAD_BYTES + 1)
        if len(raw) > _MAX_PAYLOAD_BYTES:
            return 0
        payload = json.loads(raw.decode("utf-8"))
        register_session_start(payload)
    except BaseException:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
