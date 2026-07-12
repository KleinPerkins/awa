#!/usr/bin/env python3
"""awa_finish.py — deterministic kernel core for root-bound worktree finish (AWA kernel).

KERNEL-OWNED, engine-OFF, router-OFF: stdlib only, ZERO imports of the engine package or any
router artifact. Invoked BY the shell kernel (dev-worktree.sh) exactly like awa_roots.py /
awa_policy.py, so the destructive-path safety guarantee holds with the Python engine off and
with no conversational surface installed. This module is the deterministic core of the
"finish the current linked worktree" primitive:

  * a CANONICAL inventory of every work item a discard would destroy (NUL-safe git enumeration
    + no-follow lstat classification + a versioned cruft allowlist + metadata-only descriptions);
  * a STABLE content fingerprint over that inventory + the root/branch/HEAD/marker/membership
    facts (byte-identical across repeated runs, OS directory orderings, and locales);
  * ONE content-addressed pending CHALLENGE (0600, atomic write-and-rename) with a single coarse
    staleness backstop and NO separate execution-permit window; consumed exactly once (replay-safe);
  * LITERAL-``Close`` authorization: only an exact, case-sensitive, standalone ``Close`` AND a
    byte-equal re-derived fingerprint under the lock authorizes removal;
  * a per-common-dir LOCK ABI byte-identical to engine/lock.py (shared write-serialization —
    it does NOT lock a worktree against removal), so kernel finish/clean and engine maintenance
    mutually exclude;
  * a NETWORK-FREE, local-ref branch disposition (retain vs compare-and-delete);
  * a FINAL RECHECK immediately before removal.

FAIL-SAFE on the destructive path: any uncertainty (unreadable state, ambiguous target,
fingerprint drift, lock contention, missing tool, another fresh session, traversal/mount/
nested-repo risk) PRESERVES the worktree with a precise refusal. Removal happens ONLY when, under
the lock, a freshly recomputed fingerprint byte-equals the challenge AND the answer is exactly
``Close``. Nothing probabilistic authorizes removal, and the removal path performs ZERO network
calls (no gh / fetch / ls-remote).

Storage lives under ``${XDG_STATE_HOME:-~/.local/state}/awa`` on local disk (dirs 700, files 600).
"""

from __future__ import annotations

import argparse
import calendar
import errno
import fcntl
import hashlib
import hmac
import json
import math
import os
import re
import stat
import subprocess
import sys
import time
from contextlib import contextmanager

# ---- schema / version constants (frozen, additive-within AWA contract v1) ----------------
SCHEMA_CHALLENGE = "awa_finish_challenge/v1"
SCHEMA_GENERATION_STATE = "awa_finish_generation_state/v1"
SCHEMA_SELECTED_SNAPSHOT = "awa_selected_snapshot/v1"
SCHEMA_REMOVAL_JOURNAL = "awa_finish_removal/v1"
SCHEMA_RETAIN_PUBLICATION = "awa_retain_publication/v1"
SCHEMA_OPERATION_MANIFEST = "awa_git_operation_manifest/v1"
RETAIN_PUBLICATION_PROTOCOL = "committed-marker-v1"
RETAIN_PUBLICATION_KEYS = frozenset({
    "schema", "artifact_id", "manifest_sha256",
})
# The cruft allowlist and the warning copy are BOTH versioned and BOTH fold into the fingerprint,
# so bumping either invalidates every outstanding challenge (a changed classification cannot be
# silently confirmed against an old warning).
CRUFT_ALLOWLIST_VERSION = "1"
WARNING_VERSION = "1"
RETAIN_CLASSIFICATION_VERSION = "3"
INVENTORY_FINGERPRINT_VERSION = "2"
OPERATION_CLASSIFICATION_VERSION = "1"
SELECTED_DISPOSITION_FULL_DISCARD = "full-discard"
GENERATION_TRANSITIONS = frozenset({"close_claimed", "cancelled"})
REMOVAL_PHASES = frozenset({"prepared", "removed", "finalized"})
INDEX_VISIBILITY_REFUSAL = "index_visibility_flags"

CHALLENGE_KEYS = frozenset({
    "schema", "nonce", "generation", "conversation_id", "session_key", "boot_id",
    "install_id", "root", "git_dir", "common_dir", "branch", "head", "fingerprint",
    "root_incarnation", "git_dir_incarnation",
    "operation_markers", "operation_digest", "heartbeat_membership", "warning_version",
    "cruft_allowlist_version", "selected_disposition", "hook_mode",
    "hook_requires_envelope", "hook_warning_published", "hook_activated",
    "activated_choice", "activated_envelope_digest", "created_at_epoch", "created_at",
})
GENERATION_STATE_KEYS = frozenset({
    "schema", "transition", "conversation_id", "nonce", "generation", "root",
    "common_dir", "session_key", "created_at_epoch", "created_at",
})
REMOVAL_JOURNAL_KEYS = frozenset({
    "schema", "operation_id", "phase", "root", "git_dir", "common_dir", "branch",
    "head", "conversation_id", "nonce", "generation", "session_id", "session_key",
    "boot_id", "install_id", "root_incarnation", "git_dir_incarnation",
    "fingerprint", "claim", "branch_disposition", "discard_count",
    "branch_action", "cleanup_warnings", "receipt_committed", "created_at_epoch",
    "updated_at_epoch",
})
LEGACY_REMOVAL_JOURNAL_KEYS = REMOVAL_JOURNAL_KEYS - {
    "install_id", "root_incarnation", "git_dir_incarnation",
}
PHYSICAL_INCARNATION_KEYS = frozenset({
    "device", "inode", "ctime_ns", "mode_type", "anchor_device", "anchor_inode",
})

# Single coarse staleness backstop for an ABANDONED challenge. This is a BACKSTOP, never the
# authorization mechanism: authorization is content-addressed (fingerprint byte-equality), and
# there is NO separate short-lived execution-permit window to race. Tunable, floored so a stray
# tiny value cannot create a race window.
DEFAULT_CHALLENGE_TTL_SECONDS = 900
MIN_CHALLENGE_TTL_SECONDS = 60

DIR_MODE = 0o700
FILE_MODE = 0o600

# Versioned cruft allowlist — EXACT path-SEGMENT match only (split on "/", match a whole
# segment), NEVER a substring. Broad names (data/build/dist) are deliberately NOT here: an
# unknown untracked/ignored path DEFAULTS to operator work (shown). Tracked files are NEVER
# hidden regardless of a segment match.
CRUFT_SEGMENTS = frozenset({
    "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".DS_Store", ".git",
})
CRUFT_BASENAME_SUFFIXES = (".pyc", ".pyo")

# AWA-ephemeral branch prefix (a Cursor product term, not an org literal). A branch under this
# prefix is one AWA created; matched with the trailing slash so `cursor/worktree` alone is not a
# match. Overridable to mirror dev-worktree.sh's DEV_WORKTREE_BRANCH_PREFIX.
DEFAULT_BRANCH_PREFIX = os.environ.get("DEV_WORKTREE_BRANCH_PREFIX", "cursor/worktree").strip("/")

# Branch names that are NEVER auto-deleted (default/protected), even at an empty local-only set.
PROTECTED_BRANCHES = frozenset({"main", "master", "trunk", "develop", "HEAD"})

# Secret-by-name/type patterns — a file is NAMED as a likely secret by path/type WITHOUT reading
# its contents (metadata only). Mirrors the S1 bundle denylist intent.
_SECRET_SEGMENT_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".keystore", ".jks")
_SECRET_SEGMENT_EXACT = ("id_rsa", "id_ed25519", "id_dsa", "id_ecdsa", ".netrc", ".npmrc")
_SECRET_SUBSTRINGS = ("credential", "secret", "token")


class FinishError(RuntimeError):
    """A deterministic refusal/error on the finish path (never a spurious success)."""


class LockBusy(RuntimeError):
    """Raised when a non-blocking acquire finds the per-common-dir lock already held."""


class ClosedArgumentError(RuntimeError):
    """An argparse refusal whose private parser detail must not cross the CLI boundary."""


class ClosedArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs) -> None:
        # argparse otherwise accepts unique long-option prefixes.  The finish kernel's closed
        # grammar requires exact option bytes at the root parser and every generated subparser.
        kwargs["allow_abbrev"] = False
        super().__init__(*args, **kwargs)

    def error(self, _message: str) -> None:
        raise ClosedArgumentError("invalid_arguments")


def _finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise argparse.ArgumentTypeError("finite number required")
    return parsed


# ---- storage paths (XDG-anchored, local disk) -------------------------------------------
def _state_home() -> str:
    val = os.environ.get("XDG_STATE_HOME", "").strip()
    if val:
        return os.path.expanduser(val)
    return os.path.join(os.path.expanduser("~"), ".local", "state")


def awa_state_dir() -> str:
    return os.path.join(_state_home(), "awa")


def finish_dir() -> str:
    return os.path.join(awa_state_dir(), "finish")


def locks_dir() -> str:
    return os.path.join(awa_state_dir(), "locks")


_DURABILITY = None


def _durability_module():
    """Load the one co-located stdlib durability implementation by path."""
    global _DURABILITY
    if _DURABILITY is not None:
        return _DURABILITY
    import importlib.util
    path = os.environ.get("AWA_DURABILITY_LIB", "").strip()
    if not path:
        path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "awa_durability.py")
    spec = importlib.util.spec_from_file_location("awa_durability_for_finish", path)
    if spec is None or spec.loader is None:
        raise FinishError(f"cannot load AWA durability kernel lib: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _DURABILITY = mod
    return mod


def _ensure_dir(path: str) -> None:
    _durability_module().ensure_private_directory(path, DIR_MODE)


def _write_private(path: str, text: str) -> None:
    """Atomic private replace through the shared physical-durability primitive."""
    _durability_module().atomic_private_replace(
        path, text.encode("utf-8"), file_mode=FILE_MODE, dir_mode=DIR_MODE)


def _now_epoch() -> int:
    return int(time.time())


def _iso_from_epoch(epoch: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _now_iso() -> str:
    return _iso_from_epoch(_now_epoch())


def _now_pair() -> tuple[int, str]:
    epoch = _now_epoch()
    return epoch, _iso_from_epoch(epoch)


def _strict_positive_epoch(value) -> int | None:
    return value if type(value) is int and value > 0 else None


def _strict_iso_epoch(value) -> int | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return calendar.timegm(time.strptime(value, "%Y-%m-%dT%H:%M:%SZ"))
    except (TypeError, ValueError):
        return None


def _timestamp_pair_state(iso_value, epoch_value) -> tuple[str, int | None]:
    """Exact current writer, plus the sole known old two-call boundary skew."""
    iso_epoch = _strict_iso_epoch(iso_value)
    epoch = _strict_positive_epoch(epoch_value)
    if iso_epoch is None or epoch is None:
        return "invalid", None
    if iso_epoch == epoch:
        return "exact", epoch
    if abs(iso_epoch - epoch) == 1:
        return "legacy_skew", epoch
    return "invalid", None


def canon(path: str) -> str:
    """Canonical root path: expanduser + realpath. MUST match awa_roots.canon and the kernel
    clean gate (which canonicalizes with `pwd -P`), so the heartbeat, challenge, and removal all
    key the SAME record regardless of a symlinked prefix (macOS /tmp -> /private/tmp)."""
    return os.path.realpath(os.path.abspath(os.path.expanduser(path)))


# ---- awa_roots loader (sibling kernel lib, loaded by PATH — never a package import) ------
_ROOTS = None


def _roots_module():
    """Load the co-located awa_roots.py by path (env AWA_ROOTS_LIB else the sibling file). This
    keeps the two stdlib-only kernel libs decoupled at import time while letting finish reuse the
    canonical heartbeat/session logic UNDER THE LOCK. Never imports the engine or a router."""
    global _ROOTS
    if _ROOTS is not None:
        return _ROOTS
    import importlib.util
    path = os.environ.get("AWA_ROOTS_LIB", "").strip()
    if not path:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "awa_roots.py")
    spec = importlib.util.spec_from_file_location("awa_roots_for_finish", path)
    if spec is None or spec.loader is None:
        raise FinishError(f"cannot load awa_roots kernel lib: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _ROOTS = mod
    return mod


def boot_id() -> str:
    return _roots_module().boot_id()


def install_id() -> str:
    """Read or durably create the stable private install identity.

    A visible-but-not-yet-certified file is explicitly adopted before it is trusted.  Failure is
    a finish refusal; a boot-derived fallback is not a durable installation identity.
    """
    path = os.path.join(awa_state_dir(), "install-id")
    try:
        raw = _read_regular_nofollow(path, limit=4096)
    except FileNotFoundError:
        raw = None
    except (OSError, FinishError) as exc:
        raise FinishError("install_identity_unavailable") from exc
    if raw is not None:
        try:
            _durability_module().adopt_visible(path)
            val = raw.decode("ascii").strip()
        except (OSError, UnicodeError) as exc:
            raise FinishError("install_identity_unavailable") from exc
        if (not val or len(val) > 256 or "\n" in val or "\r" in val
                or (val.startswith("inst-")
                    and re.fullmatch(r"inst-[0-9a-f]{32}", val) is None)):
            raise FinishError("install_identity_invalid")
        return val
    nonce = "inst-" + os.urandom(16).hex()
    try:
        _durability_module().create_private_exclusive(
            path, (nonce + "\n").encode("ascii"),
            file_mode=FILE_MODE, dir_mode=DIR_MODE)
        return nonce
    except FileExistsError:
        # A concurrent common-dir operation may have initialized the machine-wide identity.
        return install_id()
    except OSError as exc:
        raise FinishError("install_identity_unavailable") from exc


def _valid_incarnation(value: object) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == PHYSICAL_INCARNATION_KEYS
        and type(value.get("device")) is int and value["device"] >= 0
        and type(value.get("inode")) is int and value["inode"] > 0
        and type(value.get("ctime_ns")) is int and value["ctime_ns"] > 0
        and value.get("mode_type") == stat.S_IFDIR
        and type(value.get("anchor_device")) is int and value["anchor_device"] >= 0
        and type(value.get("anchor_inode")) is int and value["anchor_inode"] >= 0
        and ((value["anchor_device"] == 0 and value["anchor_inode"] == 0)
             or value["anchor_inode"] > 0)
    )


def physical_incarnation(path: str, *, stable_anchor: str | None = None) -> dict:
    """Strict local identity for a directory without following a replacement symlink."""
    try:
        st = os.lstat(path)
    except OSError as exc:
        raise FinishError(f"physical_identity_unavailable:{exc.errno}") from exc
    if not stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode):
        raise FinishError("physical_identity_not_directory")
    identity_time = getattr(st, "st_ctime_ns", int(st.st_ctime * 1_000_000_000))
    anchor_device = 0
    anchor_inode = 0
    if stable_anchor is not None:
        try:
            anchor = os.lstat(stable_anchor)
        except OSError as exc:
            raise FinishError(f"physical_anchor_unavailable:{exc.errno}") from exc
        if not stat.S_ISREG(anchor.st_mode) or stat.S_ISLNK(anchor.st_mode):
            raise FinishError("physical_anchor_not_regular")
        # Git may create/remove lock files inside its per-worktree admin directory during
        # read-only probes, changing the directory ctime. The immutable `gitdir` anchor's own
        # inode+ctime supplies the stable incarnation time without weakening replacement proof.
        identity_time = getattr(
            anchor, "st_ctime_ns", int(anchor.st_ctime * 1_000_000_000))
        anchor_device = anchor.st_dev
        anchor_inode = anchor.st_ino
    value = {
        "device": st.st_dev,
        "inode": st.st_ino,
        "ctime_ns": identity_time,
        "mode_type": stat.S_IFMT(st.st_mode),
        "anchor_device": anchor_device,
        "anchor_inode": anchor_inode,
    }
    if not _valid_incarnation(value):
        raise FinishError("physical_identity_invalid")
    return value


def capture_physical_incarnations(root: str, git_dir: str) -> tuple[dict, dict]:
    """Capture root + per-worktree Git-admin identity and reject an in-capture replacement."""
    root_first = physical_incarnation(canon(root))
    git_abs = os.path.abspath(git_dir)
    git_first = physical_incarnation(
        git_abs, stable_anchor=os.path.join(git_abs, "gitdir"))
    root_after = physical_incarnation(canon(root))
    git_after = physical_incarnation(
        git_abs, stable_anchor=os.path.join(git_abs, "gitdir"))
    if root_after != root_first or git_after != git_first:
        raise FinishError("physical_identity_drift")
    return root_first, git_first


# ---- per-common-dir lock ABI (SHARED with engine/lock.py — write-serialization only) -----
def common_dir_key(git_common_dir: str) -> str:
    """Stable short key for the per-common-dir advisory lock. BYTE-IDENTICAL to
    engine.identity.common_dir_key: sha256(os.path.abspath(common_dir))[:24]. Using abspath (not
    realpath) is deliberate — it matches the engine so kernel finish/clean and engine maintenance
    hash to the SAME lockfile and therefore mutually exclude."""
    return hashlib.sha256(os.path.abspath(git_common_dir).encode("utf-8")).hexdigest()[:24]


def lockfile_for(git_common_dir: str) -> str:
    return os.path.join(locks_dir(), f"common-{common_dir_key(git_common_dir)}.lock")


@contextmanager
def common_dir_lock(git_common_dir: str, *, blocking: bool = True, timeout: float = 30.0):
    """Hold the per-common-dir advisory flock for the duration of the block. This is a
    write-serialization lock (identical ABI to engine/lock.py) — it serializes the kernel finish
    critical section against ordinary clean and engine maintenance. It does NOT protect a worktree
    against removal (disposition remains advisory kernel state — the K0/K1 locked decision).

    blocking=True waits up to `timeout`s then raises LockBusy; blocking=False fails immediately."""
    _ensure_dir(locks_dir())
    lf = lockfile_for(git_common_dir)
    fd = os.open(lf, os.O_RDWR | os.O_CREAT, FILE_MODE)
    try:
        os.chmod(lf, FILE_MODE)
    except OSError:
        pass
    acquired = False
    try:
        if blocking:
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES):
                        raise
                    if time.monotonic() >= deadline:
                        raise LockBusy("lock busy")
                    time.sleep(0.05)
        else:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except OSError as exc:
                if exc.errno in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES):
                    raise LockBusy("lock busy") from exc
                raise
        try:
            os.ftruncate(fd, 0)
            os.write(fd, f"{os.getpid()}\n".encode("ascii"))
        except OSError:
            pass
        yield lf
    finally:
        if acquired:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
        os.close(fd)


def _flock_inherited_fd(fd: int, timeout: float) -> int:
    """Acquire LOCK_EX on an ALREADY-OPEN inherited file descriptor and RETURN (leaving the lock
    held). The caller (the shell kernel's ordinary `clean --path`) keeps that fd open across its
    destructive section, so the lock persists after THIS short-lived process exits — the standard
    `flock(1) <fd>` pattern. Byte-identical ABI to common_dir_lock (LOCK_EX on the SAME
    lockfile_for(common_dir) the shell opened), so ordinary clean serializes against kernel finish
    + engine maintenance. This is write-serialization ONLY (it does not lock a worktree against
    removal). Exit 0 on acquire; EX_TEMPFAIL(75) on contention within `timeout` so the caller maps
    it to a FAIL-SAFE `clean_lock_busy` refusal (preserve the worktree); 1 on an unexpected error."""
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return 0
        except OSError as exc:
            if exc.errno not in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES):
                sys.stderr.write("flock-fd: local coordination failed\n")
                return 1
            if time.monotonic() >= deadline:
                sys.stderr.write("flock-fd: another local action is in progress\n")
                return 75
            time.sleep(0.05)


# ---- git helpers (LOCAL refs only — the removal path performs ZERO network calls) --------
_SAFE_GIT_PROFILE = {
    "GIT_OPTIONAL_LOCKS": "0",
    "GIT_NO_LAZY_FETCH": "1",
    "GIT_TERMINAL_PROMPT": "0",
}
_OID_FORMATS = {"sha1": 40, "sha256": 64}


def sanitized_git_env(*, index_file: str | None = None) -> dict:
    """Return a deterministic finish Git environment.

    Every inherited ``GIT_*`` selector/config/object variable is removed first.  HOME, XDG,
    PATH, and other non-Git variables are deliberately retained so ordinary repository/global
    configuration and configured filters keep their normal semantics.  A caller may add exactly
    one internally validated index path; repository/worktree binding is passed on Git's argv.
    """
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(_SAFE_GIT_PROFILE)
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    env["LANGUAGE"] = "C"
    if index_file is not None:
        if not isinstance(index_file, str) or not os.path.isabs(index_file):
            raise FinishError("git_index_binding_invalid")
        env["GIT_INDEX_FILE"] = os.path.abspath(index_file)
    return env


def _read_regular_nofollow(path: str, *, limit: int = 1024 * 1024) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size < 0 or before.st_size > limit:
            raise FinishError("git_binding_invalid")
        chunks = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(fd, min(64 * 1024, remaining))
            if not chunk:
                raise FinishError("git_binding_invalid")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(fd, 1):
            raise FinishError("git_binding_invalid")
        after = os.fstat(fd)
    finally:
        os.close(fd)
    path_after = os.stat(path, follow_symlinks=False)
    if (_stat_identity(before) != _stat_identity(after)
            or _stat_identity(before) != _stat_identity(path_after)):
        raise FinishError("git_binding_drift")
    return b"".join(chunks)


def _pointer_target(pointer_file: str, *, prefix: bytes | None = None) -> str:
    raw = _read_regular_nofollow(pointer_file, limit=64 * 1024).strip()
    if prefix is not None:
        if not raw.startswith(prefix):
            raise FinishError("git_binding_invalid")
        raw = raw[len(prefix):].strip()
    if not raw or b"\x00" in raw or b"\n" in raw or b"\r" in raw:
        raise FinishError("git_binding_invalid")
    value = os.fsdecode(raw)
    if not os.path.isabs(value):
        value = os.path.join(os.path.dirname(pointer_file), value)
    return os.path.abspath(os.path.normpath(value))


def validated_git_binding(root: str, *, git_dir: str | None = None,
                          common_dir: str | None = None,
                          allow_primary: bool = False) -> dict:
    """Validate the linked-worktree administration files without Git discovery.

    The returned real index is the only index finish inventory may read.  Repository and
    worktree are bound on every subsequent Git argv, preventing ambient selectors from switching
    the operation to another repository or index.
    """
    root_c = canon(root)
    try:
        root_st = os.lstat(root_c)
    except OSError as exc:
        raise FinishError("git_binding_root_unavailable") from exc
    if not stat.S_ISDIR(root_st.st_mode) or stat.S_ISLNK(root_st.st_mode):
        raise FinishError("git_binding_root_invalid")
    dotgit = os.path.join(root_c, ".git")
    try:
        dotgit_st = os.lstat(dotgit)
    except OSError as exc:
        raise FinishError("git_binding_admin_unavailable") from exc
    if stat.S_ISDIR(dotgit_st.st_mode) and not stat.S_ISLNK(dotgit_st.st_mode):
        if not allow_primary:
            raise FinishError("primary_checkout")
        expected_git = os.path.abspath(git_dir) if git_dir is not None else dotgit
        expected_common = (
            os.path.abspath(common_dir) if common_dir is not None else dotgit)
        if expected_git != dotgit or expected_common != dotgit:
            raise FinishError("git_binding_invalid")
        index_file = os.path.join(dotgit, "index")
        try:
            index_st = os.lstat(index_file)
        except OSError as exc:
            raise FinishError(INDEX_VISIBILITY_REFUSAL) from exc
        if not stat.S_ISREG(index_st.st_mode) or stat.S_ISLNK(index_st.st_mode):
            raise FinishError(INDEX_VISIBILITY_REFUSAL)
        return {
            "root": root_c, "git_dir": dotgit, "common_dir": dotgit,
            "index_file": index_file,
        }
    discovered_git = _pointer_target(dotgit, prefix=b"gitdir:")
    expected_git = os.path.abspath(git_dir) if git_dir is not None else discovered_git
    if discovered_git != expected_git:
        raise FinishError("git_dir_changed")
    try:
        git_st = os.lstat(expected_git)
    except OSError as exc:
        raise FinishError("git_binding_admin_unavailable") from exc
    if not stat.S_ISDIR(git_st.st_mode) or stat.S_ISLNK(git_st.st_mode):
        raise FinishError("git_binding_admin_invalid")
    backlink = _pointer_target(os.path.join(expected_git, "gitdir"))
    if backlink != dotgit:
        raise FinishError("git_binding_backlink_mismatch")
    discovered_common = _pointer_target(os.path.join(expected_git, "commondir"))
    expected_common = (
        os.path.abspath(common_dir) if common_dir is not None else discovered_common)
    if discovered_common != expected_common or expected_git == expected_common:
        raise FinishError("common_dir_changed")
    try:
        common_st = os.lstat(expected_common)
    except OSError as exc:
        raise FinishError("git_binding_common_unavailable") from exc
    if not stat.S_ISDIR(common_st.st_mode) or stat.S_ISLNK(common_st.st_mode):
        raise FinishError("git_binding_common_invalid")
    index_file = os.path.join(expected_git, "index")
    try:
        index_st = os.lstat(index_file)
    except OSError as exc:
        raise FinishError(INDEX_VISIBILITY_REFUSAL) from exc
    if not stat.S_ISREG(index_st.st_mode) or stat.S_ISLNK(index_st.st_mode):
        raise FinishError(INDEX_VISIBILITY_REFUSAL)
    return {
        "root": root_c,
        "git_dir": expected_git,
        "common_dir": expected_common,
        "index_file": index_file,
    }


def _run_git_unbound(root: str, *args: str, text: bool) -> subprocess.CompletedProcess:
    """Sanitized discovery used only before a binding can exist."""
    return subprocess.run(
        ["git", "-C", root, *args], capture_output=True, text=text,
        env=sanitized_git_env())


def _run_git_bound(binding: dict, *args: str, text: bool = False) -> subprocess.CompletedProcess:
    command = [
        "git", "--git-dir=" + binding["git_dir"],
        "--work-tree=" + binding["root"], *args,
    ]
    return subprocess.run(
        command, capture_output=True, text=text,
        env=sanitized_git_env(index_file=binding["index_file"]))


def _run_git_admin(common_dir: str, *args: str, text: bool = False,
                   cwd: str | None = None) -> subprocess.CompletedProcess:
    common = os.path.abspath(common_dir)
    st = os.lstat(common)
    if not stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode):
        raise FinishError("git_binding_common_invalid")
    return subprocess.run(
        ["git", "--git-dir=" + common, *args], capture_output=True, text=text,
        cwd=cwd, env=sanitized_git_env())


def resolve_target(root: str) -> dict:
    """Resolve then independently bind one exact linked worktree using a sanitized environment."""
    root_c = canon(root)
    probes = {
        "root": ("rev-parse", "--show-toplevel"),
        "git_dir": ("rev-parse", "--path-format=absolute", "--git-dir"),
        "common_dir": ("rev-parse", "--path-format=absolute", "--git-common-dir"),
        "branch": ("rev-parse", "--abbrev-ref", "HEAD"),
        "head": ("rev-parse", "HEAD"),
    }
    values = {}
    for key, args in probes.items():
        proc = _run_git_unbound(root_c, *args, text=True)
        if proc.returncode != 0:
            raise FinishError("git_identity_unavailable")
        values[key] = proc.stdout.strip()
    if canon(values["root"]) != root_c:
        raise FinishError("current_root_not_worktree_toplevel")
    if os.path.abspath(values["git_dir"]) == os.path.abspath(values["common_dir"]):
        raise FinishError("primary_checkout")
    binding = validated_git_binding(
        root_c, git_dir=values["git_dir"], common_dir=values["common_dir"])
    object_format = _run_git_bound(
        binding, "rev-parse", "--show-object-format", text=True)
    if object_format.returncode != 0 or object_format.stdout.strip() not in _OID_FORMATS:
        raise FinishError("git_object_format_unavailable")
    fmt = object_format.stdout.strip()
    if re.fullmatch(rf"[0-9a-f]{{{_OID_FORMATS[fmt]}}}", values["head"]) is None:
        raise FinishError("git_head_invalid")
    # Repeat every mutable identity through the exact argv/index binding.
    bound_probes = {
        "root": ("rev-parse", "--show-toplevel"),
        "git_dir": ("rev-parse", "--path-format=absolute", "--git-dir"),
        "common_dir": ("rev-parse", "--path-format=absolute", "--git-common-dir"),
        "branch": ("rev-parse", "--abbrev-ref", "HEAD"),
        "head": ("rev-parse", "HEAD"),
    }
    for key, args in bound_probes.items():
        proc = _run_git_bound(binding, *args, text=True)
        if proc.returncode != 0:
            raise FinishError("git_identity_unavailable")
        actual = proc.stdout.strip()
        expected = values[key]
        if key == "root":
            matches = canon(actual) == root_c
        elif key in {"git_dir", "common_dir"}:
            matches = os.path.abspath(actual) == os.path.abspath(expected)
        else:
            matches = actual == expected
        if not matches:
            raise FinishError("git_identity_changed")
    effective_branch = values["branch"]
    if effective_branch in ("", "HEAD"):
        # A detached operation is accepted only when its complete canonical operation state names
        # one live original local branch. Ordinary detached HEAD remains a hard refusal.
        _index_visibility_preflight(root_c, binding["git_dir"])
        raw_index = _read_index_stable(binding["index_file"])
        status = _run_git_bound(
            binding, "-c", "core.quotepath=false",
            "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
            "status", "--porcelain=v1", "-z",
            "--untracked-files=all", "--ignored=matching")
        index = _run_git_bound(
            binding, "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
            "ls-files", "--stage", "-z")
        if status.returncode != 0 or index.returncode != 0:
            raise FinishError("detached_operation_unavailable")
        operation = _capture_operation_manifest(
            binding, status_bytes=status.stdout, index_listing=index.stdout,
            raw_index=raw_index)
        original_ref = operation.get("original_ref", "")
        if (not operation.get("active")
                or not isinstance(original_ref, str)
                or not original_ref.startswith("refs/heads/")
                or original_ref == "refs/heads/"):
            raise FinishError("detached_head")
        effective_branch = original_ref[len("refs/heads/"):]
    return {
        "root": root_c,
        "git_dir": binding["git_dir"],
        "common_dir": binding["common_dir"],
        "branch": effective_branch,
        "head": values["head"],
    }


def _git_bytes(root: str, *args: str) -> subprocess.CompletedProcess:
    """Run a LOCAL Git command against the validated real worktree/index."""
    return _run_git_bound(
        validated_git_binding(root, allow_primary=True), *args, text=False)


def _git_text(root: str, *args: str) -> subprocess.CompletedProcess:
    return _run_git_bound(
        validated_git_binding(root, allow_primary=True), *args, text=True)


_INDEX_TAG_CODES = frozenset(b"HSMRCK?U")
_INDEX_VISIBILITY_EXTENSIONS = frozenset({b"FSMN", b"sdir", b"link"})
_MAX_INDEX_BYTES = 512 * 1024 * 1024


def _read_index_stable(index_path: str) -> bytes:
    """Read one regular index file without following links and reject concurrent replacement."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(index_path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size < 0:
            raise FinishError(INDEX_VISIBILITY_REFUSAL)
        if before.st_size > _MAX_INDEX_BYTES:
            raise FinishError(INDEX_VISIBILITY_REFUSAL)
        chunks = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(fd, min(1024 * 1024, remaining))
            if not chunk:
                raise FinishError(INDEX_VISIBILITY_REFUSAL)
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(fd, 1):
            raise FinishError(INDEX_VISIBILITY_REFUSAL)
        after_fd = os.fstat(fd)
    finally:
        os.close(fd)
    after_path = os.stat(index_path, follow_symlinks=False)
    identity = lambda st: (
        st.st_dev, st.st_ino, st.st_mode, st.st_size,
        getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000)),
        getattr(st, "st_ctime_ns", int(st.st_ctime * 1_000_000_000)),
    )
    if identity(before) != identity(after_fd) or identity(before) != identity(after_path):
        raise FinishError(INDEX_VISIBILITY_REFUSAL)
    return b"".join(chunks)


def _decode_index_v4_varint(data: bytes, offset: int, limit: int) -> tuple[int, int]:
    """Decode the index-v4 path-prefix deletion count and return (value, next_offset)."""
    if offset >= limit:
        raise FinishError(INDEX_VISIBILITY_REFUSAL)
    value = data[offset] & 0x7F
    byte = data[offset]
    offset += 1
    count = 1
    while byte & 0x80:
        if offset >= limit or count >= 10:
            raise FinishError(INDEX_VISIBILITY_REFUSAL)
        byte = data[offset]
        offset += 1
        value = ((value + 1) << 7) | (byte & 0x7F)
        count += 1
    return value, offset


def _parse_index_candidate(data: bytes, *, oid_size: int, algorithm: str) -> frozenset[bytes]:
    """Validate one SHA-1/SHA-256 index candidate and return its extension signatures."""
    checksum_start = len(data) - oid_size
    if checksum_start < 12 or data[:4] != b"DIRC":
        raise FinishError(INDEX_VISIBILITY_REFUSAL)
    expected = data[checksum_start:]
    if hashlib.new(algorithm, data[:checksum_start]).digest() != expected:
        raise FinishError(INDEX_VISIBILITY_REFUSAL)
    version = int.from_bytes(data[4:8], "big")
    entry_count = int.from_bytes(data[8:12], "big")
    if version not in (2, 3, 4):
        raise FinishError(INDEX_VISIBILITY_REFUSAL)
    offset = 12
    previous_path = b""
    for _ in range(entry_count):
        entry_start = offset
        fixed = 40 + oid_size + 2
        if offset + fixed > checksum_start:
            raise FinishError(INDEX_VISIBILITY_REFUSAL)
        flags_offset = offset + 40 + oid_size
        entry_flags = int.from_bytes(data[flags_offset:flags_offset + 2], "big")
        offset += fixed
        if entry_flags & 0x4000:
            if version == 2 or offset + 2 > checksum_start:
                raise FinishError(INDEX_VISIBILITY_REFUSAL)
            offset += 2
        if version in (2, 3):
            nul = data.find(b"\x00", offset, checksum_start)
            if nul < 0 or nul == offset:
                raise FinishError(INDEX_VISIBILITY_REFUSAL)
            used = nul + 1 - entry_start
            padded = entry_start + ((used + 7) & ~7)
            if padded > checksum_start or any(data[nul + 1:padded]):
                raise FinishError(INDEX_VISIBILITY_REFUSAL)
            offset = padded
        else:
            remove_count, offset = _decode_index_v4_varint(
                data, offset, checksum_start)
            if remove_count > len(previous_path):
                raise FinishError(INDEX_VISIBILITY_REFUSAL)
            nul = data.find(b"\x00", offset, checksum_start)
            if nul < 0:
                raise FinishError(INDEX_VISIBILITY_REFUSAL)
            previous_path = previous_path[:len(previous_path) - remove_count] + data[offset:nul]
            if not previous_path:
                raise FinishError(INDEX_VISIBILITY_REFUSAL)
            offset = nul + 1
    extensions = set()
    while offset < checksum_start:
        if checksum_start - offset < 8:
            raise FinishError(INDEX_VISIBILITY_REFUSAL)
        signature = data[offset:offset + 4]
        length = int.from_bytes(data[offset + 4:offset + 8], "big")
        offset += 8
        end = offset + length
        if end > checksum_start:
            raise FinishError(INDEX_VISIBILITY_REFUSAL)
        extensions.add(signature)
        offset = end
    if offset != checksum_start:
        raise FinishError(INDEX_VISIBILITY_REFUSAL)
    return frozenset(extensions)


def _index_extensions(data: bytes) -> frozenset[bytes]:
    """Parse either object format without asking Git to inspect or refresh the index."""
    candidates = []
    for oid_size, algorithm in ((20, "sha1"), (32, "sha256")):
        try:
            candidates.append(
                _parse_index_candidate(data, oid_size=oid_size, algorithm=algorithm))
        except (FinishError, ValueError):
            pass
    if len(candidates) != 1:
        raise FinishError(INDEX_VISIBILITY_REFUSAL)
    return candidates[0]


def _effective_bool_config(root: str, key: str) -> bool | None:
    """Return Git's effective boolean, None when absent, or refuse malformed/ambiguous output."""
    proc = _git_bytes(root, "config", "--type=bool", "--get", key)
    if proc.returncode == 1 and proc.stdout == b"" and proc.stderr == b"":
        return None
    if proc.returncode != 0 or proc.stderr:
        raise FinishError(INDEX_VISIBILITY_REFUSAL)
    value = proc.stdout
    if value == b"true\n":
        return True
    if value == b"false\n":
        return False
    raise FinishError(INDEX_VISIBILITY_REFUSAL)


def _parse_index_tags(data: bytes) -> list[tuple[int, bytes]]:
    """Strictly parse ``git ls-files -[vtf] -z`` without decoding or exposing path bytes."""
    if not data:
        return []
    if not data.endswith(b"\x00"):
        raise FinishError(INDEX_VISIBILITY_REFUSAL)
    parsed = []
    for record in data[:-1].split(b"\x00"):
        code = record[0] if record else -1
        normalized = code - 32 if 97 <= code <= 122 else code
        if (len(record) < 3 or record[1:2] != b" " or not record[2:]
                or normalized not in _INDEX_TAG_CODES):
            raise FinishError(INDEX_VISIBILITY_REFUSAL)
        parsed.append((code, record[2:]))
    return parsed


def _index_visibility_preflight(root: str, git_dir: str) -> None:
    """Finish-only, read-only refusal gate for Git state that can hide tracked work.

    It runs before status or filesystem inventory. Every failure and every prohibited state maps
    to one content-safe reason; paths, object ids, hashes, config values, and stderr never escape.
    """
    try:
        root_c = canon(root)
        binding = validated_git_binding(root_c, git_dir=git_dir, allow_primary=True)
        index_path = binding["index_file"]
        before = _read_index_stable(index_path)
        extensions = _index_extensions(before)
        if extensions & _INDEX_VISIBILITY_EXTENSIONS:
            raise FinishError(INDEX_VISIBILITY_REFUSAL)
        if _effective_bool_config(root_c, "core.fsmonitor") is True:
            raise FinishError(INDEX_VISIBILITY_REFUSAL)
        if _effective_bool_config(root_c, "core.sparseCheckout") is True:
            raise FinishError(INDEX_VISIBILITY_REFUSAL)

        observations = {}
        for option in ("-v", "-t", "-f"):
            proc = _git_bytes(
                root_c, "-c", "core.fsmonitor=false",
                "-c", "core.untrackedCache=false",
                "ls-files", "--cached", option, "-z")
            if proc.returncode != 0 or proc.stderr:
                raise FinishError(INDEX_VISIBILITY_REFUSAL)
            observations[option] = _parse_index_tags(proc.stdout)
        paths = [path for _code, path in observations["-v"]]
        if any([path for _code, path in observations[option]] != paths
               for option in ("-t", "-f")):
            raise FinishError(INDEX_VISIBILITY_REFUSAL)
        if any(97 <= code <= 122 for code, _path in observations["-v"]):
            raise FinishError(INDEX_VISIBILITY_REFUSAL)
        if any(code == ord("S") or 97 <= code <= 122
               for code, _path in observations["-t"]):
            raise FinishError(INDEX_VISIBILITY_REFUSAL)
        if any(97 <= code <= 122 for code, _path in observations["-f"]):
            raise FinishError(INDEX_VISIBILITY_REFUSAL)
        after = _read_index_stable(index_path)
        if after != before or _index_extensions(after) != extensions:
            raise FinishError(INDEX_VISIBILITY_REFUSAL)
    except FinishError:
        raise FinishError(INDEX_VISIBILITY_REFUSAL) from None
    except Exception:
        raise FinishError(INDEX_VISIBILITY_REFUSAL) from None


# ---- canonical inventory ----------------------------------------------------------------
_CONFLICT_CODES = frozenset({"DD", "AU", "UD", "UA", "DU", "AA", "UU"})
_OPERATION_GROUP_COPY = {
    "merge": (
        "In-progress merge",
        "An in-progress merge and its protected recovery state would be discarded.",
    ),
    "sequence": (
        "In-progress cherry-pick or revert",
        "An in-progress cherry-pick or revert and its protected recovery state would be discarded.",
    ),
    "rebase-merge": (
        "In-progress rebase",
        "An in-progress rebase and its protected recovery state would be discarded.",
    ),
    "rebase-apply": (
        "In-progress rebase",
        "An in-progress rebase and its protected recovery state would be discarded.",
    ),
    "am": (
        "In-progress patch application",
        "An in-progress patch application and its protected recovery state would be discarded.",
    ),
    "bisect": (
        "In-progress revision search",
        "An in-progress revision search and its protected recovery state would be discarded.",
    ),
    "notes-merge": (
        "In-progress notes merge",
        "An in-progress notes merge and its protected recovery state would be discarded.",
    ),
}
_OPERATION_TOP_FILES = frozenset({
    b"MERGE_HEAD", b"MERGE_MSG", b"MERGE_MODE", b"MERGE_AUTOSTASH",
    b"CHERRY_PICK_HEAD", b"REVERT_HEAD", b"REBASE_HEAD", b"REBASE_AUTOSTASH",
    b"ORIG_HEAD", b"AUTO_MERGE",
    b"BISECT_LOG", b"BISECT_START", b"BISECT_NAMES", b"BISECT_TERMS",
    b"BISECT_ANCESTORS_OK", b"BISECT_EXPECTED_REV", b"BISECT_RUN",
    b"BISECT_HEAD",
    b"NOTES_MERGE_REF", b"NOTES_MERGE_PARTIAL",
})
_OPERATION_TOP_DIRS = frozenset({
    b"sequencer", b"rebase-merge", b"rebase-apply", b"NOTES_MERGE_WORKTREE",
})
_OPERATION_OPTIONAL_BY_GROUP = {
    "merge": frozenset({
        b"MERGE_HEAD", b"MERGE_MSG", b"MERGE_MODE", b"MERGE_AUTOSTASH",
        b"ORIG_HEAD", b"AUTO_MERGE",
    }),
    "sequence": frozenset({
        b"CHERRY_PICK_HEAD", b"REVERT_HEAD", b"sequencer", b"MERGE_MSG",
        b"ORIG_HEAD", b"AUTO_MERGE",
    }),
    "rebase-merge": frozenset({
        b"rebase-merge", b"REBASE_HEAD", b"REBASE_AUTOSTASH", b"MERGE_MSG",
        b"ORIG_HEAD", b"AUTO_MERGE",
    }),
    "rebase-apply": frozenset({
        b"rebase-apply", b"REBASE_HEAD", b"REBASE_AUTOSTASH", b"ORIG_HEAD",
        b"AUTO_MERGE",
    }),
    "am": frozenset({
        b"rebase-apply", b"REBASE_HEAD", b"ORIG_HEAD", b"AUTO_MERGE",
    }),
    "bisect": frozenset({
        b"BISECT_LOG", b"BISECT_START", b"BISECT_NAMES", b"BISECT_TERMS",
        b"BISECT_ANCESTORS_OK", b"BISECT_EXPECTED_REV", b"BISECT_RUN",
        b"BISECT_HEAD", b"ORIG_HEAD",
    }),
    "notes-merge": frozenset({
        b"NOTES_MERGE_REF", b"NOTES_MERGE_PARTIAL", b"NOTES_MERGE_WORKTREE",
        b"ORIG_HEAD",
    }),
}
_OPERATION_PSEUDO_REFS = {
    "merge": ("HEAD", "ORIG_HEAD", "MERGE_HEAD", "MERGE_AUTOSTASH", "AUTO_MERGE"),
    "sequence": (
        "HEAD", "ORIG_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "AUTO_MERGE"),
    "rebase-merge": (
        "HEAD", "ORIG_HEAD", "REBASE_HEAD", "REBASE_AUTOSTASH", "AUTO_MERGE"),
    "rebase-apply": (
        "HEAD", "ORIG_HEAD", "REBASE_HEAD", "REBASE_AUTOSTASH", "AUTO_MERGE"),
    "am": ("HEAD", "ORIG_HEAD", "REBASE_HEAD", "AUTO_MERGE"),
    "bisect": ("HEAD", "ORIG_HEAD", "BISECT_HEAD"),
    "notes-merge": ("HEAD", "ORIG_HEAD"),
}
_MAX_OPERATION_FILE_BYTES = 512 * 1024 * 1024


def _bound_git_input(binding: dict, *args: str, input_data: bytes) -> subprocess.CompletedProcess:
    command = [
        "git", "--git-dir=" + binding["git_dir"],
        "--work-tree=" + binding["root"], *args,
    ]
    return subprocess.run(
        command, input=input_data, capture_output=True,
        env=sanitized_git_env(index_file=binding["index_file"]))


def _operation_top_presence(git_dir: str) -> dict[bytes, str]:
    """Return exact top-level operation candidates without following any name."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(os.fsencode(git_dir), flags)
    try:
        root_st = os.fstat(fd)
        if not stat.S_ISDIR(root_st.st_mode):
            raise FinishError("operation_admin_invalid")
        names = sorted(
            item.name if isinstance(item.name, bytes) else os.fsencode(item.name)
            for item in os.scandir(fd))
        if any(name.endswith(b".lock") for name in names):
            raise FinishError("operation_live_lock")
        out = {}
        for name in names:
            if name not in _OPERATION_TOP_FILES and name not in _OPERATION_TOP_DIRS:
                continue
            st = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISLNK(st.st_mode):
                raise FinishError("operation_admin_link")
            if stat.S_ISREG(st.st_mode):
                out[name] = "file"
            elif stat.S_ISDIR(st.st_mode):
                out[name] = "dir"
            else:
                raise FinishError("operation_admin_special")
        return out
    finally:
        os.close(fd)


def _operation_namespace_refs(binding: dict) -> list[dict]:
    """Enumerate worktree logical refs through Git's ref API (files or reftable)."""
    proc = _run_git_bound(
        binding, "for-each-ref", "--format=%(refname)%00%(objectname)",
        "refs/bisect", "refs/rewritten")
    if proc.returncode != 0 or proc.stderr:
        raise FinishError("operation_refs_unavailable")
    records = []
    for line in proc.stdout.splitlines():
        if not line:
            continue
        fields = line.split(b"\x00")
        if len(fields) != 2 or not fields[0] or not fields[1]:
            raise FinishError("operation_refs_malformed")
        try:
            oid = fields[1].decode("ascii")
        except UnicodeError as exc:
            raise FinishError("operation_refs_malformed") from exc
        if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", oid) is None:
            raise FinishError("operation_refs_malformed")
        records.append({"name_hex": fields[0].hex(), "oid": oid, "kind": "ref"})
    records.sort(key=lambda item: (item["name_hex"], item["oid"]))
    return records


def _classify_operation_groups(
        presence: dict[bytes, str], namespace_refs: list[dict]) -> list[str]:
    groups = []
    if b"MERGE_HEAD" in presence:
        groups.append("merge")
    sequence_signals = {
        name for name in (b"CHERRY_PICK_HEAD", b"REVERT_HEAD", b"sequencer")
        if name in presence
    }
    if b"CHERRY_PICK_HEAD" in sequence_signals and b"REVERT_HEAD" in sequence_signals:
        raise FinishError("operation_ambiguous")
    if sequence_signals:
        groups.append("sequence")
    if b"rebase-merge" in presence:
        groups.append("rebase-merge")
    if b"rebase-apply" in presence:
        apply_dir = os.path.join(
            os.fsencode("."), b"rebase-apply")  # logical sentinel only
        del apply_dir
        # `applying` is git-am; `rebasing` is apply-backend rebase. Exactly one must exist.
        marker_base = None
        # Presence is top-level only; the descriptor reader below validates marker type/content.
        marker_base = presence.get(b"rebase-apply")
        if marker_base != "dir":
            raise FinishError("operation_admin_invalid")
        groups.append("rebase-apply")
    bisect_refs = any(
        bytes.fromhex(item["name_hex"]).startswith(b"refs/bisect/")
        for item in namespace_refs)
    if b"BISECT_START" in presence or b"BISECT_LOG" in presence or bisect_refs:
        if b"BISECT_START" not in presence:
            raise FinishError("operation_ambiguous")
        groups.append("bisect")
    notes_signals = {
        name for name in (
            b"NOTES_MERGE_REF", b"NOTES_MERGE_PARTIAL", b"NOTES_MERGE_WORKTREE")
        if name in presence
    }
    if notes_signals:
        if b"NOTES_MERGE_REF" not in notes_signals:
            raise FinishError("operation_ambiguous")
        groups.append("notes-merge")
    if "rebase-merge" in groups and "rebase-apply" in groups:
        raise FinishError("operation_ambiguous")
    if any(group in groups for group in ("rebase-merge", "rebase-apply")) and any(
            group in groups for group in ("merge", "sequence")):
        raise FinishError("operation_ambiguous")
    rewritten_refs = any(
        bytes.fromhex(item["name_hex"]).startswith(b"refs/rewritten/")
        for item in namespace_refs)
    if rewritten_refs and not any(
            group in groups for group in ("rebase-merge", "rebase-apply")):
        raise FinishError("operation_unknown")
    if len(groups) > 1:
        raise FinishError("operation_ambiguous")
    return sorted(groups)


def _scan_operation_entry(
        parent_fd: int, parent_path_b: bytes, name_b: bytes, rel_b: bytes, *,
        root_dev: int, records: list, oid_tokens: set[bytes], oid_length: int) -> str:
    if (not rel_b or rel_b.startswith(b"/") or b"\x00" in rel_b
            or any(part in {b"", b".", b".."} for part in rel_b.split(b"/"))):
        raise FinishError("operation_path_escape")
    if name_b.endswith(b".lock"):
        raise FinishError("operation_live_lock")
    before = os.stat(name_b, dir_fd=parent_fd, follow_symlinks=False)
    if before.st_dev != root_dev:
        raise FinishError("operation_mount_boundary")
    full_b = os.path.join(parent_path_b, name_b)
    try:
        if os.path.ismount(full_b):
            raise FinishError("operation_mount_boundary")
    except OSError as exc:
        raise FinishError(f"operation_mount_check:{exc.errno}") from exc
    mode = stat.S_IMODE(before.st_mode)
    if stat.S_ISLNK(before.st_mode):
        raise FinishError("operation_admin_link")
    if stat.S_ISREG(before.st_mode):
        if before.st_size < 0 or before.st_size > _MAX_OPERATION_FILE_BYTES:
            raise FinishError("operation_admin_too_large")
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(name_b, flags, dir_fd=parent_fd)
        digest = hashlib.sha256()
        content = bytearray()
        try:
            opened = os.fstat(fd)
            if (not stat.S_ISREG(opened.st_mode)
                    or _stat_identity(opened) != _stat_identity(before)):
                raise FinishError("operation_read_drift")
            remaining = opened.st_size
            while remaining:
                chunk = os.read(fd, min(1024 * 1024, remaining))
                if not chunk:
                    raise FinishError("operation_short_read")
                digest.update(chunk)
                content.extend(chunk)
                remaining -= len(chunk)
            if os.read(fd, 1):
                raise FinishError("operation_long_read")
            after_fd = os.fstat(fd)
        finally:
            os.close(fd)
        after_path = os.stat(name_b, dir_fd=parent_fd, follow_symlinks=False)
        if (_stat_identity(opened) != _stat_identity(after_fd)
                or _stat_identity(before) != _stat_identity(after_path)):
            raise FinishError("operation_read_drift")
        pattern = rb"(?<![0-9a-f])([0-9a-f]{" + str(oid_length).encode("ascii") + rb"})(?![0-9a-f])"
        oid_tokens.update(match.group(1) for match in re.finditer(pattern, bytes(content)))
        value = digest.hexdigest()
        records.append({
            "path_hex": rel_b.hex(), "type": "file", "mode": mode,
            "size": before.st_size, "sha256": value,
        })
        return value
    if not stat.S_ISDIR(before.st_mode):
        raise FinishError("operation_admin_special")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(name_b, flags, dir_fd=parent_fd)
    try:
        opened = os.fstat(fd)
        if (not stat.S_ISDIR(opened.st_mode)
                or _stat_identity(opened) != _stat_identity(before)):
            raise FinishError("operation_read_drift")
        children = sorted(
            item.name if isinstance(item.name, bytes) else os.fsencode(item.name)
            for item in os.scandir(fd))
        child_values = []
        for child in children:
            child_rel = os.path.join(rel_b, child)
            child_digest = _scan_operation_entry(
                fd, full_b, child, child_rel, root_dev=root_dev, records=records,
                oid_tokens=oid_tokens, oid_length=oid_length)
            child_values.append({
                "name_hex": child.hex(), "sha256": child_digest,
            })
        after_fd = os.fstat(fd)
    finally:
        os.close(fd)
    after_path = os.stat(name_b, dir_fd=parent_fd, follow_symlinks=False)
    if (_stat_identity(opened) != _stat_identity(after_fd)
            or _stat_identity(before) != _stat_identity(after_path)):
        raise FinishError("operation_read_drift")
    canonical = json.dumps(
        child_values, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    value = hashlib.sha256(canonical.encode("ascii")).hexdigest()
    records.append({
        "path_hex": rel_b.hex(), "type": "dir", "mode": mode,
        "size": before.st_size, "sha256": value,
    })
    return value


def _scan_operation_admin(
        git_dir: str, descriptor_roots: list[bytes], *, oid_length: int) -> tuple[list, set[bytes]]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    git_b = os.fsencode(os.path.abspath(git_dir))
    fd = os.open(git_b, flags)
    records = []
    oid_tokens: set[bytes] = set()
    try:
        root_st = os.fstat(fd)
        for name_b in sorted(descriptor_roots):
            _scan_operation_entry(
                fd, git_b, name_b, name_b, root_dev=root_st.st_dev,
                records=records, oid_tokens=oid_tokens, oid_length=oid_length)
    finally:
        os.close(fd)
    records.sort(key=lambda item: (item["path_hex"], item["type"]))
    return records, oid_tokens


def _descriptor_marker(git_dir: str, rel: bytes) -> bool:
    path = os.path.join(os.fsencode(git_dir), rel)
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode):
        raise FinishError("operation_admin_invalid")
    return True


def _normalize_operation_original_ref(value: bytes) -> bytes | None:
    value = value.strip()
    if value.startswith(b"ref: "):
        value = value[len(b"ref: "):].strip()
    if not value or b"\x00" in value or b"\n" in value or b"\r" in value:
        return None
    if value.startswith(b"refs/heads/"):
        return value
    if value.startswith(b"refs/"):
        return value
    if re.fullmatch(rb"[A-Za-z0-9][A-Za-z0-9._/-]*", value):
        return b"refs/heads/" + value
    return None


def _read_operation_original_ref(binding: dict, groups: list[str]) -> str:
    candidates: set[bytes] = set()
    symbolic = _run_git_bound(binding, "symbolic-ref", "-q", "HEAD")
    if symbolic.returncode == 0 and not symbolic.stderr:
        value = symbolic.stdout.strip()
        if value:
            candidates.add(value)
    elif symbolic.returncode not in (0, 1):
        raise FinishError("operation_original_ref_unavailable")
    descriptor_candidates = []
    if "rebase-merge" in groups:
        descriptor_candidates.append(b"rebase-merge/head-name")
    if any(group in groups for group in ("rebase-apply", "am")):
        descriptor_candidates.append(b"rebase-apply/head-name")
    if "bisect" in groups:
        descriptor_candidates.append(b"BISECT_START")
    for rel in descriptor_candidates:
        path = os.path.join(os.fsencode(binding["git_dir"]), rel)
        try:
            raw = _read_regular_nofollow(os.fsdecode(path), limit=64 * 1024)
        except FileNotFoundError:
            continue
        normalized = _normalize_operation_original_ref(raw)
        if normalized is not None:
            candidates.add(normalized)
    validated = []
    for candidate in sorted(candidates):
        check = _run_git_bound(
            binding, "check-ref-format", os.fsdecode(candidate))
        if check.returncode != 0 or check.stdout or check.stderr:
            continue
        show = _run_git_bound(
            binding, "show-ref", "--hash", "--verify", os.fsdecode(candidate))
        if show.returncode == 0 and not show.stderr:
            validated.append(candidate)
        elif show.returncode not in (0, 1):
            raise FinishError("operation_original_ref_unavailable")
    if len(set(validated)) > 1:
        raise FinishError("operation_original_ref_ambiguous")
    return os.fsdecode(validated[0]) if validated else ""


def _operation_ref_records(
        binding: dict, groups: list[str], namespace_refs: list[dict],
        original_ref: str) -> list[dict]:
    records = list(namespace_refs)
    pseudo_names = sorted({
        name for group in groups for name in _OPERATION_PSEUDO_REFS[group]
    })
    for name in pseudo_names:
        proc = _run_git_bound(
            binding, "rev-parse", "--verify", "--quiet", name + "^{object}")
        if proc.returncode == 1 and not proc.stdout and not proc.stderr:
            continue
        if proc.returncode != 0 or proc.stderr:
            raise FinishError("operation_pseudo_ref_unavailable")
        oids = sorted(set(proc.stdout.decode("ascii", "strict").split()))
        if (not oids or any(
                re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", oid) is None
                for oid in oids)):
            raise FinishError("operation_pseudo_ref_malformed")
        records.append({
            "name_hex": name.encode("ascii").hex(),
            "oids": oids,
            "kind": "pseudo",
        })
    if original_ref:
        proc = _run_git_bound(
            binding, "show-ref", "--hash", "--verify", original_ref)
        if proc.returncode != 0 or proc.stderr:
            raise FinishError("operation_original_ref_unavailable")
        oid = proc.stdout.decode("ascii", "strict").strip()
        if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", oid) is None:
            raise FinishError("operation_original_ref_unavailable")
        records.append({
            "name_hex": os.fsencode(original_ref).hex(),
            "oid": oid,
            "kind": "original",
        })
    # NOTES_MERGE_REF contains a ref name, not an object id. Resolve it only through Git.
    if "notes-merge" in groups:
        raw = _read_regular_nofollow(
            os.path.join(binding["git_dir"], "NOTES_MERGE_REF"), limit=64 * 1024)
        note_ref_b = _normalize_operation_original_ref(raw)
        if note_ref_b is None:
            raise FinishError("operation_notes_ref_invalid")
        note_ref = os.fsdecode(note_ref_b)
        proc = _run_git_bound(
            binding, "show-ref", "--hash", "--verify", note_ref)
        if proc.returncode != 0 or proc.stderr:
            raise FinishError("operation_notes_ref_invalid")
        oid = proc.stdout.decode("ascii", "strict").strip()
        if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", oid) is None:
            raise FinishError("operation_notes_ref_invalid")
        records.append({
            "name_hex": note_ref_b.hex(), "oid": oid, "kind": "notes-target",
        })
    records.sort(key=lambda item: (
        item["name_hex"], item["kind"], item.get("oid", ""),
        tuple(item.get("oids") or [])))
    return records


def _index_stage_records(index_listing: bytes) -> list[dict]:
    records = []
    if not index_listing:
        return records
    if not index_listing.endswith(b"\x00"):
        raise FinishError("operation_index_listing_malformed")
    for value in index_listing[:-1].split(b"\x00"):
        meta, sep, path = value.partition(b"\t")
        fields = meta.split()
        if (not sep or not path or len(fields) != 3
                or fields[0] not in {b"100644", b"100755", b"120000", b"160000"}
                or re.fullmatch(rb"[0-9a-f]{40}|[0-9a-f]{64}", fields[1]) is None
                or fields[2] not in {b"0", b"1", b"2", b"3"}):
            raise FinishError("operation_index_listing_malformed")
        records.append({
            "mode": fields[0].decode("ascii"),
            "oid": fields[1].decode("ascii"),
            "stage": int(fields[2]),
            "path_hex": path.hex(),
        })
    return records


def _operation_object_closure(
        binding: dict, root_oids: set[str]) -> list[dict]:
    if not root_oids:
        raise FinishError("operation_object_roots_missing")
    roots = ("\n".join(sorted(root_oids)) + "\n").encode("ascii")
    revs = _bound_git_input(
        binding, "rev-list", "--objects", "--no-object-names", "--stdin",
        input_data=roots)
    if revs.returncode != 0 or revs.stderr:
        raise FinishError("operation_object_closure_unavailable")
    closure = sorted(set(revs.stdout.decode("ascii", "strict").split()))
    if (not closure or any(
            re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", oid) is None
            for oid in closure)):
        raise FinishError("operation_object_closure_malformed")
    batch = _bound_git_input(
        binding, "cat-file",
        "--batch-check=%(objectname) %(objecttype) %(objectsize)",
        input_data=("\n".join(closure) + "\n").encode("ascii"))
    if batch.returncode != 0 or batch.stderr:
        raise FinishError("operation_object_closure_unavailable")
    records = []
    for line in batch.stdout.decode("ascii", "strict").splitlines():
        fields = line.split()
        if (len(fields) != 3 or fields[0] not in closure
                or fields[1] not in {"blob", "tree", "commit", "tag"}
                or not fields[2].isdigit()):
            raise FinishError("operation_object_closure_malformed")
        records.append({
            "oid": fields[0], "type": fields[1], "size": int(fields[2]),
        })
    records.sort(key=lambda item: item["oid"])
    if [item["oid"] for item in records] != closure:
        raise FinishError("operation_object_closure_malformed")
    return records


def _operation_dependencies(status_bytes: bytes, index_listing: bytes) -> list[str]:
    dependencies = set()
    for xy, path_b, original_b in _parse_status_z(status_bytes):
        cls = _coarse_class(xy)
        if cls in {"untracked", "ignored"}:
            continue
        dependencies.add(path_b.rstrip(b"/").hex())
        if original_b is not None:
            dependencies.add(original_b.rstrip(b"/").hex())
    # The raw index is atomic with the operation. Every indexed path is therefore a dependency:
    # clean stage-0 content is reconstructed from the protected object closure, while conflicted
    # and modified worktree bytes are captured separately by Retain.
    for entry in _index_stage_records(index_listing):
        dependencies.add(entry["path_hex"])
    return sorted(value for value in dependencies if value)


def _operation_manifest_digest(value: dict) -> str:
    payload = {key: item for key, item in value.items() if key != "digest"}
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def _capture_operation_manifest(
        binding: dict, *, status_bytes: bytes, index_listing: bytes,
        raw_index: bytes) -> dict:
    format_proc = _run_git_bound(binding, "rev-parse", "--show-object-format")
    if format_proc.returncode != 0 or format_proc.stderr:
        raise FinishError("operation_object_format_unavailable")
    object_format = format_proc.stdout.decode("ascii", "strict").strip()
    if object_format not in _OID_FORMATS:
        raise FinishError("operation_object_format_unknown")
    presence = _operation_top_presence(binding["git_dir"])
    # Git leaves an empty NOTES_MERGE_WORKTREE directory after a successful `notes merge
    # --abort`. It is ordinary clean state, not an active operation. Prove that exact benign
    # shape descriptor-relatively; any content, companion marker, link, special, mount, or read
    # drift remains fail-safe operation state.
    notes_signals = {
        name for name in (
            b"NOTES_MERGE_REF", b"NOTES_MERGE_PARTIAL", b"NOTES_MERGE_WORKTREE")
        if name in presence
    }
    if notes_signals == {b"NOTES_MERGE_WORKTREE"}:
        residual_records, _residual_oids = _scan_operation_admin(
            binding["git_dir"], [b"NOTES_MERGE_WORKTREE"],
            oid_length=_OID_FORMATS[object_format])
        if (len(residual_records) == 1
                and residual_records[0].get("path_hex")
                == b"NOTES_MERGE_WORKTREE".hex()
                and residual_records[0].get("type") == "dir"):
            presence.pop(b"NOTES_MERGE_WORKTREE")
    namespace_refs = _operation_namespace_refs(binding)
    groups = _classify_operation_groups(presence, namespace_refs)
    selected_roots = sorted({
        name for group in groups for name in _OPERATION_OPTIONAL_BY_GROUP[group]
        if name in presence
    })
    unexplained = (
        set(presence)
        - set(selected_roots)
        - ({b"ORIG_HEAD"} if not groups else set())
    )
    if unexplained:
        raise FinishError("operation_unknown")
    if not groups:
        payload = {
            "schema": SCHEMA_OPERATION_MANIFEST,
            "classification_version": OPERATION_CLASSIFICATION_VERSION,
            "active": False,
            "groups": [],
            "admin_roots_hex": [],
            "admin_records": [],
            "refs": [],
            "raw_index": {
                "size": len(raw_index),
                "sha256": hashlib.sha256(raw_index).hexdigest(),
            },
            "index_entries": [],
            "dependencies_hex": [],
            "object_format": object_format,
            "object_roots": [],
            "object_closure": [],
            "original_ref": "",
            "head_symbolic_ref": "",
            "head_oid": "",
        }
    else:
        if "rebase-apply" in groups:
            applying = _descriptor_marker(binding["git_dir"], b"rebase-apply/applying")
            rebasing = _descriptor_marker(binding["git_dir"], b"rebase-apply/rebasing")
            if applying == rebasing:
                raise FinishError("operation_ambiguous")
            if applying:
                groups = ["am" if group == "rebase-apply" else group for group in groups]
                selected_roots = sorted({
                    name for group in groups for name in _OPERATION_OPTIONAL_BY_GROUP[group]
                    if name in presence
                })
        admin_records, content_oids = _scan_operation_admin(
            binding["git_dir"], selected_roots,
            oid_length=_OID_FORMATS[object_format])
        original_ref = _read_operation_original_ref(binding, groups)
        refs = _operation_ref_records(
            binding, groups, namespace_refs, original_ref)
        symbolic = _run_git_bound(binding, "symbolic-ref", "-q", "HEAD")
        if symbolic.returncode == 0 and not symbolic.stderr:
            head_symbolic_ref = os.fsdecode(symbolic.stdout.strip())
        elif symbolic.returncode == 1 and not symbolic.stdout and not symbolic.stderr:
            head_symbolic_ref = ""
        else:
            raise FinishError("operation_head_identity_unavailable")
        head_oid_proc = _run_git_bound(
            binding, "rev-parse", "--verify", "HEAD^{object}")
        if head_oid_proc.returncode != 0 or head_oid_proc.stderr:
            raise FinishError("operation_head_identity_unavailable")
        head_oid = head_oid_proc.stdout.decode("ascii", "strict").strip()
        if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", head_oid) is None:
            raise FinishError("operation_head_identity_unavailable")
        stage_records = _index_stage_records(index_listing)
        root_oids = {
            value.decode("ascii")
            for value in content_oids
        }
        root_oids.update(entry["oid"] for entry in stage_records)
        for ref in refs:
            if "oid" in ref:
                root_oids.add(ref["oid"])
            root_oids.update(ref.get("oids") or [])
        # Full-length hexadecimal text in patches/messages is not necessarily an object id.
        # Retain only roots Git can resolve as objects.
        existing_roots = set()
        for oid in sorted(root_oids):
            probe = _run_git_bound(
                binding, "cat-file", "-e", oid + "^{object}")
            if probe.returncode == 0 and not probe.stdout and not probe.stderr:
                existing_roots.add(oid)
            elif probe.returncode not in (0, 1, 128):
                raise FinishError("operation_object_probe_unavailable")
        closure = _operation_object_closure(binding, existing_roots)
        payload = {
            "schema": SCHEMA_OPERATION_MANIFEST,
            "classification_version": OPERATION_CLASSIFICATION_VERSION,
            "active": True,
            "groups": sorted(groups),
            "admin_roots_hex": [name.hex() for name in selected_roots],
            "admin_records": admin_records,
            "refs": refs,
            "raw_index": {
                "size": len(raw_index),
                "sha256": hashlib.sha256(raw_index).hexdigest(),
            },
            "index_entries": stage_records,
            "dependencies_hex": _operation_dependencies(
                status_bytes, index_listing),
            "object_format": object_format,
            "object_roots": sorted(existing_roots),
            "object_closure": closure,
            "original_ref": original_ref,
            "head_symbolic_ref": head_symbolic_ref,
            "head_oid": head_oid,
        }
    return {
        **payload,
        "digest": _operation_manifest_digest(payload),
    }


def operation_markers(git_dir: str) -> list:
    """Compatibility diagnostic only; inventory authority uses the full manifest above."""
    presence = _operation_top_presence(os.path.abspath(git_dir))
    labels = []
    if b"MERGE_HEAD" in presence:
        labels.append("merge")
    if any(name in presence for name in (b"CHERRY_PICK_HEAD", b"REVERT_HEAD", b"sequencer")):
        labels.append("sequence")
    if b"rebase-merge" in presence:
        labels.append("rebase-merge")
    if b"rebase-apply" in presence:
        labels.append("rebase-apply")
    if b"BISECT_START" in presence:
        labels.append("bisect")
    if b"NOTES_MERGE_REF" in presence:
        labels.append("notes-merge")
    return sorted(labels)


def _parse_status_z(data: bytes) -> list:
    """Parse `git status --porcelain=v1 -z`. NUL-safe. For rename/copy (X or Y in R/C) the entry
    is followed by a second NUL-terminated path; we capture BOTH and lstat whichever exists on
    disk, so field-order subtleties cannot mislead classification. Returns [(xy, path_bytes,
    orig_bytes|None)]. Raises FinishError on a malformed record (unknown evidence -> refuse)."""
    entries: list = []
    parts = data.split(b"\x00")
    i, n = 0, len(parts)
    while i < n:
        rec = parts[i]
        i += 1
        if not rec:
            continue  # trailing empty field after the final NUL
        if len(rec) < 3 or rec[2:3] != b" ":
            raise FinishError("malformed git status record")
        xy = rec[:2].decode("ascii", "replace")
        path = rec[3:]
        orig = None
        if "R" in xy or "C" in xy:
            if i >= n:
                raise FinishError("truncated rename/copy record")
            orig = parts[i]
            i += 1
            # An EMPTY rename/copy source is a truncated/malformed record (a real rename always names
            # its origin). Refuse (safe direction) rather than lstat'ing the empty path -> the ROOT.
            if orig == b"":
                raise FinishError("empty rename/copy source (malformed/truncated record)")
        entries.append((xy, path, orig))
    return entries


def _coarse_class(xy: str) -> str:
    if xy == "??":
        return "untracked"
    if xy == "!!":
        return "ignored"
    if xy in _CONFLICT_CODES:
        return "conflicted"
    x, y = xy[0], xy[1]
    if x in ("R",) or y in ("R",):
        return "renamed"
    if x in ("C",) or y in ("C",):
        return "copied"
    if x != " " and x != "?":
        return "staged"
    if y == "M":
        return "modified"
    if y == "D":
        return "deleted"
    if y == "T":
        return "typechange"
    return "unknown"


def _segments(relpath: str) -> list:
    return [seg for seg in relpath.split("/") if seg]


def _is_cruft(relpath: str, cls: str) -> bool:
    """EXACT path-segment cruft match (never substring). Applies ONLY to untracked/ignored
    entries — tracked/staged/modified/conflicted work is NEVER hidden."""
    if cls not in ("untracked", "ignored"):
        return False
    for seg in _segments(relpath.rstrip("/")):
        if seg in CRUFT_SEGMENTS:
            return True
    base = os.path.basename(relpath.rstrip("/"))
    if base.endswith(CRUFT_BASENAME_SUFFIXES):
        return True
    return False


def _looks_secret(relpath: str) -> bool:
    for seg in _segments(relpath.rstrip("/")):
        low = seg.lower()
        if low in _SECRET_SEGMENT_EXACT:
            return True
        if low.endswith(_SECRET_SEGMENT_SUFFIXES):
            return True
        if low == ".env" or low.startswith(".env."):
            return True
        for sub in _SECRET_SUBSTRINGS:
            if sub in low:
                return True
    return False


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_selected_rel(value: str) -> str:
    if not isinstance(value, str) or not value or os.path.isabs(value):
        raise FinishError("unsafe selected path")
    rel = os.path.normpath(value)
    if rel in ("", ".") or rel == ".." or rel.startswith(".." + os.sep):
        raise FinishError("unsafe selected path")
    return rel


def _snapshot_fs_entry(root: str, rel: str, out: list) -> None:
    """Capture one selected path recursively without following links.

    The shape is shared by the protected-Retain writer and the kernel suppression verifier.
    Directory descendants are complete, so an added/removed child invalidates equality.
    """
    rel = _safe_selected_rel(rel)
    full = os.path.join(root, rel)
    try:
        st = os.lstat(full)
    except FileNotFoundError:
        out.append({"path": rel, "type": "absent"})
        return
    mode = stat.S_IMODE(st.st_mode)
    if stat.S_ISLNK(st.st_mode):
        target = os.readlink(full)
        record = {"path": rel, "type": "symlink", "mode": mode}
        if os.path.isabs(target):
            resolved = os.path.realpath(full)
            if resolved == root or resolved.startswith(root + os.sep):
                record["target_kind"] = "internal_absolute"
                record["target_root_relative"] = os.path.relpath(resolved, root)
            else:
                record["target_kind"] = "external_absolute"
                record["target"] = target
        else:
            record["target_kind"] = "relative"
            record["target"] = target
        out.append(record)
        return
    if stat.S_ISREG(st.st_mode):
        out.append({"path": rel, "type": "file", "mode": mode,
                    "size": st.st_size, "sha256": _sha256_file(full)})
        return
    if not stat.S_ISDIR(st.st_mode):
        raise FinishError("unsupported selected path type")
    out.append({"path": rel, "type": "dir", "mode": mode})
    try:
        children = sorted(os.scandir(full), key=lambda item: os.fsencode(item.name))
    except OSError as exc:
        raise FinishError(f"selected directory scan failed:{exc.errno}") from exc
    for child in children:
        _snapshot_fs_entry(root, os.path.join(rel, child.name), out)


def selected_snapshot(root: str, selected_paths: list) -> dict:
    """Canonical complete snapshot for protected Retain source-equality.

    Reads only explicitly selected paths and their recursively selected directory descendants.
    Git status and index bytes are preserved exactly; filesystem records bind modes, contents,
    links, absence, and the complete no-follow subtree.
    """
    root_c = canon(root)
    if not isinstance(selected_paths, list) or not selected_paths:
        raise FinishError("selected paths required")
    rels = sorted({_safe_selected_rel(value) for value in selected_paths},
                  key=lambda value: os.fsencode(value))
    try:
        selected_git_dir = validated_git_binding(
            root_c, allow_primary=True)["git_dir"]
    except (FinishError, OSError, TypeError, ValueError):
        raise FinishError(INDEX_VISIBILITY_REFUSAL) from None
    _index_visibility_preflight(root_c, selected_git_dir)
    status = _git_bytes(
        root_c, "-c", "core.quotepath=false",
        "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false", "status",
        "--porcelain=v1", "-z", "--untracked-files=all",
        "--ignored=matching", "--", *rels)
    index = _git_bytes(
        root_c, "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
        "ls-files", "--stage", "-z", "--", *rels)
    if status.returncode != 0:
        raise FinishError("selected snapshot status failed")
    if index.returncode != 0:
        raise FinishError("selected snapshot index failed")
    entries: list = []
    for rel in rels:
        _snapshot_fs_entry(root_c, rel, entries)
    entries.sort(key=lambda item: (os.fsencode(item["path"]), item["type"]))
    return {
        "schema": SCHEMA_SELECTED_SNAPSHOT,
        "selected_paths": rels,
        "status_hex": status.stdout.hex(),
        "index_hex": index.stdout.hex(),
        "entries": entries,
    }


def _retained_signatures(root: str, operation: dict | None = None) -> set:
    """Return only committed marker-v1 rows whose typed source state still byte-matches.

    Markerless v1 artifacts remain restorable by the consumer as legacy data, but cannot suppress
    source rows: only an exact committed marker bound to the true-manifest digest is trusted here.
    """
    base = os.path.join(awa_state_dir(), "protected-retain")
    signatures: set = set()
    try:
        children = sorted(os.scandir(base), key=lambda item: item.name)
    except OSError:
        return signatures
    root_c = canon(root)
    for child in children:
        if (not child.is_dir(follow_symlinks=False)
                or re.fullmatch(r"retain-[0-9a-f]{32}", child.name) is None):
            continue
        manifest = os.path.join(child.path, "manifest.json")
        try:
            manifest_data = _read_regular_nofollow(
                manifest, limit=64 * 1024 * 1024)
            doc = json.loads(manifest_data.decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError, FinishError):
            continue
        if (not isinstance(doc, dict) or doc.get("schema") != "awa_protected_retain/v1"
                or doc.get("artifact_id") != child.name
                or doc.get("protected") is not True or doc.get("restore_proven") is not True
                or doc.get("publication_protocol") != RETAIN_PUBLICATION_PROTOCOL
                or canon(str(doc.get("source") or "")) != root_c):
            continue
        digest = hashlib.sha256(manifest_data).hexdigest()
        committed = os.path.join(
            base, f".{child.name}.publication.committed.json")
        pending = os.path.join(
            base, f".{child.name}.publication.pending.json")
        staging = os.path.join(base, f".{child.name}.staging")
        rollback = os.path.join(
            base, f".{child.name}.publication-tombstone")

        def valid_marker(path: str) -> bool:
            try:
                marker_data = _read_regular_nofollow(path, limit=64 * 1024)
                marker = json.loads(marker_data.decode("utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError, FinishError):
                return False
            return (
                isinstance(marker, dict)
                and set(marker) == RETAIN_PUBLICATION_KEYS
                and marker.get("schema") == SCHEMA_RETAIN_PUBLICATION
                and marker.get("artifact_id") == child.name
                and marker.get("manifest_sha256") == digest
            )

        committed_present = os.path.lexists(committed)
        committed_valid = valid_marker(committed)
        pending_valid = valid_marker(pending)
        # A valid committed marker is authoritative. Otherwise only a sole final payload with a
        # valid pending witness and no contradictory committed/staging/rollback state is safely
        # recoverable; no reader ever suppresses from an ambiguous candidate set.
        safely_recoverable = (
            not committed_present
            and pending_valid
            and not os.path.lexists(staging)
            and not os.path.lexists(rollback)
        )
        if not committed_valid and not safely_recoverable:
            continue
        operation_state = doc.get("operation_state")
        operation_groups: list[str] = []
        if operation_state is not None:
            if (not committed_valid or doc.get("operation_abort_proven") is not True
                    or not isinstance(operation, dict)
                    or not isinstance(operation_state, dict)
                    or operation_state.get("schema") != "awa-retain-operation-state/v1"
                    or operation_state.get("operation_digest") != operation.get("digest")
                    or operation_state.get("operation_manifest") != operation):
                continue
            groups = operation_state.get("selected_groups")
            if (not isinstance(groups, list) or not groups
                    or len(groups) != len(set(groups))
                    or any(group not in (operation.get("groups") or [])
                           for group in groups)):
                continue
            payload_valid = True
            for metadata, expected in (
                    (operation_state.get("raw_index"), "git-state/index"),
                    (operation_state.get("object_pack"), "git-state/objects.pack")):
                if (not isinstance(metadata, dict)
                        or metadata.get("path") != expected
                        or type(metadata.get("size")) is not int
                        or metadata["size"] < 0
                        or re.fullmatch(
                            r"[0-9a-f]{64}",
                            str(metadata.get("sha256") or "")) is None):
                    payload_valid = False
                    break
                try:
                    data = _read_regular_nofollow(
                        os.path.join(child.path, expected),
                        limit=max(1, metadata["size"] + 1))
                except (OSError, FinishError):
                    payload_valid = False
                    break
                if (len(data) != metadata["size"]
                        or hashlib.sha256(data).hexdigest() != metadata["sha256"]):
                    payload_valid = False
                    break
            admin_root = os.path.join(child.path, "git-state", "admin")
            if payload_valid:
                for item in operation.get("admin_records") or []:
                    try:
                        rel_b = bytes.fromhex(item["path_hex"])
                        if (not rel_b or rel_b.startswith(b"/")
                                or any(part in {b"", b".", b".."}
                                       for part in rel_b.split(b"/"))):
                            raise ValueError
                        path = os.path.join(os.fsencode(admin_root), rel_b)
                        st = os.lstat(path)
                        if item.get("type") == "dir":
                            payload_valid = (
                                stat.S_ISDIR(st.st_mode) and not stat.S_ISLNK(st.st_mode))
                        elif item.get("type") == "file":
                            data = _read_regular_nofollow(
                                os.fsdecode(path),
                                limit=max(1, int(item.get("size", -1)) + 1))
                            payload_valid = (
                                len(data) == item.get("size")
                                and hashlib.sha256(data).hexdigest() == item.get("sha256"))
                        else:
                            payload_valid = False
                    except (OSError, ValueError, TypeError, FinishError):
                        payload_valid = False
                    if not payload_valid:
                        break
            if not payload_valid:
                continue
            operation_groups = groups
        snapshot = doc.get("selected_snapshot")
        selected = doc.get("selected_status")
        if (not isinstance(snapshot, dict)
                or snapshot.get("schema") != SCHEMA_SELECTED_SNAPSHOT
                or not isinstance(selected, list)):
            continue
        try:
            current = selected_snapshot(root_c, snapshot.get("selected_paths"))
        except (FinishError, OSError, TypeError, ValueError):
            continue
        if current != snapshot:
            continue
        for group in operation_groups:
            signatures.add(("operation", group, operation["digest"]))
        for row in selected:
            if not isinstance(row, dict):
                continue
            paths_hex = row.get("paths_hex")
            if (isinstance(paths_hex, list) and all(isinstance(x, str) for x in paths_hex)
                    and isinstance(row.get("code"), str)
                    and isinstance(row.get("class"), str)):
                signatures.add((row["code"], row["class"], tuple(sorted(paths_hex))))
    return signatures


# Fixed metadata->sentence template table. Descriptions are a PURE function of metadata (git
# status code, extension, path role, size, kind) — the model authors NOTHING and file contents
# are NEVER read.
_TEMPLATES = {
    "staged": "A change you have staged but not committed.",
    "modified": "A tracked file you have modified but not committed.",
    "deleted": "A tracked file you have deleted but not committed.",
    "renamed": "A tracked file you have renamed but not committed.",
    "copied": "A tracked file you have copied but not committed.",
    "typechange": "A tracked file whose type changed but is not committed.",
    "conflicted": "A file with an unresolved merge conflict.",
    "untracked_file": "A new file that is not tracked by version control.",
    "untracked_dir": "A new directory of files that is not tracked by version control.",
    "ignored_file": "A git-ignored local file.",
    "ignored_dir": "A git-ignored local directory.",
    "untracked_empty_dir_tree": "A new directory tree containing only empty directories.",
    "ignored_empty_dir_tree": "A git-ignored directory tree containing only empty directories.",
    "symlink": "A symbolic link that points inside this workspace.",
    "secret": "A file whose name or type suggests it may hold credentials or secrets; its contents are not displayed.",
    "unknown": "A local change that would be discarded.",
}


def _describe(cls: str, relpath: str, is_dir: bool, is_symlink: bool) -> tuple:
    """Return (template_id, sentence). Deterministic, one sentence, metadata-only, content-safe."""
    if _looks_secret(relpath):
        return "secret", _TEMPLATES["secret"]
    if is_symlink:
        return "symlink", _TEMPLATES["symlink"]
    if cls == "untracked":
        tid = "untracked_dir" if is_dir else "untracked_file"
        return tid, _TEMPLATES[tid]
    if cls == "ignored":
        tid = "ignored_dir" if is_dir else "ignored_file"
        return tid, _TEMPLATES[tid]
    return cls, _TEMPLATES.get(cls, _TEMPLATES["unknown"])


# Bidirectional / line / paragraph control codepoints that must never reach a renderer as-is.
_BIDI_CODEPOINTS = frozenset(
    [0x200E, 0x200F, 0x061C, 0x2028, 0x2029]
    + list(range(0x202A, 0x202F))   # LRE RLE PDF LRO RLO (+ 0x202F NNBSP)
    + list(range(0x2066, 0x206A))   # LRI RLI FSI PDI
)
_MARKDOWN_META = set("`*_[]()#|<>\\~")


def escape_for_display(text: str) -> str:
    """Escape control chars, bidirectional Unicode, and Markdown metacharacters so a path or
    description is rendered as DATA, never as instructions. Deterministic. Phase 2 wraps this."""
    out = []
    for ch in text:
        cp = ord(ch)
        if cp < 0x20 or 0x7F <= cp <= 0x9F or cp in _BIDI_CODEPOINTS:
            out.append(f"\\u{cp:04x}")
        elif 0xDC80 <= cp <= 0xDCFF:
            # os.fsdecode's surrogateescape representation of one raw non-UTF-8 path byte.
            out.append(f"\\x{cp - 0xDC00:02x}")
        elif 0xD800 <= cp <= 0xDFFF:
            out.append(f"\\u{cp:04x}")
        elif ch in _MARKDOWN_META:
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def _decode_path(path_bytes: bytes) -> str:
    """Decode a raw git path to a display string (surrogateescape keeps invalid bytes reversible)."""
    return path_bytes.decode("utf-8", "surrogateescape")


def _norm_abs_bytes(root: str, relpath_bytes: bytes) -> bytes:
    """Normalized absolute physical path as BYTES (locale-independent canonical sort key). Does NOT
    resolve symlinks (an escaping link is refused separately); os.path.normpath on the joined path."""
    root_b = os.fsencode(root)
    joined = os.path.join(root_b, relpath_bytes.rstrip(b"/"))
    return os.path.normpath(joined)


def _stat_identity(st: os.stat_result) -> tuple:
    """Fields that must remain stable across one no-follow object read."""
    return (
        st.st_dev, st.st_ino, st.st_mode, st.st_size,
        getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000)),
        getattr(st, "st_ctime_ns", int(st.st_ctime * 1_000_000_000)),
    )


def _relative_lstat(path_b: bytes, *, parent_fd: int | None,
                    name_b: bytes | None) -> os.stat_result:
    if parent_fd is None:
        return os.lstat(path_b)
    return os.stat(name_b, dir_fd=parent_fd, follow_symlinks=False)


def _regular_object(path_b: bytes, rel_b: bytes, before: os.stat_result, *,
                    parent_fd: int | None, name_b: bytes | None) -> dict:
    """Hash one regular file without following links and reject in-read drift."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = (
            os.open(path_b, flags)
            if parent_fd is None
            else os.open(name_b, flags, dir_fd=parent_fd)
        )
    except OSError as exc:
        raise FinishError(f"proof_file_open:{exc.errno}") from exc
    digest = hashlib.sha256()
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or _stat_identity(opened) != _stat_identity(before):
            raise FinishError("proof_file_open_drift")
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        after_fd = os.fstat(fd)
        if _stat_identity(after_fd) != _stat_identity(opened):
            raise FinishError("proof_file_read_drift")
    except OSError as exc:
        raise FinishError(f"proof_file_read:{exc.errno}") from exc
    finally:
        os.close(fd)
    try:
        after_path = _relative_lstat(
            path_b, parent_fd=parent_fd, name_b=name_b)
    except OSError as exc:
        raise FinishError(f"proof_file_restat:{exc.errno}") from exc
    if _stat_identity(after_path) != _stat_identity(before):
        raise FinishError("proof_file_path_drift")
    return {
        "path_hex": rel_b.hex(),
        "type": "file",
        "mode": stat.S_IMODE(before.st_mode),
        "size": before.st_size,
        "sha256": digest.hexdigest(),
    }


def _capture_tree_object(path_b: bytes, rel_b: bytes, *, root_dev: int,
                         root_real_b: bytes, objects: list,
                         parent_fd: int | None = None,
                         name_b: bytes | None = None) -> None:
    """Capture one complete filesystem object without following symlinks."""
    try:
        before = _relative_lstat(
            path_b, parent_fd=parent_fd, name_b=name_b)
    except OSError as exc:
        raise FinishError(f"proof_lstat:{exc.errno}") from exc
    if before.st_dev != root_dev:
        raise FinishError("mount_boundary")
    try:
        if rel_b and os.path.ismount(path_b):
            raise FinishError("mount_boundary")
    except OSError as exc:
        raise FinishError(f"mount_check:{exc.errno}") from exc
    mode = stat.S_IMODE(before.st_mode)
    if stat.S_ISLNK(before.st_mode):
        try:
            target = (
                os.readlink(path_b)
                if parent_fd is None
                else os.readlink(name_b, dir_fd=parent_fd)
            )
            after = _relative_lstat(
                path_b, parent_fd=parent_fd, name_b=name_b)
        except OSError as exc:
            raise FinishError(f"proof_link_read:{exc.errno}") from exc
        if _stat_identity(after) != _stat_identity(before):
            raise FinishError("proof_link_drift")
        target_b = target if isinstance(target, bytes) else os.fsencode(target)
        real = os.path.realpath(path_b)
        sep = os.fsencode(os.sep)
        if not (real == root_real_b or real.startswith(root_real_b + sep)):
            raise FinishError("symlink_escape")
        objects.append({
            "path_hex": rel_b.hex(), "type": "symlink", "mode": mode,
            "size": before.st_size, "target_hex": target_b.hex(),
        })
        return
    if stat.S_ISREG(before.st_mode):
        objects.append(_regular_object(
            path_b, rel_b, before, parent_fd=parent_fd, name_b=name_b))
        return
    if not stat.S_ISDIR(before.st_mode):
        if (stat.S_ISSOCK(before.st_mode) or stat.S_ISFIFO(before.st_mode)
                or stat.S_ISCHR(before.st_mode) or stat.S_ISBLK(before.st_mode)):
            raise FinishError("special_file")
        raise FinishError("unknown_file_type")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        directory_fd = (
            os.open(path_b, flags)
            if parent_fd is None
            else os.open(name_b, flags, dir_fd=parent_fd)
        )
    except OSError as exc:
        raise FinishError(f"proof_directory_open:{exc.errno}") from exc
    try:
        opened = os.fstat(directory_fd)
        if not stat.S_ISDIR(opened.st_mode) or _stat_identity(opened) != _stat_identity(before):
            raise FinishError("proof_directory_open_drift")
        try:
            child_names = [
                item.name if isinstance(item.name, bytes) else os.fsencode(item.name)
                for item in os.scandir(directory_fd)
            ]
        except OSError as exc:
            raise FinishError(f"proof_directory_scan:{exc.errno}") from exc
        child_names.sort()
        names = set(child_names)
        # Any `.git` below the linked worktree's own top-level administrative file is a nested
        # repository/submodule. Also reject a canonical bare-repository shape.
        if rel_b and b".git" in names:
            raise FinishError("nested_repo")
        if rel_b and {b"HEAD", b"objects", b"refs"} <= names:
            raise FinishError("nested_repo")
        objects.append({
            "path_hex": rel_b.hex(), "type": "dir", "mode": mode, "size": before.st_size,
        })
        for child_name_b in child_names:
            child_rel = child_name_b if not rel_b else os.path.join(rel_b, child_name_b)
            # The linked worktree's own `.git` administrative file is expected and included in the
            # proof; every deeper `.git` is rejected by the parent-directory check above.
            _capture_tree_object(
                os.path.join(path_b, child_name_b), child_rel, root_dev=root_dev,
                root_real_b=root_real_b, objects=objects,
                parent_fd=directory_fd, name_b=child_name_b)
        after_fd = os.fstat(directory_fd)
        if _stat_identity(after_fd) != _stat_identity(opened):
            raise FinishError("proof_directory_read_drift")
    except OSError as exc:
        raise FinishError(f"proof_directory_read:{exc.errno}") from exc
    finally:
        os.close(directory_fd)
    try:
        after = _relative_lstat(
            path_b, parent_fd=parent_fd, name_b=name_b)
    except OSError as exc:
        raise FinishError(f"proof_directory_restat:{exc.errno}") from exc
    if _stat_identity(after) != _stat_identity(before):
        raise FinishError("proof_directory_path_drift")


def _capture_complete_tree(root: str) -> list:
    """Private canonical proof of every physical object under the worktree root."""
    root_c = canon(root)
    root_b = os.fsencode(root_c)
    try:
        root_st = os.lstat(root_b)
    except OSError as exc:
        raise FinishError(f"root_unstat:{exc.errno}") from exc
    if not stat.S_ISDIR(root_st.st_mode):
        raise FinishError("root_not_directory")
    objects: list = []
    _capture_tree_object(
        root_b, b"", root_dev=root_st.st_dev,
        root_real_b=os.path.realpath(root_b), objects=objects)
    objects.sort(key=lambda item: (item["path_hex"], item["type"]))
    return objects


def _proof_inputs(root: str, git_dir: str) -> tuple[bytes, bytes, bytes, dict, list]:
    binding = validated_git_binding(root, git_dir=git_dir)
    _index_visibility_preflight(root, git_dir)
    raw_index = _read_index_stable(binding["index_file"])
    status = _git_bytes(
        root, "-c", "core.quotepath=false",
        "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
        "status", "--porcelain=v1", "-z",
        "--untracked-files=all", "--ignored=matching")
    if status.returncode != 0:
        raise FinishError("git_status_failed")
    index = _git_bytes(
        root, "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
        "ls-files", "--stage", "-z")
    if index.returncode != 0:
        raise FinishError("git_index_failed")
    operation = _capture_operation_manifest(
        binding, status_bytes=status.stdout, index_listing=index.stdout,
        raw_index=raw_index)
    objects = _capture_complete_tree(root)
    raw_index_after = _read_index_stable(binding["index_file"])
    if raw_index_after != raw_index:
        raise FinishError("git_state_drift")
    operation_after = _capture_operation_manifest(
        binding, status_bytes=status.stdout, index_listing=index.stdout,
        raw_index=raw_index_after)
    if operation_after != operation:
        raise FinishError("operation_state_drift")
    return status.stdout, index.stdout, raw_index, operation, objects


def _index_paths(index_bytes: bytes) -> list[bytes]:
    """Strict NUL-safe paths from ``git ls-files --stage -z`` output."""
    if not index_bytes:
        return []
    if not index_bytes.endswith(b"\x00"):
        raise FinishError("malformed git index listing")
    paths = []
    for record in index_bytes[:-1].split(b"\x00"):
        meta, sep, path = record.partition(b"\t")
        fields = meta.split()
        if (not sep or not path or len(fields) != 3
                or fields[0] not in {b"100644", b"100755", b"120000", b"160000"}
                or re.fullmatch(rb"[0-9a-f]{40}|[0-9a-f]{64}", fields[1]) is None
                or fields[2] not in {b"0", b"1", b"2", b"3"}):
            raise FinishError("malformed git index listing")
        paths.append(path)
    return paths


def _empty_directory_rows(root: str, objects: list, index_bytes: bytes,
                          _status_rows: list) -> list:
    """Canonical shallow rows for physical directory-only untracked/ignored trees."""
    directory_objects = {
        bytes.fromhex(item["path_hex"]): item
        for item in objects
        if item.get("type") == "dir" and item.get("path_hex")
    }
    if not directory_objects:
        return []
    non_directory_paths = [
        bytes.fromhex(item["path_hex"])
        for item in objects
        if item.get("path_hex") and item.get("type") != "dir"
    ]
    tracked_ancestors = set()
    for path in _index_paths(index_bytes):
        cursor = path
        while b"/" in cursor:
            cursor = cursor.rsplit(b"/", 1)[0]
            tracked_ancestors.add(cursor)
        if path in directory_objects:
            tracked_ancestors.add(path)
    eligible = []
    for path in sorted(directory_objects, key=lambda value: (value.count(b"/"), value)):
        if path in tracked_ancestors:
            continue
        prefix = path + b"/"
        if any(value.startswith(prefix) for value in non_directory_paths):
            continue
        if any(path == parent or path.startswith(parent + b"/") for parent in eligible):
            continue
        eligible.append(path)

    rows = []
    for path in eligible:
        rel = _decode_path(path)
        probe = _git_bytes(
            root, "check-ignore", "--quiet", "--no-index", "--",
            rel.rstrip("/") + "/")
        if probe.returncode == 0 and not probe.stdout and not probe.stderr:
            cls, code = "ignored", "!!"
        elif probe.returncode == 1 and not probe.stdout and not probe.stderr:
            cls, code = "untracked", "??"
        else:
            raise FinishError("empty_directory_ignore_unavailable")
        members = [
            {"path_hex": member.hex(), "mode": directory_objects[member]["mode"]}
            for member in sorted(directory_objects)
            if member == path or member.startswith(path + b"/")
        ]
        template_id = f"{cls}_empty_dir_tree"
        rows.append({
            "code": code,
            "class": cls,
            "kind": "empty_dir_tree",
            "size": 0,
            "hidden": bool(_is_cruft(rel, cls)),
            "template_id": template_id,
            "sentence": _TEMPLATES[template_id],
            "path": rel,
            "display": escape_for_display(rel),
            "paths_hex": [path.hex()],
            "tree_members": members,
            "commit_eligible": False,
            "retain_eligible": True,
            "_sort": _norm_abs_bytes(root, path),
        })
    return rows


def build_inventory(root: str, git_dir: str) -> dict:
    """Canonical inventory of every at-risk work item under `root`. Enumerated NUL-safe via git,
    classified with no-follow lstat. Returns a dict with:
      safe (bool), refuse_reason (str|""), entries (sorted list), markers (sorted list).
    A traversal/mount/nested-repo/special-file/symlink-escape risk sets safe=False (the item does
    NOT enter the discard set); unknown git evidence also refuses."""
    root_c = canon(root)
    try:
        status_bytes, index_bytes, raw_index, operation, objects = _proof_inputs(
            root_c, git_dir)
        # A second complete capture makes additions/removals/rewrites during reconnaissance a
        # deterministic refusal rather than a mixed-time manifest.
        (status_after, index_after, raw_index_after,
         operation_after, objects_after) = _proof_inputs(root_c, git_dir)
        _index_visibility_preflight(root_c, git_dir)
        if (status_after != status_bytes or index_after != index_bytes
                or raw_index_after != raw_index):
            raise FinishError("git_state_drift")
        if operation_after != operation:
            raise FinishError("operation_state_drift")
        if objects_after != objects:
            raise FinishError("filesystem_drift")
        raw = _parse_status_z(status_bytes)
        empty_directory_rows = _empty_directory_rows(
            root_c, objects, index_bytes, raw)
    except FinishError as exc:
        reason = str(exc).split(":", 1)[0]
        return {"safe": False, "refuse_reason": reason, "entries": [], "markers": [],
                "objects": [], "status_hex": "", "index_hex": "",
                "raw_index_hex": "", "operation_manifest": {},
                "operation_digest": ""}

    object_map = {item["path_hex"]: item for item in objects}
    empty_directory_roots = {
        bytes.fromhex(row["paths_hex"][0]) for row in empty_directory_rows
    }
    entries: list = []
    absent_objects: dict[str, dict] = {}
    for xy, path_b, orig_b in raw:
        cls = _coarse_class(xy)
        path_bytes_list = [path_b] + ([orig_b] if orig_b is not None else [])
        primary_b = path_b
        primary_disp = _decode_path(path_b)
        primary_object = None
        for cand in path_bytes_list:
            normalized = cand.rstrip(b"/")
            key = normalized.hex()
            obj = object_map.get(key)
            if obj is not None:
                primary_b = normalized
                primary_disp = _decode_path(normalized)
                primary_object = obj
                break
            absent_objects[key] = {
                "path_hex": key, "type": "absent", "mode": 0, "size": -1,
            }
        deletion_bearing = (
            cls == "deleted"
            or xy in {"DD", "UD", "DU"}
            or (len(xy) == 2 and (xy[0] == "D" or xy[1] == "D"))
        )
        if primary_object is None and not deletion_bearing:
            return {"safe": False, "refuse_reason": "status_object_missing",
                    "entries": [], "markers": [], "objects": [],
                    "status_hex": "", "index_hex": ""}
        kind = primary_object["type"] if primary_object is not None else "absent"
        is_dir = kind == "dir"
        is_symlink = kind == "symlink"
        size = primary_object["size"] if primary_object is not None else -1
        rel_for_class = primary_disp
        if (cls in {"untracked", "ignored"}
                and any(
                    primary_b == tree_root
                    or primary_b.startswith(tree_root + b"/")
                    for tree_root in empty_directory_roots)):
            continue
        hidden = _is_cruft(rel_for_class, cls)
        tid, sentence = _describe(cls, rel_for_class, is_dir, is_symlink)
        sort_key = _norm_abs_bytes(root_c, primary_b)
        entries.append({
            "code": xy,
            "class": cls,
            "kind": kind,
            "size": size,
            "hidden": bool(hidden),
            "template_id": tid,
            "sentence": sentence,
            "path": primary_disp,
            "display": escape_for_display(primary_disp),
            "paths_hex": sorted(pb.hex() for pb in path_bytes_list),
            # Git intentionally excludes ignored paths from ordinary adds.  Finish never uses
            # ``git add -f``: every visible ignored row is Retain-only, including directories and
            # secret-named files, while ordinary tracked/untracked rows remain commit-eligible.
            "commit_eligible": cls != "ignored",
            "retain_eligible": True,
            "_sort": sort_key,
        })

    entries.extend(empty_directory_rows)
    status_class_by_path = {}
    for xy, path_b, original_b in raw:
        cls = _coarse_class(xy)
        status_class_by_path[path_b.rstrip(b"/").hex()] = cls
        if original_b is not None:
            status_class_by_path[original_b.rstrip(b"/").hex()] = cls
    if operation.get("active"):
        dependencies = list(operation.get("dependencies_hex") or [])
        secret_dependencies = any(
            _looks_secret(_decode_path(bytes.fromhex(value)))
            for value in dependencies)
        ignored_dependencies = any(
            status_class_by_path.get(value) == "ignored"
            for value in dependencies)
        for group in operation.get("groups") or []:
            display, sentence = _OPERATION_GROUP_COPY[group]
            entries.append({
                "code": "OP",
                "class": "operation",
                "kind": "operation",
                "size": sum(
                    int(item.get("size") or 0)
                    for item in operation.get("admin_records") or []
                    if item.get("type") == "file"),
                "hidden": False,
                "template_id": "operation",
                "sentence": sentence,
                "path": display,
                "display": display,
                "paths_hex": [],
                "operation_group": group,
                "operation_digest": operation["digest"],
                "operation_manifest": operation,
                "dependency_paths_hex": dependencies,
                "contains_secret_dependencies": secret_dependencies,
                "contains_ignored_dependencies": ignored_dependencies,
                "operation_atomic": True,
                "commit_eligible": False,
                "retain_eligible": True,
                "_sort": os.fsencode(root_c) + b"\x00operation/" + group.encode("ascii"),
            })
    objects.extend(absent_objects.values())
    objects.sort(key=lambda item: (item["path_hex"], item["type"]))
    entries.sort(key=lambda e: (e["_sort"], e["paths_hex"]))
    retained = _retained_signatures(root_c, operation)
    for e in entries:
        e.pop("_sort", None)
        signature = (
            ("operation", e["operation_group"], e["operation_digest"])
            if e.get("template_id") == "operation"
            else (e["code"], e["class"], tuple(sorted(e["paths_hex"])))
        )
        e["retained"] = signature in retained
    return {
        "safe": True, "refuse_reason": "", "entries": entries,
        "markers": list(operation.get("groups") or []), "objects": objects,
        "status_hex": status_bytes.hex(), "index_hex": index_bytes.hex(),
        "raw_index_hex": raw_index.hex(),
        "operation_manifest": operation,
        "operation_digest": operation.get("digest", ""),
    }


# ---- stable fingerprint -----------------------------------------------------------------
def heartbeat_membership(root: str, confirming_key: str, *,
                         branch: str, common_dir: str,
                         lock_held: bool = False) -> list:
    """Sorted set of OTHER sessions' heartbeat keys (the confirming session is EXCLUDED so its own
    refresh never perturbs the fingerprint). A NEW other session appearing between preview and
    execute changes this set -> fingerprint mismatch -> refuse. A corrupt record yields a
    deterministic sentinel (the execute-time session gate independently blocks a corrupt record)."""
    roots = _roots_module()
    evidence = roots.finish_session_evidence(
        root, confirming_session_key=confirming_key,
        branch=branch, common_dir=common_dir, lock_held=lock_held)
    if not evidence.get("ok"):
        if evidence.get("reason") == "session_lock_busy":
            raise LockBusy("common directory lock busy")
        return ["__corrupt__"]
    return list(evidence.get("membership") or [])


def compute_fingerprint(inv: dict, *, root: str, git_dir: str, common_dir: str,
                        branch: str, head: str, membership: list,
                        root_incarnation: dict | None = None,
                        git_dir_incarnation: dict | None = None) -> str:
    """SHA-256 over a canonicalized (sort_keys, compact, ensure_ascii) representation of the
    inventory + root/branch/HEAD/marker/membership facts + the cruft-allowlist & warning versions.
    Paths are represented by their raw-byte HEX so the fingerprint is byte-identical across OS
    directory orderings and locales, with NO wall-clock, PID, or randomness."""
    if root_incarnation is None or git_dir_incarnation is None:
        root_incarnation, git_dir_incarnation = capture_physical_incarnations(
            root, git_dir)
    manifest = []
    for e in inv["entries"]:
        manifest.append({
            "p": e["paths_hex"],
            "code": e["code"],
            "class": e["class"],
            "kind": e["kind"],
            "size": e["size"],
            "tid": e["template_id"],
            "hidden": bool(e["hidden"]),
            "retained": bool(e.get("retained")),
            "commit_eligible": bool(e.get("commit_eligible", True)),
            "retain_eligible": bool(e.get("retain_eligible", True)),
            "tree_members": sorted(
                e.get("tree_members") or [],
                key=lambda item: (item.get("path_hex", ""), item.get("mode", 0))),
            "operation_group": e.get("operation_group", ""),
            "operation_digest": e.get("operation_digest", ""),
            "dependency_paths_hex": sorted(e.get("dependency_paths_hex") or []),
            "operation_atomic": bool(e.get("operation_atomic")),
            "contains_secret_dependencies": bool(
                e.get("contains_secret_dependencies")),
            "contains_ignored_dependencies": bool(
                e.get("contains_ignored_dependencies")),
        })
    manifest.sort(key=lambda m: (m["p"], m["code"]))
    payload = {
        "schema": SCHEMA_CHALLENGE,
        "versions": {
            "fingerprint": INVENTORY_FINGERPRINT_VERSION,
            "operation": OPERATION_CLASSIFICATION_VERSION,
            "cruft": CRUFT_ALLOWLIST_VERSION,
            "warning": WARNING_VERSION,
            "retain": RETAIN_CLASSIFICATION_VERSION,
        },
        "root": canon(root),
        "git_dir": os.path.abspath(git_dir),
        "common_dir": os.path.abspath(common_dir),
        "branch": branch or "",
        "head": head or "",
        "root_incarnation": root_incarnation,
        "git_dir_incarnation": git_dir_incarnation,
        "markers": sorted(inv["markers"]),
        "hb_members": sorted(membership),
        "git_status_hex": inv.get("status_hex", ""),
        "git_index_hex": inv.get("index_hex", ""),
        "raw_index_hex": inv.get("raw_index_hex", ""),
        "operation_manifest": inv.get("operation_manifest") or {},
        "manifest": manifest,
        # Private only: raw relative paths, types, modes, sizes, regular-file hashes, and link
        # targets for every physical worktree object (plus explicit absent/deleted paths).
        "objects": sorted(
            inv.get("objects") or [],
            key=lambda item: (item.get("path_hex", ""), item.get("type", ""))),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("ascii")).hexdigest()


# ---- content-addressed pending challenge ------------------------------------------------
def _conversation_key(conversation_id: str) -> str:
    return hashlib.sha256((conversation_id or "").encode("utf-8")).hexdigest()[:24]


def challenge_path(conversation_id: str) -> str:
    return os.path.join(finish_dir(), f"challenge-{_conversation_key(conversation_id)}.json")


def generation_state_path(conversation_id: str, nonce: str, generation: int) -> str:
    """Nonce+generation-bound terminal marker. Presence is fail-safe authority consumption."""
    nonce_key = hashlib.sha256(str(nonce).encode("utf-8")).hexdigest()[:16]
    return os.path.join(
        finish_dir(),
        f"generation-{_conversation_key(conversation_id)}-{int(generation)}-{nonce_key}.json",
    )


def _generation_state_record(*, transition: str, conversation_id: str, nonce: str,
                             generation: int, root: str, common_dir: str,
                             session_key_value: str) -> dict:
    if transition not in GENERATION_TRANSITIONS:
        raise ValueError("invalid generation transition")
    if not isinstance(nonce, str) or not nonce or type(generation) is not int or generation < 1:
        raise ValueError("invalid generation identity")
    now_epoch, now_iso = _now_pair()
    return {
        "schema": SCHEMA_GENERATION_STATE,
        "transition": transition,
        "conversation_id": conversation_id or "",
        "nonce": nonce,
        "generation": generation,
        "root": canon(root),
        "common_dir": os.path.abspath(common_dir),
        "session_key": session_key_value,
        "created_at_epoch": now_epoch,
        "created_at": now_iso,
    }


def _read_generation_state_raw(conversation_id: str, nonce: str, generation: int) -> tuple:
    """Return (record, status). Any present malformed marker remains authority-consuming."""
    try:
        path = generation_state_path(conversation_id, nonce, generation)
    except (TypeError, ValueError):
        return None, "invalid"
    try:
        _durability_module().adopt_visible(path)
        with open(path, encoding="utf-8") as fh:
            rec = json.load(fh)
    except FileNotFoundError:
        return None, "absent"
    except (OSError, json.JSONDecodeError):
        return None, "malformed"
    if (not isinstance(rec, dict) or set(rec) != GENERATION_STATE_KEYS
            or rec.get("schema") != SCHEMA_GENERATION_STATE
            or rec.get("conversation_id") != (conversation_id or "")
            or rec.get("nonce") != nonce
            or rec.get("generation") != generation
            or rec.get("transition") not in GENERATION_TRANSITIONS
            or not isinstance(rec.get("root"), str) or not rec.get("root")
            or rec.get("root") != canon(rec.get("root"))
            or not isinstance(rec.get("common_dir"), str) or not rec.get("common_dir")
            or rec.get("common_dir") != os.path.abspath(rec.get("common_dir"))
            or not isinstance(rec.get("session_key"), str) or not rec.get("session_key")
            or _timestamp_pair_state(
                rec.get("created_at"), rec.get("created_at_epoch"))[0] == "invalid"):
        return None, "malformed"
    timestamp_state, epoch = _timestamp_pair_state(
        rec.get("created_at"), rec.get("created_at_epoch"))
    if timestamp_state == "legacy_skew" and epoch is not None:
        rec = dict(rec)
        rec["created_at"] = _iso_from_epoch(epoch)
        return rec, "legacy_skew"
    return rec, "ok"


def read_generation_state(conversation_id: str, nonce: str, generation: int, *,
                          lock_held: bool = False) -> tuple:
    """Return a validated marker, normalizing only the known one-second legacy writer skew."""
    rec, status = _read_generation_state_raw(conversation_id, nonce, generation)
    if status != "legacy_skew" or rec is None:
        return rec, status

    def migrate_locked() -> tuple:
        current, current_status = _read_generation_state_raw(
            conversation_id, nonce, generation)
        if current_status == "legacy_skew" and current is not None:
            _write_private(
                generation_state_path(conversation_id, nonce, generation),
                json.dumps(current, indent=2, sort_keys=True) + "\n")
            return current, "ok"
        return current, current_status

    try:
        if lock_held:
            return migrate_locked()
        with common_dir_lock(rec["common_dir"], blocking=True, timeout=5.0):
            return migrate_locked()
    except (LockBusy, OSError):
        return None, "malformed"


def generation_state_status(conversation_id: str, nonce: str, generation: int, *,
                            lock_held: bool = False) -> str:
    """Map a terminal marker to a public inert status; malformed presence fails safe consumed."""
    rec, status = read_generation_state(
        conversation_id, nonce, generation, lock_held=lock_held)
    if status == "absent":
        return "live"
    if status != "ok" or rec is None:
        return "consumed"
    return "cancelled" if rec["transition"] == "cancelled" else "consumed"


def _transition_generation(*, transition: str, conversation_id: str, nonce: str,
                           generation: int, root: str, common_dir: str,
                           session_key_value: str) -> dict:
    """Atomically claim/cancel one generation without adding another lock ABI.

    O_EXCL is the one-use arbiter. A partial/malformed created file is still inert, so a write or
    later unlink failure can never resurrect the selected generation.
    """
    try:
        rec = _generation_state_record(
            transition=transition, conversation_id=conversation_id, nonce=nonce,
            generation=generation, root=root, common_dir=common_dir,
            session_key_value=session_key_value)
        path = generation_state_path(conversation_id, nonce, generation)
    except (TypeError, ValueError) as exc:
        return {"ok": False, "inert": False, "created": False,
                "reason": "generation_identity_invalid", "detail": str(exc)}
    _ensure_dir(os.path.dirname(path))
    data = (json.dumps(rec, indent=2, sort_keys=True) + "\n").encode("utf-8")
    try:
        _durability_module().create_private_exclusive(
            path, data, file_mode=FILE_MODE, dir_mode=DIR_MODE)
    except FileExistsError:
        existing, status = read_generation_state(conversation_id, nonce, generation)
        if status == "ok" and existing is not None and existing.get("transition") == transition:
            return {"ok": True, "inert": True, "created": False,
                    "reason": "already_" + transition}
        return {"ok": False, "inert": True, "created": False,
                "reason": "generation_already_consumed"}
    except OSError as exc:
        visible = os.path.lexists(path)
        return {
            "ok": False, "inert": visible, "created": visible,
            "reason": (
                "generation_state_write_failed" if visible
                else "generation_state_create_failed"),
            "detail": repr(exc),
        }
    return {"ok": True, "inert": True, "created": True,
            "reason": transition}


def _max_generation_state(conversation_id: str) -> int:
    """Preserve monotonic generations even after the challenge itself was cleared."""
    directory = finish_dir()
    if not os.path.isdir(directory):
        return 0
    key = re.escape(_conversation_key(conversation_id))
    pattern = re.compile(rf"^generation-{key}-([1-9][0-9]*)-[0-9a-f]{{16}}\.json$")
    highest = 0
    try:
        names = os.listdir(directory)
    except OSError:
        return 0
    for name in names:
        match = pattern.fullmatch(name)
        if match:
            highest = max(highest, int(match.group(1)))
    return highest


# ---- crash-durable finish-removal transaction -------------------------------------------
def _operation_identity_payload(*, root: str, git_dir: str, common_dir: str, branch: str,
                                head: str, conversation_id: str, nonce: str,
                                generation: int, session_id: str, session_key_value: str,
                                boot_id_value: str, install_id_value: str,
                                root_incarnation_value: dict, git_dir_incarnation_value: dict,
                                fingerprint: str, claim: str,
                                branch_disposition_value: dict, discard_count: int) -> dict:
    return {
        "root": canon(root),
        "git_dir": os.path.abspath(git_dir),
        "common_dir": os.path.abspath(common_dir),
        "branch": branch,
        "head": head,
        "conversation_id": conversation_id,
        "nonce": nonce,
        "generation": generation,
        "session_id": session_id,
        "session_key": session_key_value,
        "boot_id": boot_id_value,
        "install_id": install_id_value,
        "root_incarnation": root_incarnation_value,
        "git_dir_incarnation": git_dir_incarnation_value,
        "fingerprint": fingerprint,
        "claim": claim,
        "branch_disposition": branch_disposition_value,
        "discard_count": discard_count,
    }


def _operation_binding_payload(identity: dict) -> dict:
    """Bind destructive authority without mutable reconciliation result fields."""
    payload = {
        key: identity[key]
        for key in (
            "root", "git_dir", "common_dir", "branch", "head", "conversation_id",
            "nonce", "generation", "session_id", "session_key", "boot_id",
            "fingerprint", "claim", "branch_disposition", "discard_count")
    }
    for key in ("install_id", "root_incarnation", "git_dir_incarnation"):
        if key in identity:
            payload[key] = identity[key]
    return payload


def finish_operation_id(**identity) -> str:
    blob = json.dumps(
        _operation_binding_payload(identity),
        sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("ascii")).hexdigest()


def removal_journal_path(operation_id: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", operation_id or ""):
        raise ValueError("invalid finish operation id")
    return os.path.join(finish_dir(), f"removal-{operation_id}.json")


def _journal_identity(rec: dict) -> dict:
    identity = {
        "root": rec["root"], "git_dir": rec["git_dir"], "common_dir": rec["common_dir"],
        "branch": rec["branch"], "head": rec["head"],
        "conversation_id": rec["conversation_id"], "nonce": rec["nonce"],
        "generation": rec["generation"], "session_id": rec["session_id"],
        "session_key": rec["session_key"], "boot_id": rec["boot_id"],
        "fingerprint": rec["fingerprint"], "claim": rec["claim"],
        "branch_disposition": rec["branch_disposition"],
        "discard_count": rec["discard_count"],
    }
    for key in ("install_id", "root_incarnation", "git_dir_incarnation"):
        if key in rec:
            identity[key] = rec[key]
    return identity


def _valid_branch_disposition(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    action = value.get("action")
    if action not in {"retain", "retain_local_only", "delete_eligible"}:
        return False
    expected = {"action", "reason"}
    if action == "retain_local_only":
        expected.add("local_only_count")
    if set(value) != expected or not isinstance(value.get("reason"), str):
        return False
    if action == "retain_local_only":
        return type(value.get("local_only_count")) is int and value["local_only_count"] > 0
    return True


def _validate_removal_journal(rec: object, operation_id: str) -> bool:
    keys = set(rec) if isinstance(rec, dict) else set()
    current_shape = keys == REMOVAL_JOURNAL_KEYS
    legacy_shape = keys == LEGACY_REMOVAL_JOURNAL_KEYS
    if (not isinstance(rec, dict) or not (current_shape or legacy_shape)
            or rec.get("schema") != SCHEMA_REMOVAL_JOURNAL
            or rec.get("operation_id") != operation_id
            or rec.get("phase") not in REMOVAL_PHASES
            or not isinstance(rec.get("root"), str) or not rec.get("root")
            or rec.get("root") != canon(rec.get("root"))
            or not isinstance(rec.get("git_dir"), str) or not rec.get("git_dir")
            or rec.get("git_dir") != os.path.abspath(rec.get("git_dir"))
            or not isinstance(rec.get("common_dir"), str) or not rec.get("common_dir")
            or rec.get("common_dir") != os.path.abspath(rec.get("common_dir"))
            or not isinstance(rec.get("branch"), str) or not rec.get("branch")
            or not isinstance(rec.get("head"), str)
            or re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", rec.get("head")) is None
            or not isinstance(rec.get("conversation_id"), str)
            or not isinstance(rec.get("nonce"), str) or not rec.get("nonce")
            or type(rec.get("generation")) is not int or rec.get("generation") < 1
            or not isinstance(rec.get("session_id"), str)
            or not isinstance(rec.get("session_key"), str) or not rec.get("session_key")
            or rec.get("session_key") != _roots_module().session_key(rec.get("session_id"))
            or not isinstance(rec.get("boot_id"), str) or not rec.get("boot_id")
            or (current_shape and (
                not isinstance(rec.get("install_id"), str) or not rec.get("install_id")
                or not _valid_incarnation(rec.get("root_incarnation"))
                or not _valid_incarnation(rec.get("git_dir_incarnation"))))
            or not isinstance(rec.get("fingerprint"), str)
            or re.fullmatch(r"[0-9a-f]{64}", rec.get("fingerprint")) is None
            or rec.get("claim") not in {"direct", "close_claimed"}
            or not _valid_branch_disposition(rec.get("branch_disposition"))
            or type(rec.get("discard_count")) is not int or rec.get("discard_count") < 0
            or rec.get("branch_action") not in {
                "", "retained", "retained_local_only", "deleted",
                "delete_failed", "delete_error"}
            or not isinstance(rec.get("cleanup_warnings"), list)
            or not all(isinstance(item, str) for item in rec.get("cleanup_warnings"))
            or type(rec.get("receipt_committed")) is not bool
            or type(rec.get("created_at_epoch")) is not int
            or rec.get("created_at_epoch") < 1
            or type(rec.get("updated_at_epoch")) is not int
            or rec.get("updated_at_epoch") < rec.get("created_at_epoch")
            or (rec.get("phase") == "prepared"
                and (rec.get("branch_action") or rec.get("receipt_committed")))
            or (rec.get("phase") == "finalized"
                and (not rec.get("branch_action") or not rec.get("receipt_committed")))):
        return False
    try:
        return finish_operation_id(**_journal_identity(rec)) == operation_id
    except (KeyError, TypeError, ValueError):
        return False


def read_removal_journal(operation_id: str) -> tuple:
    try:
        path = removal_journal_path(operation_id)
    except ValueError:
        return None, "invalid"
    try:
        _durability_module().adopt_visible(path)
        with open(path, encoding="utf-8") as fh:
            rec = json.load(fh)
    except FileNotFoundError:
        return None, "absent"
    except (OSError, json.JSONDecodeError):
        return None, "malformed"
    return (rec, "ok") if _validate_removal_journal(rec, operation_id) else (None, "malformed")


def _write_removal_journal(rec: dict) -> None:
    if not _validate_removal_journal(rec, rec.get("operation_id", "")):
        raise FinishError("removal_journal_invalid")
    _write_private(
        removal_journal_path(rec["operation_id"]),
        json.dumps(rec, indent=2, sort_keys=True) + "\n")


def _prepare_removal_journal_locked(*, identity: dict) -> dict:
    operation_id = finish_operation_id(**identity)
    existing, status = read_removal_journal(operation_id)
    if status == "ok" and existing is not None:
        return existing
    if status != "absent":
        raise FinishError("removal_journal_" + status)
    now = _now_epoch()
    rec = {
        "schema": SCHEMA_REMOVAL_JOURNAL,
        "operation_id": operation_id,
        "phase": "prepared",
        **identity,
        "branch_action": "",
        "cleanup_warnings": [],
        "receipt_committed": False,
        "created_at_epoch": now,
        "updated_at_epoch": now,
    }
    _write_removal_journal(rec)
    return rec


def _worktree_registration(common_dir: str, root: str) -> tuple:
    """Return (known, exact_registration_count) using local Git administration only."""
    try:
        proc = _run_git_admin(
            common_dir, "worktree", "list", "--porcelain", "-z")
    except Exception:  # noqa: BLE001
        return False, 0
    if proc.returncode != 0:
        return False, 0
    target = canon(root)
    count = 0
    try:
        for field in proc.stdout.split(b"\x00"):
            if not field.startswith(b"worktree "):
                continue
            raw = field[len(b"worktree "):]
            if raw and canon(os.fsdecode(raw)) == target:
                count += 1
    except (OSError, UnicodeError, ValueError):
        return False, 0
    return True, count


def _physical_removal_state(rec: dict) -> dict:
    try:
        os.lstat(rec["root"])
        root_present = True
    except FileNotFoundError:
        root_present = False
    except OSError:
        return {"state": "uncertain", "reason": "root_presence_unavailable"}
    known, registrations = _worktree_registration(rec["common_dir"], rec["root"])
    if not known:
        return {"state": "uncertain", "reason": "registration_unavailable"}
    if not root_present and registrations == 0:
        return {"state": "removed", "reason": "root_absent_and_unregistered"}
    if root_present and registrations == 1:
        if not {
                "root_incarnation", "git_dir_incarnation"} <= set(rec):
            # Legacy journals can prove only a completed disappearance. Presence cannot distinguish
            # the original worktree from a same-path replacement, so never clear or resume it.
            return {"state": "uncertain", "reason": "legacy_present_identity_unavailable"}
        try:
            current_root, current_git = capture_physical_incarnations(
                rec["root"], rec["git_dir"])
        except FinishError:
            return {"state": "uncertain", "reason": "physical_identity_unavailable"}
        if (current_root != rec["root_incarnation"]
                or current_git != rec["git_dir_incarnation"]):
            return {"state": "uncertain", "reason": "physical_incarnation_changed"}
        return {"state": "present", "reason": "original_root_present_and_registered"}
    return {"state": "uncertain", "reason": "physical_registration_disagree"}


def _prove_prepared_root_unchanged_locked(rec: dict) -> dict:
    """Prove a prepared operation never altered the exact operation-bound workspace.

    This is intentionally the same content proof used for authorization: status, the real index,
    every filesystem object, operation markers, protected-Retain suppression, and heartbeat
    membership all fold into the fingerprint.  Only byte equality permits a prepared journal to
    be cleared as a definitely-not-removed attempt.
    """
    try:
        before = capture_physical_incarnations(rec["root"], rec["git_dir"])
        if before != (rec["root_incarnation"], rec["git_dir_incarnation"]):
            return {"state": "uncertain", "reason": "physical_incarnation_changed"}
        target = resolve_target(rec["root"])
        if any(target[key] != rec[key] for key in (
                "root", "git_dir", "common_dir", "branch", "head")):
            return {"state": "uncertain", "reason": "operation_target_changed"}
        known, registrations = _worktree_registration(rec["common_dir"], rec["root"])
        if not known or registrations != 1:
            return {"state": "uncertain", "reason": "physical_registration_disagree"}
        inv = build_inventory(rec["root"], rec["git_dir"])
        if not inv.get("safe"):
            return {"state": "uncertain", "reason": "operation_proof_unavailable"}
        membership = heartbeat_membership(
            rec["root"], rec["session_key"], branch=rec["branch"],
            common_dir=rec["common_dir"], lock_held=True)
        after = capture_physical_incarnations(rec["root"], rec["git_dir"])
        if after != before:
            return {"state": "uncertain", "reason": "physical_incarnation_changed"}
        known_after, registrations_after = _worktree_registration(
            rec["common_dir"], rec["root"])
        if not known_after or registrations_after != 1:
            return {"state": "uncertain", "reason": "physical_registration_disagree"}
        fingerprint = compute_fingerprint(
            inv, root=rec["root"], git_dir=rec["git_dir"],
            common_dir=rec["common_dir"], branch=rec["branch"], head=rec["head"],
            membership=membership, root_incarnation=after[0],
            git_dir_incarnation=after[1])
        if not hmac.compare_digest(fingerprint, rec["fingerprint"]):
            return {"state": "uncertain", "reason": "operation_proof_mismatch"}
        return {"state": "intact", "reason": "operation_fingerprint_unchanged"}
    except (FinishError, LockBusy, OSError, subprocess.SubprocessError, TypeError, ValueError):
        return {"state": "uncertain", "reason": "operation_proof_unavailable"}


def _operation_removal_state_locked(rec: dict) -> dict:
    """Classify a worktree-remove result from physical state, never from its return code."""
    physical = _physical_removal_state(rec)
    if physical["state"] != "present":
        return physical
    if rec.get("phase") != "prepared":
        return {"state": "uncertain", "reason": "removed_root_recreated"}
    return _prove_prepared_root_unchanged_locked(rec)


def _sync_removed_worktree_namespaces(rec: dict) -> None:
    """Adopt the two namespace removals Git made before any branch decision."""
    durability = _durability_module()
    for removed_name in (rec["root"], rec["git_dir"]):
        parent = os.path.dirname(removed_name)
        while not os.path.lexists(parent):
            higher = os.path.dirname(parent)
            if higher == parent:
                raise FinishError("removal_namespace_parent_absent")
            parent = higher
        st = os.lstat(parent)
        if not stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode):
            raise FinishError("removal_namespace_parent_invalid")
        durability.sync_directory(parent)


def _git_ref_backend(common_dir: str) -> str:
    probe = _run_git_admin(
        common_dir, "rev-parse", "--show-ref-format", text=True)
    value = probe.stdout.strip() if probe.returncode == 0 else ""
    if value in {"files", "reftable"}:
        return value
    configured = _run_git_admin(
        common_dir, "config", "--get", "extensions.refStorage", text=True)
    if configured.returncode == 1 and not configured.stdout and not configured.stderr:
        return "files"
    value = configured.stdout.strip() if configured.returncode == 0 else ""
    if value in {"files", "reftable"}:
        return value
    raise FinishError("git_ref_backend_unknown")


def _sync_existing_git_namespace(path: str) -> None:
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return
    if stat.S_ISLNK(st.st_mode):
        raise FinishError("git_ref_namespace_link")
    durability = _durability_module()
    if stat.S_ISREG(st.st_mode):
        durability.sync_regular(path)
    elif stat.S_ISDIR(st.st_mode):
        durability.sync_directory(path)
    else:
        raise FinishError("git_ref_namespace_special")


def _sync_git_ref_namespaces(common_dir: str, branch: str) -> None:
    """Persist the actual files/reftable backend touched by branch deletion."""
    common = os.path.abspath(common_dir)
    backend = _git_ref_backend(common)
    if backend == "reftable":
        table_dir = os.path.join(common, "reftable")
        list_path = os.path.join(table_dir, "tables.list")
        raw = _read_regular_nofollow(list_path, limit=64 * 1024 * 1024)
        for line in raw.splitlines():
            if (not line or b"/" in line or line in {b".", b".."}
                    or b"\x00" in line):
                raise FinishError("git_reftable_list_invalid")
            table = os.path.join(os.fsencode(table_dir), line)
            _sync_existing_git_namespace(os.fsdecode(table))
        _sync_existing_git_namespace(list_path)
        _sync_existing_git_namespace(table_dir)
        _durability_module().sync_directory(common)
        return

    ref = os.path.join(common, "refs", "heads", branch)
    reflog = os.path.join(common, "logs", "refs", "heads", branch)
    common_prefix = common.rstrip(os.sep) + os.sep
    for candidate in (ref, reflog, os.path.join(common, "packed-refs")):
        absolute = os.path.abspath(candidate)
        if not absolute.startswith(common_prefix):
            raise FinishError("git_ref_namespace_escape")
        _sync_existing_git_namespace(absolute)
    directories = set()
    for candidate in (os.path.dirname(ref), os.path.dirname(reflog)):
        cursor = candidate
        while cursor.startswith(common_prefix):
            directories.add(cursor)
            if cursor == common:
                break
            cursor = os.path.dirname(cursor)
    for directory in sorted(
            directories, key=lambda value: (value.count(os.sep), os.fsencode(value)),
            reverse=True):
        _sync_existing_git_namespace(directory)
    _durability_module().sync_directory(common)


def _finalize_branch_locked(rec: dict) -> str:
    try:
        action = rec["branch_disposition"]["action"]
        if action == "retain_local_only":
            return "retained_local_only"
        if action != "delete_eligible":
            return "retained"
        ref = f"refs/heads/{rec['branch']}"
        probe = _run_git_admin(
            rec["common_dir"], "show-ref", "--quiet", "--verify", ref, text=True)
    except Exception:  # noqa: BLE001
        return "delete_error"
    if probe.returncode == 1:
        # Desired postcondition is already true. This also makes recovery idempotent if power was
        # lost after update-ref succeeded but before the removed-phase journal was rewritten.
        try:
            _sync_git_ref_namespaces(rec["common_dir"], rec["branch"])
        except Exception:  # noqa: BLE001
            return ""
        return "deleted"
    if probe.returncode != 0:
        return "delete_error"
    try:
        deleted = _run_git_admin(
            rec["common_dir"],
            "-c", "core.fsync=reference",
            "-c", "core.fsyncMethod=fsync",
            "update-ref", "-d", ref, rec["head"], text=True)
    except Exception:  # noqa: BLE001
        return "delete_error"
    if deleted.returncode != 0:
        return "delete_failed"
    try:
        _sync_git_ref_namespaces(rec["common_dir"], rec["branch"])
    except Exception:  # noqa: BLE001
        return ""
    return "deleted"


_VALID_BRANCH_ACTIONS = frozenset({
    "retained", "retained_local_only", "deleted", "delete_failed", "delete_error",
})


def _durable_branch_action(rec: dict) -> str:
    """Return only branch truth validated from this operation's durable journal."""
    try:
        durable, status = read_removal_journal(rec["operation_id"])
    except Exception:  # noqa: BLE001
        return ""
    if status != "ok" or durable is None:
        return ""
    action = durable.get("branch_action")
    return action if action in _VALID_BRANCH_ACTIONS else ""


def _closed_removed_branch_action(rec: dict, in_memory_action: str) -> str:
    """Prefer the durably-journaled branch result; when the journal is silent, fall back only to
    THIS operation's genuine in-process action. An unknown action stays unknown — a `retained`
    default is never invented — so a removed root is never narrated with a fabricated branch fate.
    (The durable journal always PRECEDES the in-process value when both are present.)"""
    durable = _durable_branch_action(rec)
    if durable:
        return durable
    return in_memory_action if in_memory_action in _VALID_BRANCH_ACTIONS else ""


def _cleanup_challenge_locked(rec: dict) -> tuple[bool, str]:
    challenge, status = _read_challenge_raw(rec["conversation_id"])
    if status == "absent":
        return True, "absent"
    if status != "ok" or challenge is None:
        return False, "challenge_cleanup_failed"
    if (challenge.get("nonce") != rec["nonce"]
            or challenge.get("generation") != rec["generation"]):
        return True, "superseded"
    cleared = _delete_challenge_raw_cas(
        rec["conversation_id"], expected_nonce=rec["nonce"],
        expected_generation=rec["generation"])
    return (True, "cleared") if cleared else (False, "challenge_cleanup_failed")


def _removed_message(rec: dict) -> str:
    return (
        f"removed the current worktree (discarded {rec['discard_count']} item(s)); "
        f"branch {rec['branch_action']} "
        f"(branch decision: {rec['branch_disposition'].get('reason', 'unknown')})")


def _removed_fallback_from_branch_truth(
        rec: dict, base: dict, in_memory_action: str) -> dict:
    """Build a physical-removal fallback without ever inventing branch retention."""
    action = _closed_removed_branch_action(rec, in_memory_action)
    if not action:
        return {
            "outcome": "uncertain",
            "reason": "removal_branch_action_uncertain",
            "message": "the workspace was removed but branch finalization could not be classified",
        }
    rec["branch_action"] = action
    result = dict(base)
    result["branch_action"] = action
    result["message"] = _removed_message(rec)
    warnings = sorted(set(result.get("state_cleanup_warnings") or []))
    result["state_cleanup_warnings"] = warnings
    if warnings:
        result["message"] += (
            "; WARNING: local finish state cleanup was incomplete: "
            + ",".join(warnings))
    return result


def _write_removed_receipt_locked(rec: dict) -> bool:
    roots = _roots_module()
    roots.write_receipt(
        disposition="removed", reason="finish_removed",
        message=_removed_message(rec), path=rec["root"], branch=rec["branch"],
        head=rec["head"], common_dir=rec["common_dir"], finish_current=True,
        authorization_nonce=rec["nonce"], discard_count=rec["discard_count"],
        branch_action=rec["branch_action"],
        challenge_fingerprint=rec["fingerprint"],
        operation_id=rec["operation_id"])
    return True


def _clear_pre_removal_journal_locked(rec: dict) -> bool:
    """Clear a prepared operation only after dual signals prove removal never began."""
    path = removal_journal_path(rec["operation_id"])
    try:
        _durability_module().durable_unlink(path, missing_ok=True)
    except OSError:
        return False
    return not os.path.lexists(path)


def _reconcile_removal_journal_locked(rec: dict) -> dict:
    physical = _operation_removal_state_locked(rec)
    if physical["state"] == "intact":
        if not _clear_pre_removal_journal_locked(rec):
            return {
                "outcome": "uncertain", "reason": "pre_removal_journal_cleanup_failed",
                "phase": rec["phase"],
            }
        return {
            "outcome": "not_removed", "reason": "pre_removal_interrupted",
            "operation_id": rec["operation_id"], "phase": rec["phase"],
        }
    if physical["state"] != "removed":
        return {
            "outcome": "uncertain", "reason": physical["reason"],
            "phase": rec["phase"],
        }

    warnings = set(rec.get("cleanup_warnings") or [])
    try:
        _sync_removed_worktree_namespaces(rec)
    except Exception:  # noqa: BLE001
        return {
            "outcome": "uncertain",
            "reason": "removal_namespace_sync_failed",
            "phase": rec["phase"],
        }
    if rec["phase"] == "prepared":
        rec["phase"] = "removed"
        rec["updated_at_epoch"] = _now_epoch()
        try:
            _write_removal_journal(rec)
        except Exception:  # noqa: BLE001 — physical removal is already dual-signal confirmed
            return {
                "outcome": "uncertain",
                "reason": "removed_state_write_failed",
                "phase": "prepared",
            }

    in_memory_branch_action = rec.get("branch_action") or _finalize_branch_locked(rec)
    if not in_memory_branch_action:
        return {
            "outcome": "uncertain",
            "reason": "branch_namespace_sync_failed",
            "phase": rec["phase"],
        }
    rec["branch_action"] = in_memory_branch_action
    durable_branch_action = _durable_branch_action(rec)
    branch_state_committed = durable_branch_action == in_memory_branch_action
    if not branch_state_committed:
        # The branch result is part of the durable removed state and therefore must precede the
        # idempotent receipt. Otherwise a transient branch error plus a failed finalized write
        # could let a retry change the receipt identity after one receipt already exists.
        rec["cleanup_warnings"] = sorted(warnings)
        rec["updated_at_epoch"] = _now_epoch()
        try:
            _write_removal_journal(rec)
        except Exception:  # noqa: BLE001
            return {
                "outcome": "uncertain",
                "reason": "branch_state_write_failed",
                "phase": rec["phase"],
            }
        durable_branch_action = _durable_branch_action(rec)
        branch_state_committed = durable_branch_action == in_memory_branch_action
    if not branch_state_committed:
        return {
            "outcome": "uncertain",
            "reason": "branch_state_write_failed",
            "phase": rec["phase"],
        }
    rec["branch_action"] = _closed_removed_branch_action(
        rec, in_memory_branch_action)

    # Everything after branch finalization is best-effort state hygiene. No cleanup exception may
    # escape and replace the already-known branch result with an invented fallback.
    try:
        ok, reason = _cleanup_challenge_locked(rec)
    except Exception:  # noqa: BLE001
        ok, reason = False, "challenge_cleanup_failed"
    if not ok:
        warnings.add(reason)
    else:
        warnings.discard("challenge_cleanup_failed")
    try:
        roots = _roots_module()
    except Exception:  # noqa: BLE001
        roots = None
    try:
        root_cleanup = (
            roots._remove_root_locked(rec["root"])
            if roots is not None else {"ok": False})
    except Exception:  # noqa: BLE001
        root_cleanup = {"ok": False}
    if not root_cleanup.get("ok"):
        warnings.add("active_root_cleanup_failed")
    else:
        warnings.discard("active_root_cleanup_failed")
    try:
        current_cleanup = (
            roots.remove_current_session_cas(
                rec["root"], session_id=rec["session_id"],
                conversation_id=rec["conversation_id"], branch=rec["branch"],
                common_dir=rec["common_dir"], expected_boot_id=rec["boot_id"],
                lock_held=True)
            if roots is not None
            else {"ok": False, "reason": "current_session_cleanup_failed"})
    except Exception:  # noqa: BLE001
        current_cleanup = {"ok": False, "reason": "current_session_cleanup_failed"}
    if not current_cleanup.get("ok"):
        warnings.add(str(
            current_cleanup.get("reason") or "current_session_cleanup_failed"))
    else:
        warnings = {
            item for item in warnings
            if not item.startswith("current_session_")
        }

    rec["cleanup_warnings"] = sorted(warnings)
    if branch_state_committed:
        try:
            _write_removed_receipt_locked(rec)
            rec["receipt_committed"] = True
            warnings.discard("receipt_write_failed")
            rec["cleanup_warnings"] = sorted(warnings)
        except Exception:  # noqa: BLE001
            rec["receipt_committed"] = False
            warnings.add("receipt_write_failed")
            rec["cleanup_warnings"] = sorted(warnings)
    else:
        rec["receipt_committed"] = False

    if rec["receipt_committed"]:
        rec["phase"] = "finalized"
        rec["updated_at_epoch"] = _now_epoch()
        try:
            _write_removal_journal(rec)
        except Exception:  # noqa: BLE001
            warnings.add("finalized_state_write_failed")
    result = {
        "outcome": "removed",
        "reason": "finish_removed",
        "receipt_code": "finish_removed",
        "receipt_disposition": "removed",
        "message": _removed_message(rec),
        "branch_action": rec["branch_action"],
        "branch_reason": rec["branch_disposition"].get("reason", ""),
        "discard_count": rec["discard_count"],
        "authorization_nonce": rec["nonce"],
        "challenge_fingerprint": rec["fingerprint"],
        "operation_id": rec["operation_id"],
        "state_cleanup_warnings": sorted(warnings),
        "receipt_committed": rec["receipt_committed"],
    }
    if warnings:
        result["message"] += (
            "; WARNING: local finish state cleanup was incomplete: "
            + ",".join(sorted(warnings)))
    return result


def _journal_scan(*, root: str, git_dir: str, common_dir: str, branch: str,
                  head: str, conversation_id: str, session_id: str,
                  expected_nonce: str | None = None,
                  expected_generation: int | None = None) -> tuple[list, list]:
    directory = finish_dir()
    if not os.path.isdir(directory):
        return [], []
    expected = {
        "root": canon(root), "git_dir": os.path.abspath(git_dir),
        "common_dir": os.path.abspath(common_dir), "branch": branch, "head": head,
        "conversation_id": conversation_id, "session_id": session_id,
        "session_key": _roots_module().session_key(session_id),
    }
    matches = []
    malformed = []
    try:
        names = sorted(name for name in os.listdir(directory)
                       if name.startswith("removal-") and name.endswith(".json"))
    except OSError:
        return [], ["scan_unavailable"]
    for name in names:
        operation_id = name[len("removal-"):-len(".json")]
        rec, status = read_removal_journal(operation_id)
        if status == "malformed" and re.fullmatch(r"[0-9a-f]{64}", operation_id):
            # Identity cannot be trusted enough to filter a malformed journal by target. Preserve
            # uncertainty rather than letting an interrupted physical removal look like "absent".
            malformed.append(operation_id)
            continue
        if status != "ok" or rec is None:
            continue
        if any(rec.get(key) != value for key, value in expected.items()):
            continue
        if expected_nonce is not None and rec.get("nonce") != expected_nonce:
            continue
        if expected_generation is not None and rec.get("generation") != expected_generation:
            continue
        matches.append(rec)
    return matches, malformed


def _journal_candidates(*, root: str, git_dir: str, common_dir: str, branch: str,
                        head: str, conversation_id: str, session_id: str,
                        expected_nonce: str | None = None,
                        expected_generation: int | None = None) -> list:
    """Compatibility projection for callers that need only validated, target-bound records."""
    matches, _malformed = _journal_scan(
        root=root, git_dir=git_dir, common_dir=common_dir, branch=branch, head=head,
        conversation_id=conversation_id, session_id=session_id,
        expected_nonce=expected_nonce, expected_generation=expected_generation)
    return matches


def reconcile_removal(*, root: str, git_dir: str, common_dir: str, branch: str,
                      head: str, conversation_id: str, session_id: str,
                      expected_nonce: str | None = None,
                      expected_generation: int | None = None,
                      lock_timeout: float = 30.0) -> dict:
    """Reconcile exactly one operation using both physical-root and Git-registration signals."""
    try:
        with common_dir_lock(common_dir, blocking=True, timeout=lock_timeout):
            matches, malformed = _journal_scan(
                root=root, git_dir=git_dir, common_dir=common_dir, branch=branch,
                head=head, conversation_id=conversation_id, session_id=session_id,
                expected_nonce=expected_nonce, expected_generation=expected_generation)
            if malformed:
                return {"outcome": "uncertain", "reason": "removal_journal_malformed"}
            if not matches:
                return {"outcome": "absent", "reason": "removal_journal_absent"}
            if len(matches) != 1:
                return {"outcome": "uncertain", "reason": "removal_journal_ambiguous"}
            return _reconcile_removal_journal_locked(matches[0])
    except LockBusy:
        return {"outcome": "uncertain", "reason": "lock_busy"}


def _challenge_ttl(override: int | None = None) -> int:
    if override is not None:
        return max(0, int(override))
    raw = os.environ.get("AWA_FINISH_CHALLENGE_TTL_SECONDS", "").strip()
    if raw:
        try:
            val = int(raw)
        except ValueError:
            return DEFAULT_CHALLENGE_TTL_SECONDS
        if val <= 0:
            return DEFAULT_CHALLENGE_TTL_SECONDS
        return max(MIN_CHALLENGE_TTL_SECONDS, val)
    return DEFAULT_CHALLENGE_TTL_SECONDS


def create_challenge(*, conversation_id: str, root: str, git_dir: str, common_dir: str,
                     branch: str, head: str, fingerprint: str, markers: list,
                     membership: list, operation_digest: str = "",
                     root_incarnation: dict | None = None,
                     git_dir_incarnation: dict | None = None, session_id: str = "",
                     hook_mode: bool = False) -> dict:
    """Persist ONE 0600 pending challenge (atomic write-and-rename). Do NOT store the confirming
    session's heartbeat timestamp (it is refreshed by the shell hooks)."""
    previous_generation = _max_generation_state(conversation_id)
    prior, prior_status = _read_challenge_raw(conversation_id)
    if prior_status in {"ok", "legacy_skew"} and isinstance(prior, dict):
        value = prior.get("generation")
        if isinstance(value, int) and value >= 1:
            previous_generation = value
    if root_incarnation is None or git_dir_incarnation is None:
        root_incarnation, git_dir_incarnation = capture_physical_incarnations(
            root, git_dir)
    if not _valid_incarnation(root_incarnation) or not _valid_incarnation(
            git_dir_incarnation):
        raise ValueError("valid physical incarnation required")
    now_epoch, now_iso = _now_pair()
    current_install_id = install_id()
    if not isinstance(current_install_id, str) or not current_install_id:
        raise FinishError("install_identity_invalid")
    rec = {
        "schema": SCHEMA_CHALLENGE,
        "nonce": os.urandom(24).hex(),
        "generation": previous_generation + 1,
        "conversation_id": conversation_id or "",
        "session_key": _roots_module().session_key(session_id),
        "boot_id": boot_id(),
        "install_id": current_install_id,
        "root": canon(root),
        "git_dir": os.path.abspath(git_dir),
        "common_dir": os.path.abspath(common_dir),
        "branch": branch or "",
        "head": head or "",
        "fingerprint": fingerprint,
        "root_incarnation": root_incarnation,
        "git_dir_incarnation": git_dir_incarnation,
        "operation_markers": sorted(markers),
        "operation_digest": operation_digest,
        "heartbeat_membership": sorted(membership),
        "warning_version": WARNING_VERSION,
        "cruft_allowlist_version": CRUFT_ALLOWLIST_VERSION,
        "selected_disposition": SELECTED_DISPOSITION_FULL_DISCARD,
        "hook_mode": bool(hook_mode),
        "hook_requires_envelope": bool(hook_mode),
        "hook_warning_published": False,
        "hook_activated": False,
        "activated_choice": "",
        "activated_envelope_digest": "",
        "created_at_epoch": now_epoch,
        "created_at": now_iso,
    }
    _write_private(challenge_path(conversation_id), json.dumps(rec, indent=2, sort_keys=True) + "\n")
    return rec


def _read_challenge_raw(conversation_id: str) -> tuple:
    """Read one schema-valid challenge without TTL deletion or other side effects."""
    path = challenge_path(conversation_id)
    try:
        _durability_module().adopt_visible(path)
        with open(path, encoding="utf-8") as fh:
            rec = json.load(fh)
    except FileNotFoundError:
        return None, "absent"
    except (OSError, json.JSONDecodeError):
        return None, "malformed"
    if (not isinstance(rec, dict) or set(rec) != CHALLENGE_KEYS
            or rec.get("schema") != SCHEMA_CHALLENGE
            or not isinstance(rec.get("nonce"), str) or not rec.get("nonce")
            or type(rec.get("generation")) is not int or rec.get("generation") < 1
            or not isinstance(rec.get("conversation_id"), str)
            or not isinstance(rec.get("session_key"), str) or not rec.get("session_key")
            or not isinstance(rec.get("boot_id"), str) or not rec.get("boot_id")
            or not isinstance(rec.get("install_id"), str) or not rec.get("install_id")
            or not isinstance(rec.get("root"), str) or not rec.get("root")
            or rec.get("root") != canon(rec.get("root"))
            or not isinstance(rec.get("git_dir"), str) or not rec.get("git_dir")
            or rec.get("git_dir") != os.path.abspath(rec.get("git_dir"))
            or not isinstance(rec.get("common_dir"), str) or not rec.get("common_dir")
            or rec.get("common_dir") != os.path.abspath(rec.get("common_dir"))
            or not isinstance(rec.get("branch"), str)
            or not isinstance(rec.get("head"), str)
            or not isinstance(rec.get("fingerprint"), str) or not rec.get("fingerprint")
            or not _valid_incarnation(rec.get("root_incarnation"))
            or not _valid_incarnation(rec.get("git_dir_incarnation"))
            or not isinstance(rec.get("operation_markers"), list)
            or not isinstance(rec.get("operation_digest"), str)
            or (rec.get("operation_digest")
                and re.fullmatch(r"[0-9a-f]{64}", rec.get("operation_digest")) is None)
            or not isinstance(rec.get("heartbeat_membership"), list)
            or type(rec.get("hook_mode")) is not bool
            or type(rec.get("hook_requires_envelope")) is not bool
            or type(rec.get("hook_warning_published")) is not bool
            or type(rec.get("hook_activated")) is not bool):
        return None, "malformed"
    timestamp_state, created = _timestamp_pair_state(
        rec.get("created_at"), rec.get("created_at_epoch"))
    if timestamp_state == "invalid" or created is None:
        return None, "malformed"
    if timestamp_state == "legacy_skew":
        rec = dict(rec)
        rec["created_at"] = _iso_from_epoch(created)
        return rec, "legacy_skew"
    return rec, "ok"


def _delete_challenge_raw_cas(conversation_id: str, *, expected_nonce: str,
                              expected_generation: int) -> bool:
    """Re-read immediately before unlink; caller holds the record's common-dir lock."""
    rec, status = _read_challenge_raw(conversation_id)
    if (status not in {"ok", "legacy_skew"} or rec is None
            or rec.get("nonce") != expected_nonce
            or rec.get("generation") != expected_generation):
        return False
    path = challenge_path(conversation_id)
    try:
        _durability_module().durable_unlink(path, missing_ok=False)
    except OSError:
        return False
    return not os.path.exists(path)


def read_challenge(conversation_id: str, *, ttl: int | None = None,
                   lock_held: bool = False) -> tuple:
    """Return (challenge|None, status), expiry-deleting only the exact stale generation."""
    rec, status = _read_challenge_raw(conversation_id)
    if status == "legacy_skew" and rec is not None:
        def migrate_locked() -> tuple:
            current, current_status = _read_challenge_raw(conversation_id)
            if current_status == "legacy_skew" and current is not None:
                _write_private(
                    challenge_path(conversation_id),
                    json.dumps(current, indent=2, sort_keys=True) + "\n")
                return current, "ok"
            return current, current_status
        try:
            if lock_held:
                rec, status = migrate_locked()
            else:
                with common_dir_lock(rec["common_dir"], blocking=True, timeout=5.0):
                    rec, status = migrate_locked()
        except (LockBusy, OSError):
            return None, "malformed"
    if status != "ok" or rec is None:
        return rec, status
    terminal = generation_state_status(
        conversation_id, rec["nonce"], rec["generation"], lock_held=lock_held)
    if terminal != "live":
        return None, terminal
    ttl_s = _challenge_ttl(ttl)
    if _now_epoch() - rec["created_at_epoch"] > ttl_s:
        # A concurrent preview writes under this same lock. Lock contention/uncertainty leaves the
        # stale record inert; status remains stale and no newer generation can be unlinked.
        delete_challenge(
            conversation_id, expected_nonce=rec["nonce"],
            expected_generation=rec["generation"], lock_held=lock_held)
        return None, "stale"
    return rec, "ok"


def consume_challenge(conversation_id: str, *, expected_nonce: str | None = None,
                      expected_generation: int | None = None,
                      lock_held: bool = False) -> bool:
    """Delete-on-consume, exactly once. Returns True if a file was removed (idempotent False if not)."""
    return delete_challenge(
        conversation_id, expected_nonce=expected_nonce,
        expected_generation=expected_generation, lock_held=lock_held)


def delete_challenge(conversation_id: str, *, expected_nonce: str | None = None,
                     expected_generation: int | None = None,
                     lock_held: bool = False) -> bool:
    """Delete one challenge; expected nonce+generation is a shared-lock CAS."""
    path = challenge_path(conversation_id)
    if expected_nonce is None and expected_generation is None:
        # Compatibility for direct diagnostic `challenge-delete` / `challenge-consume`.
        try:
            _durability_module().durable_unlink(path, missing_ok=False)
        except OSError:
            return False
        return not os.path.exists(path)
    if expected_nonce is None or expected_generation is None:
        return False
    if lock_held:
        return _delete_challenge_raw_cas(
            conversation_id, expected_nonce=expected_nonce,
            expected_generation=expected_generation)
    rec, status = _read_challenge_raw(conversation_id)
    if status not in {"ok", "legacy_skew"} or rec is None:
        return False
    try:
        with common_dir_lock(rec["common_dir"], blocking=False):
            return _delete_challenge_raw_cas(
                conversation_id, expected_nonce=expected_nonce,
                expected_generation=expected_generation)
    except (LockBusy, OSError, ValueError):
        return False


def cancel_challenge(*, conversation_id: str, common_dir: str, root: str,
                     session_id: str, nonce: str, generation: int,
                     lock_timeout: float = 30.0) -> dict:
    """Make one selected generation inert first, then clear its challenge projection.

    The nonce+generation terminal marker is one atomic, recoverable authority transition. Challenge
    unlink and consumer projection cleanup are follow-up work; failures are reported, never treated
    as a successful Cancel. This function never touches repo/git/archive/worktree content.
    """
    ckey = _roots_module().session_key(session_id)
    pre, pre_status = _read_challenge_raw(conversation_id)
    if pre_status in {"ok", "legacy_skew"} and pre is not None and (
            pre.get("nonce") == nonce and pre.get("generation") == generation):
        if (pre.get("root") != canon(root)
                or pre.get("common_dir") != os.path.abspath(common_dir)
                or pre.get("session_key") != ckey):
            return {"ok": False, "inert": False, "reason": "cancel_cas_mismatch"}
        if pre.get("hook_mode") and (
                pre.get("hook_activated") is not True
                or pre.get("activated_choice") != "Cancel"):
            return {"ok": False, "inert": False, "reason": "cancel_not_activated"}
    transitioned = _transition_generation(
        transition="cancelled", conversation_id=conversation_id, nonce=nonce,
        generation=generation, root=root, common_dir=common_dir,
        session_key_value=ckey)
    if not transitioned.get("inert"):
        return {"ok": False, "inert": False,
                "reason": str(transitioned.get("reason") or "cancel_transition_failed")}
    if not transitioned.get("ok"):
        return {"ok": False, "inert": True,
                "reason": str(transitioned.get("reason") or "cancel_transition_failed"),
                "challenge_cleared": False}
    try:
        with common_dir_lock(common_dir, blocking=True, timeout=lock_timeout):
            rec, status = _read_challenge_raw(conversation_id)
            if status == "absent":
                return {"ok": True, "inert": True, "reason": "cancelled",
                        "challenge_cleared": True}
            if status not in {"ok", "legacy_skew"} or rec is None:
                return {"ok": False, "inert": True, "reason": f"challenge_{status}",
                        "challenge_cleared": False}
            if (rec.get("root") != canon(root)
                    or rec.get("common_dir") != os.path.abspath(common_dir)
                    or rec.get("session_key") != ckey
                    or rec.get("nonce") != nonce
                    or rec.get("generation") != generation):
                # The selected generation is already absent/superseded. Its marker remains inert;
                # never unlink the newer current challenge.
                return {"ok": True, "inert": True, "reason": "cancelled_superseded",
                        "challenge_cleared": True}
            deleted = _delete_challenge_raw_cas(
                conversation_id, expected_nonce=nonce, expected_generation=generation)
            return {
                "ok": bool(deleted),
                "inert": True,
                "reason": "cancelled" if deleted else "challenge_cleanup_failed",
                "challenge_cleared": bool(deleted),
            }
    except LockBusy:
        return {"ok": False, "inert": True, "reason": "lock_busy",
                "challenge_cleared": False}


def activate_hook_challenge(*, conversation_id: str, common_dir: str, root: str,
                            session_id: str, nonce: str, generation: int,
                            choice: str, envelope_digest: str,
                            lock_timeout: float = 30.0) -> dict:
    """Activate one hook challenge after an exact one-use envelope was consumed."""
    if choice not in ("Commit", "Retain", "Mixed", "Cancel", "Close"):
        return {"ok": False, "reason": "choice_not_exact"}
    if not isinstance(envelope_digest, str) or len(envelope_digest) != 64:
        return {"ok": False, "reason": "envelope_digest_invalid"}
    try:
        with common_dir_lock(common_dir, blocking=True, timeout=lock_timeout):
            rec, status = read_challenge(conversation_id, lock_held=True)
            if status != "ok" or rec is None:
                return {"ok": False, "reason": f"challenge_{status}"}
            if (rec.get("root") != canon(root)
                    or rec.get("common_dir") != os.path.abspath(common_dir)
                    or rec.get("session_key") != _roots_module().session_key(session_id)
                    or rec.get("nonce") != nonce
                    or rec.get("generation") != generation):
                return {"ok": False, "reason": "activation_cas_mismatch"}
            if rec.get("hook_mode") is not True or rec.get("hook_requires_envelope") is not True:
                return {"ok": False, "reason": "not_hook_challenge"}
            if rec.get("hook_warning_published") is not True:
                return {"ok": False, "reason": "warning_not_published"}
            if rec.get("hook_activated"):
                return {"ok": False, "reason": "activation_replay"}
            rec["hook_activated"] = True
            rec["activated_choice"] = choice
            rec["activated_envelope_digest"] = envelope_digest
            _write_private(challenge_path(conversation_id),
                           json.dumps(rec, indent=2, sort_keys=True) + "\n")
            return {"ok": True, "reason": "activated"}
    except LockBusy:
        return {"ok": False, "reason": "lock_busy"}


def publish_hook_challenge(*, conversation_id: str, common_dir: str, root: str,
                           session_id: str, nonce: str, generation: int,
                           lock_timeout: float = 5.0) -> dict:
    """CAS-mark a fully emitted hook warning. Missing publication keeps the challenge inert."""
    try:
        with common_dir_lock(common_dir, blocking=True, timeout=lock_timeout):
            rec, status = read_challenge(conversation_id, lock_held=True)
            if status != "ok" or rec is None:
                return {"ok": False, "reason": f"challenge_{status}"}
            if (rec.get("root") != canon(root)
                    or rec.get("common_dir") != os.path.abspath(common_dir)
                    or rec.get("session_key") != _roots_module().session_key(session_id)
                    or rec.get("nonce") != nonce
                    or rec.get("generation") != generation
                    or rec.get("hook_mode") is not True):
                return {"ok": False, "reason": "publication_cas_mismatch"}
            rec["hook_warning_published"] = True
            _write_private(challenge_path(conversation_id),
                           json.dumps(rec, indent=2, sort_keys=True) + "\n")
            return {"ok": True, "reason": "published"}
    except LockBusy:
        return {"ok": False, "reason": "lock_busy"}


# ---- literal-Close authorization --------------------------------------------------------
def is_literal_close(answer) -> bool:
    """ONLY exact bytes `Close`; whitespace, casing, extra words, and non-strings reject."""
    return isinstance(answer, str) and answer == "Close"


def authorize(answer, challenge: dict, *, current_fingerprint: str) -> tuple:
    """(ok, reason). Requires the exact literal Close AND a byte-equal re-derived fingerprint."""
    if not is_literal_close(answer):
        return False, "not_close"
    if not isinstance(challenge, dict) or "fingerprint" not in challenge:
        return False, "no_challenge"
    if current_fingerprint != challenge.get("fingerprint"):
        return False, "fingerprint_mismatch"
    return True, "authorized"


# ---- network-free local-ref branch disposition ------------------------------------------
def _is_ephemeral_branch(root: str, branch: str, common_dir: str) -> bool:
    if not branch or branch in PROTECTED_BRANCHES:
        return False
    prefix = DEFAULT_BRANCH_PREFIX
    if prefix and (branch == prefix or branch.startswith(prefix + "/")):
        return True
    # A `.awa/lease.json` attestation naming THIS branch also proves AWA-ephemeral provenance.
    lease = os.path.join(root, ".awa", "lease.json")
    try:
        with open(lease, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict) and data.get("branch") == branch and data.get("schema"):
            return True
    except (OSError, json.JSONDecodeError):
        pass
    return False


def branch_disposition(root: str, branch: str, head: str, common_dir: str) -> dict:
    """Decide branch disposition from LOCAL refs ONLY (no gh / fetch / ls-remote / network).
      retain_local_only  -> commits on `head` unreachable from any OTHER local/remote-tracking ref;
      delete_eligible    -> empty local-only set AND an AWA-attested ephemeral branch;
      retain             -> empty local-only set but NOT provably ephemeral;
      retain (uncertain) -> any tool failure or ambiguity (fail-safe: keep the branch).
    Never touches a remote ref."""
    if not branch or branch == "HEAD":
        return {"action": "retain", "reason": "no_named_branch"}
    try:
        target = resolve_target(root)
    except (FinishError, OSError):
        return {"action": "retain", "reason": "target_binding_failed"}
    if (target["common_dir"] != os.path.abspath(common_dir)
            or target["branch"] != branch or target["head"] != head):
        return {"action": "retain", "reason": "target_binding_changed"}
    try:
        binding = validated_git_binding(
            root, git_dir=target["git_dir"], common_dir=target["common_dir"])
        actual_branch = _run_git_bound(
            binding, "rev-parse", "--abbrev-ref", "HEAD", text=True)
    except (FinishError, OSError):
        return {"action": "retain", "reason": "operation_identity_unavailable"}
    if actual_branch.returncode != 0:
        return {"action": "retain", "reason": "operation_identity_unavailable"}
    if actual_branch.stdout.strip() == "HEAD":
        # resolve_target accepted this only through an operation-derived original local branch.
        # Never delete that recovery anchor after removing the detached operation worktree.
        return {"action": "retain", "reason": "detached_operation"}
    r = _git_text(root, "for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes")
    if r.returncode != 0:
        return {"action": "retain", "reason": "for_each_ref_failed"}
    others = []
    self_ref = f"refs/heads/{branch}"
    for line in r.stdout.splitlines():
        ref = line.strip()
        if ref and ref != self_ref:
            others.append(ref)
    revlist = ["rev-list", head, "--not", *others]
    rl = _git_text(root, *revlist)
    if rl.returncode != 0:
        return {"action": "retain", "reason": "rev_list_failed"}
    local_only = [c for c in rl.stdout.splitlines() if c.strip()]
    if local_only:
        return {"action": "retain_local_only", "reason": "local_only_commits",
                "local_only_count": len(local_only)}
    if _is_ephemeral_branch(root, branch, common_dir):
        return {"action": "delete_eligible", "reason": "ephemeral_no_local_only"}
    return {"action": "retain", "reason": "not_ephemeral"}


# ---- final recheck ----------------------------------------------------------------------
def final_recheck(root: str, git_dir: str, common_dir: str, branch: str, head: str, *,
                  root_incarnation: dict, git_dir_incarnation: dict) -> dict:
    """Re-verify the immutable target facts immediately before removal (under the lock). Any
    changed fact refuses. Inventory/marker/membership equality is enforced separately via a
    fingerprint byte-comparison in finish_execute."""
    root_c = canon(root)
    try:
        physical_before = capture_physical_incarnations(root_c, git_dir)
    except FinishError:
        return {"ok": False, "reason": "physical_identity_unavailable"}
    if physical_before != (root_incarnation, git_dir_incarnation):
        return {"ok": False, "reason": "physical_incarnation_changed"}
    try:
        target = resolve_target(root_c)
    except FinishError:
        return {"ok": False, "reason": "git_identity_unreadable"}
    if target["git_dir"] != os.path.abspath(git_dir):
        return {"ok": False, "reason": "git_dir_changed"}
    if target["common_dir"] != os.path.abspath(common_dir):
        return {"ok": False, "reason": "common_dir_changed"}
    if target["branch"] != branch:
        return {"ok": False, "reason": "branch_changed"}
    if target["head"] != head:
        return {"ok": False, "reason": "head_changed"}
    try:
        physical_after = capture_physical_incarnations(root_c, git_dir)
    except FinishError:
        return {"ok": False, "reason": "physical_identity_unavailable"}
    if physical_after != (root_incarnation, git_dir_incarnation):
        return {"ok": False, "reason": "physical_incarnation_changed"}
    return {"ok": True, "reason": "unchanged"}


# ---- render (plain, escaped) ------------------------------------------------------------
def render_rows(inv: dict) -> str:
    """Stable, escaped plain rendering of the OPERATOR-facing (non-hidden) rows. Phase 2 wraps
    this in the approved warning payload. Hidden cruft is omitted here but still bound into the
    fingerprint + receipt. One `None | ...` row when no operator work would be deleted."""
    visible = [e for e in inv["entries"] if not e["hidden"] and not e.get("retained")]
    if not visible:
        return "None | No operator work will be deleted."
    lines = []
    for idx, e in enumerate(visible, 1):
        lines.append(f"{idx}. {e['display']} | {escape_for_display(e['sentence'])}")
    return "\n".join(lines)


# ---- finish execute (the destructive critical section, under the lock) ------------------
# Map a (raw outcome, reason) to a BOUNDED receipt (disposition, code) pair. The shell kernel
# switches on receipt_code with LITERAL clean_set_disposition calls (so the receipt-coverage
# meta-test sees every finish terminal path); Python stays the single authority for the decision.
def _augment_receipt(res: dict) -> dict:
    outcome = res.get("outcome", "refused")
    reason = str(res.get("reason", ""))
    if outcome == "removed":
        disp, code = "removed", "finish_removed"
    elif outcome == "error":
        disp = "error"
        code = "finish_remove_failed" if reason == "worktree_remove_failed" else "finish_error"
    elif reason == "not_close":
        disp, code = "refused", "finish_not_close"
    elif reason == "challenge_target_mismatch":
        disp, code = "refused", "finish_target_mismatch"
    elif reason.startswith("challenge_") or reason == "no_challenge":
        disp, code = "refused", "finish_no_challenge"
    elif reason == "fingerprint_mismatch":
        disp, code = "refused", "finish_fingerprint_mismatch"
    elif reason.startswith("inventory_"):
        disp, code = "refused", "finish_inventory_unsafe"
    elif reason.startswith("session_"):
        disp, code = "refused", "finish_session_blocked"
    elif reason.startswith("recheck_"):
        disp, code = "refused", "finish_recheck_failed"
    elif reason == "lock_busy":
        disp, code = "refused", "finish_lock_busy"
    else:  # a truly unrecognized refusal is a surprise -> fail-safe error receipt
        disp, code = "error", "finish_error"
    res["receipt_disposition"] = disp
    res["receipt_code"] = code
    return res


def finish_execute(**kwargs) -> dict:
    """Public destructive-path entry: run the impl, then stamp the bounded receipt fields."""
    return _augment_receipt(_finish_execute_impl(**kwargs))


def _finish_execute_impl(*, root: str, git_dir: str, common_dir: str, branch: str, head: str,
                         session_id: str, conversation_id: str, answer,
                         expected_nonce: str | None = None,
                         expected_generation: int | None = None,
                         challenge_ttl: int | None = None, lock_timeout: float = 30.0) -> dict:
    """The one destructive path. Under the per-common-dir lock: re-derive the fingerprint and
    require BYTE-EQUAL to the challenge + an exact literal Close, run the per-session gate + final
    recheck, then `git worktree remove --force`, apply the network-free branch disposition,
    claim an activated hook generation exactly once BEFORE lock acquisition/validation, and clear
    the heartbeat after removal. Any uncertainty PRESERVES the worktree. Direct non-hook Phase-1
    calls remain compatible without expected nonce/generation. A branch-cleanup failure NEVER
    misreports the removed root as surviving."""
    roots = _roots_module()
    ckey = roots.session_key(session_id)

    # A prior process may have died after physical removal but before returning JSON. Detect a
    # bound durable operation before one-use claim handling, then reconcile it from the two local
    # physical signals. Fresh attempts have no journal and retain the existing claim-before-lock
    # semantics.
    prior_journals, malformed_journals = _journal_scan(
        root=root, git_dir=git_dir, common_dir=common_dir, branch=branch, head=head,
        conversation_id=conversation_id, session_id=session_id,
        expected_nonce=expected_nonce, expected_generation=expected_generation)
    if prior_journals or malformed_journals:
        recovered = reconcile_removal(
            root=root, git_dir=git_dir, common_dir=common_dir, branch=branch, head=head,
            conversation_id=conversation_id, session_id=session_id,
            expected_nonce=expected_nonce, expected_generation=expected_generation,
            lock_timeout=lock_timeout)
        if recovered.get("outcome") == "removed":
            return recovered
        if recovered.get("outcome") == "uncertain":
            return {
                "outcome": "uncertain", "reason": "removal_reconciliation_uncertain",
                "message": "a prior finish operation could not be reconciled safely",
            }

    # Hook mode is defense-in-depth bound to the exact persisted nonce+generation. The O_EXCL
    # marker is created BEFORE attempting the shared lock, so lock contention and every later
    # refusal/fault still burn this activated generation exactly once. That includes a tampered
    # non-literal answer after activation; direct non-hook Phase-1 keeps its prior cheap literal
    # refusal. This marker is not another lock ABI.
    pre, pre_status = _read_challenge_raw(conversation_id)
    pre_usable = pre_status in {"ok", "legacy_skew"} and pre is not None
    expected_binding_requested = (
        expected_nonce is not None or expected_generation is not None)
    supplied_binding = (
        isinstance(expected_nonce, str) and bool(expected_nonce)
        and type(expected_generation) is int and expected_generation >= 1
    )
    if expected_binding_requested and not supplied_binding:
        return {"outcome": "refused", "reason": "challenge_generation_required",
                "message": "hook Close requires a complete valid nonce and generation pair"}
    if expected_binding_requested:
        if not pre_usable:
            return {"outcome": "refused", "reason": f"challenge_{pre_status}",
                    "message": f"no usable pending challenge ({pre_status})"}
        if (pre.get("nonce") != expected_nonce
                or pre.get("generation") != expected_generation):
            stale_claim = _transition_generation(
                transition="close_claimed", conversation_id=conversation_id,
                nonce=expected_nonce, generation=expected_generation, root=root,
                common_dir=common_dir, session_key_value=ckey)
            if not stale_claim.get("created"):
                return {"outcome": "refused", "reason": "challenge_consumed",
                        "message": "this Close generation was already attempted and is permanently inert"}
            if not stale_claim.get("ok"):
                return {"outcome": "error", "reason": "challenge_claim_state_failed",
                        "message": "the replaced Close generation became inert with malformed claim state"}
            return {"outcome": "refused", "reason": "challenge_generation_mismatch",
                    "message": "the persisted hook generation was replaced before execution"}
        if pre.get("hook_mode") is not True:
            return {"outcome": "refused", "reason": "challenge_generation_mismatch",
                    "message": "expected hook generation no longer names a hook challenge"}
    hook_claimed = False
    hook_attempt = pre_usable and pre.get("hook_mode") is True
    if not hook_attempt and not is_literal_close(answer):
        return {"outcome": "refused", "reason": "not_close",
                "message": "authorization was not the exact literal 'Close'"}
    if hook_attempt:
        if (pre.get("hook_requires_envelope") is not True
                or pre.get("hook_warning_published") is not True
                or pre.get("hook_activated") is not True
                or pre.get("activated_choice") != "Close"
                or not isinstance(pre.get("activated_envelope_digest"), str)
                or len(pre.get("activated_envelope_digest")) != 64):
            return {"outcome": "refused", "reason": "challenge_unactivated",
                    "message": "hook challenge was not activated by an exact one-use Close envelope"}
        claim_nonce = expected_nonce if supplied_binding else pre["nonce"]
        claim_generation = expected_generation if supplied_binding else pre["generation"]
        claim = _transition_generation(
            transition="close_claimed", conversation_id=conversation_id,
            nonce=claim_nonce, generation=claim_generation, root=pre["root"],
            common_dir=pre["common_dir"], session_key_value=pre["session_key"])
        if not claim.get("created"):
            return {"outcome": "refused", "reason": "challenge_consumed",
                    "message": "this Close generation was already attempted and is permanently inert"}
        if not claim.get("ok"):
            return {"outcome": "error", "reason": "challenge_claim_state_failed",
                    "message": "the Close generation became inert but its claim state is malformed"}
        hook_claimed = True
        if not supplied_binding:
            return {"outcome": "refused", "reason": "challenge_generation_required",
                    "message": "hook Close requires its exact expected nonce and generation"}
        if not is_literal_close(answer):
            return {"outcome": "refused", "reason": "not_close",
                    "message": "authorization was not the exact literal 'Close'"}
    elif not pre_usable:
        return {"outcome": "refused", "reason": f"challenge_{pre_status}",
                "message": f"no usable pending challenge ({pre_status})"}

    # `removed` LATCHES once the worktree is physically gone (see the point-of-no-return below).
    # After that, NO code path — not a raising branch-delete/consume/remove_root, not the outer
    # except — may report the already-removed root as surviving/error; it returns removed_result.
    removed = False
    removed_result: dict = {}
    journal: dict | None = None
    finalized_branch_action = ""
    try:
        with common_dir_lock(common_dir, blocking=True, timeout=lock_timeout):
            # Re-scan after acquiring the serialization lock. A concurrent direct caller can
            # prepare/remove after the optimistic pre-scan but before this lock acquisition; that
            # removed root must be reconciled, never narrated as a fresh validation refusal.
            locked_journals, locked_malformed = _journal_scan(
                root=root, git_dir=git_dir, common_dir=common_dir, branch=branch, head=head,
                conversation_id=conversation_id, session_id=session_id,
                expected_nonce=expected_nonce, expected_generation=expected_generation)
            if locked_malformed or len(locked_journals) > 1:
                return {
                    "outcome": "uncertain", "reason": "removal_reconciliation_uncertain",
                    "message": "a prior finish operation could not be reconciled safely",
                }
            if len(locked_journals) == 1:
                recovered = _reconcile_removal_journal_locked(locked_journals[0])
                if recovered.get("outcome") == "removed":
                    return recovered
                if recovered.get("outcome") == "uncertain":
                    return {
                        "outcome": "uncertain", "reason": "removal_reconciliation_uncertain",
                        "message": "a prior finish operation could not be reconciled safely",
                    }
            # A claimed hook challenge is intentionally hidden from public readers; this executor
            # holds the exact one-use claim and therefore re-reads the raw record under the lock.
            if hook_claimed:
                ch, status = _read_challenge_raw(conversation_id)
                if status == "legacy_skew" and ch is not None:
                    _write_private(
                        challenge_path(conversation_id),
                        json.dumps(ch, indent=2, sort_keys=True) + "\n")
                    status = "ok"
                if status in {"ok", "legacy_skew"} and ch is not None:
                    ttl_s = _challenge_ttl(challenge_ttl)
                    if _now_epoch() - ch["created_at_epoch"] > ttl_s:
                        ch, status = None, "stale"
            else:
                ch, status = read_challenge(
                    conversation_id, ttl=challenge_ttl, lock_held=True)
            if status not in {"ok", "legacy_skew"} or ch is None:
                return {"outcome": "refused", "reason": f"challenge_{status}",
                        "message": f"no usable pending challenge ({status})"}
            # Bind the challenge to THIS exact target (cross-root/branch/head/dir use refuses).
            # boot_id is bound too: create_challenge stores it, so a challenge minted before a reboot
            # can NEVER authorize a removal on a later boot (a reused pid/path could otherwise alias).
            if (ch.get("root") != canon(root) or ch.get("branch") != (branch or "")
                    or ch.get("head") != (head or "")
                    or ch.get("git_dir") != os.path.abspath(git_dir)
                    or ch.get("common_dir") != os.path.abspath(common_dir)
                    or ch.get("session_key") != ckey
                    or ch.get("boot_id") != boot_id()
                    or not isinstance(ch.get("install_id"), str)
                    or not ch.get("install_id")
                    or ch.get("install_id") != install_id()):
                return {"outcome": "refused", "reason": "challenge_target_mismatch",
                        "message": "pending challenge is bound to a different root/branch/HEAD/boot/install"}
            try:
                capture_physical_incarnations(root, git_dir)
            except FinishError:
                return {"outcome": "refused", "reason": "recheck_physical_identity_unavailable",
                        "message": "pending challenge physical identity could not be revalidated"}
            if expected_binding_requested and ch.get("hook_mode") is not True:
                return {"outcome": "refused", "reason": "challenge_generation_mismatch",
                        "message": "expected hook generation no longer names a hook challenge"}
            if ch.get("hook_mode"):
                if (not hook_claimed or ch.get("nonce") != expected_nonce
                        or ch.get("generation") != expected_generation):
                    return {"outcome": "refused", "reason": "challenge_generation_mismatch",
                            "message": "hook Close did not match its claimed nonce and generation"}
                if (ch.get("hook_requires_envelope") is not True
                        or ch.get("hook_warning_published") is not True
                        or ch.get("hook_activated") is not True
                        or ch.get("activated_choice") != "Close"
                        or not isinstance(ch.get("activated_envelope_digest"), str)
                        or len(ch.get("activated_envelope_digest")) != 64):
                    return {"outcome": "refused", "reason": "challenge_unactivated",
                            "message": "hook challenge was not activated by an exact one-use Close envelope"}
            # Validate finish-only session evidence BEFORE fingerprinting. A malformed active_root
            # member is reported as malformed (not blurred into a generic fingerprint drift), and
            # only the confirming session's strict pid-less identity may be waived.
            gate = roots.finish_session_gate(
                root, confirming_session_key=ckey,
                branch=branch, common_dir=common_dir, lock_held=True)
            if gate.get("blocked"):
                gate_reason = str(gate.get("reason") or "session_malformed")
                reason = gate_reason if gate_reason.startswith("session_") else (
                    "session_" + gate_reason)
                return {"outcome": "refused", "reason": reason,
                        "message": f"session gate blocked: {gate_reason}"}
            # Re-derive the inventory + fingerprint UNDER THE LOCK.
            physical_before = capture_physical_incarnations(root, git_dir)
            inv = build_inventory(root, git_dir)
            if not inv["safe"]:
                return {"outcome": "refused", "reason": f"inventory_{inv['refuse_reason']}",
                        "message": f"inventory unsafe at recheck: {inv['refuse_reason']}"}
            membership = heartbeat_membership(
                root, ckey, branch=branch, common_dir=common_dir,
                lock_held=True)
            physical_after = capture_physical_incarnations(root, git_dir)
            if physical_after != physical_before:
                return {"outcome": "refused", "reason": "recheck_physical_incarnation_changed",
                        "message": "physical workspace identity changed during authorization"}
            fp = compute_fingerprint(
                inv, root=root, git_dir=git_dir, common_dir=common_dir,
                branch=branch, head=head, membership=membership,
                root_incarnation=physical_after[0],
                git_dir_incarnation=physical_after[1])
            ok, why = authorize(answer, ch, current_fingerprint=fp)
            if not ok:
                return {"outcome": "refused", "reason": why,
                        "message": f"authorization failed: {why}"}
            # Final immutable-fact recheck.
            rc = final_recheck(
                root, git_dir, common_dir, branch, head,
                root_incarnation=ch["root_incarnation"],
                git_dir_incarnation=ch["git_dir_incarnation"])
            if not rc["ok"]:
                return {"outcome": "refused", "reason": "recheck_" + rc["reason"],
                        "message": f"final recheck refused: {rc['reason']}"}
            # Decide the branch disposition (network-free) BEFORE removal.
            bdisp = branch_disposition(root, branch, head, common_dir)
            # FINAL re-fingerprint as the LAST gate before the destructive remove. The inventory +
            # fingerprint authorized above were computed BEFORE finish_session_gate + final_recheck +
            # branch_disposition ran their ~7 git subprocesses; a file created in THAT window would
            # otherwise be discarded though it was never authorized. Rebuild the inventory + recompute
            # the fingerprint here and require inv.safe AND byte-equality to the challenge — any drift
            # (a new file, a newly-unsafe tree, a new concurrent session in membership) PRESERVES the
            # worktree, reusing the fingerprint_mismatch / inventory_unsafe receipts (fail-safe).
            gate = roots.finish_session_gate(
                root, confirming_session_key=ckey,
                branch=branch, common_dir=common_dir, lock_held=True)
            if gate.get("blocked"):
                gate_reason = str(gate.get("reason") or "session_malformed")
                reason = gate_reason if gate_reason.startswith("session_") else (
                    "session_" + gate_reason)
                return {"outcome": "refused", "reason": reason,
                        "message": f"session gate changed before removal: {gate_reason}"}
            physical_before = capture_physical_incarnations(root, git_dir)
            inv = build_inventory(root, git_dir)
            if not inv["safe"]:
                return {"outcome": "refused", "reason": f"inventory_{inv['refuse_reason']}",
                        "message": f"inventory became unsafe before removal: {inv['refuse_reason']}"}
            physical_after = capture_physical_incarnations(root, git_dir)
            if physical_after != physical_before:
                return {"outcome": "refused", "reason": "recheck_physical_incarnation_changed",
                        "message": "physical workspace identity changed before removal"}
            fp = compute_fingerprint(
                inv, root=root, git_dir=git_dir, common_dir=common_dir,
                branch=branch, head=head,
                membership=heartbeat_membership(
                    root, ckey, branch=branch,
                    common_dir=common_dir, lock_held=True),
                root_incarnation=physical_after[0],
                git_dir_incarnation=physical_after[1])
            if fp != ch["fingerprint"]:
                return {"outcome": "refused", "reason": "fingerprint_mismatch",
                        "message": "inventory changed between authorization and removal (final gate)"}
            discard_count = len(inv["entries"])
            cd_abs = os.path.abspath(common_dir)
            root_c = canon(root)
            identity = _operation_identity_payload(
                root=root_c, git_dir=git_dir, common_dir=cd_abs, branch=branch,
                head=head, conversation_id=conversation_id, nonce=ch["nonce"],
                generation=ch["generation"], session_id=session_id,
                session_key_value=ckey, boot_id_value=ch["boot_id"],
                install_id_value=ch["install_id"],
                root_incarnation_value=ch["root_incarnation"],
                git_dir_incarnation_value=ch["git_dir_incarnation"],
                fingerprint=fp, claim="close_claimed" if hook_claimed else "direct",
                branch_disposition_value=bdisp, discard_count=discard_count)
            # PREPARED is file+directory fsynced before the physical operation. Failure here is
            # strictly pre-removal and preserves the worktree.
            journal = _prepare_removal_journal_locked(identity=identity)
            # CWD SAFETY: removing the current worktree unlinks this process's cwd; move to a
            # surviving dir FIRST so every post-removal subprocess (branch delete, and the shell's
            # receipt writer) can still fork/exec. All git calls below pass an explicit --git-dir,
            # so they never depend on cwd being inside a repo.
            safe_cwd = common_dir_arg_root(cd_abs)
            try:
                current_cwd = canon(os.getcwd())
                root_prefix = root_c + os.sep
                if current_cwd == root_c or current_cwd.startswith(root_prefix):
                    os.chdir(safe_cwd)
            except OSError:
                os.chdir(safe_cwd)
            # Remove the worktree. --force because the authorized inventory is a deliberate discard;
            # safety came from the fingerprint+Close authorization, not git's own dirty check.
            rm = _run_git_admin(
                cd_abs, "worktree", "remove", "--force", root_c,
                text=True, cwd=safe_cwd)
            try:
                _sync_removed_worktree_namespaces(journal)
            except Exception:  # noqa: BLE001
                return {
                    "outcome": "uncertain",
                    "reason": "removal_namespace_sync_failed",
                    "message": "workspace removal durability could not be certified",
                    "operation_id": journal["operation_id"],
                }
            # Git's return code is not a physical-state oracle.  Under the same common-dir lock,
            # classify the root + registration after EVERY returned result.  A nonzero result may
            # follow complete removal; a zero result may still leave a partially changed tree.
            physical = _operation_removal_state_locked(journal)
            if physical["state"] == "intact":
                if not _clear_pre_removal_journal_locked(journal):
                    return {
                        "outcome": "uncertain",
                        "reason": "pre_removal_journal_cleanup_failed",
                        "message": "workspace removal could not be classified safely",
                    }
                return {
                    "outcome": "error",
                    "reason": "worktree_remove_failed",
                    "message": "workspace removal did not occur; the exact prior state was preserved",
                    "operation_id": journal["operation_id"],
                }
            if physical["state"] != "removed":
                return {
                    "outcome": "uncertain",
                    "reason": "worktree_remove_uncertain",
                    "message": "workspace removal could not be classified safely",
                }
            # ---- PAST THE POINT OF NO RETURN: absence + unregistration are proven. ----
            removed = True
            try:
                journal["phase"] = "removed"
                journal["cleanup_warnings"] = []
                journal["updated_at_epoch"] = _now_epoch()
                _write_removal_journal(journal)
            except Exception:  # noqa: BLE001
                journal["phase"] = "prepared"
                return {
                    "outcome": "uncertain",
                    "reason": "removed_state_write_failed",
                    "message": "workspace removal state could not be persisted",
                    "operation_id": journal["operation_id"],
                }
            # Finalize the branch — the genuine in-process action — as part of the durable removed
            # state, BEFORE the non-authoritative reconciliation cleanup. Reconciliation reuses this
            # exact value (`rec["branch_action"] or _finalize_branch_locked(...)`), so it is computed
            # ONCE; capturing it here means any later reconciliation fault still reports the removed
            # root honestly (durable branch truth, else this exact action) instead of reversing the
            # `removed` latch to a survived/uncertain misreport.
            finalized_branch_action = (
                journal.get("branch_action") or _finalize_branch_locked(journal))
            journal["branch_action"] = finalized_branch_action
            removed_result = {
                "outcome": "removed",
                "reason": "finish_removed",
                "receipt_code": "finish_removed",
                "receipt_disposition": "removed",
                "branch_reason": journal["branch_disposition"].get("reason", ""),
                "discard_count": journal["discard_count"],
                "authorization_nonce": journal["nonce"],
                "challenge_fingerprint": journal["fingerprint"],
                "operation_id": journal["operation_id"],
                "receipt_committed": False,
            }
            try:
                reconciled = _reconcile_removal_journal_locked(journal)
            except Exception:  # noqa: BLE001 — post-branch cleanup is non-authoritative
                return _removed_fallback_from_branch_truth(
                    journal,
                    {**removed_result,
                     "state_cleanup_warnings": ["removal_reconciliation_failed"]},
                    finalized_branch_action)
            if reconciled.get("outcome") == "removed":
                return reconciled
            return _removed_fallback_from_branch_truth(
                journal,
                {**removed_result,
                 "state_cleanup_warnings": [
                     str(reconciled.get("reason") or "removal_reconciliation_incomplete")]},
                finalized_branch_action)
    except LockBusy:
        if removed:
            try:
                recovered = reconcile_removal(
                    root=root, git_dir=git_dir, common_dir=common_dir, branch=branch,
                    head=head, conversation_id=conversation_id, session_id=session_id,
                    expected_nonce=(journal or {}).get("nonce"),
                    expected_generation=(journal or {}).get("generation"),
                    lock_timeout=lock_timeout)
                return (recovered if recovered.get("outcome") == "removed"
                        else _removed_fallback_from_branch_truth(
                            journal, removed_result, finalized_branch_action))
            except Exception:  # noqa: BLE001 — removed latch survives reconciliation faults
                removed_result.setdefault("state_cleanup_warnings", []).append(
                    "removal_reconciliation_failed")
                return _removed_fallback_from_branch_truth(
                    journal, removed_result, finalized_branch_action)
        return {
            "outcome": "refused", "reason": "lock_busy",
            "message": "another local action is in progress",
        }
    except FinishError:
        if removed:
            try:
                recovered = reconcile_removal(
                    root=root, git_dir=git_dir, common_dir=common_dir, branch=branch,
                    head=head, conversation_id=conversation_id, session_id=session_id,
                    expected_nonce=(journal or {}).get("nonce"),
                    expected_generation=(journal or {}).get("generation"),
                    lock_timeout=lock_timeout)
                return (recovered if recovered.get("outcome") == "removed"
                        else _removed_fallback_from_branch_truth(
                            journal, removed_result, finalized_branch_action))
            except Exception:  # noqa: BLE001 — removed latch survives reconciliation faults
                removed_result.setdefault("state_cleanup_warnings", []).append(
                    "removal_reconciliation_failed")
                return _removed_fallback_from_branch_truth(
                    journal, removed_result, finalized_branch_action)
        return {
            "outcome": "refused", "reason": "finish_error",
            "message": "finish could not be completed safely",
        }
    except Exception:  # noqa: BLE001 — fail-safe: any surprise preserves the worktree
        if removed:
            try:
                recovered = reconcile_removal(
                    root=root, git_dir=git_dir, common_dir=common_dir, branch=branch,
                    head=head, conversation_id=conversation_id, session_id=session_id,
                    expected_nonce=(journal or {}).get("nonce"),
                    expected_generation=(journal or {}).get("generation"),
                    lock_timeout=lock_timeout)
                return (recovered if recovered.get("outcome") == "removed"
                        else _removed_fallback_from_branch_truth(
                            journal, removed_result, finalized_branch_action))
            except Exception:  # noqa: BLE001 — removed latch survives reconciliation faults
                removed_result.setdefault("state_cleanup_warnings", []).append(
                    "removal_reconciliation_failed")
                return _removed_fallback_from_branch_truth(
                    journal, removed_result, finalized_branch_action)
        return {
            "outcome": "error", "reason": "unexpected",
            "message": "finish could not be completed safely",
        }


def common_dir_arg_root(common_dir: str) -> str:
    """A surviving directory to use as cwd for the post-removal git calls (the common dir's
    parent — the primary checkout — which the linked-worktree removal never destroys). Falls back
    to the common dir itself (a .git dir always survives) then the filesystem root."""
    parent = os.path.dirname(os.path.abspath(common_dir))
    if os.path.isdir(parent):
        return parent
    if os.path.isdir(common_dir):
        return os.path.abspath(common_dir)
    return os.sep


# ---- preview (read-only: inventory + fingerprint + create challenge) --------------------
def preview(*, root: str, git_dir: str, common_dir: str, branch: str, head: str,
            session_id: str, conversation_id: str, hook_mode: bool = False,
            lock_timeout: float = 30.0) -> dict:
    """Read-only reconnaissance: compute the inventory + fingerprint and persist ONE pending
    challenge. Performs NO fetch/push/branch update/archive/repo mutation, so a later Cancel is
    literally no-op. Refuses (creates no challenge) when the inventory is unsafe."""
    roots = _roots_module()
    ckey = roots.session_key(session_id)
    try:
        with common_dir_lock(common_dir, blocking=True, timeout=lock_timeout):
            evidence = roots.finish_session_evidence(
                root, confirming_session_key=ckey,
                branch=branch, common_dir=common_dir, lock_held=True)
            if not evidence.get("ok"):
                detail = str(evidence.get("detail") or evidence.get("reason") or "malformed")
                return {"ok": False, "reason": "session_malformed",
                        "rows": f"None | Cannot preview: {detail}."}
            try:
                physical_before = capture_physical_incarnations(root, git_dir)
            except FinishError as exc:
                return {"ok": False, "reason": "physical_identity_unavailable",
                        "rows": f"None | Cannot preview: {str(exc).split(':', 1)[0]}."}
            inv = build_inventory(root, git_dir)
            if not inv["safe"]:
                return {"ok": False, "reason": f"inventory_{inv['refuse_reason']}",
                        "rows": f"None | Cannot preview: {inv['refuse_reason']}."}
            membership = list(evidence.get("membership") or [])
            try:
                physical_after = capture_physical_incarnations(root, git_dir)
            except FinishError as exc:
                return {"ok": False, "reason": "physical_identity_unavailable",
                        "rows": f"None | Cannot preview: {str(exc).split(':', 1)[0]}."}
            if physical_after != physical_before:
                return {"ok": False, "reason": "physical_identity_drift",
                        "rows": "None | Cannot preview: physical_identity_drift."}
            root_incarnation, git_dir_incarnation = physical_after
            fp = compute_fingerprint(inv, root=root, git_dir=git_dir, common_dir=common_dir,
                                     branch=branch, head=head, membership=membership,
                                     root_incarnation=root_incarnation,
                                     git_dir_incarnation=git_dir_incarnation)
            ch = create_challenge(
                conversation_id=conversation_id, root=root, git_dir=git_dir,
                common_dir=common_dir, branch=branch, head=head, fingerprint=fp,
                markers=inv["markers"], operation_digest=inv["operation_digest"],
                membership=membership, session_id=session_id,
                root_incarnation=root_incarnation,
                git_dir_incarnation=git_dir_incarnation, hook_mode=hook_mode)
    except LockBusy:
        return {"ok": False, "reason": "lock_busy",
                "rows": "None | Cannot preview: lock_busy."}
    visible = [{"path": e["display"], "sentence": e["sentence"], "class": e["class"]}
               for e in inv["entries"] if not e["hidden"] and not e.get("retained")]
    return {
        "ok": True,
        "reason": "preview",
        "fingerprint": fp,
        "nonce": ch["nonce"],
        "generation": ch["generation"],
        "hook_mode": bool(hook_mode),
        "conversation_id": conversation_id or "",
        "discard_count": len(inv["entries"]),
        "visible_count": len(visible),
        "markers": inv["markers"],
        "rows": render_rows(inv),
        "visible": visible,
    }


# ---- CLI (invoked by the shell kernel) --------------------------------------------------
def _print(obj) -> int:
    json.dump(obj, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def _public_inventory(inv: dict) -> dict:
    """Diagnostic inventory projection: never expose private hashes, link targets, or raw bytes."""
    public_entries = []
    for entry in inv.get("entries") or []:
        projected = {
            key: entry[key]
            for key in (
                "code", "class", "kind", "size", "hidden", "template_id",
                "sentence", "display", "retained", "commit_eligible",
                "retain_eligible")
            if key in entry
        }
        # Preserve the established operator-row key. Private encoded paths, hashes, targets, and
        # grouped descendants remain omitted.
        projected["path"] = str(entry.get("path") or "")
        if entry.get("kind") == "empty_dir_tree":
            projected["tree_member_count"] = len(entry.get("tree_members") or [])
        public_entries.append(projected)
    return {
        "safe": bool(inv.get("safe")),
        "refuse_reason": str(inv.get("refuse_reason") or ""),
        "entries": public_entries,
        "markers": list(inv.get("markers") or []),
        "object_count": len(inv.get("objects") or []),
    }


def _common_target_args(sp) -> None:
    sp.add_argument("--root", required=True)
    sp.add_argument("--git-dir", dest="git_dir", required=True)
    sp.add_argument("--common-dir", dest="common_dir", required=True)
    sp.add_argument("--branch", required=True)
    sp.add_argument("--head", required=True)
    sp.add_argument("--session-id", dest="session_id", default="")
    sp.add_argument("--conversation-id", dest="conversation_id", default="")


def main(argv: list | None = None) -> int:
    p = ClosedArgumentParser(
        prog="awa_finish",
        description="AWA kernel: deterministic root-bound worktree finish")
    sub = p.add_subparsers(dest="cmd", required=True)

    rt = sub.add_parser("resolve-target", help="resolve one exact linked-worktree target")
    rt.add_argument("--root", required=True)

    inv = sub.add_parser("inventory", help="canonical inventory JSON")
    inv.add_argument("--root", required=True)
    inv.add_argument("--git-dir", dest="git_dir", required=True)

    rr = sub.add_parser("render-rows", help="plain escaped operator rows")
    rr.add_argument("--root", required=True)
    rr.add_argument("--git-dir", dest="git_dir", required=True)

    fp = sub.add_parser("fingerprint", help="stable content fingerprint")
    _common_target_args(fp)

    pv = sub.add_parser("preview", help="inventory + fingerprint + create pending challenge")
    _common_target_args(pv)
    pv.add_argument("--hook-mode", action="store_true")

    cr = sub.add_parser("challenge-read", help="read the current pending challenge")
    cr.add_argument("--conversation-id", dest="conversation_id", default="")
    cr.add_argument("--ttl", type=int, default=None)

    cc = sub.add_parser("challenge-consume", help="consume (delete) the pending challenge")
    cc.add_argument("--conversation-id", dest="conversation_id", default="")

    cd = sub.add_parser("challenge-delete", help="cancel = delete the pending challenge")
    cd.add_argument("--conversation-id", dest="conversation_id", default="")
    cd.add_argument("--nonce", default=None)
    cd.add_argument("--generation", type=int, default=None)

    ca = sub.add_parser("challenge-cancel", help="kernel-validated challenge CAS cancel")
    ca.add_argument("--conversation-id", required=True)
    ca.add_argument("--common-dir", required=True)
    ca.add_argument("--root", required=True)
    ca.add_argument("--session-id", required=True)
    ca.add_argument("--nonce", required=True)
    ca.add_argument("--generation", required=True, type=int)

    ha = sub.add_parser("hook-activate", help="activate hook challenge from consumed envelope")
    ha.add_argument("--conversation-id", required=True)
    ha.add_argument("--common-dir", required=True)
    ha.add_argument("--root", required=True)
    ha.add_argument("--session-id", required=True)
    ha.add_argument("--nonce", required=True)
    ha.add_argument("--generation", required=True, type=int)
    ha.add_argument("--choice", required=True)
    ha.add_argument("--envelope-digest", required=True)

    hp = sub.add_parser("hook-publish", help="CAS-mark a fully emitted hook warning")
    hp.add_argument("--conversation-id", required=True)
    hp.add_argument("--common-dir", required=True)
    hp.add_argument("--root", required=True)
    hp.add_argument("--session-id", required=True)
    hp.add_argument("--nonce", required=True)
    hp.add_argument("--generation", required=True, type=int)

    ss = sub.add_parser("selected-snapshot", help="canonical selected source snapshot")
    ss.add_argument("--root", required=True)
    ss.add_argument("--path", action="append", required=True)

    au = sub.add_parser("authorize", help="check literal Close + fingerprint (no consume)")
    _common_target_args(au)
    au.add_argument("--answer", default="")
    au.add_argument("--ttl", type=int, default=None)

    bd = sub.add_parser("branch-disposition", help="network-free local-ref branch decision")
    bd.add_argument("--root", required=True)
    bd.add_argument("--branch", required=True)
    bd.add_argument("--head", required=True)
    bd.add_argument("--common-dir", dest="common_dir", required=True)

    fx = sub.add_parser("finish-execute", help="the destructive finish path (under the lock)")
    _common_target_args(fx)
    fx.add_argument("--answer", default="")
    fx.add_argument("--expected-nonce", dest="expected_nonce", default=None)
    fx.add_argument("--expected-generation", dest="expected_generation", type=int, default=None)
    fx.add_argument("--ttl", type=int, default=None)
    fx.add_argument("--lock-timeout", dest="lock_timeout", type=_finite_float, default=30.0)

    fr = sub.add_parser("finish-reconcile", help="reconcile a crash-interrupted finish")
    _common_target_args(fr)
    fr.add_argument("--expected-nonce", dest="expected_nonce", default=None)
    fr.add_argument("--expected-generation", dest="expected_generation", type=int, default=None)
    fr.add_argument("--lock-timeout", dest="lock_timeout", type=_finite_float, default=30.0)

    lp = sub.add_parser("lock-path", help="print the per-common-dir lockfile path (ABI)")
    lp.add_argument("--common-dir", dest="common_dir", required=True)

    le = sub.add_parser("lock-ensure",
                        help="ensure the locks dir + lockfile exist (700/600) and print the path")
    le.add_argument("--common-dir", dest="common_dir", required=True)

    ff = sub.add_parser("flock-fd",
                        help="LOCK_EX an inherited fd and return (shell holds it open); busy -> exit 75")
    ff.add_argument("--fd", type=int, required=True)
    ff.add_argument("--timeout", type=_finite_float, default=30.0)

    sub.add_parser("finish-dir", help="print the finish storage dir")

    try:
        args = p.parse_args(argv)
    except ClosedArgumentError:
        _print({
            "outcome": "refused",
            "reason": "finish_error",
            "message": "finish request arguments were invalid",
        })
        return 2

    try:
        if args.cmd == "resolve-target":
            return _print(resolve_target(args.root))
        if args.cmd == "inventory":
            return _print(_public_inventory(build_inventory(args.root, args.git_dir)))
        if args.cmd == "render-rows":
            i = build_inventory(args.root, args.git_dir)
            if not i["safe"]:
                sys.stdout.write(f"None | Cannot preview: {i['refuse_reason']}.\n")
                return 1
            sys.stdout.write(render_rows(i) + "\n")
            return 0
        if args.cmd == "fingerprint":
            i = build_inventory(args.root, args.git_dir)
            if not i["safe"]:
                _print({"ok": False, "reason": f"inventory_{i['refuse_reason']}"})
                return 1
            roots = _roots_module()
            ck = roots.session_key(args.session_id)
            mem = heartbeat_membership(
                args.root, ck, branch=args.branch, common_dir=args.common_dir)
            physical = capture_physical_incarnations(args.root, args.git_dir)
            fpv = compute_fingerprint(i, root=args.root, git_dir=args.git_dir,
                                      common_dir=args.common_dir, branch=args.branch,
                                      head=args.head, membership=mem,
                                      root_incarnation=physical[0],
                                      git_dir_incarnation=physical[1])
            return _print({"ok": True, "fingerprint": fpv, "membership": mem,
                           "markers": i["markers"], "discard_count": len(i["entries"])})
        if args.cmd == "preview":
            out = preview(root=args.root, git_dir=args.git_dir, common_dir=args.common_dir,
                          branch=args.branch, head=args.head, session_id=args.session_id,
                          conversation_id=args.conversation_id, hook_mode=args.hook_mode)
            _print(out)
            return 0 if out.get("ok") else 1
        if args.cmd == "challenge-read":
            ch, status = read_challenge(args.conversation_id, ttl=args.ttl)
            _print({"status": status, "challenge": ch})
            return 0 if status == "ok" else 1
        if args.cmd == "challenge-consume":
            return _print({"consumed": consume_challenge(args.conversation_id)})
        if args.cmd == "challenge-delete":
            return _print({"deleted": delete_challenge(
                args.conversation_id, expected_nonce=args.nonce,
                expected_generation=args.generation)})
        if args.cmd == "challenge-cancel":
            out = cancel_challenge(
                conversation_id=args.conversation_id, common_dir=args.common_dir,
                root=args.root, session_id=args.session_id, nonce=args.nonce,
                generation=args.generation)
            _print(out)
            return 0 if out.get("ok") else 1
        if args.cmd == "hook-activate":
            out = activate_hook_challenge(
                conversation_id=args.conversation_id, common_dir=args.common_dir,
                root=args.root, session_id=args.session_id, nonce=args.nonce,
                generation=args.generation, choice=args.choice,
                envelope_digest=args.envelope_digest)
            _print(out)
            return 0 if out.get("ok") else 1
        if args.cmd == "hook-publish":
            out = publish_hook_challenge(
                conversation_id=args.conversation_id, common_dir=args.common_dir,
                root=args.root, session_id=args.session_id, nonce=args.nonce,
                generation=args.generation)
            _print(out)
            return 0 if out.get("ok") else 1
        if args.cmd == "selected-snapshot":
            return _print(selected_snapshot(args.root, args.path))
        if args.cmd == "authorize":
            ch, status = read_challenge(args.conversation_id, ttl=args.ttl)
            if status != "ok" or ch is None:
                _print({"authorized": False, "reason": f"challenge_{status}"})
                return 1
            i = build_inventory(args.root, args.git_dir)
            if not i["safe"]:
                _print({"authorized": False, "reason": f"inventory_{i['refuse_reason']}"})
                return 1
            roots = _roots_module()
            ck = roots.session_key(args.session_id)
            mem = heartbeat_membership(
                args.root, ck, branch=args.branch, common_dir=args.common_dir)
            physical = capture_physical_incarnations(args.root, args.git_dir)
            fpv = compute_fingerprint(i, root=args.root, git_dir=args.git_dir,
                                      common_dir=args.common_dir, branch=args.branch,
                                      head=args.head, membership=mem,
                                      root_incarnation=physical[0],
                                      git_dir_incarnation=physical[1])
            ok, why = authorize(args.answer, ch, current_fingerprint=fpv)
            _print({"authorized": ok, "reason": why, "fingerprint": fpv})
            return 0 if ok else 1
        if args.cmd == "branch-disposition":
            return _print(branch_disposition(args.root, args.branch, args.head, args.common_dir))
        if args.cmd == "finish-execute":
            out = finish_execute(root=args.root, git_dir=args.git_dir, common_dir=args.common_dir,
                                 branch=args.branch, head=args.head, session_id=args.session_id,
                                 conversation_id=args.conversation_id, answer=args.answer,
                                 expected_nonce=args.expected_nonce,
                                 expected_generation=args.expected_generation,
                                 challenge_ttl=args.ttl, lock_timeout=args.lock_timeout)
            _print(out)
            return 0 if out.get("outcome") == "removed" else 1
        if args.cmd == "finish-reconcile":
            out = reconcile_removal(
                root=args.root, git_dir=args.git_dir, common_dir=args.common_dir,
                branch=args.branch, head=args.head, session_id=args.session_id,
                conversation_id=args.conversation_id,
                expected_nonce=args.expected_nonce,
                expected_generation=args.expected_generation,
                lock_timeout=args.lock_timeout)
            _print(out)
            return 0 if out.get("outcome") == "removed" else 1
        if args.cmd == "lock-path":
            sys.stdout.write(lockfile_for(args.common_dir) + "\n")
            return 0
        if args.cmd == "lock-ensure":
            # Create the locks dir (700) + the lockfile (600) with the SAME perms common_dir_lock
            # uses, so the shell's `exec N>"$lf"` opens an already byte-identical lockfile.
            _ensure_dir(locks_dir())
            lf = lockfile_for(args.common_dir)
            lfd = os.open(lf, os.O_RDWR | os.O_CREAT, FILE_MODE)
            try:
                os.chmod(lf, FILE_MODE)
            except OSError:
                pass
            os.close(lfd)
            sys.stdout.write(lf + "\n")
            return 0
        if args.cmd == "flock-fd":
            # RAW exit code (no JSON): 0 acquired, 75 busy, 1 error. Not wrapped by the JSON
            # fail-safe below so the shell can distinguish busy (clean_lock_busy) from error.
            return _flock_inherited_fd(args.fd, args.timeout)
        if args.cmd == "finish-dir":
            sys.stdout.write(finish_dir() + "\n")
            return 0
    except LockBusy:
        _print({
            "outcome": "refused", "reason": "lock_busy",
            "message": "another local action is in progress",
        })
        return 1
    except FinishError:
        _print({
            "outcome": "refused", "reason": "finish_error",
            "message": "finish could not be completed safely",
        })
        return 1
    except Exception:  # noqa: BLE001 — fail-safe: never a spurious success
        _print({
            "outcome": "error", "reason": "unexpected",
            "message": "finish could not be completed safely",
        })
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
