#!/usr/bin/env python3
"""run_trial.py — AWA Root-Bound Worktree Finish comprehensive UAT trial runner (Layer A).

Drives EVERY finish/retention state transition built across Phases 1-3 end-to-end against a fully
disposable sandbox and emits a results matrix. See ``README.md`` for the full description and
``LIVE-OPERATOR-RUNBOOK.md`` for the Desktop-only (Layer B) surfaces.

Run:

    python3 live-verify/trial-runner/run_trial.py

Options:

    --json-out PATH   also write the machine-readable matrix to PATH
    --filter TEXT     only run transitions whose id/phase/title contains TEXT (case-insensitive)
    --list            list the registered transitions and exit (no sandboxes created)
    --quiet           print only the summary + failures

Exit code is non-zero if any headless transition FAILs/ERRORs or the real environment was touched.
It is idempotent and self-cleaning: every transition provisions and tears down its own sandbox, and
the real state root (~/.local/state/awa) + this worktree's git status are fingerprinted before and
after the run and asserted unchanged.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import _trial_lib as lib  # noqa: E402
# Import the phase modules for their registration side effects.
import _trial_phase1  # noqa: E402,F401
import _trial_phase2  # noqa: E402,F401
import _trial_phase3  # noqa: E402,F401
import _trial_live  # noqa: E402,F401

from _trial_lib import PASS, FAIL, ERROR, SKIP, Row, Sandbox, TrialAssertion  # noqa: E402


def _run_one(row: Row, drive) -> None:
    if row.layer == "live-deferred":
        row.status = SKIP
        return
    try:
        with Sandbox() as sb:
            observed = drive(sb)
        row.observed = observed or ""
        row.status = PASS
    except TrialAssertion as exc:
        row.status = FAIL
        row.detail = str(exc)
    except Exception as exc:  # noqa: BLE001 — any crash is an ERROR row, never a silent pass
        row.status = ERROR
        row.detail = f"{type(exc).__name__}: {exc}\n" + "".join(
            traceback.format_exc().splitlines(keepends=True)[-4:])


def _human_table(rows: list[Row]) -> str:
    width = max((len(r.id) for r in rows), default=8)
    lines = [f"{'ID'.ljust(width)}  PH   STATUS  LAYER          TITLE",
             f"{'-' * width}  --   ------  -----          -----"]
    for r in rows:
        lines.append(
            f"{r.id.ljust(width)}  {r.phase:<3}  {r.status:<6}  {r.layer:<13}  {r.title}")
    return "\n".join(lines)


def _summary(rows: list[Row]) -> dict:
    counts = {PASS: 0, FAIL: 0, ERROR: 0, SKIP: 0}
    for r in rows:
        counts[r.status] = counts.get(r.status, 0) + 1
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="run_trial.py",
                                 description="AWA finish/retention comprehensive UAT trial runner")
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--filter", default=None)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    registry = lib.registry()
    if args.filter:
        needle = args.filter.lower()
        registry = [(r, fn) for (r, fn) in registry
                    if needle in (r.id + r.phase + r.title).lower()]

    rows = [r for (r, _fn) in registry]

    if args.list:
        print(_human_table(rows))
        print(f"\n{len(rows)} transitions registered.")
        return 0

    before = lib.fingerprint_real_env()
    started = time.time()
    for row, drive in registry:
        _run_one(row, drive)
        if not args.quiet:
            marker = {PASS: "ok ", FAIL: "FAIL", ERROR: "ERR ", SKIP: "skip"}[row.status]
            print(f"[{marker}] {row.id}  {row.title}")
            if row.status in (FAIL, ERROR):
                print(f"        -> {row.detail.strip().splitlines()[0] if row.detail else ''}")
    elapsed = time.time() - started

    # ---- real-environment guard (idempotent + self-clean proof) ----
    after = lib.fingerprint_real_env()
    problems = lib.diff_real_env(before, after)
    churn = lib.live_churn(before, after)
    guard = Row(
        id="GUARD-REAL-ENV-UNTOUCHED", phase="G", title="Real state root + worktree git unchanged",
        precondition="fingerprint before/after the whole run",
        inp="compare ~/.local/state/awa non-volatile file-set + worktree git status/HEAD",
        expected="no added/removed/resized files in the finish/recovery/non-volatile state; worktree git unchanged",
        oracle="harness self-check (live-runtime heartbeat/receipt/lock churn excluded — see _is_volatile)")
    if problems:
        guard.status = FAIL
        guard.detail = "; ".join(problems)
    else:
        guard.status = PASS
        guard.observed = (
            f"finish/recovery/non-volatile state unchanged ({after['strict_count']} files); "
            f"worktree git status+HEAD unchanged; "
            f"{churn} live-runtime volatile heartbeat/receipt/lock file(s) changed concurrently "
            f"(not harness-caused)")
    rows.append(guard)

    counts = _summary(rows)
    matrix = {
        "schema": "awa-finish-uat-matrix/v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source_head": before["wt_head"],
        "elapsed_seconds": round(elapsed, 2),
        "counts": counts,
        "rows": [r.to_dict() for r in rows],
    }

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(matrix, indent=2, sort_keys=True),
                                       encoding="utf-8")

    print("\n" + _human_table(rows))
    print("\n--- failures / errors ---")
    any_bad = False
    for r in rows:
        if r.status in (FAIL, ERROR):
            any_bad = True
            print(f"\n{r.status}  {r.id}  ({r.oracle})")
            print(f"  {r.detail.strip()}")
    if not any_bad:
        print("(none)")

    print("\n=== BEGIN MACHINE-READABLE MATRIX (awa-finish-uat-matrix/v1) ===")
    print(json.dumps({k: matrix[k] for k in ("counts", "source_head", "elapsed_seconds")},
                     sort_keys=True))
    print("=== END MACHINE-READABLE MATRIX ===")

    total = len(rows)
    print(f"\nSummary: {counts[PASS]} PASS, {counts[FAIL]} FAIL, {counts[ERROR]} ERROR, "
          f"{counts[SKIP]} SKIP (live-deferred) of {total} rows in {elapsed:.1f}s")
    return 1 if (counts[FAIL] or counts[ERROR]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
