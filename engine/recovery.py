"""recovery.py — recovery manager: bundles / patches / quarantine / restore (Phase 3).

Built BEFORE any new destructive cleanup. Two artifact kinds:

  * PATCH  — a git diff (tracked working-tree + staged changes) that round-trips:
             create -> restore reproduces the uncommitted work exactly. This is what
             makes "uncommitted work is preserved" true (§H1 recovery-manager gate).
  * BUNDLE — a tar.gz of git-IGNORED files (`.env`, local `*.db`, build output) that
             `git worktree remove` would otherwise delete with no recovery.
  * WORKTREE-ARCHIVE — a tar.gz of the WHOLE worktree tree (tracked + untracked + ignored,
             minus `.git`) captured as a protected, archive-only safety net. It is written
             read-only (file mode 0o400 — NO OS immutable flag / lock) and `prune_artifacts`
             REFUSES to destroy it, so a later cleanup can never silently discard it.

S1: secret-pattern files are EXCLUDED from a bundle (recorded as skipped) unless the
operator explicitly opts in. S5: the manifest + audit are metadata-only (never file
content). S2: a symlink whose real target escapes the worktree root is never archived.
Recovery archives live on durable LOCAL disk under the state root, never a repo, and
their names never start with a dot (operators list them with a plain `ls`).
"""

from __future__ import annotations

import json
import hashlib
import os
import re
import stat
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from . import gitutil, lock as lock_mod, paths, retention, state as state_mod

# S1 secret denylist (basename patterns), mirroring .gitignore secret classes.
_SECRET = re.compile(
    r"(\.env$|\.env\.|\.(pem|key|p12|pfx|keystore|jks)$|(^|/)(id_rsa|id_ed25519)"
    r"|credential|secret|token|\.netrc$|\.npmrc$)",
    re.I,
)

# Manifest `kind` for the protected whole-worktree archive (D2). `prune_artifacts` treats any
# artifact whose manifest marks `protected: true` as never-deletable.
WORKTREE_ARCHIVE_KIND = "worktree-archive"

QUARANTINE_SCHEMA = "awa-recovery-quarantine/v1"
QUARANTINE_JOURNAL_SCHEMA = "awa-recovery-quarantine-journal/v1"
QUARANTINE_REVERSAL_SCHEMA = "awa-recovery-quarantine-reversal/v1"
QUARANTINE_CRASH_POINTS = (
    "journal_durable",
    "permissions_tightened",
    "renamed",
    "source_dir_synced",
    "destination_dir_synced",
    "post_move_verified",
    "metadata_committed",
    "journal_removed",
)
QUARANTINE_SIDECAR_CRASH_POINTS = (
    "sidecar_phase_durable",
    "sidecar_permissions_tightened",
    "sidecar_renamed",
    "sidecar_source_dir_synced",
    "sidecar_destination_dir_synced",
    "components_phase_durable",
)
QUARANTINE_REVERSAL_SIDECAR_CRASH_POINTS = (
    "reverse_journal_durable",
    "reverse_archive_renamed",
    "reverse_archive_synced",
    "reverse_sidecar_renamed",
    "reverse_sidecar_synced",
    "reverse_metadata_committed",
)


class QuarantineRefused(RuntimeError):
    """The requested quarantine transition did not satisfy its frozen evidence."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class QuarantineInjectedCrash(RuntimeError):
    """Test-only abrupt cut point; production never constructs this exception."""


class QuarantineAppliedIncomplete(RuntimeError):
    """Bytes moved, but durable bookkeeping/finalization did not complete."""

    def __init__(self, message: str, quarantined_path: str):
        super().__init__(message)
        self.applied = True
        self.mutated = True
        self.quarantined_path = quarantined_path


def _quarantine_root(recovery_root: Path) -> Path:
    return recovery_root / "quarantine"


def _absolute_path(path: Path) -> Path:
    return Path(os.path.abspath(os.path.expanduser(str(path))))


def _open_contained_directory(
    directory: Path,
    recovery_root: Path,
    *,
    quarantine_namespace: bool = False,
) -> int:
    """Open and pin one real directory without following its leaf symlink."""
    root = _absolute_path(recovery_root)
    target = _absolute_path(directory)
    fd = -1
    try:
        root_named = root.lstat()
        if stat.S_ISLNK(root_named.st_mode) or not stat.S_ISDIR(root_named.st_mode):
            raise QuarantineRefused("recovery_root_invalid")
        root_real = root.resolve(strict=True)
        target_real = target.resolve(strict=True)
        try:
            relative = target.relative_to(root)
        except ValueError:
            relative = target_real.relative_to(root_real)
            if target != target_real:
                raise QuarantineRefused("quarantine_namespace_alias")
        if quarantine_namespace and (
            not relative.parts or relative.parts[0] != "quarantine"
        ):
            raise QuarantineRefused("quarantine_namespace_escape")
        named = target.lstat()
        if stat.S_ISLNK(named.st_mode) or not stat.S_ISDIR(named.st_mode):
            raise QuarantineRefused("quarantine_namespace_invalid")
        if target_real != root_real / relative:
            raise QuarantineRefused("quarantine_namespace_alias")
        flags = (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        fd = os.open(str(target), flags)
        opened = os.fstat(fd)
        after = target.lstat()
        if (
            not stat.S_ISDIR(opened.st_mode)
            or (opened.st_dev, opened.st_ino)
            != (named.st_dev, named.st_ino)
            or (after.st_dev, after.st_ino)
            != (opened.st_dev, opened.st_ino)
        ):
            raise QuarantineRefused("quarantine_namespace_swap")
        return fd
    except QuarantineRefused:
        if fd >= 0:
            os.close(fd)
        raise
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        if fd >= 0:
            os.close(fd)
        raise QuarantineRefused("quarantine_namespace_invalid") from exc


def _validate_recovery_root(recovery_root: Path) -> None:
    fd = _open_contained_directory(recovery_root, recovery_root)
    os.close(fd)


def _mkdir_private_directory(
    directory: Path,
    recovery_root: Path,
) -> None:
    parent_fd = _open_contained_directory(
        directory.parent,
        recovery_root,
        quarantine_namespace=directory.parent != _absolute_path(recovery_root),
    )
    try:
        os.mkdir(directory.name, paths.DIR_MODE, dir_fd=parent_fd)
        os.fsync(parent_fd)
    except FileExistsError:
        pass
    finally:
        os.close(parent_fd)
    fd = _open_contained_directory(
        directory,
        recovery_root,
        quarantine_namespace=True,
    )
    try:
        os.fchmod(fd, paths.DIR_MODE)
        os.fsync(fd)
    finally:
        os.close(fd)


def _quarantine_dirs(
    recovery_root: Path,
    *,
    create: bool = True,
) -> dict[str, Path]:
    recovery_root = _absolute_path(recovery_root)
    _validate_recovery_root(recovery_root)
    root = _quarantine_root(recovery_root)
    result = {
        "root": root,
        "artifacts": root / "artifacts",
        "metadata": root / "metadata",
        "journals": root / "journals",
        "reversals": root / "reversals",
    }
    # Validate every existing component before creating anything through this namespace.
    for directory in result.values():
        if os.path.lexists(directory):
            fd = _open_contained_directory(
                directory,
                recovery_root,
                quarantine_namespace=True,
            )
            os.close(fd)
    if create:
        for directory in result.values():
            if not os.path.lexists(directory):
                _mkdir_private_directory(directory, recovery_root)
        for directory in result.values():
            fd = _open_contained_directory(
                directory,
                recovery_root,
                quarantine_namespace=True,
            )
            try:
                os.fchmod(fd, paths.DIR_MODE)
            finally:
                os.close(fd)
    return result


def _fsync_dir(
    directory: Path,
    recovery_root: Path | None = None,
    *,
    quarantine_namespace: bool = False,
) -> None:
    fd = (
        _open_contained_directory(
            directory,
            recovery_root,
            quarantine_namespace=quarantine_namespace,
        )
        if recovery_root is not None
        else os.open(
            str(directory),
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
    )
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_all(fd: int, payload: bytes) -> None:
    view = memoryview(payload)
    written = 0
    while written < len(view):
        count = os.write(fd, view[written:])
        if count <= 0:
            raise OSError("short write made no progress")
        written += count


def _atomic_private_write(
    target: Path,
    document: dict,
    recovery_root: Path,
) -> None:
    payload = (
        json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    temporary = target.parent / f".{target.name}.{uuid.uuid4().hex}.tmp"
    parent_fd = _open_contained_directory(
        target.parent,
        recovery_root,
        quarantine_namespace=True,
    )
    try:
        fd = os.open(
            temporary.name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            paths.FILE_MODE,
            dir_fd=parent_fd,
        )
    except BaseException:
        os.close(parent_fd)
        raise
    try:
        _write_all(fd, payload)
        os.fchmod(fd, paths.FILE_MODE)
        os.fsync(fd)
    except BaseException:
        os.close(fd)
        try:
            os.unlink(temporary.name, dir_fd=parent_fd)
        except OSError:
            pass
        os.close(parent_fd)
        raise
    else:
        os.close(fd)
    try:
        check_fd = _open_contained_directory(
            target.parent,
            recovery_root,
            quarantine_namespace=True,
        )
        try:
            if (
                os.fstat(check_fd).st_dev,
                os.fstat(check_fd).st_ino,
            ) != (
                os.fstat(parent_fd).st_dev,
                os.fstat(parent_fd).st_ino,
            ):
                raise QuarantineRefused("quarantine_namespace_swap")
        finally:
            os.close(check_fd)
        os.replace(
            temporary.name,
            target.name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        os.fsync(parent_fd)
    except BaseException:
        try:
            os.unlink(temporary.name, dir_fd=parent_fd)
        except OSError:
            pass
        raise
    finally:
        os.close(parent_fd)


def _durable_unlink(path: Path, recovery_root: Path) -> None:
    parent_fd = _open_contained_directory(
        path.parent,
        recovery_root,
        quarantine_namespace=True,
    )
    try:
        try:
            os.unlink(path.name, dir_fd=parent_fd)
        except FileNotFoundError:
            return
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


def _contained(path: Path, root: Path) -> bool:
    try:
        resolved_root = root.resolve(strict=True)
        resolved = path.resolve(strict=True)
        resolved.relative_to(resolved_root)
    except (FileNotFoundError, OSError, RuntimeError, ValueError):
        return False
    return resolved != resolved_root


def _fingerprint_open(
    path: Path,
    recovery_root: Path,
    *,
    allow_quarantine: bool = False,
) -> tuple[str, dict]:
    """Open without following the leaf, hash through that fd, then re-lstat."""
    try:
        before = path.lstat()
    except OSError as exc:
        raise QuarantineRefused("archive_unavailable") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise QuarantineRefused("archive_not_regular")
    if not _contained(path, recovery_root):
        raise QuarantineRefused("archive_outside_recovery_root")
    if (
        not allow_quarantine
        and retention._is_quarantine_target(path, recovery_root)
    ):
        raise QuarantineRefused("archive_already_quarantined")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(str(path), flags)
    except OSError as exc:
        raise QuarantineRefused("archive_open_refused") from exc
    digest = hashlib.sha256()
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            raise QuarantineRefused("archive_not_regular")
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise QuarantineRefused("archive_identity_drift")
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        after_open = os.fstat(fd)
    finally:
        os.close(fd)
    try:
        after_path = path.lstat()
    except OSError as exc:
        raise QuarantineRefused("archive_path_swap") from exc
    authoritative = (
        opened.st_dev,
        opened.st_ino,
        opened.st_size,
        opened.st_mtime_ns,
    )
    if (
        (
            after_open.st_dev,
            after_open.st_ino,
            after_open.st_size,
            after_open.st_mtime_ns,
        )
        != authoritative
        or (
            after_path.st_dev,
            after_path.st_ino,
            after_path.st_size,
            after_path.st_mtime_ns,
        )
        != authoritative
    ):
        raise QuarantineRefused("archive_evidence_drift")
    return str(path.resolve(strict=True)), {
        "sha256": digest.hexdigest(),
        "size": opened.st_size,
        "mtime_ns": opened.st_mtime_ns,
        "device": opened.st_dev,
        "inode": opened.st_ino,
    }


def _token_for(
    canonical_path: str,
    fingerprint: dict,
    sidecar: dict | None = None,
) -> str:
    evidence = {
        "canonical_path": canonical_path,
        "sha256": fingerprint["sha256"],
        "size": fingerprint["size"],
        "mtime_ns": fingerprint["mtime_ns"],
        "device": fingerprint["device"],
        "inode": fingerprint["inode"],
        "sidecar": sidecar if sidecar is not None else {"present": False},
    }
    return hashlib.sha256(
        json.dumps(
            evidence,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _destination_for(
    canonical_path: str,
    fingerprint: dict,
    recovery_root: Path,
) -> Path:
    basename = _slug(Path(canonical_path).name)
    return (
        _quarantine_root(recovery_root)
        / "artifacts"
        / f"{fingerprint['sha256']}-{basename}"
    )


def _sidecar_path(archive: Path) -> Path | None:
    """Use the existing deterministic recovery writer naming; never manifest content."""
    name = archive.name
    if name.endswith(".tar.gz"):
        return archive.with_name(
            name[: -len(".tar.gz")] + ".manifest.json"
        )
    if name.endswith(".patch"):
        return archive.with_name(name + ".manifest.json")
    return None


def _normalized_path(value: str) -> str | None:
    try:
        path = Path(value).expanduser()
        if not path.is_absolute():
            return None
        return str(path.resolve(strict=False))
    except (OSError, RuntimeError, ValueError):
        return None


def _sidecar_evidence(
    archive_path: Path,
    canonical_archive: str,
    archive_fingerprint: dict,
    recovery_root: Path,
) -> dict:
    candidate = _sidecar_path(archive_path)
    if candidate is None or not os.path.lexists(candidate):
        return {"present": False}
    canonical, fingerprint = _fingerprint_open(candidate, recovery_root)
    document = _read_json(candidate)
    if (
        document is None
        or document.get("schema") != retention.SCHEMA_ARTIFACT
        or document.get("archive_name") != Path(canonical_archive).name
        or _normalized_path(str(document.get("archive") or ""))
        != canonical_archive
        or document.get("sha256") != archive_fingerprint["sha256"]
        or document.get("size") != archive_fingerprint["size"]
    ):
        raise QuarantineRefused("sidecar_pairing_invalid")
    return {
        "present": True,
        "original_path": canonical,
        "quarantined_path": str(
            _destination_for(canonical, fingerprint, recovery_root)
        ),
        "fingerprint": fingerprint,
    }


def _sidecar_preview(sidecar: dict) -> dict:
    if sidecar.get("present") is not True:
        return {"present": False}
    return {
        "present": True,
        "path": sidecar["original_path"],
        "destination": sidecar["quarantined_path"],
        "fingerprint": sidecar["fingerprint"],
    }


def preview_quarantine(
    archive: str,
    *,
    recovery_dir: Path | None = None,
) -> dict:
    """Return deterministic, read-only evidence for one explicitly named archive."""
    recovery_root = (
        Path(recovery_dir) if recovery_dir is not None else paths.recovery_dir()
    )
    recovery_root = _absolute_path(recovery_root)
    _quarantine_dirs(recovery_root, create=False)
    candidate = Path(os.path.abspath(os.path.expanduser(archive)))
    canonical, fingerprint = _fingerprint_open(candidate, recovery_root)
    sidecar = _sidecar_evidence(
        candidate,
        canonical,
        fingerprint,
        recovery_root,
    )
    token = _token_for(canonical, fingerprint, sidecar)
    return {
        "schema": QUARANTINE_SCHEMA,
        "action": "quarantine",
        "outcome": "previewed",
        "mutated": False,
        "applied": False,
        "archive": canonical,
        "destination": str(
            _destination_for(canonical, fingerprint, recovery_root)
        ),
        "fingerprint": fingerprint,
        "sidecar": _sidecar_preview(sidecar),
        "token": token,
    }


def _read_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _read_quarantine_json(
    path: Path,
    recovery_root: Path,
) -> dict | None:
    parent_fd = _open_contained_directory(
        path.parent,
        recovery_root,
        quarantine_namespace=True,
    )
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        try:
            fd = os.open(path.name, flags, dir_fd=parent_fd)
        except OSError:
            return None
        try:
            opened = os.fstat(fd)
            if not stat.S_ISREG(opened.st_mode):
                return None
            payload = bytearray()
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                payload.extend(chunk)
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _operation_token(document: dict) -> str | None:
    source = document.get("original_path")
    fingerprint = document.get("fingerprint")
    sidecar = document.get("sidecar")
    if not isinstance(source, str) or not isinstance(fingerprint, dict):
        return None
    required = {"sha256", "size", "mtime_ns", "device", "inode"}
    if set(fingerprint) != required:
        return None
    try:
        return _token_for(source, fingerprint, sidecar)
    except (KeyError, TypeError):
        return None


def _valid_fingerprint(fingerprint: object) -> bool:
    return bool(
        isinstance(fingerprint, dict)
        and set(fingerprint) == {"sha256", "size", "mtime_ns", "device", "inode"}
        and isinstance(fingerprint.get("sha256"), str)
        and re.fullmatch(r"[0-9a-f]{64}", fingerprint["sha256"]) is not None
        and all(
            type(fingerprint.get(key)) is int and fingerprint[key] >= 0
            for key in ("size", "mtime_ns", "device", "inode")
        )
    )


def _valid_sidecar_document(
    sidecar: object,
    recovery_root: Path,
    archive_original: str,
) -> bool:
    if sidecar == {"present": False}:
        return True
    if not isinstance(sidecar, dict) or sidecar.get("present") is not True:
        return False
    if set(sidecar) != {
        "present",
        "original_path",
        "quarantined_path",
        "fingerprint",
    }:
        return False
    original = sidecar.get("original_path")
    destination = sidecar.get("quarantined_path")
    fingerprint = sidecar.get("fingerprint")
    if (
        not isinstance(original, str)
        or not Path(original).is_absolute()
        or not isinstance(destination, str)
        or not _valid_fingerprint(fingerprint)
    ):
        return False
    try:
        root = recovery_root.resolve(strict=True)
        Path(original).parent.resolve(strict=True).relative_to(root)
        deterministic = _sidecar_path(Path(archive_original))
        if (
            deterministic is None
            or str(deterministic.resolve(strict=False)) != original
        ):
            return False
        observed = Path(destination)
        expected = _destination_for(original, fingerprint, recovery_root)
        return (
            observed == expected
            and observed.parent.resolve(strict=True)
            == (_quarantine_root(recovery_root) / "artifacts").resolve(strict=True)
        )
    except (FileNotFoundError, OSError, RuntimeError, ValueError):
        return False


def _valid_operation_document(
    document: dict,
    recovery_root: Path,
    *,
    committed: bool,
) -> bool:
    expected_schema = QUARANTINE_SCHEMA if committed else QUARANTINE_JOURNAL_SCHEMA
    expected_state = "committed" if committed else "prepared"
    operation_id = document.get("operation_id")
    original = document.get("original_path")
    destination = document.get("quarantined_path")
    fingerprint = document.get("fingerprint")
    sidecar = document.get("sidecar")
    if (
        document.get("schema") != expected_schema
        or document.get("state") != expected_state
        or not isinstance(operation_id, str)
        or re.fullmatch(r"[0-9a-f]{32}", operation_id) is None
        or not isinstance(original, str)
        or not Path(original).is_absolute()
        or not isinstance(destination, str)
        or not _valid_fingerprint(fingerprint)
        or not _valid_sidecar_document(sidecar, recovery_root, original)
    ):
        return False
    try:
        root = recovery_root.resolve(strict=True)
        source_parent = Path(original).parent.resolve(strict=True)
        source_parent.relative_to(root)
        expected_destination = _destination_for(
            original, fingerprint, recovery_root
        )
        observed_destination = Path(destination)
        return (
            observed_destination == expected_destination
            and observed_destination.parent.resolve(strict=True)
            == (_quarantine_root(recovery_root) / "artifacts").resolve(strict=True)
        )
    except (FileNotFoundError, OSError, RuntimeError, ValueError):
        return False


def _find_operation(
    recovery_root: Path,
    original_path: str,
    token: str,
) -> tuple[Path, dict, bool] | None:
    root = _quarantine_root(recovery_root)
    for child, committed in (("metadata", True), ("journals", False)):
        directory = root / child
        if not os.path.lexists(directory):
            continue
        directory_fd = _open_contained_directory(
            directory,
            recovery_root,
            quarantine_namespace=True,
        )
        try:
            names = sorted(
                name
                for name in os.listdir(directory_fd)
                if name.endswith(".json")
            )
            for name in names:
                candidate = directory / name
                document = _read_quarantine_json(
                    candidate, recovery_root
                )
                if (
                    document is not None
                    and _valid_operation_document(
                        document, recovery_root, committed=committed
                    )
                    and document.get("original_path") == original_path
                    and _operation_token(document) == token
                ):
                    return candidate, document, committed
        finally:
            os.close(directory_fd)
    return None


def _verified_component(
    destination_raw: object,
    fingerprint: object,
    recovery_root: Path,
) -> Path:
    if not isinstance(destination_raw, str) or not _valid_fingerprint(fingerprint):
        raise QuarantineRefused("quarantine_record_malformed")
    destination = Path(destination_raw)
    expected_parent = _quarantine_root(recovery_root) / "artifacts"
    try:
        if destination.parent.resolve(strict=True) != expected_parent.resolve(strict=True):
            raise QuarantineRefused("quarantine_destination_escape")
    except (FileNotFoundError, OSError, RuntimeError):
        raise QuarantineRefused("quarantine_destination_unavailable")
    canonical, observed = _fingerprint_open(
        destination,
        recovery_root,
        allow_quarantine=True,
    )
    if canonical != str(destination.resolve(strict=True)) or observed != fingerprint:
        raise QuarantineRefused("quarantine_fingerprint_drift")
    return destination


def _verified_destination(document: dict, recovery_root: Path) -> Path:
    if not _valid_operation_document(document, recovery_root, committed=True):
        raise QuarantineRefused("quarantine_record_malformed")
    destination = _verified_component(
        document.get("quarantined_path"),
        document.get("fingerprint"),
        recovery_root,
    )
    sidecar = document["sidecar"]
    if sidecar.get("present") is True:
        _verified_component(
            sidecar.get("quarantined_path"),
            sidecar.get("fingerprint"),
            recovery_root,
        )
    return destination


def _committed_result(metadata_path: Path, document: dict, *, replay: bool) -> dict:
    result = {
        "schema": QUARANTINE_SCHEMA,
        "action": "quarantine",
        "outcome": "already_quarantined" if replay else "quarantined",
        "mutated": not replay,
        "applied": True,
        "archive": document["original_path"],
        "quarantined_path": document["quarantined_path"],
        "metadata_path": str(metadata_path),
        "fingerprint": document["fingerprint"],
        "sidecar": (
            {
                "present": True,
                "original_path": document["sidecar"]["original_path"],
                "quarantined_path": document["sidecar"]["quarantined_path"],
                "fingerprint": document["sidecar"]["fingerprint"],
            }
            if document["sidecar"].get("present") is True
            else {"present": False}
        ),
    }
    return result


def _commit_quarantine_metadata(
    path: Path,
    document: dict,
    recovery_root: Path,
) -> None:
    if os.path.lexists(path):
        raise QuarantineRefused("metadata_collision")
    _atomic_private_write(path, document, recovery_root)


def _fault(fault, point: str) -> None:
    if fault is not None:
        fault(point)


def _move_verified_source(
    source: Path,
    destination: Path,
    fingerprint: dict,
    recovery_root: Path,
    *,
    fault=None,
    source_quarantine: bool = False,
    destination_quarantine: bool = True,
    permissions_point: str = "permissions_tightened",
    renamed_point: str = "renamed",
) -> None:
    """Re-open/no-follow and keep the verified file descriptor across rename."""
    destination_parent_fd = _open_contained_directory(
        destination.parent,
        recovery_root,
        quarantine_namespace=destination_quarantine,
    )
    try:
        source_parent_fd = _open_contained_directory(
            source.parent,
            recovery_root,
            quarantine_namespace=source_quarantine,
        )
    except BaseException:
        os.close(destination_parent_fd)
        raise
    try:
        try:
            os.stat(
                destination.name,
                dir_fd=destination_parent_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        else:
            raise QuarantineRefused("destination_collision")
    except BaseException:
        os.close(source_parent_fd)
        os.close(destination_parent_fd)
        raise
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(source.name, flags, dir_fd=source_parent_fd)
    except OSError as exc:
        os.close(source_parent_fd)
        os.close(destination_parent_fd)
        raise QuarantineRefused("archive_open_refused") from exc
    try:
        opened = os.fstat(fd)
        identity = {
            "size": opened.st_size,
            "mtime_ns": opened.st_mtime_ns,
            "device": opened.st_dev,
            "inode": opened.st_ino,
        }
        if any(identity[key] != fingerprint[key] for key in identity):
            raise QuarantineRefused("archive_identity_drift")
        digest = hashlib.sha256()
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        if digest.hexdigest() != fingerprint["sha256"]:
            raise QuarantineRefused("archive_content_drift")
        os.fchmod(fd, paths.FILE_MODE)
        _fault(fault, permissions_point)
        named = source.lstat()
        if (named.st_dev, named.st_ino) != (opened.st_dev, opened.st_ino):
            raise QuarantineRefused("archive_path_swap")
        if os.fstat(destination_parent_fd).st_dev != opened.st_dev:
            raise QuarantineRefused("cross_filesystem_destination")
        check_fd = _open_contained_directory(
            destination.parent,
            recovery_root,
            quarantine_namespace=destination_quarantine,
        )
        try:
            if (
                os.fstat(check_fd).st_dev,
                os.fstat(check_fd).st_ino,
            ) != (
                os.fstat(destination_parent_fd).st_dev,
                os.fstat(destination_parent_fd).st_ino,
            ):
                raise QuarantineRefused("quarantine_namespace_swap")
        finally:
            os.close(check_fd)
        try:
            os.stat(
                destination.name,
                dir_fd=destination_parent_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        else:
            raise QuarantineRefused("destination_collision")
        os.rename(
            source.name,
            destination.name,
            src_dir_fd=source_parent_fd,
            dst_dir_fd=destination_parent_fd,
        )
        _fault(fault, renamed_point)
        moved = os.fstat(fd)
        if (moved.st_dev, moved.st_ino) != (opened.st_dev, opened.st_ino):
            raise QuarantineRefused("archive_identity_drift")
    finally:
        os.close(fd)
        os.close(source_parent_fd)
        os.close(destination_parent_fd)


def _write_journal_phase(
    path: Path,
    document: dict,
    phase: str,
    recovery_root: Path,
) -> None:
    document["phase"] = phase
    _atomic_private_write(path, document, recovery_root)


def _component_state(component: dict) -> tuple[Path, Path, bool, bool]:
    source = Path(component["original_path"])
    destination = Path(component["quarantined_path"])
    return (
        source,
        destination,
        os.path.lexists(source),
        os.path.lexists(destination),
    )


def _verify_bound_component(
    component: dict,
    recovery_root: Path,
    *,
    allow_destination: bool,
) -> None:
    source, destination, source_exists, destination_exists = _component_state(
        component
    )
    if source_exists and destination_exists:
        raise QuarantineRefused("destination_collision")
    if source_exists:
        canonical, observed = _fingerprint_open(source, recovery_root)
        if (
            canonical != component["original_path"]
            or observed != component["fingerprint"]
        ):
            raise QuarantineRefused("evidence_drift")
        if destination.parent.stat().st_dev != observed["device"]:
            raise QuarantineRefused("cross_filesystem_destination")
        return
    if allow_destination and destination_exists:
        _verified_component(
            str(destination),
            component["fingerprint"],
            recovery_root,
        )
        return
    raise QuarantineRefused("component_missing")


def apply_quarantine(
    archive: str,
    token: str,
    *,
    recovery_dir: Path | None = None,
    fault=None,
) -> dict:
    """Apply/resume one token-bound quarantine operation, including its sidecar."""
    if not isinstance(token, str) or re.fullmatch(r"[0-9a-f]{64}", token) is None:
        raise QuarantineRefused("token_invalid")
    recovery_root = (
        Path(recovery_dir) if recovery_dir is not None else paths.recovery_dir()
    )
    recovery_root = _absolute_path(recovery_root)
    input_path = Path(os.path.abspath(os.path.expanduser(archive)))
    try:
        original_input = str(input_path.resolve(strict=False))
    except (OSError, RuntimeError):
        original_input = str(input_path)
    moved = False
    destination: Path | None = None
    sidecar: dict | None = None
    try:
        with lock_mod.state_root_lock(blocking=True, timeout=30.0):
            dirs = _quarantine_dirs(recovery_root, create=False)
            existing = _find_operation(recovery_root, original_input, token)
            if existing is not None:
                record_path, document, committed = existing
                if committed and document.get("state") == "committed":
                    if os.path.lexists(original_input):
                        raise QuarantineRefused("original_path_reappeared")
                    sidecar = document["sidecar"]
                    if (
                        sidecar.get("present") is True
                        and os.path.lexists(sidecar["original_path"])
                    ):
                        raise QuarantineRefused("sidecar_path_reappeared")
                    _verified_destination(document, recovery_root)
                    stale_journal = (
                        _quarantine_root(recovery_root)
                        / "journals"
                        / f"{document['operation_id']}.json"
                    )
                    stale = _read_quarantine_json(
                        stale_journal, recovery_root
                    )
                    if (
                        stale is not None
                        and _valid_operation_document(
                            stale, recovery_root, committed=False
                        )
                        and stale.get("operation_id") == document["operation_id"]
                        and _operation_token(stale) == token
                    ):
                        try:
                            _durable_unlink(stale_journal, recovery_root)
                        except (OSError, QuarantineRefused):
                            pass
                    return _committed_result(record_path, document, replay=True)
            else:
                record_path = None
                document = None
                committed = False

            source = Path(original_input)
            if document is None:
                canonical, fingerprint = _fingerprint_open(source, recovery_root)
                if canonical != original_input:
                    original_input = canonical
                    source = Path(canonical)
                sidecar = _sidecar_evidence(
                    source,
                    canonical,
                    fingerprint,
                    recovery_root,
                )
                if _token_for(canonical, fingerprint, sidecar) != token:
                    raise QuarantineRefused("evidence_drift")
                dirs = _quarantine_dirs(recovery_root, create=True)
                destination = _destination_for(canonical, fingerprint, recovery_root)
                operation_id = uuid.uuid4().hex
                journal_path = dirs["journals"] / f"{operation_id}.json"
                document = {
                    "schema": QUARANTINE_JOURNAL_SCHEMA,
                    "operation_id": operation_id,
                    "state": "prepared",
                    "original_path": canonical,
                    "quarantined_path": str(destination),
                    "fingerprint": fingerprint,
                    "sidecar": sidecar,
                    "phase": "prepared",
                }
                archive_component = {
                    "original_path": document["original_path"],
                    "quarantined_path": document["quarantined_path"],
                    "fingerprint": document["fingerprint"],
                }
                _verify_bound_component(
                    archive_component,
                    recovery_root,
                    allow_destination=False,
                )
                if sidecar.get("present") is True:
                    _verify_bound_component(
                        sidecar,
                        recovery_root,
                        allow_destination=False,
                    )
                _atomic_private_write(journal_path, document, recovery_root)
                record_path = journal_path
                _fault(fault, "journal_durable")
            else:
                journal_path = record_path
                destination = Path(str(document["quarantined_path"]))
                dirs = _quarantine_dirs(recovery_root, create=False)

            assert document is not None
            assert destination is not None
            fingerprint = document["fingerprint"]
            sidecar = document["sidecar"]
            if sidecar.get("present") is not True:
                candidate = _sidecar_path(Path(document["original_path"]))
                if candidate is not None and os.path.lexists(candidate):
                    raise QuarantineRefused("sidecar_presence_drift")
            archive_component = {
                "original_path": document["original_path"],
                "quarantined_path": document["quarantined_path"],
                "fingerprint": fingerprint,
            }
            (
                source,
                destination,
                source_exists,
                destination_exists,
            ) = _component_state(archive_component)
            moved = destination_exists and not source_exists
            _verify_bound_component(
                archive_component,
                recovery_root,
                allow_destination=True,
            )
            if sidecar.get("present") is True:
                _verify_bound_component(
                    sidecar,
                    recovery_root,
                    allow_destination=True,
                )

            if sidecar.get("present") is True:
                (
                    sidecar_source,
                    sidecar_destination,
                    sidecar_source_exists,
                    sidecar_destination_exists,
                ) = _component_state(sidecar)
                if sidecar_source_exists:
                    try:
                        _move_verified_source(
                            sidecar_source,
                            sidecar_destination,
                            sidecar["fingerprint"],
                            recovery_root,
                            fault=fault,
                            permissions_point="sidecar_permissions_tightened",
                            renamed_point="sidecar_renamed",
                        )
                    finally:
                        moved = moved or (
                            sidecar_destination.exists()
                            and not sidecar_source.exists()
                        )
                    _fsync_dir(
                        sidecar_source.parent, recovery_root
                    )
                    _fault(fault, "sidecar_source_dir_synced")
                    _fsync_dir(
                        sidecar_destination.parent,
                        recovery_root,
                        quarantine_namespace=True,
                    )
                    _fault(fault, "sidecar_destination_dir_synced")
                elif sidecar_destination_exists:
                    moved = True
                _write_journal_phase(
                    journal_path,
                    document,
                    "sidecar_moved",
                    recovery_root,
                )
                _fault(fault, "sidecar_phase_durable")

            (
                source,
                destination,
                source_exists,
                destination_exists,
            ) = _component_state(archive_component)
            if source_exists:
                try:
                    _move_verified_source(
                        source,
                        destination,
                        fingerprint,
                        recovery_root,
                        fault=fault,
                    )
                finally:
                    moved = moved or (
                        destination.exists() and not source.exists()
                    )
                _fsync_dir(source.parent, recovery_root)
                _fault(fault, "source_dir_synced")
                _fsync_dir(
                    destination.parent,
                    recovery_root,
                    quarantine_namespace=True,
                )
                _fault(fault, "destination_dir_synced")
            _write_journal_phase(
                journal_path,
                document,
                "components_moved",
                recovery_root,
            )
            if sidecar.get("present") is True:
                _fault(fault, "components_phase_durable")

            canonical_destination, observed = _fingerprint_open(
                destination,
                recovery_root,
                allow_quarantine=True,
            )
            if (
                canonical_destination != str(destination.resolve(strict=True))
                or observed != fingerprint
            ):
                raise QuarantineRefused("post_move_verification_failed")
            if sidecar.get("present") is True:
                _verified_component(
                    sidecar["quarantined_path"],
                    sidecar["fingerprint"],
                    recovery_root,
                )
            _fault(fault, "post_move_verified")

            committed_document = {
                "schema": QUARANTINE_SCHEMA,
                "operation_id": document["operation_id"],
                "state": "committed",
                "original_path": document["original_path"],
                "quarantined_path": document["quarantined_path"],
                "fingerprint": fingerprint,
                "sidecar": sidecar,
            }
            metadata_path = (
                dirs["metadata"] / f"{document['operation_id']}.json"
            )
            _commit_quarantine_metadata(
                metadata_path,
                committed_document,
                recovery_root,
            )
            _fault(fault, "metadata_committed")
            _durable_unlink(journal_path, recovery_root)
            _fault(fault, "journal_removed")
            return _committed_result(
                metadata_path, committed_document, replay=False
            )
    except QuarantineInjectedCrash:
        raise
    except QuarantineRefused as exc:
        moved_path = (
            destination
            if destination is not None and destination.exists()
            else (
                Path(sidecar["quarantined_path"])
                if (
                    isinstance(sidecar, dict)
                    and sidecar.get("present") is True
                    and Path(sidecar["quarantined_path"]).exists()
                )
                else None
            )
        )
        if moved and moved_path is not None:
            raise QuarantineAppliedIncomplete(
                f"quarantine bytes moved; bookkeeping incomplete: {exc}",
                str(moved_path),
            ) from exc
        raise
    except Exception as exc:
        moved_path = (
            destination
            if destination is not None and destination.exists()
            else (
                Path(sidecar["quarantined_path"])
                if (
                    isinstance(sidecar, dict)
                    and sidecar.get("present") is True
                    and Path(sidecar["quarantined_path"]).exists()
                )
                else None
            )
        )
        if moved and moved_path is not None:
            raise QuarantineAppliedIncomplete(
                f"quarantine bytes moved; bookkeeping incomplete: {exc}",
                str(moved_path),
            ) from exc
        raise QuarantineRefused("quarantine_apply_failed") from exc


def _reverse_quarantine(
    metadata_path: str | Path,
    *,
    recovery_dir: Path | None = None,
    fault=None,
) -> dict:
    """Internal guarded reversal; intentionally not exposed as a public CLI verb."""
    recovery_root = (
        Path(recovery_dir) if recovery_dir is not None else paths.recovery_dir()
    )
    recovery_root = _absolute_path(recovery_root)
    metadata = Path(metadata_path)
    with lock_mod.state_root_lock(blocking=True, timeout=30.0):
        dirs = _quarantine_dirs(recovery_root, create=False)
        try:
            if (
                metadata.is_symlink()
                or not metadata.is_file()
                or metadata.parent.resolve(strict=True)
                != (
                    _quarantine_root(recovery_root) / "metadata"
                ).resolve(strict=True)
            ):
                raise QuarantineRefused("quarantine_metadata_invalid")
        except (FileNotFoundError, OSError, RuntimeError):
            raise QuarantineRefused("quarantine_metadata_invalid")
        document = _read_quarantine_json(metadata, recovery_root)
        if (
            document is None
            or not _valid_operation_document(
                document, recovery_root, committed=True
            )
        ):
            raise QuarantineRefused("quarantine_metadata_invalid")
        operation_id = document.get("operation_id")
        if not isinstance(operation_id, str) or not operation_id:
            raise QuarantineRefused("quarantine_metadata_invalid")
        reversal_path = dirs["reversals"] / f"{operation_id}.json"
        pending_path = dirs["reversals"] / f"{operation_id}.pending.json"
        reversal = (
            _read_quarantine_json(reversal_path, recovery_root)
            if os.path.lexists(reversal_path)
            else None
        )
        pending = (
            _read_quarantine_json(pending_path, recovery_root)
            if os.path.lexists(pending_path)
            else None
        )
        components = [
            {
                "original_path": document["original_path"],
                "quarantined_path": document["quarantined_path"],
                "fingerprint": document["fingerprint"],
            }
        ]
        if document["sidecar"].get("present") is True:
            components.append(document["sidecar"])

        def component_states() -> list[tuple[Path, Path, bool, bool]]:
            return [_component_state(component) for component in components]

        original = Path(components[0]["original_path"])
        quarantined = Path(components[0]["quarantined_path"])
        all_restored = all(
            source_exists and not destination_exists
            for _, _, source_exists, destination_exists in component_states()
        )
        if (
            isinstance(reversal, dict)
            and reversal.get("schema") == QUARANTINE_REVERSAL_SCHEMA
            and reversal.get("state") == "restored"
            and reversal.get("operation_id") == operation_id
            and reversal.get("sidecar") == document["sidecar"]
            and all_restored
        ):
            if pending is not None:
                _durable_unlink(pending_path, recovery_root)
            return {
                "schema": QUARANTINE_REVERSAL_SCHEMA,
                "outcome": "already_restored",
                "mutated": False,
                "applied": True,
                "restored_path": str(original),
            }
        pending_valid = (
            isinstance(pending, dict)
            and pending.get("schema") == QUARANTINE_REVERSAL_SCHEMA
            and pending.get("operation_id") == operation_id
            and pending.get("state") == "prepared"
            and pending.get("original_path") == str(original)
            and pending.get("quarantined_path") == str(quarantined)
            and pending.get("fingerprint") == document["fingerprint"]
            and pending.get("sidecar") == document["sidecar"]
        )
        if pending is not None and not pending_valid:
            raise QuarantineRefused("reversal_journal_invalid")
        resumed_effect = bool(
            pending_valid
            and any(
                source_exists
                for _, _, source_exists, _ in component_states()
            )
        )
        if not pending_valid:
            if any(source_exists for _, _, source_exists, _ in component_states()):
                raise QuarantineRefused("original_destination_collision")
            for component in components:
                _verified_component(
                    component["quarantined_path"],
                    component["fingerprint"],
                    recovery_root,
                )
            reversal_intent = {
                "schema": QUARANTINE_REVERSAL_SCHEMA,
                "operation_id": operation_id,
                "state": "prepared",
                "phase": "prepared",
                "original_path": str(original),
                "quarantined_path": str(quarantined),
                "fingerprint": document["fingerprint"],
                "sidecar": document["sidecar"],
            }
            if os.path.lexists(pending_path):
                raise QuarantineRefused("reversal_journal_collision")
            _atomic_private_write(
                pending_path, reversal_intent, recovery_root
            )
            pending = reversal_intent
            _fault(fault, "reverse_journal_durable")
        else:
            reversal_intent = pending

        reverse_moved = resumed_effect
        try:
            for index, component in enumerate(components):
                (
                    component_original,
                    component_quarantined,
                    original_exists,
                    quarantined_exists,
                ) = _component_state(component)
                if original_exists and quarantined_exists:
                    raise QuarantineRefused("reverse_destination_collision")
                if not original_exists and not quarantined_exists:
                    raise QuarantineRefused("reverse_component_missing")
                if not original_exists:
                    renamed_point = (
                        "reverse_archive_renamed"
                        if index == 0
                        else "reverse_sidecar_renamed"
                    )
                    try:
                        _move_verified_source(
                            component_quarantined,
                            component_original,
                            component["fingerprint"],
                            recovery_root,
                            fault=fault,
                            source_quarantine=True,
                            destination_quarantine=False,
                            permissions_point=(
                                "reverse_archive_permissions_tightened"
                                if index == 0
                                else "reverse_sidecar_permissions_tightened"
                            ),
                            renamed_point=renamed_point,
                        )
                    finally:
                        reverse_moved = reverse_moved or (
                            component_original.exists()
                            and not component_quarantined.exists()
                        )
                    _fsync_dir(
                        component_quarantined.parent,
                        recovery_root,
                        quarantine_namespace=True,
                    )
                    _fsync_dir(
                        component_original.parent, recovery_root
                    )
                    _fault(
                        fault,
                        "reverse_archive_synced"
                        if index == 0
                        else "reverse_sidecar_synced",
                    )
                    _write_journal_phase(
                        pending_path,
                        reversal_intent,
                        "archive_restored" if index == 0 else "sidecar_restored",
                        recovery_root,
                    )
            for component in components:
                canonical, observed = _fingerprint_open(
                    Path(component["original_path"]), recovery_root
                )
                if (
                    canonical != component["original_path"]
                    or observed != component["fingerprint"]
                ):
                    raise QuarantineRefused("restored_fingerprint_drift")
            reversal = dict(reversal_intent)
            reversal["state"] = "restored"
            reversal["phase"] = "complete"
            if os.path.lexists(reversal_path):
                raise QuarantineAppliedIncomplete(
                    "reverse bytes moved; reversal bookkeeping collision",
                    str(original),
                )
            _atomic_private_write(
                reversal_path, reversal, recovery_root
            )
            _fault(fault, "reverse_metadata_committed")
            _durable_unlink(pending_path, recovery_root)
        except QuarantineInjectedCrash:
            raise
        except QuarantineRefused as exc:
            if not reverse_moved:
                raise
            raise QuarantineAppliedIncomplete(
                f"reverse bytes moved; reversal bookkeeping incomplete: {exc}",
                str(original),
            ) from exc
        except QuarantineAppliedIncomplete:
            raise
        except Exception as exc:
            if not reverse_moved:
                raise QuarantineRefused(
                    "quarantine_reverse_failed"
                ) from exc
            raise QuarantineAppliedIncomplete(
                f"reverse bytes moved; reversal bookkeeping incomplete: {exc}",
                str(original),
            ) from exc
        return {
            "schema": QUARANTINE_REVERSAL_SCHEMA,
            "outcome": "already_restored" if resumed_effect else "restored",
            "mutated": not resumed_effect,
            "applied": True,
            "restored_path": str(original),
        }


def quarantine_count(recovery_dir: Path | None = None) -> int:
    """Count only committed records whose referenced artifact still matches."""
    recovery_root = (
        Path(recovery_dir) if recovery_dir is not None else paths.recovery_dir()
    )
    recovery_root = _absolute_path(recovery_root)
    try:
        dirs = _quarantine_dirs(recovery_root, create=False)
    except QuarantineRefused:
        return 0
    metadata_dir = dirs["metadata"]
    if not os.path.lexists(metadata_dir):
        return 0
    count = 0
    directory_fd = _open_contained_directory(
        metadata_dir,
        recovery_root,
        quarantine_namespace=True,
    )
    try:
        names = sorted(
            name
            for name in os.listdir(directory_fd)
            if name.endswith(".json")
        )
        for name in names:
            metadata = metadata_dir / name
            document = _read_quarantine_json(metadata, recovery_root)
            if (
                document is None
                or document.get("schema") != QUARANTINE_SCHEMA
                or document.get("state") != "committed"
            ):
                continue
            try:
                _verified_destination(document, recovery_root)
            except QuarantineRefused:
                continue
            count += 1
    finally:
        os.close(directory_fd)
    return count


def _prune_on_creation(state: state_mod.State | None, recovery_dir: Path) -> None:
    """The DETERMINISTIC primary retention trigger: every artifact write runs the same bounded
    maintenance pass under the shared state-root lock, so storage self-limits without depending on
    any schedule. Fail-safe: a maintenance hiccup NEVER breaks artifact creation (we just wrote a
    safety artifact — keeping it matters more than pruning)."""
    try:
        retention.run_maintenance(state, recovery_dir=recovery_dir, trigger="create")
    except Exception:  # noqa: BLE001 - creation must succeed regardless of maintenance
        pass


def _slug(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")
    s = re.sub(r"^\.+", "", s)  # never a hidden (leading-dot) archive name.
    return s or "worktree"


def _stamp() -> str:
    return time.strftime("%Y%m%d%H%M%S", time.gmtime())


@dataclass
class BundleResult:
    archive: str
    manifest: str
    included: list[str] = field(default_factory=list)
    skipped_secrets: list[str] = field(default_factory=list)
    skipped_symlink_escape: list[str] = field(default_factory=list)


@dataclass
class ArchiveResult:
    archive: str
    manifest: str
    included: list[str] = field(default_factory=list)
    skipped_secrets: list[str] = field(default_factory=list)
    skipped_symlink_escape: list[str] = field(default_factory=list)
    protected: bool = True


def create_bundle(worktree_path: str, *, allow_secrets: bool = False,
                  recovery_dir: Path | None = None,
                  state: state_mod.State | None = None,
                  lease_id: str | None = None) -> BundleResult:
    """Archive git-ignored files under `worktree_path` (S1/S2/S5-safe)."""
    src = os.path.abspath(worktree_path)
    src_real = os.path.realpath(src)
    rec = Path(recovery_dir) if recovery_dir else paths.recovery_dir()
    paths.ensure_dir(rec)

    entries = gitutil.ignored_files(src)
    included: list[str] = []
    skipped_secrets: list[str] = []
    skipped_symlink: list[str] = []
    for e in entries:
        real = os.path.realpath(os.path.join(src, e))
        if real != src_real and not real.startswith(src_real + os.sep):
            skipped_symlink.append(e)  # S2: escapes the worktree root.
            continue
        if _SECRET.search(e) and not allow_secrets:
            skipped_secrets.append(e)  # S1.
        else:
            included.append(e)

    slug = _slug(os.path.basename(src))
    stamp = _stamp()
    archive = rec / f"{slug}-{stamp}.tar.gz"
    manifest = rec / f"{slug}-{stamp}.manifest.json"

    if included:
        listfile = str(archive) + ".list"
        Path(listfile).write_text("\n".join(included) + "\n", encoding="utf-8")
        try:
            rc = subprocess.run(
                ["tar", "-czf", str(archive), "-C", src, "-T", listfile],
            ).returncode
        finally:
            try:
                os.remove(listfile)
            except OSError:
                pass
        if rc != 0:
            raise RuntimeError(f"tar failed ({rc}) creating {archive}")
    else:
        archive.write_bytes(b"")  # nothing safe to archive; still write the manifest.
    try:
        os.chmod(archive, paths.FILE_MODE)
    except OSError:
        pass

    manifest_doc = retention.build_manifest(
        "bundle", src, archive, protected=False, recovery_root=rec,
        extra={
            "included": included,
            "skipped_secrets": skipped_secrets,
            "skipped_symlink_escape": skipped_symlink,
            "allow_secrets": allow_secrets,
        })
    paths.write_private(manifest, json.dumps(manifest_doc, indent=2) + "\n")

    if state is not None:
        state.record_recovery("bundle", src, str(archive), str(manifest), lease_id,
                              artifact_id=manifest_doc["artifact_id"],
                              sha256=manifest_doc["sha256"], bytes=manifest_doc["size"],
                              protected=False)
        state.record_event("recovery_bundle",
                           f"bundle {archive.name}: {len(included)} incl, "
                           f"{len(skipped_secrets)} secret-skipped", lease_id)
    _prune_on_creation(state, rec)
    return BundleResult(str(archive), str(manifest), included, skipped_secrets, skipped_symlink)


def create_worktree_archive(worktree_path: str, *, allow_secrets: bool = False,
                            recovery_dir: Path | None = None,
                            state: state_mod.State | None = None,
                            lease_id: str | None = None) -> ArchiveResult:
    """Archive the WHOLE worktree tree (tracked + untracked + ignored, minus `.git`) as a
    PROTECTED, archive-only safety net (D2).

    S1/S2/S5-safe, exactly like `create_bundle`: secret-pattern files are excluded (unless
    `allow_secrets`), symlinks whose real target escapes the worktree root are dropped, and the
    manifest is metadata-only. The archive + manifest are then made READ-ONLY (file mode 0o400)
    so the protected copy cannot be edited/truncated in place — deliberately PERMS-ONLY, with NO
    macOS immutable flag / OS lock (a locked K0/K1 non-goal, enforced product-wide by the
    kernel-off matrix). `prune_artifacts` refuses to delete it.
    """
    src = os.path.abspath(worktree_path)
    src_real = os.path.realpath(src)
    rec = Path(recovery_dir) if recovery_dir else paths.recovery_dir()
    paths.ensure_dir(rec)

    included: list[str] = []
    skipped_secrets: list[str] = []
    skipped_symlink: list[str] = []
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d != ".git"]  # never descend git metadata.
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, src)
            if rel == ".git" or rel.startswith(".git" + os.sep):
                continue  # a linked worktree's `.git` is a pointer FILE — skip it.
            real = os.path.realpath(full)
            if real != src_real and not real.startswith(src_real + os.sep):
                skipped_symlink.append(rel)  # S2: escapes the worktree root.
                continue
            if _SECRET.search(rel) and not allow_secrets:
                skipped_secrets.append(rel)  # S1.
            else:
                included.append(rel)
    included.sort()
    skipped_secrets.sort()
    skipped_symlink.sort()

    slug = _slug(os.path.basename(src))
    stamp = _stamp()
    archive = rec / f"{slug}-{stamp}.worktree.tar.gz"
    manifest = rec / f"{slug}-{stamp}.worktree.manifest.json"

    if included:
        listfile = str(archive) + ".list"
        Path(listfile).write_text("\n".join(included) + "\n", encoding="utf-8")
        try:
            rc = subprocess.run(
                ["tar", "-czf", str(archive), "-C", src, "-T", listfile],
            ).returncode
        finally:
            try:
                os.remove(listfile)
            except OSError:
                pass
        if rc != 0:
            raise RuntimeError(f"tar failed ({rc}) creating {archive}")
    else:
        archive.write_bytes(b"")  # nothing safe to archive; still write the manifest.

    manifest_doc = retention.build_manifest(
        WORKTREE_ARCHIVE_KIND, src, archive, protected=True, recovery_root=rec,
        extra={
            "included": included,
            "skipped_secrets": skipped_secrets,
            "skipped_symlink_escape": skipped_symlink,
            "allow_secrets": allow_secrets,
            "hardening": "archive-only (read-only file mode 0o400); no OS immutable flag / lock",
        })
    paths.write_private(manifest, json.dumps(manifest_doc, indent=2) + "\n")
    # Archive-only hardening (perms-only, no OS lock): make the archive + manifest READ-ONLY.
    for p in (archive, manifest):
        try:
            os.chmod(p, 0o400)
        except OSError:
            pass

    if state is not None:
        state.record_recovery(WORKTREE_ARCHIVE_KIND, src, str(archive), str(manifest), lease_id,
                              artifact_id=manifest_doc["artifact_id"],
                              sha256=manifest_doc["sha256"], bytes=manifest_doc["size"],
                              protected=True)
        state.record_event("recovery_worktree_archive",
                           f"protected whole-worktree archive {archive.name}: "
                           f"{len(included)} file(s), {len(skipped_secrets)} secret-skipped",
                           lease_id)
    # Prune-on-creation still self-limits ORDINARY storage; the protected archive is never removed.
    _prune_on_creation(state, rec)
    return ArchiveResult(str(archive), str(manifest), included, skipped_secrets, skipped_symlink, True)


def restore_bundle(archive: str, dest: str) -> list[str]:
    """Extract a bundle into `dest`. Returns the list of restored paths."""
    dest_p = Path(dest)
    dest_p.mkdir(parents=True, exist_ok=True)
    if os.path.getsize(archive) == 0:
        return []
    rc = subprocess.run(["tar", "-xzf", archive, "-C", str(dest_p)]).returncode
    if rc != 0:
        raise RuntimeError(f"tar extract failed ({rc}) for {archive}")
    rc, out, _ = _tar_list(archive)
    return [ln for ln in out.splitlines() if ln.strip()] if rc == 0 else []


def _tar_list(archive: str) -> tuple[int, str, str]:
    proc = subprocess.run(["tar", "-tzf", archive], capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


@dataclass
class PatchResult:
    patch: str
    has_changes: bool
    included_staged: bool


def create_patch(worktree_path: str, *, recovery_dir: Path | None = None,
                 state: state_mod.State | None = None,
                 lease_id: str | None = None) -> PatchResult:
    """Capture uncommitted tracked changes (working tree + staged) as a git patch.

    Round-trips with `restore_patch`. Uses `git diff HEAD --binary` so staged AND
    unstaged changes to tracked files are captured in one applyable patch.
    """
    src = os.path.abspath(worktree_path)
    rec = Path(recovery_dir) if recovery_dir else paths.recovery_dir()
    paths.ensure_dir(rec)
    slug = _slug(os.path.basename(src))
    stamp = _stamp()
    patch = rec / f"{slug}-{stamp}.patch"

    rc, out, err = gitutil.git(src, "diff", "HEAD", "--binary", timeout=60)
    if rc != 0:
        raise RuntimeError(f"git diff failed: {err.strip()}")
    paths.write_private(patch, out)
    has_changes = bool(out.strip())
    # were there staged changes? (informational)
    rc2, staged, _ = gitutil.git(src, "diff", "--cached", "--name-only", timeout=30)
    included_staged = rc2 == 0 and bool(staged.strip())

    # Sidecar manifest so a patch participates in the ONE unified artifact format (collision-
    # resistant id, size, SHA-256, source attribution, creation time) — the age clock can then
    # start from the patch source's deletion, same as a bundle.
    manifest = rec / f"{patch.name}.manifest.json"
    manifest_doc = retention.build_manifest(
        "patch", src, patch, protected=False, recovery_root=rec,
        extra={"has_changes": has_changes, "included_staged": included_staged})
    paths.write_private(manifest, json.dumps(manifest_doc, indent=2) + "\n")

    if state is not None:
        state.record_recovery("patch", src, str(patch), str(manifest), lease_id,
                              artifact_id=manifest_doc["artifact_id"],
                              sha256=manifest_doc["sha256"], bytes=manifest_doc["size"],
                              protected=False)
        state.record_event("recovery_patch",
                           f"patch {patch.name} ({'changes' if has_changes else 'empty'})",
                           lease_id)
    _prune_on_creation(state, rec)
    return PatchResult(str(patch), has_changes, included_staged)


def restore_patch(patch: str, dest_worktree: str, *, index: bool = False) -> None:
    """Apply a patch created by `create_patch` back into `dest_worktree`.

    `index=True` also stages the changes (git apply --index). Raises on conflict.
    """
    if os.path.getsize(patch) == 0:
        return  # empty patch: nothing to restore.
    args = ["apply", "--whitespace=nowarn"]
    if index:
        args.append("--index")
    args.append(patch)
    rc, _, err = gitutil.git(dest_worktree, *args, timeout=60)
    if rc != 0:
        raise RuntimeError(f"git apply failed: {err.strip()}")


def list_artifacts(recovery_dir: Path | None = None) -> list[dict]:
    """Enumerate recovery artifacts on disk (manifests + any legacy bare patches).

    A patch now carries a sidecar `<name>.patch.manifest.json`, so the bare `.patch` is only
    synthesized when it has NO manifest (a legacy patch), avoiding a double entry.
    """
    rec = Path(recovery_dir) if recovery_dir else paths.recovery_dir()
    if not rec.exists():
        return []
    out: list[dict] = []
    referenced: set[str] = set()
    manifest_names = {p.name for p in rec.iterdir()
                      if p.is_file() and p.name.endswith(".manifest.json")}
    for p in sorted(rec.iterdir()):
        if p.name.startswith("."):
            continue  # skip the internal .trash journal area
        if p.name.endswith(".manifest.json"):
            try:
                doc = json.loads(p.read_text(encoding="utf-8"))
                out.append(doc)
                if doc.get("archive"):
                    referenced.add(os.path.basename(str(doc["archive"])))
                if doc.get("archive_name"):
                    referenced.add(str(doc["archive_name"]))
            except (OSError, json.JSONDecodeError):
                pass
    for p in sorted(rec.iterdir()):
        if (p.is_file() and p.suffix == ".patch"
                and (p.name + ".manifest.json") not in manifest_names
                and p.name not in referenced):
            out.append({"kind": "patch", "archive": str(p), "size": p.stat().st_size})
    return out


def prune_artifacts(recovery_dir: Path | None = None, *,
                    older_than_seconds: float | None = None,
                    force: bool = False) -> dict:
    """Cleanup pass over recovery artifacts that REFUSES to destroy a protected archive (D2).

    A protected whole-worktree archive (manifest ``protected: true``) is NEVER deleted — not
    even with ``force`` — so a later cleanup cannot silently discard the safety net. Other
    (non-protected) artifacts are eligible only when explicitly requested: ``force`` deletes
    them, or ``older_than_seconds`` deletes those whose manifest/patch mtime is at least that
    old. With neither, nothing is deleted (the pass just reports what it would keep/refuse).

    Returns ``{"deleted": [...], "refused_protected": [...], "kept": [...]}`` (archive paths).
    """
    rec = Path(recovery_dir) if recovery_dir else paths.recovery_dir()
    result: dict[str, list[str]] = {"deleted": [], "refused_protected": [], "kept": []}
    if not rec.exists():
        return result
    now = time.time()

    def _eligible(p: Path) -> bool:
        if force:
            return True
        if older_than_seconds is None:
            return False
        try:
            return (now - p.stat().st_mtime) >= older_than_seconds
        except OSError:
            return False

    def _rm(p: Path) -> None:
        try:
            os.chmod(p, 0o600)  # loosen only what we are deleting (bundles are already 0o600).
        except OSError:
            pass
        try:
            p.unlink()
        except OSError:
            pass

    for p in sorted(rec.iterdir()):
        if p.name.endswith(".manifest.json"):
            try:
                doc = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                doc = {}
            label = doc.get("archive") or str(p)
            if doc.get("protected"):
                result["refused_protected"].append(label)  # cleanup MUST refuse to destroy it.
                continue
            if _eligible(p):
                archive = doc.get("archive")
                if archive and Path(archive).exists():
                    _rm(Path(archive))
                _rm(p)
                result["deleted"].append(label)
            else:
                result["kept"].append(label)
        elif p.suffix == ".patch":
            if _eligible(p):
                _rm(p)
                result["deleted"].append(str(p))
            else:
                result["kept"].append(str(p))
        # A `.tar.gz` is reached via its manifest; a protected archive is thus never unlinked here.
    return result
