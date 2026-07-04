"""lease.py — .awa/lease.json (awa-lease/v1) writer/reader (frozen contract).

The lease is the on-disk claim that a worktree is an AWA-managed Safe Workspace.
Its identity is the derived hash (identity.lease_id), NEVER a bare pid. The file is
written under the worktree at `.awa/lease.json` with S4 perms; the same record is
mirrored into the durable SQLite state so the engine can discover orphaned leases
without walking the filesystem.

Required keys (frozen awa-contract.v1.json): schema, lease_id, worktree_path,
branch, git_common_dir, boot_id, created_at. pid is informational only.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from . import identity, paths

SCHEMA = "awa-lease/v1"
REQUIRED_KEYS = (
    "schema", "lease_id", "worktree_path", "branch", "git_common_dir",
    "boot_id", "created_at",
)


def lease_path(worktree_path: str) -> Path:
    return Path(worktree_path) / ".awa" / "lease.json"


def build_lease(worktree_path: str, branch: str, git_common_dir: str,
                *, base_ref: str | None = None, head: str | None = None,
                boot: str | None = None) -> dict:
    boot = boot if boot is not None else identity.boot_id()
    lid = identity.lease_id(worktree_path, branch, git_common_dir, boot)
    return {
        "schema": SCHEMA,
        "lease_id": lid,
        "worktree_path": os.path.abspath(worktree_path),
        "branch": branch,
        "git_common_dir": os.path.abspath(git_common_dir),
        "boot_id": boot,
        "base_ref": base_ref,
        "head": head,
        "status": "active",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pid": os.getpid(),  # informational ONLY (never the identity — §H6).
    }


def validate(lease: dict) -> list[str]:
    """Return a list of contract violations ([] == valid)."""
    errs: list[str] = []
    for k in REQUIRED_KEYS:
        if k not in lease:
            errs.append(f"missing required key: {k}")
    if lease.get("schema") != SCHEMA:
        errs.append(f"schema must be {SCHEMA!r}, got {lease.get('schema')!r}")
    # identity must equal the derived hash (not a bare pid).
    if all(k in lease for k in ("worktree_path", "branch", "git_common_dir", "boot_id")):
        expect = identity.lease_id(
            lease["worktree_path"], lease["branch"], lease["git_common_dir"], lease["boot_id"]
        )
        if lease.get("lease_id") != expect:
            errs.append("lease_id does not match hash(worktree_path+branch+common_dir+boot_id)")
    lid = lease.get("lease_id", "")
    if lid.isdigit():
        errs.append("lease_id must not be a bare pid")
    return errs


def write_lease(worktree_path: str, lease: dict) -> Path:
    errs = validate(lease)
    if errs:
        raise ValueError("invalid lease: " + "; ".join(errs))
    lp = lease_path(worktree_path)
    paths.ensure_dir(lp.parent)
    paths.write_private(lp, json.dumps(lease, indent=2, sort_keys=False) + "\n")
    return lp


def read_lease(worktree_path: str) -> dict | None:
    lp = lease_path(worktree_path)
    if not lp.exists():
        return None
    try:
        return json.loads(lp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
