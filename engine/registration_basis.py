"""Read-only single-root Git/policy/lifecycle basis collection for Body B."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import time
from pathlib import Path

from . import (
    native_entry,
    registration_admission,
    registration_runtime,
    registration_store,
)


def _hash(domain: str, value: dict) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    return hashlib.sha256(
        domain.encode("ascii") + b"\0" + encoded
    ).hexdigest()


def _canonical_directory(path: Path) -> Path:
    if (
        not path.is_absolute()
        or os.path.normpath(str(path)) != str(path)
        or os.path.realpath(path) != str(path)
    ):
        raise registration_admission.BasisUnavailable("ROOT_UNSUPPORTED")
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise registration_admission.BasisUnavailable(
            "ROOT_UNSUPPORTED"
        ) from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise registration_admission.BasisUnavailable("ROOT_UNSUPPORTED")
    return path


class GitBasisCollector:
    def __init__(
        self,
        *,
        proof_parent: Path,
        projection_parent: Path,
        legacy_parent: Path,
        deadline_seconds: float = 5.0,
    ) -> None:
        self.proof_parent = Path(proof_parent)
        self.projection_parent = Path(projection_parent)
        self.legacy_parent = Path(legacy_parent)
        self.deadline_seconds = deadline_seconds

    def collect(
        self, event: registration_admission.RegistrationEvent
    ) -> registration_admission.BasisSample:
        return self.collect_observation(event).basis_sample

    def collect_observation(
        self, event: registration_admission.RegistrationEvent
    ) -> registration_runtime.BasisObservation:
        root = _canonical_directory(Path(event.root))
        deadline = time.monotonic() + self.deadline_seconds
        try:
            identity_value = native_entry._observe_identity(  # noqa: SLF001
                str(root), deadline=deadline
            )
        except native_entry.EntryUnavailable as exc:
            raise registration_admission.BasisUnavailable(
                _reason(exc.reason)
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise registration_admission.BasisUnavailable(
                "BASIS_TIMEOUT"
            ) from exc
        except Exception as exc:
            raise registration_admission.BasisUnavailable(
                "ROOT_UNSUPPORTED"
            ) from exc
        request_kind = "CLEAN_ELIGIBLE"
        blocked_reason = ""
        try:
            native_entry._validated_registration_identity(  # noqa: SLF001
                str(root),
                deadline=deadline,
                policy_reason="root_not_eligible",
                policy_result="failed",
            )
        except native_entry.EntryUnavailable as exc:
            if exc.reason in {
                "worktree_dirty",
                "worktree_ignored_state",
                "index_hidden_state",
            }:
                request_kind = "BLOCKED_DIRTY"
                blocked_reason = exc.reason
            elif exc.reason in {
                "git_operation_active",
                "git_operation_unknown",
            }:
                request_kind = "BLOCKED_OPERATION"
                blocked_reason = exc.reason
            else:
                raise registration_admission.BasisUnavailable(
                    _reason(exc.reason)
                ) from exc
        except subprocess.TimeoutExpired as exc:
            raise registration_admission.BasisUnavailable(
                "BASIS_TIMEOUT"
            ) from exc
        if request_kind != "CLEAN_ELIGIBLE":
            self._require_policy(identity_value, deadline)

        targets = {
            "root": root,
            "git_dir": _canonical_directory(Path(identity_value.git_dir)),
            "git_common": _canonical_directory(
                Path(identity_value.git_common_dir)
            ),
            "proof": _canonical_directory(self.proof_parent),
            "projection": _canonical_directory(self.projection_parent),
            "legacy": _canonical_directory(self.legacy_parent),
        }
        metadata = {name: path.stat() for name, path in targets.items()}
        devices = {int(value.st_dev) for value in metadata.values()}
        if len(devices) != 1:
            raise registration_admission.BasisUnavailable("DEVICE_MISMATCH")
        physical = _hash(
            "awa-registration-physical-basis/v1",
            {
                name: {
                    "dev": str(value.st_dev),
                    "ino": str(value.st_ino),
                }
                for name, value in metadata.items()
            },
        )
        git_basis = _hash(
            "awa-registration-git-basis/v1",
            {
                "branch": identity_value.branch,
                "head": identity_value.head,
                "git_dir_dev": str(metadata["git_dir"].st_dev),
                "git_dir_ino": str(metadata["git_dir"].st_ino),
                "git_common_dev": str(metadata["git_common"].st_dev),
                "git_common_ino": str(metadata["git_common"].st_ino),
            },
        )
        policy_basis = _hash(
            "awa-registration-policy-basis/v1",
            {"eligible": "true"},
        )
        operation_basis = _hash(
            "awa-registration-operation-basis/v1",
            {
                "request_kind": request_kind,
                "reason": blocked_reason or "clean_idle",
            },
        )
        lifecycle_state = native_entry.inspect_lease_state(str(root))
        lifecycle_basis = _hash(
            "awa-registration-lifecycle-basis/v1",
            {
                "target_state": (
                    "valid"
                    if request_kind == "CLEAN_ELIGIBLE"
                    else lifecycle_state
                )
            },
        )
        current_basis = _hash(
            "awa-registration-current-basis/v1",
            {
                "physical": physical,
                "git": git_basis,
                "policy": policy_basis,
                "operation": operation_basis,
                "lifecycle": lifecycle_basis,
            },
        )
        root_meta = metadata["root"]
        git_meta = metadata["git_dir"]
        common_meta = metadata["git_common"]
        identity = registration_store.MemberIdentity(
            canonical_root=str(root),
            root_dev=int(root_meta.st_dev),
            root_ino=int(root_meta.st_ino),
            git_toplevel=str(root),
            git_dir=str(targets["git_dir"]),
            git_dir_dev=int(git_meta.st_dev),
            git_dir_ino=int(git_meta.st_ino),
            git_common_dir=str(targets["git_common"]),
            git_common_dev=int(common_meta.st_dev),
            git_common_ino=int(common_meta.st_ino),
            proof_dev=int(metadata["proof"].st_dev),
            projection_dev=int(metadata["projection"].st_dev),
            legacy_state_dev=int(metadata["legacy"].st_dev),
            physical_basis_hash=physical,
            git_basis_hash=git_basis,
            policy_basis_hash=policy_basis,
            operation_basis_hash=operation_basis,
            lifecycle_basis_hash=lifecycle_basis,
            current_basis_hash=current_basis,
        )
        workspace_hash = _hash(
            "awa-registration-workspace-roots/v1",
            {"count": "1", "root_hash": hashlib.sha256(str(root).encode()).hexdigest()},
        )
        fingerprint = (
            None
            if request_kind == "CLEAN_ELIGIBLE"
            else _hash(
                "awa-registration-blocked-fingerprint/v1",
                {
                    "request_kind": request_kind,
                    "operation_basis_hash": operation_basis,
                },
            )
        )
        return registration_runtime.BasisObservation.from_identity(
            identity,
            request_kind=request_kind,
            workspace_roots_hash=workspace_hash,
            blocked_basis_fingerprint=fingerprint,
        )

    def _require_policy(self, identity_value, deadline: float) -> None:
        try:
            config = native_entry._git(  # noqa: SLF001
                identity_value.root,
                "config",
                "--get-regexp",
                r"^(remote\.origin\.url|core\.hookspath)$",
                deadline=deadline,
            )
        except subprocess.TimeoutExpired as exc:
            raise registration_admission.BasisUnavailable(
                "BASIS_TIMEOUT"
            ) from exc
        if config.returncode not in {0, 1}:
            raise registration_admission.BasisUnavailable("ROOT_UNSUPPORTED")
        origin = False
        hooks = []
        for line in config.stdout.splitlines():
            key, separator, value = line.partition(" ")
            if not separator:
                raise registration_admission.BasisUnavailable(
                    "ROOT_UNSUPPORTED"
                )
            if key == "remote.origin.url":
                origin = True
            elif key == "core.hookspath":
                hooks.append(value)
        if len(set(hooks)) > 1 or not native_entry._policy_decision(  # noqa: SLF001
            identity_value,
            has_origin=origin,
            hooks_path=hooks[0] if hooks else "",
        ):
            raise registration_admission.BasisUnavailable("ROOT_UNSUPPORTED")


def _reason(reason: str) -> str:
    return {
        "worktree_dirty": "DIRTY_UNSUPPORTED",
        "git_operation_active": "GIT_OPERATION_UNSUPPORTED",
        "git_operation_unknown": "GIT_OPERATION_UNSUPPORTED",
        "policy_unavailable": "ROOT_UNSUPPORTED",
        "root_not_eligible": "ROOT_UNSUPPORTED",
        "git_identity_unavailable": "BASIS_TIMEOUT",
    }.get(reason, "ROOT_UNSUPPORTED")
