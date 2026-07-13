"""_trial_live.py — the inherently live-Desktop-only surfaces (D1-D4).

These CANNOT be proven headlessly (per AGENTS.md: do not claim live Desktop proof from tests). They
are recorded in the matrix as ``live-deferred`` (SKIP) rows so the matrix has ZERO silent gaps and
each points at the operator step in ``LIVE-OPERATOR-RUNBOOK.md`` that proves it. The kernel safety
guarantee (exact-`Close`-only, fail-safe preservation, zero-network removal) is fully headless-proven
and does NOT depend on any of D1-D4.
"""

from __future__ import annotations

from _trial_lib import Row, transition


def _skip(_sb):  # never invoked: run_trial short-circuits live-deferred rows to SKIP
    return ""


@transition(Row(
    id="LIVE-D1-HOOK-RENDER", phase="LV", layer="live-deferred",
    title="Cursor Desktop renders the warning modal + hard-blocks the prompt",
    precondition="disposable UAT runtime + throwaway worktree opened in a Cursor window",
    inp="operator submits `I'm done`",
    expected="the fixed WARNING block renders, five options each on their own line, submission blocked",
    oracle="LIVE-OPERATOR-RUNBOOK.md step L1 (build-dependent; convenience, not the safety gate)"))
def d1(sb):
    return _skip(sb)


@transition(Row(
    id="LIVE-D2-CHOICE-SUBMIT", phase="LV", layer="live-deferred",
    title="Live operator submission of Close / Commit / Retain / Mixed",
    precondition="pending finish dialogue on the throwaway worktree",
    inp="operator submits each choice; agent runs `dispatch --current`",
    expected="real removal on exact Close; real Retain artifact; real Commit delivery; correction on Close-variant",
    oracle="LIVE-OPERATOR-RUNBOOK.md steps L2-L6 (only `I'm done`+`Cancel` were driven live to date)"))
def d2(sb):
    return _skip(sb)


@transition(Row(
    id="LIVE-D3-AGENT-STOP", phase="LV", layer="live-deferred",
    title="Live agent runtime cessation after a terminal Close",
    precondition="a successful live Close on the throwaway worktree",
    inp="observe the agent after the terminal receipt",
    expected="agent issues no further task tools; chat stays open (flags headless-proven, cessation live-only)",
    oracle="LIVE-OPERATOR-RUNBOOK.md step L6 verification"))
def d3(sb):
    return _skip(sb)


@transition(Row(
    id="LIVE-D4-COMMIT-GITHUB", phase="LV", layer="live-deferred",
    title="Commit delivery against a real GitHub remote",
    precondition="a throwaway GitHub repo with merge commits enabled",
    inp="operator submits Commit; agent runs `commit` against a real merged PR",
    expected="exact-head merge-commit PR into the live default branch with complete passing checks",
    oracle="LIVE-OPERATOR-RUNBOOK.md step L5 (evaluator + failure matrix are headless-proven)"))
def d4(sb):
    return _skip(sb)
