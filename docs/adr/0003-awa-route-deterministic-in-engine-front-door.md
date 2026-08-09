# ADR 0003: awa_route — a deterministic, in-engine routing front door
Status: draft — 2026-08-06

## Decision

Add one MCP tool, `awa_route`, resolved entirely from the ADR 0002 capability graph. It exposes a
pinned, closed `awa-route/v1` schema — a `version` discriminator, closed enums for `state`
(including an explicit `invalid_request` reject branch), `source`, `route_kind`, `persistence`, and
`risk`; bounded `candidates[]`/`next_actions[]`; and the authority constants `executed: false` and
`authorized: false` on **every** branch. It runs an advisory finish/cleanup hand-off recognizer,
guarded by a parity gate against `consumer/finish_current.recognize_finish` (FG1/FG2). It never
executes, authorizes, confirms, echoes the request, or emits `Close`.

## Why

Live evidence shows that Cursor gives agents tool name/description/schema and
`initialize.instructions` automatically, but does **not** auto-inject resource descriptors; the one
static resource added zero routing coverage (`live-verify/RESULTS-MCP-GUIDANCE-BASELINE-20260709.md:5`).
So the discoverability answer is a deterministic tool, and the only safe place for it is the engine.

- **No front door (rejected).** Relying on metadata alone leaves ambiguous natural language with no
  single obvious entry point. The baseline scored 0/8 route+caveat metadata coverage before
  guidance existed (`RESULTS-MCP-GUIDANCE-BASELINE-20260709.md:10`–`12`); a deterministic router
  tool is what closes the discoverability gap without inventing a new authority.
- **Router-in-engine (rejected — violates the contamination boundary).** Importing or subprocessing
  an intent router from `engine/` would fail the test-enforced invariant:
  `engine/tests/test_consumer_contamination_structural.py:55`
  (`test_engine_imports_neither_consumer_nor_router`) AST-scans every `engine/*.py` (tests excluded,
  docstring at `:59`; `rglob("*.py")` at `:61`) and asserts zero `consumer`/`intent_router` imports
  (`for bad in ("consumer", "intent_router")` at `:65`) plus a router-artifact usage scan
  (`:68`–`70`). An in-engine router is therefore structurally impossible here by design.
- **Deterministic-in-engine (chosen).** `awa_route` resolves only from ADR 0002's engine-owned
  graph, so the contamination invariant stays trivially intact and the route table has one source.
  The pinned closed schema makes "never leaks on any branch" testable (an M6 test asserts
  `executed`/`authorized` are literal constant `false` in every branch including `invalid_request`,
  v4 FG1). Because the engine cannot import the authoritative `recognize_finish`
  (`consumer/finish_current.py:308`, a recall-only recognizer), `awa_route`'s advisory recognizer is
  a second wording surface that can drift — so a parity gate
  (`engine/tests/test_mcp_route_finish_parity.py`, modeled on `test_kernel_policy_parity.py`, engine
  tests may import `consumer`) asserts the two agree over a frozen corpus (v4 FG2).

## Consequences

- Enables: a single obvious front door that selects and explains a route (MCP tool, resource,
  kernel/engine CLI, consumer flow, or explicit `unsupported`), with required inputs, persistence,
  risk, authority, verification limit, and next action stated per route.
- Forecloses: any routing authority. `awa_route` performs finish/cleanup recognition as an
  **advisory hand-off only** — it points at the finish dialog and never runs the authoritative
  recognizer and never emits `Close`; kernel exact-`Close` authorization
  (`consumer/finish_current.py:333`–`334`) remains the sole gate. The authority constants and the
  parity gate are release-blocking.
- Must stay true: `awa_route` reads only the ADR 0002 graph (no consumer/router import), the schema
  stays additive-within-`v1`, and the parity gate runs in `make verify`.
- Defers/creates: the routing *strategy* (deterministic-only vs a gated router fallback) is
  measured and graduated in ADR 0004 — which complements this ADR today and would supersede its
  routing scope only if measurement reverses it. Cross-links: ADR 0002 (graph), ADR 0004 (routing
  graduation, bidirectional), ADR 0005 (lifecycle preview routes surface here as `consumer_flow`).
