"""ADR 0030's trusted-agent association ABI and bounded physical Git probe.

This module grants no registration/admission, lease or lifecycle authority. The
probe reads standard linked-worktree metadata directly; it never starts Git,
loads Git includes, executes helpers, or reads the index or worktree contents.
Disposable qualification tests compare its supported layout with Git itself.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
import time
from dataclasses import dataclass

MAX_INT = (1 << 63) - 1
REQUEST_CAP = 131072
FILE_CAP = 262144
HOST = "codex-desktop-local"
TRUST = "trusted-agent-mediated"
ADAPTER = "codex-association-agent/v1"
UNKNOWN = frozenset(("native_unavailable", "association_conflict", "archive_observed",
                     "worktree_missing", "identity_changed", "source_unsupported",
                     "physical_identity_unavailable", "policy_refused", "clock_unavailable"))
HEX = re.compile(r"[0-9a-f]{64}\Z")
OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")


class AssociationError(ValueError):
    def __init__(self, reason="invalid_input"):
        super().__init__(reason)
        self.reason = reason


def canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def integer(value, minimum=0):
    if type(value) is not int or not minimum <= value <= MAX_INT:
        raise AssociationError()
    return value


def text(value, cap=256):
    if (not isinstance(value, str) or not value or value != value.strip()
            or any(ord(c) < 32 or 127 <= ord(c) <= 159 or 0xD800 <= ord(c) <= 0xDFFF for c in value)):
        raise AssociationError()
    if len(value.encode("utf-8")) > cap:
        raise AssociationError()
    return value


def path_text(value):
    text(value, 4096)
    if (not value.startswith("/") or value.startswith("//") or "~" in value.split("/")
            or os.path.normpath(value) != value or any(x in (".", "..") for x in value.split("/"))):
        raise AssociationError()
    return value


def keys(value, expected):
    if type(value) is not dict or set(value) != set(expected.split()):
        raise AssociationError()


def strict_json(raw, cap=REQUEST_CAP):
    if type(raw) is not bytes or len(raw) > cap:
        raise AssociationError()
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise AssociationError()
            result[k] = v
        return result
    def reject(_):
        raise AssociationError()
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=reject)
        def walk(x, depth=0):
            if isinstance(x, str):
                x.encode("utf-8", errors="strict")
            elif isinstance(x, (list, dict)):
                if depth >= 8:
                    raise AssociationError()
                for item in (list(x.keys()) + list(x.values()) if isinstance(x, dict) else x):
                    walk(item, depth + 1)
        walk(value)
        return value
    except (UnicodeError, ValueError, RecursionError, TypeError) as exc:
        raise AssociationError() from exc


def snapshot(value, chat):
    keys(value, "chat_id current_workspace attachments")
    if text(value["chat_id"]) != chat:
        raise AssociationError()
    path_text(value["current_workspace"])
    items = value["attachments"]
    if type(items) is not list or len(items) > 64:
        raise AssociationError()
    result, seen = [], set()
    for a in items:
        keys(a, "attachment_id root workspace_root")
        ident = text(a["attachment_id"])
        if ident in seen:
            raise AssociationError()
        seen.add(ident)
        path_text(a["root"])
        path_text(a["workspace_root"])
        result.append(dict(a))
    return {"chat_id": chat, "current_workspace": value["current_workspace"],
            "attachments": sorted(result, key=lambda x: x["attachment_id"].encode("utf-8"))}


def inside(parent, child):
    return parent == child or child.startswith(parent.rstrip("/") + "/")


def validate_time(request, now):
    start = integer(request["reported_started_ms"])
    end = integer(request["reported_completed_ms"])
    if start > end or end - start > 30000 or now - end > 60000 or end - now > 5000:
        raise AssociationError()


def parse_request(raw, action, now):
    r = strict_json(raw)
    keys(r, "schema action expected_revision host_scope chat_id trust adapter_revision outcome reason reported_started_ms reported_completed_ms before after")
    if r["host_scope"] != HOST:
        raise AssociationError("unsupported_host")
    if (r["schema"] != "awa-codex-association-request/v1" or r["action"] != action
            or action not in ("record", "refresh") or r["trust"] != TRUST or r["adapter_revision"] != ADAPTER):
        raise AssociationError()
    text(r["chat_id"])
    rev = integer(r["expected_revision"])
    if (action == "record" and rev != 0) or (action == "refresh" and rev == 0):
        raise AssociationError()
    validate_time(r, now)
    # Structurally valid conflicting native evidence is a conservative unknown
    # transition, not an invalid packet that could leave an old positive current.
    r = dict(r)
    r["selection_reason"] = None
    if r["outcome"] == "unknown":
        if not isinstance(r["reason"], str) or r["reason"] not in UNKNOWN or r["before"] is not None or r["after"] is not None:
            raise AssociationError()
        return r
    if r["outcome"] != "current" or r["reason"] != "none":
        raise AssociationError()
    before, after = (snapshot(r[n], r["chat_id"]) for n in ("before", "after"))
    r["before"], r["after"] = before, after
    if before != after:
        r["selection_reason"] = "association_conflict"
        return r
    groups = {}
    for a in before["attachments"]:
        if inside(a["root"], a["workspace_root"]) and inside(a["workspace_root"], before["current_workspace"]):
            groups.setdefault(a["root"], []).append(a)
    if len(groups) != 1:
        r["selection_reason"] = "association_conflict" if groups else "physical_identity_unavailable"
    else:
        r["selected_root"], r["selected"] = next(iter(groups.items()))
    return r


def result(action, outcome, reason, code=1, *, revision=None, changed=False, complete=False, associations=None):
    value = {"schema": "awa-codex-association-result/v1", "action": action,
             "outcome": outcome, "reason": reason, "revision": revision, "changed": changed,
             "complete": complete, "associations": associations or [], "verification_source": TRUST,
             "protection_claim": False, "writer_exclusion_granted": False, "cleanup_authorized": False}
    if len(canonical(value)) + 1 > REQUEST_CAP:
        return result(action, "unknown", "limit_exceeded")
    return value, code


@dataclass(frozen=True)
class Clock:
    wall_ms: int
    boot: str | None
    continuous_ns: int | None


def sample_clock():
    """Only the clock's pure helper is reused; no ADR 0026 runtime initializes."""
    import subprocess
    from .registration_clock import mach_continuous_time_ns
    wall = time.time_ns() // 1000000
    try:
        if sys.platform != "darwin":
            return Clock(wall, None, None)
        # Fixed executable/arguments and closed environment; output is bounded
        # while streaming, not merely sliced after an unbounded communicate().
        import selectors
        p = subprocess.Popen(["/usr/sbin/sysctl", "-n", "kern.boottime"], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"})
        raw, deadline = b"", time.monotonic() + 1
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(p.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not selector.select(remaining):
                        raise ValueError()
                    chunk = os.read(p.stdout.fileno(), 257 - len(raw))
                    if not chunk:
                        break
                    raw += chunk
                    if len(raw) > 256:
                        raise ValueError()
            if p.wait(timeout=max(0.001, deadline - time.monotonic())) != 0:
                raise ValueError()
        finally:
            if p.poll() is None:
                p.kill()
            p.wait()
            p.stdout.close()
        m = re.fullmatch(rb"\{ sec = ([0-9]{1,20}), usec = ([0-9]{1,6}) \}(?: [^\r\n]{0,160})?\n?", raw)
        if not m or int(m[2]) > 999999:
            raise ValueError()
        sec, usec = int(m[1]), int(m[2]); integer(sec); integer(usec)
        wall = time.time_ns() // 1000000
        return Clock(wall, digest([sec, usec]), integer(mach_continuous_time_ns()))
    except Exception:
        return Clock(wall, None, None)


def edge_key(chat, edge):
    return digest([HOST, chat] + [edge[k] for k in
                  ("root", "git_dir", "common_dir", "root_dev", "root_ino", "git_dev", "git_ino", "common_dev", "common_ino")])


def _config_value(raw):
    """Bounded non-continuation Git value grammar, without includes/evaluation."""
    quoted, escaped, out = False, False, []
    escapes = {"n": "\n", "t": "\t", "b": "\b", "\\": "\\", '"': '"'}
    for c in raw:
        if escaped:
            if c not in escapes:
                raise AssociationError("physical_identity_unavailable")
            out.append(escapes[c]); escaped = False
        elif c == "\\":
            escaped = True
        elif c == '"':
            quoted = not quoted
        elif c in "#;" and not quoted:
            break
        else:
            out.append(c)
    if quoted or escaped:
        raise AssociationError("physical_identity_unavailable")
    return "".join(out).strip()


def _config_supported(raw):
    """Closed identity-affecting config subset; no include is ever followed."""
    section, version, object_format = None, None, "sha1"
    decoded = raw.decode("utf-8")
    if any(ord(c) < 32 and c not in "\n\t" or 127 <= ord(c) <= 159 for c in decoded):
        raise AssociationError("physical_identity_unavailable")
    for line in decoded.split("\n"):
        line = line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.endswith("\\"):
            raise AssociationError("physical_identity_unavailable")
        if line.startswith("["):
            m = re.fullmatch(r'\[([A-Za-z][A-Za-z0-9-]*)(?:\s+"(?:[^"\\]|\\["\\])*")?\]\s*(?:[#;].*)?', line)
            if not m:
                raise AssociationError("physical_identity_unavailable")
            section = m[1].lower()
            if section in ("include", "includeif"):
                raise AssociationError("physical_identity_unavailable")
        else:
            m = re.fullmatch(r"([A-Za-z][A-Za-z0-9-]*)(?:\s*=\s*(.*))?", line)
            if not m or section is None:
                raise AssociationError("physical_identity_unavailable")
            key, val = m[1].lower(), _config_value(m[2] or "").lower()
            if section == "core" and (key == "worktree" or key == "bare" and val != "false"):
                raise AssociationError("physical_identity_unavailable")
            if section == "core" and key == "repositoryformatversion":
                if val not in ("0", "1"):
                    raise AssociationError("physical_identity_unavailable")
                version = val
            if section == "extensions" and not (key == "objectformat" and val in ("sha1", "sha256")):
                raise AssociationError("physical_identity_unavailable")
            if section == "extensions" and key == "objectformat":
                object_format = val
    if version is None or object_format == "sha256" and version != "1":
        raise AssociationError("physical_identity_unavailable")
    return 64 if object_format == "sha256" else 40


def probe(request, matcher):
    """Qualified standard linked layout only. No native tools or Git subprocess."""
    from .codex_association_files import Access
    access = Access(matcher)
    root = request["selected_root"]
    try:
        root_id = access.directory_identity(root)
        locator = access.read(root + "/.git", 8192).decode("utf-8")
        if not locator.startswith("gitdir: ") or locator.count("\n") > 1:
            raise AssociationError("physical_identity_unavailable")
        gitdir = access.locator(root, locator[8:].rstrip("\n"))
        if os.path.basename(os.path.dirname(gitdir)) != "worktrees" or not os.path.basename(gitdir):
            raise AssociationError("physical_identity_unavailable")
        git_id = access.directory_identity(gitdir)
        common_raw = access.read(gitdir + "/commondir", 8192)
        common = access.locator(gitdir, common_raw.decode("utf-8").rstrip("\n"))
        if os.path.dirname(gitdir) != common + "/worktrees" or not os.path.basename(gitdir):
            raise AssociationError("physical_identity_unavailable")
        back_raw = access.read(gitdir + "/gitdir", 8192)
        back = access.locator(gitdir, back_raw.decode("utf-8").rstrip("\n"))
        if back != root + "/.git":
            raise AssociationError("physical_identity_unavailable")
        common_id = access.directory_identity(common)
        config = access.read(common + "/config", FILE_CAP)
        oid_length = _config_supported(config)
        if access.exists(gitdir + "/config.worktree"):
            raise AssociationError("physical_identity_unavailable")
        cwd = request["before"]["current_workspace"]
        if not inside(root, cwd):
            raise AssociationError("association_conflict")
        cursor = root
        for part in cwd[len(root):].strip("/").split("/") if cwd != root else []:
            cursor += "/" + part
            current_id = access.directory_identity(cursor)
            if current_id[0] != root_id[0]:
                raise AssociationError("physical_identity_unavailable")
            if access.exists(cursor + "/.git"):
                raise AssociationError("association_conflict")
            if access.exists(cursor + "/HEAD") and (access.exists(cursor + "/commondir")
                    or access.exists(cursor + "/objects")):
                raise AssociationError("association_conflict")
        head_raw = access.read(gitdir + "/HEAD", 8192).decode("utf-8").rstrip("\n")
        branch = None
        if head_raw.startswith("ref: refs/heads/"):
            ref = head_raw[5:]
            branch = text(ref[11:])
            if (any(c in ref for c in " ~^:?*[\\") or ".." in ref or "@{" in ref
                    or any(not p or p.startswith(".") or p.endswith((".", ".lock")) for p in ref.split("/"))):
                raise AssociationError("physical_identity_unavailable")
            try:
                head_raw = access.read(common + "/" + ref, 256).decode("ascii").rstrip("\n")
            except FileNotFoundError:
                head_raw = ""
                for line in access.read(common + "/packed-refs", FILE_CAP).decode("utf-8").splitlines():
                    if line and not line.startswith(("#", "^")):
                        oid, sep, name = line.partition(" ")
                        if name == ref and sep:
                            if head_raw:
                                raise AssociationError("physical_identity_unavailable")
                            head_raw = oid
        if not OID.fullmatch(head_raw) or len(head_raw) != oid_length:
            raise AssociationError("physical_identity_unavailable")
        if (root_id != access.directory_identity(root) or git_id != access.directory_identity(gitdir)
                or common_id != access.directory_identity(common)):
            raise AssociationError("identity_changed")
        if (access.read(root + "/.git", 8192).decode("utf-8") != locator
                or access.read(gitdir + "/commondir", 8192) != common_raw
                or access.read(gitdir + "/gitdir", 8192) != back_raw
                or access.read(common + "/config", FILE_CAP) != config):
            raise AssociationError("identity_changed")
        out = {"root": root, "git_dir": gitdir, "common_dir": common, "head": head_raw, "branch": branch}
        for prefix, ident in (("root", root_id), ("git", git_id), ("common", common_id)):
            out[prefix + "_dev"], out[prefix + "_ino"] = map(str, ident)
        return out
    except AssociationError:
        raise
    except (OSError, UnicodeError, ValueError) as exc:
        raise AssociationError("physical_identity_unavailable") from exc
