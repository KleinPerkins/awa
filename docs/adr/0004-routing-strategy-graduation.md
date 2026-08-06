# ADR 0004: Routing-strategy graduation — deterministic-first, router-fallback gated on the scorecard
Status: draft — 2026-08-06

## Decision

Ship deterministic-first routing (ADR 0003) as the default. Treat an out-of-engine router
*fallback* (the "fuse" strategy: deterministic-first plus an optional `source:router_suggestion`
proposal) as a separately gated enhancement that graduates only if it beats deterministic routing on
the frozen 96-run scorecard (18 eligible scenarios incl. 8 safety-critical + 6 negative controls, 2
model classes × 2 reps, with v4's split-rep rule). The router fallback is **never** a dependency:
deterministic routes must work with the router (and daemon, and SQLite) absent
(optional-component-off invariant). This ADR **complements** ADR 0003 today; if measurement later
reverses ADR 0003's routing scope, that reversal is recorded as a new ADR carrying
`Supersedes: ADR-0003` with a bidirectional cross-link — it is not pre-declared here, because the
measurement has not run.

## Why

- **Keep deterministic-only forever (rejected as a permanent ceiling).** Deterministic metadata
  routing already scored 8/8 on the route+caveat rubric
  (`live-verify/RESULTS-MCP-GUIDANCE-BASELINE-20260709.md:10`–`12`), so it is the correct first
  release. But permanently foreclosing a fuzzy fallback would discard a measurable improvement path
  the operator wants held open, so "deterministic-only, never revisit" is rejected in favor of
  "deterministic-first, fallback gated + measured."
- **Replace deterministic with a fuzzy router (rejected — safety + coupling).** Making a router the
  primary path would put a fuzzy component on the discoverability-critical path and risk the
  contamination boundary (`engine/tests/test_consumer_contamination_structural.py:55`). The router
  can only ever live out-of-engine; it must never become required.
- **Fuse: deterministic-first + optional out-of-engine router fallback (chosen).** AWA already pins
  the router it is proven against by an immutable commit SHA — `consumer/router-pin.json` pins
  `base_sha` `f44dbadd` (`:7`), and the seam test *skips* (never fails) when the router is not
  importable, preserving the kernel-first / off-switch property (`make verify` passes
  router-uninstalled), with a dedicated CI `router-seam` job that co-installs the pinned router and
  runs the seam non-skipped (`router-pin.json` `install_note`). v4 carries this design forward: an
  out-of-engine `consumer/`-owned wrapper invoked lazily in a bounded child process, where AWA
  validates every proposal against its own capability graph and *ignores* the router's routing,
  safety, and confirmation fields (v4 plan §M7 Phase 2). "In scope" therefore means gated + measured,
  never mandatory.

## Consequences

- Enables: a measured, operator-gated path to a fuzzy fallback without ever making it a dependency;
  the frozen scorecard + split-rep rule decide graduation (a split on a safety-critical scenario is
  a fail; on a non-safety-critical scenario it forces a rep increase to 4 before the merge
  decision).
- Forecloses: any release that blocks on an optional component's failure, or that ships a router on
  a mutable `main` rather than an immutable pinned SHA; the fallback owns its own launcher /
  `install.sh` / `mcp.json`-entry migration and rollback.
- Must stay true: deterministic routing works with router/daemon/SQLite absent (present-and-absent
  tested); the router's routing/safety/confirmation fields are never trusted.
- Defers/creates: the graduation *measurement* is a plan work item (M6 bulk matrix + M7 Phase 2),
  not performed by this ADR; its outcome is an explicit GO/NO-GO fork for the operator. Cross-links:
  ADR 0003 (routing front door this graduates, bidirectional), plan §M7 (Phase 2 gate).
