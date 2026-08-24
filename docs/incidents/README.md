# Incident Records

This directory contains incident and remediation records for `awa`.

**Governance:** `~/dev/_ops/doc-warden/POLICY.md` §2 (taxonomy), §10 rule 9 (normalization).
AWA uses the `docs/` convention for all governed artifacts, so incident records live here under
`docs/incidents/` (the policy's docs-convention carve-out) rather than `_ops/incidents/`. Incident
records track what happened, impact, root cause, and corrective actions for significant events.
The index below is mutable as incidents move from `DRAFT` to `closed`; the record template shape
(the five `## What Happened / Impact / Root Cause / What We Changed / Notes` sections) stays fixed.

## Index

| Incident | Status | Date | Notes |
|---|---|---|---|
| [awa-integrity-incident-20260824.md](awa-integrity-incident-20260824.md) | DRAFT — 2026-08-24 (open) | 2026-08-24 | Reported "guard bug" REFUTED — the guard correctly denied `cd <worktree> && commit` from a protected primary. Real gaps: Safe-Workspace entry (external `move_agent_to_root` broke) and unmonitored lifecycle/surveillance (64 leaseless worktrees, 2 unreconciled leases, 12 dangling in-namespace sessions, a legacy recovery-scan error since cleared reversibly into `.trash`). Overall integrity DEGRADED, not green. Corrective design: ADR 0020 + plan `awa-integrity-surveillance-and-lifecycle-v1`. |

## Conventions

- Filename: `<slug>.md`
- Status values: `DRAFT` while the record is being authored / the incident is open, then `closed`
  once all corrective items are confirmed complete
- Store one incident narrative per file; related follow-up work (ADRs, plans) is linked from the record
