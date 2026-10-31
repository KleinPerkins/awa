"""Offline verifier for the reviewed controller-bound A03 capture bundle."""

from __future__ import annotations

import collections
import copy
import contextlib
import fcntl
import hashlib
import importlib.util
import os
import re
import resource
import stat
import sys

def load_core():
    """Load only the reviewed sibling, independent of cwd/PYTHONPATH/user site."""
    if not (sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode):
        raise ValueError()
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    root = os.path.dirname(os.path.abspath(__file__))
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        expected_names = {
            "README.md", "capture_hook.py", "verify_capture.py", "capture-schema.v2.json",
            "scenario-catalog.v2.json", "forbidden-fields.v2.txt", "fixture-hooks.v2.json.in",
            "MANIFEST.sha256",
        }
        if set(os.listdir(directory)) != expected_names:
            raise ValueError()
        data = {}
        for name in ("MANIFEST.sha256", "capture_hook.py"):
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=directory)
            try:
                info = os.fstat(fd)
                if not (stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and
                        info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o644 and
                        info.st_size <= 1024 * 1024):
                    raise ValueError()
                data[name] = os.read(fd, 1024 * 1024 + 1)
                if len(data[name]) != info.st_size:
                    raise ValueError()
            finally:
                os.close(fd)
        line = [s for s in data["MANIFEST.sha256"].decode("ascii").splitlines()
                if re.fullmatch(r"[0-9a-f]{64}  capture_hook.py", s)]
        if len(line) != 1 or hashlib.sha256(data["capture_hook.py"]).hexdigest() != line[0][:64]:
            raise ValueError()
        spec = importlib.util.spec_from_loader("_awa_capture_source", loader=None)
        module = importlib.util.module_from_spec(spec)
        module.__file__ = root + "/capture_hook.py"
        exec(compile(data["capture_hook.py"], module.__file__, "exec"), module.__dict__)
        return module
    finally:
        os.close(directory)


c = None


def source_inputs():
    root = os.path.dirname(os.path.abspath(__file__))
    with contextlib.ExitStack() as stack:
        directory = c.open_directory(root)
        stack.callback(os.close, directory)

        def read(name):
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=directory)
            stack.callback(os.close, fd)
            info = os.fstat(fd)
            c.require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid())
            c.require(info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == 0o644)
            return c.read_bytes(fd, c.MAX_JSON)

        manifest_raw = read("MANIFEST.sha256")
        wanted = {}
        for line in manifest_raw.decode("ascii").splitlines():
            parts = line.split("  ")
            c.require(len(parts) == 2 and c.HEX.fullmatch(parts[0]) and parts[1] in c.FILES)
            c.require(parts[1] not in wanted)
            wanted[parts[1]] = parts[0]
        c.require(list(wanted) == sorted(c.FILES))
        contents = {name: read(name) for name in c.FILES}
        c.require(wanted == {name: c.digest(raw) for name, raw in contents.items()})
        catalog = c.strict_json(contents["scenario-catalog.v2.json"])
        c.closed(catalog, "schema scenarios")
        c.require(catalog["schema"] == "awa-codex-capture-catalog/v2")
        c.require(type(catalog["scenarios"]) is list)
        c.require([row.get("id") for row in catalog["scenarios"]] == list(c.SCENARIOS))
        for row in catalog["scenarios"]:
            c.closed(row, "id action gate executable session_rule event_predicates")
            c.require(type(row["action"]) is str and c.re.fullmatch(r"[A-Z0-9_]+", row["action"]))
            c.require(type(row["executable"]) is bool and row["executable"] == (row["id"] == "A03"))
            c.require(row["gate"] in ("CP2-A", "CP2-HOSTED", "CP3", "CP4", "CP5", "NONE"))
            c.require(row["session_rule"] in ("SAME", "OBSERVE", "NONE"))
            c.require(type(row["event_predicates"]) is list and len(row["event_predicates"]) <= 4)
            for predicate in row["event_predicates"]:
                c.closed(predicate, "event_names sources tool_discriminators root_labels")
                for key, domain in (
                    ("event_names", c.EVENTS), ("sources", (None,) + c.SOURCES),
                    ("tool_discriminators", (None,) + tuple(sorted({t[1] for t in c.TOOLS.values()}))),
                    ("root_labels", ("R1", "SUBDIR", "CHANGED", "MISSING", "AMBIGUOUS")),
                ):
                    values = predicate[key]
                    c.require(type(values) is list and values and len(values) == len(set(values)))
                    c.require(all(v in domain for v in values))
        return wanted, contents, {r["id"]: r for r in catalog["scenarios"]}


def render_config(hook_path):
    """Pure later-CP1 rendering; no allocation, config discovery, trust or write."""
    c.require(type(hook_path) is str and hook_path.endswith("/fixture/.codex/hooks/capture_hook.py"))
    c.require(hook_path.startswith("/") and os.path.normpath(hook_path) == hook_path)
    c.require(all(re.fullmatch(r"[A-Za-z0-9_.-]+", part) and part not in (".", "..")
                  for part in hook_path.split("/")[1:]))
    _inputs, contents, _catalog = source_inputs()
    raw = contents["fixture-hooks.v2.json.in"]
    c.require(raw.count(b"@@CAPTURE_HOOK_PATH@@") == 1)
    rendered = c.strict_json(raw.replace(b"@@CAPTURE_HOOK_PATH@@", hook_path.encode("ascii")))
    c.closed(rendered, "description hooks")
    c.closed(rendered["hooks"], "PreToolUse")
    seed = rendered["hooks"]["PreToolUse"]
    rendered["hooks"] = {name: copy.deepcopy(seed) for name in c.EVENTS}
    return c.canonical(rendered) + b"\n"


def same_route_controls(scenario, run):
    before = [r["event"] for r in scenario["events"] if r["phase"] == "BEFORE"]
    after = [r["event"] for r in scenario["events"] if r["phase"] == "AFTER"]
    routes = run["control_event_names"][scenario["pre"]["scenario_id"]]
    pairs = scenario["post"]["control_sequences"]
    session = scenario["action_session_label"]
    if session is None or len(before) != len(routes) or len(after) != len(routes):
        return False
    action_routes = {r["event"]["event_name"] for r in scenario["events"] if r["phase"] == "ACTION"}
    if not action_routes.issubset(routes):
        return False
    for route in routes:
        matching = any(
            b["event_name"] == a["event_name"] == route
            and b["sequence"] == pairs[route]["before"]
            and a["sequence"] == pairs[route]["after"]
            and b["session_label"] == a["session_label"] == session
            and b["root_label"] in ("R1", "SUBDIR")
            and a["root_label"] in ("R1", "SUBDIR")
            for b in before for a in after
        )
        if not matching:
            return False
    return bool(routes)


def validate_action(events, signature, session):
    for event in events:
        c.require(any(
            event["event_name"] in p["event_names"] and event["source"] in p["sources"]
            and event["tool_discriminator"] in p["tool_discriminators"]
            and event["root_label"] in p["root_labels"]
            for p in signature["event_predicates"]
        ))
        if signature["session_rule"] == "SAME":
            c.require(session is not None and event["session_label"] == session)


def scenario_row(identifier, scenario, run, catalog):
    empty_counts = dict.fromkeys(c.EVENTS, 0)
    action_hash = c.digest(c.canonical(catalog[identifier]))
    if identifier == "C05":
        c.require(scenario is None and run["expected_event_counts"][identifier] == [empty_counts])
        pre_id = post_id = 0
        observed = empty_counts
        exit_class = "NOT_APPLICABLE"
        health = "UNKNOWN"
        witness = "NOT_APPLICABLE"
        route_match = "UNAVAILABLE"
        completion = "DOCUMENTATION_ONLY"
        stability = "UNAVAILABLE"
    else:
        c.require(scenario is not None)
        pre, post = scenario["pre"], scenario["post"]
        c.require(pre["action_sha256"] == post["action_sha256"] == action_hash)
        c.require(post["terminal"] == "COMPLETED" and post["origin"] == "HOST")
        c.require(post["children_clean"] is True and post["config_stability"] == "MATCH")
        c.require(post["process_exit_class"] not in ("SIGNAL", "TIMEOUT"))
        action_events = [r["event"] for r in scenario["events"] if r["phase"] == "ACTION"]
        validate_action(action_events, catalog[identifier], scenario["action_session_label"])
        allowed_routes = {name for predicate in catalog[identifier]["event_predicates"]
                          for name in predicate["event_names"]}
        if identifier == "C02":
            allowed_routes = {"PreToolUse", "PermissionRequest", "PostToolUse"}
        c.require(set(run["control_event_names"][identifier]).issubset(allowed_routes))
        actual = collections.Counter(e["event_name"] for e in action_events)
        observed = {name: actual[name] for name in c.EVENTS}
        c.require(observed in run["expected_event_counts"][identifier])
        # V2 is A03-only: exact controls are mandatory even when health is unknown.
        c.require(same_route_controls(scenario, run))
        controlled = (catalog[identifier]["session_rule"] == "SAME" and
                      post["health"] == "SAME_ROUTE" and same_route_controls(scenario, run))
        # An asserted positive-control result must be backed by actual callbacks.
        c.require(post["health"] != "SAME_ROUTE" or controlled)
        health = "HEALTHY" if controlled else "UNKNOWN"
        route_match = "SAME_ROUTE" if controlled else "UNAVAILABLE"
        witness = "MATCHED"
        completion = "OBSERVED" if controlled and sum(observed.values()) else "UNPROVEN"
        pre_id, post_id = scenario["pre_barrier_id"], scenario["post_barrier_id"]
        exit_class = post["process_exit_class"]
        stability = "MATCH"
    return {
        "schema": "awa-codex-capture-scenario/v2", "run_label": run["run_label"],
        "scenario_id": identifier, "scenario_action_sha256": action_hash,
        "pre_barrier_id": pre_id, "post_barrier_id": post_id,
        "expected_event_counts": observed,
        "observed_event_counts": observed, "harness_health": health,
        "hook_content_sha256": run["hook_content_sha256"],
        "config_template_sha256": run["config_template_sha256"],
        "rendered_config_stability": stability, "action_witness": witness,
        "positive_control_route_match": route_match, "process_exit_class": exit_class,
        "completion_status": completion,
    }


def verify(path):
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    inputs, contents, catalog = source_inputs()
    c.require(path.endswith("/capture"))
    operation = path[:-len("/capture")]
    with contextlib.ExitStack() as stack:
        for private_path in (operation, operation + "/fixture"):
            private_fd = c.open_directory(private_path, private=True)
            stack.callback(os.close, private_fd)
        directory = c.open_directory(path, private=True)
        stack.callback(os.close, directory)
        c.require(set(os.listdir(directory)) == {"manifest.json", "ledger.ndjson", "capture.lock"})
        lock = c.open_file(directory, "capture.lock", write=True)
        stack.callback(os.close, lock)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        c.require(os.fstat(lock).st_size == 0)
        manifest_fd = c.open_file(directory, "manifest.json")
        stack.callback(os.close, manifest_fd)
        manifest_raw = c.read_bytes(manifest_fd, c.MAX_JSON)
        run = c.manifest(manifest_raw)
        c.require(run["input_sha256"] == inputs)
        hooks = c.open_directory(operation + "/fixture/.codex/hooks", private=True)
        stack.callback(os.close, hooks)
        hook_fd = c.open_file(hooks, "capture_hook.py")
        stack.callback(os.close, hook_fd)
        c.require(c.digest(c.read_bytes(hook_fd, c.MAX_JSON)) == run["hook_content_sha256"])
        config = c.open_directory(operation + "/fixture/.codex", private=True)
        stack.callback(os.close, config)
        config_fd = c.open_file(config, "hooks.json")
        stack.callback(os.close, config_fd)
        c.require(c.digest(c.read_bytes(config_fd, c.MAX_JSON)) == run["rendered_config_sha256"])
        ledger_fd = c.open_file(directory, "ledger.ndjson")
        stack.callback(os.close, ledger_fd)
        active, completed, events = c.ledger(c.read_rows(ledger_fd), run, c.digest(manifest_raw))
        c.require(active is None)
        selected_live = [i for i in run["scenario_ids"] if i != "C05"]
        c.require([s["pre"]["scenario_id"] for s in completed] == selected_live)
        scenarios = {s["pre"]["scenario_id"]: s for s in completed}
        export = {
            "schema": "awa-codex-capture-export/v2", "run_label": run["run_label"],
            "session_scope": "CONTROLLER_BOUND",
            "input_sha256": inputs, "events": events,
            "scenarios": [scenario_row(i, scenarios.get(i), run, catalog) for i in run["scenario_ids"]],
        }
        raw = c.canonical(export) + b"\n"
        c.require(len(raw) <= c.MAX_LEDGER)
        lower = raw.lower()
        corpus = contents["forbidden-fields.v2.txt"].decode("utf-8").splitlines()
        c.require(corpus and all(line and line == line.strip() for line in corpus))
        c.require(not any(line.lower().encode("utf-8") in lower for line in corpus))
        # Recheck fixed namespace and ephemera absence under the controller lock.
        fresh = c.open_directory(path, private=True)
        try:
            c.require((os.fstat(fresh).st_dev, os.fstat(fresh).st_ino) ==
                      (os.fstat(directory).st_dev, os.fstat(directory).st_ino))
            c.require(set(os.listdir(fresh)) == {"manifest.json", "ledger.ndjson", "capture.lock"})
        finally:
            os.close(fresh)
        fd = os.open("export.pending", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                     0o600, dir_fd=directory)
        try:
            os.fchmod(fd, 0o600)
            remaining = memoryview(raw)
            while remaining:
                written = os.write(fd, remaining)
                c.require(written > 0)
                remaining = remaining[written:]
            os.fsync(fd)
            os.link("export.pending", "export.json", src_dir_fd=directory, dst_dir_fd=directory,
                    follow_symlinks=False)
            os.unlink("export.pending", dir_fd=directory)
            os.fsync(directory)
        finally:
            os.close(fd)
        return c.digest(raw)


def main():
    global c
    try:
        c = load_core()
        c.require(len(sys.argv) == 2)
        result = verify(sys.argv[1])
    except BaseException:
        sys.stderr.write("FAILED_EVIDENCE\n")
        return 1
    sys.stdout.write(result + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
