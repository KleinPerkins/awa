# ADR 0002: MCP capability registry as the single source of truth
Status: draft — 2026-08-06

## Decision

Introduce one in-engine Python module, `engine/mcp_catalog.py` (pure constants + validators, no
runtime I/O), as the sole authority for every MCP capability's stable id, name, input/output
schema, ordering, route kind, read/write/persistent/destructive class, authority + verification
limit, aliases/examples, and references. `tools/list`, argument validation, preferred ordering,
`initialize.instructions`, the operator-guide resource body, and the generated
`docs/MCP-CAPABILITY-REFERENCE.md` all derive from this one registry; handlers stay explicitly
bound (FG4). No second description source ships.

## Why

The MCP surface today already leans on a single tool dict, but that dict is a bare description
carrier, not a governed capability graph, and it is coupled to its renderers by a string-equality
gate rather than by a shared source. As new consumers arrive (`awa_route` per ADR 0003, dynamic
resources per ADR 0007, the generated doc, drift gates), that coupling is the drift risk.

- **Status quo — inline per-module metadata (rejected).** `engine/mcp_server.py` declares the nine
  tools in `_TOOLS` (`engine/mcp_server.py:145`, `awa_status` at `:146`) and derives
  `initialize.instructions` from it via `mcp_resources.render_guidance(_TOOLS)`
  (`engine/mcp_server.py:501`). The operator-guide resource renders from the *same* dict
  (`engine/mcp_resources.py:73` `render_operator_guide`). This is nearly single-source for tool
  *descriptions*, but it carries no schema/route-kind/authority/reference metadata, produces no
  generated doc, and (per v4 FG4) couples two renderers by an `instructions == operator-guide`
  string-equality assertion that breaks the moment `initialize.instructions` is intentionally made
  shorter than the full guide. Every new count/name site (`install_mcp_smoke.py`, `test_mcp.py`)
  is a separate hard-coded literal that drifts independently.
- **External schema file / package-data (rejected).** A JSON or `pyproject.toml`-packaged schema
  read at runtime would add packaging drift and a filesystem read on the hot path. v4 explicitly
  chose "pure Python constants + validators (no runtime JSON/package-data reads; avoids
  `pyproject.toml` packaging drift)" for exactly this reason (v4 plan §M1). A runtime read would
  also endanger the `engine/mcp_resources.py` zero-I/O purity invariant this ADR set preserves
  (`engine/mcp_resources.py:1`–`6`; see ADR 0007).
- **Registry-derived in-memory Python (chosen).** A pure-constant registry keeps zero runtime I/O,
  is the one place every consumer reads, and makes both the byte-identical generated-doc gate and
  the `len == len(registry)` count/URI-set gates mechanically checkable (v4 FG4/FG5). It composes
  cleanly with ADR 0003 (`awa_route` resolves only from this graph) and ADR 0007 (dynamic resources
  register as a route kind), so the whole surface has one authority.

## Consequences

- Enables: one authority for tools/list, validation, ordering, short instructions, operator-guide
  body, and generated reference; a byte-identical `docs/MCP-CAPABILITY-REFERENCE.md` drift gate;
  and tool-count + resource-count + full-URI-set gates expressed as `len == len(registry)` rather
  than integer literals (v4 FG5).
- Forecloses: a second description source. The current `instructions == operator-guide`
  equality gate is replaced by a registry-derivation gate; the short-instructions renderer is split
  from the full-guide renderer, both catalog-sourced (v4 FG4).
- Must stay true: the registry performs no I/O (determinism), and `engine/mcp_resources.py` stays
  pure (ADR 0007). Handlers remain explicitly bound — the registry describes and orders, it does
  not dispatch.
- Defers/creates: `engine/mcp_catalog.py` does not exist yet (confirmed absent at HEAD `bb85a5c`);
  it is the plan's M1 work item, not built by this ADR. This is a build gap, not a subtraction
  (ADR 0009). Cross-links: ADR 0003 (front door resolves from this graph), ADR 0007 (dynamic
  resources as a registered route kind), ADR 0009 (count-drift / proof-to-kill discipline).
