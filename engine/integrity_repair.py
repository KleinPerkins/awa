"""Digest-bound, explicitly row-authorized AWA integrity repairs.

The closed action set is deliberately small.  Planning is pure/read-only.
Retirement changes SQLite bookkeeping only under the lease row's stored
git-common-dir lock.  Worktree removal delegates to the existing kernel clean
path after a protected whole-worktree capture; it never acquires an outer lock.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import os
import sqlite3
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import (
    lifecycle_reconcile,
    lock,
    paths,
    recovery,
    retention,
    state as state_mod,
)


PLAN_SCHEMA = "awa-integrity-repair-plan/v1"
ACTION_SCHEMA = "awa-integrity-repair-action/v1"
AUTHORIZATION_SCHEMA = "awa-integrity-repair-authorization/v1"
ACTION_KINDS = frozenset({"retire-bookkeeping", "remove-worktree"})
_LEASE_FIELDS = (
    "lease_id",
    "worktree_path",
    "branch",
    "git_common_dir",
    "boot_id",
    "base_ref",
    "head",
    "status",
    "created_at",
    "updated_at",
    "attested_at",
    "pid",
)


class RepairRefused(RuntimeError):
    """Live evidence or explicit authorization did not permit the repair."""


class RepairAppliedPlanUnavailable(RuntimeError):
    """The repair committed, but its mandatory post-success plan could not render."""

    def __init__(self, applied_result: dict):
        super().__init__("repair applied but fresh post-success plan is unavailable")
        self.applied_result = applied_result


@dataclass(frozen=True)
class Capture:
    archive: str
    manifest: str
    protected: bool
    skipped_secrets: tuple[str, ...]
    skipped_symlink_escape: tuple[str, ...]


@dataclass(frozen=True)
class CleanResult:
    returncode: int
    stdout: str
    stderr: str
    receipt: dict | None


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _authorization_for(plan_digest: str, action: dict) -> str:
    return _digest(
        {
            "schema": AUTHORIZATION_SCHEMA,
            "plan_digest": plan_digest,
            "action": action,
        }
    )


def _safe_git(path: str, *args: str) -> subprocess.CompletedProcess:
    allowed = {
        ("rev-parse", "--abbrev-ref", "HEAD"),
        ("rev-parse", "HEAD"),
        ("rev-parse", "--path-format=absolute", "--git-common-dir"),
    }
    normalized = tuple(args)
    if normalized not in allowed:
        raise ValueError("integrity repair permits only closed local Git identity probes")
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
            path,
            *normalized,
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        env=env,
    )


def _live_git_identity(
    observation: lifecycle_reconcile._Observation,
) -> dict:
    registration = observation.registration
    if registration is None:
        return {
            "branch": None,
            "git_common_dir": None,
            "head": None,
        }
    try:
        probes = (
            _safe_git(observation.path, "rev-parse", "--abbrev-ref", "HEAD"),
            _safe_git(observation.path, "rev-parse", "HEAD"),
            _safe_git(
                observation.path,
                "rev-parse",
                "--path-format=absolute",
                "--git-common-dir",
            ),
        )
    except (OSError, subprocess.SubprocessError):
        return {
            "branch": None,
            "git_common_dir": None,
            "head": None,
        }
    if any(probe.returncode != 0 for probe in probes):
        return {
            "branch": None,
            "git_common_dir": None,
            "head": None,
        }
    branch, head, common_dir = (probe.stdout.strip() for probe in probes)
    if (
        not branch
        or branch == "HEAD"
        or lifecycle_reconcile._OBJECT_ID.fullmatch(head) is None
        or not common_dir
        or lifecycle_reconcile._common_key(common_dir)
        != lifecycle_reconcile._common_key(registration.git_common_dir)
    ):
        return {
            "branch": None,
            "git_common_dir": None,
            "head": None,
        }
    return {
        "branch": branch,
        "git_common_dir": lifecycle_reconcile._common_key(common_dir),
        "head": head,
    }


def _stored_row(lease: dict | None) -> dict | None:
    if lease is None:
        return None
    if set(lease) != set(_LEASE_FIELDS):
        return None
    return {field: lease[field] for field in _LEASE_FIELDS}


def _action_for_observation(
    observation: lifecycle_reconcile._Observation,
) -> dict | None:
    row = lifecycle_reconcile._classify_observation(observation)
    if row.classification == "retire_candidate":
        kind = "retire-bookkeeping"
    elif row.classification == "adopt_candidate":
        kind = "remove-worktree"
    else:
        return None

    stored = _stored_row(observation.lease)
    if kind == "retire-bookkeeping" and (
        stored is None
        or stored["status"] != "active"
        or stored["lease_id"] != row.lease_id
    ):
        return None
    if kind == "remove-worktree" and stored is not None:
        return None

    live_git = _live_git_identity(observation)
    if kind == "remove-worktree" and any(
        not live_git[key] for key in ("branch", "git_common_dir", "head")
    ):
        return None

    action = {
        "schema": ACTION_SCHEMA,
        "kind": kind,
        "target": lifecycle_reconcile._path_key(row.worktree_path),
        "lease_id": row.lease_id,
        "stored_row": stored,
        "classification": {
            "classification": row.classification,
            "topology": row.topology,
            "content_safety": row.content_safety,
            "activity": row.activity,
            "cached_remote": row.cached_remote,
        },
        "evidence": {
            "path_exists": row.diagnostics["root_exists"],
            "git_registered": row.diagnostics["git_registered"],
            "lease_on_disk": row.diagnostics["lease_on_disk"],
            "live_session": row.diagnostics["live_session"],
            "journal_or_recovery_ambiguous": row.diagnostics[
                "journal_or_recovery_ambiguous"
            ],
            "disposition": row.disposition,
        },
        "live_git": live_git,
    }
    action["action_id"] = _digest(action)
    return action


def _plan_from_actions(actions: list[dict]) -> dict:
    canonical_actions = sorted(
        (json.loads(_json_bytes(action)) for action in actions),
        key=lambda action: (
            action.get("kind", ""),
            action.get("target", ""),
            action.get("lease_id") or "",
            action.get("action_id", ""),
        ),
    )
    core = {"schema": PLAN_SCHEMA, "actions": canonical_actions}
    plan_digest = _digest(core)
    displayed = []
    for action in canonical_actions:
        rendered = dict(action)
        rendered["authorization"] = _authorization_for(plan_digest, action)
        displayed.append(rendered)
    return {
        "schema": PLAN_SCHEMA,
        "plan_digest": plan_digest,
        "actions": displayed,
    }


def build_plan() -> dict:
    """Build a deterministic read-only plan from the canonical lifecycle snapshot."""
    actions = []
    for observation in lifecycle_reconcile._observations():
        action = _action_for_observation(observation)
        if action is not None:
            actions.append(action)
    return _plan_from_actions(actions)


def _select_action(
    plan: dict,
    *,
    kind: str,
    authorization: str,
) -> dict:
    if kind not in ACTION_KINDS:
        raise RepairRefused("unknown integrity repair action")
    if not isinstance(authorization, str) or not authorization:
        raise RepairRefused("explicit row authorization is required")
    matches = [
        action
        for action in plan.get("actions", [])
        if action.get("kind") == kind
        and isinstance(action.get("authorization"), str)
        and hmac.compare_digest(action["authorization"], authorization)
    ]
    if len(matches) != 1:
        raise RepairRefused("authorization does not select exactly one planned row")
    return matches[0]


def _fresh_action(plan_digest: str, kind: str, authorization: str) -> dict:
    plan = build_plan()
    observed_digest = plan.get("plan_digest")
    if (
        not isinstance(observed_digest, str)
        or not hmac.compare_digest(observed_digest, plan_digest)
    ):
        raise RepairRefused("integrity repair evidence changed; create a fresh plan")
    return _select_action(plan, kind=kind, authorization=authorization)


def _write_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(
        str(paths.state_db_path()),
        timeout=30.0,
        isolation_level=None,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=30000")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _fault(fault: Callable[[str], None] | None, point: str) -> None:
    if fault is not None:
        fault(point)


def _apply_retire_bookkeeping(
    action: dict,
    *,
    plan_digest: str,
    authorization: str,
    fault: Callable[[str], None] | None,
) -> dict:
    stored = action.get("stored_row")
    if not isinstance(stored, dict):
        raise RepairRefused("planned lease row is incomplete")
    common_dir = stored.get("git_common_dir")
    lease_id = stored.get("lease_id")
    if not isinstance(common_dir, str) or not common_dir or not isinstance(lease_id, str):
        raise RepairRefused("planned lease identity is incomplete")

    with lock.common_dir_lock(common_dir):
        connection = _write_connection()
        committed = False
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT lease_id, worktree_path, branch, git_common_dir, boot_id,
                       base_ref, head, status, created_at, updated_at, attested_at, pid
                  FROM leases
                 WHERE lease_id=?
                """,
                (lease_id,),
            ).fetchone()
            if row is None or dict(row) != stored:
                raise RepairRefused("stored lease row changed; create a fresh plan")
            # Re-read every filesystem/session/Git classification input while
            # holding both the stored common-dir lock and the SQLite write
            # transaction, immediately before the status transition.
            fresh = _fresh_action(
                plan_digest,
                "retire-bookkeeping",
                authorization,
            )
            if fresh.get("action_id") != action.get("action_id"):
                raise RepairRefused("integrity repair row changed; create a fresh plan")
            now = state_mod.now_iso()
            updated = connection.execute(
                """
                UPDATE leases
                   SET status='retired', updated_at=?
                 WHERE lease_id=? AND status='active'
                """,
                (now, lease_id),
            )
            if updated.rowcount != 1:
                raise RepairRefused("lease is no longer active")
            _fault(fault, "retire-after-update")
            detail = {
                "schema": "awa-integrity-repair-audit/v1",
                "action_id": action["action_id"],
                "plan_digest": plan_digest,
                "authorization_sha256": hashlib.sha256(
                    authorization.encode("utf-8")
                ).hexdigest(),
                "rollback": {
                    "prior_status": "active",
                    "stored_row_sha256": _digest(stored),
                },
            }
            connection.execute(
                "INSERT INTO events(ts,lease_id,kind,detail) VALUES(?,?,?,?)",
                (
                    now,
                    lease_id,
                    "integrity_repair_retire_bookkeeping",
                    json.dumps(
                        detail,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                ),
            )
            _fault(fault, "retire-after-audit")
            connection.execute("COMMIT")
            committed = True
        finally:
            if not committed:
                with contextlib.suppress(sqlite3.Error):
                    connection.execute("ROLLBACK")
            connection.close()

    return {
        "schema": "awa-integrity-repair-result/v1",
        "kind": "retire-bookkeeping",
        "action_id": action["action_id"],
        "result": "retired",
        "fresh_plan_required": True,
    }


def _default_capture(path: str, *, lease_id: str | None = None) -> Capture:
    with state_mod.State(assert_local=False) as state:
        result = recovery.create_worktree_archive(
            path,
            allow_secrets=False,
            state=state,
            lease_id=lease_id,
        )
    return Capture(
        archive=result.archive,
        manifest=result.manifest,
        protected=result.protected,
        skipped_secrets=tuple(result.skipped_secrets),
        skipped_symlink_escape=tuple(result.skipped_symlink_escape),
    )


def _regular_file(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    return not path.is_symlink() and stat.S_ISREG(metadata.st_mode)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validated_capture(capture: Capture, target: str) -> dict:
    if (
        not isinstance(capture, Capture)
        or capture.protected is not True
        or capture.skipped_secrets
        or capture.skipped_symlink_escape
    ):
        raise RepairRefused("protected recovery capture was incomplete")
    archive = Path(capture.archive)
    manifest = Path(capture.manifest)
    if not _regular_file(archive) or not _regular_file(manifest):
        raise RepairRefused("protected recovery capture is unavailable")
    try:
        recovery_root = paths.recovery_dir().resolve()
        if (
            archive.resolve().parent != recovery_root
            or manifest.resolve().parent != recovery_root
        ):
            raise RepairRefused("protected recovery capture escaped its private root")
        raw = manifest.read_bytes()
        if len(raw) > 1_048_576:
            raise RepairRefused("protected recovery manifest is oversized")
        document = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RepairRefused("protected recovery manifest is invalid") from exc
    try:
        digest = _sha256_file(archive)
        size = archive.stat().st_size
    except OSError as exc:
        raise RepairRefused("protected recovery capture is unreadable") from exc
    if (
        not isinstance(document, dict)
        or document.get("schema") != retention.SCHEMA_ARTIFACT
        or document.get("kind") != recovery.WORKTREE_ARCHIVE_KIND
        or document.get("protected") is not True
        or lifecycle_reconcile._path_key(str(document.get("source") or ""))
        != target
        or Path(str(document.get("archive") or "")).resolve() != archive.resolve()
        or document.get("size") != size
        or document.get("sha256") != digest
        or document.get("skipped_secrets") != []
        or document.get("skipped_symlink_escape") != []
        or document.get("allow_secrets") is not False
    ):
        raise RepairRefused("protected recovery capture failed validation")
    return {
        "artifact_id": document.get("artifact_id"),
        "archive": str(archive),
        "manifest": str(manifest),
        "sha256": digest,
    }


def _receipt_files() -> set[str]:
    directory = paths.receipts_dir()
    try:
        return {
            entry.name
            for entry in directory.iterdir()
            if entry.name.startswith("clean-")
            and entry.name.endswith(".json")
            and _regular_file(entry)
        }
    except OSError:
        return set()


def _read_new_receipt(before: set[str], target: str) -> dict | None:
    candidates = []
    directory = paths.receipts_dir()
    try:
        entries = list(directory.iterdir())
    except OSError:
        return None
    for entry in entries:
        if entry.name in before or not _regular_file(entry):
            continue
        if not entry.name.startswith("clean-") or not entry.name.endswith(".json"):
            continue
        try:
            raw = entry.read_bytes()
            if len(raw) > 1_048_576:
                continue
            receipt = json.loads(raw)
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if (
            isinstance(receipt, dict)
            and lifecycle_reconcile._path_key(str(receipt.get("path") or "")) == target
        ):
            candidates.append(receipt)
    return candidates[0] if len(candidates) == 1 else None


def _default_clean_runner(argv: list[str]) -> CleanResult:
    path_positions = [
        index for index, value in enumerate(argv) if value == "--path"
    ]
    if len(path_positions) != 1 or path_positions[0] + 1 >= len(argv):
        raise ValueError("clean argv must contain exactly one --path value")
    target = lifecycle_reconcile._path_key(argv[path_positions[0] + 1])
    before = _receipt_files()
    result = subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        env=os.environ.copy(),
    )
    return CleanResult(
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
        receipt=_read_new_receipt(before, target),
    )


def _valid_removed_receipt(receipt: object, action: dict) -> bool:
    if not isinstance(receipt, dict):
        return False
    flags = receipt.get("flags")
    live_git = action["live_git"]
    return bool(
        receipt.get("schema") == "clean_receipt/v1"
        and isinstance(receipt.get("receipt_id"), str)
        and receipt["receipt_id"]
        and receipt.get("disposition") == "removed"
        and lifecycle_reconcile._path_key(str(receipt.get("path") or ""))
        == action["target"]
        and receipt.get("branch") == live_git["branch"]
        and receipt.get("head") == live_git["head"]
        and lifecycle_reconcile._common_key(
            str(receipt.get("git_common_dir") or "")
        )
        == live_git["git_common_dir"]
        and isinstance(flags, dict)
        and flags.get("bundle") is True
        and flags.get("force") is False
        and flags.get("delete_branch") is False
    )


def _record_remove_audit(
    action: dict,
    *,
    plan_digest: str,
    authorization: str,
    capture: dict,
    receipt: dict,
    fault: Callable[[str], None] | None,
) -> None:
    connection = _write_connection()
    committed = False
    try:
        connection.execute("BEGIN IMMEDIATE")
        now = state_mod.now_iso()
        detail = {
            "schema": "awa-integrity-repair-audit/v1",
            "action_id": action["action_id"],
            "plan_digest": plan_digest,
            "authorization_sha256": hashlib.sha256(
                authorization.encode("utf-8")
            ).hexdigest(),
            "rollback": {
                "recovery_artifact_id": capture["artifact_id"],
                "recovery_sha256": capture["sha256"],
                "clean_receipt_id": receipt["receipt_id"],
            },
        }
        connection.execute(
            "INSERT INTO events(ts,lease_id,kind,detail) VALUES(?,?,?,?)",
            (
                now,
                None,
                "integrity_repair_remove_worktree",
                json.dumps(detail, sort_keys=True, separators=(",", ":")),
            ),
        )
        _fault(fault, "remove-after-audit")
        connection.execute("COMMIT")
        committed = True
    finally:
        if not committed:
            with contextlib.suppress(sqlite3.Error):
                connection.execute("ROLLBACK")
        connection.close()


def _apply_remove_worktree(
    action: dict,
    *,
    plan_digest: str,
    authorization: str,
    capture: Callable[..., Capture],
    clean_runner: Callable[[list[str]], CleanResult],
    fault: Callable[[str], None] | None,
) -> dict:
    try:
        captured = capture(action["target"], lease_id=action.get("lease_id"))
    except Exception as exc:
        raise RepairRefused("protected recovery capture failed") from exc
    capture_metadata = _validated_capture(captured, action["target"])
    _fault(fault, "remove-after-capture")

    fresh = _fresh_action(plan_digest, "remove-worktree", authorization)
    if (
        fresh.get("action_id") != action.get("action_id")
        or fresh["evidence"].get("disposition") == "active"
        or fresh["evidence"].get("live_session") is not False
        or fresh["live_git"] != action["live_git"]
    ):
        raise RepairRefused("worktree evidence changed; create a fresh plan")

    clean_script = (
        Path(__file__).resolve().parent.parent
        / "kernel"
        / "bin"
        / "dev-worktree.sh"
    )
    argv = [
        "bash",
        str(clean_script),
        "clean",
        "--path",
        action["target"],
        "--bundle",
        "--expected-branch",
        action["live_git"]["branch"],
        "--expected-head",
        action["live_git"]["head"],
        "--expected-common-dir",
        action["live_git"]["git_common_dir"],
    ]
    try:
        result = clean_runner(argv)
    except Exception as exc:
        raise RepairRefused("the existing clean safety path did not complete") from exc
    if result.returncode != 0 or not _valid_removed_receipt(result.receipt, action):
        raise RepairRefused("the existing clean safety path refused or was not receipted")

    _record_remove_audit(
        action,
        plan_digest=plan_digest,
        authorization=authorization,
        capture=capture_metadata,
        receipt=result.receipt,
        fault=fault,
    )
    return {
        "schema": "awa-integrity-repair-result/v1",
        "kind": "remove-worktree",
        "action_id": action["action_id"],
        "result": "removed",
        "recovery_artifact_id": capture_metadata["artifact_id"],
        "clean_receipt_id": result.receipt["receipt_id"],
        "fresh_plan_required": True,
    }


def apply(
    plan_digest: str,
    action_kind: str,
    authorization: str,
    *,
    capture: Callable[..., Capture] | None = None,
    clean_runner: Callable[[list[str]], CleanResult] | None = None,
    fault: Callable[[str], None] | None = None,
) -> dict:
    """Re-plan and apply exactly one explicitly authorized current action row."""
    if (
        not isinstance(plan_digest, str)
        or len(plan_digest) != 64
        or any(character not in "0123456789abcdef" for character in plan_digest)
    ):
        raise RepairRefused("a canonical plan digest is required")
    action = _fresh_action(plan_digest, action_kind, authorization)
    if action_kind == "retire-bookkeeping":
        applied = _apply_retire_bookkeeping(
            action,
            plan_digest=plan_digest,
            authorization=authorization,
            fault=fault,
        )
    elif action_kind == "remove-worktree":
        applied = _apply_remove_worktree(
            action,
            plan_digest=plan_digest,
            authorization=authorization,
            capture=capture or _default_capture,
            clean_runner=clean_runner or _default_clean_runner,
            fault=fault,
        )
    else:
        raise RepairRefused("unknown integrity repair action")

    # The side effect and its audit/receipt are already committed. A fresh plan
    # is mandatory in every successful response; if rebuilding fails, preserve
    # the truthful applied outcome in a typed error rather than implying rollback.
    try:
        fresh_plan = build_plan()
    except Exception as exc:
        raise RepairAppliedPlanUnavailable(applied) from exc
    return {**applied, "fresh_plan": fresh_plan}
