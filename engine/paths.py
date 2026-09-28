"""paths.py — XDG-anchored path resolution + local-disk placement guard (S4/H6).

The engine's durable state (SQLite WAL db + sidecars), recovery archives, detection
receipts, config, and the daemon socket/pidfile all live under XDG roots on LOCAL
disk. WAL sidecars corrupt on cloud-synced/network filesystems (§H6), so
`assert_local_disk` refuses/warns when the resolved state root sits on a synced or
network mount. Directory/file modes follow S4 (dirs 700, files 600).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

# S4: private-by-default modes for anything the engine creates.
DIR_MODE = 0o700
FILE_MODE = 0o600

# Substrings that, if present in a mount source or mount point, mark a filesystem
# as cloud-synced or network — WAL must never live there (§H6). Generic, zero-link.
_SYNCED_MOUNT_MARKERS = (
    "icloud", "com~apple~clouddocs", "dropbox", "google drive", "googledrive",
    "gdrive", "onedrive", "box sync", "boxsync", "pcloud", "mega", "nextcloud",
    "syncthing", "creative cloud",
)
_NETWORK_FS_TYPES = (
    "nfs", "smbfs", "cifs", "afpfs", "webdav", "fuse.sshfs", "9p", "ncpfs", "afs",
)


def _xdg(env_var: str, default_rel: str) -> Path:
    val = os.environ.get(env_var, "").strip()
    if val:
        return Path(val).expanduser()
    return Path.home() / default_rel


def state_home() -> Path:
    """${XDG_STATE_HOME:-~/.local/state} — durable, local-disk state root."""
    return _xdg("XDG_STATE_HOME", ".local/state")


def data_home() -> Path:
    """${XDG_DATA_HOME:-~/.local/share} — durable data (e.g. managed worktrees)."""
    return _xdg("XDG_DATA_HOME", ".local/share")


def config_home() -> Path:
    """${XDG_CONFIG_HOME:-~/.config} — operator config (setup opt-in allow-list)."""
    return _xdg("XDG_CONFIG_HOME", ".config")


def awa_state_dir() -> Path:
    return state_home() / "awa"


def state_db_path() -> Path:
    return awa_state_dir() / "state.db"


def registration_dir() -> Path:
    """ADR 0025 dedicated authority root (separate from legacy state.db)."""
    return awa_state_dir() / "registration-v1"


def registration_db_path() -> Path:
    return registration_dir() / "registration.db"


def recovery_dir() -> Path:
    return awa_state_dir() / "recovery"


def integrity_dir() -> Path:
    return awa_state_dir() / "integrity"


def integrity_status_path() -> Path:
    return integrity_dir() / "status.json"


def detections_dir() -> Path:
    return awa_state_dir() / "detections"


def receipts_dir() -> Path:
    """Kernel-owned clean_receipt/v1 records (written by dev-worktree.sh clean). The engine only
    READS these to fold them into its observable timeline — same XDG anchor as awa_roots.py."""
    return awa_state_dir() / "receipts"


def roots_dir() -> Path:
    """Kernel-owned active_root/v1 heartbeat records. The engine only READS these (never writes)
    to detect vanished-but-unattributed worktrees — same XDG anchor as awa_roots.py."""
    return awa_state_dir() / "roots"


def locks_dir() -> Path:
    return awa_state_dir() / "locks"


def run_dir() -> Path:
    """Daemon socket + pidfile live here (local disk; socket needs POSIX locking)."""
    return awa_state_dir() / "run"


def managed_worktrees_dir() -> Path:
    return data_home() / "awa" / "worktrees"


def ensure_dir(path: Path, mode: int = DIR_MODE) -> Path:
    """Create `path` (and parents) with private perms; tighten an existing dir too."""
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, mode)
    except OSError:
        pass
    return path


def write_private(path: Path, data: str, mode: int = FILE_MODE) -> None:
    """Write text to `path` with S4 file perms (600), creating parents privately."""
    ensure_dir(path.parent)
    # Create with a restrictive umask so the file is never briefly world-readable.
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        os.write(fd, data.encode("utf-8"))
    finally:
        os.close(fd)
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def _mount_info(path: Path) -> tuple[str, str, str]:
    """Best-effort (fstype, mount_source, mount_point) for `path`. Empty on failure.

    Uses `df`/`mount` (portable across macOS + Linux) rather than parsing
    /proc/mounts (absent on macOS).
    """
    target = path
    while not target.exists() and target != target.parent:
        target = target.parent
    src = mnt = fstype = ""
    try:
        out = subprocess.run(
            ["df", "-P", str(target)], capture_output=True, text=True, timeout=5
        ).stdout.splitlines()
        if len(out) >= 2:
            fields = out[1].split()
            if fields:
                src = fields[0]
                mnt = fields[-1]
    except (OSError, subprocess.SubprocessError):
        pass
    # fstype via `mount` line matching the mount point (macOS: "... (fstype, ...)").
    try:
        for line in subprocess.run(
            ["mount"], capture_output=True, text=True, timeout=5
        ).stdout.splitlines():
            if mnt and f" on {mnt} " in line:
                low = line.lower()
                if "(" in low:
                    fstype = low.split("(", 1)[1].split(",", 1)[0].strip()
                break
    except (OSError, subprocess.SubprocessError):
        pass
    return fstype, src, mnt


def is_local_disk(path: Path) -> tuple[bool, str]:
    """Return (ok, reason). ok=False when `path` resolves onto a synced/network mount."""
    fstype, src, mnt = _mount_info(path)
    hay = " ".join((fstype, src, mnt, str(path))).lower()
    for marker in _SYNCED_MOUNT_MARKERS:
        if marker in hay:
            return False, f"cloud-synced mount detected ({marker}) at {mnt or path}"
    for netfs in _NETWORK_FS_TYPES:
        if fstype == netfs or fstype.startswith(netfs):
            return False, f"network filesystem ({fstype}) at {mnt or path}"
    return True, f"local disk ({fstype or 'unknown fstype'}) at {mnt or path}"


def assert_local_disk(path: Path) -> None:
    """Raise RuntimeError if `path` is on a synced/network mount (WAL corruption risk)."""
    ok, reason = is_local_disk(path)
    if not ok:
        raise RuntimeError(
            f"AWA state root must be on local disk (WAL corrupts on synced/network "
            f"filesystems, §H6): {reason}. Set XDG_STATE_HOME to a local path."
        )
