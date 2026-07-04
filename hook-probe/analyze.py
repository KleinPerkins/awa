#!/usr/bin/env python3
"""Read-only analyzer for the AWA hook-probe harness.

Reads the JSONL event log produced by probe-hook.sh and prints, per event:
  - whether it fired (and how many times)
  - the observed stdin field names (union across invocations)
  - a surface inference (Desktop vs cloud) for the whole run
  - a verdict scaffold for the afterFileEdit deny-is-ignored question

Dependency-free (Python 3 stdlib only). It NEVER writes anything; it only
reads the log file. It does NOT itself prove that an edit landed — that is a
runtime fact the operator must observe and note (see README).
"""

import argparse
import json
import os
import sys

# The full set of project-hook events this harness wires up (hooks.json).
ALL_EVENTS = [
    "sessionStart",
    "beforeSubmitPrompt",
    "beforeShellExecution",
    "beforeReadFile",
    "beforeMCPExecution",
    "afterFileEdit",
    "stop",
    "sessionEnd",
    "workspaceOpen",
]

# Events that only exist on Desktop agents (absent in cloud). If any of these
# is observed, the run is Desktop; if none are, the run is (probably) cloud.
DESKTOP_ONLY_EVENTS = {
    "sessionStart",
    "beforeSubmitPrompt",
    "beforeMCPExecution",
    "stop",
    "sessionEnd",
    "workspaceOpen",
}


def default_log_path():
    base = os.environ.get("XDG_STATE_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "state"
    )
    return os.path.join(base, "awa", "hook-probe", "events.jsonl")


def load_records(path):
    records = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                sys.stderr.write(f"warning: skipping malformed line {lineno}\n")
    return records


def infer_surface(seen_events):
    desktop_seen = sorted(seen_events & DESKTOP_ONLY_EVENTS)
    if desktop_seen:
        return "Desktop", desktop_seen
    if seen_events:
        return "cloud (probable)", []
    return "unknown (no events)", []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "log",
        nargs="?",
        default=default_log_path(),
        help="path to events.jsonl (default: XDG state dir)",
    )
    args = parser.parse_args()

    if not os.path.exists(args.log):
        sys.stderr.write(
            f"no log file at {args.log}\n"
            "Run the harness first (see README.md), then re-run this analyzer.\n"
        )
        return 2

    records = load_records(args.log)
    if not records:
        sys.stderr.write(f"log file {args.log} has no parseable records\n")
        return 2

    # Aggregate per event.
    counts = {}
    fields = {}
    for rec in records:
        event = rec.get("event", "unknown")
        counts[event] = counts.get(event, 0) + 1
        keys = rec.get("payload_keys") or []
        fields.setdefault(event, set()).update(keys)

    seen_events = {e for e, c in counts.items() if c > 0}
    surface, desktop_seen = infer_surface(seen_events)

    print(f"log file: {args.log}")
    print(f"records:  {len(records)}")
    print(f"surface:  {surface}")
    if desktop_seen:
        print(f"          (Desktop-only events observed: {', '.join(desktop_seen)})")
    print()

    header = f"{'event':<22} {'fired':<7} {'count':<6} observed_stdin_fields"
    print(header)
    print("-" * len(header))
    # Known events first (stable order), then any unexpected extras.
    ordered = ALL_EVENTS + [e for e in sorted(counts) if e not in ALL_EVENTS]
    seen_print = set()
    for event in ordered:
        if event in seen_print:
            continue
        seen_print.add(event)
        count = counts.get(event, 0)
        fired = "yes" if count else "no"
        field_names = ", ".join(sorted(fields.get(event, set()))) or "-"
        print(f"{event:<22} {fired:<7} {count:<6} {field_names}")

    print()
    _afterfileedit_verdict(counts, fields)
    return 0


def _afterfileedit_verdict(counts, fields):
    print("afterFileEdit deny verdict:")
    if not counts.get("afterFileEdit"):
        print("  afterFileEdit did not fire — cannot assess. Drive one file edit "
              "on the probed agent and re-run.")
        return
    print("  afterFileEdit fired and probe-hook.sh returned "
          '{"permission":"deny", ...} on each invocation.')
    print("  Claim under test (ledger L4): Cursor IGNORES a permission returned "
          "from a POST-action hook.")
    print("  Verdict requires the runtime observation the operator recorded: did "
          "the edited file actually change on disk?")
    print("    - edit LANDED  -> deny was IGNORED -> L4 confirmed "
          "(afterFileEdit is observation-only).")
    print("    - edit BLOCKED -> deny was HONORED -> L4 REFUTED (investigate).")
    print("  observed afterFileEdit stdin fields: "
          + (", ".join(sorted(fields.get("afterFileEdit", set()))) or "-"))


if __name__ == "__main__":
    sys.exit(main())
