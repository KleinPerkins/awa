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
   version), it is **frozen immutable** — never edit it again, including for typos, and
   (per doc-warden POLICY §9, adopted for new plans by ADR 0017) **not even a
   status-bullet edit**. A revision is always a **new** `-v<N+1>.md` file, preserving the
   prior version byte-identically, with the pointer stated explicitly in the new file's
   `**Supersedes:**` bullet; the prior version's frozen/superseded status is recorded in
   the **index row below only**, never by editing the accepted file.
4. **Body shape.** purpose and boundary → live-state verification → inherited
   scope/ground truth → numbered or lettered decisions → acceptance-test ledger →
   non-goals → owner GO/NO-GO gate → review provenance. Pick whichever skeleton fits
   a *new* document's shape and stay internally consistent within that document; do
   not retrofit an old file to a newer skeleton.
5. **Discoverability.** Any agent or reviewer starting work in this repo should read
   this file before writing a new plan or acting on an old one. The root `AGENTS.md`
   points here.

## Convention reconciliation with doc-warden (2026-08-06)

> **New plans adopt doc-warden's canonical shape going forward** — see the ADR-set meta-decision
> [`../adr/0017-adopt-and-reconcile-doc-warden-conventions.md`](../adr/0017-adopt-and-reconcile-doc-warden-conventions.md).
> New plans use doc-warden's status vocabulary `DRAFT → ACCEPTED → SUPERSEDED` (the local
> `APPROVED — FROZEN` / `COMPLETE` values remain valid for existing records). This index keeps its local
> `File | Status | One-line description` columns for now so the existing `guard-…` row stays
> byte-identical; migrating to doc-warden's canonical `Plan | Status | Date | Notes` is a deferred,
> operator-gated, index-only change under doc-warden's POC 3d.

## Index

| File | Status | One-line description |
|---|---|---|
| `guard-target-path-precision-v1.md` | COMPLETE — 2026-08-06 | Fix `beforeShellExecution` DENYing mutating commands whose resolved target path is outside every protected primary checkout (e.g. `rm /tmp/x` from inside a protected repo); establishes this `docs/` governance layer itself. |
| `awa-mcp-evolution-v1.md` | DRAFT — 2026-08-06 | Consolidates the v3/v4 MCP-discoverability floor and expands it: single-source capability registry, deterministic `awa_route`, kernel-gated MCP lifecycle previews, MCP worktree creation, engine-owned dynamic resources, and doc-warden alignment (ADRs 0011–0018). |
| `git-readonly-command-classifier-v1.md` | COMPLETE — 2026-08-10 | Refined the AWA shell guard's Git classifier so deterministic read-only nested commands such as `git worktree list --porcelain`, `git stash list/show`, and `git clean --dry-run` allow while mutating forms stay denied; implemented by PR #95. |
| `git-command-policy-hardening-v1.md` | DRAFT — 2026-08-11 | Prove and govern remote dry-run behavior, then fully classify branch, remote, config, submodule, and sparse-checkout forms with closed read-only grammars and conservative deny defaults. |
| `external-hook-owner-contract-v1.md` | ACCEPTED — 2026-08-15 | Add a persistent direct/external hook-file owner contract, preserve direct standalone defaults and all v1.5.1 behavior, and gate a tested v1.5.2 release for the serial Skills/Dev handoff. |
| `context-efficiency-s03-awa-operator-reduction-v1.md` | COMPLETE — 2026-08-20 | Reduced only the AWA-owned `awa-operator` projection in PR #116 and recorded hermetic v2 measurement, Bugbot, and fresh-agent canary evidence in `live-verify/RESULTS-context-efficiency-s03-20260820.md`. |
| `guard-fast-forward-primary-carve-out-v1.md` | ACCEPTED — 2026-08-23 | State-aware maintenance carve-out for one configured-upstream fetch plus an upstream-bound fast-forward of a clean protected primary; configured Git behavior remains trusted while development operations and unnecessary maintenance stay denied. Implementation requires a separate explicit GO. |
| `awa-integrity-surveillance-and-lifecycle-v1.md` | ACCEPTED — 2026-08-24 | Agentic-execution plan for ADR 0020: one evaluator + status-last atomic `status.json` + runnerless surveillance + attempted loud alerts + self-staling static console (M1, four serial Draft PRs A–D + two `~/dev` PRs), then read-only lifecycle reconciliation, digest-bound recovery quarantine, and entry handshake (M2). Guard unchanged; no autonomous deletion; separate GO required. |
| `awa-integrity-execution-priority-addendum-v1.md` | ACCEPTED — 2026-08-28 | Current delivery priority only: Slack activation/integration stays deprioritized with the shipped adapter supported but opted out/unconfigured and native alerts as the M1 path; M2 → M3 remain after successful M1; M4 is removed indefinitely pending explicit reprioritization. |

## Related conventions

- `docs/adr/` (architecture decision records) has its own equivalent
  convention/index file — [`docs/adr/README.md`](../adr/README.md).
