"""Read-only lifecycle classification for AWA leases and Git worktrees.

This module reports candidates only.  It never constructs ``State``, changes a
lease, invokes a lifecycle action, or runs a Git command that can contact a
remote.  PID and boot fields are copied into diagnostics but never participate
in classification.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import sqlite3
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import integrity, paths


SCHEMA = "awa-integrity-lifecycle/v1"
CLASSIFICATIONS = frozenset(
    {"retire_candidate", "adopt_candidate", "preserve", "unknown"}
)
_DISPOSITIONS = frozenset(
    {"active", "stale", "dead", "untracked", "absent"}
)
_OBJECT_ID = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


@dataclass(frozen=True)
class GitRegistration:
    """One locally registered Git worktree and its read-only local scores."""

    path: str
    git_common_dir: str
    linked: bool | None
    dirty: bool | None
    cached_remote: bool | None


@dataclass(frozen=True)
class _Observation:
    """Unreduced local evidence for one lease/worktree path."""

    path: str
    lease: dict | None
    registration: GitRegistration | None
    registration_known: bool
    root_exists: bool | None
    lease_on_disk: bool | None
    disposition: str | None
    live_session: bool | None
    journal_or_recovery_ambiguous: bool | None
    lease_snapshot_known: bool = True
    lease_ambiguous: bool = False
    registration_ambiguous: bool = False


@dataclass(frozen=True)
class Row:
    """A lifecycle report row with four independently scored dimensions."""

    worktree_path: str
    lease_id: str | None
    classification: str
    topology: str
    content_safety: str
    activity: str
    cached_remote: str
    disposition: str
    diagnostics: dict

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class _GitSnapshot:
    registrations: tuple[GitRegistration, ...]
    known_common_dirs: frozenset[str]


def _path_key(value: str) -> str:
    return os.path.realpath(os.path.abspath(os.path.expanduser(value)))


def _common_key(value: str) -> str:
    return _path_key(value) if value else ""


def _read_lease_snapshot() -> tuple[list[dict], bool]:
    """Read active durable leases through the established live-WAL RO path."""
    try:
        conn = integrity._ro_conn()
    except (OSError, sqlite3.Error):
        return [], False
    try:
        rows = conn.execute(
            """
            SELECT lease_id, worktree_path, branch, git_common_dir, boot_id,
                   base_ref, head, status, created_at, updated_at, attested_at, pid
              FROM leases
             WHERE status='active'
             ORDER BY worktree_path, lease_id
            """
        ).fetchall()
        return [dict(row) for row in rows], True
    except sqlite3.Error:
        return [], False
    finally:
        conn.close()


def _git_args_are_local_read_only(args: tuple[str, ...]) -> bool:
    if args in {
        ("worktree", "list", "--porcelain", "-z"),
        ("rev-parse", "--path-format=absolute", "--git-common-dir"),
        ("rev-parse", "HEAD"),
        ("status", "--porcelain=v1", "--untracked-files=all"),
    }:
        return True
    return bool(
        len(args) == 4
        and args[0] == "for-each-ref"
        and args[1].startswith("--contains=")
        and _OBJECT_ID.fullmatch(args[1][len("--contains=") :])
        and args[2] == "--format=%(refname)"
        and args[3] == "refs/remotes"
    )


def _local_git(cwd: str, *args: str) -> subprocess.CompletedProcess:
    """Run only the closed local-read grammar; remote-capable verbs are invalid."""
    normalized = tuple(str(arg) for arg in args)
    if not _git_args_are_local_read_only(normalized):
        raise ValueError("lifecycle reconciliation permits local read-only Git probes only")

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
    return subprocess.run(
        [
            "git",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.untrackedCache=false",
            "-C",
            str(cwd),
            *normalized,
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        env=env,
    )


def _repo_from_common_dir(common_dir: str) -> str | None:
    if not common_dir:
        return None
    common = Path(common_dir).expanduser()
    if common.name == ".git":
        return str(common.parent)
    return None


def _candidate_repositories(leases: list[dict]) -> list[str]:
    candidates = []
    configured = os.environ.get("AWA_INTEGRITY_PROBE_REPO", "").strip()
    if configured:
        candidates.append(configured)
    else:
        source = integrity._source_root()
        if (source / ".git").exists():
            candidates.append(str(source))
    for lease in leases:
        repo = _repo_from_common_dir(str(lease.get("git_common_dir") or ""))
        if repo:
            candidates.append(repo)

    result = []
    seen = set()
    for candidate in candidates:
        key = _path_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        result.append(key)
    return result


def _parse_worktree_porcelain(raw: str) -> list[dict]:
    records = []
    current: dict[str, object] = {}
    for token in raw.split("\0"):
        if not token:
            if current:
                records.append(current)
                current = {}
            continue
        key, separator, value = token.partition(" ")
        if key == "worktree" and "worktree" in current:
            records.append(current)
            current = {}
        current[key] = value if separator else True
    if current:
        records.append(current)
    return [
        record
        for record in records
        if isinstance(record.get("worktree"), str) and record["worktree"]
    ]


def _registration_for(
    record: dict,
    *,
    common_dir: str,
) -> GitRegistration:
    path = _path_key(str(record["worktree"]))
    root_exists = os.path.isdir(path) and not os.path.islink(path)
    dirty: bool | None = None
    cached_remote: bool | None = None
    head = record.get("HEAD")

    if root_exists:
        status = _local_git(
            path,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        )
        dirty = bool(status.stdout) if status.returncode == 0 else None

        if not isinstance(head, str) or not _OBJECT_ID.fullmatch(head):
            head_probe = _local_git(path, "rev-parse", "HEAD")
            head = (
                head_probe.stdout.strip()
                if head_probe.returncode == 0
                else None
            )
        if isinstance(head, str) and _OBJECT_ID.fullmatch(head):
            cached = _local_git(
                path,
                "for-each-ref",
                f"--contains={head}",
                "--format=%(refname)",
                "refs/remotes",
            )
            cached_remote = (
                bool(cached.stdout.strip())
                if cached.returncode == 0
                else None
            )

    common = _common_key(common_dir)
    primary = _repo_from_common_dir(common)
    linked = (
        _path_key(path) != _path_key(primary)
        if primary is not None
        else None
    )
    return GitRegistration(
        path=path,
        git_common_dir=common,
        linked=linked,
        dirty=dirty,
        cached_remote=cached_remote,
    )


def _read_git_snapshot(leases: list[dict]) -> _GitSnapshot:
    registrations = []
    known_common_dirs = set()
    for repo in _candidate_repositories(leases):
        try:
            common_probe = _local_git(
                repo,
                "rev-parse",
                "--path-format=absolute",
                "--git-common-dir",
            )
            worktrees = _local_git(
                repo,
                "worktree",
                "list",
                "--porcelain",
                "-z",
            )
        except (OSError, subprocess.SubprocessError, ValueError):
            continue
        if common_probe.returncode != 0 or worktrees.returncode != 0:
            continue
        common_dir = common_probe.stdout.strip()
        if not common_dir:
            continue
        common_key = _common_key(common_dir)
        if common_key in known_common_dirs:
            continue
        known_common_dirs.add(common_key)
        for record in _parse_worktree_porcelain(worktrees.stdout):
            try:
                registrations.append(
                    _registration_for(record, common_dir=common_key)
                )
            except (OSError, subprocess.SubprocessError, ValueError):
                registrations.append(
                    GitRegistration(
                        path=_path_key(str(record["worktree"])),
                        git_common_dir=common_key,
                        linked=None,
                        dirty=None,
                        cached_remote=None,
                    )
                )
    return _GitSnapshot(
        registrations=tuple(registrations),
        known_common_dirs=frozenset(known_common_dirs),
    )


def _canonical_disposition(path: str) -> dict | None:
    try:
        roots = integrity._roots_module(integrity._source_root())
        result = roots.disposition(path)
    except Exception:  # Canonical evidence unavailable is non-actionable.
        return None
    if (
        not isinstance(result, dict)
        or result.get("disposition") not in _DISPOSITIONS
        or type(result.get("exists")) is not bool
    ):
        return None
    return result


def _lexists(path: Path) -> bool | None:
    try:
        path.lstat()
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return None


def _root_exists(path: str, disposition: dict | None) -> bool | None:
    if disposition is None:
        return None
    canonical = disposition.get("exists")
    lexical = _lexists(Path(path))
    if type(canonical) is not bool or lexical is None:
        return None
    if canonical != lexical:
        return None
    return canonical


def _live_session(disposition: dict | None) -> bool | None:
    if disposition is None:
        return None
    if disposition.get("disposition") == "active":
        return True
    # Absence of a heartbeat record proves there is no recorded live session.
    # If a record exists, PID/boot cannot turn it into retirement authorization.
    return False if disposition.get("record") is None else None


def _bounded_json(path: Path) -> dict | None:
    try:
        metadata = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            return None
        with path.open("rb") as handle:
            raw = handle.read(1_048_577)
        if len(raw) > 1_048_576:
            return None
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _related_path(candidate: object, root: str) -> bool:
    if not isinstance(candidate, str) or not candidate:
        return False
    try:
        candidate_key = _path_key(candidate)
        root_key = _path_key(root)
    except (OSError, RuntimeError, ValueError):
        return False
    return (
        candidate_key == root_key
        or candidate_key.startswith(root_key + os.sep)
        or root_key.startswith(candidate_key + os.sep)
    )


def _directory_entries(directory: Path) -> list[Path] | None:
    try:
        metadata = directory.lstat()
    except FileNotFoundError:
        return []
    except OSError:
        return None
    if directory.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        return None
    try:
        return sorted(directory.iterdir())
    except OSError:
        return None


def _journal_or_recovery_ambiguity(path: str) -> bool | None:
    """Read pending local lifecycle journals; malformed state fails non-actionable."""
    finish = paths.awa_state_dir() / "finish"
    finish_entries = _directory_entries(finish)
    if finish_entries is None:
        return None
    for journal in (
        entry
        for entry in finish_entries
        if entry.name.startswith("removal-") and entry.name.endswith(".json")
    ):
        document = _bounded_json(journal)
        if (
            document is None
            or not isinstance(document.get("root"), str)
            or document.get("phase")
            not in {"prepared", "removed", "finalized"}
        ):
            return True
        if (
            _related_path(document["root"], path)
            and document["phase"] != "finalized"
        ):
            return True

    trash = paths.recovery_dir() / ".trash"
    trash_entries = _directory_entries(trash)
    if trash_entries is None:
        return None
    if any(not entry.name.endswith(".deletion.json") for entry in trash_entries):
        return True
    for journal in trash_entries:
        document = _bounded_json(journal)
        related_fields = (
            document.get("source"),
            document.get("archive"),
            document.get("manifest"),
        ) if document is not None else ()
        if (
            document is None
            or not any(
                isinstance(value, str) and value for value in related_fields
            )
        ):
            return True
        if any(_related_path(value, path) for value in related_fields):
            return True
    return False


def _registrations_by_path(
    registrations: tuple[GitRegistration, ...],
) -> dict[str, list[GitRegistration]]:
    result: dict[str, list[GitRegistration]] = {}
    for registration in registrations:
        result.setdefault(_path_key(registration.path), []).append(registration)
    return result


def _leases_by_path(leases: list[dict]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for lease in leases:
        path = lease.get("worktree_path")
        if not isinstance(path, str) or not path:
            continue
        result.setdefault(_path_key(path), []).append(lease)
    return result


def _observation_for(
    path: str,
    *,
    lease: dict | None,
    lease_snapshot_known: bool,
    lease_ambiguous: bool,
    registrations: list[GitRegistration],
    git_snapshot: _GitSnapshot,
) -> _Observation:
    registration_ambiguous = len(registrations) > 1
    registration = registrations[0] if len(registrations) == 1 else None
    common_dir = str(lease.get("git_common_dir") or "") if lease else ""
    registration_known = bool(
        registrations
        or (
            common_dir
            and _common_key(common_dir) in git_snapshot.known_common_dirs
        )
    )
    disposition_result = _canonical_disposition(path)
    return _Observation(
        path=path,
        lease=lease,
        registration=registration,
        registration_known=registration_known,
        root_exists=_root_exists(path, disposition_result),
        lease_on_disk=_lexists(Path(path) / ".awa" / "lease.json"),
        disposition=(
            str(disposition_result["disposition"])
            if disposition_result is not None
            else None
        ),
        live_session=_live_session(disposition_result),
        journal_or_recovery_ambiguous=_journal_or_recovery_ambiguity(path),
        lease_snapshot_known=lease_snapshot_known,
        lease_ambiguous=lease_ambiguous,
        registration_ambiguous=registration_ambiguous,
    )


def _observations() -> list[_Observation]:
    leases, lease_snapshot_known = _read_lease_snapshot()
    git_snapshot = _read_git_snapshot(leases)
    leases_by_path = _leases_by_path(leases)
    registrations_by_path = _registrations_by_path(
        git_snapshot.registrations
    )
    paths_to_score = sorted(set(leases_by_path) | set(registrations_by_path))
    result = []
    for path in paths_to_score:
        matching_leases = leases_by_path.get(path, [])
        matching_registrations = registrations_by_path.get(path, [])
        if matching_leases:
            for lease in matching_leases:
                result.append(
                    _observation_for(
                        path,
                        lease=lease,
                        lease_snapshot_known=lease_snapshot_known,
                        lease_ambiguous=len(matching_leases) > 1,
                        registrations=matching_registrations,
                        git_snapshot=git_snapshot,
                    )
                )
        else:
            result.append(
                _observation_for(
                    path,
                    lease=None,
                    lease_snapshot_known=lease_snapshot_known,
                    lease_ambiguous=False,
                    registrations=matching_registrations,
                    git_snapshot=git_snapshot,
                )
            )
    return result


def _score_topology(observation: _Observation) -> str:
    if (
        observation.root_exists is None
        or not observation.registration_known
        or observation.registration_ambiguous
    ):
        return "unknown"
    registered = observation.registration is not None
    if observation.root_exists:
        return "present_registered" if registered else "present_unregistered"
    return "absent_registered" if registered else "absent_unregistered"


def _score_content_safety(observation: _Observation) -> str:
    if (
        observation.root_exists is False
        and observation.lease_on_disk is False
    ):
        return "absent"
    if observation.root_exists is True and observation.registration is None:
        return "husk"
    if observation.root_exists is True and observation.registration is not None:
        if observation.registration.dirty is True:
            return "dirty"
        if observation.registration.dirty is False:
            return "clean"
    return "unknown"


def _score_activity(observation: _Observation) -> str:
    if observation.disposition == "active" or observation.live_session is True:
        return "active"
    if (
        observation.disposition in _DISPOSITIONS - {"active"}
        and observation.live_session is False
    ):
        return "inactive"
    return "unknown"


def _score_cached_remote(observation: _Observation) -> str:
    if observation.registration is None:
        return "not_applicable"
    if observation.registration.cached_remote is True:
        return "redundant"
    if observation.registration.cached_remote is False:
        return "local_only"
    return "unknown"


def _classification(
    observation: _Observation,
    *,
    topology: str,
    content_safety: str,
    activity: str,
    cached_remote: str,
) -> str:
    # Positive preservation evidence always wins, independent of other scores.
    if (
        activity == "active"
        or content_safety in {"dirty", "husk"}
        or cached_remote == "local_only"
        or observation.lease_ambiguous
        or observation.registration_ambiguous
        or observation.journal_or_recovery_ambiguous is True
    ):
        return "preserve"

    if observation.lease is not None:
        complete_retire_conjunction = (
            topology == "absent_unregistered"
            and content_safety == "absent"
            and activity == "inactive"
            and observation.disposition != "active"
            and observation.live_session is False
            and observation.lease_on_disk is False
            and observation.journal_or_recovery_ambiguous is False
        )
        if complete_retire_conjunction:
            return "retire_candidate"
        if (
            topology == "unknown"
            or content_safety == "unknown"
            or activity == "unknown"
            or observation.journal_or_recovery_ambiguous is None
        ):
            return "unknown"
        return "preserve"

    if not observation.lease_snapshot_known:
        return "unknown"
    complete_adopt_conjunction = (
        topology == "present_registered"
        and content_safety == "clean"
        and activity == "inactive"
        and cached_remote == "redundant"
        and observation.registration is not None
        and observation.registration.linked is True
        and observation.lease_on_disk is False
        and observation.journal_or_recovery_ambiguous is False
    )
    if complete_adopt_conjunction:
        return "adopt_candidate"
    if (
        topology == "unknown"
        or content_safety == "unknown"
        or activity == "unknown"
        or cached_remote == "unknown"
        or observation.journal_or_recovery_ambiguous is None
    ):
        return "unknown"
    return "preserve"


def _classify_observation(observation: _Observation) -> Row:
    topology = _score_topology(observation)
    content_safety = _score_content_safety(observation)
    activity = _score_activity(observation)
    cached_remote = _score_cached_remote(observation)
    classification = _classification(
        observation,
        topology=topology,
        content_safety=content_safety,
        activity=activity,
        cached_remote=cached_remote,
    )
    if classification not in CLASSIFICATIONS:
        raise RuntimeError("invalid lifecycle classification")
    lease = observation.lease if isinstance(observation.lease, dict) else {}
    registration = observation.registration
    return Row(
        worktree_path=_path_key(observation.path),
        lease_id=(
            str(lease["lease_id"])
            if isinstance(lease.get("lease_id"), str)
            else None
        ),
        classification=classification,
        topology=topology,
        content_safety=content_safety,
        activity=activity,
        cached_remote=cached_remote,
        disposition=observation.disposition or "unknown",
        diagnostics={
            "root_exists": observation.root_exists,
            "git_registered": (
                registration is not None
                if observation.registration_known
                else None
            ),
            "linked": registration.linked if registration else None,
            "lease_on_disk": observation.lease_on_disk,
            "live_session": observation.live_session,
            "journal_or_recovery_ambiguous": (
                observation.journal_or_recovery_ambiguous
            ),
            # Diagnostic only: neither value is read by any score or predicate.
            "pid": lease.get("pid"),
            "boot_id": lease.get("boot_id"),
        },
    )


def classify() -> list[Row]:
    """Return deterministic read-only lifecycle rows; perform no lifecycle action."""
    return sorted(
        (_classify_observation(item) for item in _observations()),
        key=lambda row: (row.worktree_path, row.lease_id or ""),
    )
