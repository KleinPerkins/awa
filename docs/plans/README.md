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
| `awa-integrity-surveillance-and-lifecycle-v1.md` | IMPLEMENTATION TASKS COMPLETE — 13/13; ROLLOUT GATES DEFERRED — 2026-09-17 | All active AWA implementation bodies through M3.1 merged (final body: [PR #165](https://github.com/KleinPerkins/awa/pull/165), `5b734c70`); M4 remains excluded by the accepted priority addendum. |
| `awa-integrity-execution-priority-addendum-v1.md` | ACCEPTED — 2026-08-28 | Current delivery priority only: Slack activation/integration stays deprioritized with the shipped adapter supported but opted out/unconfigured and native alerts as the M1 path; M2 → M3 remain after successful M1; M4 is removed from the active delivery sequence indefinitely pending explicit reprioritization. |
| `awa-integrity-m3-2-figma-interface-componentization-v1.md` | IMPLEMENTATION, RELEASE, AND SKILLS BINDING COMPLETE; INSTALLATION, HOST ACTIVATION, AND LIVE DESKTOP UAT PENDING — 2026-09-20 | M3.2-A/B/C merged in [PR #167](https://github.com/KleinPerkins/awa/pull/167), [PR #168](https://github.com/KleinPerkins/awa/pull/168), and [PR #169](https://github.com/KleinPerkins/awa/pull/169); [AWA PR #170](https://github.com/KleinPerkins/awa/pull/170) released v1.8.0 at `60ae49b4`, and [Skills PR #203](https://github.com/KleinPerkins/skills/pull/203) pins that commit. Rollout is not complete: the live runtime and `~/dev` host overlay remain on v1.7.3 pending installation, host activation, and live Cursor Desktop UAT. |
| `awa-verification-and-discovery-velocity-v1.md` | ACCEPTED — 2026-08-29 | Agentic-execution plan for ADR 0021: measured lane-aware verification (M1), equivalence-gated module sharding (M2), narrowly authorized guard/finish process reductions (M3–M4), fast display discovery (M5), and advisory runnerless regression governance (M6), with serial fallback and all safety behavior retained. |
| `native-entry-first-prompt-recovery-v1.md` | ACCEPTED — FROZEN — 2026-09-25 | Plan for ADR 0024's payload-bound first-prompt recovery, monotonic `awa-native-entry/v2` evidence, timeout-contained prompt adapter, and hook-owner v3; implementation GO recorded against `ff978ade5ff9c7604f58f4b3810b1cd75ea3287f`. |
| `native-entry-durable-registration-v2.md` | SUPERSEDED DRAFT — 2026-09-26 | Rejected as non-minimal and superseded by the v3 draft indexed immediately below; preserved byte-identically for provenance and never implementation authority. |
| `native-entry-durable-registration-v3.md` | ACCEPTED — C0-DESIGN NO-GO — 2026-09-26 | Single-root candidate with one merged request/effect authority and member epoch, exact 7-table/9-trigger/97-generated-leaf manifest, direct OPEN authority, audit-only transition witness, stateless rendering, member-isolated admission, and distinct implementation/R1/C1/R2 gates; fresh exact-hash review/verifier adjudication remain C0 gates. |
| `native-entry-durable-registration-v4.md` | ACCEPTED — GOVERNANCE ONLY; IMPLEMENTATION AND R0 NO-GO — 2026-09-29 | Conditional v3 successor with exact SQL v2, typed exhaustion, measured installer-selected interpreter, staged custody and >8 recovery, closed authority vectors, generation bundles, offline signing, status-last acceptance, three bodies, and finite-scope R0. |

## Related conventions

- `docs/adr/` (architecture decision records) has its own equivalent
  convention/index file — [`docs/adr/README.md`](../adr/README.md).
