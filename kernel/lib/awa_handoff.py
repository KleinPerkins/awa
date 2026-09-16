#!/usr/bin/env python3
"""Private metadata-only Safe-Workspace handoff authority.

The producer, sessionStart consumer, and integrity reader all use this module.
It owns a dedicated lock and a single crash-safe generation record; it never
moves a session or mutates Git, worktrees, refs, leases, or hook configuration.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as _datetime
import errno
import fcntl
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import time
from pathlib import Path

SCHEMA = "awa-session-handoff/v1"
STATES = frozenset({"absent", "pending", "closed", "unknown"})
_STATUSES = frozenset({"pending", "closed"})
_KEYS = frozenset(
    {
        "schema",
        "handoff_id",
        "generation",
        "status",
        "root",
        "branch",
        "git_common_dir",
        "head",
        "timestamp",
    }
)
_OBJECT_ID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_HANDOFF_ID = re.compile(r"[0-9a-f]{32}\Z")
_MAX_RECORD_BYTES = 16 * 1024
_DURABILITY = None


class HandoffUnavailable(RuntimeError):
    """The private handoff namespace could not be safely updated."""


def _durability_module():
    """Load the sibling stdlib authority without a package dependency."""
    global _DURABILITY
    if _DURABILITY is not None:
        return _DURABILITY
    path = Path(__file__).resolve().with_name("awa_durability.py")
    spec = importlib.util.spec_from_file_location("awa_handoff_durability", path)
    if spec is None or spec.loader is None:
        raise HandoffUnavailable("durability authority is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _DURABILITY = module
    return module


def _state_home() -> Path:
    configured = os.environ.get("XDG_STATE_HOME", "").strip()
    if configured:
        return Path(configured).expanduser()
    home = os.environ.get("HOME", "").strip()
    if not home:
        raise HandoffUnavailable("HOME is unavailable")
    return Path(home).expanduser() / ".local" / "state"


def handoff_dir() -> Path:
    return _state_home() / "awa" / "handoff"


def record_path() -> Path:
    return handoff_dir() / "status.json"


def lock_path() -> Path:
    return handoff_dir() / ".lock"


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("utf-8")


def _atomic_replace(path: Path, value: dict) -> None:
    _durability_module().atomic_private_replace(str(path), _json_bytes(value))


@contextlib.contextmanager
def _lock(*, wait_seconds: float):
    directory = handoff_dir()
    _durability_module().ensure_private_directory(str(directory))
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(str(lock_path()), flags, 0o600)
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise HandoffUnavailable("handoff lock is not a regular file")
        os.fchmod(fd, 0o600)
        deadline = time.monotonic() + max(0.0, wait_seconds)
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise HandoffUnavailable("handoff lock is busy")
                time.sleep(0.01)
        yield
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _read_bytes() -> bytes | None:
    path = record_path()
    try:
        parent = path.parent.lstat()
    except FileNotFoundError:
        return None
    if (
        path.parent.is_symlink()
        or not stat.S_ISDIR(parent.st_mode)
        or stat.S_IMODE(parent.st_mode) != 0o700
    ):
        raise HandoffUnavailable("handoff directory is not private")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(str(path), flags)
    except FileNotFoundError:
        return None
    try:
        metadata = os.fstat(fd)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise HandoffUnavailable("handoff record is not private and regular")
        chunks = []
        remaining = _MAX_RECORD_BYTES + 1
        while remaining:
            chunk = os.read(fd, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > _MAX_RECORD_BYTES:
            raise HandoffUnavailable("handoff record is oversized")
        return raw
    finally:
        os.close(fd)


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
    return os.path.realpath(absolute)


def _valid_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = _datetime.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _valid_branch(value: object) -> bool:
    if not isinstance(value, str) or not value or value == "HEAD":
        return False
    if (
        value.startswith(("-", ".", "/"))
        or value.endswith((".", "/"))
        or ".." in value
        or "@{" in value
        or "//" in value
        or any(character.isspace() or character in "~^:?*[\\\\" for character in value)
    ):
        return False
    return all(part and not part.endswith(".lock") for part in value.split("/"))


def _validate(value: object) -> dict | None:
    if not isinstance(value, dict) or set(value) != _KEYS:
        return None
    root = _canonical_existing_directory(value.get("root"))
    common = _canonical_existing_directory(value.get("git_common_dir"))
    if (
        value.get("schema") != SCHEMA
        or not isinstance(value.get("handoff_id"), str)
        or _HANDOFF_ID.fullmatch(value["handoff_id"]) is None
        or type(value.get("generation")) is not int
        or value["generation"] < 1
        or value.get("status") not in _STATUSES
        or root is None
        or common is None
        or root != value.get("root")
        or common != value.get("git_common_dir")
        or not _valid_branch(value.get("branch"))
        or not isinstance(value.get("head"), str)
        or _OBJECT_ID.fullmatch(value["head"]) is None
        or not _valid_timestamp(value.get("timestamp"))
    ):
        return None
    return dict(value)


def read_record() -> dict | None:
    """Return one strict record, or None for absent/unknown metadata."""
    try:
        raw = _read_bytes()
        if raw is None:
            return None
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, HandoffUnavailable):
        return None
    return _validate(value)


def read_state() -> str:
    """Return only the closed state vocabulary; never expose private metadata."""
    try:
        raw = _read_bytes()
    except (OSError, HandoffUnavailable):
        return "unknown"
    if raw is None:
        return "absent"
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return "unknown"
    record = _validate(value)
    return str(record["status"]) if record is not None else "unknown"


def _git(root: str, *args: str) -> str:
    allowed = {
        ("rev-parse", "--abbrev-ref", "HEAD"),
        ("rev-parse", "HEAD"),
        ("rev-parse", "--path-format=absolute", "--git-common-dir"),
    }
    if tuple(args) not in allowed:
        raise ValueError("handoff permits only closed local Git identity probes")
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
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
    result = subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-C", root, *args],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        env=env,
    )
    if result.returncode != 0:
        raise HandoffUnavailable("Git identity is unavailable")
    return result.stdout.strip()


def identity(root: str) -> dict:
    canonical_root = _canonical_existing_directory(root)
    if canonical_root is None:
        raise HandoffUnavailable("handoff root is not one canonical physical directory")
    branch = _git(canonical_root, "rev-parse", "--abbrev-ref", "HEAD")
    head = _git(canonical_root, "rev-parse", "HEAD")
    common = _canonical_existing_directory(
        _git(canonical_root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    )
    if (
        not _valid_branch(branch)
        or _OBJECT_ID.fullmatch(head) is None
        or common is None
    ):
        raise HandoffUnavailable("handoff Git identity is ambiguous")
    return {
        "root": canonical_root,
        "branch": branch,
        "git_common_dir": common,
        "head": head,
    }


def _now() -> str:
    return _datetime.datetime.now(_datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def create_pending(root: str) -> dict:
    """Publish pending intent after deriving the exact target identity."""
    observed = identity(root)
    with _lock(wait_seconds=2.0):
        raw = _read_bytes()
        previous = None
        if raw is not None:
            try:
                previous = _validate(json.loads(raw.decode("utf-8")))
            except (UnicodeError, json.JSONDecodeError):
                previous = None
            if previous is None:
                raise HandoffUnavailable("existing handoff metadata is unknown")
            if previous["status"] == "pending" and all(
                previous[key] == observed[key] for key in observed
            ):
                return previous
        generation = previous["generation"] + 1 if previous is not None else 1
        record = {
            "schema": SCHEMA,
            "handoff_id": os.urandom(16).hex(),
            "generation": generation,
            "status": "pending",
            **observed,
            "timestamp": _now(),
        }
        _atomic_replace(record_path(), record)
        return record


def close_pending(expected: dict) -> bool:
    """Crash-safe CAS pending→closed; never overwrite a newer record."""
    valid_expected = _validate(expected)
    if valid_expected is None or valid_expected["status"] != "pending":
        return False
    try:
        with _lock(wait_seconds=0.0):
            raw = _read_bytes()
            if raw is None:
                return False
            current = _validate(json.loads(raw.decode("utf-8")))
            if current is None or current != valid_expected:
                return False
            closed = dict(current)
            closed["status"] = "closed"
            _atomic_replace(record_path(), closed)
            return True
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        HandoffUnavailable,
    ):
        return False


def _session_root(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    candidates = []
    for key in ("cwd", "workspaceRoot", "workspace_path", "root", "projectRoot"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            candidates.append(value.strip())
        elif value is not None:
            return None
    roots = payload.get("workspace_roots")
    if roots is not None:
        if not isinstance(roots, list):
            return None
        if any(not isinstance(item, str) or not item.strip() for item in roots):
            return None
        candidates.extend(item.strip() for item in roots)
    if not candidates:
        candidates.append(os.getcwd())
    canonical = {_canonical_existing_directory(item) for item in candidates}
    if None in canonical or len(canonical) != 1:
        return None
    return next(iter(canonical))


def consume_session_start(payload: object) -> bool:
    """Close exactly one exact pending intent; every uncertainty preserves it."""
    record = read_record()
    if record is None or record.get("status") != "pending":
        return False
    root = _session_root(payload)
    if root is None or root != record["root"]:
        return False
    try:
        observed = identity(root)
    except (OSError, subprocess.SubprocessError, HandoffUnavailable):
        return False
    if any(record[key] != observed[key] for key in observed):
        return False
    return close_pending(record)


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="verb", required=True)
    create = sub.add_parser("create")
    create.add_argument("--root", required=True)
    sub.add_parser("consume")
    sub.add_parser("state")
    args = parser.parse_args(argv)
    if args.verb == "state":
        print(read_state())
        return 0
    if args.verb == "consume":
        try:
            payload = json.load(sys.stdin)
        except Exception:
            return 0
        consume_session_start(payload)
        return 0
    try:
        record = create_pending(args.root)
    except Exception as exc:
        print(f"handoff intent unavailable: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"generation": record["generation"], "status": "pending"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
