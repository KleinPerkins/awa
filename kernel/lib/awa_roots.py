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
import hashlib
import json
import os
import platform
import subprocess
import sys
import time

# ---- schema strings (frozen, additive-within AWA contract v1) ---------------------------
SCHEMA_ACTIVE_ROOT = "active_root/v1"
SCHEMA_CLEAN_RECEIPT = "clean_receipt/v1"

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


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)
    try:
        os.chmod(path, DIR_MODE)
    except OSError:
        pass


def _write_private(path: str, text: str) -> None:
    """Atomic-ish private write: temp file in the same dir, chmod 600, os.replace."""
    _ensure_dir(os.path.dirname(path))
    tmp = f"{path}.tmp.{os.getpid()}.{os.urandom(3).hex()}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, FILE_MODE)
    try:
        os.write(fd, text.encode("utf-8"))
    finally:
        os.close(fd)
    try:
        os.chmod(tmp, FILE_MODE)
    except OSError:
        pass
    os.replace(tmp, path)


def _now_epoch() -> int:
    return int(time.time())


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


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


def record_path(root_path: str) -> str:
    return os.path.join(roots_dir(), f"{root_key(root_path)}.json")


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
    if not os.path.exists(rp):
        return None, False
    try:
        with open(rp, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data, False
        return None, True
    except (OSError, json.JSONDecodeError):
        return None, True


def heartbeat(root_path: str, *, branch: str | None = None, common_dir: str | None = None,
              session_id: str | None = None, pid: int | None = None,
              boot: str | None = None) -> dict:
    """Write/refresh the active_root/v1 heartbeat for ``root_path``. Preserves ``first_seen``.

    ``pid`` is recorded for STRONG liveness ONLY when the caller owns a long-lived process for
    this root;     ephemeral callers (a sessionStart hook that exits immediately) MUST omit it, so
    disposition falls back to the TTL rather than seeing an instantly-dead pid.
    """
    ap = canon(root_path)
    prior, _ = read_record(ap)
    first_seen = (prior or {}).get("first_seen") or _now_iso()
    rec = {
        "schema": SCHEMA_ACTIVE_ROOT,
        "root_path": ap,
        "git_common_dir": os.path.abspath(common_dir) if common_dir else (prior or {}).get("git_common_dir"),
        "branch": branch if branch is not None else (prior or {}).get("branch"),
        "boot_id": boot if boot is not None else boot_id(),
        "pid": int(pid) if pid is not None else None,
        "session_id": session_id if session_id is not None else (prior or {}).get("session_id"),
        "first_seen": first_seen,
        "last_heartbeat": _now_iso(),
        "last_heartbeat_epoch": _now_epoch(),
    }
    _write_private(record_path(ap), json.dumps(rec, indent=2, sort_keys=False) + "\n")
    return rec


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


def remove_root(root_path: str) -> bool:
    """Remove a root's heartbeat record (called after its worktree is removed, so a removed
    root never lingers as a phantom 'dead' record). Idempotent."""
    rp = record_path(root_path)
    try:
        os.remove(rp)
        return True
    except OSError:
        return False


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
                  tool: str = "dev-worktree.sh clean") -> str:
    """Write ONE clean_receipt/v1 record and return its path. A disposition not in the frozen
    vocabulary is coerced to ``refused`` (fail-safe) and annotated, so a mis-wired new path can
    never mint a spurious ``removed`` receipt."""
    disp = disposition if disposition in CLEAN_DISPOSITIONS else CLEAN_REFUSED
    if disp != disposition:
        message = f"[coerced from invalid disposition {disposition!r}] {message}".strip()
        reason = reason or "invalid_disposition"
    ts = _now_iso()
    receipt_id = f"{time.strftime('%Y%m%d%H%M%S', time.gmtime())}-{os.getpid()}-{os.urandom(3).hex()}"
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
        "tool": tool,
    }
    dest = os.path.join(receipts_dir(), f"clean-{receipt_id}.json")
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

    lr = sub.add_parser("list-receipts", help="list recent clean receipts")
    lr.add_argument("--limit", type=int, default=100)

    sub.add_parser("dead-roots", help="list recorded roots whose path no longer exists")

    rr = sub.add_parser("remove-root", help="remove a root's heartbeat record (idempotent)")
    rr.add_argument("--root", required=True)

    sub.add_parser("roots-dir", help="print the roots storage dir")
    sub.add_parser("receipts-dir", help="print the receipts storage dir")

    args = p.parse_args(argv)

    if args.cmd == "heartbeat":
        return _print(heartbeat(args.root, branch=args.branch, common_dir=args.common_dir,
                                session_id=args.session_id, pid=args.pid))
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
        )
        sys.stdout.write(dest + "\n")
        return 0
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
