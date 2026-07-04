"""identity.py — durable lease identity (§H6, frozen contract awa-lease/v1).

Lease ownership identity = sha256(worktree_path + branch + git_common_dir + boot_id).
NEVER a bare pid (a pid is reused across reboots and processes). `boot_id`
disambiguates reboots; `git_common_dir` ties the lease to the real object store;
`worktree_path + branch` make it unique per Safe Workspace. A pid MAY be recorded as
an informational field but is never the identity.
"""

from __future__ import annotations

import hashlib
import os
import platform
import subprocess

_SEP = "\x1f"  # unit separator — cannot appear in a path/branch, so no ambiguity.


def boot_id() -> str:
    """A per-boot nonce, stable across a machine's uptime.

    - Linux: /proc/sys/kernel/random/boot_id.
    - macOS: kern.boottime (sysctl) — the boot timestamp is stable per boot.
    - Fallback: psutil-free btime is unavailable, so hash of uname + a coarse marker.
    """
    try:
        with open("/proc/sys/kernel/random/boot_id", encoding="ascii") as fh:
            val = fh.read().strip()
            if val:
                return val
    except OSError:
        pass
    if platform.system() == "Darwin":
        try:
            out = subprocess.run(
                ["sysctl", "-n", "kern.boottime"],
                capture_output=True, text=True, timeout=5,
            ).stdout.strip()
            if out:
                # e.g. "{ sec = 1782872917, usec = 778983 } ..." — sec is per-boot stable.
                digits = "".join(c for c in out.split("sec")[1] if c.isdigit()) if "sec" in out else ""
                return f"darwin-boot-{digits or out}"
        except (OSError, subprocess.SubprocessError, IndexError):
            pass
    # Last resort: still deterministic within a process lineage, never a bare pid.
    return "uname-" + hashlib.sha256(
        (platform.node() + platform.version()).encode("utf-8")
    ).hexdigest()[:16]


def lease_id(worktree_path: str, branch: str, git_common_dir: str,
             boot: str | None = None) -> str:
    """Derive the frozen-contract lease identity. Deterministic; never a pid."""
    boot = boot if boot is not None else boot_id()
    material = _SEP.join((
        os.path.abspath(worktree_path),
        branch or "",
        os.path.abspath(git_common_dir),
        boot,
    ))
    return "awa1-" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def common_dir_key(git_common_dir: str) -> str:
    """Stable short key for the per-git-common-dir advisory lock (collision boundary)."""
    return hashlib.sha256(os.path.abspath(git_common_dir).encode("utf-8")).hexdigest()[:24]
