"""Controller-bound first-prompt observer; conservative UNPROVEN export; use only the reviewed, source-pinned bundle."""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import hmac
import json
import os
import re
import resource
import stat
import sys
import time


EVENTS = (
    "SessionStart", "SessionEnd", "PreToolUse", "PermissionRequest", "PostToolUse",
    "PreCompact", "PostCompact", "UserPromptSubmit", "SubagentStart", "SubagentStop",
    "Stop", "Interrupt",
)
SCENARIOS = tuple(
    ["A%02d" % i for i in range(1, 10)]
    + ["B%02d" % i for i in range(1, 13)]
    + ["C%02d" % i for i in range(1, 10)]
    + ["D%02d" % i for i in range(1, 5)]
)
SOURCES = ("startup", "resume", "clear", "compact", "fork", "manual", "auto", "other", "UNKNOWN")
EXIT_CLASSES = ("ZERO", "TWO", "OTHER", "SIGNAL", "TIMEOUT", "NOT_APPLICABLE")
PHASES = ("BEFORE", "ACTION", "AFTER")
UNAVAILABLE = ("C03", "C04", "C06")
FILES = (
    "README.md", "capture_hook.py", "verify_capture.py", "capture-schema.v3.json",
    "scenario-catalog.v3.json", "forbidden-fields.v3.txt", "fixture-hooks.v3.json.in",
)
TOOLS = {
    "Bash": ("LOCAL", "BASH"),
    "exec_command": ("LOCAL", "UNIFIED_EXEC"),
    "write_stdin": ("LOCAL", "WRITE_STDIN"),
    "apply_patch": ("LOCAL", "APPLY_PATCH"),
    "update_plan": ("LOCAL", "UPDATE_PLAN"),
    "spawn_agent": ("LOCAL", "SPAWN_AGENT"),
    "Agent": ("LOCAL", "SPAWN_AGENT"),
    "WebSearch": ("HOSTED", "HOSTED_WEB_SEARCH"),
}
HEX = re.compile(r"[0-9a-f]{64}\Z")
LABEL = re.compile(r"[ST][1-9][0-9]{0,3}\Z")
MAX_JSON = 1024 * 1024
MAX_LEDGER = 4 * 1024 * 1024


class Invalid(ValueError):
    """Fixed, value-free invalid-evidence signal."""


def require(condition):
    if not condition:
        raise Invalid()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def closed(value, keys):
    require(type(value) is dict and set(value) == set(keys.split()))


def strict_json(raw, limit=MAX_JSON):
    require(type(raw) is bytes and len(raw) <= limit)

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result)
            result[key] = value
        return result

    def reject(_value):
        raise Invalid()

    value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=reject)
    pending = [(value, 0)]
    nodes = 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        require(depth <= 24 and nodes <= 32768)
        if type(item) is dict:
            pending.extend((v, depth + 1) for v in item.values())
        elif type(item) is list:
            pending.extend((v, depth + 1) for v in item)
        elif type(item) is float:
            raise Invalid()
    return value


def open_directory(path, private=False):
    """Walk descriptor-relative; never follow any supplied path component."""
    require(type(path) is str and path.startswith("/") and os.path.normpath(path) == path)
    parts = path.split("/")[1:]
    require(all(re.fullmatch(r"[A-Za-z0-9_.-]+", p) and p not in (".", "..") for p in parts))
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    current = os.open("/", flags)
    try:
        for component in parts:
            before = os.fstat(current)
            require(not stat.S_IMODE(before.st_mode) & 0o022)
            require(before.st_uid in (0, os.getuid()))
            child = os.open(component, flags, dir_fd=current)
            os.close(current)
            current = child
        info = os.fstat(current)
        require(not stat.S_IMODE(info.st_mode) & 0o022)
        require(info.st_uid in (0, os.getuid()))
        if private:
            require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700)
        return current
    except BaseException:
        os.close(current)
        raise


def open_file(directory, name, write=False):
    require(re.fullmatch(r"[A-Za-z0-9_.-]+", name) is not None)
    flags = (os.O_RDWR if write else os.O_RDONLY) | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
    fd = os.open(name, flags, dir_fd=directory)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1)
        require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o600)
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_bytes(fd, limit):
    require(os.fstat(fd).st_size <= limit)
    os.lseek(fd, 0, os.SEEK_SET)
    raw = os.read(fd, limit + 1)
    require(len(raw) <= limit and len(raw) == os.fstat(fd).st_size)
    return raw


def replace_bytes(fd, raw):
    os.lseek(fd, 0, os.SEEK_SET)
    require(os.write(fd, raw) == len(raw))
    os.ftruncate(fd, len(raw))
    os.fsync(fd)


def read_rows(fd):
    raw = read_bytes(fd, MAX_LEDGER)
    require(not raw or raw.endswith(b"\n"))
    lines = raw.splitlines()
    require(len(lines) <= 8192)
    return [strict_json(line, 16384) for line in lines]


def counts(value):
    closed(value, " ".join(EVENTS))
    require(all(type(v) is int and 0 <= v <= 256 for v in value.values()))


def manifest(raw):
    value = strict_json(raw)
    closed(value, "schema run_label scenario_ids input_sha256 hook_content_sha256 "
                  "rendered_config_sha256 config_template_sha256 expected_event_counts control_event_names session_binding_sha256")
    require(value["schema"] == "awa-codex-capture-run/v3")
    require(type(value["run_label"]) is str and re.fullmatch(r"C[1-9][0-9]{0,2}", value["run_label"]))
    selected = value["scenario_ids"]
    require(type(selected) is list and selected and all(type(i) is str and i in SCENARIOS for i in selected))
    require(selected == [i for i in SCENARIOS if i in selected])
    require(selected == ["A02"])
    require(type(value["session_binding_sha256"]) is str and HEX.fullmatch(value["session_binding_sha256"]))
    closed(value["input_sha256"], " ".join(FILES))
    require(all(type(v) is str and HEX.fullmatch(v) for v in value["input_sha256"].values()))
    for name in ("hook_content_sha256", "rendered_config_sha256", "config_template_sha256"):
        require(type(value[name]) is str and HEX.fullmatch(value[name]))
    require(value["hook_content_sha256"] == value["input_sha256"]["capture_hook.py"])
    require(value["config_template_sha256"] == value["input_sha256"]["fixture-hooks.v3.json.in"])
    closed(value["expected_event_counts"], " ".join(selected))
    for alternatives in value["expected_event_counts"].values():
        require(type(alternatives) is list and 1 <= len(alternatives) <= 8)
        for row in alternatives:
            counts(row)
        require(len({canonical(row) for row in alternatives}) == len(alternatives))
    closed(value["control_event_names"], " ".join(selected))
    for identifier, routes in value["control_event_names"].items():
        require(type(routes) is list and routes == [e for e in EVENTS if e in routes])
        require(bool(routes) if identifier != "C05" else not routes)
    require(value["expected_event_counts"] == {
        "A02": [{name: int(name == "UserPromptSubmit") for name in EVENTS}]
    })
    require(value["control_event_names"] == {"A02": ["UserPromptSubmit"]})
    return value


def event(value, run):
    closed(value, "schema run_label scenario_id sequence event_name source session_label turn_label "
                  "root_label identity_presence tool_class tool_discriminator hook_outcome "
                  "ordering_counter timing_bucket process_exit_class")
    require(value["schema"] == "awa-codex-capture-event/v3" and value["run_label"] == run["run_label"])
    require(value["scenario_id"] in run["scenario_ids"] and value["scenario_id"] != "C05")
    require(value["event_name"] in EVENTS and value["source"] in (None,) + SOURCES)
    require(value["session_label"] == "S1")
    for name, prefix in (("session_label", "S"), ("turn_label", "T")):
        label = value[name]
        require(label is None or (type(label) is str and LABEL.fullmatch(label) and label.startswith(prefix)))
        require(label is None or int(label[1:]) <= 2048)
    require(value["root_label"] in ("R1", "SUBDIR", "CHANGED", "MISSING", "AMBIGUOUS"))
    require(value["hook_outcome"] == "OBSERVED" and value["process_exit_class"] == "NOT_APPLICABLE")
    require(type(value["sequence"]) is int and 1 <= value["sequence"] <= 8192)
    require(type(value["ordering_counter"]) is int and value["ordering_counter"] == value["sequence"])
    require(value["timing_bucket"] in ("LT_10MS", "LT_100MS", "LT_1S", "LT_5S", "GTE_5S"))
    tool = (value["tool_class"], value["tool_discriminator"])
    require(tool in set(TOOLS.values()) | {(None, None), ("UNKNOWN", "UNKNOWN"), ("MCP", "UNKNOWN")})
    is_tool_event = value["event_name"] in ("PreToolUse", "PermissionRequest", "PostToolUse")
    require((tool != (None, None)) == is_tool_event)
    closed(value["identity_presence"], "session turn cwd")
    for presence in value["identity_presence"].values():
        closed(presence, "presence type length_bucket")
        require(presence["presence"] in ("PRESENT", "MISSING"))
        require(presence["type"] in ("STRING", "NULL", "OTHER"))
        require(presence["length_bucket"] in (None, "EMPTY", "1_64", "65_256", "257_4096", "OVER_4096"))
        require((presence["length_bucket"] is not None) == (presence["type"] == "STRING"))
        require(presence["presence"] != "MISSING" or presence["type"] == "NULL")
    for name, identity in (("session_label", "session"), ("turn_label", "turn")):
        if value[name] is not None:
            require(value["identity_presence"][identity]["type"] == "STRING")
            require(value["identity_presence"][identity]["length_bucket"] != "EMPTY")
    require(value["turn_label"] is None or value["session_label"] is not None)


def ledger(rows, run, manifest_sha256):
    active = None
    completed = []
    events = []
    seen_nonces = set()
    for ordinal, row in enumerate(rows, 1):
        require(type(row) is dict)
        kind = row.get("kind")
        if kind == "pre":
            closed(row, "kind scenario_id nonce action_sha256 manifest_sha256")
            require(active is None and row["scenario_id"] in run["scenario_ids"] and row["scenario_id"] != "C05")
            require(row["scenario_id"] not in [p["pre"]["scenario_id"] for p in completed])
            require(type(row["nonce"]) is str and re.fullmatch(r"[0-9a-f]{32}", row["nonce"]))
            require(row["nonce"] not in seen_nonces)
            require(type(row["action_sha256"]) is str and HEX.fullmatch(row["action_sha256"]))
            require(row["manifest_sha256"] == manifest_sha256)
            seen_nonces.add(row["nonce"])
            active = {"pre": row, "pre_barrier_id": ordinal, "phase": "BEFORE", "events": []}
        elif kind == "phase":
            closed(row, "kind scenario_id nonce phase session_label")
            require(active is not None and row["nonce"] == active["pre"]["nonce"])
            require(row["scenario_id"] == active["pre"]["scenario_id"])
            require((active["phase"], row["phase"]) in (("BEFORE", "ACTION"), ("ACTION", "AFTER")))
            label = row["session_label"]
            require(label is None or (type(label) is str and re.fullmatch(r"S[1-9][0-9]{0,3}", label) and int(label[1:]) <= 2048))
            if row["phase"] == "ACTION":
                active["action_session_label"] = label
            else:
                require(label == active["action_session_label"])
            active["phase"] = row["phase"]
        elif kind == "post":
            closed(row, "kind scenario_id nonce action_sha256 manifest_sha256 terminal origin health config_stability children_clean process_exit_class action_session_label control_sequences")
            require(active is not None and active["phase"] == "AFTER")
            for field in ("scenario_id", "nonce", "action_sha256", "manifest_sha256"):
                require(row[field] == active["pre"][field])
            require(row["action_session_label"] == active["action_session_label"])
            closed(row["control_sequences"], " ".join(run["control_event_names"][row["scenario_id"]]))
            for pair in row["control_sequences"].values():
                closed(pair, "before after")
                require(all(type(n) is int and 0 <= n <= 8192 for n in pair.values()))
            require(row["terminal"] in ("COMPLETED", "FAILED", "TIMEOUT", "UNKNOWN"))
            require(row["origin"] in ("HOST", "HARNESS"))
            require(row["health"] in ("SAME_ROUTE", "UNAVAILABLE"))
            require(row["config_stability"] in ("MATCH", "MISMATCH", "UNAVAILABLE"))
            require(type(row["children_clean"]) is bool and row["process_exit_class"] in EXIT_CLASSES)
            active.update(post=row, post_barrier_id=ordinal)
            completed.append(active)
            active = None
        elif kind == "event":
            closed(row, "kind phase event")
            require(active is not None and row["phase"] == active["phase"])
            event(row["event"], run)
            require(row["event"]["scenario_id"] == active["pre"]["scenario_id"])
            require(row["event"]["sequence"] == len(events) + 1)
            active["events"].append(row)
            events.append(row["event"])
        else:
            raise Invalid()
    return active, completed, events


def presence(raw, key):
    value = raw.get(key)
    bucket = None
    if type(value) is str:
        n = len(value)
        bucket = "EMPTY" if n == 0 else "1_64" if n <= 64 else "65_256" if n <= 256 else "257_4096" if n <= 4096 else "OVER_4096"
    return {"presence": "PRESENT" if key in raw else "MISSING",
            "type": "STRING" if type(value) is str else "NULL" if value is None else "OTHER",
            "length_bucket": bucket}


def bound_session(raw, labels, salt, binding):
    """Admit only the controller's prebound native session; never allocate one."""
    require(labels["session"] == {binding.hex(): "S1"})
    value = raw.get("session_id")
    require(type(value) is str and bool(value))
    token = hmac.new(salt, b"session\0" + value.encode("utf-8"), hashlib.sha256).digest()
    require(hmac.compare_digest(token, binding))
    return "S1"


def equality(labels, salt, kind, value):
    if type(value) is not str or not value:
        return None
    token = hmac.new(salt, kind.encode("ascii") + b"\0" + value.encode("utf-8"), hashlib.sha256).hexdigest()
    mapping = labels[kind]
    if token not in mapping:
        require(len(mapping) < 2048)
        mapping[token] = ("S" if kind == "session" else "T") + str(len(mapping) + 1)
    return mapping[token]


def root_relation(cwd, fixture):
    if cwd is None:
        return "MISSING"
    if type(cwd) is not str or os.path.normpath(cwd) != cwd:
        return "AMBIGUOUS"
    if cwd != fixture and not cwd.startswith(fixture + "/"):
        return "AMBIGUOUS"
    # Never open an arbitrary raw path. Only the approved lexical fixture can
    # reach the no-follow walk, and the hook's real cwd descriptor must agree.
    try:
        with contextlib.ExitStack() as stack:
            target = open_directory(cwd)
            stack.callback(os.close, target)
            actual = os.open(".", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            stack.callback(os.close, actual)
            a, b = os.fstat(target), os.fstat(actual)
            if (a.st_dev, a.st_ino) != (b.st_dev, b.st_ino):
                return "AMBIGUOUS"
        return "R1" if cwd == fixture else "SUBDIR"
    except (OSError, Invalid):
        return "AMBIGUOUS"


def collector_contention(directory, fd):
    """Read the preallocated sticky byte only through its original private inode."""
    info = os.stat("collector-contention.bin", dir_fd=directory, follow_symlinks=False)
    expected = os.fstat(fd)
    require((info.st_dev, info.st_ino) == (expected.st_dev, expected.st_ino))
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid())
    require(info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == 0o600)
    value = read_bytes(fd, 1)
    require(value in (b"0", b"1"))
    return value


def record_contention(directory, fd, capture):
    fresh = open_directory(capture, private=True)
    try:
        require((os.fstat(fresh).st_dev, os.fstat(fresh).st_ino) ==
                (os.fstat(directory).st_dev, os.fstat(directory).st_ino))
        collector_contention(directory, fd)
        require(os.pwrite(fd, b"1", 0) == 1)
        os.fsync(fd)
        require(collector_contention(directory, fd) == b"1")
    finally:
        os.close(fresh)


def observe():
    # This must precede any read of raw stdin; no payload enters diagnostics.
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode)
    started = time.monotonic()
    hook = os.path.abspath(__file__)
    suffix = "/fixture/.codex/hooks/capture_hook.py"
    require(hook.endswith(suffix))
    operation = hook[:-len(suffix)]
    capture = operation + "/capture"
    with contextlib.ExitStack() as stack:
        for private_path in (operation, operation + "/fixture"):
            private_fd = open_directory(private_path, private=True)
            stack.callback(os.close, private_fd)
        directory = open_directory(capture, private=True)
        stack.callback(os.close, directory)
        lock = open_file(directory, "capture.lock", write=True)
        stack.callback(os.close, lock)
        contention = open_file(directory, "collector-contention.bin", write=True)
        stack.callback(os.close, contention)
        collector_contention(directory, contention)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            # Keep the host action fail-open, but never silently qualify a lost event.
            record_contention(directory, contention, capture)
            raise Invalid()
        require(os.fstat(lock).st_size == 0)
        fds = {}
        for name in ("manifest.json", "salt.bin", "session.bin", "labels.json", "ledger.ndjson"):
            fds[name] = open_file(directory, name, write=name in ("labels.json", "ledger.ndjson"))
            stack.callback(os.close, fds[name])
        manifest_raw = read_bytes(fds["manifest.json"], MAX_JSON)
        run = manifest(manifest_raw)
        active, _completed, events = ledger(read_rows(fds["ledger.ndjson"]), run, digest(manifest_raw))
        require(active is not None)
        hooks = open_directory(operation + "/fixture/.codex/hooks", private=True)
        stack.callback(os.close, hooks)
        self_fd = open_file(hooks, "capture_hook.py")
        stack.callback(os.close, self_fd)
        require(digest(read_bytes(self_fd, MAX_JSON)) == run["hook_content_sha256"])
        config = open_directory(operation + "/fixture/.codex", private=True)
        stack.callback(os.close, config)
        config_fd = open_file(config, "hooks.json")
        stack.callback(os.close, config_fd)
        require(digest(read_bytes(config_fd, MAX_JSON)) == run["rendered_config_sha256"])
        salt = read_bytes(fds["salt.bin"], 32)
        require(len(salt) == 32)
        binding = read_bytes(fds["session.bin"], 32)
        require(len(binding) == 32 and digest(binding) == run["session_binding_sha256"])
        labels = strict_json(read_bytes(fds["labels.json"], MAX_JSON))
        closed(labels, "session turn")
        for kind, mapping in labels.items():
            require(type(mapping) is dict and len(mapping) <= 2048)
            for key, value in mapping.items():
                require(HEX.fullmatch(key) and type(value) is str and LABEL.fullmatch(value))
                require(value.startswith("S" if kind == "session" else "T"))
            require(len(set(mapping.values())) == len(mapping))
            prefix = "S" if kind == "session" else "T"
            require(set(mapping.values()) == {prefix + str(i) for i in range(1, len(mapping) + 1)})
        raw = strict_json(sys.stdin.buffer.read(65537), 65536)
        require(type(raw) is dict and raw.get("hook_event_name") in EVENTS)
        name = raw["hook_event_name"]
        session = bound_session(raw, labels, salt, binding)
        turn_raw = raw.get("turn_id")
        turn_value = (canonical([raw["session_id"], turn_raw]).decode("ascii")
                      if session is not None and type(turn_raw) is str and turn_raw else None)
        turn = equality(labels, salt, "turn", turn_value)
        cwd = raw.get("cwd")
        fixture = operation + "/fixture"
        relation = root_relation(cwd, fixture)
        source_field = "trigger" if name in ("PreCompact", "PostCompact") else "reason" if name == "SessionEnd" else "source"
        source_raw = raw.get(source_field)
        source = None if source_raw is None else source_raw if source_raw in SOURCES else "UNKNOWN"
        tool_name = raw.get("tool_name")
        tool = (None, None)
        if name in ("PreToolUse", "PermissionRequest", "PostToolUse"):
            tool = TOOLS.get(tool_name, ("MCP", "UNKNOWN") if type(tool_name) is str and tool_name.startswith("mcp__") else ("UNKNOWN", "UNKNOWN"))
        elapsed = max(0.0, time.monotonic() - started)
        bucket = "LT_10MS" if elapsed < .01 else "LT_100MS" if elapsed < .1 else "LT_1S" if elapsed < 1 else "LT_5S" if elapsed < 5 else "GTE_5S"
        row = {
            "schema": "awa-codex-capture-event/v3", "run_label": run["run_label"],
            "scenario_id": active["pre"]["scenario_id"], "sequence": len(events) + 1,
            "event_name": name, "source": source, "session_label": session, "turn_label": turn,
            "root_label": relation,
            "identity_presence": {"session": presence(raw, "session_id"), "turn": presence(raw, "turn_id"), "cwd": presence(raw, "cwd")},
            "tool_class": tool[0], "tool_discriminator": tool[1], "hook_outcome": "OBSERVED",
            "ordering_counter": len(events) + 1, "timing_bucket": bucket,
            "process_exit_class": "NOT_APPLICABLE",
        }
        event(row, run)
        require(len(events) < 4096)
        # Recheck namespace identity before writes. No directory/file is created.
        fresh = open_directory(capture, private=True)
        try:
            require((os.fstat(fresh).st_dev, os.fstat(fresh).st_ino) ==
                    (os.fstat(directory).st_dev, os.fstat(directory).st_ino))
        finally:
            os.close(fresh)
        replace_bytes(fds["labels.json"], canonical(labels))
        record = canonical({"kind": "event", "phase": active["phase"], "event": row}) + b"\n"
        require(os.fstat(fds["ledger.ndjson"]).st_size + len(record) <= MAX_LEDGER)
        os.lseek(fds["ledger.ndjson"], 0, os.SEEK_END)
        require(os.write(fds["ledger.ndjson"], record) == len(record))
        os.fsync(fds["ledger.ndjson"])


def main():
    try:
        if len(sys.argv) == 1:
            observe()
    except BaseException:
        pass
    # The observer never returns model context, raw text or a blocking decision.
    try:
        sys.stdout.write("{}\n")
    except BaseException:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
