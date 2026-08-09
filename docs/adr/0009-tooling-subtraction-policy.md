# ADR 0009: Tooling-subtraction policy — proof-to-kill, nothing subtracted now
Status: draft — 2026-08-06

## Decision

Subtract no MCP surface in this body of work. All nine tools are actively used and tested; the one
static resource is **retained** on live evidence (not policy-locked against future dynamic
siblings); and the declared-but-unbuilt catalog verbs are a **build gap** (closed by ADR 0005), not
a subtraction. Establish the durable rule: only genuinely unused/dormant surface may be removed;
any policy-locked or actively-used surface requires **proof-to-kill** — measured evidence of
non-utility, previewed and reversible, before removal.

## Why

- **Subtract the static resource (rejected).** The live-verify verdict is "RETAIN
  `awa://assistant/operator-guide/v1`" (`live-verify/RESULTS-MCP-GUIDANCE-BASELINE-20260709.md:5`).
  The finding is narrow: the resource added no *routing* score because it duplicates inline guidance
  (`:97`–`98`), yet its explicit on-demand fetch is proven useful (`:5`–`8`). That is an argument
  against a duplicative *static* resource's routing value, not a lock against the ADR 0007 dynamic
  siblings. Rejected.
- **Defer the policy (rejected).** Leaving "what may be removed" unstated invites ad-hoc removals of
  actively-used surface. Rejected in favor of a stated proof-to-kill rule.
- **Subtract nothing now + establish proof-to-kill (chosen).** All nine tools are live: the nine
  `_tool_*` handlers (`engine/mcp_server.py:60`–`143`) are declared in `_TOOLS`
  (`engine/mcp_server.py:145`) and dispatched by `handle` (`:476`). The catalog verbs
  `protect`/`save`/`resume`/`cleanup` carry `tool_path: mcp`
  (`consumer/intent-catalog.v1.json:29`/`102`/`83`/`122`) but have no executor
  (`consumer/operator_loop.py:151`,`:276`,`:389`) — a build gap ADR 0005 closes, not a surface to
  cut. v4 already codifies the discipline: "Existing tools stay available until measured evidence
  supports a separately versioned rename/removal" and the kill criterion "remove any resource/prompt
  /facade without measured utility" (v4 plan §"Non-negotiable invariants" / §"Out of scope and kill
  criteria").

## Consequences

- Enables: a clear, durable rule that distinguishes removable dormant surface from
  actively-used/policy-locked surface requiring proof-to-kill; honesty about the executor build gap
  as a gap, not a subtraction.
- Forecloses: any blind rename/removal this release; subtracting the retained static resource;
  treating the unbuilt `mcp` catalog verbs as evidence for removal.
- Must stay true: all nine tools remain available; the static resource remains retained; a future
  removal must present measured non-utility, a preview, and a rollback.
- Defers/creates: the executor build gap is closed by ADR 0005 (M3); count/URI-set drift gates
  (ADR 0002 / v4 FG5) enforce that additions and retentions are deliberate. Cross-links: ADR 0005
  (build gap it distinguishes), ADR 0007 (dynamic resources are additions, and the static resource
  is not locked against them), ADR 0002 (registry count discipline).
