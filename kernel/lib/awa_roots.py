#!/usr/bin/env python3
"""awa_roots.py — canonical per-root disposition + heartbeat + clean receipts (AWA kernel).

KERNEL-OWNED, engine-OFF, router-OFF: stdlib only, ZERO imports of the engine package or
any router artifact. Invoked BY the shell kernel (dev-worktree.sh / worktree-session.sh)
exactly like awa_policy.py, so the safety behavior holds with the Python engine off and
with no router installed. This module is the SINGLE SOURCE OF TRUTH (canonical disposition)
for three kernel-owned concerns:

  * a Safe-Workspace ROOT's disposition — one of active | stale | dead | untracked | absent;
  * the per-root ``active_root/v1`` heartbeat record (write/refresh/read/remove);
  * the ``clean_receipt/v1`` durable record written on EVERY terminal ``clean`` path
    (removed / refused / error) — a new clean path that fails to classify a disposition
    records a FAIL-SAFE refusal receipt, never a silent success.

Storage lives under ``${XDG_STATE_HOME:-~/.local/state}/awa`` on local disk (dirs 700,
files 600 — S4). Heartbeat liveness prefers a strong signal (recorded owning process alive
on the SAME boot) and otherwise falls back to a TTL on the last heartbeat. Only ``off``-like
absence of evidence is ever treated as safe: UNKNOWN evidence (an unreadable record, an
unparseable heartbeat time) resolves to ``active`` so it BLOCKS removal.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
import platform
import re
import stat
import subprocess
import sys
import time

# ---- schema strings (frozen, additive-within AWA contract v1) ---------------------------
SCHEMA_ACTIVE_ROOT = "active_root/v1"
SCHEMA_CLEAN_RECEIPT = "clean_receipt/v1"
SCHEMA_CURRENT_SESSION = "awa_current_session/v1"

# Exact keysets emitted by the v1 writers.  The ordinary disposition reader deliberately remains
# permissive for additive-within-v1 compatibility; finish-only readers validate these strictly
# because malformed session identity must never be waived on a destructive finish path.
ACTIVE_SESSION_KEYS = frozenset({
    "session_id", "pid", "boot_id", "branch", "git_common_dir",
    "first_seen", "last_heartbeat", "last_heartbeat_epoch",
})
CURRENT_SESSION_KEYS = frozenset({
    "schema", "root", "session_id", "conversation_id", "session_key",
    "branch", "common_dir", "boot_id", "updated_at_epoch",
})

# ---- canonical root disposition vocabulary ----------------------------------------------
DISP_ACTIVE = "active"        # a live session's Safe Workspace -> BLOCKS removal
DISP_STALE = "stale"          # heartbeat TTL-expired / owner gone -> does NOT block
DISP_DEAD = "dead"            # a recorded root whose path no longer exists -> session guidance
DISP_UNTRACKED = "untracked"  # path exists, no heartbeat record -> does NOT block
DISP_ABSENT = "absent"        # no record and no path
ROOT_DISPOSITIONS = (DISP_ACTIVE, DISP_STALE, DISP_DEAD, DISP_UNTRACKED, DISP_ABSENT)

# ---- clean receipt disposition vocabulary -----------------------------------------------
CLEAN_REMOVED = "removed"
CLEAN_REFUSED = "refused"
CLEAN_ERROR = "error"
CLEAN_DISPOSITIONS = (CLEAN_REMOVED, CLEAN_REFUSED, CLEAN_ERROR)

DIR_MODE = 0o700
FILE_MODE = 0o600

# Default heartbeat TTL. A root whose last heartbeat is younger than this (and whose owning
# process cannot be proven dead) is treated as ACTIVE. Deliberately generous: the guard hot-path
# refresh + a sessionStart refresh should comfortably cover a normal working session, and the
# fail-safe direction is to BLOCK removal of a possibly-in-use workspace. Tunable via
# AWA_HEARTBEAT_TTL_SECONDS, but CLAMPED (see _ttl_seconds) so a stray env export can never
# silently DISABLE protection.
DEFAULT_TTL_SECONDS = 12 * 3600
# Floor for an operator-supplied TTL: a value below this is clamped up, and <=0 / non-integer is
# treated as "use the default" (MINOR #6 — a `AWA_HEARTBEAT_TTL_SECONDS=0` export must NOT make
# every pid-less heartbeat instantly stale/removable).
MIN_TTL_SECONDS = 300


def _ttl_seconds(override: int | None = None) -> int:
    if override is not None:
        # TRUSTED programmatic override (internal re-reads / unit tests): NOT clamped, so a test
        # may still force stale with ttl=0. The safety-critical clean gate never passes an
        # override — it goes through the CLAMPED env/default path below.
        return max(0, int(override))
    raw = os.environ.get("AWA_HEARTBEAT_TTL_SECONDS", "").strip()
    if raw:
        try:
            val = int(raw)
        except ValueError:
            sys.stderr.write(
                f"awa_roots: ignoring non-integer AWA_HEARTBEAT_TTL_SECONDS={raw!r}; "
                f"using default {DEFAULT_TTL_SECONDS}s\n")
            return DEFAULT_TTL_SECONDS
        if val <= 0:
            sys.stderr.write(
                f"awa_roots: AWA_HEARTBEAT_TTL_SECONDS={val} would disable protection; "
                f"using default {DEFAULT_TTL_SECONDS}s\n")
            return DEFAULT_TTL_SECONDS
        if val < MIN_TTL_SECONDS:
            sys.stderr.write(
                f"awa_roots: clamping AWA_HEARTBEAT_TTL_SECONDS={val} up to floor "
                f"{MIN_TTL_SECONDS}s\n")
            return MIN_TTL_SECONDS
        return val
    return DEFAULT_TTL_SECONDS


# ---- storage paths (XDG-anchored, local disk) -------------------------------------------
def _state_home() -> str:
    val = os.environ.get("XDG_STATE_HOME", "").strip()
    if val:
        return os.path.expanduser(val)
    return os.path.join(os.path.expanduser("~"), ".local", "state")


def awa_state_dir() -> str:
    return os.path.join(_state_home(), "awa")


def roots_dir() -> str:
    return os.path.join(awa_state_dir(), "roots")


def receipts_dir() -> str:
    return os.path.join(awa_state_dir(), "receipts")


def current_sessions_dir() -> str:
    return os.path.join(awa_state_dir(), "current-session")


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
    spec = importlib.util.spec_from_file_location("awa_durability_for_roots", path)
    if spec is None or spec.loader is None:
        raise OSError(f"cannot load AWA durability kernel lib: {path}")
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
    """Sample the wall clock once, then derive every representation from that sample."""
    epoch = _now_epoch()
    return epoch, _iso_from_epoch(epoch)


def _iso_to_epoch(value) -> int | None:
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str) and value:
        try:
            import calendar
            return calendar.timegm(time.strptime(value, "%Y-%m-%dT%H:%M:%SZ"))
        except (ValueError, TypeError):
            return None
    return None


def _strict_positive_epoch(value) -> int | None:
    """Finish-state epochs are exact positive integers; bool/float/string coercion is forbidden."""
    return value if type(value) is int and value > 0 else None


def _strict_iso_epoch(value) -> int | None:
    """Parse only the writer's exact UTC timestamp representation."""
    if not isinstance(value, str) or not value:
        return None
    return _iso_to_epoch(value)


def _timestamp_pair_state(iso_value, epoch_value) -> tuple[str, int | None]:
    """Classify a dual timestamp.

    Writers are exact. A one-second difference is the sole recognized legacy shape from the old
    two-clock-call writer and is normalized by the next locked writer. Larger/malformed differences
    remain invalid evidence.
    """
    iso_epoch = _strict_iso_epoch(iso_value)
    epoch = _strict_positive_epoch(epoch_value)
    if iso_epoch is None or epoch is None:
        return "invalid", None
    if iso_epoch == epoch:
        return "exact", epoch
    if abs(iso_epoch - epoch) == 1:
        return "legacy_skew", epoch
    return "invalid", None


def boot_id() -> str:
    """Per-boot nonce, stable across a machine's uptime (independent of engine/identity.py so
    the kernel path never imports the engine). Linux boot_id, macOS kern.boottime, else uname."""
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
            if out and "sec" in out:
                digits = "".join(c for c in out.split("sec")[1] if c.isdigit())
                return f"darwin-boot-{digits or out}"
        except (OSError, subprocess.SubprocessError, IndexError):
            pass
    return "uname-" + hashlib.sha256(
        (platform.node() + platform.version()).encode("utf-8")
    ).hexdigest()[:16]


def _slug(name: str) -> str:
    import re
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-.")
    return s.lower() or "root"


def canon(path: str) -> str:
    """Canonical root path: expanduser + realpath (resolve symlinks). MUST match the kernel
    clean gate, which canonicalizes the worktree with `pwd -P` before looking up disposition —
    otherwise a symlinked prefix (e.g. macOS /tmp -> /private/tmp) keys the heartbeat and the
    clean gate to DIFFERENT records and an active root would not block."""
    return os.path.realpath(os.path.abspath(os.path.expanduser(path)))


def root_key(root_path: str) -> str:
    """Filesystem-safe, collision-resistant key for a root path (slug + realpath hash)."""
    ap = canon(root_path)
    digest = hashlib.sha256(ap.encode("utf-8")).hexdigest()[:16]
    return f"{_slug(os.path.basename(ap.rstrip(os.sep)) or 'root')}-{digest}"


def session_key(session_id) -> str:
    """Stable per-session key for the additive ``sessions`` map. A present session_id hashes to a
    short key; an absent/empty session_id maps to a single stable ``unattributed`` bucket (so many
    pid-less hookless callers do not each mint a distinct session and inflate finish membership).
    Used by BOTH the heartbeat writer and the finish gate so they agree on the confirming key."""
    sid = session_id.strip() if isinstance(session_id, str) else ""
    if not sid:
        return "unattributed"
    return "s-" + hashlib.sha256(sid.encode("utf-8")).hexdigest()[:20]


def record_path(root_path: str) -> str:
    return os.path.join(roots_dir(), f"{root_key(root_path)}.json")


def current_session_path(root_path: str) -> str:
    return os.path.join(current_sessions_dir(), f"{root_key(root_path)}.json")


def _common_dir_key(common_dir: str) -> str:
    return hashlib.sha256(os.path.abspath(common_dir).encode("utf-8")).hexdigest()[:24]


@contextmanager
def _common_dir_lock(common_dir: str, timeout: float = 5.0):
    """Use the one shared kernel/engine per-common-dir lock ABI."""
    _ensure_dir(locks_dir())
    path = os.path.join(locks_dir(), f"common-{_common_dir_key(common_dir)}.lock")
    fd = os.open(path, os.O_RDWR | os.O_CREAT, FILE_MODE)
    os.chmod(path, FILE_MODE)
    deadline = time.monotonic() + max(0.0, timeout)
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("common directory lock busy")
                time.sleep(0.025)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _current_session_record(root_path: str, *, session_id: str, conversation_id: str,
                            branch: str, common_dir: str) -> dict:
    values = (session_id, branch, common_dir)
    if not all(isinstance(value, str) and value.strip() for value in values):
        raise ValueError("session, branch, and common directory required")
    if not isinstance(conversation_id, str):
        raise ValueError("conversation identity must be a string")
    return {
        "schema": SCHEMA_CURRENT_SESSION,
        "root": canon(root_path),
        "session_id": session_id.strip(),
        "conversation_id": conversation_id.strip(),
        "session_key": session_key(session_id),
        "branch": branch.strip(),
        "common_dir": os.path.abspath(common_dir),
        "boot_id": boot_id(),
        "updated_at_epoch": _now_epoch(),
    }


def write_current_session(root_path: str, *, session_id: str, conversation_id: str,
                          branch: str, common_dir: str) -> dict:
    """Write the one root-bound Desktop identity used by guard and current dispatch."""
    if not isinstance(conversation_id, str) or not conversation_id.strip():
        raise ValueError("complete current session identity required")
    rec = _current_session_record(
        root_path, session_id=session_id, conversation_id=conversation_id,
        branch=branch, common_dir=common_dir)
    with _common_dir_lock(common_dir):
        target_ok, target_reason = _heartbeat_target_recheck(
            root_path, branch=branch, common_dir=common_dir, require_linked=True)
        if not target_ok:
            raise ValueError("current_session_target_" + target_reason)
        _write_current_session_locked(root_path, rec)
    return rec


def _write_current_session_locked(root_path: str, rec: dict) -> None:
    """Write a validated current-session record while the common-dir lock is held."""
    _write_private(current_session_path(root_path),
                   json.dumps(rec, indent=2, sort_keys=True) + "\n")


def _read_current_session(root_path: str, *, allow_partial: bool = False,
                          expected_boot_id: str | None = None) -> tuple:
    path = current_session_path(root_path)
    try:
        _durability_module().adopt_visible(path)
        with open(path, encoding="utf-8") as fh:
            rec = json.load(fh)
    except FileNotFoundError:
        return None, "absent"
    except (OSError, json.JSONDecodeError):
        return None, "malformed"
    if (not isinstance(rec, dict) or set(rec) != CURRENT_SESSION_KEYS
            or rec.get("schema") != SCHEMA_CURRENT_SESSION
            or rec.get("root") != canon(root_path)
            or not isinstance(rec.get("boot_id"), str) or not rec.get("boot_id")
            or not isinstance(rec.get("session_id"), str)
            or not rec.get("session_id") or rec.get("session_id") != rec.get("session_id").strip()
            or rec.get("session_key") != session_key(rec.get("session_id"))
            or not isinstance(rec.get("conversation_id"), str)
            or not isinstance(rec.get("branch"), str)
            or not rec.get("branch") or rec.get("branch") != rec.get("branch").strip()
            or not isinstance(rec.get("common_dir"), str)
            or not rec.get("common_dir")
            or rec.get("common_dir") != os.path.abspath(rec.get("common_dir"))
            or _strict_positive_epoch(rec.get("updated_at_epoch")) is None):
        return None, "malformed"
    expected_boot = expected_boot_id if expected_boot_id is not None else boot_id()
    prior_boot = rec.get("boot_id") != expected_boot
    if not rec.get("conversation_id"):
        status = "partial_prior_boot" if prior_boot else "partial"
        return (rec, status) if allow_partial else (None, status)
    return rec, "prior_boot" if prior_boot else "ok"


def read_current_session(root_path: str) -> tuple:
    return _read_current_session(root_path)


def bind_current_session(root_path: str, *, session_id: str, conversation_id: str,
                         branch: str, common_dir: str, source: str,
                         lock_timeout: float = 5.0) -> dict:
    """CAS-bind one root/session, attaching the first real prompt conversation when needed.

    sessionStart may replace a previous session but never clears an already attached conversation
    for the same session. beforeSubmitPrompt may create an absent binding or attach only to its
    exact session; it never adopts another session or conversation.
    """
    if source not in {"sessionStart", "beforeSubmitPrompt"}:
        raise ValueError("unsupported current session bind source")
    incoming = _current_session_record(
        root_path, session_id=session_id, conversation_id=conversation_id,
        branch=branch, common_dir=common_dir)
    if source == "beforeSubmitPrompt" and not incoming["conversation_id"]:
        return {"ok": False, "reason": "conversation_missing"}
    try:
        with _common_dir_lock(common_dir, timeout=lock_timeout):
            target_ok, target_reason = _heartbeat_target_recheck(
                root_path, branch=branch, common_dir=common_dir, require_linked=True)
            if not target_ok:
                return {"ok": False, "reason": "current_session_target_" + target_reason}
            prior, status = _read_current_session(root_path, allow_partial=True)
            if status == "malformed":
                return {"ok": False, "reason": "current_session_malformed"}
            replaced_prior_boot = status in {"prior_boot", "partial_prior_boot"}
            if replaced_prior_boot:
                # A structurally valid projection from a prior boot has no current-session
                # authority. The live linked-target recheck above makes replacing it safe.
                prior = None
            if prior is not None:
                same_target = (
                    prior.get("root") == incoming["root"]
                    and prior.get("branch") == incoming["branch"]
                    and os.path.abspath(prior.get("common_dir", ""))
                    == incoming["common_dir"])
                if not same_target:
                    return {"ok": False, "reason": "current_session_target_mismatch"}
                if source == "beforeSubmitPrompt" and prior["session_id"] != incoming["session_id"]:
                    return {"ok": False, "reason": "current_session_session_mismatch"}
                if prior["session_id"] == incoming["session_id"]:
                    prior_conversation = prior.get("conversation_id", "")
                    incoming_conversation = incoming["conversation_id"]
                    if (prior_conversation and incoming_conversation
                            and prior_conversation != incoming_conversation):
                        return {"ok": False, "reason": "current_session_conversation_mismatch"}
                    incoming["conversation_id"] = (
                        incoming_conversation or prior_conversation)
            _write_current_session_locked(root_path, incoming)
            return {
                "ok": True,
                "reason": "replaced_prior_boot" if replaced_prior_boot else (
                    "bound" if status == "absent" else (
                    "conversation_attached" if status == "partial"
                    and bool(incoming["conversation_id"]) else "matched")),
                "created": status == "absent",
                "replaced_prior_boot": replaced_prior_boot,
                "current_session": incoming,
            }
    except TimeoutError:
        return {"ok": False, "reason": "current_session_lock_busy"}


def _remove_current_session_cas_locked(
        root_path: str, *, session_id: str, conversation_id: str, branch: str,
        common_dir: str, expected_boot_id: str | None = None) -> dict:
    """Delete only the exact removed operation's current-session identity.

    A replacement record is a successful no-op (``superseded``), never something this cleanup may
    unlink. Malformed/unreadable state remains present and is surfaced as a cleanup failure.
    """
    rec, status = _read_current_session(root_path, allow_partial=True)
    if status == "absent":
        return {"ok": True, "reason": "absent", "removed": False}
    if status not in {"ok", "partial", "prior_boot", "partial_prior_boot"} or rec is None:
        return {"ok": False, "reason": f"current_session_{status}", "removed": False}
    expected = {
        "root": canon(root_path),
        "session_id": session_id,
        "conversation_id": conversation_id,
        "session_key": session_key(session_id),
        "branch": branch,
        "common_dir": os.path.abspath(common_dir),
    }
    if any(rec.get(key) != value for key, value in expected.items()):
        return {"ok": True, "reason": "superseded", "removed": False}
    expected_boot = expected_boot_id if expected_boot_id is not None else boot_id()
    if rec.get("boot_id") != expected_boot:
        return {"ok": True, "reason": "superseded", "removed": False}
    path = current_session_path(root_path)
    try:
        _durability_module().durable_unlink(path, missing_ok=False)
    except OSError:
        return {"ok": False, "reason": "current_session_unlink_failed", "removed": False}
    if os.path.lexists(path):
        return {"ok": False, "reason": "current_session_still_present", "removed": False}
    return {"ok": True, "reason": "cleared", "removed": True}


def remove_current_session_cas(
        root_path: str, *, session_id: str, conversation_id: str, branch: str,
        common_dir: str, expected_boot_id: str | None = None,
        lock_held: bool = False, lock_timeout: float = 5.0) -> dict:
    """Lock-safe exact-identity CAS cleanup for ``awa_current_session/v1``."""
    if lock_held:
        return _remove_current_session_cas_locked(
            root_path, session_id=session_id, conversation_id=conversation_id,
            branch=branch, common_dir=common_dir, expected_boot_id=expected_boot_id)
    try:
        with _common_dir_lock(common_dir, timeout=lock_timeout):
            return _remove_current_session_cas_locked(
                root_path, session_id=session_id, conversation_id=conversation_id,
                branch=branch, common_dir=common_dir, expected_boot_id=expected_boot_id)
    except TimeoutError:
        return {"ok": False, "reason": "current_session_lock_busy", "removed": False}


def _pid_alive(pid) -> bool:
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but not ours
    except OSError:
        return False
    return True


def read_record(root_path: str) -> tuple[dict | None, bool]:
    """Return (record, corrupt). corrupt=True means the file exists but is unreadable/invalid
    JSON — treated as UNKNOWN evidence by disposition() (fail-safe active)."""
    rp = record_path(root_path)
    try:
        _durability_module().adopt_visible(rp)
        with open(rp, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data, False
        return None, True
    except FileNotFoundError:
        return None, False
    except (OSError, json.JSONDecodeError):
        return None, True


def _synthesize_legacy_session(prior: dict) -> dict:
    """Turn a pre-migration single-session record's top-level fields into ONE ``sessions`` entry so
    a legacy heartbeat is never silently dropped from finish membership on the first re-write/read."""
    return {
        session_key(prior.get("session_id")): {
            "session_id": prior.get("session_id"),
            "pid": prior.get("pid"),
            "boot_id": prior.get("boot_id"),
            "branch": prior.get("branch"),
            "git_common_dir": prior.get("git_common_dir"),
            "first_seen": prior.get("first_seen"),
            "last_heartbeat": prior.get("last_heartbeat"),
            "last_heartbeat_epoch": prior.get("last_heartbeat_epoch"),
        }
    }


def _valid_optional_pid(value) -> bool:
    return value is None or (type(value) is int and value > 0)


def _valid_optional_identity(value) -> bool:
    return value is None or (isinstance(value, str) and value == value.strip())


def _validate_session_member(skey: str, sess: dict) -> tuple[bool, str]:
    if not isinstance(skey, str) or not skey or not isinstance(sess, dict):
        return False, "session_member_not_object"
    if set(sess) != ACTIVE_SESSION_KEYS:
        return False, "session_member_keyset_invalid"
    sid = sess.get("session_id")
    if not _finish_session_identity_valid(sid) or skey != session_key(sid):
        return False, "session_key_identity_mismatch"
    if not _valid_optional_pid(sess.get("pid")):
        return False, "session_pid_invalid"
    if not isinstance(sess.get("boot_id"), str) or not sess.get("boot_id"):
        return False, "session_boot_invalid"
    if not _valid_optional_identity(sess.get("branch")):
        return False, "session_branch_invalid"
    common = sess.get("git_common_dir")
    if not _valid_optional_identity(common):
        return False, "session_common_dir_invalid"
    if isinstance(common, str) and common and common != os.path.abspath(common):
        return False, "session_common_dir_not_absolute"
    first = _strict_iso_epoch(sess.get("first_seen"))
    timestamp_state, last_epoch = _timestamp_pair_state(
        sess.get("last_heartbeat"), sess.get("last_heartbeat_epoch"))
    if (first is None or timestamp_state == "invalid" or last_epoch is None
            or first > last_epoch
            or last_epoch > _now_epoch() + 5):
        return False, "session_timestamp_invalid"
    return True, "ok"


def _validate_record_for_heartbeat_merge(root_path: str, prior: dict) -> tuple[bool, str, dict]:
    """Strictly validate existing evidence before a heartbeat may merge it.

    Corrupt or semantically malformed bytes are never repaired by a convenience hook. A valid
    pre-sessions legacy record is the sole migration case and is returned with one synthesized
    member for the writer to persist under the same lock.
    """
    ap = canon(root_path)
    if not isinstance(prior, dict):
        return False, "record_not_object", {}
    if prior.get("schema") != SCHEMA_ACTIVE_ROOT or prior.get("root_path") != ap:
        return False, "record_identity_invalid", {}
    common = prior.get("git_common_dir")
    branch = prior.get("branch")
    sid = prior.get("session_id")
    if (not _valid_optional_identity(common)
            or (isinstance(common, str) and common
                and common != os.path.abspath(common))
            or not _valid_optional_identity(branch)
            or not _finish_session_identity_valid(sid)
            or not _valid_optional_pid(prior.get("pid"))
            or not isinstance(prior.get("boot_id"), str)
            or not prior.get("boot_id")):
        return False, "record_aggregate_invalid", {}
    first = _strict_iso_epoch(prior.get("first_seen"))
    timestamp_state, last_epoch = _timestamp_pair_state(
        prior.get("last_heartbeat"), prior.get("last_heartbeat_epoch"))
    if (first is None or timestamp_state == "invalid" or last_epoch is None
            or first > last_epoch
            or last_epoch > _now_epoch() + 5):
        return False, "record_timestamp_invalid", {}

    if "sessions" not in prior:
        sessions = _synthesize_legacy_session(prior)
        valid, reason = _validate_session_member(next(iter(sessions)), next(iter(sessions.values())))
        if valid:
            member = next(iter(sessions.values()))
            member_state, member_epoch = _timestamp_pair_state(
                member.get("last_heartbeat"), member.get("last_heartbeat_epoch"))
            if member_state == "legacy_skew" and member_epoch is not None:
                member["last_heartbeat"] = _iso_from_epoch(member_epoch)
        return (valid, "valid_legacy" if valid else reason, sessions if valid else {})
    raw_sessions = prior["sessions"]
    if not isinstance(raw_sessions, dict) or not raw_sessions:
        return False, "sessions_not_nonempty_object", {}
    raw_top = raw_sessions.get(session_key(sid))
    if (not isinstance(raw_top, dict)
            or raw_top.get("pid") != prior.get("pid")
            or raw_top.get("boot_id") != prior.get("boot_id")
            or raw_top.get("branch") != branch
            or raw_top.get("git_common_dir") != common
            or raw_top.get("last_heartbeat") != prior.get("last_heartbeat")
            or raw_top.get("last_heartbeat_epoch") != prior.get("last_heartbeat_epoch")):
        return False, "record_member_projection_mismatch", {}
    sessions = {}
    for skey, sess in raw_sessions.items():
        valid, reason = _validate_session_member(skey, sess)
        if not valid:
            return False, reason, {}
        normalized = dict(sess)
        member_state, member_epoch = _timestamp_pair_state(
            normalized.get("last_heartbeat"), normalized.get("last_heartbeat_epoch"))
        if member_state == "legacy_skew" and member_epoch is not None:
            normalized["last_heartbeat"] = _iso_from_epoch(member_epoch)
        sessions[skey] = normalized
    top = sessions.get(session_key(sid))
    top_last = _strict_positive_epoch(prior.get("last_heartbeat_epoch"))
    if (top is None or top.get("pid") != prior.get("pid")
            or top.get("boot_id") != prior.get("boot_id")
            or top.get("branch") != branch
            or top.get("git_common_dir") != common
            or top.get("last_heartbeat_epoch") != top_last
            or (top_last is not None
                and top.get("last_heartbeat") != _iso_from_epoch(top_last))):
        return False, "record_member_projection_mismatch", {}
    return True, "valid_current", sessions


def _sanitized_git_env(*, index_file: str | None = None) -> dict:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update({
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "LC_ALL": "C",
        "LANG": "C",
        "LANGUAGE": "C",
    })
    if index_file is not None:
        env["GIT_INDEX_FILE"] = os.path.abspath(index_file)
    return env


def _git_pointer(path: str, prefix: bytes | None = None) -> str:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode)
                or before.st_size < 1 or before.st_size > 64 * 1024):
            raise OSError("invalid git pointer")
        chunks = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(fd, remaining)
            if not chunk:
                raise OSError("short git pointer read")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(fd, 1):
            raise OSError("long git pointer read")
        after = os.fstat(fd)
    finally:
        os.close(fd)
    path_after = os.stat(path, follow_symlinks=False)
    identity = lambda value: (
        value.st_dev, value.st_ino, value.st_mode, value.st_size,
        getattr(value, "st_mtime_ns", int(value.st_mtime * 1_000_000_000)),
        getattr(value, "st_ctime_ns", int(value.st_ctime * 1_000_000_000)),
    )
    if identity(before) != identity(after) or identity(before) != identity(path_after):
        raise OSError("git pointer changed")
    raw = b"".join(chunks)
    raw = raw.rstrip(b"\r\n")
    if prefix is not None:
        if not raw.startswith(prefix):
            raise OSError("invalid git pointer prefix")
        raw = raw[len(prefix):].lstrip(b" ")
    if not raw or b"\x00" in raw or b"\n" in raw or b"\r" in raw:
        raise OSError("invalid git pointer content")
    value = os.fsdecode(raw)
    if not os.path.isabs(value):
        value = os.path.join(os.path.dirname(path), value)
    return os.path.abspath(os.path.normpath(value))


def _validated_recheck_binding(root: str, git_dir: str, common_dir: str) -> dict:
    root_st = os.lstat(root)
    if not stat.S_ISDIR(root_st.st_mode) or stat.S_ISLNK(root_st.st_mode):
        raise OSError("invalid worktree root")
    dotgit = os.path.join(root, ".git")
    bound_git = _git_pointer(dotgit, b"gitdir:")
    if bound_git != os.path.abspath(git_dir):
        raise OSError("git dir mismatch")
    if _git_pointer(os.path.join(bound_git, "gitdir")) != dotgit:
        raise OSError("git backlink mismatch")
    if _git_pointer(os.path.join(bound_git, "commondir")) != os.path.abspath(common_dir):
        raise OSError("common dir mismatch")
    for directory in (bound_git, os.path.abspath(common_dir)):
        directory_st = os.lstat(directory)
        if (not stat.S_ISDIR(directory_st.st_mode)
                or stat.S_ISLNK(directory_st.st_mode)):
            raise OSError("invalid git administration directory")
    index_file = os.path.join(bound_git, "index")
    index_st = os.lstat(index_file)
    if not stat.S_ISREG(index_st.st_mode) or stat.S_ISLNK(index_st.st_mode):
        raise OSError("invalid worktree index")
    return {
        "root": root,
        "git_dir": bound_git,
        "common_dir": os.path.abspath(common_dir),
        "index_file": index_file,
    }


def _detached_operation_branch(binding: dict) -> str | None:
    """Read the narrow original-branch descriptors used by detached rebase/bisect."""
    candidates = []
    descriptors = []
    if os.path.isdir(os.path.join(binding["git_dir"], "rebase-merge")):
        descriptors.append(os.path.join(binding["git_dir"], "rebase-merge", "head-name"))
    if os.path.isdir(os.path.join(binding["git_dir"], "rebase-apply")):
        descriptors.append(os.path.join(binding["git_dir"], "rebase-apply", "head-name"))
    if os.path.lexists(os.path.join(binding["git_dir"], "BISECT_START")):
        descriptors.append(os.path.join(binding["git_dir"], "BISECT_START"))
    for descriptor in descriptors:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(descriptor, flags)
            try:
                st = os.fstat(fd)
                if not stat.S_ISREG(st.st_mode) or st.st_size < 1 or st.st_size > 64 * 1024:
                    return None
                raw = os.read(fd, st.st_size + 1)
            finally:
                os.close(fd)
        except OSError:
            return None
        value = raw.strip()
        if (not value or b"\x00" in value or b"\n" in value or b"\r" in value):
            continue
        if value.startswith(b"refs/heads/"):
            ref = os.fsdecode(value)
        elif re.fullmatch(rb"[A-Za-z0-9][A-Za-z0-9._/-]*", value):
            ref = "refs/heads/" + os.fsdecode(value)
        else:
            continue
        command = [
            "git", "--git-dir=" + binding["git_dir"],
            "--work-tree=" + binding["root"],
            "show-ref", "--hash", "--verify", ref,
        ]
        proc = subprocess.run(
            command, capture_output=True, text=True,
            env=_sanitized_git_env(index_file=binding["index_file"]))
        if proc.returncode == 0 and proc.stdout.strip():
            candidates.append(ref[len("refs/heads/"):])
        elif proc.returncode not in (0, 1):
            return None
    unique = sorted(set(candidates))
    return unique[0] if len(unique) == 1 else None


def _heartbeat_target_recheck(root_path: str, *, branch: str | None,
                              common_dir: str | None,
                              require_linked: bool = False) -> tuple[bool, str]:
    """Revalidate a real linked-worktree target while the common-dir lock is held.

    Legacy non-git callers remain supported only when no git identity is observable. A missing
    physical root always refuses, which prevents a delayed heartbeat from recreating a phantom
    record after finish removed the worktree.
    """
    ap = canon(root_path)
    if not os.path.isdir(ap):
        return False, "root_absent"
    if not branch or not common_dir:
        if require_linked:
            return False, "git_identity_missing"
        return True, "legacy_identity_unavailable"
    expected_common = os.path.abspath(common_dir)
    discovery_env = _sanitized_git_env()
    probes = (
        subprocess.run(
            ["git", "-C", ap, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, env=discovery_env),
        subprocess.run(
            ["git", "-C", ap, "rev-parse", "--path-format=absolute", "--git-dir"],
            capture_output=True, text=True, env=discovery_env),
        subprocess.run(
            ["git", "-C", ap, "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, env=discovery_env),
        subprocess.run(
            ["git", "-C", ap, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, env=discovery_env),
    )
    if any(proc.returncode != 0 for proc in probes):
        # Synthetic/non-git heartbeat compatibility is intentionally narrow. An observable git
        # marker/common dir means this was meant to be a real worktree and identity uncertainty
        # fails safe.
        if require_linked or os.path.lexists(os.path.join(ap, ".git")) or os.path.isdir(expected_common):
            return False, "git_identity_unavailable"
        return True, "legacy_non_git"
    top, git_dir, actual_common, actual_branch = (
        proc.stdout.strip() for proc in probes)
    if canon(top) != ap:
        return False, "root_not_toplevel"
    if os.path.abspath(git_dir) == os.path.abspath(actual_common):
        return False, "root_not_linked"
    if os.path.abspath(actual_common) != expected_common:
        return False, "common_dir_mismatch"
    if actual_branch == "HEAD":
        try:
            preliminary = _validated_recheck_binding(ap, git_dir, actual_common)
            actual_branch = _detached_operation_branch(preliminary) or "HEAD"
        except OSError:
            actual_branch = "HEAD"
    if actual_branch != branch or actual_branch == "HEAD":
        return False, "branch_mismatch"
    try:
        binding = _validated_recheck_binding(ap, git_dir, actual_common)
    except OSError:
        return False, "git_binding_invalid"
    command_prefix = [
        "git", "--git-dir=" + binding["git_dir"],
        "--work-tree=" + binding["root"],
    ]
    bound_env = _sanitized_git_env(index_file=binding["index_file"])
    bound_probes = (
        subprocess.run(
            [*command_prefix, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, env=bound_env),
        subprocess.run(
            [*command_prefix, "rev-parse", "--path-format=absolute", "--git-dir"],
            capture_output=True, text=True, env=bound_env),
        subprocess.run(
            [*command_prefix, "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, env=bound_env),
        subprocess.run(
            [*command_prefix, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, env=bound_env),
    )
    if any(proc.returncode != 0 for proc in bound_probes):
        return False, "git_binding_unavailable"
    bound_top, bound_git, bound_common, bound_branch = (
        proc.stdout.strip() for proc in bound_probes)
    if bound_branch == "HEAD":
        bound_branch = _detached_operation_branch(binding) or "HEAD"
    if (canon(bound_top) != ap
            or os.path.abspath(bound_git) != binding["git_dir"]
            or os.path.abspath(bound_common) != expected_common
            or bound_branch != branch):
        return False, "git_binding_changed"
    return True, "validated"


def _heartbeat_locked(root_path: str, *, branch: str | None, common_dir: str | None,
                      session_id: str | None, pid: int | None,
                      boot: str | None) -> dict:
    ap = canon(root_path)
    target_ok, target_reason = _heartbeat_target_recheck(
        ap, branch=branch, common_dir=common_dir)
    if not target_ok:
        return {"ok": False, "reason": "heartbeat_target_" + target_reason}

    eff_boot = boot if boot is not None else boot_id()
    rp = record_path(ap)
    try:
        _durability_module().adopt_visible(rp)
        with open(rp, "rb") as fh:
            raw_prior = fh.read()
    except FileNotFoundError:
        raw_prior = None
    except OSError:
        return {"ok": False, "reason": "heartbeat_record_unreadable"}

    prior: dict = {}
    sessions: dict = {}
    if raw_prior is not None:
        try:
            parsed = json.loads(raw_prior.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {"ok": False, "reason": "heartbeat_record_corrupt"}
        valid, reason, sessions = _validate_record_for_heartbeat_merge(ap, parsed)
        if not valid:
            return {"ok": False, "reason": "heartbeat_" + reason}
        prior = parsed
        prior_boot = prior.get("boot_id")
        current_boot_sessions = {
            key: value for key, value in sessions.items()
            if value.get("boot_id") == eff_boot
        }
        if prior_boot != eff_boot:
            if current_boot_sessions:
                # A prior-boot aggregate projecting over a current-boot member cannot be emitted
                # by the writer. Preserve the bytes as malformed evidence.
                return {"ok": False, "reason": "heartbeat_mixed_boot_projection"}
            # A wholly prior-boot projection is stale session state. The linked-target recheck
            # already succeeded under this lock, so replace it rather than carrying old members
            # into the new boot.
            prior = {}
            sessions = {}
        elif len(current_boot_sessions) != len(sessions):
            # Valid mixed member history with a current aggregate is a known old-writer shape.
            # Prune prior-boot members while retaining current-boot membership.
            sessions = current_boot_sessions

    now_epoch, now_iso = _now_pair()
    eff_common = os.path.abspath(common_dir) if common_dir else prior.get("git_common_dir")
    eff_branch = branch if branch is not None else prior.get("branch")
    eff_session = session_id if session_id is not None else prior.get("session_id")
    eff_pid = int(pid) if pid is not None else None
    if not _valid_optional_pid(eff_pid):
        return {"ok": False, "reason": "heartbeat_pid_invalid"}
    if prior:
        prior_common = prior.get("git_common_dir")
        prior_branch = prior.get("branch")
        if (common_dir and prior_common and os.path.abspath(prior_common) != eff_common):
            return {"ok": False, "reason": "heartbeat_existing_common_dir_mismatch"}
        if branch and prior_branch and prior_branch != eff_branch:
            return {"ok": False, "reason": "heartbeat_existing_branch_mismatch"}

    skey = session_key(eff_session)
    sess_first_seen = sessions.get(skey, {}).get("first_seen") or now_iso
    sessions[skey] = {
        "session_id": eff_session,
        "pid": eff_pid,
        "boot_id": eff_boot,
        "branch": eff_branch,
        "git_common_dir": eff_common,
        "first_seen": sess_first_seen,
        "last_heartbeat": now_iso,
        "last_heartbeat_epoch": now_epoch,
    }
    # Preserve unknown additive top-level fields from a valid v1 record. Only malformed evidence
    # is refused; valid legacy evidence is migrated by adding `sessions`.
    rec = dict(prior)
    rec.update({
        "schema": SCHEMA_ACTIVE_ROOT,
        "root_path": ap,
        "git_common_dir": eff_common,
        "branch": eff_branch,
        "boot_id": eff_boot,
        "pid": eff_pid,
        "session_id": eff_session,
        "first_seen": prior.get("first_seen") or now_iso,
        "last_heartbeat": now_iso,
        "last_heartbeat_epoch": now_epoch,
        "sessions": sessions,
    })
    _write_private(rp, json.dumps(rec, indent=2, sort_keys=False) + "\n")
    return rec


def heartbeat(root_path: str, *, branch: str | None = None, common_dir: str | None = None,
              session_id: str | None = None, pid: int | None = None,
              boot: str | None = None, lock_held: bool = False,
              lock_timeout: float = 5.0) -> dict:
    """Write/refresh the active_root/v1 heartbeat for ``root_path``. Preserves ``first_seen``.

    Additive per-session tracking (ADDITIVE-WITHIN-v1): the FROZEN top-level keys are preserved and
    always reflect the FRESHEST heartbeat across sessions (so disposition()/the freeze test/existing
    readers are unchanged), AND an optional ``sessions`` map records EACH session's own entry
    (keyed by session_key) so the finish path can distinguish the confirming session's own heartbeat
    from another live session. Per-session ``first_seen`` is preserved across refreshes.

    ``pid`` is recorded for STRONG liveness ONLY when the caller owns a long-lived process for
    this root; ephemeral callers (a sessionStart hook that exits immediately) MUST omit it, so
    disposition falls back to the TTL rather than seeing an instantly-dead pid.
    """
    ap = canon(root_path)
    # Real hook callers always supply the actual common dir. The deterministic root/.git fallback
    # keeps the pre-existing non-git diagnostic API compatible while still using the same lock ABI
    # shape (locks/common-<sha256(abspath)>[:24].lock).
    lock_common = os.path.abspath(common_dir) if common_dir else os.path.join(ap, ".git")
    if lock_held:
        return _heartbeat_locked(
            ap, branch=branch, common_dir=common_dir, session_id=session_id,
            pid=pid, boot=boot)
    try:
        with _common_dir_lock(lock_common, timeout=lock_timeout):
            return _heartbeat_locked(
                ap, branch=branch, common_dir=common_dir, session_id=session_id,
                pid=pid, boot=boot)
    except TimeoutError:
        return {"ok": False, "reason": "heartbeat_lock_busy"}


def _disp(disposition: str, reason: str, root_path: str, *, exists: bool,
          record: dict | None = None, ttl: int | None = None,
          age: int | None = None, failsafe: bool = False,
          pid_backed: bool = False) -> dict:
    return {
        "disposition": disposition,
        "reason": reason,
        "root": canon(root_path),
        "exists": exists,
        "ttl_seconds": ttl,
        "age_seconds": age,
        "record": record,
        "blocks_removal": disposition == DISP_ACTIVE,
        # failsafe=True  -> ACTIVE derived from UNKNOWN evidence (unreadable record / unparseable
        #                   heartbeat time). This is the ONLY active flavor an operator `--force`
        #                   may override (it is not backed by any positive liveness signal).
        # pid_backed=True -> ACTIVE derived from a recorded owning process alive on this boot
        #                   (the strongest signal; NEVER force-overridable).
        "failsafe": bool(failsafe),
        "pid_backed": bool(pid_backed),
    }


def disposition(root_path: str, *, ttl: int | None = None) -> dict:
    """Canonical disposition for a root. SINGLE SOURCE OF TRUTH used by the clean gate and by
    sessionStart guidance. UNKNOWN evidence resolves to ``active`` (blocks removal).

    NOTE (lease vs heartbeat): the removal gate consults ONLY this heartbeat disposition. The
    ``.awa/lease.json`` ``status:"active"`` field is NOT a removal-blocking signal — do not
    assume editing a lease changes removability."""
    ttl_s = _ttl_seconds(ttl)
    ap = canon(root_path)
    exists = os.path.exists(ap)
    rec, corrupt = read_record(ap)

    if corrupt:
        return _disp(DISP_ACTIVE,
                     "active_root record present but unreadable — fail-safe active "
                     "(unknown evidence blocks removal)",
                     ap, exists=exists, ttl=ttl_s, failsafe=True)
    if rec is None:
        if exists:
            return _disp(DISP_UNTRACKED, "no active_root record for this root", ap, exists=True, ttl=ttl_s)
        return _disp(DISP_ABSENT, "no active_root record and root path does not exist",
                     ap, exists=False, ttl=ttl_s)

    if not exists:
        return _disp(DISP_DEAD,
                     "recorded root path no longer exists (removed/moved) — session guidance",
                     ap, exists=False, record=rec, ttl=ttl_s)

    # Strong liveness: an owning process recorded on THIS boot that is provably alive/dead.
    cur_boot = boot_id()
    rec_boot = rec.get("boot_id") or ""
    pid = rec.get("pid")
    if rec_boot and rec_boot == cur_boot and isinstance(pid, int) and pid > 0:
        if _pid_alive(pid):
            return _disp(DISP_ACTIVE, f"recorded session process (pid {pid}) is alive on this boot",
                         ap, exists=True, record=rec, ttl=ttl_s, pid_backed=True)
        return _disp(DISP_STALE, f"recorded session process (pid {pid}) is gone on this boot",
                     ap, exists=True, record=rec, ttl=ttl_s)

    # TTL fallback (cross-boot, or no owning pid recorded).
    last = _iso_to_epoch(rec.get("last_heartbeat_epoch"))
    if last is None:
        last = _iso_to_epoch(rec.get("last_heartbeat"))
    if last is None:
        return _disp(DISP_ACTIVE,
                     "active_root record present without a parseable heartbeat time — "
                     "fail-safe active (unknown evidence blocks removal)",
                     ap, exists=True, record=rec, ttl=ttl_s, failsafe=True)
    age = _now_epoch() - int(last)
    if age < ttl_s:
        return _disp(DISP_ACTIVE, f"heartbeat fresh ({age}s < {ttl_s}s TTL)",
                     ap, exists=True, record=rec, ttl=ttl_s, age=age)
    return _disp(DISP_STALE, f"heartbeat expired ({age}s >= {ttl_s}s TTL)",
                 ap, exists=True, record=rec, ttl=ttl_s, age=age)


def _sync_parent(path: str) -> None:
    _durability_module().sync_parent(path)


def _remove_root_locked(root_path: str) -> dict:
    rp = record_path(root_path)
    try:
        _durability_module().durable_unlink(rp, missing_ok=False)
        return {"ok": True, "reason": "cleared", "removed": True}
    except FileNotFoundError:
        return {"ok": True, "reason": "absent", "removed": False}
    except OSError:
        return {"ok": False, "reason": "active_root_unlink_failed", "removed": False}


def remove_root(root_path: str, *, common_dir: str | None = None,
                lock_held: bool = False, lock_timeout: float = 5.0) -> bool:
    """Remove a root heartbeat idempotently under the shared lock when identity is available."""
    if lock_held:
        return bool(_remove_root_locked(root_path).get("removed"))
    lock_common = (
        os.path.abspath(common_dir) if common_dir
        else os.path.join(canon(root_path), ".git"))
    try:
        with _common_dir_lock(lock_common, timeout=lock_timeout):
            return bool(_remove_root_locked(root_path).get("removed"))
    except TimeoutError:
        return False


def _session_confirming_waivable(sess: dict, branch: str | None, common_dir: str | None) -> bool:
    """A confirming session's fresh heartbeat is waivable ONLY when it is PID-LESS (no live owning
    process to speak of) AND its recorded branch + common_dir MATCH the finish target. Any absent
    field or mismatch -> not waivable (fail-safe: the gate then blocks)."""
    pid = sess.get("pid")
    if isinstance(pid, int) and pid > 0:
        return False
    sb = sess.get("branch")
    if not branch or not sb or sb != branch:
        return False
    sc = sess.get("git_common_dir")
    if not common_dir or not sc or os.path.abspath(sc) != os.path.abspath(common_dir):
        return False
    return True


def _finish_session_identity_valid(session_id) -> bool:
    """Heartbeat writers may use None/empty only for the legacy `unattributed` bucket."""
    return session_id is None or (
        isinstance(session_id, str) and session_id == session_id.strip())


def _finish_session_evidence_locked(root_path: str, *, confirming_session_key: str,
                                    branch: str | None, common_dir: str | None) -> dict:
    """Strict finish-only semantic validation for active_root/v1 session evidence.

    This helper is intentionally NOT used by disposition() or ordinary clean.  It rejects every
    coercible/ambiguous member before the finish gate may waive the confirming heartbeat.
    """
    ap = canon(root_path)
    rec, corrupt = read_record(ap)
    if corrupt:
        return {"ok": False, "reason": "record_corrupt", "detail": "record_unreadable"}
    if rec is None:
        return {
            "ok": True, "reason": "no_record", "record": None, "sessions": {},
            "membership": [], "confirming_present": False,
        }
    if not isinstance(confirming_session_key, str) or not confirming_session_key:
        return {"ok": False, "reason": "session_malformed",
                "detail": "confirming_session_key_invalid"}
    if (not isinstance(rec, dict) or rec.get("schema") != SCHEMA_ACTIVE_ROOT
            or rec.get("root_path") != ap):
        return {"ok": False, "reason": "session_malformed",
                "detail": "record_identity_invalid"}
    if not branch or not isinstance(branch, str) or not common_dir or not isinstance(common_dir, str):
        return {"ok": False, "reason": "session_malformed",
                "detail": "finish_target_identity_missing"}
    record_valid, record_reason, sessions = _validate_record_for_heartbeat_merge(ap, rec)
    if not record_valid:
        return {"ok": False, "reason": "session_malformed", "detail": record_reason}
    legacy = record_reason == "valid_legacy"
    target_common = os.path.abspath(common_dir)
    current_boot = boot_id()
    top_pid = rec.get("pid")
    if top_pid is not None and (type(top_pid) is not int or top_pid <= 0):
        return {"ok": False, "reason": "session_malformed", "detail": "record_pid_invalid"}
    top_first = _strict_iso_epoch(rec.get("first_seen"))
    top_timestamp_state, top_last_epoch = _timestamp_pair_state(
        rec.get("last_heartbeat"), rec.get("last_heartbeat_epoch"))
    if (rec.get("git_common_dir") != target_common
            or rec.get("branch") != branch
            or rec.get("boot_id") != current_boot
            or not _finish_session_identity_valid(rec.get("session_id"))
            or top_first is None or top_timestamp_state == "invalid" or top_last_epoch is None
            or top_first > top_last_epoch
            or top_last_epoch > _now_epoch() + 5):
        return {"ok": False, "reason": "session_malformed",
                "detail": "record_target_or_timestamp_invalid"}

    validated: dict = {}
    now = _now_epoch()
    for skey, sess in sessions.items():
        if not isinstance(skey, str) or not skey or not isinstance(sess, dict):
            return {"ok": False, "reason": "session_malformed",
                    "detail": "session_member_not_object"}
        if set(sess) != ACTIVE_SESSION_KEYS:
            return {"ok": False, "reason": "session_malformed",
                    "detail": "session_member_keyset_invalid"}
        sid = sess.get("session_id")
        if not _finish_session_identity_valid(sid) or skey != session_key(sid):
            return {"ok": False, "reason": "session_malformed",
                    "detail": "session_key_identity_mismatch"}
        pid = sess.get("pid")
        if pid is not None and (type(pid) is not int or pid <= 0):
            return {"ok": False, "reason": "session_malformed",
                    "detail": "session_pid_invalid"}
        first = _strict_iso_epoch(sess.get("first_seen"))
        member_timestamp_state, last_epoch = _timestamp_pair_state(
            sess.get("last_heartbeat"), sess.get("last_heartbeat_epoch"))
        if (sess.get("boot_id") != current_boot
                or sess.get("branch") != branch
                or sess.get("git_common_dir") != target_common
                or first is None or member_timestamp_state == "invalid" or last_epoch is None
                or first > last_epoch or last_epoch > now + 5):
            return {"ok": False, "reason": "session_malformed",
                    "detail": "session_target_or_timestamp_invalid"}
        validated[skey] = sess

    top_key = session_key(rec.get("session_id"))
    top_member = validated.get(top_key)
    if (top_member is None
            or top_member.get("pid") != top_pid
            or top_member.get("last_heartbeat_epoch") != top_last_epoch
            or top_member.get("last_heartbeat") != _iso_from_epoch(top_last_epoch)):
        return {"ok": False, "reason": "session_malformed",
                "detail": "record_member_projection_mismatch"}
    return {
        "ok": True,
        "reason": "validated_legacy" if legacy else "validated",
        "record": rec,
        "sessions": validated,
        "membership": sorted(k for k in validated if k != confirming_session_key),
        "confirming_present": confirming_session_key in validated,
    }


def finish_session_evidence(root_path: str, *, confirming_session_key: str,
                            branch: str | None = None,
                            common_dir: str | None = None,
                            lock_held: bool = False,
                            lock_timeout: float = 5.0) -> dict:
    """Public strict snapshot used by finish preview/fingerprinting and the finish gate.

    Membership reads share the same per-common-dir lock as heartbeat merges. Callers already in
    the finish critical section pass ``lock_held=True`` to avoid recursive flock deadlock.
    """
    if lock_held:
        return _finish_session_evidence_locked(
            root_path, confirming_session_key=confirming_session_key,
            branch=branch, common_dir=common_dir)
    lock_common = (
        common_dir if isinstance(common_dir, str) and common_dir
        else os.path.join(canon(root_path), ".git"))
    try:
        with _common_dir_lock(lock_common, timeout=lock_timeout):
            return _finish_session_evidence_locked(
                root_path, confirming_session_key=confirming_session_key,
                branch=branch, common_dir=common_dir)
    except TimeoutError:
        return {"ok": False, "reason": "session_lock_busy",
                "detail": "heartbeat_membership_lock_busy"}


def finish_session_gate(root_path: str, *, confirming_session_key: str,
                        branch: str | None = None, common_dir: str | None = None,
                        ttl: int | None = None, lock_held: bool = False,
                        lock_timeout: float = 5.0) -> dict:
    """Finish-ONLY per-session gate (NOT used by ordinary clean; disposition() is unchanged).

    Returns {"blocked": bool, "reason": str, ...}. It may WAIVE ONLY the confirming session's OWN
    pid-less, TTL-fresh heartbeat (when its branch + common_dir match the target). It BLOCKS on:
    any OTHER session fresh-by-TTL or pid-alive; ANY live pid (even the confirming session's — a
    live owning process means work may be in flight); a corrupt/unreadable record; an unparseable
    heartbeat time; malformed/missing session evidence. Fail-safe = block.

    A completely ABSENT record does NOT block (nothing claims the root; the challenge target-binding
    + fingerprint gates still protect) — the gate's job is only to catch a CONCURRENT live session.
    """
    ttl_s = _ttl_seconds(ttl)
    evidence = finish_session_evidence(
        root_path, confirming_session_key=confirming_session_key,
        branch=branch, common_dir=common_dir, lock_held=lock_held,
        lock_timeout=lock_timeout)
    if not evidence.get("ok"):
        return {"blocked": True, "reason": str(evidence.get("reason") or "session_malformed"),
                "detail": str(evidence.get("detail") or "unknown")}
    if evidence.get("record") is None:
        return {"blocked": False, "reason": "no_record"}
    sessions = evidence["sessions"]

    now = _now_epoch()
    cur_boot = boot_id()
    blockers: list[str] = []
    waived = False
    for skey, sess in sessions.items():
        if not isinstance(sess, dict):
            return {"blocked": True, "reason": "session_malformed"}
        pid = sess.get("pid")
        s_boot = sess.get("boot_id") or ""
        # ANY live pid recorded on THIS boot blocks, regardless of session identity.
        if isinstance(pid, int) and pid > 0 and s_boot and s_boot == cur_boot and _pid_alive(pid):
            blockers.append(f"pid_alive:{skey}")
            continue
        last = _iso_to_epoch(sess.get("last_heartbeat_epoch"))
        if last is None:
            last = _iso_to_epoch(sess.get("last_heartbeat"))
        if last is None:
            # Unknown evidence (unparseable heartbeat time) -> fail-safe block.
            return {"blocked": True, "reason": "unparseable_heartbeat"}
        fresh = (now - int(last)) < ttl_s
        if not fresh:
            continue  # a stale session neither blocks nor waives
        if skey == confirming_session_key and _session_confirming_waivable(sess, branch, common_dir):
            waived = True
            continue
        blockers.append(f"other_session_fresh:{skey}" if skey != confirming_session_key
                        else f"confirming_not_waivable:{skey}")
    if blockers:
        return {"blocked": True, "reason": blockers[0].split(":", 1)[0], "blockers": blockers}
    if not evidence.get("confirming_present"):
        return {"blocked": True, "reason": "session_malformed",
                "detail": "confirming_session_missing"}
    return {"blocked": False, "reason": "waived_confirming" if waived else "only_stale_sessions",
            "waived": waived}


# K2 TODO (deferred — observability, NOT a safety gap): dead-root records and clean receipts
# accumulate unbounded under roots/ and receipts/. Add a prune/TTL + a size cap in K2. The
# SAFETY-relevant escape (clearing a stuck record) ships now as `forget` / `--force`, below.
def dead_roots() -> list[dict]:
    """Every recorded root whose path no longer exists — used for sessionStart guidance."""
    out: list[dict] = []
    rd = roots_dir()
    if not os.path.isdir(rd):
        return out
    for name in sorted(os.listdir(rd)):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(rd, name), encoding="utf-8") as fh:
                rec = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        rpath = rec.get("root_path")
        if rpath and not os.path.exists(rpath):
            out.append(rec)
    return out


def _coerce_bool(value) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def write_receipt(*, disposition: str, reason: str, message: str = "", path: str = "",
                  branch: str = "", head: str = "", common_dir: str = "",
                  bundle: bool = False, force: bool = False, delete_branch: bool = False,
                  ignored_present: bool = False, ignored_count: int = 0,
                  safe_reason: str = "", archive: str = "",
                  root_disposition: str = "", root_disposition_reason: str = "",
                  finish_current: bool = False, authorization_nonce: str = "",
                  discard_count: int = 0, branch_action: str = "",
                  challenge_fingerprint: str = "",
                  operation_id: str = "",
                  tool: str = "dev-worktree.sh clean") -> str:
    """Write ONE clean_receipt/v1 record and return its path. A disposition not in the frozen
    vocabulary is coerced to ``refused`` (fail-safe) and annotated, so a mis-wired new path can
    never mint a spurious ``removed`` receipt.

    The ``finish_*``/``authorization_nonce``/``discard_count``/``branch_action``/
    ``challenge_fingerprint`` fields are ADDITIVE-WITHIN-v1 (optional): they are populated by the
    root-bound finish path and left at their defaults on the ordinary ``clean --path`` path, so
    every existing clean_receipt/v1 consumer stays valid."""
    disp = disposition if disposition in CLEAN_DISPOSITIONS else CLEAN_REFUSED
    if disp != disposition:
        message = f"[coerced from invalid disposition {disposition!r}] {message}".strip()
        reason = reason or "invalid_disposition"
    if operation_id and not re.fullmatch(r"[0-9a-f]{64}", operation_id):
        raise ValueError("invalid finish operation id")
    ts = _now_iso()
    receipt_id = (
        f"finish-{operation_id}" if operation_id
        else f"{time.strftime('%Y%m%d%H%M%S', time.gmtime())}-{os.getpid()}-{os.urandom(3).hex()}")
    rec = {
        "schema": SCHEMA_CLEAN_RECEIPT,
        "receipt_id": receipt_id,
        "time": ts,
        "verb": "clean",
        "disposition": disp,
        "reason_code": reason or "unspecified",
        "message": message,
        "path": os.path.abspath(path) if path else "",
        "branch": branch,
        "head": head,
        "git_common_dir": os.path.abspath(common_dir) if common_dir else "",
        "flags": {"bundle": bool(bundle), "force": bool(force), "delete_branch": bool(delete_branch)},
        "ignored_present": bool(ignored_present),
        "ignored_count": int(ignored_count or 0),
        "safe_reason": safe_reason,
        "archive": archive,
        "root_disposition": root_disposition,
        "root_disposition_reason": root_disposition_reason,
        # additive-within-v1 finish fields
        "finish_current": bool(finish_current),
        "authorization_nonce": authorization_nonce,
        "discard_count": int(discard_count or 0),
        "branch_action": branch_action,
        "challenge_fingerprint": challenge_fingerprint,
        "operation_id": operation_id,
        "tool": tool,
    }
    dest = os.path.join(receipts_dir(), f"clean-{receipt_id}.json")
    if operation_id and os.path.lexists(dest):
        try:
            _durability_module().adopt_visible(dest)
            with open(dest, encoding="utf-8") as fh:
                existing = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            raise OSError("existing finish receipt is unreadable") from exc
        identity = (
            "schema", "disposition", "reason_code", "path", "branch", "head",
            "git_common_dir", "finish_current", "authorization_nonce",
            "discard_count", "branch_action", "challenge_fingerprint", "operation_id",
        )
        if all(existing.get(key) == rec.get(key) for key in identity):
            return dest
        raise OSError("existing finish receipt identity mismatch")
    _write_private(dest, json.dumps(rec, indent=2, sort_keys=False) + "\n")
    return dest


def list_receipts(limit: int = 100) -> list[dict]:
    rd = receipts_dir()
    if not os.path.isdir(rd):
        return []
    files = sorted((n for n in os.listdir(rd) if n.startswith("clean-") and n.endswith(".json")),
                   reverse=True)
    out: list[dict] = []
    for name in files[:limit]:
        try:
            with open(os.path.join(rd, name), encoding="utf-8") as fh:
                out.append(json.load(fh))
        except (OSError, json.JSONDecodeError):
            continue
    return out


# ---- CLI (invoked by the shell kernel) --------------------------------------------------
def _print(obj) -> int:
    json.dump(obj, sys.stdout, indent=2, sort_keys=False)
    sys.stdout.write("\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="awa_roots", description="AWA kernel roots: disposition/heartbeat/receipts")
    sub = p.add_subparsers(dest="cmd", required=True)

    hb = sub.add_parser("heartbeat", help="write/refresh a root's active_root/v1 heartbeat")
    hb.add_argument("--root", required=True)
    hb.add_argument("--branch", default=None)
    hb.add_argument("--common-dir", dest="common_dir", default=None)
    hb.add_argument("--session-id", dest="session_id", default=None)
    hb.add_argument("--pid", type=int, default=None)

    di = sub.add_parser("disposition", help="print a root's canonical disposition")
    di.add_argument("--root", required=True)
    di.add_argument("--ttl", type=int, default=None)
    di.add_argument("--format", choices=["json", "tsv"], default="json")

    # `gate` is the SINGLE line the kernel clean gate consumes: a fixed 5-field TSV that lets the
    # bash gate stay tiny AND fail CLOSED (an empty line / non-zero exit => tool unavailable =>
    # the gate refuses). Fields: disposition, reason, failsafe(0/1), pid_backed(0/1), record(0/1).
    ga = sub.add_parser("gate", help="emit the clean gate's canonical disposition line (TSV)")
    ga.add_argument("--root", required=True)
    ga.add_argument("--ttl", type=int, default=None)

    fg = sub.add_parser("forget", help="operator override: forget a root's heartbeat record")
    fg.add_argument("--root", required=True)

    wr = sub.add_parser("write-receipt", help="write a clean_receipt/v1 record")
    wr.add_argument("--disposition", required=True)
    wr.add_argument("--reason", default="unspecified")
    wr.add_argument("--message", default="")
    wr.add_argument("--path", default="")
    wr.add_argument("--branch", default="")
    wr.add_argument("--head", default="")
    wr.add_argument("--common-dir", dest="common_dir", default="")
    wr.add_argument("--bundle", default="0")
    wr.add_argument("--force", default="0")
    wr.add_argument("--delete-branch", dest="delete_branch", default="0")
    wr.add_argument("--ignored-present", dest="ignored_present", default="0")
    wr.add_argument("--ignored-count", dest="ignored_count", type=int, default=0)
    wr.add_argument("--safe-reason", dest="safe_reason", default="")
    wr.add_argument("--archive", default="")
    wr.add_argument("--root-disposition", dest="root_disposition", default="")
    wr.add_argument("--root-disposition-reason", dest="root_disposition_reason", default="")
    # additive-within-v1 finish fields
    wr.add_argument("--finish-current", dest="finish_current", default="0")
    wr.add_argument("--authorization-nonce", dest="authorization_nonce", default="")
    wr.add_argument("--discard-count", dest="discard_count", type=int, default=0)
    wr.add_argument("--branch-action", dest="branch_action", default="")
    wr.add_argument("--challenge-fingerprint", dest="challenge_fingerprint", default="")
    wr.add_argument("--operation-id", dest="operation_id", default="")

    fgate = sub.add_parser("finish-gate", help="finish-only per-session gate verdict (JSON)")
    fgate.add_argument("--root", required=True)
    fgate.add_argument("--session-id", dest="session_id", default="")
    fgate.add_argument("--branch", default=None)
    fgate.add_argument("--common-dir", dest="common_dir", default=None)
    fgate.add_argument("--ttl", type=int, default=None)

    sk = sub.add_parser("session-key", help="print the stable session key for a session id")
    sk.add_argument("--session-id", dest="session_id", default="")

    csw = sub.add_parser("current-session-write", help="write root-bound current session identity")
    csw.add_argument("--root", required=True)
    csw.add_argument("--session-id", required=True)
    csw.add_argument("--conversation-id", required=True)
    csw.add_argument("--branch", required=True)
    csw.add_argument("--common-dir", required=True)

    csb = sub.add_parser("current-session-bind", help="CAS-bind root/session conversation identity")
    csb.add_argument("--root", required=True)
    csb.add_argument("--session-id", required=True)
    csb.add_argument("--conversation-id", default="")
    csb.add_argument("--branch", required=True)
    csb.add_argument("--common-dir", required=True)
    csb.add_argument("--source", choices=("sessionStart", "beforeSubmitPrompt"), required=True)

    csr = sub.add_parser("current-session-read", help="read root-bound current session identity")
    csr.add_argument("--root", required=True)

    csd = sub.add_parser("current-session-remove", help="exact-identity CAS current-session cleanup")
    csd.add_argument("--root", required=True)
    csd.add_argument("--session-id", required=True)
    csd.add_argument("--conversation-id", required=True)
    csd.add_argument("--branch", required=True)
    csd.add_argument("--common-dir", required=True)
    csd.add_argument("--boot-id", default=None)

    lr = sub.add_parser("list-receipts", help="list recent clean receipts")
    lr.add_argument("--limit", type=int, default=100)

    sub.add_parser("dead-roots", help="list recorded roots whose path no longer exists")

    rr = sub.add_parser("remove-root", help="remove a root's heartbeat record (idempotent)")
    rr.add_argument("--root", required=True)

    sub.add_parser("roots-dir", help="print the roots storage dir")
    sub.add_parser("receipts-dir", help="print the receipts storage dir")

    args = p.parse_args(argv)

    if args.cmd == "heartbeat":
        result = heartbeat(args.root, branch=args.branch, common_dir=args.common_dir,
                           session_id=args.session_id, pid=args.pid)
        _print(result)
        return 1 if result.get("ok") is False else 0
    if args.cmd == "disposition":
        d = disposition(args.root, ttl=args.ttl)
        if args.format == "tsv":
            sys.stdout.write(f"{d['disposition']}\t{d['reason']}\n")
            return 0
        return _print(d)
    if args.cmd == "gate":
        d = disposition(args.root, ttl=args.ttl)
        # Sanitize the reason so a literal tab/newline can never desync the fixed-field parse.
        reason = str(d["reason"]).replace("\t", " ").replace("\n", " ")
        rec_present = 1 if d.get("record") is not None else 0
        sys.stdout.write("\t".join([
            str(d["disposition"]), reason,
            "1" if d.get("failsafe") else "0",
            "1" if d.get("pid_backed") else "0",
            str(rec_present),
        ]) + "\n")
        return 0
    if args.cmd == "forget":
        # Operator override (agent-invoked on the operator's behalf): clear a stuck heartbeat
        # record so a corrupt/future/fail-safe-active root is not permanently un-cleanable via
        # the tool (MINOR #7). This touches only kernel state, never git/worktrees.
        removed = remove_root(args.root)
        return _print({"forgot": removed, "root": canon(args.root),
                       "note": "heartbeat record cleared; the root is now removable if content-safe"})
    if args.cmd == "write-receipt":
        dest = write_receipt(
            disposition=args.disposition, reason=args.reason, message=args.message,
            path=args.path, branch=args.branch, head=args.head, common_dir=args.common_dir,
            bundle=_coerce_bool(args.bundle), force=_coerce_bool(args.force),
            delete_branch=_coerce_bool(args.delete_branch),
            ignored_present=_coerce_bool(args.ignored_present), ignored_count=args.ignored_count,
            safe_reason=args.safe_reason, archive=args.archive,
            root_disposition=args.root_disposition,
            root_disposition_reason=args.root_disposition_reason,
            finish_current=_coerce_bool(args.finish_current),
            authorization_nonce=args.authorization_nonce, discard_count=args.discard_count,
            branch_action=args.branch_action, challenge_fingerprint=args.challenge_fingerprint,
            operation_id=args.operation_id,
        )
        sys.stdout.write(dest + "\n")
        return 0
    if args.cmd == "finish-gate":
        return _print(finish_session_gate(
            args.root, confirming_session_key=session_key(args.session_id),
            branch=args.branch, common_dir=args.common_dir, ttl=args.ttl))
    if args.cmd == "session-key":
        sys.stdout.write(session_key(args.session_id) + "\n")
        return 0
    if args.cmd == "current-session-write":
        return _print(write_current_session(
            args.root, session_id=args.session_id, conversation_id=args.conversation_id,
            branch=args.branch, common_dir=args.common_dir))
    if args.cmd == "current-session-bind":
        result = bind_current_session(
            args.root, session_id=args.session_id, conversation_id=args.conversation_id,
            branch=args.branch, common_dir=args.common_dir, source=args.source)
        _print(result)
        return 0 if result.get("ok") else 1
    if args.cmd == "current-session-read":
        rec, status = read_current_session(args.root)
        _print({"status": status, "current_session": rec})
        return 0 if status == "ok" else 1
    if args.cmd == "current-session-remove":
        result = remove_current_session_cas(
            args.root, session_id=args.session_id,
            conversation_id=args.conversation_id, branch=args.branch,
            common_dir=args.common_dir, expected_boot_id=args.boot_id)
        _print(result)
        return 0 if result.get("ok") else 1
    if args.cmd == "list-receipts":
        return _print(list_receipts(args.limit))
    if args.cmd == "dead-roots":
        return _print(dead_roots())
    if args.cmd == "remove-root":
        return _print({"removed": remove_root(args.root), "root": os.path.abspath(args.root)})
    if args.cmd == "roots-dir":
        sys.stdout.write(roots_dir() + "\n")
        return 0
    if args.cmd == "receipts-dir":
        sys.stdout.write(receipts_dir() + "\n")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
