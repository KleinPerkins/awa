"""Private per-chat association snapshots and read-only cache views (ADR 0030).

No lifecycle, lease, Cursor registration, admission, installer or native client
is called. Dependency arguments are test seams; the state directory always comes
from the existing configured AWA state root, never from a request/CLI argument.
"""
from __future__ import annotations

import contextlib
import errno
import fcntl
import os
import re
import stat
import sys
import time
import uuid

from . import paths
from .codex_association import (
    ADAPTER, FILE_CAP, HEX, HOST, MAX_INT, OID, TRUST, UNKNOWN, AssociationError, Clock,
    canonical, digest, edge_key, integer, keys, parse_request, path_text, probe,
    result, sample_clock, strict_json, text, validate_time,
)
from .codex_association_files import Access, close_all, exchange_operation

SNAPSHOT = re.compile(r"assoc-([0-9a-f]{64})\.json\Z")
LOCK = re.compile(r"assoc-([0-9a-f]{64})\.lock\Z")
EDGE_FIELDS = "edge_key root git_dir common_dir root_dev root_ino git_dev git_ino common_dev common_ino head branch first_verified_ms last_verified_ms attachment_ids"


def supported_host():
    return sys.platform == "darwin"


def _ids(values):
    if type(values) is not list or len(values) > 64:
        raise AssociationError()
    for value in values:
        text(value)
    if values != sorted(set(values), key=lambda x: x.encode("utf-8")):
        raise AssociationError()


def validate_record(raw, name):
    """Validate all stored fields before exposing any item; no target probing."""
    try:
        r = strict_json(raw, FILE_CAP)
        keys(r, "schema host_scope chat_id trust adapter_revision revision observation current_edge_key edges history_truncated")
        if (r["schema"] != "awa-codex-association/v1" or r["host_scope"] != HOST
                or r["trust"] != TRUST or r["adapter_revision"] != ADAPTER):
            raise AssociationError()
        chat = text(r["chat_id"])
        if name != "assoc-" + digest([HOST, chat]) + ".json":
            raise AssociationError()
        integer(r["revision"], 1)
        if type(r["history_truncated"]) is not bool or type(r["edges"]) is not list or len(r["edges"]) > 16:
            raise AssociationError()
        obs = r["observation"]
        keys(obs, "outcome reason reported_started_ms reported_completed_ms recorded_ms boot_digest continuous_ns attachment_set_sha256 selected_attachment_ids other_attachment_ids")
        for key in ("reported_started_ms", "reported_completed_ms", "recorded_ms"):
            integer(obs[key])
        if (obs["reported_started_ms"] > obs["reported_completed_ms"]
                or obs["reported_completed_ms"] - obs["reported_started_ms"] > 30000):
            raise AssociationError()
        _ids(obs["selected_attachment_ids"]); _ids(obs["other_attachment_ids"])
        if (set(obs["selected_attachment_ids"]) & set(obs["other_attachment_ids"])
                or len(obs["selected_attachment_ids"]) + len(obs["other_attachment_ids"]) > 64):
            raise AssociationError()
        if obs["boot_digest"] is not None and (not isinstance(obs["boot_digest"], str) or not HEX.fullmatch(obs["boot_digest"])):
            raise AssociationError()
        if obs["continuous_ns"] is not None:
            integer(obs["continuous_ns"])
        if (obs["boot_digest"] is None) != (obs["continuous_ns"] is None):
            raise AssociationError()
        if obs["outcome"] == "current":
            if (obs["reason"] != "none" or obs["boot_digest"] is None
                    or not isinstance(obs["attachment_set_sha256"], str)
                    or not HEX.fullmatch(obs["attachment_set_sha256"]) or not obs["selected_attachment_ids"]):
                raise AssociationError()
            validate_time(obs, obs["recorded_ms"])
        elif obs["outcome"] == "unknown":
            if (obs["reason"] not in UNKNOWN or obs["attachment_set_sha256"] is not None
                    or obs["selected_attachment_ids"] or obs["other_attachment_ids"] or r["current_edge_key"] is not None):
                raise AssociationError()
        else:
            raise AssociationError()
        seen = []
        for e in r["edges"]:
            keys(e, EDGE_FIELDS)
            for key in ("root", "git_dir", "common_dir"):
                path_text(e[key])
            for key in ("root_dev", "root_ino", "git_dev", "git_ino", "common_dev", "common_ino"):
                v = e[key]
                if type(v) is not str or not re.fullmatch(r"0|[1-9][0-9]{0,19}", v) or int(v) >= 1 << 64:
                    raise AssociationError()
            if not isinstance(e["head"], str) or not OID.fullmatch(e["head"]):
                raise AssociationError()
            if e["branch"] is not None:
                text(e["branch"])
            integer(e["first_verified_ms"]); integer(e["last_verified_ms"])
            if e["first_verified_ms"] > e["last_verified_ms"]:
                raise AssociationError()
            _ids(e["attachment_ids"])
            if not e["attachment_ids"] or e["edge_key"] != edge_key(chat, e):
                raise AssociationError()
            seen.append(e["edge_key"])
        if seen != sorted(set(seen)):
            raise AssociationError()
        if obs["outcome"] == "current":
            selected = [e for e in r["edges"] if e["edge_key"] == r["current_edge_key"]]
            if (len(selected) != 1 or selected[0]["attachment_ids"] != obs["selected_attachment_ids"]
                    or selected[0]["last_verified_ms"] != obs["recorded_ms"]):
                raise AssociationError()
        if raw != canonical(r) + b"\n":
            raise AssociationError()
        return r
    except (ValueError, TypeError, KeyError, UnicodeError, OverflowError) as exc:
        raise AssociationError("unsafe_state") from exc


def _clock_valid(clock):
    try:
        integer(clock.wall_ms); integer(clock.continuous_ns)
        return isinstance(clock.boot, str) and bool(HEX.fullmatch(clock.boot))
    except (ValueError, AttributeError, TypeError):
        return False


def _recent(r, clock):
    o = r["observation"]
    if not _clock_valid(clock) or o["outcome"] != "current" or o["boot_digest"] != clock.boot:
        return False
    mono_age = clock.continuous_ns - o["continuous_ns"]
    wall_age = clock.wall_ms - o["recorded_ms"]
    return 0 <= mono_age <= 300000000000 and 0 <= wall_age <= 300000 and o["reported_completed_ms"] <= clock.wall_ms + 5000


class Store:
    def __init__(self, matcher, *, clock=sample_clock, physical_probe=probe, wall=None, fault=None):
        self.access = Access(matcher)
        self.matcher = matcher
        self.clock = clock
        self.physical_probe = physical_probe
        self.wall = wall or (lambda: time.time_ns() // 1000000)
        self.fault = fault or (lambda stage: None)
        self.base = str(paths.awa_state_dir())
        self.root = self.base + "/codex-associations/v1"

    @staticmethod
    def _name(chat):
        return "assoc-" + digest([HOST, chat])

    def _load(self, fd, filename):
        try:
            raw = self.access.read(self.root + "/" + filename, FILE_CAP, private=True, parent_fd=fd)
        except FileNotFoundError:
            return None, None
        return validate_record(raw, filename), raw

    def _sample(self):
        try:
            return self.clock()
        except Exception:
            return Clock(integer(self.wall()), None, None)

    @contextlib.contextmanager
    def _transaction(self, create, lockname, *, attempted=None, publication=None):
        # Close directory/read handles while the chat lock is still held. The
        # lock's own release/close is last; only then may success be returned.
        with contextlib.ExitStack() as descriptors:
            directory = descriptors.enter_context(self.access.directory(self.root, create=create, private_from=self.base))
            with self._lock(directory, lockname) as ticket:
                try:
                    yield directory
                except BaseException:
                    try:
                        if not attempted or not attempted[0]:
                            self._remove_empty_new_lock(directory, lockname, ticket)
                    except Exception:
                        pass  # Preserve the primary failure; still close all FDs.
                    descriptors.__exit__(*sys.exc_info())
                    raise
                ticket["publication"] = publication
                if not attempted or not attempted[0]:
                    self._remove_empty_new_lock(directory, lockname, ticket)
                descriptors.close()
                self.fault("directory_cleanup")
            self.fault("lock_cleanup")

    @contextlib.contextmanager
    def _lock(self, directory, filename):
        self.access.check(self.root + "/" + filename)
        try:
            try:
                fd = os.open(filename, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=directory)
                created = True
            except FileExistsError:
                fd = os.open(filename, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
                created = False
        except OSError as exc:
            if exc.errno in (errno.ELOOP, errno.ENOTDIR, errno.EISDIR, errno.EACCES, errno.EPERM):
                raise AssociationError("unsafe_state") from exc
            raise
        primary, locked = None, False
        try:
            self.access.private_file(fd, self.root + "/" + filename)
            if os.fstat(fd).st_size != 0:
                raise AssociationError("unsafe_state")
            end = time.monotonic() + 2
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locked = True
                    break
                except BlockingIOError:
                    if time.monotonic() >= end:
                        raise AssociationError("lock_busy")
                    time.sleep(min(0.02, max(0, end - time.monotonic())))
            st = os.fstat(fd)
            try:
                named = os.stat(filename, dir_fd=directory, follow_symlinks=False)
            except FileNotFoundError as exc:
                raise AssociationError("lock_busy") from exc
            if (st.st_dev, st.st_ino) != (named.st_dev, named.st_ino):
                raise AssociationError("unsafe_state")
            directory_stat = os.fstat(directory)
            ticket = {"created": created, "fd": fd, "identity": (st.st_dev, st.st_ino),
                      "directory_identity": (directory_stat.st_dev, directory_stat.st_ino)}
            yield ticket
            if ticket.get("removed"):
                return
            # Even an actor outside the cooperating lock protocol must not make
            # a replaced lock name support a successful publication claim.
            self.access.private_file(fd, self.root + "/" + filename)
            if os.fstat(fd).st_size != 0:
                raise AssociationError("unsafe_state")
            # Never use the now-closed directory FD number (another thread may
            # have reused it). Open/validate the namespace afresh under this lock.
            with self.access.directory(self.root, private_from=self.base) as fresh:
                fresh_stat = os.fstat(fresh)
                if (fresh_stat.st_dev, fresh_stat.st_ino) != ticket["directory_identity"]:
                    raise AssociationError("unsafe_state")
                named = os.stat(filename, dir_fd=fresh, follow_symlinks=False)
                proof = ticket.get("publication")
                if proof:
                    current = os.stat(proof["filename"], dir_fd=fresh, follow_symlinks=False)
                    if (current.st_dev, current.st_ino) != proof["identity"]:
                        raise OSError("publication identity changed during cleanup")
                    if self.access.read(self.root + "/" + proof["filename"], FILE_CAP, private=True, parent_fd=fresh) != proof["postimage"]:
                        raise OSError("publication changed during cleanup")
            if (st.st_dev, st.st_ino) != (named.st_dev, named.st_ino):
                raise AssociationError("unsafe_state")
        except BaseException as exc:
            primary = exc
            raise
        finally:
            error = primary
            if locked:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except OSError as exc:
                    if error is None:
                        error = exc
            try:
                close_all([fd], primary=error)
            except OSError as exc:
                if error is None:
                    error = exc
            if primary is None and error is not None:
                raise error

    def _remove_empty_new_lock(self, directory, filename, ticket):
        if not ticket["created"]:
            return
        snapshot = filename[:-5] + ".json"
        self.access.check(self.root + "/" + snapshot)
        try:
            os.stat(snapshot, dir_fd=directory, follow_symlinks=False)
            return
        except FileNotFoundError:
            pass
        named = os.stat(filename, dir_fd=directory, follow_symlinks=False)
        self.access.private_file(ticket["fd"], self.root + "/" + filename)
        if os.fstat(ticket["fd"]).st_size != 0:
            raise AssociationError("unsafe_state")
        if (named.st_dev, named.st_ino) != ticket["identity"]:
            raise AssociationError("unsafe_state")
        # Delete only this invocation's new empty lock, while holding its flock.
        # Waiters validate the lock-name inode after acquiring it, so they cannot
        # write through this unlinked old inode alongside a new cooperating lock.
        os.unlink(filename, dir_fd=directory)
        ticket["removed"] = True
        os.fsync(directory)

    def _namespace(self, directory):
        with self.access.directory(self.root, private_from=self.base) as fresh:
            a, b = os.fstat(directory), os.fstat(fresh)
            if (a.st_dev, a.st_ino) != (b.st_dev, b.st_ino):
                raise AssociationError("unsafe_state")

    def _publish(self, directory, filename, old_raw, postimage, attempted):
        temp = "." + filename + "." + uuid.uuid4().hex + ".tmp"
        self.access.check(self.root + "/" + temp)
        fd, identity, primary = None, None, None
        exchange = exchange_operation() if old_raw is not None else None
        try:
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            st = os.fstat(fd); identity = (st.st_dev, st.st_ino)
            new_identity = identity
            self.access.private_file(fd, self.root + "/" + temp)
            offset = 0
            while offset < len(postimage):
                count = os.write(fd, postimage[offset:])
                if count <= 0:
                    raise OSError("write failed")
                offset += count
                self.fault("write")
            os.fsync(fd); self.fault("file_fsync")
            closing, fd = fd, None
            os.close(closing); self.fault("file_close")
            self.fault("before_replace")
            self._namespace(directory)
            _, current_raw = self._load(directory, filename)
            if current_raw != old_raw:
                raise AssociationError("unsafe_state")
            temp_stat = os.stat(temp, dir_fd=directory, follow_symlinks=False)
            if (temp_stat.st_dev, temp_stat.st_ino) != identity:
                raise AssociationError("unsafe_state")
            if self.access.read(self.root + "/" + temp, FILE_CAP, private=True, parent_fd=directory) != postimage:
                raise OSError("temporary contents changed")
            expected = os.stat(filename, dir_fd=directory, follow_symlinks=False) if old_raw is not None else None
            attempted[0] = True
            self.fault("replace_attempt")
            if old_raw is None:
                # link() is atomic create-if-absent, never replacement of a
                # concurrently inserted file. Remove our extra link below.
                os.link(temp, filename, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
            else:
                exchange(directory, temp, filename)
                identity = None  # Preserve a displaced object until proven ours.
                displaced = os.stat(temp, dir_fd=directory, follow_symlinks=False)
                if ((displaced.st_dev, displaced.st_ino) != (expected.st_dev, expected.st_ino)
                        or not stat.S_ISREG(displaced.st_mode) or displaced.st_uid != os.getuid()
                        or stat.S_IMODE(displaced.st_mode) != 0o600 or displaced.st_nlink != 1):
                    raise OSError("unexpected displaced object retained")
                if self.access.read(self.root + "/" + temp, FILE_CAP, private=True, parent_fd=directory) != old_raw:
                    raise OSError("changed displaced object retained")
                identity = (displaced.st_dev, displaced.st_ino)
            named_target = os.stat(filename, dir_fd=directory, follow_symlinks=False)
            if (named_target.st_dev, named_target.st_ino) != new_identity:
                if old_raw is not None:
                    identity = None  # Retain prior version, never roll back over a newer writer.
                raise OSError("unexpected published object; prior version retained")
            if old_raw is not None:
                try:
                    published = self.access.read(self.root + "/" + filename, FILE_CAP, private=True, parent_fd=directory)
                    if published != postimage:
                        raise OSError("changed publication; prior version retained")
                except BaseException:
                    identity = None
                    raise
            self.fault("replace")
            named = os.stat(temp, dir_fd=directory, follow_symlinks=False)
            if (named.st_dev, named.st_ino) != identity:
                raise OSError("temporary identity changed")
            os.unlink(temp, dir_fd=directory)
            identity = None
            os.fsync(directory); self.fault("parent_fsync")
            readback = self.access.read(self.root + "/" + filename, FILE_CAP, private=True, parent_fd=directory)
            if readback != postimage:
                raise OSError("readback differs")
            validate_record(readback, filename); self.fault("readback")
            return new_identity
        except BaseException as exc:
            primary = exc
            raise
        finally:
            error = primary
            if fd is not None:
                try:
                    os.close(fd)
                except OSError as exc:
                    if error is None:
                        error = exc
            if identity is not None:
                try:
                    st = os.stat(temp, dir_fd=directory, follow_symlinks=False)
                    if (st.st_dev, st.st_ino) != identity:
                        raise OSError("temporary identity changed")
                    os.unlink(temp, dir_fd=directory)
                except OSError as exc:
                    if error is None:
                        error = exc
            try:
                self.fault("temp_cleanup")
            except Exception as exc:
                if error is None:
                    error = exc
            if primary is None and error is not None:
                raise error

    def mutate(self, raw, action):
        try:
            request = parse_request(raw, action, self.wall())
        except AssociationError as exc:
            return result(action, "refused", exc.reason if exc.reason == "unsupported_host" else "invalid_input", 2)
        if not supported_host():
            return result(action, "refused", "unsupported_host", 2)
        reason = request["reason"] if request["outcome"] == "unknown" else request["selection_reason"]
        first = None
        if reason is None:
            try:
                first = self.physical_probe(request, self.matcher)
            except AssociationError as exc:
                reason = exc.reason if exc.reason in UNKNOWN else "physical_identity_unavailable"
            except Exception:
                reason = "physical_identity_unavailable"
        attempted = [False]
        publication = {}
        try:
            # Invalid requests were rejected before this first state access. An
            # unverifiable create never bootstraps a state directory/lock.
            create = action == "record" and reason is None
            entered = False
            try:
                with self._transaction(create, self._name(request["chat_id"]) + ".lock", attempted=attempted, publication=publication) as directory:
                    entered = True
                    filename = self._name(request["chat_id"]) + ".json"
                    old, old_raw = self._load(directory, filename)
                    rev = old["revision"] if old else None
                    if (action == "record" and old is not None) or (action == "refresh" and (old is None or rev != request["expected_revision"])):
                        return result(action, "conflict", "revision_conflict", revision=rev)
                    if old and rev == MAX_INT:
                        return result(action, "refused", "limit_exceeded")
                    if reason is None:
                        try:
                            final = self.physical_probe(request, self.matcher)
                            binding = lambda e: {k: v for k, v in e.items() if k not in ("head", "branch")}
                            if binding(first) != binding(final):
                                reason = "identity_changed"
                        except AssociationError as exc:
                            reason = exc.reason if exc.reason in UNKNOWN else "physical_identity_unavailable"
                        except Exception:
                            reason = "physical_identity_unavailable"
                    clock = self._sample()
                    integer(clock.wall_ms)
                    wall_reversed = old is not None and clock.wall_ms < old["observation"]["recorded_ms"]
                    if reason is None and not _clock_valid(clock):
                        reason = "clock_unavailable"
                    if wall_reversed:
                        reason = "clock_unavailable"
                    if reason is None and old:
                        prior_edge = next((e for e in old["edges"] if e["edge_key"] == edge_key(request["chat_id"], final)), None)
                        if prior_edge and clock.wall_ms < prior_edge["last_verified_ms"]:
                            reason = "clock_unavailable"
                            wall_reversed = True
                    if (reason is None and old and _clock_valid(clock)
                            and clock.boot == old["observation"]["boot_digest"]
                            and old["observation"]["continuous_ns"] is not None
                            and clock.continuous_ns < old["observation"]["continuous_ns"]):
                        reason = "clock_unavailable"
                    if not wall_reversed:
                        try:
                            validate_time(request, clock.wall_ms)
                        except AssociationError:
                            # Valid at entry; only the evidence's freshness was
                            # lost while processing. Never promote a stale edge.
                            reason = "source_unsupported"
                    if reason is not None and old is None:
                        return result(action, "unknown", reason)
                    record = self._postimage(request, old, final if reason is None else None, clock, reason)
                    encoded = canonical(record) + b"\n"
                    if len(encoded) > FILE_CAP:
                        return result(action, "refused", "limit_exceeded")
                    validate_record(encoded, filename)
                    published_identity = self._publish(directory, filename, old_raw, encoded, attempted)
                    publication.update(filename=filename, identity=published_identity, postimage=encoded)
            except FileNotFoundError:
                if entered:
                    raise
                if action == "refresh":
                    return result(action, "conflict", "revision_conflict")
                if reason is not None:
                    return result(action, "unknown", reason)
                raise
            if reason is None:
                item = self._item(record, next(e for e in record["edges"] if e["edge_key"] == record["current_edge_key"]), True)
                return result(action, "recorded_as_observed", "none", 0, revision=record["revision"], changed=True, complete=True, associations=[item])
            return result(action, "unknown", reason, 0 if request["outcome"] == "unknown" else 1,
                          revision=record["revision"], changed=True)
        except Exception as exc:
            if attempted[0]:
                return result(action, "durability_unconfirmed", "publication_failed", changed=None)
            if isinstance(exc, AssociationError):
                if exc.reason == "invalid_input":
                    # The request was already validated. A malformed configured
                    # state path is unsafe state, not a bad input packet.
                    return result(action, "refused", "unsafe_state")
                if exc.reason in ("policy_refused", "unsafe_state", "lock_busy", "limit_exceeded"):
                    return result(action, "refused", exc.reason)
            return result(action, "refused", "publication_failed")

    def _postimage(self, request, old, edge, clock, reason):
        r = {"schema": "awa-codex-association/v1", "host_scope": HOST, "chat_id": request["chat_id"],
             "trust": TRUST, "adapter_revision": ADAPTER, "revision": old["revision"] + 1 if old else 1,
             "edges": [dict(e) for e in old["edges"]] if old else [], "current_edge_key": None,
             "history_truncated": old["history_truncated"] if old else False}
        selected, other, commitment = [], [], None
        if edge is not None:
            ident = edge_key(request["chat_id"], edge)
            prior = next((e for e in r["edges"] if e["edge_key"] == ident), None)
            selected = [a["attachment_id"] for a in request["selected"]]
            other = [a["attachment_id"] for a in request["before"]["attachments"] if a["attachment_id"] not in selected]
            commitment = digest(request["before"]["attachments"])
            edge = dict(edge, edge_key=ident, first_verified_ms=prior["first_verified_ms"] if prior else clock.wall_ms,
                        last_verified_ms=clock.wall_ms, attachment_ids=selected)
            r["edges"] = [e for e in r["edges"] if e["edge_key"] != ident] + [edge]
            r["current_edge_key"] = ident
            while len(r["edges"]) > 16:
                oldest = min((e for e in r["edges"] if e["edge_key"] != ident), key=lambda e: (e["last_verified_ms"], e["edge_key"]))
                r["edges"].remove(oldest); r["history_truncated"] = True
        r["edges"].sort(key=lambda e: e["edge_key"])
        valid_clock = _clock_valid(clock)
        r["observation"] = {"outcome": "current" if edge is not None else "unknown", "reason": reason or "none",
                            "reported_started_ms": request["reported_started_ms"], "reported_completed_ms": request["reported_completed_ms"],
                            "recorded_ms": clock.wall_ms, "boot_digest": clock.boot if valid_clock else None,
                            "continuous_ns": clock.continuous_ns if valid_clock else None,
                            "attachment_set_sha256": commitment, "selected_attachment_ids": selected, "other_attachment_ids": other}
        return r

    @staticmethod
    def _item(record, edge, recent):
        return {"chat_id": record["chat_id"], "root": edge["root"], "edge_key": edge["edge_key"],
                "state": "recent_as_observed" if recent else "historical", "as_of_ms": edge["last_verified_ms"]}

    def inspect(self, *, chat_id=None, worktree=None):
        try:
            if (chat_id is None) == (worktree is None):
                raise AssociationError()
            if chat_id is not None:
                text(chat_id)
            else:
                path_text(worktree)
        except AssociationError:
            return result("inspect", "refused", "invalid_input", 2)
        if not supported_host():
            return result("inspect", "refused", "unsupported_host", 2)
        try:
            if worktree is not None:
                self.access.check(worktree)
            with self.access.directory(self.root, private_from=self.base) as directory:
                if chat_id is not None:
                    record, _ = self._load(directory, self._name(chat_id) + ".json")
                    if record is None:
                        return result("inspect", "unknown", "no_record", 0)
                    records = [record]
                else:
                    names = []
                    with os.scandir(directory) as entries:
                        for entry in entries:
                            if len(names) >= 1024:
                                raise AssociationError("limit_exceeded")
                            names.append(entry.name)
                    if sum(bool(SNAPSHOT.fullmatch(n)) for n in names) > 256:
                        raise AssociationError("limit_exceeded")
                    records = []
                    for name in sorted(names):
                        if LOCK.fullmatch(name):
                            try:
                                self.access.read(self.root + "/" + name, 0, private=True, parent_fd=directory)
                            except Exception as exc:
                                raise AssociationError("unsafe_state") from exc
                        elif SNAPSHOT.fullmatch(name):
                            record, _ = self._load(directory, name)
                            if record is None:
                                raise OSError("snapshot disappeared")
                            records.append(record)
                        else:
                            raise AssociationError("unsafe_state")
                clock = self._sample()
                items, relevant = [], []
                for r in records:
                    edges = r["edges"] if worktree is None else [e for e in r["edges"] if e["root"] == worktree]
                    if worktree is not None and edges:
                        current = next((e for e in edges if e["edge_key"] == r["current_edge_key"]), None)
                        edges = [current or max(edges, key=lambda e: (e["last_verified_ms"], e["edge_key"]))]
                    if edges or chat_id is not None:
                        relevant.append(r)
                    for e in edges:
                        items.append(self._item(r, e, e["edge_key"] == r["current_edge_key"] and _recent(r, clock)))
                if not relevant:
                    return result("inspect", "unknown", "no_cached_match", 0)
                items.sort(key=lambda x: tuple(x[k].encode("utf-8") for k in ("root", "chat_id", "edge_key")))
                revision = relevant[0]["revision"] if chat_id is not None else None
                complete = all(_recent(r, clock) and not r["history_truncated"] for r in relevant)
                if worktree is not None:
                    complete = complete and all(x["state"] == "recent_as_observed" for x in items)
                if not _clock_valid(clock):
                    outcome, reason = "unknown", "clock_unavailable"
                elif any(x["state"] == "recent_as_observed" for x in items):
                    outcome, reason = "recorded_as_observed", "none"
                elif any(r["observation"]["outcome"] == "unknown" for r in relevant):
                    outcome, reason = "unknown", "cached_unknown"
                else:
                    outcome, reason = "historical", "stale"
            return result("inspect", outcome, reason, 0, revision=revision, complete=complete, associations=items)
        except FileNotFoundError:
            return result("inspect", "unknown", "no_record", 0)
        except AssociationError as exc:
            reason = exc.reason if exc.reason in ("unsafe_state", "limit_exceeded", "policy_refused") else "unsafe_state"
            return result("inspect", "refused" if reason == "policy_refused" else "unknown", reason)
        except OSError as exc:
            return result("inspect", "unknown", "unsafe_state" if exc.errno in (errno.ENOTDIR, errno.ELOOP) else "state_unavailable")
        except Exception:
            return result("inspect", "unknown", "state_unavailable")


def cli(argv, policy_path):
    """Closed new-command grammar; no raw argparse errors/arguments escape."""
    from .policy import load_hard_no_touch_matcher
    action = argv[0] if argv and argv[0] in ("record", "refresh", "inspect") else "inspect"
    try:
        if argv in (["record"], ["refresh"]):
            try:
                raw = sys.stdin.buffer.read(131073)
            except Exception:
                return result(action, "refused", "invalid_input", 2)
            return Store(load_hard_no_touch_matcher(policy_path)).mutate(raw, action)
        if len(argv) == 3 and argv[0] == "inspect" and argv[1] in ("--chat-id", "--worktree"):
            store = Store(load_hard_no_touch_matcher(policy_path))
            return store.inspect(**{"chat_id" if argv[1] == "--chat-id" else "worktree": argv[2]})
    except Exception:
        return result(action, "unknown" if action == "inspect" else "refused",
                      "state_unavailable" if action == "inspect" else "unsafe_state")
    return result(action, "refused", "invalid_input", 2)
