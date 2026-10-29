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

## Convention reconciliation with doc-warden (2026-08-06)

> **New records authored under this convention (the MCP-expansion set 0011–0018, and ADRs going
> forward) adopt doc-warden's canonical shape** — see
> [`0017-adopt-and-reconcile-doc-warden-conventions.md`](0017-adopt-and-reconcile-doc-warden-conventions.md).
> New ADRs use doc-warden's status vocabulary `draft → accepted → superseded` (not the local
> `proposed`) and are **byte-identical-forever once accepted — no inline `> Update —` correction**
> (supersede with a higher-numbered ADR instead). This index keeps its local
> `ADR | Status | One-line decision` columns for now so the accepted **0001** row stays byte-identical;
> migrating to doc-warden's canonical `ADR | Title | Status | Date` is a deferred, operator-gated,
> index-only change under doc-warden's POC 3d. ADR 0001 is not retroactively re-governed — it keeps its
> local `proposed|accepted|superseded|deprecated` vocabulary and the inline-`> Update —` exception.

## Index

> **Numbering note.** ADR numbers **0003–0009 are intentionally unused.** The MCP-expansion set was
> first authored as 0002–0009, colliding with the accepted cross-repo-authority ADR that had already
> taken 0002 (and is referenced from `~/dev`). Because accepted numbers are never reused and that ADR
> could not move, the MCP-expansion set was renumbered to **0011–0018**; the 0003–0009 gap is deliberate.

| ADR | Status | One-line decision |
|---|---|---|
| [0001](0001-target-path-aware-mutation-scope.md) | Accepted — 2026-08-05 | Mutation-scope decisions must resolve and check actual command target path(s), not just cwd+verb; additive-only, conservative-fallback-preserving. |
| [0002](0002-awa-dev-overlay.md) | Accepted — 2026-08-06 | Cross-repo authority: `KleinPerkins/awa` is the sole canonical owner of AWA product statements; `~/dev` carries pointers to this repo, not second copies (poc3d profile, six governed topics). |
| [0010](0010-remote-dry-run-policy.md) | Accepted — 2026-08-23 | Keep fetch/push mutating and all dry-run forms denied; permit only ADR 0019's exact configured-upstream fetch on a clean protected primary as a decision-layer maintenance exception. |
| [0011](0011-mcp-capability-registry-single-source.md) | Draft — 2026-08-06 | One in-engine `engine/mcp_catalog.py` is the single source of truth for every MCP capability's metadata; all consumers (tools/list, validation, ordering, instructions, operator-guide, generated docs) derive from it (FG4). |
| [0012](0012-awa-route-deterministic-in-engine-front-door.md) | Draft — 2026-08-06 | Add a deterministic, in-engine `awa_route` front door with a pinned closed `awa-route/v1` schema (explicit reject branch; `executed`/`authorized` literal false on every branch) and a finish-recognizer parity gate (FG1/FG2). |
| [0013](0013-routing-strategy-graduation.md) | Draft — 2026-08-06 | Ship deterministic-first routing; graduate an out-of-engine router fallback only if it beats the frozen 96-run scorecard — gated + measured, never a dependency (complements ADR 0012). |
| [0014](0014-lifecycle-verbs-via-mcp-preview-kernel-gated.md) | Draft — 2026-08-06 | Lifecycle verbs (protect/save/resume/cleanup/finish) get MCP preview/propose surfaces only; the mutating/destructive step stays kernel-gated by a one-use operator-chat-turn envelope — no agent self-authorization. |
| [0015](0015-mcp-worktree-creation-and-path-whitelisting.md) | Draft — 2026-08-06 | MCP worktree provisioning is fused `dev-worktree.sh ensure` reuse (primary) + optional disposable scratch dir (secondary); whitelisting never downgrades an included primary checkout's protection (FG3 mirror). |
| [0016](0016-dynamic-resources-module-boundary.md) | Draft — 2026-08-06 | Expose engine-owned live state via a new `engine/mcp_dynamic_resources.py`, preserving `mcp_resources.py` zero-I/O purity; excludes consumer conversational state; persists no user text. |
| [0017](0017-adopt-and-reconcile-doc-warden-conventions.md) | Draft — 2026-08-06 | Adopt doc-warden's canonical conventions for new artifacts and reconcile AWA's five local divergences per-divergence; index-column migration deferred to an operator-gated POC 3d. |
| [0018](0018-tooling-subtraction-policy.md) | Draft — 2026-08-06 | Subtract no MCP surface now (all 9 tools used/tested; the one resource is retained); establish a durable proof-to-kill rule for any future removal. |
| [0019](0019-fast-forward-primary-carve-out.md) | Accepted — 2026-08-23 | Allow one exact configured-upstream fetch plus one clean upstream-bound `merge --ff-only --no-overwrite-ignore` as state-aware decision-layer maintenance exceptions; all development and unnecessary Git maintenance remain denied. |
| [0020](0020-awa-integrity-surveillance-and-lifecycle.md) | Accepted — 2026-08-24 | Guard-bug claim refuted; add one engine-side integrity evaluator, a status-last atomic `status.json` of record (live `mode=ro` reads), runnerless fast hooks + `local-jobs` deep sweep, always-attempted native/opt-in-Slack alerts, a self-staling static console, and read-only lifecycle reconciliation — no guard change; AWA owns product, `~/dev` owns host wiring. |
| [0021](0021-verification-and-discovery-velocity.md) | Accepted — 2026-08-29 | Adopt one measured verification DAG with explicit feedback/authority lanes, evidence-only receipts, equivalence-gated process isolation, independent fixtures, and display-only discovery optimization; narrowly supersede ADR 0020's guard-byte freeze only for equivalence-gated invocation-local probe collection, never guard behavior. |
| [0022](0022-two-worker-verification-default.md) | Accepted — 2026-08-30 | Make two process-isolated module workers the ordinary verification default after the owner accepted M2's equivalent, repeatable 22.376% gain; keep explicit serial fallback and all failure, cleanup, receipt, inventory, and dashboard guarantees. |
| [0023](0023-native-entry-registration-and-honest-worktree-metrics.md) | Superseded by ADR 0024 — 2026-09-25 | Add fail-open exact post-`sessionStart` adoption/attestation and private native-entry evidence for native Cursor worktrees; seed read-only lifecycle discovery from observations and report computed linked/managed/active/problem populations without changing cleanup authority. |
| [0024](0024-first-prompt-native-entry-recovery.md) | Accepted — 2026-09-25 | Adopt payload-bound first-prompt recovery because no documented Cursor event combines immediate workspace-entry timing with exact conversation identity; supersedes ADR 0023. |
| [0025](0025-durable-registration-episodes-and-tool-admission.md) | Accepted — C0-DESIGN NO-GO — 2026-09-26 | Propose single-root durable registration with one merged request/effect authority and member epoch, exact 7-table/9-trigger/97-generated-leaf manifest, direct OPEN authority, audit-only transition witness, stateless rendering, member-isolated admission, and distinct implementation/R1/C1/R2 gates; fresh exact-hash review/verifier adjudication remain C0 gates. |
| [0026](0026-durable-registration-authority-hardening.md) | Accepted — 2026-09-29 | Conditionally supersede ADR 0025 with canonical SQL v2, typed recovery boundaries, installer-selected measured interpreter capability, external-deny/internal custody, complete authority preimages, restart-stable recovery, offline owner gates, and separately gated evidence. |
| [0027](0027-hard-no-touch-host-policy.md) | Accepted — 2026-10-06 | Add an optional version-1 hard-no-touch host-policy field with immutable kernel/engine lexical matchers, component-boundary roots, fail-closed malformed input, and zero target access. |
| [0028](0028-govern-v1-8-maintenance-release-line.md) | Accepted — 2026-10-06 | Govern one protected `release/1.8` line from exact v1.8.1 for the PR #184 safety backport, with controller/ruleset-before-ref gates, reviewer-App-only merge, separate Release GO, one-way provenance, and explicit EOL. |
| [0029](0029-native-codex-interoperability-boundary.md) | Draft — 2026-10-28 | Propose a host-tagged Codex identity and evidence boundary, preserving explicit owner choice between bounded registration with visible residuals and full-parity unsupported status; no implementation authority. |

## Related conventions

- `docs/plans/` (execution plans) has its own equivalent convention/index file —
  [`docs/plans/README.md`](../plans/README.md).
