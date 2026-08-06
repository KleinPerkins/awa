# `docs/adr/` — architecture decision records

This directory holds durable architecture decisions for AWA — the "why," not the "how"
(that's `docs/plans/`). Convention adapted from the equivalent, proven convention in
`KleinPerkins/pr-automation-controller` (`docs/adr/README.md`), which a concurrent
cross-fleet documentation-governance review (`~/dev`'s in-progress "doc-warden"
initiative, `_ops/plans/doc-warden-execution-plan-v1.md`, DRAFT as of 2026-08-05)
independently identified as the fleet's clearest versioned-plan + Nygard-ADR
convention. Adopting it here now, ahead of that initiative reaching general
availability, means no rework is expected when/if a fleet-wide convention formally
lands — this directory already follows the reference shape it derived from.

## The convention

1. **Header.** `# ADR NNNN: <title>` (4-digit, zero-padded, sequential — never reused,
   even if a later decision reverses an earlier one), then
   `Status: <status> — YYYY-MM-DD (optional context)` on the next line. Valid statuses:
   `proposed`, `accepted`, `superseded`, `deprecated` — use `proposed` until an
   explicit acceptance (e.g. a merged PR implementing it, or an owner sign-off);
   flip the line to `accepted` at that point rather than rewriting the rest of the
   record.
2. **Body.** An optional short intro paragraph, then `## Decision` (numbered/named
   subsections for a multi-part decision are fine), then `## Why` or a `## Context`
   section preceding `## Decision`, then `## Consequences`. Add a
   `## Live-state verification record` section when the decision depends on
   point-in-time ground truth (disk state, remote state, a specific commit) —
   record exactly what was checked and how, not just the conclusion.
3. **Immutability.** An accepted ADR is never rewritten to reflect new information —
   write a new, higher-numbered ADR that supersedes it (cross-link both directions)
   or, for a small in-scope correction, an inline `> **Update — ...**` blockquote at
   point of use.
4. **ADRs vs. `docs/plans/`.** An ADR records a durable decision and its rationale
   (rarely changes once accepted). A plan document records the execution detail for
   *carrying out* work — scope, sequencing, acceptance tests, an owner GO/NO-GO gate
   — and is expected to be superseded by later versions as work proceeds. A plan may
   cite the ADR that authorizes its architectural shape; an ADR should not carry
   execution/sequencing detail that belongs in a plan.
5. **Cursor-local plan files are not this.** Ephemeral `~/.cursor/plans/*.plan.md`
   files (or any other session-local planning artifact) are never committed to this
   repository and are not a substitute for either an ADR or a `docs/plans/` document.
   Once a Cursor-local plan is actioned, the durable decision/rationale belongs here
   and the durable execution record belongs in `docs/plans/`.
6. **Discoverability.** Read this file before adding a new architecture decision or
   trying to find out why an existing one was made. The root `AGENTS.md` points here.

## Index

| ADR | Status | One-line decision |
|---|---|---|
| [0001](0001-target-path-aware-mutation-scope.md) | Accepted — 2026-08-05 | Mutation-scope decisions must resolve and check actual command target path(s), not just cwd+verb; additive-only, conservative-fallback-preserving. |

## Related conventions

- `docs/plans/` (execution plans) has its own equivalent convention/index file —
  [`docs/plans/README.md`](../plans/README.md).
