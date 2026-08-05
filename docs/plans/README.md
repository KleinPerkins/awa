# `docs/plans/` — planning-document convention

This directory holds every substantial execution/design plan for AWA (a corrective
pass, a milestone build-out, a go-live). Convention adapted from the equivalent,
proven convention in `KleinPerkins/pr-automation-controller` (`docs/plans/README.md`),
which a concurrent cross-fleet documentation-governance review (`~/dev`'s in-progress
"doc-warden" initiative, `_ops/plans/doc-warden-execution-plan-v1.md`, DRAFT as of
2026-08-05) independently identified as the fleet's clearest versioned-plan +
Nygard-ADR convention. Adopting it here now, ahead of that initiative reaching general
availability, means no rework is expected when/if a fleet-wide convention formally
lands — this directory already follows the reference shape it derived from.

## The convention

1. **Header.** Title as an H1, then a bare bullet list directly under it — no
   `## Metadata` heading:
   - `- **Version:** vN`
   - `- **Status:** DRAFT (for review) | APPROVED — FROZEN (immutable) | COMPLETE | ...`
   - `- **Date:** YYYY-MM-DD`
   - Optionally `**Supersedes:**` / `**Relates to:**` / `**Review provenance:**` /
     `**Version discipline:**` bullets, as needed.
2. **Naming.** `<topic-slug>-vN.md`. A continuously-amended single-version tracker
   (no competing versions expected) may omit the `-vN` suffix.
3. **Freeze-on-approval.** Once a version is owner-approved (or superseded by a newer
   version), it is **frozen immutable** — never edit it again, including for typos. A
   revision is always a **new** `-v<N+1>.md` file, preserving the prior version
   byte-identically. State the pointer explicitly in the new file's `**Supersedes:**`
   bullet and, where practical, add a one-line "now frozen historical" note to the
   superseded file's own `**Status:**` bullet (its body stays untouched).
4. **Body shape.** purpose and boundary → live-state verification → inherited
   scope/ground truth → numbered or lettered decisions → acceptance-test ledger →
   non-goals → owner GO/NO-GO gate → review provenance. Pick whichever skeleton fits
   a *new* document's shape and stay internally consistent within that document; do
   not retrofit an old file to a newer skeleton.
5. **Discoverability.** Any agent or reviewer starting work in this repo should read
   this file before writing a new plan or acting on an old one. The root `AGENTS.md`
   points here.

## Index

| File | Status | One-line description |
|---|---|---|
| `guard-target-path-precision-v1.md` | Proposed — 2026-08-05 | Fix `beforeShellExecution` DENYing mutating commands whose resolved target path is outside every protected primary checkout (e.g. `rm /tmp/x` from inside a protected repo); establishes this `docs/` governance layer itself. |

## Related conventions

- `docs/adr/` (architecture decision records) has its own equivalent
  convention/index file — [`docs/adr/README.md`](../adr/README.md).
